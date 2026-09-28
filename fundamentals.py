"""Turn SEC 'company facts' JSON into clean quarterly and annual series.

The main complications this module handles:
  * Q4 is never filed on its own: it's the 10-K annual figure minus the 9-month YTD.
  * Cash-flow statements in 10-Qs are year-to-date, so Q2/Q3 are differences.
  * Tag names differ between companies and over time (see concepts.py).
  * Stock splits: values filed before a split are adjusted to today's share basis.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from . import concepts

# US companies file 10-Q/10-K. Foreign companies that report in US GAAP (e.g. ARM) file quarterly
# results on 6-K and annual reports on 20-F/40-F; only their us-gaap facts are used either way.
FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "10-KT", "10-KT/A",
         "6-K", "6-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
QUARTER_DAYS = (80, 100)
ANNUAL_DAYS = (350, 380)


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _node(facts: dict, tag: str):
    f = facts.get("facts", {})
    for ns in ("us-gaap", "dei"):
        if tag in f.get(ns, {}):
            return f[ns][tag]
    return None


def _pick_unit(units: dict, kind: str):
    if kind == "eps":
        keys = [k for k in units if k.endswith("/shares")]
    elif kind == "shares":
        keys = [k for k in units if k == "shares"]
    else:
        keys = [k for k in units if "/" not in k and k not in ("shares", "pure")]
    if not keys:
        return None
    usd = [k for k in keys if k.startswith("USD")]
    return (usd or keys)[0]


class SplitAdjuster:
    """Restates per-share values and share counts filed before a split onto today's basis."""

    def __init__(self, splits: list[tuple[date, float]] | None):
        self.splits = sorted(splits or [])

    def factor(self, filed: date) -> float:
        f = 1.0
        for when, ratio in self.splits:
            if when > filed and ratio > 0:
                f *= ratio
        return f

    def apply(self, val: float, filed: date, kind: str) -> float:
        if kind == "eps":
            return val / self.factor(filed)
        if kind == "shares":
            return val * self.factor(filed)
        return val


# ---------------------------------------------------------------- raw extraction

def durations(facts, tags, kind, adj: SplitAdjuster):
    """{(start, end): value} merged across fallback tags (first tag wins per period)."""
    periods, used, unit = {}, [], None
    for tag in tags:
        node = _node(facts, tag)
        if not node:
            continue
        u = _pick_unit(node.get("units", {}), kind)
        if not u:
            continue
        best = {}
        for e in node["units"][u]:
            if e.get("form") not in FORMS or "start" not in e:
                continue
            key = (_d(e["start"]), _d(e["end"]))
            if key not in best or e["filed"] > best[key][0]:
                best[key] = (e["filed"], float(e["val"]))
        added = 0
        for key, (filed, val) in best.items():
            if key not in periods:
                periods[key] = adj.apply(val, _d(filed), kind)
                added += 1
        if added:
            used.append(tag)
            unit = unit or u
    return periods, used, unit


def instants(facts, tags, kind, adj: SplitAdjuster):
    """{end_date: value} merged across fallback tags."""
    points, used = {}, []
    for tag in tags:
        node = _node(facts, tag)
        if not node:
            continue
        u = _pick_unit(node.get("units", {}), kind)
        if not u:
            continue
        best = {}
        for e in node["units"][u]:
            if e.get("form") not in FORMS or "start" in e:
                continue
            k = _d(e["end"])
            if k not in best or e["filed"] > best[k][0]:
                best[k] = (e["filed"], float(e["val"]))
        added = 0
        for k, (filed, val) in best.items():
            if k not in points:
                points[k] = adj.apply(val, _d(filed), kind)
                added += 1
        if added:
            used.append(tag)
    return points, used


def quarterize(periods: dict) -> dict:
    """Discrete quarters {end: (value, derived?)} from a mix of 3/6/9/12-month periods."""
    q = {}
    for (s, e), v in periods.items():
        if QUARTER_DAYS[0] <= (e - s).days <= QUARTER_DAYS[1]:
            q[e] = (v, False)

    # YTD(start, e) - YTD(start, e_prev) where e_prev is one quarter earlier
    by_start = defaultdict(dict)
    for (s, e), v in periods.items():
        by_start[s][e] = v
    for s, ends in by_start.items():
        for e, v in sorted(ends.items()):
            if _near(q, e) or not (170 <= (e - s).days <= ANNUAL_DAYS[1]):
                continue
            for e2, v2 in ends.items():
                if QUARTER_DAYS[0] <= (e - e2).days <= QUARTER_DAYS[1]:
                    q[e] = (v - v2, True)
                    break

    # Fallback: annual minus the three discrete quarters inside it
    for (s, e), v in periods.items():
        if _near(q, e) or not (ANNUAL_DAYS[0] <= (e - s).days <= ANNUAL_DAYS[1]):
            continue
        inside = [val for end, (val, _) in q.items() if s + timedelta(80) <= end <= e - timedelta(80)]
        if len(inside) == 3:
            q[e] = (v - sum(inside), True)
    return q


