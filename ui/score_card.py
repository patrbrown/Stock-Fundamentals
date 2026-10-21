"""The TTT score card shown at the top of a company's page, plus the 'how it was scored' breakdown."""
from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from core import db, market, trend as trend_mod
from ui import style

BAND_COLORS = {"lime": "#C6F432", "green": "#4ADE80", "amber": "#FFB547", "red": "#FF6B6B"}
TREND_COLORS = {"Uptrend": "#4ADE80", "Recovering": "#C6F432", "Mixed": "#FFB547",
                "Weakening": "#FF9F6B", "Downtrend": "#FF6B6B"}
TREND_HELP = {
    "Uptrend": "Above its 200-day average, the 50-day is above the 200-day, and the 200-day is rising.",
    "Recovering": "Back above the 200-day average after spending most of the last 6 months below it.",
    "Mixed": "Above the 200-day average, but the other signals disagree.",
    "Weakening": "Slipped below the 200-day average. The longer averages haven't rolled over yet.",
    "Downtrend": "Below the 200-day average, the 50-day is below the 200-day, and the 200-day is falling.",
}
READING = {
    (True, True): ("Strong business, and the market agrees.", "How much of the good news is already in the price?"),
    (True, False): ("Strong business the market is selling.", "Is it cheap for a reason — or has the market overreacted?"),
    (False, True): ("Weaker fundamentals, but the stock is rising.", "What does the market see that the numbers don't show yet?"),
    (False, False): ("Weak fundamentals and a falling price.", "What would have to change for either to improve?"),
}

CSS = """
<style>
.ttt{background:#131A23;border:1px solid #1E2733;border-radius:16px;padding:18px 20px;margin:6px 0 14px;
     display:flex;gap:22px;flex-wrap:wrap;align-items:stretch;font-family:inherit;color:#E6EBF0}
.ttt .big{min-width:120px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center}
.ttt .lbl{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#93A1B0;font-weight:600}
.ttt .num{font-size:56px;line-height:1;font-weight:800;margin:4px 0 6px}
.ttt .badges{display:flex;gap:6px;flex-wrap:wrap}
.ttt .b{font-size:11px;font-weight:700;border-radius:999px;padding:2px 8px;border:1px solid #2A3646;color:#E6EBF0}
.ttt .b.up{color:#4ADE80;border-color:#24563A}.ttt .b.dn{color:#FF6B6B;border-color:#5A2A2A}
.ttt .b.flag{color:#FF6B6B;border-color:#5A2A2A}.ttt .b.f{color:#7CC4FF;border-color:#24425E}
.ttt .b.cx{color:#FFB547;border-color:#5A4424}
.ttt .pillars{flex:1;min-width:240px;display:grid;gap:9px;align-content:center}
.ttt .p{display:grid;grid-template-columns:120px 1fr 52px;gap:10px;align-items:center;font-size:13px}
.ttt .bar{height:8px;background:#1E2733;border-radius:6px;overflow:hidden}
.ttt .bar i{display:block;height:100%;border-radius:6px}
.ttt .pts{text-align:right;color:#C9D3DD;font-variant-numeric:tabular-nums}
.ttt .tr{min-width:170px;border-left:1px solid #1E2733;padding-left:20px;display:flex;flex-direction:column;
         justify-content:center;gap:6px}
.ttt .state{font-size:20px;font-weight:700}
.ttt .sub{font-size:12px;color:#93A1B0}
.ttt .sub b{color:#E6EBF0;font-weight:600}
.ttt .flags{flex-basis:100%;font-size:12.5px;color:#FF9F9F;border-top:1px solid #1E2733;padding-top:10px}
.ttt .read{flex-basis:100%;font-size:12.5px;color:#C9D3DD;border-top:1px solid #1E2733;padding-top:10px}
.ttt .read b{color:#E6EBF0}
.ttt .na{font-size:15px;color:#C9D3DD}
@media (max-width:640px){.ttt .tr{border-left:0;padding-left:0}.ttt .p{grid-template-columns:96px 1fr 46px}}
</style>
"""


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=300)
def get_trend(price_symbol: str, industry_key: str | None, ticker: str) -> dict:
    close = market.close_history(price_symbol, "2y")
    return trend_mod.build(close, industry_key, ticker)


def _signed(x, d=0):
    if x is None:
        return "—"
    v = round(x * 100, d) + 0.0   # avoids "-0%"
    return f"{v:+.{d}f}%"


