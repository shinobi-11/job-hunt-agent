"""User authentication — signup, login, session cookies."""
from __future__ import annotations

import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, EmailStr, Field

from config import get_config

SESSION_COOKIE = "jha_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

_serializer: Optional[URLSafeTimedSerializer] = None


def _secret() -> str:
    return os.environ.get("SESSION_SECRET") or "dev-only-secret-change-in-prod-please"


def _ser() -> URLSafeTimedSerializer:
    global _serializer
    if _serializer is None:
        _serializer = URLSafeTimedSerializer(_secret(), salt="jha-session")
    return _serializer


def _is_postgres() -> bool:
    return bool(os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")))


def _connect():
    """Open a connection to the active backend (psycopg2 for PG, sqlite3 for local)."""
    if _is_postgres():
        import psycopg2
        return psycopg2.connect(os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1))
    cfg = get_config()
    p = Path(cfg.database_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(p)


def _placeholder() -> str:
    return "%s" if _is_postgres() else "?"


def init_users_table() -> None:
    """Create the users table on whichever backend is active."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ─── Models ──────────────────────────────────────────────────────────

class SignupPayload(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8, max_length=200)
    name: str = Field("", max_length=120)


class LoginPayload(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None
    created_at: str | None


# ─── Password hashing ────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ─── User CRUD ───────────────────────────────────────────────────────

def _row_to_dict(cur, row):
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def create_user(email: str, password: str, name: str = "") -> dict:
    if not EMAIL_RE.match(email):
        raise ValueError("Invalid email format")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    user_id = f"u_{uuid.uuid4().hex[:16]}"
    pw_hash = hash_password(password)
    ph = _placeholder()

    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                f"INSERT INTO users (id, email, password_hash, name) VALUES ({ph},{ph},{ph},{ph})",
                (user_id, email.lower().strip(), pw_hash, name.strip()),
            )
            conn.commit()
        except Exception as e:
            if "unique" in str(e).lower() or "duplicate" in str(e).lower() or isinstance(e, sqlite3.IntegrityError):
                raise ValueError("An account with this email already exists")
            raise
    finally:
        conn.close()

    return {"id": user_id, "email": email.lower(), "name": name, "created_at": datetime.now().isoformat()}


def find_user_by_email(email: str) -> Optional[dict]:
    ph = _placeholder()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, email, password_hash, name, created_at FROM users WHERE email = {ph}",
            (email.lower().strip(),),
        )
        return _row_to_dict(cur, cur.fetchone())
    finally:
        conn.close()


def find_user_by_id(user_id: str) -> Optional[dict]:
    ph = _placeholder()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, email, name, created_at FROM users WHERE id = {ph}",
            (user_id,),
        )
        return _row_to_dict(cur, cur.fetchone())
    finally:
        conn.close()


def authenticate(email: str, password: str) -> Optional[dict]:
    user = find_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    ph = _placeholder()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = {ph}", (user["id"],))
        conn.commit()
    finally:
        conn.close()
    return {k: v for k, v in user.items() if k != "password_hash"}


# ─── Session management ──────────────────────────────────────────────

def issue_session(response: Response, user_id: str) -> None:
    token = _ser().dumps({"uid": user_id, "iat": datetime.utcnow().isoformat()})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def read_session_user_id(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        data = _ser().loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    except Exception:
        return None
    return data.get("uid") if isinstance(data, dict) else None


def get_current_user(jha_session: Optional[str] = Cookie(default=None)) -> Optional[dict]:
    uid = read_session_user_id(jha_session)
    if not uid:
        return None
    return find_user_by_id(uid)


def require_user(user: Optional[dict] = Depends(get_current_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Login required")
    return user
