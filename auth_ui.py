"""Sign-in / sign-up screens and the 'remember me' cookie."""
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from core import auth

COOKIE = "sf_session"


def _cookie_js(value: str, max_age: int) -> None:
    components.html(
        f"<script>window.parent.document.cookie = '{COOKIE}={value}; path=/; max-age={max_age}; SameSite=Lax';</script>",
        height=0,
    )


def flush_cookie() -> None:
    """Write (or clear) the login cookie queued by the previous run."""
    pending = st.session_state.pop("cookie_pending", None)
    if pending is not None:
        _cookie_js(pending, auth.SESSION_DAYS * 86400 if pending else 0)


def current_user():
    token = st.session_state.get("token")
    if token is None and not st.session_state.get("logged_out"):
        token = st.context.cookies.get(COOKIE)
    user = auth.user_for_token(token)
    if user:
        st.session_state["token"] = token
    return user


def _start_session(user) -> None:
    token = auth.create_session(user.id)
    st.session_state["token"] = token
    st.session_state["cookie_pending"] = token
    st.session_state.pop("logged_out", None)
    st.rerun()


def log_out() -> None:
    auth.end_session(st.session_state.get("token"))
    st.session_state.clear()
    st.session_state["logged_out"] = True
    st.session_state["cookie_pending"] = ""
    st.rerun()


def login_screen() -> None:
    st.markdown("<div style='height:4vh'></div>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.title("📈 Stock Fundamentals")
        if not auth.has_users():
            st.write("Sign in to continue.")
            with st.form("login_empty"):
                st.text_input("Username", key="le_u")
                st.text_input("Password", type="password", key="le_p")
                if st.form_submit_button("Sign in", type="primary", use_container_width=True):
                    st.error("Wrong username or password.")
            with st.expander("Owner setup"):
                st.caption("For the owner only: enter the setup code to create the admin account. "
                           "Running locally, it's in data/admin_setup_code.txt (and printed in the black console "
                           "window). When deployed, it's the ADMIN_SETUP_CODE secret.")
                with st.form("first_admin"):
                    code = st.text_input("Setup code", type="password")
                    u = st.text_input("Username")
                    n = st.text_input("Display name")
                    e = st.text_input("Email")
                    p1 = st.text_input("Password", type="password")
                    p2 = st.text_input("Confirm password", type="password")
                    if st.form_submit_button("Create admin account", use_container_width=True):
                        if p1 != p2:
                            st.error("Passwords don't match.")
                        else:
                            try:
                                _start_session(auth.sign_up(u, p1, e, n, admin_code=code))
                            except auth.AuthError as err:
                                st.error(str(err))
            return

        invite = st.query_params.get("invite", "")
        tab_in, tab_up = st.tabs(["Sign in", "Create account"])
        with tab_in:
            with st.form("login"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in", type="primary", use_container_width=True):
                    try:
                        _start_session(auth.log_in(u, p))
                    except auth.AuthError as err:
                        st.error(str(err))
        with tab_up:
            st.caption("Accounts are invite-only. Ask the admin for an invite link or code.")
            with st.form("signup"):
                code = st.text_input("Invite code", value=invite)
                u = st.text_input("Username", key="su_u")
                n = st.text_input("Display name", key="su_n")
                e = st.text_input("Email", key="su_e")
                p1 = st.text_input("Password (8+ characters)", type="password", key="su_p1")
                p2 = st.text_input("Confirm password", type="password", key="su_p2")
                if st.form_submit_button("Create account", type="primary", use_container_width=True):
                    if p1 != p2:
                        st.error("Passwords don't match.")
                    else:
                        try:
                            _start_session(auth.sign_up(u, p1, e, n, code))
                        except auth.AuthError as err:
                            st.error(str(err))


def account_page(user) -> None:
    st.title("Your account")
    st.write(f"Signed in as **{user.display_name or user.username}** (`{user.username}`)"
             + (" · admin" if user.is_admin else ""))
    with st.form("pw"):
        st.subheader("Change password")
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password (8+ characters)", type="password")
        if st.form_submit_button("Update password"):
            try:
                auth.change_password(user.id, old, new)
                st.success("Password updated.")
            except auth.AuthError as err:
                st.error(str(err))
    if st.button("Sign out"):
        log_out()
