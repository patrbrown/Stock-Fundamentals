"""Share price, price history, splits and forward P/E from Yahoo Finance (no key needed).

Everything here is optional: if Yahoo is unreachable the fundamentals still work,
and the price-based ratios show as blank.
"""
from __future__ import annotations

from datetime import date

import pandas as pd


def market_data(ticker: str) -> dict:
    out = {"price": None, "forward_pe": None, "history": None, "splits": [], "error": None,
           "long_name": None, "sector": None, "industry": None, "industry_key": None,
           "target_mean": None, "analyst_count": None, "recommendation": None, "return_12m": None,
           "currency": None, "financial_currency": None, "exchange": None, "shares_outstanding": None,
           "symbol": ticker, "info": {}}
    try:
        import yfinance as yf
    except ImportError:
        out["error"] = "yfinance isn't installed"
        return out
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="10y", auto_adjust=False)
        if hist is not None and not hist.empty:
            closes = hist["Close"].copy()
            closes.index = pd.to_datetime(closes.index).tz_localize(None)
            out["history"] = closes
            out["price"] = float(closes.iloc[-1])
        splits = t.splits
        if splits is not None and len(splits):
            out["splits"] = [(pd.Timestamp(d).date(), float(r)) for d, r in splits.items() if r and r != 1]
        try:
            fast = t.fast_info
            lp = fast.get("last_price") if hasattr(fast, "get") else fast.last_price
            if lp:
                out["price"] = float(lp)
        except Exception:
            pass
        try:
            info = t.info or {}
            out["forward_pe"] = info.get("forwardPE")
            out["long_name"] = info.get("longName")
            out["sector"] = info.get("sector")
            out["industry"] = info.get("industry")
            out["industry_key"] = info.get("industryKey")
            out["target_mean"] = info.get("targetMeanPrice")
            out["analyst_count"] = info.get("numberOfAnalystOpinions")
            out["recommendation"] = (info.get("recommendationKey") or "").replace("_", " ") or None
            out["currency"] = info.get("currency")
            out["financial_currency"] = info.get("financialCurrency")
            out["exchange"] = info.get("fullExchangeName") or info.get("exchange")
            out["shares_outstanding"] = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            out["long_name"] = info.get("longName") or info.get("shortName")
            out["info"] = {k: info.get(k) for k in ("longName", "shortName", "quoteType", "country")}
        except Exception:
            pass
        if not out["currency"]:
            try:
                out["currency"] = t.fast_info.get("currency")
            except Exception:
                pass
        _fix_pence(out)
        h = out["history"]
        if h is not None and len(h) and out["price"]:
            year_ago = price_on(h, (h.index[-1] - pd.Timedelta(days=365)).date())
            if year_ago:
                out["return_12m"] = out["price"] / year_ago - 1
    except Exception as exc:  # network, delisted, rate-limited...
        out["error"] = f"Price data unavailable ({exc.__class__.__name__})"
    return out


def price_on(history: pd.Series | None, when: date) -> float | None:
    """Last close on or before `when`."""
    if history is None or history.empty:
        return None
    s = history.loc[: pd.Timestamp(when)]
    if s.empty or (pd.Timestamp(when) - s.index[-1]).days > 10:
        return None
    return float(s.iloc[-1])


def industry_leaders(industry_key: str | None, limit: int = 10) -> list[str]:
    """Largest companies in the same Yahoo industry (by market weight)."""
    if not industry_key:
        return []
    try:
        import yfinance as yf
        top = yf.Industry(industry_key).top_companies
        if top is None or top.empty:
            return []
        return [str(t).upper() for t in top.index[:limit]]
    except Exception:
        return []


# ------------------------------------------------------------------ currency handling

def _fix_pence(m: dict) -> None:
    """London quotes are in pence (GBp); convert to pounds."""
    if m.get("currency") in ("GBp", "GBX"):
        for k in ("price", "target_mean"):
            if m.get(k):
                m[k] = m[k] / 100
        if m.get("history") is not None:
            m["history"] = m["history"] / 100
        m["currency"] = "GBP"


_fx_cache: dict = {}


def fx_history(src: str, dst: str) -> pd.Series | None:
    """Daily closes of 1 unit of `src` in `dst` (e.g. USD->CAD ~1.37)."""
    if src == dst:
        return None
    key = (src, dst)
    if key in _fx_cache:
        return _fx_cache[key]
    series = None
    try:
        import yfinance as yf
        h = yf.Ticker(f"{src}{dst}=X").history(period="10y")
        if h is not None and not h.empty:
            series = h["Close"].copy()
            series.index = pd.to_datetime(series.index).tz_localize(None)
    except Exception:
        series = None
    _fx_cache[key] = series
    return series


def fx_rate(src: str | None, dst: str | None) -> float | None:
    if not src or not dst or src == dst:
        return 1.0
    h = fx_history(src, dst)
    return float(h.iloc[-1]) if h is not None and len(h) else None


