"""One call that produces everything the app shows for a ticker.

`build_report("DELL")` returns a CompanyReport. A competitor comparison later is just
several reports side by side, so keep new features working off this object.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import fundamentals, market, metrics, sec_client, segments, yahoo_fundamentals


@dataclass
class CompanyReport:
    ticker: str
    name: str
    cik: int | None
    currency: str                    # currency of the financial statements
    quarterly: pd.DataFrame          # last N quarters
    quarterly_all: pd.DataFrame      # full history (for growth calcs)
    annual: pd.DataFrame
    growth: pd.DataFrame
    snapshot: dict
    derived_flags: dict
    tags_used: dict
    notes: list = field(default_factory=list)
    sector: str | None = None
    industry: str | None = None
    industry_key: str | None = None
    breakdowns: dict = field(default_factory=dict)   # segment/product/region splits (see segments.py)
    source: str = "SEC"              # "SEC" (EDGAR filings) or "Yahoo" (TSX / IFRS companies)
    price_symbol: str | None = None  # the listing the share price comes from (e.g. ENB.TO)
    exchange: str | None = None


def build_report(ticker: str, n_quarters: int = 20, refresh: bool = False, with_market: bool = True,
                 with_segments: bool = False, progress=None) -> CompanyReport:
    """SEC filings when the company files with the SEC in US GAAP; otherwise Yahoo Finance statements."""
    t = ticker.strip().upper()
    if yahoo_fundamentals.is_yahoo_symbol(t):
        return build_report_yahoo(t, n_quarters)
    try:
        return build_report_sec(t, n_quarters, refresh, with_market, with_segments, progress)
    except sec_client.SecError as exc:
        if "Couldn't reach" in str(exc) or "contact" in str(exc):
            raise
        sec_problem = str(exc)
    except ValueError as exc:   # IFRS filer, or no usable quarterly data
        sec_problem = str(exc)
    try:
        r = build_report_yahoo(t, n_quarters)
    except Exception:
        raise ValueError(sec_problem)
    why = ("it reports under IFRS" if "IFRS" in sec_problem
           else "it isn't an SEC filer" if "No US SEC filer" in sec_problem or "isn't in" in sec_problem
           else "its filings have no usable quarterly figures")
    r.notes.insert(0, f"These figures come from Yahoo Finance because the SEC has no usable quarterly data "
                      f"for this company ({why}).")
    return r


def build_report_sec(ticker: str, n_quarters: int = 20, refresh: bool = False, with_market: bool = True,
                     with_segments: bool = False, progress=None) -> CompanyReport:
    info = sec_client.lookup(ticker)
    facts = sec_client.company_facts(info["cik"], force=refresh)
    mkt = market.market_data(info["ticker"]) if with_market else {"price": None, "splits": [], "history": None}

    data = fundamentals.build(facts, splits=mkt.get("splits"), n_quarters=n_quarters)
    if with_market:
        mkt = market.align_currency(mkt, info["ticker"], data["currency"])

    notes = []
    if len(data["quarterly"]) < n_quarters:
        notes.append(f"Only {len(data['quarterly'])} quarters of XBRL data are available for this company.")
    if not data["capex_known"]:
        notes.append("No capital-expenditure line found, so free cash flow equals cash from operations.")
    if not data["debt_known"]:
        notes.append("No debt appears in this company's filings, so debt is treated as zero.")
    if mkt.get("splits"):
        recent = [f"{r:g}-for-1 on {d:%b %d, %Y}" for d, r in mkt["splits"] if (pd.Timestamp.today().date() - d).days < 365 * 12]
        if recent:
            notes.append("Per-share figures are adjusted for splits: " + ", ".join(recent) + ".")

    r = _finish(ticker=info["ticker"], name=sec_client.pretty_name(facts.get("entityName") or info["title"]),
                cik=info["cik"], data=data, mkt=mkt, n_quarters=n_quarters, notes=notes, source="SEC")
    if with_segments:
        try:
            r.breakdowns = segments.build_breakdowns(info["cik"], facts, list(r.quarterly.index), progress=progress)
        except Exception as exc:  # segment data is a nice-to-have
            r.notes.append(f"Segment breakdowns unavailable ({exc.__class__.__name__}).")
    return r


def build_report_yahoo(symbol: str, n_quarters: int = 20) -> CompanyReport:
    data = yahoo_fundamentals.build(symbol, n_quarters)
    mkt = market.market_data(symbol)
    mkt = market.align_currency(mkt, symbol, data["currency"])
    nq = len(data["quarterly"])
    if data.get("periods") == "years":
        notes = [f"Yahoo Finance has no quarterly statements for this company, so the charts show its "
                 f"{nq} most recent fiscal years instead."]
    else:
        notes = [f"Source: Yahoo Finance, which provides about 5 quarters and 4 fiscal years of statements "
                 f"({nq} quarters here). See Annual & growth for the longer view."]
    latest = data.get("latest_period")
    if latest and (pd.Timestamp.today().date() - latest).days > 270:
        notes.insert(0, f"⚠️ Yahoo's most recent statements for this company are from {latest:%B %Y}, so these "
                        f"figures are out of date. The company's newer filings are on SEDAR+ (sedarplus.ca).")
    if data["quarterly"]["revenue"].isna().all():
        notes.append("No revenue is reported (typical for exploration-stage companies), so revenue-based "
                     "margins and ratios are blank.")
    if not data["debt_known"]:
        notes.append("No debt figure was reported, so debt is treated as zero.")
    return _finish(ticker=symbol, name=data["name"], cik=None, data=data, mkt=mkt, n_quarters=n_quarters,
                   notes=notes, source="Yahoo")


def _finish(*, ticker, name, cik, data, mkt, n_quarters, notes, source) -> CompanyReport:
    q_all = data["quarterly_all"]
    # Historical P/E at each quarter end (price already in the statements' currency)
    hist = mkt.get("history")
    prices = [market.price_on(hist, d) for d in q_all.index]
    q_all["price"] = prices
    eps_ttm = pd.to_numeric(q_all["eps_diluted_ttm"], errors="coerce")
    q_all["pe_ttm"] = [p / e if (p and e and e > 0) else None for p, e in zip(prices, eps_ttm)]
    q = q_all.tail(n_quarters)

    if mkt.get("error"):
        notes.append(mkt["error"] + ". Price-based ratios are blank.")
    if mkt.get("price_note"):
        notes.append(mkt["price_note"])

    snap = metrics.snapshot(q_all, mkt, data["shares_outstanding"])
    g = metrics.growth_table(q_all, data["annual"])
    snap["revenue_cagr_3y"] = _cell(g, "Revenue", "3y CAGR (TTM)") or _cell(g, "Revenue", "3y CAGR (FY)")
    snap["revenue_cagr_5y"] = _cell(g, "Revenue", "5y CAGR (FY)")
    snap["eps_cagr_3y"] = _cell(g, "EPS (diluted)", "3y CAGR (TTM)") or _cell(g, "EPS (diluted)", "3y CAGR (FY)")
    snap["price_currency"] = mkt.get("price_currency") or data["currency"]
    # Short histories (Yahoo: ~5 quarters) can't give a TTM-vs-year-ago comparison; use fiscal years instead
    a = data["annual"]
    if a is not None and len(a) >= 2:
        def fy_growth(col):
            cur_, prev_ = pd.to_numeric(a[col], errors="coerce").iloc[-1], pd.to_numeric(a[col], errors="coerce").iloc[-2]
            return float(cur_ / prev_ - 1) if (pd.notna(cur_) and pd.notna(prev_) and prev_ > 0 and cur_ > 0) else None
        if snap.get("revenue_growth") is None:
            snap["revenue_growth"] = fy_growth("revenue")
        if snap.get("eps_growth_ttm") is None:
            snap["eps_growth_ttm"] = fy_growth("eps_diluted")
            if snap["eps_growth_ttm"] and snap.get("pe"):
                snap["peg"] = snap["pe"] / (snap["eps_growth_ttm"] * 100)

    return CompanyReport(
        ticker=ticker, name=name, cik=cik, currency=data["currency"],
        quarterly=q, quarterly_all=q_all, annual=data["annual"], growth=g, snapshot=snap,
        derived_flags=data["derived_flags"], tags_used=data["tags_used"], notes=notes,
        sector=mkt.get("sector"), industry=mkt.get("industry"), industry_key=mkt.get("industry_key"),
        source=source, price_symbol=mkt.get("symbol") or ticker, exchange=mkt.get("exchange"),
    )


def _cell(df, row, col):
    try:
        v = df.loc[row, col]
        return None if v is None or pd.isna(v) else float(v)
    except KeyError:
        return None
