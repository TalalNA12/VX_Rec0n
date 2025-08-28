from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import delete as sa_delete
from sqlmodel import select
from typing import List

# DB session dependency
try:
    from app.core.db import get_db  # shared dependency if present
except Exception:
    from app.core.db import SessionLocal
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

from app.models.models import Target, Job, Finding  # <-- include Finding

# NOTE: main.py should include: app.include_router(targets_router, prefix="/api/targets")
router = APIRouter(tags=["Targets"])

@router.get("", response_model=List[Target])
def list_targets(db: Session = Depends(get_db)):
    return db.execute(select(Target).order_by(Target.id)).scalars().all()

@router.get("/{target_id}", response_model=Target)
def get_target(target_id: int, db: Session = Depends(get_db)):
    t = db.get(Target, target_id)
    if not t:
        raise HTTPException(status_code=404, detail="Target not found")
    return t

@router.post("", response_model=Target)
def create_target(t: Target, db: Session = Depends(get_db)):
    if not t.name or not t.base_url:
        raise HTTPException(status_code=422, detail="name and base_url are required")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t

@router.put("/{target_id}", response_model=Target)
def update_target(target_id: int, payload: Target, db: Session = Depends(get_db)):
    t = db.get(Target, target_id)
    if not t:
        raise HTTPException(status_code=404, detail="Target not found")

    # update allowable fields
    t.name = payload.name or t.name
    t.base_url = payload.base_url or t.base_url
    # handle bool/None carefully
    if getattr(payload, "is_lab_only", None) is not None:
        t.is_lab_only = payload.is_lab_only
    if getattr(payload, "notes", None) is not None:
        t.notes = payload.notes

    db.add(t)
    db.commit()
    db.refresh(t)
    return t

@router.delete("/{target_id}")
def delete_target(target_id: int, db: Session = Depends(get_db)):
    """
    Hard-delete a target and all of its child rows (jobs, findings).
    This makes the UI Delete button succeed even if the target has history.
    """
    t = db.get(Target, target_id)
    if not t:
        raise HTTPException(status_code=404, detail="Target not found")

    # 1) gather job ids
    job_ids = [jid for (jid,) in db.execute(select(Job.id).where(Job.target_id == target_id)).all()]

    # 2) delete findings for those jobs
    if job_ids:
        db.execute(sa_delete(Finding).where(Finding.job_id.in_(job_ids)))

    # 3) delete jobs
    if job_ids:
        db.execute(sa_delete(Job).where(Job.id.in_(job_ids)))

    # 4) delete target
    db.delete(t)
    db.commit()

    return {"ok": True, "deleted_id": target_id, "purged_jobs": len(job_ids)}
