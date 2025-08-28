# backend/app/api/jobs.py
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from sqlalchemy.orm import Session
from datetime import datetime
import subprocess
import threading
from urllib.parse import urlparse, urljoin
from sqlmodel import select
from app.core.db import SessionLocal
import os, io, csv, re, html, logging, shutil, time, importlib
from typing import List, Optional
from collections import deque

import httpx  # used for verifying findings

from app.core.settings import settings
from app.models.models import Job, Target, Finding

# ---- scan tuning (env overrides) ----
REQ_TIMEOUT = float(os.getenv("SCAN_TIMEOUT_S", "8"))   # httpx timeout (s)
REQ_DELAY_S = float(os.getenv("SCAN_DELAY_S", "0"))     # delay between requests (s)
SCAN_MAX_PAGES = int(os.getenv("SCAN_MAX_PAGES", "60")) # crawler page cap
SCAN_MAX_DEPTH = int(os.getenv("SCAN_MAX_DEPTH", "2"))  # crawler depth
CUSTOM_UA     = os.getenv("SCAN_USER_AGENT", "VX_Rec0n")
AUTHZ_HDR     = os.getenv("SCAN_AUTHZ_HEADER", "X-Scan-Authorized")
AUTHZ_VAL     = os.getenv("SCAN_AUTHZ_VALUE", "TICKET-REQUIRED")

# Image selection (env can override settings)
IMAGE = os.getenv("NIKTO_IMAGE", getattr(settings, "NIKTO_IMAGE", "ghcr.io/sullo/nikto:latest"))

# Try to import a shared dependency; provide a local fallback if not present
try:
    from app.core.db import get_db  # type: ignore
except Exception:
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

# Router (prefix is added in main.py → "/api/jobs")
router = APIRouter(tags=["Jobs"])
logger = logging.getLogger(__name__)

# ---------- helpers ----------

def _docker_safe_target(url: str) -> str:
    """Map localhost to host.docker.internal so Nikto-in-Docker can reach host services."""
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        if host in {"localhost", "127.0.0.1"}:
            netloc = "host.docker.internal"
            if p.port:
                netloc += f":{p.port}"
            rebuilt = f"{p.scheme}://{netloc}{p.path or ''}"
            if p.query:
                rebuilt += f"?{p.query}"
            return rebuilt
        return url
    except Exception:
        return url

def _update_job(
    db: Session,
    job: Job,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    append_log: Optional[str] = None,
) -> None:
    changed = False
    if status is not None and job.status != status:
        job.status = status
        changed = True
    if progress is not None:
        job.progress = max(0, min(100, int(progress)))
        changed = True
    if append_log:
        tail = (job.log_tail or "") + append_log
        job.log_tail = tail[-4000:]  # keep last 4k chars
        changed = True
    if changed:
        db.add(job)
        db.commit()