def annualize(periods: dict) -> dict:
    return {e: v for (s, e), v in periods.items() if ANNUAL_DAYS[0] <= (e - s).days <= ANNUAL_DAYS[1]}


def _near(d: dict, when: date, tol: int = 6):
    if when in d:
        return d[when]
    for k, v in d.items():
        if abs((k - when).days) <= tol:
            return v
    return None


# ---------------------------------------------------------------- fiscal labels

def fiscal_label(end: date, fy_ends: list[date]) -> tuple[int, int]:
    """(fiscal_year, quarter) for a quarter ending on `end`."""
    anchor = None
    for a in sorted(fy_ends):
        if a >= end - timedelta(7):
            anchor = a
            break
    if anchor is None:
        anchor = max(fy_ends) if fy_ends else date(end.year, 12, 31)
        while anchor < end - timedelta(7):
            anchor = anchor + timedelta(days=364 if (anchor + timedelta(364)).month == anchor.month else 365)
    fy = anchor.year - 1 if (anchor.month == 1 and anchor.day <= 7) else anchor.year
    start = anchor - timedelta(365)
    qn = int(round((end - start).days / 91.3))
    return fy, min(max(qn, 1), 4)


# ---------------------------------------------------------------- main builder

def build(facts: dict, splits=None, n_quarters: int = 20) -> dict:
    if not facts.get("facts", {}).get("us-gaap"):
        raise ValueError(
            "This company reports under IFRS rather than US GAAP (common for foreign companies filing "
            "20-F/40-F), so the SEC has no structured quarterly data for it."
        )
    adj = SplitAdjuster(splits)
    kinds = {"eps_diluted": "eps", "diluted_shares": "shares"}

    flow_q, flow_a, tags_used, derived, currency = {}, {}, {}, {}, None
    for key, tags in concepts.FLOW.items():
        kind = kinds.get(key, "money")
        periods, used, unit = durations(facts, tags, kind, adj)
        q = quarterize(periods)
        if key == "diluted_shares":  # averages aren't additive: keep only reported quarters
            q = {e: (v, d) for e, (v, d) in q.items() if not d}
        flow_q[key] = {e: v for e, (v, _) in q.items()}
        derived[key] = {e for e, (_, d) in q.items() if d}
        flow_a[key] = annualize(periods)
        tags_used[key] = used
        if key == "revenue" and unit:
            currency = unit
    # Tax items for ROIC
    for key, tags in {"income_tax": ["IncomeTaxExpenseBenefit"],
                      "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                                        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]}.items():
        periods, used, _ = durations(facts, tags, "money", adj)
        flow_q[key] = {e: v for e, (v, _) in quarterize(periods).items()}
        tags_used[key] = used

    inst = {}
    for key, tags in concepts.INSTANT.items():
        inst[key], tags_used[key] = instants(facts, tags, "money", adj)
    shares_out, _ = instants(facts, concepts.SHARES_OUTSTANDING, "shares", adj)

    # Quarter calendar: anchor on revenue, fall back to net income
    anchor_key = "revenue" if len(flow_q["revenue"]) >= 4 else "net_income"
    all_ends = sorted(flow_q[anchor_key])
    if not all_ends:
        raise ValueError("No quarterly revenue or net income found in this company's filings.")
    fy_ends = sorted(set(flow_a[anchor_key]) | set(flow_a["net_income"]))

    rows = []
    for e in all_ends:
        fy, qn = fiscal_label(e, fy_ends)
        r = {"period_end": e, "fiscal_year": fy, "fiscal_quarter": qn, "label": f"Q{qn} FY{str(fy)[2:]}"}
        for key in flow_q:
            r[key] = _near(flow_q[key], e)
        for key in inst:
            r[key] = _near(inst[key], e)
        rows.append(r)
    q = pd.DataFrame(rows).set_index("period_end").sort_index()
    q = q[~q.index.duplicated(keep="last")]
    debt_known = any(tags_used[k] for k in ("total_debt", "debt_noncurrent", "debt_current", "short_term_borrowings"))
    q = _derive(q, capex_known=bool(flow_q["capex"]), debt_known=debt_known)

    # Derived-value flags (for footnotes)
    flags = defaultdict(set)
    for key, ends in derived.items():
        for e in ends:
            flags[key].add(e)
    for e in q.index:
        if e in flags["operating_income"] or e in flags["depreciation_amortization"]:
            flags["ebitda"].add(e)
        if e in flags["cash_from_operations"] or e in flags["capex"]:
            flags["free_cash_flow"].add(e)
        if _near(flow_q["gross_profit"], e) is None and (e in flags["revenue"] or e in flags["cost_of_revenue"]):
            flags["gross_profit"].add(e)

    # Annual table
    arows = []
    for e in sorted(set(flow_a[anchor_key])):
        fy, _ = fiscal_label(e, fy_ends)
        r = {"period_end": e, "fiscal_year": fy, "label": f"FY{fy}"}
        for key in flow_a:
            r[key] = _near(flow_a[key], e, tol=10)
        for key in inst:
            r[key] = _near(inst[key], e)
        arows.append(r)
    a = pd.DataFrame(arows)
    if not a.empty:
        a = a.set_index("period_end").sort_index()
        a = a[~a["fiscal_year"].duplicated(keep="last")]
        a = _derive(a, capex_known=bool(flow_q["capex"]), debt_known=debt_known, annual=True)

    latest_shares = None
    if shares_out:
        last = max(shares_out)
        # multi-class companies report one value per class on the same date; sum them
        latest_shares = shares_out[last]
        same_day = _all_values_on(facts, concepts.SHARES_OUTSTANDING[0], last, adj)
        if same_day:
            latest_shares = same_day

    return {
        "quarterly_all": q,
        "quarterly": q.tail(n_quarters),
        "annual": a,
        "derived_flags": {k: sorted(v) for k, v in flags.items()},
        "tags_used": tags_used,
        "currency": (currency or "USD").split("/")[0],
        "shares_outstanding": latest_shares,
        "capex_known": bool(flow_q["capex"]),
        "debt_known": debt_known,
    }


def _all_values_on(facts, tag, when, adj):
    node = _node(facts, tag)
    if not node or "shares" not in node.get("units", {}):
        return None
    latest_filed = {}
    for e in node["units"]["shares"]:
        if _d(e["end"]) == when and e.get("form") in FORMS:
            # one value per share class (distinct 'frame'/'accn' rows on the same date)
            latest_filed.setdefault(e["accn"], []).append(e)
    if not latest_filed:
        return None
    accn = max(latest_filed, key=lambda k: latest_filed[k][0]["filed"])
    vals = {float(x["val"]) for x in latest_filed[accn]}
    filed = _d(latest_filed[accn][0]["filed"])
    return adj.apply(sum(vals), filed, "shares")


def _derive(df: pd.DataFrame, capex_known: bool, debt_known: bool = True, annual: bool = False) -> pd.DataFrame:
    df = df.copy()
    num = lambda c: pd.to_numeric(df.get(c), errors="coerce") if c in df else pd.Series(np.nan, index=df.index)
    rev, cor = num("revenue"), num("cost_of_revenue")
    df["gross_profit"] = num("gross_profit").fillna(rev - cor)
    df["ebitda"] = num("operating_income") + num("depreciation_amortization")
    capex = num("capex") if capex_known else pd.Series(0.0, index=df.index)
    df["free_cash_flow"] = num("cash_from_operations") - capex
    # Debt: total if tagged, else current + non-current; plus short-term borrowings
    comp = num("debt_noncurrent").add(num("debt_current"), fill_value=0)
    comp[num("debt_noncurrent").isna() & num("debt_current").isna()] = np.nan
    df["total_debt"] = num("total_debt").fillna(comp).add(num("short_term_borrowings").fillna(0))
    if not debt_known:
        df["total_debt"] = 0.0  # company has never tagged any debt
    with np.errstate(divide="ignore", invalid="ignore"):
        safe_rev = rev.where(rev > 0)
        df["gross_margin"] = df["gross_profit"] / safe_rev
        df["operating_margin"] = num("operating_income") / safe_rev
        df["net_margin"] = num("net_income") / safe_rev
        df["fcf_margin"] = df["free_cash_flow"] / safe_rev
    lag = 1 if annual else 4
    for src, dst in (("revenue", "revenue_yoy"), ("eps_diluted", "eps_yoy")):
        cur, prev = num(src), num(src).shift(lag)
        df[dst] = np.where(prev > 0, cur / prev - 1, np.nan)
    if not annual:
        for col in ("revenue", "gross_profit", "operating_income", "net_income", "eps_diluted",
                    "ebitda", "cash_from_operations", "free_cash_flow", "income_tax", "pretax_income"):
            s = pd.to_numeric(df[col], errors="coerce")
            ttm = s.rolling(4, min_periods=4).sum()
            # only trust TTM when the 4 quarters are consecutive (~1 year apart)
            span = pd.Series(pd.to_datetime(df.index), index=df.index).diff(3).dt.days
            ok = span.between(250, 300)
            df[f"{col}_ttm"] = ttm.where(ok)
    return df
