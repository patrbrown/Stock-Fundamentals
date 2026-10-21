"""Market trend state (from the 200-day moving average), relative strength and industry momentum.

The trend sits beside the TTT score and is never blended into it.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import market

STATES = ("Uptrend", "Recovering", "Mixed", "Weakening", "Downtrend")


def _ret(s: pd.Series, start_back: int, end_back: int = 0) -> float | None:
    """Return from `start_back` trading days ago to `end_back` days ago."""
    if s is None or len(s) <= start_back:
        return None
    a, b = float(s.iloc[-1 - start_back]), float(s.iloc[-1 - end_back])
    return b / a - 1 if a > 0 else None


def trend_state(close: pd.Series | None) -> dict:
    out = {"state": None, "ma50": None, "ma200": None, "price": None, "pct_below_6m": None}
    if close is None or len(close.dropna()) < 220:
        return out
    c = close.dropna()
    ma50, ma200 = c.rolling(50).mean(), c.rolling(200).mean()
    price, m50, m200 = float(c.iloc[-1]), float(ma50.iloc[-1]), float(ma200.iloc[-1])
    rising = m200 > float(ma200.iloc[-21])          # 200-day average higher than a month ago
    last6 = (c.iloc[-126:] < ma200.iloc[-126:])
    below_share = float(last6.mean())
    if price > m200:
        if m50 > m200 and rising:
            state = "Uptrend"
        elif below_share > 0.5:
            state = "Recovering"
        else:
            state = "Mixed"
    else:
        state = "Downtrend" if (m50 < m200 and not rising) else "Weakening"
    out.update(state=state, ma50=m50, ma200=m200, price=price, pct_below_6m=below_share)
    return out


def relative_strength(close: pd.Series | None) -> float | None:
    """12-month return minus the S&P 500's, skipping the most recent month (~21 trading days)."""
    spx = market.close_history("^GSPC", "2y")
    r_s, r_b = _ret(close, 252, 21), _ret(spx, 252, 21)
    return (r_s - r_b) if (r_s is not None and r_b is not None) else None


def industry_momentum(industry_key: str | None, exclude: str | None = None) -> float | None:
    """Average 6-month return of the industry's leading companies minus the S&P 500's 6-month return."""
    if not industry_key:
        return None
    members = [m for m in market.industry_members(industry_key, limit=10) if m != (exclude or "")]
    if not members:
        return None
    with ThreadPoolExecutor(max_workers=5) as pool:
        series = list(pool.map(lambda s: market.close_history(s, "1y"), members))
    rets = [r for r in (_ret(s, 126) for s in series) if r is not None]
    spx = _ret(market.close_history("^GSPC", "2y"), 126)
    if not rets or spx is None:
        return None
    return sum(rets) / len(rets) - spx


def build(close: pd.Series | None, industry_key: str | None, ticker: str | None = None) -> dict:
    t = trend_state(close)
    try:
        t["rs"] = relative_strength(close)
    except Exception:
        t["rs"] = None
    try:
        t["ind"] = industry_momentum(industry_key, exclude=ticker)
    except Exception:
        t["ind"] = None
    return t
