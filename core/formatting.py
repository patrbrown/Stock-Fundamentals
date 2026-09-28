"""Human-readable number formatting shared by the app and the Excel export."""
from __future__ import annotations

import math


def _bad(x) -> bool:
    try:
        return x is None or math.isnan(float(x))
    except (TypeError, ValueError):
        return True


SYMBOLS = {"USD": "$", "CAD": "C$", "AUD": "A$", "EUR": "€", "GBP": "£", "JPY": "¥", "CHF": "CHF ",
           "HKD": "HK$", "CNY": "CN¥", "INR": "₹", "SEK": "SEK ", "NOK": "NOK ", "DKK": "DKK "}


def symbol(currency: str | None) -> str:
    c = (currency or "USD").upper()
    return SYMBOLS.get(c, c + " ")


def money(x, currency: str = "USD") -> str:
    if _bad(x):
        return "—"
    sym = symbol(currency)
    x = float(x)
    sign = "-" if x < 0 else ""
    a = abs(x)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{sign}{sym}{a / div:,.2f}{suf}"
    return f"{sign}{sym}{a:,.0f}"


def pct(x) -> str:
    return "—" if _bad(x) else f"{float(x) * 100:.2f}%"


def ratio(x) -> str:
    return "—" if _bad(x) else f"{float(x):,.2f}"


def eps(x, currency: str = "USD") -> str:
    if _bad(x):
        return "—"
    sym = symbol(currency)
    return f"-{sym}{abs(float(x)):,.2f}" if float(x) < 0 else f"{sym}{float(x):,.2f}"


def shares(x) -> str:
    if _bad(x):
        return "—"
    x = float(x)
    return f"{x / 1e9:,.2f}B" if x >= 1e9 else f"{x / 1e6:,.1f}M"


def by_kind(x, kind: str, currency: str = "USD") -> str:
    return {"money": lambda v: money(v, currency), "pct": pct, "ratio": ratio,
            "eps": lambda v: eps(v, currency), "shares": shares}[kind](x)
