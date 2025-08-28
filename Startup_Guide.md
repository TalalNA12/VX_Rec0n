VX_Rec0n — Startup Guide (v1 / Sprint 3)

FastAPI + React + Tailwind + Postgres + Nikto (Docker)

Contents

Prerequisites

Quick Start (Daily)

First-Time Setup (One-Time)

Postgres (Docker) – Create / Reset

Backend – Run

Frontend – Run

Demo Target (Juice Shop)

API Smoke Tests

Findings Filters

PDF Export Options

Troubleshooting

Emergency SQLite Fallback

Useful Commands

Prerequisites

Docker Desktop (running; WSL2 enabled)

Python 3.10+ (3.12 is fine)

Node.js LTS (for Vite/React)

(Optional) wkhtmltopdf or Playwright Chromium for PDF export

Quick Start (Daily)
# 0) Start Docker Desktop (idempotent)
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
Start-Service -Name com.docker.service -ErrorAction SilentlyContinue
$deadline=(Get-Date).AddMinutes(2); while((Get-Date) -lt $deadline){ try { docker version | Out-Null; break } catch { Start-Sleep 3 } }
docker start vx_postgres 2>$null
docker exec -it vx_postgres psql -U vx -d vx_rec0n -c "\conninfo"

# 1) Backend
cd C:\Users\PMLS\vx_rec0n\backend
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL = "postgresql+psycopg://vx:vxpass@localhost:5432/vx_rec0n"
$env:NIKTO_IMAGE  = "ghcr.io/sullo/nikto:latest"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 2) Frontend (new terminal)
cd C:\Users\PMLS\vx_rec0n\frontend
npm run dev


