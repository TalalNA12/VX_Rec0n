from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.settings import settings
from app.core.db import init_db
from app.api.targets import router as targets_router
from app.api.jobs import router as jobs_router

app = FastAPI(title="VX_Rec0n API")

# CORS (dev-friendly). For production, set FRONTEND_ORIGIN in .env and keep this as-is.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],  # during early dev you can use ["*"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # Create tables if they don't exist
    init_db()

# Centralize prefixes here to avoid double-prefix mistakes
app.include_router(targets_router, prefix="/api/targets", tags=["Targets"])
app.include_router(jobs_router,    prefix="/api/jobs",    tags=["Jobs"])

@app.get("/health")
def health():
    return {"ok": True}

