"""Accounts: invite-only sign-up, password login, remember-me sessions.

The very first account created becomes the admin and needs no invite.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import timedelta

from sqlalchemy import func, select

from .db import Invite, LoginSession, User, session, utcnow
from .settings import APP_DIR

SESSION_DAYS = 30


class AuthError(ValueError):
    pass


# ------------------------------------------------------------------ passwords (scrypt, stdlib only)

def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def check_password(pw: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt_b64), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


# ------------------------------------------------------------------ users

def has_users() -> bool:
    with session() as s:
        return (s.scalar(select(func.count(User.id))) or 0) > 0


def _clean_username(u: str) -> str:
    u = (u or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,32}", u):
        raise AuthError("Username must be 3–32 characters: letters, numbers, dot, dash or underscore.")
    return u


def setup_code() -> str:
    """Private code needed to create the first (admin) account.

    Deployed: set the ADMIN_SETUP_CODE secret. Local: generated once and saved to data/admin_setup_code.txt
    (also printed in the console window), so only the person running the computer/server can see it.
    """
    env = os.environ.get("ADMIN_SETUP_CODE", "").strip()
    if env:
        return env
    path = APP_DIR / "data" / "admin_setup_code.txt"
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_hex(4).upper(), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def sign_up(username: str, password: str, email: str = "", display_name: str = "", invite_code: str = "",
            admin_code: str = "") -> User:
    username = _clean_username(username)
    if len(password or "") < 8:
        raise AuthError("Password must be at least 8 characters.")
    with session() as s:
        first = (s.scalar(select(func.count(User.id))) or 0) == 0
        inv = None
        if first and not hmac.compare_digest((admin_code or "").strip().upper(), setup_code().upper()):
            raise AuthError("Wrong setup code.")
        if not first:
            inv = s.get(Invite, (invite_code or "").strip())
            if not inv or inv.revoked or inv.uses >= inv.max_uses:
                raise AuthError("That invite code isn't valid or has already been used.")
        if s.scalar(select(User).where(User.username == username)):
            raise AuthError("That username is taken.")
        user = User(username=username, email=(email or "").strip(), display_name=(display_name or "").strip() or username,
                    pw_hash=hash_password(password), is_admin=first, invite_code=inv.code if inv else None)
        s.add(user)
        if inv:
            inv.uses += 1
        s.commit()
        return user


def log_in(username: str, password: str) -> User:
    with session() as s:
        user = s.scalar(select(User).where(User.username == (username or "").strip().lower()))
        if not user or not check_password(password or "", user.pw_hash):
            raise AuthError("Wrong username or password.")
        if not user.is_active:
            raise AuthError("This account has been disabled.")
        user.last_login_at = utcnow()
        s.commit()
        return user


def change_password(user_id: int, old: str, new: str) -> None:
    if len(new or "") < 8:
        raise AuthError("New password must be at least 8 characters.")
    with session() as s:
        user = s.get(User, user_id)
        if not user or not check_password(old, user.pw_hash):
            raise AuthError("Current password is wrong.")
        user.pw_hash = hash_password(new)
        s.commit()


def reset_password(user_id: int) -> str:
    """Admin action: returns a new temporary password."""
    temp = secrets.token_urlsafe(9)
    with session() as s:
        u = s.get(User, user_id)
        u.pw_hash = hash_password(temp)
        s.execute(LoginSession.__table__.delete().where(LoginSession.user_id == user_id))
        s.commit()
    return temp


# ------------------------------------------------------------------ sessions (remember me)

def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with session() as s:
        s.add(LoginSession(token=token, user_id=user_id, expires_at=utcnow() + timedelta(days=SESSION_DAYS)))
        s.commit()
    return token


def user_for_token(token: str | None) -> User | None:
    if not token:
        return None
    with session() as s:
        ls = s.get(LoginSession, token)
        if not ls or ls.expires_at < utcnow():
            return None
        user = s.get(User, ls.user_id)
        return user if user and user.is_active else None


def end_session(token: str | None) -> None:
    if not token:
        return
    with session() as s:
        ls = s.get(LoginSession, token)
        if ls:
            s.delete(ls)
            s.commit()


# ------------------------------------------------------------------ invites + admin

def create_invite(created_by: int, note: str = "", max_uses: int = 1) -> str:
    code = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:10].upper()
    with session() as s:
        s.add(Invite(code=code, note=note.strip(), created_by=created_by, max_uses=max(1, int(max_uses))))
        s.commit()
    return code


def list_invites():
    with session() as s:
        return s.scalars(select(Invite).order_by(Invite.created_at.desc())).all()


def revoke_invite(code: str) -> None:
    with session() as s:
        inv = s.get(Invite, code)
        if inv:
            inv.revoked = True
            s.commit()


def list_users():
    with session() as s:
        return s.scalars(select(User).order_by(User.created_at)).all()


def set_user_flags(user_id: int, *, is_admin: bool | None = None, is_active: bool | None = None) -> None:
    with session() as s:
        u = s.get(User, user_id)
        if is_admin is not None:
            u.is_admin = is_admin
        if is_active is not None:
            u.is_active = is_active
            if not is_active:
                s.execute(LoginSession.__table__.delete().where(LoginSession.user_id == user_id))
        s.commit()
