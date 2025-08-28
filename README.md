# VX_Rec0n — Reconnaissance Platform (Sprint 1–3)

**Last Updated:** 2025-08-17 09:53 UTC

VX_Rec0n is a lightweight network/web reconnaissance platform that automates vulnerability scans, stores findings, and generates exportable reports.

---

## 📦 Tech Stack
- **Backend:** FastAPI (Python), SQLModel, Alembic, httpx  
- **Database:** Postgres 15 (Dockerized)  
- **Frontend:** React (Vite + TailwindCSS)  
- **Scanner:** Nikto (Docker container)  

---

## ✅ Features (Sprint 1–3 Complete)
### Sprint 1 — Environment & Skeleton Setup
- FastAPI backend skeleton with models, API routes, and Postgres via Docker Compose.  
- Vite + React + TailwindCSS frontend with health check component.

### Sprint 2 — Targets & Jobs
- Add, list, and delete targets.  
- Start scan jobs against targets.  
- Job status + logs.

### Sprint 3 — Scanning Engine & Findings
- Nikto integration (runs via Docker).  
- Findings stored with evidence JSON (`tool`, `raw`, `verified`, `path`, `status`, `content_length`).  
- Verification logic: 200/401/403 = verified (loose policy).  
- Frontend job watcher: live status, findings table, verified/unverified filter.  
- Export reports in CSV, HTML, PDF, JSON.

---

## ⚙️ Prerequisites
- Python 3.11+  
- Node.js 18+  
- Docker Desktop / Docker Engine  
- **wkhtmltopdf** (recommended) or Playwright (for PDF export)  

---

## 🚀 Quick Start

### 1) Start Postgres
```bash
docker compose up -d postgres
```

### 2) Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt

# Run DB migrations
alembic upgrade head

# Run FastAPI
uvicorn app.main:app --reload --port 8000
```

### 3) Frontend
```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

---

## 🔗 API Overview

### Health
```
GET /health
```

### Targets
```
GET    /api/targets
POST   /api/targets
DELETE /api/targets/{id}
```

### Jobs
```
POST   /api/jobs/start/{target_id}   # Start scan
GET    /api/jobs/{job_id}/status     # Job status/log
GET    /api/jobs/{job_id}/findings   # Findings (filter by verified_only=true|false)
```

### Reports
```
GET /api/jobs/{job_id}/report.csv
GET /api/jobs/{job_id}/report.html
GET /api/jobs/{job_id}/report.pdf
GET /api/jobs/{job_id}/report.json
```

---

## 🖥 Frontend Features
- Add targets from UI.  
- Start scans, view job status + logs.  
- Findings table with severity, path, verification badge.  
- Filters: verified / unverified / all.  
- Export reports (CSV, HTML, PDF, JSON).  

---

## 🧪 Example Finding JSON
```json
{
  "tool": "nikto",
  "raw": "Directory indexing found at /public/",
  "verified": true,
  "path": "/public/",
  "status": 200,
  "content_length": "1234"
}
```

---

## ⚠️ Notes
- Most findings appear as **verified** because Nikto often triggers 401/403 responses.  
- This is expected with the current “loose” verification policy.  

---

## 🛡️ Legal Disclaimer
Only use VX_Rec0n against systems you own or are authorized to test. Unauthorized scanning is illegal.