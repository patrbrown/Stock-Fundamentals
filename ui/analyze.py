"""The main page: pick a company, see 20 quarters of fundamentals, ratios, and competitors."""
from __future__ import annotations

from urllib.parse import quote

import pandas as pd
import streamlit as st

from core import db, formatting as fmt, market, peers as peer_mod, segments, sec_client
from core.concepts import METRICS
from core.export import metric_table, to_excel
from core.report import build_report
from core.sec_client import SecError, lookup, ticker_map
from core.settings import sec_user_agent
from ui import charts
from ui.breakdowns import hover_for

CHARTS = [
    ("revenue", "Revenue"), ("gross_profit", "Gross Profit"), ("operating_income", "Operating Income"),
    ("net_income", "Net Income"), ("eps_diluted", "Earnings Per Share (diluted)"),
    ("pe_ttm", "Price to Earnings (P/E, TTM)"), ("ebitda", "EBITDA"),
    ("cash_from_operations", "Cash from Operations"), ("free_cash_flow", "Free Cash Flow"),
]


# ------------------------------------------------------------------ cached data access (shared by all users)
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _company_options() -> list[tuple[str, str]]:
    return [(t, f"{t}  ·  {i['title']}") for t, i in ticker_map().items()]


def company_options() -> list[tuple[str, str]]:
    try:
        return _company_options()
    except Exception:
        return []  # SEC unreachable: fall back to a text box (not cached, so it retries)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=200)
def get_report(t: str, n: int, nonce: int):
    return build_report(t, n_quarters=n, refresh=nonce > 0)


@st.cache_data(ttl=24 * 3600, show_spinner="Reading segment data from the filings (the first time for a company takes ~30 s)…",
               max_entries=200)
def get_breakdowns(cik: int, quarter_ends: tuple):
    return segments.build_breakdowns(cik, sec_client.company_facts(cik), list(quarter_ends))


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=200)
def get_peer_suggestions(ticker: str, n: int):
    return peer_mod.suggest_peers(get_report(ticker, n, 0))


@st.cache_data(ttl=3600, show_spinner="Loading competitors from the SEC and Yahoo…", max_entries=100)
def get_peers(tickers: tuple, n: int):
    return peer_mod.load_peers(list(tickers), n_quarters=n)


# ------------------------------------------------------------------ small UI helpers
def panel(title: str, rows: list[tuple[str, str]], hint: str = ""):
    body = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)
    hint_html = f'<div class="hint">{hint}</div>' if hint else ""
    st.markdown(f'<div class="panel"><h4>{title}</h4><table>{body}</table>{hint_html}</div>', unsafe_allow_html=True)


def format_table(t: pd.DataFrame, cur: str) -> pd.DataFrame:
    kinds = {v[0]: v[1] for v in METRICS.values()}
    return pd.DataFrame([[fmt.by_kind(v, kinds.get(idx, "money"), cur) for v in row] for idx, row in t.iterrows()],
                        index=t.index, columns=t.columns, dtype=object)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def tsx_search(q: str):
    return market.search_canadian(q)


def sidebar_controls():
    options = company_options()
    with st.sidebar:
        mkt_choice = st.radio("Market", ["US-listed (SEC filings)", "Canada: TSX / TSXV"], key="market_choice",
                              help="US-listed companies use 20 quarters of SEC filings. Canadian listings use "
                                   "Yahoo Finance statements (about 5 quarters + 4 fiscal years).")
        if mkt_choice.startswith("Canada"):
            qtext = st.text_input("Search Canadian companies", key="tsx_query",
                                  placeholder="e.g. Suncor, Galantas, GAL, SU.TO")
            results = tsx_search(qtext.strip()) if qtext.strip() else []
            ticker = ""
            if results:
                pick = st.selectbox("Company", range(len(results)),
                                    format_func=lambda i: f"{results[i]['symbol']}  ·  {results[i]['name']} ({results[i]['exchange']})")
                ticker = results[pick]["symbol"]
            elif qtext.strip():
                st.caption("No Canadian listings found. Try the company name, the bare symbol (e.g. GAL), "
                           "or the symbol with .TO (TSX) or .V (TSXV).")
            n_q = st.slider("Quarters", 4, 40, 20, step=4)
            go_btn = st.button("Analyze", type="primary", use_container_width=True, disabled=not ticker)
            seg_on, refresh = False, False
            st.caption("Data: Yahoo Finance statements and prices, in the company's reporting currency.")
            return options, ticker, n_q, seg_on, refresh, go_btn
        with st.form("ticker_form"):
            if options:
                current = st.session_state.get("ticker", "DELL")
                tickers = [t for t, _ in options]
                choice = st.selectbox(
                    "Company", range(len(options)), format_func=lambda i: options[i][1],
                    index=tickers.index(current) if current in tickers else None,
                    placeholder="Type a name or ticker, e.g. Netflix",
                    help="Start typing a company name or ticker to filter the list.",
                )
                ticker = tickers[choice] if choice is not None else ""
            else:
                ticker = st.text_input("Company or ticker", value=st.session_state.get("ticker", "DELL"),
                                       placeholder="e.g. Netflix or NFLX").strip()
            n_q = st.slider("Quarters", 8, 40, 20, step=4)
            seg_on = st.checkbox("Segment breakdowns in hovers", value=True,
                                 help="Reads each filing's segment tables. Slower the first time for each company.")
            refresh = st.checkbox("Re-download from SEC (ignore cache)")
            go_btn = st.form_submit_button("Analyze", type="primary", use_container_width=True)
        st.caption("Data: SEC EDGAR filings (10-Q/10-K, 6-K/20-F). Prices & analyst targets: Yahoo Finance.")
    return options, ticker, n_q, seg_on, refresh, go_btn


