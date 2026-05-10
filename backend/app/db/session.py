"""SQLAlchemy engine, session factory, and FastAPI DB dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# pool_pre_ping avoids handing out stale connections after DB restarts.
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for ORM models."""

    pass


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for the request scope; closes after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
