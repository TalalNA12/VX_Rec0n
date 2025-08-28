# backend/app/core/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from app.core.settings import settings

# Import models so they are registered with SQLModel metadata
from app.models.models import Target, Job, Finding  # noqa: F401

# Engine: pre-ping to avoid stale connections
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

# Session factory:
# - autoflush=False for explicit flushes
# - autocommit=False (transactional)
# - expire_on_commit=False so returned objects keep attribute values after commit
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

def init_db() -> None:
    """Create all tables registered on SQLModel metadata."""
    SQLModel.metadata.create_all(engine)

def get_db():
    """
    FastAPI dependency for a request-scoped DB session.

    Usage:
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
