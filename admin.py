"""Admin: usage analytics (which equities people request), users, invites and settings."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from core import auth, db
from core.settings import load_settings, save_settings, sec_user_agent
from ui import charts


def _invite_link(code: str) -> str:
    try:
        base = st.context.url.split("?")[0]
    except Exception:
        base = ""
    return f"{base}?invite={code}" if base else code


def admin_page(user) -> None:
    st.title("Admin")
    t_usage, t_users, t_inv, t_set = st.tabs(["📊 Usage", "👥 Users", "✉️ Invites", "⚙️ Settings"])

    with t_usage:
        c = db.counts()
        m = st.columns(3)
        m[0].metric("Users", c["users"])
        m[1].metric("Requests logged", c["requests"])
        m[2].metric("Distinct equities", c["tickers"])
        period = st.radio("Period", ["7 days", "30 days", "90 days", "All time"], index=1, horizontal=True)
        days = {"7 days": 7, "30 days": 30, "90 days": 90, "All time": None}[period]
        df = db.usage_frame(days)
        if df.empty:
            st.info("No requests yet in this period.")
        else:
            views = df[df["kind"] == "view"]
            left, right = st.columns(2)
            with left:
                top = views.groupby("ticker").size().nlargest(15)
                if len(top):
                    st.plotly_chart(charts.usage_bar(top, "Most-requested equities"), use_container_width=True,
                                    config={"displayModeBar": False})
            with right:
                peers = df[df["kind"] == "peer"].groupby("ticker").size().nlargest(15)
                if len(peers):
                    st.plotly_chart(charts.usage_bar(peers, "Most-compared competitors"), use_container_width=True,
                                    config={"displayModeBar": False})
            daily = df.set_index(pd.to_datetime(df["when_utc"])).resample("D").size()
            st.plotly_chart(charts.daily_chart(daily), use_container_width=True, config={"displayModeBar": False})

            st.subheader("By user")
            by_user = (df.groupby("user").agg(requests=("ticker", "size"), equities=("ticker", "nunique"),
                                              last_seen=("when_utc", "max"))
                       .sort_values("requests", ascending=False))
            top_t = views.groupby(["user", "ticker"]).size().reset_index(name="n").sort_values("n", ascending=False)
            by_user["favourites"] = [", ".join(top_t[top_t["user"] == u]["ticker"].head(5)) for u in by_user.index]
            st.dataframe(by_user, use_container_width=True)

            st.subheader("Request log")
            st.dataframe(df, use_container_width=True, hide_index=True, height=320)
            st.download_button("⬇ Download log (CSV)", df.to_csv(index=False).encode(), "requests.csv", "text/csv")

    with t_users:
        users = auth.list_users()
        st.dataframe(pd.DataFrame([{
            "username": u.username, "name": u.display_name, "email": u.email, "admin": u.is_admin,
            "active": u.is_active, "invite": u.invite_code, "joined (UTC)": u.created_at, "last login (UTC)": u.last_login_at,
        } for u in users]), hide_index=True, use_container_width=True)
        others = [u for u in users if u.id != user.id]
        if others:
            by_id = {u.id: u for u in others}
            pick = by_id[st.selectbox("Manage user", list(by_id), format_func=lambda i: f"{by_id[i].username} ({by_id[i].display_name})")]
            a, b, c = st.columns(3)
            if a.button("Make admin" if not pick.is_admin else "Remove admin"):
                auth.set_user_flags(pick.id, is_admin=not pick.is_admin)
                st.rerun()
            if b.button("Disable account" if pick.is_active else "Re-enable account"):
                auth.set_user_flags(pick.id, is_active=not pick.is_active)
                st.rerun()
            if c.button("Reset password"):
                temp = auth.reset_password(pick.id)
                st.success(f"Temporary password for {pick.username}: `{temp}` — send it to them privately.")

    with t_inv:
        with st.form("new_invite"):
            note = st.text_input("Who is it for? (note)")
            uses = st.number_input("How many sign-ups can use it", 1, 100, 1)
            if st.form_submit_button("Create invite", type="primary"):
                code = auth.create_invite(user.id, note, uses)
                st.success("Invite created. Send this link (or the code):")
                st.code(_invite_link(code))
        invs = auth.list_invites()
        if invs:
            st.dataframe(pd.DataFrame([{
                "code": i.code, "note": i.note, "used": f"{i.uses}/{i.max_uses}",
                "status": "revoked" if i.revoked else ("used up" if i.uses >= i.max_uses else "open"),
                "created (UTC)": i.created_at, "link": _invite_link(i.code),
            } for i in invs]), hide_index=True, use_container_width=True)
            open_codes = [i.code for i in invs if not i.revoked and i.uses < i.max_uses]
            if open_codes:
                rc = st.selectbox("Revoke an open invite", open_codes)
                if st.button("Revoke"):
                    auth.revoke_invite(rc)
                    st.rerun()

    with t_set:
        st.subheader("SEC contact")
        st.caption("The SEC requires a name and email on every request this server makes. "
                   "It's sent only to sec.gov.")
        if os.environ.get("SEC_USER_AGENT"):
            st.write(f"Set by the server's `SEC_USER_AGENT` secret: `{sec_user_agent()}`")
        else:
            s = load_settings()
            with st.form("sec"):
                n = st.text_input("Name", value=s.get("name", ""))
                e = st.text_input("Email", value=s.get("email", ""))
                if st.form_submit_button("Save"):
                    if "@" not in e:
                        st.error("Enter a valid email.")
                    else:
                        save_settings({**s, "name": n.strip(), "email": e.strip()})
                        st.success("Saved.")
        st.subheader("Database")
        st.write(f"Backend: **{db.backend_name()}**")
        if db.backend_name().startswith("SQLite"):
            st.caption("Fine for running on your own computer. When you deploy, set `DATABASE_URL` to a hosted "
                       "Postgres database so accounts and history survive restarts (see DEPLOY.md).")