# ------------------------------------------------------------------ page
def company_link(ticker: str, name: str) -> str:
    """URL that opens this app on `ticker` (used for click-through from the competitor table)."""
    try:
        base = st.context.url.split("?")[0].split("#")[0]
    except Exception:
        base = ""
    return f"{base}?ticker={quote(ticker)}#{name}"


def analyze_page(user) -> None:
    # Deep link: ?ticker=XYZ (e.g. opened from the competitor table in a new window)
    qp = st.query_params.get("ticker", "").strip().upper()
    if qp and qp != st.session_state.get("qp_applied"):
        st.session_state["qp_applied"] = qp
        st.session_state["ticker"] = qp
        st.session_state["log_view"] = True
        if "." in qp and qp.endswith((".TO", ".V", ".NE", ".CN")):
            st.session_state["market_choice"] = "Canada: TSX / TSXV"

    options, ticker, n_q, seg_on, refresh, go_btn = sidebar_controls()

    if go_btn and ticker:
        if not options and "." not in ticker:
            try:
                ticker = lookup(ticker)["ticker"]
            except Exception:
                pass
        st.session_state["ticker"] = ticker
        st.session_state["nonce"] = st.session_state.get("nonce", 0) + (1 if refresh else 0)
        st.session_state["log_view"] = True
        st.session_state["qp_applied"] = ticker.upper()
        st.query_params["ticker"] = ticker   # keeps the address bar shareable

    active = st.session_state.get("ticker")
    if not active:
        st.title("Stock Fundamentals")
        st.write("Pick a company in the sidebar (type a name like *Netflix* or a ticker like *NFLX*) and press "
                 "**Analyze** to see the last 20 quarters of revenue, profit, EPS, EBITDA, cash flow and growth, "
                 "plus how it stacks up against its competitors.")
        return
    if not sec_user_agent() and "." not in active:
        st.warning("The SEC contact name/email hasn't been set yet. "
                   + ("Add it under **Admin → Settings**." if user.is_admin else "Ask the admin to set it."))
        return

    try:
        with st.spinner(f"Loading {active}…"):
            r = get_report(active, n_q, st.session_state.get("nonce", 0) if refresh else 0)
    except (SecError, ValueError) as e:
        st.error(str(e))
        return
    except Exception as e:  # network problems etc.
        st.error(f"Couldn't load {active}: {e}")
        return

    if st.session_state.pop("log_view", False):
        db.log_request(user.id, r.ticker, r.name, "view")

    q, s, cur = r.quarterly, r.snapshot, r.currency
    if q.empty:
        st.error(f"No financial statements are available for {r.ticker}.")
        return
    M = lambda x: fmt.money(x, cur)

    breakdowns = {}
    if seg_on and r.source == "SEC":
        try:
            breakdowns = get_breakdowns(r.cik, tuple(q.index))
        except Exception:
            st.caption("ℹ️ Segment data couldn't be read from the filings right now.")

    # ---------------------------------------------------------------- header
    left, right = st.columns([3, 1])
    with left:
        st.title(r.name)
        pcur = s.get("price_currency") or cur
        meta = [f"**{r.ticker}**" + (f" ({r.exchange})" if r.exchange else "")]
        meta.append(f"💱 Financials in **{cur}**")
        if r.price_symbol and r.price_symbol != r.ticker:
            meta.append(f"price from **{r.price_symbol}** in {pcur}")
        elif pcur != cur:
            meta.append(f"price converted to {cur}")
        meta.append(f"Source: {'SEC filings' if r.source == 'SEC' else 'Yahoo Finance'}"
                    + (f" (CIK {r.cik})" if r.cik else ""))
        if r.sector:
            meta.append(f"{r.sector} · {r.industry}")
        meta.append(f"Latest {'quarter' if q['label'].iloc[-1].startswith('Q') else 'period'}: "
                    f"{q['label'].iloc[-1]} (ended {q.index[-1]:%b %d, %Y})")
        st.markdown(" · ".join(meta))
    with right:
        st.download_button("⬇ Download Excel", data=to_excel(r), file_name=f"{r.ticker}_fundamentals.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True, on_click=db.log_request, args=(user.id, r.ticker, r.name, "export"))

    k = st.columns(7)
    k[0].metric(f"Share price ({cur})", fmt.eps(s["price"], cur))
    k[1].metric(f"Market cap ({cur})", M(s["market_cap"]))
    k[2].metric("P/E (TTM)", fmt.ratio(s["pe"]) if s["pe"] else "n/m",
                help="Share price ÷ diluted EPS over the last four quarters. "
                     + (f"Forward P/E (analyst estimates): {fmt.ratio(s['forward_pe'])}." if s.get("forward_pe") else "")
                     + (" Shown as n/m when trailing earnings are negative." if not s["pe"] else ""))
    k[3].metric("Revenue (TTM)", M(s["revenue_ttm"]))
    k[4].metric("Net income (TTM)", M(s["net_income_ttm"]))
    k[5].metric("EPS (TTM)", fmt.eps(s["eps_ttm"], cur))
    k[6].metric("Free cash flow (TTM)", M(s["fcf_ttm"]))
    for n in r.notes:
        st.caption("ℹ️ " + n)

    tab_charts, tab_stats, tab_table, tab_annual, tab_notes = st.tabs(
        ["📊 Charts", "📐 Valuation & ratios", "📋 Quarterly table", "📅 Annual & growth", "ℹ️ Data notes"])

    # ---------------------------------------------------------------- charts
    with tab_charts:
        rev_axes = list(breakdowns.get("revenue", {}).keys())
        axis = None
        if rev_axes:
            axis = st.radio("Revenue hover breaks down by", rev_axes, horizontal=True) if len(rev_axes) > 1 else rev_axes[0]
        st.caption("Hover over any bar to see what makes it up"
                   + (" — revenue split by " + axis.lower() + "." if axis else ".")
                   + (" Hatched bars are fiscal Q4s, calculated as the annual figure minus the first nine months."
                      if r.source == "SEC" else " Yahoo Finance provides about 5 quarters; see Annual & growth "
                      "for 4 fiscal years.")
                   + " P/E uses the share price on each quarter-end date; the dashed line is today's P/E, and "
                     "quarters with negative trailing earnings have no bar.")
        cols = st.columns(2)
        shown_charts = [(k, t) for k, t in CHARTS if k in q and pd.to_numeric(q[k], errors="coerce").notna().any()]
        for i, (key, title) in enumerate(shown_charts):
            with cols[i % 2]:
                extra = hover_for(key, q, cur, breakdowns, axis)
                ref = (s["pe"], f"Today: {s['pe']:.1f}x") if (key == "pe_ttm" and s["pe"]) else None
                derived = set() if key == "pe_ttm" else set(r.derived_flags.get(key, []))
                fig = charts.bar_chart(q, key, title, cur, derived, extra, ref_line=ref)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with cols[len(shown_charts) % 2]:
            st.plotly_chart(charts.margin_chart(q), use_container_width=True, config={"displayModeBar": False})

    # ---------------------------------------------------------------- stats
    with tab_stats:
        g = r.growth
        gv = lambda m, c: fmt.pct(g.loc[m, c]) if (m in g.index and c in g.columns) else "—"
        c1, c2 = st.columns(2)
        with c1:
            panel("Earnings-Based Valuation", [
                ("Price to Earnings (P/E)", fmt.ratio(s["pe"])),
                ("Forward P/E", fmt.ratio(s["forward_pe"])),
                ("Price/Earnings Growth (PEG)", fmt.ratio(s["peg"])),
                ("Earnings Yield", fmt.pct(s["earnings_yield"])),
                ("EV / EBITDA", fmt.ratio(s["ev_ebitda"])),
            ], "PEG = P/E ÷ TTM EPS growth year over year. Forward P/E is the analyst consensus from Yahoo.")
            panel("Profitability", [
                ("Profit Margin", fmt.pct(s["profit_margin"])),
                ("Operating Profit Margin", fmt.pct(s["operating_margin"])),
                ("FCF Margin", fmt.pct(s["fcf_margin"])),
                ("Return on Equity (ROE)", fmt.pct(s["roe"])),
                ("Return on Invested Capital (ROIC)", fmt.pct(s["roic"])),
            ], "ROE uses average equity over the last year; ROIC = after-tax operating income ÷ (debt + equity − cash).")
            panel("Returns & Analyst View", [
                ("Trailing 12-month return", fmt.pct(s["return_12m"])),
                (f"Analyst mean price target ({cur})", fmt.eps(s["target_mean"], cur)),
                ("Expected 12-month return (to target)", fmt.pct(s["forward_return"])),
                ("Analysts covering", str(int(s["analyst_count"])) if s["analyst_count"] else "—"),
                ("Consensus rating", (s["recommendation"] or "—").title()),
            ], "Expected return = analyst mean 12-month target ÷ current price − 1 (excludes dividends).")
        with c2:
            panel("Revenue & Cash Flow Metrics", [
                ("Price to Sales (P/S)", fmt.ratio(s["ps"])),
                ("Price to Cash Flow (P/CF)", fmt.ratio(s["pcf"])),
                ("Price to Free Cash Flow (P/FCF)", fmt.ratio(s["pfcf"])),
                ("Free Cash Flow Yield", fmt.pct(s["fcf_yield"])),
            ])
            panel("Financial Health", [
                ("Free Cash Flow (TTM)", M(s["fcf_ttm"])),
                ("Net Income (TTM)", M(s["net_income_ttm"])),
                ("Net Debt", M(s["net_debt"])),
                ("Debt to Equity", fmt.ratio(s["debt_to_equity"])),
            ])
            panel("Growth", [
                ("Revenue growth YoY (TTM)", fmt.pct(s["revenue_growth"])),
                ("EPS growth YoY (TTM)", fmt.pct(s["eps_growth_ttm"])),
                ("Revenue CAGR 3y", gv("Revenue", "3y CAGR (FY)")),
                ("Revenue CAGR 5y", gv("Revenue", "5y CAGR (FY)")),
                ("Revenue CAGR 10y", gv("Revenue", "10y CAGR (FY)")),
                ("EPS CAGR 3y", gv("EPS (diluted)", "3y CAGR (FY)")),
            ], "CAGR uses fiscal-year 10-K figures. Full table under Annual & growth.")

    # ---------------------------------------------------------------- tables
    with tab_table:
        shown = format_table(metric_table(q), cur)
        for key in r.derived_flags:
            if key in METRICS and METRICS[key][0] in shown.index:
                for d in r.derived_flags[key]:
                    if d in q.index:
                        col = q.loc[d, "label"]
                        shown.loc[METRICS[key][0], col] = shown.loc[METRICS[key][0], col] + " †"
        shown.columns = [f"{c} ({d:%b '%y})" for c, d in zip(shown.columns, q.index)]
        st.dataframe(shown, use_container_width=True, height=780)
        st.caption("† calculated from the annual or year-to-date figure minus earlier quarters. "
                   "Money is in the company's reporting currency.")

    with tab_annual:
        st.subheader("Growth")
        st.dataframe(r.growth.astype(object).map(fmt.pct), use_container_width=True)
        st.caption("TTM columns compare trailing-twelve-month totals. FY columns compare fiscal years from 10-K "
                   "filings. CAGR is blank when either end is a loss.")
        if r.annual is not None and not r.annual.empty:
            st.subheader("Fiscal years")
            rows = ["revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "ebitda",
                    "cash_from_operations", "capex", "free_cash_flow", "gross_margin", "operating_margin", "net_margin"]
            st.dataframe(format_table(metric_table(r.annual.tail(11), rows), cur), use_container_width=True)

    with tab_notes:
        st.markdown("""
**Where the numbers come from.** Every figure is pulled from the company's own 10-Q and 10-K filings via the
SEC's free XBRL API; segment splits come from the same filings' segment tables. Prices, splits, forward P/E and
analyst targets come from Yahoo Finance.

**Definitions**
- **EBITDA** = operating income + depreciation & amortization (companies don't report EBITDA, so it's calculated).
- **Free cash flow** = cash from operations − capital expenditures.
- **EPS** is diluted EPS as reported, adjusted for later stock splits.
- **TTM** = sum of the last four quarters.
- **Fiscal quarters** follow the company's fiscal year (Dell's FY ends around February, Apple's in September).
""")
        tag_rows = [(METRICS.get(k, (k,))[0], ", ".join(v)) for k, v in r.tags_used.items() if v]
        st.dataframe(pd.DataFrame(tag_rows, columns=["Metric", "XBRL tags used"]), hide_index=True,
                     use_container_width=True)

    competitor_section(user, r, n_q)


# ------------------------------------------------------------------ competitors
def competitor_section(user, r, n_q: int) -> None:
    st.divider()
    st.header("Competitor analysis")
    try:
        suggested = get_peer_suggestions(r.ticker, n_q)
    except Exception:
        suggested = []
    options = company_options()
    all_tickers = [t for t, _ in options]
    labels = dict(options)

    key = f"peers_{r.ticker}"
    if key not in st.session_state:
        st.session_state[key] = suggested
    with st.form(f"peer_form_{r.ticker}"):
        chosen = st.multiselect(
            "Competitors to compare",
            options=list(dict.fromkeys(st.session_state[key] + (all_tickers or suggested))),
            default=st.session_state[key],
            format_func=lambda t: labels.get(t, t), max_selections=8, accept_new_options=True,
            help="Pre-filled with the largest companies in the same industry. Add any SEC-filing company, "
                 "or type a Canadian symbol such as SU.TO and press Enter.",
        )
        chosen = [c.strip().upper() for c in chosen if c.strip()]
        run = st.form_submit_button("Compare", type="primary")
    if not suggested:
        st.caption("Couldn't find industry leaders automatically right now. Pick competitors above.")
    if run:
        st.session_state[key] = chosen
        st.session_state[f"{key}_run"] = True
        for t in chosen:
            db.log_request(user.id, t, labels.get(t, t).split("·")[-1].strip(), "peer")
    if not st.session_state.get(f"{key}_run") or not st.session_state[key]:
        st.caption("Choose competitors and press **Compare** to see how "
                   f"{r.name} stacks up on growth, margins, returns and valuation.")
        return

    reports, errors = get_peers(tuple(st.session_state[key]), n_q)
    for t, err in errors.items():
        st.caption(f"⚠️ {t} skipped: {err}")
    if not reports:
        return
    df, fx_notes = peer_mod.comparison_frame(r, reports)
    rk = peer_mod.ranks(df, r.ticker)

    # Headline ranks
    n_co = len(df)
    highlights = ["P/E (TTM)", "Revenue growth YoY", "Operating margin", "Return on equity", "PEG",
                  "12-mo expected return (analyst target)", "Free cash flow (TTM)"]
    cols = st.columns(len(highlights))
    for c, label in zip(cols, highlights):
        if label in rk:
            pos, of = rk[label]
            c.metric(label, f"#{pos} of {of}")
        else:
            c.metric(label, "—")
    st.caption(f"Rank of {r.ticker} among the {n_co} companies (1 = best; lower is better for P/E, PEG and debt).")

    # Full table, subject row highlighted
    kinds = {label: kind for _, label, kind, _ in peer_mod.COMPARE}
    shown = df.copy().astype(object)
    for col, kind in kinds.items():
        shown[col] = [fmt.by_kind(v, kind, r.currency) for v in df[col]]
    shown["Company"] = [company_link(t, n) for t, n in zip(shown.index, df["Company"])]
    styled = shown.style.apply(
        lambda row: ["background-color: rgba(57,135,229,0.22); font-weight: 600" if row.name == r.ticker else ""
                     for _ in row], axis=1)
    st.dataframe(styled, use_container_width=True, column_config={
        "Company": st.column_config.LinkColumn("Company ↗", display_text=r"#(.*)$",
                                               help="Click a company to open its full analysis in a new window"),
    })
    st.caption("Click a company name to open its full analysis in a new window.")
    st.caption(f"Money and per-share figures are shown in {r.currency}"
               + ("; " + "; ".join(fx_notes) + " (today's exchange rates)." if fx_notes else "."))

    # Side-by-side charts
    chart_cols = ["P/E (TTM)", "Forward P/E", "Revenue (TTM)", "Revenue growth YoY", "Revenue CAGR 3y", "Free cash flow (TTM)",
                  "Operating margin", "Profit margin", "Return on equity", "Debt to equity", "PEG",
                  "EPS (TTM)", "12-mo return (trailing)", "12-mo expected return (analyst target)"]
    grid = st.columns(3)
    i = 0
    for col in chart_cols:
        fig = charts.peer_bar(df, col, kinds[col], r.ticker, r.currency)
        if fig is not None:
            with grid[i % 3]:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            i += 1
    st.caption(f"{r.ticker} in blue. Negative P/E and PEG (loss-making companies) are left out of the rankings.")
