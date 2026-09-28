"""Backend storage: users, invites, login sessions and a log of every equity requested.

Uses DATABASE_URL when set (e.g. a free Neon/Supabase Postgres when deployed);
otherwise a local SQLite file at data/app.db.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String, create_engine, func,
                        select, text)
from sqlalchemy.orm import declarative_base, sessionmaker

from .settings import APP_DIR

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255))
    display_name = Column(String(128))
    pw_hash = Column(String(512), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    invite_code = Column(String(64))
    created_at = Column(DateTime, default=utcnow)
    last_login_at = Column(DateTime)


class Invite(Base):
    __tablename__ = "invites"
    code = Column(String(64), primary_key=True)
    note = Column(String(255))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=utcnow)
    max_uses = Column(Integer, default=1, nullable=False)
    uses = Column(Integer, default=0, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)


class LoginSession(Base):
    __tablename__ = "sessions"
    token = Column(String(128), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)


class Request(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    ticker = Column(String(16), nullable=False, index=True)
    company = Column(String(255))
    kind = Column(String(16), nullable=False, default="view")   # view | peer | export
    created_at = Column(DateTime, default=utcnow, index=True)


_engine = None
_Session = None


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # Name the driver explicitly: SQLAlchemy 2.1+ defaults to "psycopg" (v3), but we install psycopg2.
        # Also accepts Heroku-style postgres:// URLs.
        return re.sub(r"^postgres(ql)?://", "postgresql+psycopg2://", url)
    data = APP_DIR / "data"
    data.mkdir(exist_ok=True)
    return f"sqlite:///{(data / 'app.db').as_posix()}"


def engine():
    global _engine, _Session
    if _engine is None:
        url = database_url()
        kw = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kw["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kw)
        Base.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session():
    engine()
    return _Session()


def backend_name() -> str:
    return "PostgreSQL" if database_url().startswith("postgresql") else "SQLite (local file)"


# ------------------------------------------------------------------ request tracking

def log_request(user_id: int | None, ticker: str, company: str | None = None, kind: str = "view") -> None:
    try:
        with session() as s:
            s.add(Request(user_id=user_id, ticker=ticker.upper(), company=company, kind=kind))
            s.commit()
    except Exception:
        pass  # tracking must never break the app


def usage_frame(days: int | None = None) -> pd.DataFrame:
    """Every request joined with the username, newest first."""
    q = (select(Request.created_at, Request.ticker, Request.company, Request.kind, User.username)
         .join(User, User.id == Request.user_id, isouter=True)
         .order_by(Request.created_at.desc()))
    if days:
        q = q.where(Request.created_at >= utcnow() - timedelta(days=days))
    with engine().connect() as c:
        rows = c.execute(q).fetchall()
    return pd.DataFrame(rows, columns=["when_utc", "ticker", "company", "kind", "user"])


def counts() -> dict:
    with session() as s:
        return {
            "users": s.scalar(select(func.count(User.id))) or 0,
            "requests": s.scalar(select(func.count(Request.id))) or 0,
            "tickers": s.scalar(select(func.count(func.distinct(Request.ticker)))) or 0,
        }


def ping() -> bool:
    with engine().connect() as c:
        c.execute(text("select 1"))
    return True
