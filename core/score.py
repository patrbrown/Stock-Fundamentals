"""TTT Score: a 0–100 score for the quality of a business and the price you pay for it.

Four pillars (Value 25, Growth 25, Quality 30, Financial Health 20). Every check scores on a
sliding scale between a "zero" and a "full" threshold (no pass/fail cliffs). A missing number skips
its check and the rest of that pillar is re-weighted. Red flags cap the total (59 with one, 39 with
two or more). Banks, insurers, brokers, asset managers and exchanges use the financials scorecard.

All cut-offs live in THRESHOLDS below, so they can be tuned in one place.
Educational scoring model, not investment advice.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

import pandas as pd

PILLARS = (("value", "Value", 25), ("growth", "Growth", 25), ("quality", "Quality", 30),
           ("health", "Financial Health", 20))

# (zero-credit value, full-credit value). Works in either direction.
THRESHOLDS = {
    # --- main scorecard ---
    "pe_vs_median":        (1.40, 0.70),   # current P/E ÷ own 5-year median P/E
    "peg":                 (2.50, 1.00),   # forward P/E ÷ expected EPS growth (%)
    "fwd_vs_trailing":     (-0.05, 0.15),  # forward EPS ÷ trailing EPS − 1
    "fcf_yield":           (0.00, 0.06),   # TTM free cash flow ÷ market cap
    "rev_cagr_5y":         (0.00, 0.15),
    "rev_cagr_10y":        (0.00, 0.12),
    "trend_rise_share":    (0.20, 1.00),   # share of years the figure rose
    "trend_cagr":          (0.00, 0.15),   # how fast it rose
    "roic":                (0.05, 0.20),
    "margin_std":          (0.10, 0.02),   # std dev of yearly operating margin (10pp → 0, 2pp → full)
    "margin_drift":        (-0.05, 0.00),  # latest margin minus earlier average
    "cash_conversion":     (0.50, 1.00),   # free cash ÷ net income, 3-year sums
    "roic_year":           (0.05, 0.15),   # per-year ROIC for durability
    "debt_to_equity":      (2.00, 0.30),
    "debt_to_ebitda":      (4.00, 1.00),
    "share_cagr":          (0.03, -0.02),  # +3 %/yr dilution → 0, −2 %/yr buybacks → full
    "interest_coverage":   (2.00, 15.0),
    "fcf_positive_share":  (0.50, 1.00),   # share of the last ~10 fiscal years with positive FCF
    # --- financials scorecard ---
    "ptbv_vs_median":      (1.40, 0.70),
    "shareholder_yield":   (0.01, 0.06),   # (dividends + buybacks) ÷ market cap
    "tbvps_cagr_5y":       (0.00, 0.10),
    "fin_rev_cagr_5y":     (0.00, 0.10),
    "roe":                 (0.05, 0.15),
    "roa":                 (0.003, 0.015),
    "roe_year":            (0.05, 0.15),
    "equity_to_assets":    (0.05, 0.12),
    "payout_ratio":        (1.00, 0.40),
    "profitable_share":    (0.50, 1.00),
}
RED_FLAG_CAPS = {1: 59, 2: 39}            # max score with one flag / two or more
CAPEX_MULTIPLE = 2.0                       # "heavy investor" when capex > 2× depreciation

FIN_INDUSTRIES = ("bank", "insurance", "capital markets", "asset management", "credit services",
                  "financial data & stock exchanges", "mortgage finance", "financial conglomerates",
                  "shell companies")
FIN_EXCEPTIONS = {"V", "MA", "PYPL"}      # payment networks stay on the main scorecard

BANDS = ((80, "lime"), (65, "green"), (50, "amber"), (0, "red"))


# ---------------------------------------------------------------- result types

@dataclass
class Check:
    pillar: str
    name: str
    value: str            # human-readable measurement, e.g. "18.4%"
    rule: str             # what earns full credit
    fraction: float | None  # 0..1, None = skipped (missing data)
    points: float = 0.0     # max points after re-weighting
    earned: float = 0.0


@dataclass
class ScoreResult:
    scored: bool
    reason: str = ""                        # why not scored
    total: int | None = None
    uncapped: float | None = None
    pillars: dict = field(default_factory=dict)   # key -> {"label", "earned", "max"}
    checks: list = field(default_factory=list)
    red_flags: list = field(default_factory=list)
    scorecard: str = "main"                 # "main" | "financials"
    capex_heavy: bool = False
    band: str | None = None
    trend: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- helpers

def lin(x, zero, full) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if full == zero:
        return 1.0 if x >= full else 0.0
    return max(0.0, min(1.0, (x - zero) / (full - zero)))


def _num(x):
    try:
        x = float(x)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def pct(x, d=1):
    return "—" if x is None else f"{x * 100:.{d}f}%"


def times(x, d=1):
    return "—" if x is None else f"{x:.{d}f}×"


def yearly(annual: pd.DataFrame, q_all: pd.DataFrame, col: str, ttm: bool = True) -> list[tuple[date, float]]:
    """Fiscal-year values, plus the latest twelve months as the newest point.

    Fiscal years that end within ~10 months of the latest quarter are dropped when the TTM point is
    added, so consecutive points never mostly overlap.
    """
    pts = []
    if annual is not None and not annual.empty and col in annual:
        for d, v in pd.to_numeric(annual[col], errors="coerce").items():
            if pd.notna(v):
                pts.append((d, float(v)))
    if ttm and q_all is not None and not q_all.empty and f"{col}_ttm" in q_all:
        s = pd.to_numeric(q_all[f"{col}_ttm"], errors="coerce").dropna()
        if len(s):
            d_ttm, v_ttm = s.index[-1], float(s.iloc[-1])
            if not pts or (d_ttm - pts[-1][0]).days > 20:
                pts = [(d, v) for d, v in pts if (d_ttm - d).days >= 300] + [(d_ttm, v_ttm)]
            else:
                pts[-1] = (pts[-1][0], v_ttm)
    return sorted(pts)


def cagr_years(pts, years: float) -> float | None:
    if len(pts) < 2:
        return None
    d1, v1 = pts[-1]
    target = d1 - timedelta(days=round(years * 365.25))
    best = min(pts[:-1], key=lambda p: abs((p[0] - target).days))
    if abs((best[0] - target).days) > 200:
        return None
    d0, v0 = best
    yrs = (d1 - d0).days / 365.25
    if v0 <= 0 or v1 <= 0 or yrs <= 0:
        return None
    return (v1 / v0) ** (1 / yrs) - 1


def trend_fraction(pts, n_changes: int = 5):
    """'How often it rose, and how fast': half for the share of rising years, half for the growth rate."""
    pts = pts[-(n_changes + 1):]
    if len(pts) < 4:
        return None, "—"
    vals = [v for _, v in pts]
    rises = sum(1 for a, b in zip(vals, vals[1:]) if b > a)
    share = rises / (len(vals) - 1)
    first, last = vals[0], vals[-1]
    yrs = max((pts[-1][0] - pts[0][0]).days / 365.25, 0.5)
    if first > 0 and last > 0:
        g = (last / first) ** (1 / yrs) - 1
        speed = lin(g, *THRESHOLDS["trend_cagr"])
        gtxt = f"{g * 100:+.1f}%/yr"
    elif first <= 0 < last:
        speed, gtxt = 1.0, "turned positive"
    else:
        speed, gtxt = 0.0, "negative"
    frac = 0.5 * lin(share, *THRESHOLDS["trend_rise_share"]) + 0.5 * speed
    return frac, f"rose {rises} of {len(vals) - 1} yrs · {gtxt}"


def margin_stability(pts_num, pts_den):
    den = dict(pts_den)
    m = [(d, n / den[d]) for d, n in pts_num if d in den and den[d] and den[d] > 0]
    m = m[-6:]
    if len(m) < 4:
        return None, "—"
    vals = [v for _, v in m]
    sd = statistics.pstdev(vals)
    drift = vals[-1] - statistics.mean(vals[:-1])
    frac = 0.5 * lin(sd, *THRESHOLDS["margin_std"]) + 0.5 * lin(drift, *THRESHOLDS["margin_drift"])
    return frac, f"latest {pct(vals[-1])} · swing ±{sd * 100:.1f}pp · {drift * 100:+.1f}pp vs avg"


def _tax_rate(tax, pretax):
    if tax is None or not pretax or pretax <= 0:
        return 0.21
    return min(max(tax / pretax, 0.0), 0.5)


# ---------------------------------------------------------------- main entry

def is_financial(industry: str | None, ticker: str) -> bool:
    if ticker.split(".")[0].upper() in FIN_EXCEPTIONS:
        return False
    ind = (industry or "").lower()
    return any(k in ind for k in FIN_INDUSTRIES)


def compute(q_all: pd.DataFrame, annual: pd.DataFrame, snap: dict, mkt: dict, ticker: str,
            industry: str | None, trend: dict | None = None) -> ScoreResult:
    trend = trend or {}
    qt = (mkt.get("quote_type") or "").upper()
    if qt in ("ETF", "MUTUALFUND"):
        return ScoreResult(False, "ETFs aren't scored.", trend=trend)
    if "reit" in (industry or "").lower():
        return ScoreResult(False, "REITs aren't scored (their earnings work differently).", trend=trend)
    rev_pts = yearly(annual, q_all, "revenue") or yearly(annual, q_all, "net_income")
    if len(rev_pts) < 5 or (rev_pts[-1][0] - rev_pts[0][0]).days < 4.5 * 365:
        return ScoreResult(False, "Needs at least 5 years of financial history to be scored.", trend=trend)

    fin = is_financial(industry, ticker)
    checks = (_financial_checks if fin else _main_checks)(q_all, annual, snap, mkt)
    flags, capex_heavy = (_financial_flags if fin else _main_flags)(q_all, annual, snap)

    pillars = {}
    total = 0.0
    for key, label, pts in PILLARS:
        mine = [c for c in checks if c.pillar == key]
        live = [c for c in mine if c.fraction is not None]
        if not live:
            pillars[key] = {"label": label, "earned": None, "max": pts}
            continue
        each = pts / len(live)
        earned = 0.0
        for c in live:
            c.points = each
            c.earned = each * c.fraction
            earned += c.earned
        pillars[key] = {"label": label, "earned": earned, "max": pts}
        total += earned
    # A pillar with no data at all: scale the others up so the total stays on a 0–100 scale
    covered = sum(p["max"] for p in pillars.values() if p["earned"] is not None)
    if covered == 0:
        return ScoreResult(False, "Not enough data to score.", trend=trend)
    total = total * 100 / covered
    uncapped = total
    if flags:
        total = min(total, RED_FLAG_CAPS[min(len(flags), 2)])
    score = int(round(total))
    band = next(name for floor, name in BANDS if score >= floor)
    return ScoreResult(True, total=score, uncapped=uncapped, pillars=pillars, checks=checks, red_flags=flags,
                       scorecard="financials" if fin else "main", capex_heavy=capex_heavy and not fin,
                       band=band, trend=trend)


# ---------------------------------------------------------------- main scorecard

def _capex_heavy(q_all) -> bool:
    last = q_all.iloc[-1]
    capex, da = _num(last.get("capex_ttm")), _num(last.get("depreciation_amortization_ttm"))
    return bool(capex and da and da > 0 and capex > CAPEX_MULTIPLE * da)


def _pe_vs_median(q_all, pe_now, col="pe_ttm"):
    if col not in q_all:
        return None, "—"
    hist = pd.to_numeric(q_all[col], errors="coerce").dropna().tail(20)
    hist = hist[hist > 0]
    if len(hist) < 8 or pe_now is None:
        return None, "—"
    med = float(hist.median())
    if pe_now <= 0:
        return 0.0, f"negative earnings vs median {med:.1f}"
    r = pe_now / med
    return lin(r, *THRESHOLDS["pe_vs_median"]), f"{pe_now:.1f} now vs {med:.1f} median ({r:.2f}×)"


def _fwd_growth(mkt):
    fe, te = _num(mkt.get("forward_eps")), _num(mkt.get("trailing_eps"))
    if fe is None or te is None:
        return None
    if te <= 0:
        return 1.0 if fe > 0 else -1.0
    return fe / te - 1


def _main_checks(q_all, annual, snap, mkt) -> list[Check]:
    T = THRESHOLDS
    last = q_all.iloc[-1]
    checks: list[Check] = []
    heavy = _capex_heavy(q_all)

    # ---- Value
    f, txt = _pe_vs_median(q_all, snap.get("pe"))
    checks.append(Check("value", "P/E vs its own 5-year median", txt, "≤0.7× its median for full credit", f))

    g = _fwd_growth(mkt)
    fpe = _num(snap.get("forward_pe"))
    if fpe is None and _num(mkt.get("forward_eps")) and snap.get("price"):
        fe = _num(mkt.get("forward_eps"))
        fpe = snap["price"] / fe if fe and fe > 0 else None
    if g is None or fpe is None:
        checks.append(Check("value", "PEG (forward)", "—", "≤1.0 for full credit", None))
    elif g <= 0 or fpe <= 0:
        checks.append(Check("value", "PEG (forward)", "earnings not expected to grow", "≤1.0 for full credit", 0.0))
    else:
        peg = fpe / (g * 100)
        checks.append(Check("value", "PEG (forward)", f"{peg:.2f} (fwd P/E {fpe:.1f} ÷ {g * 100:.1f}% growth)",
                            "≤1.0 for full credit", lin(peg, *T["peg"])))

    checks.append(Check("value", "Forward vs trailing earnings",
                        "—" if g is None else f"{g * 100:+.1f}% expected over the next 12 months",
                        "+15% or more for full credit", lin(g, *T["fwd_vs_trailing"])))

    fcf, mcap = _num(last.get("free_cash_flow_ttm")), _num(snap.get("market_cap"))
    fy = fcf / mcap if (fcf is not None and mcap) else None
    checks.append(Check("value", "Free-cash-flow yield", pct(fy), "6% or more for full credit",
                        lin(fy, *T["fcf_yield"])))

    # ---- Growth
    rev = yearly(annual, q_all, "revenue")
    c5, c10 = cagr_years(rev, 5), cagr_years(rev, 10)
    checks.append(Check("growth", "Revenue growth, 5 years", pct(c5) + ("/yr" if c5 is not None else ""),
                        "15%/yr or more for full credit", lin(c5, *T["rev_cagr_5y"])))
    checks.append(Check("growth", "Revenue growth, 10 years", pct(c10) + ("/yr" if c10 is not None else ""),
                        "12%/yr or more for full credit", lin(c10, *T["rev_cagr_10y"])))
    f, txt = trend_fraction(yearly(annual, q_all, "net_income"))
    checks.append(Check("growth", "Net income trend", txt, "rising every year at 15%/yr for full credit", f))
    cash_col = "owner_cash" if heavy else "free_cash_flow"
    cash_pts = _owner_cash_pts(annual, q_all) if heavy else yearly(annual, q_all, "free_cash_flow")
    f, txt = trend_fraction(cash_pts)
    checks.append(Check("growth", "Cash-flow trend" + (" (maintenance capex only)" if heavy else ""), txt,
                        "rising every year at 15%/yr for full credit", f))

    # ---- Quality
    cash_now = (_num(last.get("cash")) or 0.0) + (_num(last.get("short_term_investments")) or 0.0)
    debt_now = _num(snap.get("total_debt"))
    roic = _roic(_num(last.get("operating_income_ttm")), _num(last.get("income_tax_ttm")),
                 _num(last.get("pretax_income_ttm")), debt_now, _num(snap.get("equity")), cash_now)
    if roic is None:
        roic = _num(snap.get("roic"))
    checks.append(Check("quality", "Return on invested capital", pct(roic), "20% or more for full credit",
                        lin(roic, *T["roic"])))
    f, txt = margin_stability(yearly(annual, q_all, "operating_income"), yearly(annual, q_all, "revenue"))
    checks.append(Check("quality", "Operating margin stability", txt, "steady (±2pp) and not shrinking", f))

    ni3 = yearly(annual, q_all, "net_income")[-3:]
    cash3 = cash_pts[-3:]
    if len(ni3) == 3 and len(cash3) == 3:
        ni_sum, cash_sum = sum(v for _, v in ni3), sum(v for _, v in cash3)
        if ni_sum > 0:
            conv = cash_sum / ni_sum
            checks.append(Check("quality", "Cash conversion" + (" (maintenance capex only)" if heavy else ""),
                                f"{conv * 100:.0f}% of profit became free cash (3 yrs)",
                                "100% or more for full credit", lin(conv, *T["cash_conversion"])))
        else:
            checks.append(Check("quality", "Cash conversion", "no profit over 3 yrs", "100% or more", 0.0))
    else:
        checks.append(Check("quality", "Cash conversion", "—", "100% or more", None))

    yr_roic = _annual_roic(annual)[-10:]
    if len(yr_roic) >= 4:
        f = sum(lin(v, *T["roic_year"]) for v in yr_roic) / len(yr_roic)
        hi = sum(1 for v in yr_roic if v >= T["roic_year"][1])
        checks.append(Check("quality", "ROIC durability", f"{hi} of {len(yr_roic)} yrs at 15%+",
                            "15%+ every year for full credit", f))
    else:
        checks.append(Check("quality", "ROIC durability", "—", "15%+ every year", None))

    # ---- Financial health
    debt, equity = _num(snap.get("total_debt")), _num(snap.get("equity"))
    if debt is None and equity is not None:
        debt = 0.0   # no debt anywhere in the filings
    ebitda = _num(last.get("ebitda_ttm"))
    sh5 = _share_cagr(annual, 5)
    use_earnings = equity is None or equity <= 0 or (
        debt is not None and equity and debt / equity > 1.5 and sh5 is not None and sh5 < -0.01)
    if debt is None:
        checks.append(Check("health", "Debt load", "—", "low debt", None))
    elif use_earnings:
        if ebitda and ebitda > 0:
            x = debt / ebitda
            checks.append(Check("health", "Debt load (vs earnings; buybacks shrank equity)", f"{x:.1f}× EBITDA",
                                "≤1× EBITDA for full credit", lin(x, *T["debt_to_ebitda"])))
        else:
            checks.append(Check("health", "Debt load", "debt with no EBITDA", "≤1× EBITDA", 0.0 if debt > 0 else 1.0))
    else:
        de = debt / equity
        checks.append(Check("health", "Debt load", f"{de:.2f}× equity", "≤0.3× equity for full credit",
                            lin(de, *T["debt_to_equity"])))

    checks.append(Check("health", "Share count", "—" if sh5 is None else f"{sh5 * 100:+.1f}%/yr over 5 yrs",
                        "shrinking 2%/yr for full credit", lin(sh5, *T["share_cagr"])))

    cov = _coverage(last, debt, equity)
    checks.append(Check("health", "Interest coverage", cov[1], "15× or more for full credit", cov[0]))

    fcf_years = [v for _, v in yearly(annual, q_all, "free_cash_flow", ttm=False)][-10:]
    if len(fcf_years) >= 5:
        pos = sum(1 for v in fcf_years if v > 0)
        checks.append(Check("health", "Free-cash-flow history", f"positive in {pos} of {len(fcf_years)} yrs",
                            "positive every year for full credit",
                            lin(pos / len(fcf_years), *T["fcf_positive_share"])))
    else:
        checks.append(Check("health", "Free-cash-flow history", "—", "positive every year", None))
    return checks


def _owner_cash_pts(annual, q_all):
    """Cash from operations minus maintenance spending (estimated as depreciation)."""
    cfo = dict(yearly(annual, q_all, "cash_from_operations"))
    da = dict(yearly(annual, q_all, "depreciation_amortization"))
    return sorted((d, cfo[d] - da[d]) for d in cfo if d in da)


def _annual_roic(annual) -> list[float]:
    out = []
    if annual is None or annual.empty:
        return out
    for _, r in annual.iterrows():
        opi = _num(r.get("operating_income"))
        eq, debt = _num(r.get("equity")), _num(r.get("total_debt")) or 0.0
        cash = (_num(r.get("cash")) or 0.0) + (_num(r.get("short_term_investments")) or 0.0)
        if opi is None or eq is None:
            continue
        v = _roic(opi, _num(r.get("income_tax")), _num(r.get("pretax_income")), debt, eq, cash)
        if v is not None:
            out.append(v)
    return out


def _roic(opi, tax, pretax, debt, eq, cash):
    """After-tax operating profit ÷ (debt + equity − cash).

    When cash swamps the capital base (cash-rich companies) the ratio explodes, so cash is only netted off
    while invested capital stays above a quarter of debt + equity.
    """
    if opi is None or eq is None:
        return None
    gross = (debt or 0.0) + eq
    if gross <= 0:
        return None
    inv = gross - (cash or 0.0)
    if inv < 0.25 * gross:
        inv = gross
    return opi * (1 - _tax_rate(tax, pretax)) / inv


def _share_cagr(annual, years) -> float | None:
    pts = yearly(annual, None, "diluted_shares", ttm=False)
    pts = [(d, v) for d, v in pts if v > 0]
    return cagr_years(pts, years) if len(pts) >= 3 else None


def _coverage(last, debt, equity):
    opi, ie = _num(last.get("operating_income_ttm")), _num(last.get("interest_expense_ttm"))
    if ie is not None and ie > 0 and opi is not None:
        c = opi / ie
        return lin(c, *THRESHOLDS["interest_coverage"]), f"{c:.1f}× (operating profit ÷ interest)"
    if debt is not None and (debt == 0 or (equity and equity > 0 and debt / equity < 0.1)):
        return 1.0, "little or no debt"
    return None, "—"


def _main_flags(q_all, annual, snap):
    last = q_all.iloc[-1]
    flags = []
    ni = _num(last.get("net_income_ttm"))
    if ni is not None and ni < 0:
        flags.append("Net loss over the last 12 months")
    fcf3 = [v for _, v in yearly(annual, q_all, "free_cash_flow", ttm=False)][-3:]
    if len(fcf3) == 3 and sum(1 for v in fcf3 if v < 0) >= 2:
        flags.append("Negative free cash flow in 2 of the last 3 years")
    sh3 = _share_cagr(annual, 3)
    if sh3 is not None and sh3 > 0.04:
        flags.append(f"Share count growing {sh3 * 100:.1f}% a year")
    opi, ie = _num(last.get("operating_income_ttm")), _num(last.get("interest_expense_ttm"))
    if ie and ie > 0 and opi is not None and opi / ie < 2:
        flags.append(f"Operating profit covers interest only {opi / ie:.1f}×")
    return flags, _capex_heavy(q_all)


# ---------------------------------------------------------------- financials scorecard

def _tbvps_points(annual, q_all=None):
    out = []
    if annual is None or annual.empty:
        return out
    for d, r in annual.iterrows():
        eq, sh = _num(r.get("equity")), _num(r.get("diluted_shares"))
        if eq is None or not sh:
            continue
        tbv = eq - (_num(r.get("goodwill")) or 0) - (_num(r.get("intangibles")) or 0)
        out.append((d, tbv / sh))
    return out


def _financial_checks(q_all, annual, snap, mkt) -> list[Check]:
    T = THRESHOLDS
    last = q_all.iloc[-1]
    checks: list[Check] = []
    price, mcap = _num(snap.get("price")), _num(snap.get("market_cap"))

    # ---- Value
    f, txt = _pe_vs_median(q_all, snap.get("pe"))
    checks.append(Check("value", "P/E vs its own 5-year median", txt, "≤0.7× its median", f))
    # price-to-tangible-book at each quarter end vs today
    eq = pd.to_numeric(q_all.get("equity"), errors="coerce")
    gw = pd.to_numeric(q_all.get("goodwill"), errors="coerce").fillna(0) if "goodwill" in q_all else 0
    ia = pd.to_numeric(q_all.get("intangibles"), errors="coerce").fillna(0) if "intangibles" in q_all else 0
    sh = pd.to_numeric(q_all.get("diluted_shares"), errors="coerce").ffill()
    tbvps = (eq - gw - ia) / sh
    px = pd.to_numeric(q_all.get("price"), errors="coerce")
    ptbv_hist = (px / tbvps).where(tbvps > 0).dropna().tail(20)
    shares_now = _num(snap.get("shares_outstanding"))
    tb_now = _num(tbvps.dropna().iloc[-1]) if tbvps.notna().any() else None
    if shares_now and eq.notna().any():
        tbv_total = float(eq.dropna().iloc[-1]) - float(gw.iloc[-1] if hasattr(gw, "iloc") else 0) \
            - float(ia.iloc[-1] if hasattr(ia, "iloc") else 0)
        tb_now = tbv_total / shares_now
    if price and tb_now and tb_now > 0 and len(ptbv_hist) >= 8:
        now, med = price / tb_now, float(ptbv_hist.median())
        r = now / med
        checks.append(Check("value", "Price-to-tangible-book vs its 5-year median",
                            f"{now:.2f} now vs {med:.2f} median ({r:.2f}×)", "≤0.7× its median",
                            lin(r, *T["ptbv_vs_median"])))
    else:
        checks.append(Check("value", "Price-to-tangible-book vs its 5-year median", "—", "≤0.7× its median", None))
    div, bb = _num(last.get("dividends_paid_ttm")), _num(last.get("buybacks_ttm"))
    if mcap and (div is not None or bb is not None):
        y = ((div or 0) + (bb or 0)) / mcap
        checks.append(Check("value", "Shareholder yield", f"{pct(y)} (dividends + buybacks)", "6% or more",
                            lin(y, *T["shareholder_yield"])))
    else:
        checks.append(Check("value", "Shareholder yield", "—", "6% or more", None))

    # ---- Growth
    tb = _tbvps_points(annual)
    g = cagr_years(tb, 5) if len(tb) >= 5 else None
    checks.append(Check("growth", "Tangible book value per share growth", pct(g) + ("/yr" if g is not None else ""),
                        "10%/yr or more", lin(g, *T["tbvps_cagr_5y"])))
    c5 = cagr_years(yearly(annual, q_all, "revenue"), 5)
    checks.append(Check("growth", "Revenue growth, 5 years", pct(c5) + ("/yr" if c5 is not None else ""),
                        "10%/yr or more", lin(c5, *T["fin_rev_cagr_5y"])))
    f, txt = trend_fraction(yearly(annual, q_all, "eps_diluted"))
    checks.append(Check("growth", "EPS trend", txt, "rising every year at 15%/yr", f))

    # ---- Quality
    roe = _num(snap.get("roe"))
    checks.append(Check("quality", "Return on equity", pct(roe), "15% or more", lin(roe, *T["roe"])))
    ni, ta = _num(last.get("net_income_ttm")), _num(last.get("total_assets"))
    roa = ni / ta if (ni is not None and ta) else None
    checks.append(Check("quality", "Return on assets", pct(roa, 2), "1.5% or more", lin(roa, *T["roa"])))
    f, txt = margin_stability(yearly(annual, q_all, "pretax_income"), yearly(annual, q_all, "revenue"))
    checks.append(Check("quality", "Pre-tax margin stability", txt, "steady (±2pp) and not shrinking", f))
    roes = []
    for _, r in (annual.iterrows() if annual is not None else []):
        n, e = _num(r.get("net_income")), _num(r.get("equity"))
        if n is not None and e and e > 0:
            roes.append(n / e)
    roes = roes[-10:]
    if len(roes) >= 4:
        f = sum(lin(v, *T["roe_year"]) for v in roes) / len(roes)
        hi = sum(1 for v in roes if v >= T["roe_year"][1])
        checks.append(Check("quality", "ROE durability", f"{hi} of {len(roes)} yrs at 15%+", "15%+ every year", f))
    else:
        checks.append(Check("quality", "ROE durability", "—", "15%+ every year", None))

    # ---- Financial health
    eqn = _num(last.get("equity"))
    ea = eqn / ta if (eqn is not None and ta) else None
    checks.append(Check("health", "Equity vs total assets", pct(ea), "12% or more",
                        lin(ea, *T["equity_to_assets"])))
    sh5 = _share_cagr(annual, 5)
    checks.append(Check("health", "Share count", "—" if sh5 is None else f"{sh5 * 100:+.1f}%/yr over 5 yrs",
                        "shrinking 2%/yr", lin(sh5, *T["share_cagr"])))
    div3 = yearly(annual, None, "dividends_paid", ttm=False)[-3:]
    ni3 = dict(yearly(annual, None, "net_income", ttm=False))
    pairs = [(v, ni3[d]) for d, v in div3 if d in ni3]
    if pairs and sum(n for _, n in pairs) > 0:
        pr = sum(d for d, _ in pairs) / sum(n for _, n in pairs)
        checks.append(Check("health", "Dividend payout ratio", f"{pr * 100:.0f}% of earnings (3 yrs)", "≤40%",
                            lin(pr, *T["payout_ratio"])))
    else:
        checks.append(Check("health", "Dividend payout ratio", "—", "≤40%", None))
    nis = [v for _, v in yearly(annual, None, "net_income", ttm=False)][-10:]
    if len(nis) >= 5:
        p = sum(1 for v in nis if v > 0)
        checks.append(Check("health", "Profitable years", f"{p} of {len(nis)}", "every year",
                            lin(p / len(nis), *T["profitable_share"])))
    else:
        checks.append(Check("health", "Profitable years", "—", "every year", None))
    return checks


def _financial_flags(q_all, annual, snap):
    last = q_all.iloc[-1]
    flags = []
    ni = _num(last.get("net_income_ttm"))
    if ni is not None and ni < 0:
        flags.append("Net loss over the last 12 months")
    eq, ta = _num(last.get("equity")), _num(last.get("total_assets"))
    if eq is not None and ta and eq / ta < 0.05:
        flags.append(f"Equity only {eq / ta * 100:.1f}% of total assets")
    div = dict(yearly(annual, None, "dividends_paid", ttm=False))
    nis = yearly(annual, None, "net_income", ttm=False)[-3:]
    over = sum(1 for d, n in nis if d in div and div[d] > n)
    if len(nis) == 3 and over >= 2:
        flags.append("Dividends above earnings in 2 of the last 3 years")
    sh3 = _share_cagr(annual, 3)
    if sh3 is not None and sh3 > 0.04:
        flags.append(f"Share count growing {sh3 * 100:.1f}% a year")
    tb = [v for _, v in _tbvps_points(annual)][-4:]
    if len(tb) == 4 and tb[0] > tb[1] > tb[2] > tb[3]:
        flags.append("Tangible book value per share down 3 years straight")
    return flags, False
