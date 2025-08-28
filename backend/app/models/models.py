from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON, CheckConstraint, Index  # ← added Index

# ---------------------------
# Target
# ---------------------------
class Target(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    base_url: str
    is_lab_only: bool = True

    # Arbitrary metadata as JSON (queryable)
    notes: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)

# ---------------------------
# Job
# ---------------------------
class Job(SQLModel, table=True):
    __table_args__ = (
        # keep progress sane
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_job_progress_0_100"),
        # fast “latest job per target” lookups
        Index("ix_job_target_started", "target_id", "started_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    target_id: int = Field(foreign_key="target.id")
    type: str  # e.g., "scan"
    status: str = "queued"  # queued|running|complete|error
    progress: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # Rolling tail of scan logs for quick UI feedback
    log_tail: Optional[str] = None

# ---------------------------
# Finding
# ---------------------------
class Finding(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")
    category: str
    title: str
    severity: str = "medium"  # low|medium|high|critical

    # Rich evidence and tags as JSON (queryable)
    evidence_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    remediation: Optional[str] = None
    owasp_tags: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))

    confidence: Optional[str] = "medium"
