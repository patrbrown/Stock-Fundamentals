"""Financial statements from Yahoo Finance, for companies the SEC doesn't cover (TSX/TSXV listings,
and cross-listed companies that report under IFRS).

Yahoo's free data goes back about 5 quarters and 4 fiscal years, so these reports are shorter than
SEC-based ones; the annual table and fiscal-year growth fill in the longer view.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import fundamentals

INCOME = {
    "revenue": ["TotalRevenue", "OperatingRevenue"],
    "cost_of_revenue": ["CostOfRevenue", "ReconciledCostOfRevenue"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncome", "TotalOperatingIncomeAsReported"],
    "net_income": ["NetIncomeCommonStockholders", "NetIncome", "NetIncomeContinuousOperations"],
    "eps_diluted": ["DilutedEPS", "BasicEPS"],
    "diluted_shares": ["DilutedAverageShares", "BasicAverageShares"],
    "pretax_income": ["PretaxIncome"],
    "income_tax": ["TaxProvision"],
    "depreciation_amortization": ["ReconciledDepreciation"],
}
CASH = {
    "cash_from_operations": ["OperatingCashFlow", "CashFlowFromContinuingOperatingActivities"],
    "capex": ["CapitalExpenditure", "PurchaseOfPPE"],
    "depreciation_amortization": ["DepreciationAndAmortization", "DepreciationAmortizationDepletion"],
}
BALANCE = {
    "cash": ["CashAndCashEquivalents", "CashCashEquivalentsAndShortTermInvestments"],
    "short_term_investments": ["OtherShortTermInvestments"],
    "total_debt": ["TotalDebt"],
    "equity": ["StockholdersEquity", "CommonStockEquity"],
}

EXCHANGE_SUFFIXES = (".TO", ".V", ".NE", ".CN")


def is_yahoo_symbol(t: str) -> bool:
    return t.upper().endswith(EXCHANGE_SUFFIXES)


def _statements(ticker, freq: str) -> dict[str, pd.DataFrame]:
    out = {}
    for name, fn in (("income", ticker.get_income_stmt), ("cash", ticker.get_cash_flow),
                     ("balance", ticker.get_balance_sheet)):
        try:
            df = fn(freq=freq, pretty=False)
            out[name] = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        except Exception:
            out[name] = pd.DataFrame()
    return out


def _table(stmts: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    """Rows = period end dates, columns = our metric keys (first available Yahoo line item wins)."""
    dates = set()
    for df in stmts.values():
        dates.update(pd.to_datetime(df.columns).date if len(df.columns) else [])
    rows = {d: {} for d in dates}
    used = {}
    for stmt, mapping in (("income", INCOME), ("cash", CASH), ("balance", BALANCE)):
        df = stmts.get(stmt, pd.DataFrame())
        if df.empty:
            continue
        df = df.copy()
        df.columns = pd.to_datetime(df.columns).date
        for key, names in mapping.items():
            for n in names:
                if n not in df.index:
                    continue
                for d, v in df.loc[n].items():
                    if pd.notna(v) and rows[d].get(key) is None:
                        rows[d][key] = float(v)
                        used.setdefault(key, [])
                        if n not in used[key]:
                            used[key].append(n)
    t = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    if "capex" in t:
        t["capex"] = t["capex"].abs()   # Yahoo reports capex as a negative cash flow
    return t, used


def build(symbol: str, n_quarters: int = 20) -> dict:
    import yfinance as yf

    tk = yf.Ticker(symbol)
    q_raw, q_used = _table(_statements(tk, "quarterly"))
    a_raw, a_used = _table(_statements(tk, "yearly"))
    if q_raw.empty and a_raw.empty:
        raise ValueError(f"Yahoo Finance has no financial statements for {symbol}. This is common for small "
                         "exploration-stage companies, which file only on SEDAR+.")
    try:
        info = tk.info or {}
    except Exception:
        info = {}

    fy_ends = sorted(a_raw.index) if not a_raw.empty else []
    capex_known = "capex" in q_raw or "capex" in a_raw
    debt_known = "total_debt" in q_raw or "total_debt" in a_raw

    def finish(raw: pd.DataFrame, annual: bool) -> pd.DataFrame:
        if raw.empty:
            return raw
        raw = raw.copy()
        if annual:
            raw["fiscal_year"] = [fundamentals.fiscal_label(d, fy_ends)[0] for d in raw.index]
            raw["label"] = [f"FY{y}" for y in raw["fiscal_year"]]
        else:
            labs = [fundamentals.fiscal_label(d, fy_ends) for d in raw.index]
            raw["fiscal_year"] = [y for y, _ in labs]
            raw["fiscal_quarter"] = [qn for _, qn in labs]
            raw["label"] = [f"Q{qn} FY{str(y)[2:]}" for y, qn in labs]
        for col in ("revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income", "eps_diluted",
                    "diluted_shares", "pretax_income", "income_tax", "depreciation_amortization",
                    "cash_from_operations", "capex", "cash", "short_term_investments", "total_debt", "equity"):
            if col not in raw:
                raw[col] = np.nan
        return fundamentals._derive(raw, capex_known=capex_known, debt_known=debt_known, annual=annual)

    q_all = finish(q_raw, annual=False)
    a = finish(a_raw, annual=True)
    periods = "quarters"
    if q_all.empty and not a.empty:
        # Common for small TSXV companies: Yahoo only has fiscal years. Chart those instead,
        # treating each year as its own trailing-twelve-month figure.
        q_all = a.copy()
        for col in ("revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "ebitda",
                    "cash_from_operations", "free_cash_flow", "income_tax", "pretax_income"):
            if col in q_all:
                q_all[f"{col}_ttm"] = q_all[col]
        periods = "years"
    latest = max(list(q_all.index) + list(a.index)) if (len(q_all) or len(a)) else None
    tags = {k: [f"Yahoo: {', '.join(v)}"] for k, v in {**a_used, **q_used}.items()}
    return {
        "quarterly_all": q_all,
        "quarterly": q_all.tail(n_quarters),
        "annual": a,
        "derived_flags": {},
        "tags_used": tags,
        "currency": info.get("financialCurrency") or info.get("currency") or "USD",
        "shares_outstanding": info.get("sharesOutstanding") or info.get("impliedSharesOutstanding"),
        "capex_known": capex_known,
        "debt_known": debt_known,
        "name": info.get("longName") or info.get("shortName") or symbol,
        "periods": periods,
        "latest_period": latest,
    }
