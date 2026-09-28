"""Stock Fundamentals: 20 quarters of SEC-reported financials, segment breakdowns and competitor comparison.

Run locally:  streamlit run app.py   (or double-click run.bat on Windows)
Deploy:       see DEPLOY.md
"""
from __future__ import annotations

import os

import streamlit as st

st.set_page_config(page_title="Stock Fundamentals", page_icon=":material/insights:", layout="wide")

# Deployed secrets (Streamlit Cloud "Secrets", or .streamlit/secrets.toml) -> environment
try:
    for _k in ("DATABASE_URL", "SEC_USER_AGENT", "ADMIN_SETUP_CODE"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass  # no secrets file: local mode

from core import db  # noqa: E402  (after secrets are loaded)
from ui import auth_ui, style  # noqa: E402
from ui.admin import admin_page  # noqa: E402
from ui.analyze import analyze_page  # noqa: E402

style.inject()

try:
    db.engine()
except Exception as exc:
    st.error(f"Can't connect to the database: {exc}")
    st.stop()

if "setup_code_printed" not in st.session_state:
    from core import auth as _auth
    if not _auth.has_users() and not os.environ.get("ADMIN_SETUP_CODE"):
        print(f"\n  Owner setup code (needed once to create the admin account): {_auth.setup_code()}\n", flush=True)
    st.session_state["setup_code_printed"] = True

auth_ui.flush_cookie()
user = auth_ui.current_user()
if not user:
    auth_ui.login_screen()
    st.stop()

with st.sidebar:
    style.brand()
    pages = ["Analyze", "Account"] + (["Admin"] if user.is_admin else [])
    page = st.radio("Page", pages, horizontal=True, label_visibility="collapsed")
    style.user_chip(user.display_name or user.username)

if page == "Analyze":
    analyze_page(user)
elif page == "Admin":
    admin_page(user)
else:
    auth_ui.account_page(user)