Open the Vite URL (usually http://localhost:5173).
Health check: Invoke-RestMethod http://127.0.0.1:8000/health → {"status":"ok"}

First-Time Setup (One-Time)
# A) Docker readiness
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
Start-Service -Name com.docker.service -ErrorAction SilentlyContinue
$deadline=(Get-Date).AddMinutes(2); while((Get-Date) -lt $deadline){ try { docker version | Out-Null; break } catch { Start-Sleep 3 } }
docker version

# B) Postgres container (create once)
docker run -d --name vx_postgres `
  -e POSTGRES_USER=vx `
  -e POSTGRES_PASSWORD=vxpass `
  -e POSTGRES_DB=vx_rec0n `
  -p 5432:5432 `
  -v vx_pgdata:/var/lib/postgresql/data `
  postgres:15
docker exec -it vx_postgres psql -U vx -d vx_rec0n -c "\conninfo"

# C) Backend virtualenv + deps (create once)
cd C:\Users\PMLS\vx_rec0n\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install fastapi uvicorn[standard] sqlmodel pydantic-settings httpx psycopg[binary] pdfkit
# If you have requirements.txt:
# pip install -r requirements.txt

# D) Frontend deps (create once)
cd C:\Users\PMLS\vx_rec0n\frontend
npm install

Postgres (Docker) – Create / Reset

Create (fresh):

docker rm -f vx_postgres 2>$null
docker run -d --name vx_postgres `
  -e POSTGRES_USER=vx `
  -e POSTGRES_PASSWORD=vxpass `
  -e POSTGRES_DB=vx_rec0n `
  -p 5432:5432 `
  -v vx_pgdata:/var/lib/postgresql/data `
  postgres:15
docker exec -it vx_postgres psql -U vx -d vx_rec0n -c "\conninfo"


Full reset (nuclear):

docker rm -f vx_postgres
docker volume rm vx_pgdata
# then re-create with the block above

Backend – Run
cd C:\Users\PMLS\vx_rec0n\backend
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL = "postgresql+psycopg://vx:vxpass@localhost:5432/vx_rec0n"
$env:NIKTO_IMAGE  = "ghcr.io/sullo/nikto:latest"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000


Health:

Invoke-RestMethod http://127.0.0.1:8000/health

Frontend – Run
cd C:\Users\PMLS\vx_rec0n\frontend
npm run dev

Demo Target (Juice Shop)
# Use 3000 or 3001 if busy
docker rm -f juice-shop 2>$null
docker run -d --name juice-shop -p 3000:3000 bkimminich/juice-shop
# If 3000 is taken:
# docker run -d --name juice-shop -p 3001:3000 bkimminich/juice-shop


In the UI → Add Target

Name: Juice Shop

URL: http://localhost:3000 (or http://localhost:3001)
Click Start Scan.

API Smoke Tests
# Health
Invoke-RestMethod http://127.0.0.1:8000/health

# Targets
Invoke-RestMethod http://127.0.0.1:8000/api/targets
Invoke-RestMethod -Method POST `
  -Uri http://127.0.0.1:8000/api/targets `
  -ContentType "application/json" `
  -Body (@{ name="Juice Shop"; base_url="http://localhost:3000"; is_lab_only=$true } | ConvertTo-Json)

# Jobs
Invoke-RestMethod -Method POST http://127.0.0.1:8000/api/jobs/1          # start
Invoke-RestMethod http://127.0.0.1:8000/api/jobs/by-target/1/latest      # latest job

# Findings (All / Only verified / Only unverified)
Invoke-RestMethod "http://127.0.0.1:8000/api/jobs/2/findings"
Invoke-RestMethod "http://127.0.0.1:8000/api/jobs/2/findings?verified_only=true"
Invoke-RestMethod "http://127.0.0.1:8000/api/jobs/2/findings?verified_only=false"

# Reports
start http://127.0.0.1:8000/api/jobs/2/report.html
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/jobs/2/report.csv -OutFile report.csv
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/jobs/2/report.pdf -OutFile report.pdf

Findings Filters

UI (Findings tab):

“Only verified” / “Only unverified” / “All”

API (tri-state query):

verified_only=true → return only verified

verified_only=false → return only unverified

omit param → all findings

PDF Export Options

Pick one:

wkhtmltopdf installed (recommended)

Playwright with system Edge

Playwright bundling Chromium

pip install playwright
python -m playwright install chromium

Troubleshooting

Backend import error (get_session not found)

You’re on the fixed code path: jobs.py uses Depends(get_db) only. If you ever see this again, ensure there’s no get_session import in backend/app/api/jobs.py.

Cannot connect to Postgres / ConnectionTimeout

Docker Desktop must be running.

Ensure container exists & is up:

docker start vx_postgres 2>$null
docker exec -it vx_postgres psql -U vx -d vx_rec0n -c "\conninfo"


If the DB/role is missing, recreate the container with the env vars (see “Create (fresh)”).

Port 5432 already in use

netstat -ano | Select-String ":5432"
Stop-Process -Id <PID>  # or stop that service/app


Then start Postgres.

Nikto image pull issues

docker pull ghcr.io/sullo/nikto:latest
# If needed:
docker login ghcr.io


Only verified results show up

Set filter to All or Only unverified in the UI.

Compare these API counts:

/findings

/findings?verified_only=true

/findings?verified_only=false

PDF export fails

Install wkhtmltopdf, or use Playwright & run the install chromium step.

Emergency SQLite Fallback

Run backend with SQLite (no Docker required):

cd C:\Users\PMLS\vx_rec0n\backend
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL = "sqlite:///./vx.db"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Useful Commands
# Start Docker & wait
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
Start-Service -Name com.docker.service -ErrorAction SilentlyContinue
$deadline=(Get-Date).AddMinutes(2); while((Get-Date) -lt $deadline){ try { docker version | Out-Null; break } catch { Start-Sleep 3 } }

# DB sanity
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
docker exec -it vx_postgres psql -U vx -d vx_rec0n -c "\l"
docker exec -it vx_postgres psql -U vx -d vx_rec0n -c "\dt"

# Reset DB (danger)
docker rm -f vx_postgres
docker volume rm vx_pgdata

# Backend env
cd C:\Users\PMLS\vx_rec0n\backend
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL = "postgresql+psycopg://vx:vxpass@localhost:5432/vx_rec0n"
$env:NIKTO_IMAGE  = "ghcr.io/sullo/nikto:latest"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend
cd C:\Users\PMLS\vx_rec0n\frontend
npm run dev

Notes

On Windows, the Nikto container can’t hit localhost; backend rewrites to host.docker.internal automatically.

Reports available: CSV, HTML, PDF.

“Delete target” cascades to child jobs and findings in the backend code.