def render(r) -> None:
    sc = r.score
    if sc is None:
        return
    try:
        tr = get_trend(r.price_symbol or r.ticker, r.industry_key, r.ticker)
    except Exception:
        tr = {}
    sc.trend = tr or {}

    trend_html = ""
    if tr.get("state"):
        col = TREND_COLORS.get(tr["state"], "#E6EBF0")
        trend_html = (f'<div class="tr"><div class="lbl">Trend</div>'
                      f'<div class="state" style="color:{col}" title="{escape(TREND_HELP[tr["state"]])}">{tr["state"]}</div>'
                      f'<div class="sub" title="12-month return minus the S&amp;P 500, skipping the latest month">'
                      f'RS <b>{_signed(tr.get("rs"))}</b></div>'
                      f'<div class="sub" title="Industry peers\' 6-month return minus the S&amp;P 500">'
                      f'Ind <b>{_signed(tr.get("ind"))}</b></div></div>')

    if not sc.scored:
        style.html(CSS + f'<div class="ttt"><div class="big"><div class="lbl">TTT score</div>'
                         f'<div class="na">Not scored — {escape(sc.reason)}</div></div>{trend_html}</div>')
        return

    rec_key = f"ttt_saved_{r.ticker}_{pd.Timestamp.utcnow():%Y%m%d}"
    if not st.session_state.get(rec_key):
        db.record_score(r.ticker, sc)
        st.session_state[rec_key] = True
    prev = db.score_last_week(r.ticker)
    color = BAND_COLORS[sc.band]
    badges = []
    if prev:
        d = sc.total - prev["total"]
        if d:
            badges.append(f'<span class="b {"up" if d > 0 else "dn"}" title="Change since {prev["scored_on"]:%b %d}">'
                          f'{"▲" if d > 0 else "▼"} {abs(d)}</span>')
        else:
            badges.append(f'<span class="b" title="Unchanged since {prev["scored_on"]:%b %d}">= 0</span>')
    if sc.scorecard == "financials":
        badges.append('<span class="b f" title="Scored on the financials scorecard (book value and return on equity)">F</span>')
    if sc.capex_heavy:
        badges.append('<span class="b cx" title="Capital spending is more than 2× depreciation">CAPEX</span>')
    if sc.red_flags:
        badges.append(f'<span class="b flag" title="A red flag is capping the score">⚑ {len(sc.red_flags)}</span>')

    rows = []
    for key, p in sc.pillars.items():
        if p["earned"] is None:
            rows.append(f'<div class="p"><span>{p["label"]}</span><div class="bar"></div><span class="pts">n/a</span></div>')
            continue
        w = max(0, min(100, p["earned"] / p["max"] * 100))
        rows.append(f'<div class="p"><span>{p["label"]}</span><div class="bar"><i style="width:{w:.0f}%;background:{color}">'
                    f'</i></div><span class="pts">{p["earned"]:.0f}/{p["max"]}</span></div>')

    extra = ""
    if sc.red_flags:
        cap = 59 if len(sc.red_flags) == 1 else 39
        extra += (f'<div class="flags">⚑ <b>Capped at {cap}</b> (would be {sc.uncapped:.0f}): '
                  + "; ".join(escape(f) for f in sc.red_flags) + "</div>")
    if tr.get("state") in ("Uptrend", "Downtrend"):
        what, ask = READING[(sc.total >= 65, tr["state"] == "Uptrend")]
        extra += f'<div class="read"><b>{"High" if sc.total >= 65 else "Low"} score + {tr["state"]}:</b> {what} <i>Ask: {ask}</i></div>'

    style.html(CSS + f'<div class="ttt"><div class="big"><div class="lbl">TTT score</div>'
                     f'<div class="num" style="color:{color}">{sc.total}</div>'
                     f'<div class="badges">{"".join(badges)}</div></div>'
                     f'<div class="pillars">{"".join(rows)}</div>{trend_html}{extra}</div>')

    with st.expander("How this score was built"):
        st.caption(("Financials scorecard (banks, brokers, insurers, asset managers, card lenders, exchanges): judged "
                    "on book value and return on equity. " if sc.scorecard == "financials" else "")
                   + ("Marked CAPEX: cash conversion and the cash-flow trend subtract only maintenance spending "
                      "(estimated as depreciation); cash-flow yield, cash-flow history and red flags use strict "
                      "free cash flow. " if sc.capex_heavy else "")
                   + "Every check earns partial credit on a sliding scale. A check with missing data is skipped "
                     "and the rest of its pillar is re-weighted. Valuation is compared with the company's own "
                     "5-year history; trend and cash checks include the latest 12 months.")
        rows = []
        for c in sc.checks:
            rows.append({
                "Pillar": sc.pillars[c.pillar]["label"],
                "Check": c.name,
                "Measured": c.value,
                "Full credit": c.rule,
                "Points": "skipped (no data)" if c.fraction is None else f"{c.earned:.1f} / {c.points:.1f}",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("Red flags cap the score at 59 (one) or 39 (two or more). The trend sits beside the score "
                   "and is never blended into it. RS = 12-month return minus the S&P 500's, skipping the most "
                   "recent month; Ind = the industry's leading companies vs the S&P 500 over 6 months.")
        st.caption("Educational scoring model, not investment advice. Do your own research.")
