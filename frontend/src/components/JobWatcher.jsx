import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../store/api";

export default function JobWatcher({ jobId, onClose }) {
  const [data, setData] = useState(null);
  const [target, setTarget] = useState(null);
  const [findings, setFindings] = useState([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("log"); // "log" | "findings"
  const [query, setQuery] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);

  // verification filter: "verified" | "unverified" | "all"
  const [verFilter, setVerFilter] = useState("verified");

  // refresh UX
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  const timerRef = useRef(null);
  const logRef = useRef(null);

  // Report links
  const csvUrl = api.reportCsvUrl(jobId);
  const htmlUrl = api.reportHtmlUrl(jobId);
  const pdfUrl  = api.reportPdfUrl(jobId);

  const done = data?.status === "complete" || data?.status === "error";

  // ---------- helpers ----------
  const toVerifiedOnly = (filterMode) => {
    if (filterMode === "verified") return true;
    if (filterMode === "unverified") return false;
    return null;
  };

  const fetchFindings = async (filterMode, signal) => {
    setRefreshing(true);
    try {
      const verifiedOnly = toVerifiedOnly(filterMode);
      const f = await api.findingsForJob(jobId, {
        verifiedOnly,
        cacheBust: true,
        signal,
      });
      setFindings(Array.isArray(f) ? f : []);
      setError("");
      setLastRefreshed(new Date());
    } catch (e) {
      setError(`Refresh failed: ${e?.message || e}`);
    } finally {
      setRefreshing(false);
    }
  };

  const buildPathUrl = (path) => {
    try {
      if (!path) return null;
      const base = target?.base_url || "";
      return new URL(path, base).toString();
    } catch {
      return null;
    }
  };

  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); } catch {}
  };

  // ---------- lifecycle ----------
  useEffect(() => {
    setData(null);
    setTarget(null);
    setFindings([]);
    setError("");
    setTab("log");
    setQuery("");
    setVerFilter("verified");
    setAutoScroll(true);
    setRefreshing(false);
    setLastRefreshed(null);
  }, [jobId]);

  // Poll job status; when done, load findings
  useEffect(() => {
    if (!jobId) return;
    const ctrl = new AbortController();

    const poll = async () => {
      try {
        const d = await api.jobStatus(jobId, { signal: ctrl.signal });
        setData(d);

        if (d?.target_id && !target) {
          api.getTarget?.(d.target_id, { signal: ctrl.signal }).then(setTarget).catch(() => {});
        }

        if (d.status === "complete" || d.status === "error") {
          if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
          await fetchFindings(verFilter, ctrl.signal);
          setTab("findings");
        }
      } catch (e) {
        if (!ctrl.signal.aborted) setError(String(e?.message || e));
      }
    };

    poll();
    timerRef.current = setInterval(poll, 1200);

    return () => {
      ctrl.abort();
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  // When the verification filter changes and job is done, refetch
  useEffect(() => {
    if (!jobId || !done) return;
    const ctrl = new AbortController();
    fetchFindings(verFilter, ctrl.signal);
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verFilter, done, jobId]);

  // Autoscroll logs
  useEffect(() => {
    if (autoScroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [data?.log_tail, autoScroll]);

  // ESC to close
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // ----- smooth, neon progress -----
  const targetProgress = Number.isFinite(data?.progress) ? data.progress : 0;
  const [displayedProgress, setDisplayedProgress] = useState(0);

  useEffect(() => {
    // ease toward the backend progress
    let raf;
    const tick = () => {
      setDisplayedProgress((prev) => {
        const diff = targetProgress - prev;
        if (Math.abs(diff) < 0.2) return targetProgress; // snap when close
        return prev + diff * 0.15; // ease factor
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [targetProgress]);

  if (!jobId) return null;

  const status = data?.status || "queued";
  const statusDot =
    status === "complete" ? "bg-green-500" :
    status === "error" ? "bg-red-500" :
    "bg-yellow-500";

  // Counts (from the current dataset returned by API)
  const verifiedCount   = findings.filter((f) => (f.evidence_json || {}).verified === true).length;
  const unverifiedCount = findings.filter((f) => (f.evidence_json || {}).verified !== true).length;

  // Text classes
  const sevClass = (s) => {
    const t = (s || "").toLowerCase();
    if (t === "high") return "text-red-400";
    if (t === "medium") return "text-yellow-300";
    return "text-green-300";
  };

  const SeverityCell = ({ severity }) => {
    const t = (severity || "medium").toLowerCase();
    const dot =
      t === "high" ? "bg-red-500" : t === "medium" ? "bg-yellow-400" : "bg-green-400";
    return (
      <div className="flex items-center gap-2 capitalize">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot}`} />
        <span className={`font-body ${sevClass(severity)}`}>{severity || "unknown"}</span>
      </div>
    );
  };

  const VerifiedBadge = ({ ev }) => {
    const verified = ev?.verified === true;
    const st = ev?.status;
    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] border font-body ${
          verified
            ? "bg-green-900/30 border-green-700 text-green-300"
            : "bg-yellow-900/20 border-yellow-700 text-yellow-200"
        }`}
        title={verified ? "HTTP confirmed (200/401/403)" : "Not confirmed by HTTP probe"}
      >
        {verified ? "Verified" : "Unverified"}{typeof st !== "undefined" ? ` · ${st}` : ""}
      </span>
    );
  };

  const filtered = useMemo(() => {
    let rows = findings;
    if (verFilter === "unverified") {
      rows = rows.filter((f) => (f.evidence_json || {}).verified !== true);
    } else if (verFilter === "verified") {
      rows = rows.filter((f) => (f.evidence_json || {}).verified === true);
    }
    if (query.trim()) {
      const q = query.toLowerCase();
      rows = rows.filter(
        (f) =>
          (f.title || "").toLowerCase().includes(q) ||
          (f.category || "").toLowerCase().includes(q) ||
          (f.severity || "").toLowerCase().includes(q)
      );
    }
    return rows;
  }, [findings, query, verFilter]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-2 sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        className="w-[96vw] max-w-[1400px] h-[88vh] rounded-2xl bg-[#0f1117]/75 backdrop-blur-md border border-[#1f2430] shadow-2xl flex flex-col overflow-hidden glass"
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#1f2430]">
          <h2 className="text-lg text-white neon-title">Scan Job #{jobId}</h2>
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${statusDot}`} />
          <span className="text-sm text-gray-300 font-body">
            Status: <strong className="uppercase">{status}</strong>
          </span>

          {/* Target pill */}
          {target ? (
            <a
              className="ml-2 text-xs px-2 py-1 rounded bg-[#111827]/70 hover:bg-[#1f2937] border border-[#2b2f3a] text-gray-200 truncate max-w-[30%] font-body"
              href={target.base_url}
              target="_blank"
              rel="noopener noreferrer"
              title={target.base_url}
            >
              {target.name} · {target.base_url}
            </a>
          ) : null}

          <span className="ml-auto text-xs text-gray-400 font-body">
            {data?.started_at ? new Date(data.started_at).toLocaleString() : ""}
            {data?.finished_at ? ` → ${new Date(data.finished_at).toLocaleString()}` : ""}
          </span>
          <button
            onClick={onClose}
            className="ml-3 text-xs px-3 py-1.5 rounded-lg bg-[#1f2937] hover:bg-[#374151] text-gray-200 border border-[#2b2f3a] shadow-md hover:shadow-lg transition font-display btn-neon"
            aria-label="Close"
          >
            Close
          </button>
        </div>

        {/* Progress */}
        <div className="px-4 pt-3">
          <div className="relative w-full h-3 rounded-lg overflow-hidden bg-[#0b0d13] border border-[#1f2430] neon-ring progress-shimmer">
            {/* filled bar */}
            <div
              className="h-full transition-[width] duration-300 ease-out progress-glow"
              style={{
                width: `${Math.max(0, Math.min(100, displayedProgress))}%`,
                background:
                  "linear-gradient(90deg, rgba(34,211,238,1) 0%, rgba(147,51,234,1) 50%, rgba(59,130,246,1) 100%)",
                filter: "saturate(120%)",
              }}
            />
            {/* shimmer stripes, clipped to current width */}
            <div
              className="absolute inset-0 pointer-events-none progress-stripes"
              style={{ clipPath: `inset(0 ${100 - Math.max(0, Math.min(100, displayedProgress))}% 0 0)` }}
            />
          </div>
          <div className="mt-1 text-[11px] text-gray-400 font-body">{Math.round(displayedProgress)}%</div>
        </div>

        {/* Tabs */}
        <div className="px-4 pt-3">
          <div className="inline-flex items-center gap-1 rounded-lg bg-[#0b0d13] border border-[#1f2430] p-1">
            <button
              className={`px-3 py-1 text-sm rounded font-display ${tab === "log" ? "bg-[#111827] text-white" : "text-gray-300"}`}
              onClick={() => setTab("log")}
            >
              Log
            </button>
            <button
              className={`px-3 py-1 text-sm rounded font-display ${tab === "findings" ? "bg-[#111827] text-white" : "text-gray-300"}`}
              onClick={() => setTab("findings")}
              disabled={!done}
              title={!done ? "Available when job finishes" : ""}
            >
              Findings
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 p-4 overflow-hidden">
          {tab === "log" && (
            <div className="h-full flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <div className="text-xs text-gray-400 font-body">
                  Autoscroll
                  <label className="ml-2 inline-flex items-center gap-2 text-gray-200">
                    <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
                    <span className="text-xs text-gray-300">{autoScroll ? "On" : "Off"}</span>
                  </label>
                </div>
                {error && (
                  <div className="text-xs text-red-300 bg-red-900/30 border border-red-900 rounded px-2 py-1 font-body">
                    {error}
                  </div>
                )}
              </div>
              <div
                ref={logRef}
                className="text-xs text-gray-200 bg-[#0b0d13]/80 backdrop-blur-sm border border-[#1f2430] rounded-lg p-3 flex-1 overflow-auto"
              >
                <pre className="whitespace-pre-wrap break-words font-mono">
                  {data?.log_tail || "Waiting for output..."}
                </pre>
              </div>
            </div>
          )}

          {tab === "findings" && (
            <div className="h-full flex flex-col gap-3">
              {/* Actions */}
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search title/severity/category…"
                  className="px-3 py-1.5 text-sm rounded-lg bg-[#0b0d13] border border-[#1f2430] text-gray-200 w-72
                             shadow-md hover:shadow-lg focus-visible:ring-neon outline-none transition font-body"
                />
                <select
                  value={verFilter}
                  onChange={(e) => setVerFilter(e.target.value)}
                  className="px-3 py-1.5 text-sm rounded-lg bg-[#0b0d13] border border-[#1f2430] text-gray-200
                             shadow-md hover:shadow-lg focus-visible:ring-neon outline-none transition font-body"
                  title="Verification filter"
                >
                  <option value="verified">Only verified</option>
                  <option value="unverified">Only unverified</option>
                  <option value="all">All</option>
                </select>

                <span className="text-xs text-gray-400 font-body">
                  {verifiedCount} verified · {unverifiedCount} unverified
                </span>

                <button
                  onClick={() => fetchFindings(verFilter)}
                  disabled={refreshing}
                  className={`ml-2 text-sm px-4 py-2 rounded-lg border border-[#2b2f3a] font-display
                    ${refreshing ? "bg-[#222] text-gray-400 cursor-not-allowed" : "bg-[#1f2937] hover:bg-[#374151] text-gray-200 shadow-md hover:shadow-lg transition btn-neon"}`}
                  title="Refresh findings from server"
                >
                  {refreshing ? "Refreshing…" : "Refresh"}
                </button>

                {lastRefreshed && (
                  <span className="text-xs text-gray-500 ml-1 font-body">
                    Updated {lastRefreshed.toLocaleTimeString()}
                  </span>
                )}

                <div className="ml-auto flex gap-2">
                  <a
                    className="text-sm px-4 py-2 rounded-lg bg-[#1f2937] hover:bg-[#374151] text-gray-200 border border-[#2b2f3a] shadow-md hover:shadow-lg transition font-display btn-neon"
                    href={csvUrl}
                    download
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Export CSV
                  </a>
                  <a
                    className="text-sm px-4 py-2 rounded-lg bg-[#1f2937] hover:bg-[#374151] text-gray-200 border border-[#2b2f3a] shadow-md hover:shadow-lg transition font-display btn-neon"
                    href={htmlUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open HTML Report
                  </a>
                  <a
                    className="text-sm px-4 py-2 rounded-lg bg-[#1f2937] hover:bg-[#374151] text-gray-200 border border-[#2b2f3a] shadow-md hover:shadow-lg transition font-display btn-neon"
                    href={pdfUrl}
                    download
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    PDF
                  </a>
                </div>
              </div>

              {/* Refresh error (findings tab) */}
              {error && (
                <div className="text-xs text-red-300 bg-red-900/30 border border-red-900 rounded px-2 py-1 font-body">
                  {error}
                </div>
              )}

              {/* Table */}
              <div className="flex-1 overflow-auto rounded border border-[#1f2430] bg-[#0b0d13]/80 backdrop-blur-sm">
                {filtered.length ? (
                  <table className="table-fixed min-w-full text-sm">
                    <colgroup>
                      <col className="w-28" />
                      <col />
                      <col className="w-64" />
                    </colgroup>
                    <thead className="bg-[#0f1117] sticky top-0">
                      <tr>
                        <th className="px-3 py-2 text-left font-display">Severity</th>
                        <th className="px-3 py-2 text-left font-display">Title</th>
                        <th className="px-3 py-2 text-left font-display">Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((f) => {
                        const ev = f?.evidence_json || {};
                        const pathUrl = buildPathUrl(ev.path);
                        const isVerified = ev.verified === true;
                        return (
                          <tr
                            key={f.id ?? `${f.title}-${Math.random()}`}
                            className={`border-t border-[#1f2430] align-top
                                        odd:bg-[#0f1117]/60 even:bg-[#0b0d13]/60
                                        hover:bg-white/5 transition-colors
                                        ${isVerified ? "" : "bg-yellow-900/5"}`}
                          >
                            <td className="px-3 py-2">
                              <SeverityCell severity={f.severity} />
                            </td>
                            <td className="px-3 py-2 whitespace-pre-wrap break-words">
                              <div className="text-gray-200 font-body">{f.title}</div>
                              <div className="text-xs text-gray-400 mt-1 font-body">{f.category || "nikto"}</div>
                            </td>
                            <td className="px-3 py-2">
                              <div className="flex flex-col gap-1">
                                <VerifiedBadge ev={ev} />
                                {ev.path ? (
                                  <div className="text-xs text-gray-400 truncate font-body" title={ev.path}>
                                    Path: {ev.path}
                                  </div>
                                ) : null}
                                <div className="flex items-center gap-2">
                                  {isVerified && pathUrl ? (
                                    <a
                                      className="text-xs underline text-blue-300 hover:text-blue-200 font-body"
                                      href={pathUrl}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                    >
                                      Open
                                    </a>
                                  ) : null}
                                  {ev.path ? (
                                    <button
                                      className="text-xs underline text-gray-300 hover:text-gray-200 font-body"
                                      onClick={() => copy(ev.path)}
                                      title="Copy path"
                                    >
                                      Copy
                                    </button>
                                  ) : null}
                                </div>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                ) : (
                  <div className="p-3 text-xs text-gray-400 font-body">No findings match your filters.</div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-[#1f2430] text-right">
          <button
            onClick={onClose}
            className="text-sm px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-100 transition font-display btn-neon"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
