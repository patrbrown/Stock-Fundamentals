"""Visual theme: global CSS plus small HTML building blocks (cards, badges, rank tiles).

Colours
  ink      #0B0F14  page background        teal   #2EE6C5  primary / the company you're analyzing
  surface  #131A23  cards and panels       amber  #FFB547  derived Q4s, medians, "trails"
  border   #1E2733                         coral  #FF8A7A  negative numbers
  text     #E6EBF0  muted #93A1B0
"""
from __future__ import annotations

from html import escape

import streamlit as st

TEAL, AMBER, CORAL = "#2EE6C5", "#FFB547", "#FF8A7A"
INK, SURFACE, BORDER, TEXT, MUTED = "#0B0F14", "#131A23", "#1E2733", "#E6EBF0", "#93A1B0"

FONTS = ("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800"
         "&family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap")

CSS = """
<style>
@import url('%(fonts)s');
:root {
  --sf-ink:#0B0F14; --sf-surface:#131A23; --sf-surface2:#18212C; --sf-border:#1E2733; --sf-border2:#2A3544;
  --sf-text:#E6EBF0; --sf-muted:#93A1B0; --sf-soft:#A9B5C2;
  --sf-teal:#2EE6C5; --sf-amber:#FFB547; --sf-coral:#FF8A7A;
  --sf-display:'Bricolage Grotesque','Segoe UI',system-ui,sans-serif;
  --sf-body:'IBM Plex Sans','Segoe UI',system-ui,sans-serif;
  --sf-mono:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
}
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {font-family: var(--sf-body);}
[data-testid="stAppViewContainer"] {
  background-color: var(--sf-ink);
  background-image: radial-gradient(rgba(230,235,240,0.05) 1px, transparent 1px);
  background-size: 18px 18px;
}
[data-testid="stHeader"] {background: transparent;}
h1, h2, h3, h4 {font-family: var(--sf-display) !important; letter-spacing: -0.02em;}
h1 {font-weight: 800 !important;}
h2, h3 {font-weight: 700 !important;}
[data-testid="stCaptionContainer"], .stCaption {color: var(--sf-muted);}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {border-right: 1px solid var(--sf-border);}
[data-testid="stSidebar"] [data-testid="stForm"] {
  background: var(--sf-surface); border: 1px solid var(--sf-border); border-radius: 14px; padding: 18px;
}
[data-testid="stSidebar"] label p {font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--sf-muted);}
[data-testid="stSidebar"] [data-testid="stCheckbox"] label p {text-transform: none; letter-spacing: 0; font-size: 14px;
  font-weight: 400; color: var(--sf-text);}
[data-testid="stSidebar"] [role="radiogroup"] label p {text-transform: none; letter-spacing: 0; font-size: 14px;
  font-weight: 500; color: var(--sf-text);}
.sf-brand {display:flex; align-items:center; gap:12px; margin: 4px 0 18px;}
.sf-brand .mark {width:36px; height:36px; border-radius:10px; background:var(--sf-teal); color:#062019;
  display:flex; align-items:center; justify-content:center; flex-shrink:0;}
.sf-brand .bars {display:flex; align-items:flex-end; gap:3px; height:19px;}
.sf-brand .bars i {display:block; width:3.5px; border-radius:2px; background:#062019;}
.sf-brand .name {font-family:var(--sf-display); font-size:19px; font-weight:700; letter-spacing:-.01em;}
.sf-user {display:flex; align-items:center; gap:10px; margin-top:6px;}
.sf-user .av {width:32px; height:32px; border-radius:50%%; background:var(--sf-amber); color:#2A1A00;
  display:flex; align-items:center; justify-content:center; font-family:var(--sf-display); font-weight:700;}
.sf-user .who {font-size:14px; font-weight:600; line-height:1.2;}
.sf-user .sub {font-size:12px; color:var(--sf-muted);}

/* ---------- buttons: dark text on teal for contrast ---------- */
[data-testid^="stBaseButton-primary"] {color:#062019 !important; font-weight:600; border:0;}
[data-testid^="stBaseButton-primary"] p {color:#062019 !important; font-weight:600;}
[data-testid^="stBaseButton-secondary"], [data-testid="stDownloadButton"] button {
  background: var(--sf-surface); border: 1px solid var(--sf-border2);}

/* ---------- multiselect chips ---------- */
[data-baseweb="tag"], [data-testid="stMultiSelectTagsContainer"] [data-tag] {
  background: var(--sf-surface2) !important; border: 1px solid var(--sf-border2); border-radius: 999px !important;}
[data-baseweb="tag"] span, [data-testid="stMultiSelectTagsContainer"] [data-tag] span,
[data-testid="stMultiSelectTagsContainer"] [data-tag] svg {color: var(--sf-text) !important;}

/* ---------- tabs as a segmented control ---------- */
.stTabs [role="tablist"] {gap:4px; background:var(--sf-surface); border:1px solid var(--sf-border);
  border-radius:12px; padding:4px; width:fit-content; max-width:100%%; margin-bottom:8px;}
.stTabs [role="tablist"]::before, .stTabs [role="tablist"]::after {display:none !important; content:none !important;}
.stTabs [data-testid="stTab"] {height:38px; padding:0 16px; border-radius:8px; border:0 !important;
  box-shadow:none !important; background:transparent; color:var(--sf-soft);}
.stTabs [data-testid="stTab"] p {color:var(--sf-soft);}
.stTabs [data-testid="stTab"][aria-selected="true"] {background:var(--sf-text);}
.stTabs [data-testid="stTab"][aria-selected="true"] p {color:var(--sf-ink); font-weight:600;}
.stTabs [data-testid="stTab"]:hover p {color:var(--sf-text);}
.stTabs [data-testid="stTab"][aria-selected="true"]:hover p {color:var(--sf-ink);}

/* ---------- bordered containers become panels ---------- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
  background: var(--sf-surface); border-color: var(--sf-border) !important; border-radius: 16px;}
[data-testid="stDataFrame"] {border: 1px solid var(--sf-border); border-radius: 12px; overflow: hidden;}
[data-testid="stExpander"] details {background: var(--sf-surface); border-color: var(--sf-border); border-radius: 14px;}

/* ---------- header ---------- */
.sf-eyebrow {display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:13px; color:var(--sf-muted);}
.sf-badge {font-family:var(--sf-mono); font-size:13px; font-weight:600; padding:4px 10px; border-radius:6px;
  background:rgba(46,230,197,.12); color:var(--sf-teal);}
.sf-meta {font-size:13px; color:var(--sf-muted); margin-top:-6px;}
.sf-meta b {color:var(--sf-text); font-weight:500;}
.sf-price {text-align:right; margin-bottom:10px;}
.sf-price .lbl {font-size:12px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; color:var(--sf-muted);}
.sf-price .val {font-family:var(--sf-mono); font-size:42px; font-weight:500; line-height:1.1; letter-spacing:-.02em;}

/* ---------- KPI cards ---------- */
.sf-kpis {display:grid; grid-template-columns:repeat(6, minmax(0,1fr)); gap:12px; margin: 6px 0 18px;}
@media (max-width: 1100px) {.sf-kpis {grid-template-columns:repeat(3, minmax(0,1fr));}}
@media (max-width: 640px) {.sf-kpis {grid-template-columns:repeat(2, minmax(0,1fr));}}
.sf-kpi {background:var(--sf-surface); border:1px solid var(--sf-border); border-radius:14px; padding:16px;
  display:flex; flex-direction:column; gap:10px; min-width:0;}
.sf-kpi .top {display:flex; justify-content:space-between; align-items:flex-start; gap:8px;}
.sf-kpi .lbl {font-size:12px; color:var(--sf-muted);}
.sf-kpi .val {font-family:var(--sf-mono); font-size:24px; font-weight:500; letter-spacing:-.02em; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis;}
.sf-kpi .foot {display:flex; align-items:center; gap:8px; font-size:12px; color:var(--sf-muted); flex-wrap:wrap;}
.sf-spark {display:flex; align-items:flex-end; gap:2px; width:56px; height:24px; flex-shrink:0;}
.sf-spark span {flex:1 1 0; border-radius:2px; background:var(--sf-teal); opacity:.85;}
.sf-chip {font-family:var(--sf-mono); font-size:12px; font-weight:600; padding:3px 8px; border-radius:999px; white-space:nowrap;}
.sf-chip.pos {color:var(--sf-teal); background:rgba(46,230,197,.12);}
.sf-chip.neg {color:var(--sf-coral); background:rgba(255,138,122,.12);}
.sf-chip.neu {color:var(--sf-text); background:#1B2430;}
.sf-chip.amb {color:var(--sf-amber); background:rgba(255,181,71,.12);}

/* ---------- selected-quarter panel ---------- */
.sf-q {background:#0F141B; border:1px solid var(--sf-border); border-radius:14px; padding:20px;
  display:flex; flex-direction:column; gap:16px;}
.sf-q .eyebrow {font-size:12px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; color:var(--sf-muted);}
.sf-q .title {font-family:var(--sf-display); font-size:26px; font-weight:700; line-height:1.1;}
.sf-q .sub {font-size:13px; color:var(--sf-muted);}
.sf-q .big {font-family:var(--sf-mono); font-size:34px; font-weight:500; line-height:1; letter-spacing:-.02em;}
.sf-q .row {display:flex; gap:14px; font-size:12px; color:var(--sf-muted); align-items:center; flex-wrap:wrap;}
.sf-q .grid2 {display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; padding-top:14px;
  border-top:1px solid var(--sf-border);}
.sf-q .k {font-size:12px; color:var(--sf-muted);}
.sf-q .v {font-family:var(--sf-mono); font-size:16px;}
.sf-mix {display:flex; height:10px; border-radius:999px; overflow:hidden; gap:2px;}
.sf-mix span {display:block; height:100%%;}
.sf-mixlist {display:flex; flex-direction:column; gap:6px; font-size:12px;}
.sf-mixlist div {display:flex; align-items:center; gap:8px;}
.sf-mixlist i {width:10px; height:10px; border-radius:3px; flex-shrink:0;}
.sf-mixlist .n {flex-grow:1; color:var(--sf-soft); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
.sf-mixlist .p {font-family:var(--sf-mono); color:var(--sf-text);}
.sf-legend {display:flex; gap:20px; flex-wrap:wrap; font-size:12px; color:var(--sf-muted); margin:-4px 0 4px;}
.sf-legend span {display:inline-flex; align-items:center; gap:8px;}
.sf-legend i {width:12px; height:12px; border-radius:3px; display:inline-block;}

/* ---------- competitor rank tiles ---------- */
.sf-ranks {display:grid; grid-template-columns:repeat(auto-fit, minmax(128px,1fr)); gap:12px; margin:8px 0 6px;}
.sf-rank {background:var(--sf-surface); border:1px solid var(--sf-border); border-radius:14px; padding:16px;
  display:flex; flex-direction:column; gap:12px;}
.sf-rank .lbl {font-size:12px; color:var(--sf-muted); min-height:32px;}
.sf-rank .num {display:flex; align-items:baseline; gap:6px;}
.sf-rank .num b {font-family:var(--sf-display); font-size:38px; font-weight:800; line-height:1; letter-spacing:-.02em;}
.sf-rank .num span {font-size:14px; color:var(--sf-muted);}
.sf-dots {display:flex; gap:5px; flex-wrap:wrap;}
.sf-dots i {width:10px; height:10px; border-radius:50%%; background:#26303C;}
.sf-rank .tag {align-self:flex-start;}

/* ---------- legacy stat panels (Valuation & ratios tab) ---------- */
.panel {background: var(--sf-surface); border: 1px solid var(--sf-border); border-radius: 14px;
        padding: 16px 20px; margin-bottom: 14px;}
.panel h4 {margin: 0 0 8px 0; font-size: 1.05rem;}
.panel table {width: 100%%; border-collapse: collapse;}
.panel td {padding: 7px 0; border-bottom: 1px solid var(--sf-border); font-size: 0.92rem;}
.panel td:last-child {text-align: right; font-family: var(--sf-mono); font-weight: 500; font-variant-numeric: tabular-nums;}
.panel tr:last-child td {border-bottom: none;}
.panel .hint {color: var(--sf-muted); font-size: 0.78rem; margin-top: 6px;}
</style>
""" % {"fonts": FONTS}

