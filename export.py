"""Excel export: Summary, Quarterly, Annual, Growth and Notes sheets."""
from __future__ import annotations

import io

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .concepts import METRICS
from .metrics import CAGR_METRICS
from .report import CompanyReport

QUARTER_ROWS = [
    "revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "ebitda",
    "cash_from_operations", "capex", "free_cash_flow", "gross_margin", "operating_margin",
    "net_margin", "fcf_margin", "revenue_yoy", "eps_yoy", "diluted_shares", "cash",
    "total_debt", "equity", "price", "pe_ttm",
]

NUMFMT = {"money": '#,##0.0,,"M";[Red]-#,##0.0,,"M"', "eps": '#,##0.00;[Red]-#,##0.00',
          "pct": '0.0%;[Red]-0.0%', "ratio": '0.00', "shares": '#,##0.0,,"M"'}
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def metric_table(df: pd.DataFrame, rows=QUARTER_ROWS) -> pd.DataFrame:
    rows = [r for r in rows if r in df.columns]
    t = df[rows].T
    t.columns = df["label"].tolist()
    t.index = [METRICS[r][0] for r in rows]
    return t


def _style_sheet(ws, kinds_by_row: dict | None = None, first_col_width=30):
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = first_col_width
    for i in range(2, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(i)].width = 14
    ws.freeze_panes = "B2"
    if kinds_by_row:
        for row in ws.iter_rows(min_row=2):
            fmt = NUMFMT.get(kinds_by_row.get(row[0].value, "money"))
            for c in row[1:]:
                c.number_format = fmt


def to_excel(r: CompanyReport) -> bytes:
    buf = io.BytesIO()
    kinds = {v[0]: v[1] for v in METRICS.values()}
    s = r.snapshot
    summary = [
        ("Company", r.name), ("Ticker", r.ticker), ("SEC CIK", r.cik or "n/a"),
        ("Currency (all money and per-share figures)", r.currency),
        ("Data source", "SEC filings" if r.source == "SEC" else "Yahoo Finance"),
        ("Share price", s["price"]), ("Market cap", s["market_cap"]), ("Enterprise value", s["enterprise_value"]),
        ("Revenue (TTM)", s["revenue_ttm"]), ("Net income (TTM)", s["net_income_ttm"]),
        ("EPS diluted (TTM)", s["eps_ttm"]), ("EBITDA (TTM)", s["ebitda_ttm"]),
        ("Cash from operations (TTM)", s["cfo_ttm"]), ("Free cash flow (TTM)", s["fcf_ttm"]),
        ("P/E (TTM)", s["pe"]), ("Forward P/E (Yahoo)", s["forward_pe"]), ("PEG (P/E ÷ TTM EPS growth)", s["peg"]),
        ("Earnings yield", s["earnings_yield"]), ("P/S", s["ps"]), ("P/CF", s["pcf"]), ("P/FCF", s["pfcf"]),
        ("FCF yield", s["fcf_yield"]), ("EV/EBITDA", s["ev_ebitda"]), ("Profit margin", s["profit_margin"]),
        ("Operating margin", s["operating_margin"]), ("ROE", s["roe"]), ("ROIC", s["roic"]),
        ("Cash + short-term investments", s["cash"]), ("Total debt", s["total_debt"]), ("Net debt", s["net_debt"]),
        ("Debt to equity", s["debt_to_equity"]),
        ("Revenue growth YoY (TTM)", s.get("revenue_growth")), ("FCF margin", s.get("fcf_margin")),
        ("Trailing 12-month return", s.get("return_12m")), ("Analyst mean target", s.get("target_mean")),
        ("Expected 12-month return (to target)", s.get("forward_return")),
    ]
    pct_rows = {"Earnings yield", "FCF yield", "Profit margin", "Operating margin", "ROE", "ROIC",
                "Revenue growth YoY (TTM)", "FCF margin", "Trailing 12-month return", "Expected 12-month return (to target)"}
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame(summary, columns=["Item", "Value"]).to_excel(xw, sheet_name="Summary", index=False)
        ws = xw.sheets["Summary"]
        _style_sheet(ws)
        ws.column_dimensions["B"].width = 22
        for row in ws.iter_rows(min_row=2):
            name, c = row[0].value, row[1]
            if not isinstance(c.value, (int, float)) or name == "SEC CIK":
                continue
            if name in pct_rows:
                c.number_format = NUMFMT["pct"]
            elif name.startswith(("P/", "PEG", "EV/", "Forward", "Debt to")):
                c.number_format = NUMFMT["ratio"]
            elif name.startswith(("EPS", "Share price", "Analyst mean")):
                c.number_format = NUMFMT["eps"]
            else:
                c.number_format = NUMFMT["money"]

        qt = metric_table(r.quarterly)
        qt.to_excel(xw, sheet_name="Quarterly", index_label="Metric")
        _style_sheet(xw.sheets["Quarterly"], kinds)

        if r.annual is not None and not r.annual.empty:
            at = metric_table(r.annual, [x for x in QUARTER_ROWS if x not in ("price", "pe_ttm")])
            at.to_excel(xw, sheet_name="Annual", index_label="Metric")
            _style_sheet(xw.sheets["Annual"], kinds)

        r.growth.to_excel(xw, sheet_name="Growth", index_label="Metric")
        _style_sheet(xw.sheets["Growth"], {n: "pct" for _, n in CAGR_METRICS}, 24)

        notes = [("Source", "SEC EDGAR XBRL company facts (10-Q / 10-K), prices from Yahoo Finance"),
                 ("Money units", f"{r.currency}. Quarterly/Annual sheets show money in millions; cells hold full values"),
                 ("EBITDA", "Operating income + depreciation & amortization"),
                 ("Free cash flow", "Cash from operations − capital expenditures"),
                 ("Q4 values", "Derived as annual (10-K) minus 9-month year-to-date")]
        notes += [("Note", n) for n in r.notes]
        for key, dates in r.derived_flags.items():
            if key in METRICS and dates:
                shown = [d for d in dates if d in set(r.quarterly.index)]
                if shown:
                    notes.append((f"Derived: {METRICS[key][0]}", ", ".join(r.quarterly.loc[shown, "label"])))
        for key, tags in r.tags_used.items():
            if tags:
                notes.append((f"XBRL tags: {METRICS.get(key, (key,))[0]}", ", ".join(tags)))
        pd.DataFrame(notes, columns=["Item", "Detail"]).to_excel(xw, sheet_name="Notes", index=False)
        _style_sheet(xw.sheets["Notes"], None, 34)
        xw.sheets["Notes"].column_dimensions["B"].width = 110
    return buf.getvalue()