def _ensure_image_pulled() -> bool:
    """If IMAGE isn't present locally, attempt a 'docker pull' once."""
    try:
        subprocess.run(
            ["docker", "image", "inspect", IMAGE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        p = subprocess.run(["docker", "pull", IMAGE], text=True, capture_output=True)
        return p.returncode == 0

# -------- Nikto parsing → Finding rows --------

F_IGNORE = re.compile(
    r"^\s*\+\s*(Nikto v|Start Time|End Time|Target (IP|Hostname|Port)|No CGI Directories|Server:|Retrieved|Uncommon header)",
    re.I,
)

def _classify_severity(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["remote code", "rce", "sql injection", "sqli", "xss", "authentication bypass"]):
        return "high"
    if any(k in t for k in ["directory indexing", "directory listing", "misconfiguration", "insecure"]):
        return "medium"
    if "header" in t or "info" in t:
        return "low"
    return "medium"

def _parse_nikto_findings(lines: List[str]) -> List[dict]:
    findings: List[dict] = []
    seen: set[str] = set()
    for raw in lines:
        s = raw.strip()
        if not s.startswith("+ "):
            continue
        if F_IGNORE.search(s):
            continue
        title = s[2:].strip()
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        findings.append({
            "category": "nikto",
            "title": title,
            "severity": _classify_severity(title),
            "evidence_json": {"tool": "nikto", "raw": title},
            "owasp_tags": ["A05:2021-Security Misconfiguration"],
            "confidence": "medium",
        })
    return findings

# ---- verification & dedupe ----

SUSPECT_EXTS = (
    ".pem", ".jks", ".p12", ".pfx", ".crt", ".cer",
    ".war", ".jar", ".ear",
    ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".zip", ".gz", ".bz2", ".lzma", ".alz",
    ".egg",
)
ALWAYS_SENSITIVE_PATHS = {"/.htpasswd"}

def _extract_path_from_title(title: str) -> Optional[str]:
    m = re.search(r"(/[\w\-./%~]+)", title)
    if m:
        return m.group(1)
    return None

def _verify_nikto_findings(base_url: str, findings: List[dict]) -> List[dict]:
    """Verify via HEAD (GET fallback) when a path is present."""
    base = base_url if re.match(r"^https?://", base_url, re.I) else f"http://{base_url}"

    out: List[dict] = []
    seen_verified_paths: set[str] = set()

    def bump_if_sensitive(sev: str, path: Optional[str]) -> str:
        if not path:
            return sev
        sensitive = (path in ALWAYS_SENSITIVE_PATHS) or any(path.lower().endswith(ext) for ext in SUSPECT_EXTS)
        return "high" if (sensitive and sev != "high") else sev

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=REQ_TIMEOUT,
            verify=False,
            headers={"User-Agent": CUSTOM_UA, AUTHZ_HDR: AUTHZ_VAL},
        ) as client:
            for f in findings:
                path = _extract_path_from_title(f["title"])
                if not path:
                    sev = bump_if_sensitive(f.get("severity", "medium"), None)
                    out.append({
                        **f,
                        "severity": sev,
                        "evidence_json": {
                            **(f.get("evidence_json") or {}),
                            "verified": False,
                            "path": None,
                            "status": None,
                            "content_length": None,
                            "note": "no path extracted; verification skipped",
                        },
                    })
                    continue

                url = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
                status_code: Optional[int] = None
                content_len: Optional[str] = None
                verified_flag = False
                err: Optional[str] = None

                try:
                    r = client.head(url)
                    status_code = r.status_code
                    if status_code in (405, 501):
                        r = client.get(url)
                        status_code = r.status_code
                    content_len = r.headers.get("content-length")
                    verified_flag = status_code in (200, 401, 403)
                except Exception as e:
                    err = str(e)

                if REQ_DELAY_S > 0:
                    time.sleep(REQ_DELAY_S)

                sev = bump_if_sensitive(f.get("severity", "medium"), path)

                if verified_flag:
                    key = path
                    if key in seen_verified_paths:
                        continue
                    seen_verified_paths.add(key)

                out.append({
                    **f,
                    "severity": sev,
                    "evidence_json": {
                        **(f.get("evidence_json") or {}),
                        "verified": verified_flag,
                        "path": path,
                        "status": status_code,
                        "content_length": content_len,
                        **({"error": err} if err else {}),
                    },
                })
    except Exception:
        return [{**f, "evidence_json": {**(f.get("evidence_json") or {}), "verified": False}} for f in findings]

    return out or [{**f, "evidence_json": {**(f.get("evidence_json") or {}), "verified": False}} for f in findings]

# ---------- extra modules (safe, non-evasive) ----------

def _audit_security_headers(base_url: str) -> List[dict]:
    """Single GET to base URL to audit common security headers & cookies."""
    out: List[dict] = []
    base = base_url if re.match(r"^https?://", base_url, re.I) else f"http://{base_url}"

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=REQ_TIMEOUT,
            verify=False,
            headers={"User-Agent": CUSTOM_UA, AUTHZ_HDR: AUTHZ_VAL},
        ) as client:
            r = client.get(base)
            h = {k.lower(): v for k, v in r.headers.items()}

            def add(title: str, severity="medium", category="headers", extra=None):
                out.append({
                    "category": category,
                    "title": title,
                    "severity": severity,
                    "evidence_json": {"verified": True, "status": r.status_code, "path": "/", **(extra or {})},
                    "owasp_tags": ["A05:2021-Security Misconfiguration"],
                    "confidence": "medium",
                })

            if base.lower().startswith("https://") and "strict-transport-security" not in h:
                add("Missing Strict-Transport-Security (HSTS) header", "medium")
            if "x-content-type-options" not in h:
                add("Missing X-Content-Type-Options: nosniff", "low")
            if ("content-security-policy" not in h) and ("x-frame-options" not in h):
                add("Missing CSP and X-Frame-Options (clickjacking exposure)", "medium")
            if "referrer-policy" not in h:
                add("Missing Referrer-Policy header", "low")
            if "permissions-policy" not in h and "feature-policy" not in h:
                add("Missing Permissions-Policy header", "low")

            set_cookies = []
            try:
                set_cookies = r.headers.get_list("set-cookie")  # type: ignore[attr-defined]
            except Exception:
                v = r.headers.get("set-cookie")
                if v:
                    set_cookies = [v]

            for raw_ck in set_cookies:
                low = raw_ck.lower()
                name = raw_ck.split("=", 1)[0].strip()
                missing = []
                if "secure" not in low and base.lower().startswith("https://"):
                    missing.append("Secure")
                if "httponly" not in low:
                    missing.append("HttpOnly")
                if "samesite" not in low:
                    missing.append("SameSite")
                if missing:
                    out.append({
                        "category": "cookies",
                        "title": f"Cookie '{name}' missing flags: {', '.join(missing)}",
                        "severity": "medium" if any(m.lower()=="secure" for m in missing) else "low",
                        "evidence_json": {"verified": True, "status": r.status_code, "path": "/", "cookie": raw_ck},
                        "owasp_tags": ["A05:2021-Security Misconfiguration"],
                        "confidence": "medium",
                    })
            return out
    except Exception as e:
        return [{
            "category": "headers",
            "title": f"Header audit failed: {e}",
            "severity": "low",
            "evidence_json": {"verified": False, "error": str(e)},
            "owasp_tags": ["A05:2021-Security Misconfiguration"],
            "confidence": "low",
        }]

