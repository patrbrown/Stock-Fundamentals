"""Hover text that explains what makes up each bar (segments, or the line items behind a metric)."""
from __future__ import annotations

import math

import pandas as pd

from core import formatting as fmt

MAX_ROWS = 8


def _v(row, key):
    try:
        x = float(row.get(key))
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _lines(items) -> str:
    return "".join(f"<br>{txt}" for txt in items if txt)


def _pct(part, whole):
    return f" ({part / whole:.0%})" if (part is not None and whole) else ""


def segment_lines(rows: list[tuple[str, float]], total: float | None, cur: str, show_other: bool = True) -> list[str]:
    if not rows:
        return []
    base = total if total else sum(v for _, v in rows)
    out = [f"• {name}: {fmt.money(v, cur)}{_pct(v, base)}" for name, v in rows[:MAX_ROWS]]
    rest = rows[MAX_ROWS:]
    if rest:
        rv = sum(v for _, v in rest)
        out.append(f"• {len(rest)} others: {fmt.money(rv, cur)}{_pct(rv, base)}")
    if show_other and total:
        gap = total - sum(v for _, v in rows)
        if abs(gap) > abs(total) * 0.01:
            out.append(f"• Unallocated / other: {fmt.money(gap, cur)}{_pct(gap, total)}")
    return out


def hover_for(key: str, q: pd.DataFrame, cur: str, breakdowns: dict, revenue_axis: str | None) -> list[str]:
    """One HTML snippet per quarter for chart `key`."""
    out = []
    M = lambda x: fmt.money(x, cur)
    prev_rows = {d: q.iloc[i - 4] if i >= 4 else None for i, d in enumerate(q.index)}
    for d, row in q.iterrows():
        rev, cor, gp = _v(row, "revenue"), _v(row, "cost_of_revenue"), _v(row, "gross_profit")
        opi, da, ni = _v(row, "operating_income"), _v(row, "depreciation_amortization"), _v(row, "net_income")
        cfo, capex, fcf = _v(row, "cash_from_operations"), _v(row, "capex"), _v(row, "free_cash_flow")
        pre, tax, sh, eps = _v(row, "pretax_income"), _v(row, "income_tax"), _v(row, "diluted_shares"), _v(row, "eps_diluted")
        lines = []
        if key == "revenue":
            prev = prev_rows[d]
            pv = _v(prev, "revenue") if prev is not None else None
            if rev and pv and pv > 0:
                lines.append(f"Growth vs. year-ago quarter: {rev / pv - 1:+.1%}")
            axis_data = breakdowns.get("revenue", {}).get(revenue_axis or "", {})
            if d in axis_data:
                lines.append(f"<b>By {revenue_axis.lower()}</b>")
                lines += segment_lines(axis_data[d], rev, cur, show_other=False)
            elif breakdowns.get("revenue"):
                lines.append("<i>No breakdown filed for this quarter</i>")
        elif key == "gross_profit":
            lines += [f"Revenue: {M(rev)}", f"− Cost of revenue: {M(cor)}" if cor is not None else "",
                      f"Gross margin: {gp / rev:.1%}" if (gp is not None and rev) else ""]
        elif key == "operating_income":
            seg = breakdowns.get("operating_income", {}).get("Segment", {})
            if d in seg:
                lines.append("<b>By segment</b>")
                lines += segment_lines(seg[d], opi, cur, show_other=True)
            lines.append(f"Operating margin: {opi / rev:.1%}" if (opi is not None and rev) else "")
        elif key == "net_income":
            lines += [f"Operating income: {M(opi)}" if opi is not None else "",
                      f"Pre-tax income: {M(pre)}" if pre is not None else "",
                      f"− Income tax: {M(tax)}" + (f" ({tax / pre:.0%} rate)" if (tax is not None and pre and pre > 0) else "")
                      if tax is not None else "",
                      f"Net margin: {ni / rev:.1%}" if (ni is not None and rev) else ""]
        elif key == "eps_diluted":
            lines += [f"Net income: {M(ni)}" if ni is not None else "",
                      f"÷ Diluted shares: {fmt.shares(sh)}" if sh else ""]
            prev = prev_rows[d]
            pe_ = _v(prev, "eps_diluted") if prev is not None else None
            if eps is not None and pe_ and pe_ > 0:
                lines.append(f"Growth vs. year-ago quarter: {eps / pe_ - 1:+.1%}")
        elif key == "pe_ttm":
            price, eps_ttm = _v(row, "price"), _v(row, "eps_diluted_ttm")
            lines += [f"Share price at quarter end: {fmt.eps(price, cur)}" if price is not None else "",
                      f"÷ EPS, last 4 quarters: {fmt.eps(eps_ttm, cur)}" if eps_ttm is not None else ""]
            if eps_ttm is not None and eps_ttm <= 0:
                lines.append("<i>No P/E: trailing earnings were negative</i>")
        elif key == "ebitda":
            lines += [f"Operating income: {M(opi)}" if opi is not None else "",
                      f"+ Depreciation & amortization: {M(da)}" if da is not None else "",
                      f"EBITDA margin: {(opi + da) / rev:.1%}" if (opi is not None and da is not None and rev) else ""]
        elif key == "cash_from_operations":
            other = cfo - ni - da if None not in (cfo, ni, da) else None
            lines += [f"Net income: {M(ni)}" if ni is not None else "",
                      f"+ Depreciation & amortization: {M(da)}" if da is not None else "",
                      f"+ Working capital & other: {M(other)}" if other is not None else ""]
        elif key == "free_cash_flow":
            lines += [f"Cash from operations: {M(cfo)}" if cfo is not None else "",
                      f"− Capital expenditures: {M(capex)}" if capex is not None else "",
                      f"FCF margin: {fcf / rev:.1%}" if (fcf is not None and rev) else ""]
        out.append(_lines(lines))
    return out