def align_currency(mkt: dict, ticker: str, report_currency: str) -> dict:
    """Make price-based numbers use the same currency as the financial statements.

    For a Canadian company reporting in CAD but looked up by its US ticker, use its TSX listing
    (TICKER.TO) so the price is in CAD. Otherwise convert the price at the Yahoo FX rate.
    """
    listing = mkt.get("currency")
    mkt["price_currency"] = listing or report_currency
    if not mkt.get("price") or not listing or listing == report_currency:
        return mkt
    if report_currency == "CAD" and "." not in ticker:
        alt = market_data(f"{ticker}.TO")
        if alt.get("price") and alt.get("currency") == "CAD":
            alt["splits"] = mkt.get("splits") or alt.get("splits")
            for k in ("sector", "industry", "industry_key"):
                alt[k] = alt.get(k) or mkt.get(k)
            alt["price_currency"] = "CAD"
            alt["price_note"] = f"Share price from the TSX listing ({ticker}.TO) in CAD, to match the CAD financials."
            return alt
    fx = fx_history(listing, report_currency)
    if fx is None or fx.empty:
        mkt["price_note"] = (f"The share price is in {listing} but the financials are in {report_currency}, and no "
                             f"exchange rate was available, so price-based ratios are blank.")
        mkt["price"] = mkt["target_mean"] = None
        mkt["history"] = None
        return mkt
    rate = float(fx.iloc[-1])
    mkt["price"] = mkt["price"] * rate
    if mkt.get("target_mean"):
        mkt["target_mean"] = mkt["target_mean"] * rate
    h = mkt.get("history")
    if h is not None and len(h):
        aligned = fx.reindex(h.index.union(fx.index)).ffill().reindex(h.index).bfill()
        mkt["history"] = h * aligned
    mkt["price_currency"] = report_currency
    mkt["price_note"] = (f"{mkt.get('symbol', ticker)} trades in {listing}; its price was converted to {report_currency} "
                         f"at {rate:.4f} to match the {report_currency} financials.")
    return mkt


CANADIAN_EXCHANGES = {"TOR": "TSX", "VAN": "TSXV", "NEO": "Cboe Canada", "CNQ": "CSE"}


def search_canadian(query: str, limit: int = 10) -> list[dict]:
    """Yahoo search restricted to Canadian listings: [{'symbol': 'SU.TO', 'name': 'Suncor Energy Inc.', 'exchange': 'TSX'}]."""
    q = (query or "").strip()
    if not q:
        return []
    out = []
    try:
        import yfinance as yf
        quotes = yf.Search(q, max_results=25, news_count=0, lists_count=0, raise_errors=False).quotes or []
        if not any(CANADIAN_EXCHANGES.get(x.get("exchange")) for x in quotes):
            # catches small misspellings, e.g. "Galantis" -> Galantas
            quotes += yf.Search(q, max_results=25, news_count=0, lists_count=0, raise_errors=False,
                                enable_fuzzy_query=True).quotes or []
        for x in quotes:
            sym = str(x.get("symbol", "")).upper()
            exch = CANADIAN_EXCHANGES.get(x.get("exchange"))
            if not exch and not sym.endswith((".TO", ".V", ".NE", ".CN")):
                continue
            if x.get("quoteType") not in (None, "EQUITY"):
                continue
            out.append({"symbol": sym, "name": x.get("longname") or x.get("shortname") or sym,
                        "exchange": exch or sym.rsplit(".", 1)[-1]})
    except Exception:
        pass
    seen = {o["symbol"] for o in out}
    out = [o for i, o in enumerate(out) if o["symbol"] not in {x["symbol"] for x in out[:i]}]
    if q.upper().endswith((".TO", ".V", ".NE", ".CN")):
        if q.upper() not in seen:
            out.insert(0, {"symbol": q.upper(), "name": q.upper(), "exchange": q.upper().rsplit(".", 1)[-1]})
    elif q.replace("-", "").replace(".", "").isalnum() and len(q) <= 6 and " " not in q:
        # A bare symbol like "GAL": check which Canadian exchanges actually list it
        for suffix, exch in ((".TO", "TSX"), (".V", "TSXV"), (".CN", "CSE"), (".NE", "Cboe Canada")):
            sym = q.upper() + suffix
            if sym in seen:
                continue
            m = quick_quote(sym)
            if m:
                out.insert(0, {"symbol": sym, "name": m, "exchange": exch})
    return out[:limit]


def quick_quote(symbol: str) -> str | None:
    """Name of the listing if Yahoo has a live price for it, else None."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        fi = t.fast_info
        lp = fi.get("last_price") if hasattr(fi, "get") else fi.last_price
        if not lp:
            return None
        try:
            info = t.info or {}
            return info.get("longName") or info.get("shortName") or symbol
        except Exception:
            return symbol
    except Exception:
        return None