def _same_origin(u1: str, u2: str) -> bool:
    try:
        a, b = urlparse(u1), urlparse(u2)
        return (a.scheme, a.hostname, a.port or (443 if a.scheme=="https" else 80)) == \
               (b.scheme, b.hostname, b.port or (443 if b.scheme=="https" else 80))
    except Exception:
        return False

def _crawl_and_discover(base_url: str) -> List[dict]:
    """
    BFS crawl within same origin; discover interesting files/paths (backups, creds, dotfiles, etc).
    If BeautifulSoup isn't available, we skip crawling cleanly (no editor warnings).
    """
    base = base_url if re.match(r"^https?://", base_url, re.I) else f"http://{base_url}"
    out: List[dict] = []
    seen_urls: set[str] = set()
    q = deque([(base, 0)])

    interesting_exts = {e.lower() for e in SUSPECT_EXTS}
    interesting_exact = set(ALWAYS_SENSITIVE_PATHS)

    # Dynamic import to avoid static-analysis warnings if bs4 isn't installed
    try:
        bs4_mod = importlib.import_module("bs4")
        BeautifulSoup = getattr(bs4_mod, "BeautifulSoup")
    except Exception:
        return [{
            "category": "crawler",
            "title": "Crawler disabled (install 'beautifulsoup4' to enable)",
            "severity": "low",
            "evidence_json": {"verified": False},
            "owasp_tags": ["A05:2021-Security Misconfiguration"],
            "confidence": "low",
        }]

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=REQ_TIMEOUT,
            verify=False,
            headers={"User-Agent": CUSTOM_UA, AUTHZ_HDR: AUTHZ_VAL},
        ) as client:

            while q and len(seen_urls) < SCAN_MAX_PAGES:
                url, depth = q.popleft()
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                try:
                    r = client.get(url)
                    html_text = r.text or ""
                except Exception:
                    continue

                try:
                    soup = BeautifulSoup(html_text, "html.parser")
                except Exception:
                    soup = None

                def enqueue(target):
                    try:
                        absolute = urljoin(url, target)
                        if _same_origin(base, absolute) and absolute not in seen_urls:
                            if depth < SCAN_MAX_DEPTH:
                                q.append((absolute, depth + 1))
                    except Exception:
                        pass

                if soup:
                    for tag in soup.find_all(["a", "script", "link", "img"]):
                        href = tag.get("href") or tag.get("src")
                        if href:
                            enqueue(href)

                # Check for sensitive-looking paths
                try:
                    pth = urlparse(url).path or "/"
                    path_lower = pth.lower()
                    looks_sensitive = (pth in interesting_exact) or any(path_lower.endswith(ext) for ext in interesting_exts)
                    if looks_sensitive:
                        code = None
                        content_len = None
                        err = None
                        try:
                            rr = client.head(url)
                            code = rr.status_code
                            if code in (405, 501):
                                rr = client.get(url)
                                code = rr.status_code
                            content_len = rr.headers.get("content-length")
                        except Exception as e:
                            err = str(e)

                        if REQ_DELAY_S > 0:
                            time.sleep(REQ_DELAY_S)

                        if code in (200, 401, 403):
                            out.append({
                                "category": "crawler",
                                "title": f"Discovered sensitive-looking path: {pth}",
                                "severity": "high" if any(path_lower.endswith(ext) for ext in interesting_exts) else "medium",
                                "evidence_json": {
                                    "verified": True,
                                    "path": pth,
                                    "status": code,
                                    "content_length": content_len,
                                },
                                "owasp_tags": ["A05:2021-Security Misconfiguration"],
                                "confidence": "medium",
                            })
                        else:
                            out.append({
                                "category": "crawler",
                                "title": f"Potential sensitive path (unverified): {pth}",
                                "severity": "medium",
                                "evidence_json": {"verified": False, "path": pth, **({"error": err} if err else {})},
                                "owasp_tags": ["A05:2021-Security Misconfiguration"],
                                "confidence": "low",
                            })
                except Exception:
                    pass

            return out

    except Exception as e:
        return [{
            "category": "crawler",
            "title": f"Crawler failed: {e}",
            "severity": "low",
            "evidence_json": {"verified": False, "error": str(e)},
            "owasp_tags": ["A05:2021-Security Misconfiguration"],
            "confidence": "low",
        }]

