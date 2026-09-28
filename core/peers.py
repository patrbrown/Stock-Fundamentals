"""Competitor comparison: pick peers and line their key stats up against the subject company."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import market, sec_client, yahoo_fundamentals
from .report import CompanyReport, build_report

# (snapshot key, column label, kind, higher_is_better)
COMPARE = [
    ("market_cap", "Market cap", "money", True),
    ("pe", "P/E (TTM)", "ratio", False),
    ("forward_pe", "Forward P/E", "ratio", False),
    ("revenue_ttm", "Revenue (TTM)", "money", True),
    ("revenue_growth", "Revenue growth YoY", "pct", True),
    ("revenue_cagr_3y", "Revenue CAGR 3y", "pct", True),
    ("eps_ttm", "EPS (TTM)", "eps", True),
    ("eps_growth_ttm", "EPS growth YoY", "pct", True),
    ("fcf_ttm", "Free cash flow (TTM)", "money", True),
    ("fcf_margin", "FCF margin", "pct", True),
    ("operating_margin", "Operating margin", "pct", True),
    ("profit_margin", "Profit margin", "pct", True),
    ("roe", "Return on equity", "pct", True),
    ("debt_to_equity", "Debt to equity", "ratio", False),
    ("peg", "PEG", "ratio", False),
    ("return_12m", "12-mo return (trailing)", "pct", True),
    ("forward_return", "12-mo expected return (analyst target)", "pct", True),
]


def suggest_peers(r: CompanyReport, limit: int = 5) -> list[str]:
    """Leading companies in the same industry (SEC filers, or TSX listings via Yahoo)."""
    known = sec_client.ticker_map()
    out = []
    for t in market.industry_leaders(r.industry_key, limit=15):
        sec_t = t.replace(".", "-")
        if yahoo_fundamentals.is_yahoo_symbol(t):
            cand = t
        elif sec_t in known and known[sec_t]["cik"] != r.cik:
            cand = sec_t
        else:
            continue
        if cand != r.ticker and cand not in out:
            out.append(cand)
        if len(out) >= limit:
            break
    return out


def load_peers(tickers: list[str], n_quarters: int = 20) -> tuple[list[CompanyReport], dict[str, str]]:
    """Build reports in parallel. Returns (reports, {ticker: error}) — foreign filers etc. just get skipped."""
    reports, errors = {}, {}

    def one(t):
        try:
            return t, build_report(t, n_quarters=n_quarters), None
        except Exception as exc:
            return t, None, str(exc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for t, rep, err in pool.map(one, tickers):
            if rep:
                reports[t] = rep
            else:
                errors[t] = err
    return [reports[t] for t in tickers if t in reports], errors


def comparison_frame(subject: CompanyReport, peers: list[CompanyReport]) -> tuple[pd.DataFrame, list[str]]:
    """One row per company. Money and per-share values are converted into the subject's currency
    so they can be compared; returns (frame, notes about conversions)."""
    base = subject.currency
    rows, notes = [], []
    for r in [subject] + peers:
        rate = market.fx_rate(r.currency, base)
        row = {"Ticker": r.ticker, "Company": r.name, "Reports in": r.currency}
        for key, label, kind, _ in COMPARE:
            v = r.snapshot.get(key)
            if kind in ("money", "eps") and v is not None:
                v = v * rate if rate else None
            row[label] = v
        if r.currency != base:
            notes.append(f"{r.ticker}: {r.currency} converted to {base} at {rate:.4f}" if rate
                         else f"{r.ticker}: no {r.currency}→{base} rate available, so its money figures are blank")
        rows.append(row)
    return pd.DataFrame(rows).set_index("Ticker"), notes


def ranks(df: pd.DataFrame, subject: str) -> dict[str, tuple[int, int]]:
    """{column: (rank of subject, companies with data)}; rank 1 = best."""
    out = {}
    for key, label, _, higher in COMPARE:
        s = pd.to_numeric(df[label], errors="coerce").dropna()
        if label in ("P/E (TTM)", "Forward P/E", "PEG"):
            s = s[s > 0]   # negative P/E means losses, not cheapness
        if subject not in s.index or len(s) < 2:
            continue
        order = s.sort_values(ascending=not higher)
        out[label] = (list(order.index).index(subject) + 1, len(s))
    return out
