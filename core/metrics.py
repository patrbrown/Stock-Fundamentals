"""Growth (CAGR) and valuation/ratio snapshot built from the cleaned series."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

CAGR_METRICS = [
    ("revenue", "Revenue"),
    ("gross_profit", "Gross Profit"),
    ("operating_income", "Operating Income"),
    ("net_income", "Net Income"),
    ("eps_diluted", "EPS (diluted)"),
    ("ebitda", "EBITDA"),
    ("cash_from_operations", "Cash from Operations"),
    ("free_cash_flow", "Free Cash Flow"),
]


def cagr(start, end, years):
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError):
        return None
    if any(map(math.isnan, (start, end))) or start <= 0 or end <= 0 or years <= 0:
        return None  # CAGR is meaningless across losses
    return (end / start) ** (1 / years) - 1


def _val(x):
    try:
        x = float(x)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def growth_table(quarterly_all: pd.DataFrame, annual: pd.DataFrame) -> pd.DataFrame:
    """Rows = metrics; columns = TTM YoY, 3y/5y TTM CAGR (from quarters), and 3/5/10y fiscal-year CAGR."""
    rows = []
    q = quarterly_all
    a = annual.set_index("fiscal_year") if annual is not None and not annual.empty else None
    for key, name in CAGR_METRICS:
        r = {"Metric": name}
        ttm = q.get(f"{key}_ttm")
        if ttm is not None:
            ttm = ttm.dropna()
            for yrs, col in ((1, "TTM YoY"), (3, "3y CAGR (TTM)"), (5, "5y CAGR (TTM)")):
                lag = 4 * yrs
                r[col] = cagr(ttm.iloc[-1 - lag], ttm.iloc[-1], yrs) if len(ttm) > lag else None
        if a is not None and key in a:
            s = a[key].dropna()
            if len(s):
                last_fy = s.index.max()
                for yrs in (3, 5, 10):
                    r[f"{yrs}y CAGR (FY)"] = cagr(s.get(last_fy - yrs), s[last_fy], yrs) if (last_fy - yrs) in s.index else None
        rows.append(r)
    return pd.DataFrame(rows).set_index("Metric")


def snapshot(q: pd.DataFrame, market: dict, shares_out) -> dict:
    """Latest TTM ratios, mirroring a typical 'Statistics (TTM)' panel."""
    last = q.iloc[-1]
    year_ago = q.iloc[-5] if len(q) >= 5 else None
    price = market.get("price")
    shares = shares_out or _val(last.get("diluted_shares"))
    mcap = price * shares if price and shares else None

    g = lambda k: _val(last.get(k))
    rev, ni, eps = g("revenue_ttm"), g("net_income_ttm"), g("eps_diluted_ttm")
    cfo, fcf, ebitda, opi = g("cash_from_operations_ttm"), g("free_cash_flow_ttm"), g("ebitda_ttm"), g("operating_income_ttm")
    cash = (g("cash") or 0) + (g("short_term_investments") or 0)
    debt, equity = g("total_debt"), g("equity")
    net_debt = debt - cash if debt is not None else None

    div = lambda a, b: (a / b) if (a is not None and b not in (None, 0)) else None
    pos = lambda a, b: div(a, b) if (b is not None and b > 0) else None

    eps_prev = _val(year_ago.get("eps_diluted_ttm")) if year_ago is not None else None
    eps_growth = (eps / eps_prev - 1) if (eps and eps_prev and eps_prev > 0 and eps > 0) else None
    pe = pos(price, eps)
    peg = (pe / (eps_growth * 100)) if (pe and eps_growth and eps_growth > 0) else None

    eq_prev = _val(year_ago.get("equity")) if year_ago is not None else None
    avg_eq = (equity + eq_prev) / 2 if (equity and eq_prev) else equity
    tax, pretax = g("income_tax_ttm"), g("pretax_income_ttm")
    tax_rate = min(max(tax / pretax, 0), 0.5) if (tax is not None and pretax and pretax > 0) else 0.21
    invested = (debt or 0) + (equity or 0) - cash
    roic = (opi * (1 - tax_rate) / invested) if (opi is not None and invested > 0) else None
    ev = mcap + net_debt if (mcap and net_debt is not None) else mcap

    target = market.get("target_mean")
    rev_prev = _val(year_ago.get("revenue_ttm")) if year_ago is not None else None
    return {
        "price": price,
        "target_mean": target,
        "forward_return": (target / price - 1) if (target and price) else None,
        "return_12m": market.get("return_12m"),
        "analyst_count": market.get("analyst_count"),
        "recommendation": market.get("recommendation"),
        "revenue_growth": (rev / rev_prev - 1) if (rev and rev_prev and rev_prev > 0) else None,
        "fcf_margin": pos(fcf, rev),
        "market_cap": mcap,
        "enterprise_value": ev,
        "shares_outstanding": shares,
        "revenue_ttm": rev,
        "net_income_ttm": ni,
        "eps_ttm": eps,
        "ebitda_ttm": ebitda,
        "cfo_ttm": cfo,
        "fcf_ttm": fcf,
        "pe": pe,
        "forward_pe": market.get("forward_pe"),
        "peg": peg,
        "eps_growth_ttm": eps_growth,
        "earnings_yield": div(eps, price),
        "ps": pos(mcap, rev),
        "pcf": pos(mcap, cfo),
        "pfcf": pos(mcap, fcf),
        "fcf_yield": div(fcf, mcap),
        "ev_ebitda": pos(ev, ebitda),
        "profit_margin": pos(ni, rev),
        "operating_margin": pos(opi, rev),
        "roe": pos(ni, avg_eq),
        "roic": roic,
        "cash": cash,
        "total_debt": debt,
        "net_debt": net_debt,
        "debt_to_equity": pos(debt, equity),
        "equity": equity,
    }