def _findings_to_csv(rows: List[Finding]) -> io.StringIO:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "job_id", "severity", "category", "title", "path", "http_status", "verified"])
    for f in rows:
        ev = f.evidence_json or {}
        w.writerow([
            f.id, f.job_id, f.severity, f.category, f.title,
            ev.get("path"), ev.get("status"), ev.get("verified"),
        ])
    buf.seek(0)
    return buf

# ---------- scan runner with live progress ----------

STATUS_PCT_RE = re.compile(r"\(~\s*(\d+)\s*%\s*complete", re.I)

def _run_nikto_scan(job_id: int, target_url: str):
    """Background worker: run Nikto via Docker, stream output into Job.log_tail."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        # start
        if getattr(job, "started_at", None) is None:
            job.started_at = datetime.utcnow()
        _update_job(db, job, status="running", progress=10,
                    append_log=f"Starting Nikto scan...\nUsing image: {IMAGE}\n")

        # image check
        if not _ensure_image_pulled():
            _update_job(db, job, status="error", progress=100,
                        append_log=f"ERROR: Could not pull image '{IMAGE}'. "
                                   "If you're behind a proxy or need auth, run 'docker login' and try again.\n")
            return

        safe_url = _docker_safe_target(target_url)
        job_tag = f"VX_Rec0nJob/{job_id}"
        cmd = [
            "docker", "run", "--rm",
            IMAGE,
            "-h", safe_url,
            "-nointeractive",
            "-useragent", job_tag,
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            _update_job(db, job, status="error", progress=100,
                        append_log="ERROR: Docker not found or not in PATH.\n")
            return

        buffer_lines: List[str] = []
        line_counter = 0
        last_progress = 10

        for line in iter(proc.stdout.readline, ""):
            buffer_lines.append(line)
            _update_job(db, job, append_log=line)

            # try to parse a "~5% complete" style line
            m = STATUS_PCT_RE.search(line)
            if m:
                pct = int(m.group(1))
                # cap Nikto's portion at 80%
                backend_pct = min(80, max(12, pct))
                if backend_pct > last_progress:
                    last_progress = backend_pct
                    _update_job(db, job, progress=backend_pct)
            else:
                # gentle trickle if Nikto doesn't print percentage frequently
                line_counter += 1
                if line_counter % 30 == 0 and last_progress < 80:
                    last_progress = min(80, last_progress + 1)
                    _update_job(db, job, progress=last_progress)

        proc.stdout.close()
        rc = proc.wait()

        # Nikto done; parsing/verify
        if last_progress < 85:
            last_progress = 85
            _update_job(db, job, progress=last_progress)

        try:
            parsed = _parse_nikto_findings(buffer_lines)
            verified = _verify_nikto_findings(target_url, parsed)

            if last_progress < 92:
                last_progress = 92
                _update_job(db, job, progress=last_progress)

            header_findings = _audit_security_headers(target_url)
            crawl_findings  = _crawl_and_discover(target_url)

            for f in (verified + header_findings + crawl_findings):
                db.add(Finding(
                    job_id=job.id,
                    category=f.get("category", "nikto"),
                    title=f.get("title", ""),
                    severity=f.get("severity", "medium"),
                    evidence_json=f.get("evidence_json"),
                    owasp_tags=f.get("owasp_tags"),
                    confidence=f.get("confidence", "medium"),
                ))
            db.commit()

            if last_progress < 96:
                last_progress = 96
                _update_job(db, job, progress=last_progress)

        except Exception:
            logger.exception("Failed to parse/store findings for job %s", job_id)

        # finalize
        job.finished_at = datetime.utcnow()
        if rc in (0, 1):
            _update_job(db, job, status="complete", progress=100,
                        append_log=f"\nScan finished with exit code {rc}.\n")
        elif rc == 125:
            _update_job(
                db, job, status="error", progress=100,
                append_log=(
                    "\nDocker failed to run the image (exit 125). "
                    f"Ensure '{IMAGE}' exists locally and 'docker login' succeeded.\n"
                ),
            )
        else:
            _update_job(db, job, status="error", progress=100,
                        append_log=f"\nNikto exited with code {rc}.\n")

    except Exception as e:
        try:
            job = db.get(Job, job_id)
            if job:
                job.finished_at = datetime.utcnow()
                _update_job(db, job, status="error", progress=100,
                            append_log=f"\nUNEXPECTED ERROR: {e}\n")
        except Exception:
            pass
    finally:
        db.close()

# ---------- routes ----------

@router.post("/{target_id}")
def start_job(target_id: int, db: Session = Depends(get_db)):
    """Enqueue a scan job for a target and return job_id."""
    target = db.get(Target, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    job = Job(
        target_id=target.id,
        type="scan",
        status="queued",
        progress=0,
        log_tail="Queued scan.\n",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    t = threading.Thread(target=_run_nikto_scan, args=(job.id, target.base_url), daemon=True)
    t.start()

    return {"job_id": job.id, "message": "Scan queued"}

@router.get("/{job_id}/status")
def job_status(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "log_tail": job.log_tail,
        "target_id": getattr(job, "target_id", None),
        "started_at": getattr(job, "started_at", None),
        "finished_at": getattr(job, "finished_at", None),
    }

@router.get("/by-target/{target_id}/latest")
def latest_job_for_target(target_id: int, db: Session = Depends(get_db)):
    """Return the most recent job for a given target (if any)."""
    q = (
        select(Job)
        .where(Job.target_id == target_id)
        .order_by(Job.started_at.desc().nullslast(), Job.id.desc())
        .limit(1)
    )
    job = db.execute(q).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="No jobs for this target")
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "log_tail": job.log_tail,
        "target_id": job.target_id,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }

# ---- findings + reports ----

@router.get("/{job_id}/findings", response_model=List[Finding])
def job_findings(
    job_id: int,
    db: Session = Depends(get_db),
    verified_only: Optional[str] = Query(
        None,
        description="true → only verified, false → only unverified, omitted → all",
    ),
):
    rows = db.execute(select(Finding).where(Finding.job_id == job_id)).scalars().all()

    val = (verified_only or "").strip().lower()
    if val in {"true", "1", "yes"}:
        rows = [f for f in rows if (f.evidence_json or {}).get("verified") is True]
    elif val in {"false", "0", "no"}:
        rows = [f for f in rows if (f.evidence_json or {}).get("verified") is not True]

    return rows

@router.get("/{job_id}/report.csv")
def job_report_csv(job_id: int, db: Session = Depends(get_db)):
    rows = db.execute(select(Finding).where(Finding.job_id == job_id)).scalars().all()
    buf = _findings_to_csv(rows)
    filename = f"vx_recon_job_{job_id}_findings.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )

_REPORT_HTML_TMPL = """<!doctype html>
<html><head><meta charset="utf-8"><title>VX_Rec0n Report #{job_id}</title>
<style>
body{{font-family:system-ui,Segoe UI,Roboto,Arial;padding:24px;background:#0b0b0f;color:#e5e7eb}}
table{{border-collapse:collapse;width:100%;margin-top:12px}}
th,td{{padding:8px 10px;border:1px solid #2b2f3a}}
th{{background:#0f1117;text-align:left}}
.sev-high{{color:#ef4444}}.sev-medium{{color:#f59e0b}}.sev-low{{color:#22c55e}}
small{{color:#9ca3af}}
</style></head><body>
<h1>VX_Rec0n Report <small>Job #{job_id}</small></h1>
<p><small>Target ID: {target_id} • Started: {started_at} • Finished: {finished_at}</small></p>
<table><thead><tr><th>Severity</th><th>Title</th><th>Category</th></tr></thead><tbody>
{rows}
</tbody></table></body></html>"""

def _row_html(f: Finding) -> str:
    sev = (getattr(f, "severity", None) or "medium").lower()
    cls = "sev-high" if sev == "high" else "sev-medium" if sev == "medium" else "sev-low"
    title = html.escape(getattr(f, "title", "") or "")
    category = html.escape(getattr(f, "category", "") or "")
    return f"<tr><td class='{cls}'>{sev.title()}</td><td>{title}</td><td>{category}</td></tr>"

@router.get("/{job_id}/report.html")
def job_report_html(job_id: int, db: Session = Depends(get_db)):
    try:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")

        rows = db.execute(select(Finding).where(Finding.job_id == job_id)).scalars().all()
        rows_html = "".join(_row_html(f) for f in rows) or "<tr><td colspan='3'><em>No findings</em></td></tr>"

        started = getattr(job, "started_at", None)
        finished = getattr(job, "finished_at", None)

        html_doc = _REPORT_HTML_TMPL.format(
            job_id=job.id,
            target_id=getattr(job, "target_id", ""),
            started_at=str(started or ""),
            finished_at=str(finished or ""),
            rows=rows_html,
        )
        return HTMLResponse(content=html_doc)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error building HTML report for job %s", job_id)
        return HTMLResponse(
            content=f"<pre>Report builder error: {html.escape(str(e))}</pre>",
            status_code=500,
        )

@router.get("/{job_id}/report.pdf")
def job_report_pdf(job_id: int, db: Session = Depends(get_db)):
    """
    PDF via wkhtmltopdf (pdfkit). If unavailable, return 503 with guidance.
    No Playwright import to avoid editor warnings.
    """
    html_resp = job_report_html(job_id, db)
    if not isinstance(html_resp, HTMLResponse) or html_resp.status_code != 200:
        return html_resp
    html_str = html_resp.body.decode("utf-8")

    try:
        import pdfkit  # type: ignore
        wkhtml_env = os.getenv("WKHTMLTOPDF_CMD")
        candidates = [
            wkhtml_env,
            r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
            r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
            shutil.which("wkhtmltopdf"),
        ]
        wkhtml_path = next((p for p in candidates if p and os.path.exists(p)), None)
        cfg = pdfkit.configuration(wkhtmltopdf=wkhtml_path) if wkhtml_path else None
        pdf_bytes = pdfkit.from_string(html_str, False, configuration=cfg)
        filename = f"vx_recon_job_{job_id}_report.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e1:
        raise HTTPException(
            status_code=503,
            detail=(
                "PDF export unavailable. Install wkhtmltopdf and the 'pdfkit' Python package "
                "(or use the HTML/CSV exports). Error: " + str(e1)
            ),
        )

@router.get("/{job_id}/report.json")
def job_report_json(job_id: int, db: Session = Depends(get_db)):
    rows = db.execute(select(Finding).where(Finding.job_id == job_id)).scalars().all()
    return rows

@router.get("/{job_id}/summary")
def job_summary(job_id: int, db: Session = Depends(get_db)):
    """Simple summary using in-Python JSON, no DB JSON ops."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    rows = db.execute(select(Finding).where(Finding.job_id == job_id)).scalars().all()
    total = len(rows)
    verified = sum(1 for f in rows if (f.evidence_json or {}).get("verified") is True)
    unverified = total - verified

    sev_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for f in rows:
        sev = (f.severity or "medium").lower()
        if sev in sev_dist:
            sev_dist[sev] += 1
        else:
            sev_dist["medium"] += 1

    target = db.get(Target, job.target_id) if job.target_id else None

    return {
        "job_id": job.id,
        "target": getattr(target, "base_url", None),
        "findings_count": total,
        "verified_count": verified,
        "unverified_count": unverified,
        "severity_distribution": sev_dist,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "status": job.status,
    }