LOGO_SVG = ('<span class="bars" aria-hidden="true"><i style="height:9px"></i><i style="height:16px"></i>'
            '<i style="height:12px"></i><i style="height:19px"></i></span>')  # CSS-drawn: st.html strips <svg>


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def html(s: str) -> None:
    """Raw HTML (no Markdown pass, so "$" amounts are never read as LaTeX)."""
    st.html(s)


def brand() -> None:
    html(f'<div class="sf-brand"><div class="mark">{LOGO_SVG}</div><div class="name">Stock Fundamentals</div></div>')


def user_chip(name: str) -> None:
    initial = escape((name or "?")[:1].upper())
    html(f'<div class="sf-user"><div class="av">{initial}</div><div><div class="who">{escape(name)}</div>'
         f'<div class="sub">Signed in</div></div></div>')


def chip(text: str, kind: str = "neu") -> str:
    return f'<span class="sf-chip {kind}">{escape(text)}</span>'


def signed_chip(x, text: str) -> str:
    """Teal for >= 0, coral for < 0, neutral when there's no number."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return chip("—", "neu")
    if v != v:  # NaN
        return chip("—", "neu")
    return chip(("+" + text) if v >= 0 else text, "pos" if v >= 0 else "neg")


def kpi(label: str, value: str, foot: str = "", spark: list[float] | None = None) -> str:
    sp = ""
    vals = [v for v in (spark or []) if v is not None and v == v]
    if len(vals) >= 2:
        lo, hi = min(vals), max(vals)
        rng = (hi - lo) or 1
        bars = "".join(f'<span style="height:{max(3, round(4 + (v - lo) / rng * 20))}px"></span>' for v in vals)
        sp = f'<div class="sf-spark" aria-hidden="true">{bars}</div>'
    return (f'<div class="sf-kpi"><div class="top"><div class="lbl">{escape(label)}</div>{sp}</div>'
            f'<div class="val">{escape(value)}</div><div class="foot">{foot}</div></div>')


def rank_tile(label: str, pos: int | None, of: int | None) -> str:
    if not pos:
        return (f'<div class="sf-rank"><div class="lbl">{escape(label)}</div>'
                f'<div class="num"><b>—</b></div><span class="tag">{chip("No data", "neu")}</span></div>')
    top, bottom = pos == 1, pos == of
    color = TEAL if top else AMBER if bottom else "#A9B5C2"
    dots = "".join(f'<i style="background:{color}"></i>' if i == pos - 1 else "<i></i>" for i in range(of))
    tag = chip("Leads", "pos") if top else chip("Trails", "amb") if bottom else chip("Mid-pack", "neu")
    return (f'<div class="sf-rank"><div class="lbl">{escape(label)}</div>'
            f'<div class="num"><b>#{pos}</b><span>of {of}</span></div>'
            f'<div class="sf-dots">{dots}</div><span class="tag">{tag}</span></div>')
