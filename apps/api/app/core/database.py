from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def _connect_args(url: str) -> dict:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


engine = create_engine(settings().database_url, future=True, pool_pre_ping=True, connect_args=_connect_args(settings().database_url))
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def session_scope():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
