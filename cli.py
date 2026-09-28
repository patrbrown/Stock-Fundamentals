"""Command-line version: print a summary and save an Excel file.

    python cli.py DELL
    python cli.py NFLX --quarters 20 --out NFLX.xlsx
"""
from __future__ import annotations

import argparse

from core import formatting as fmt
from core.export import to_excel
from core.report import build_report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ticker")
    p.add_argument("--quarters", type=int, default=20)
    p.add_argument("--out")
    p.add_argument("--refresh", action="store_true")
    a = p.parse_args()

    r = build_report(a.ticker, n_quarters=a.quarters, refresh=a.refresh)
    q, s = r.quarterly, r.snapshot
    print(f"\n{r.name} ({r.ticker})  CIK {r.cik}  currency {r.currency}")
    print(f"{'Quarter':<10}{'End':>12}{'Revenue':>12}{'NetInc':>12}{'EPS':>9}{'EBITDA':>12}{'CFO':>12}{'FCF':>12}")
    for d, row in q.iterrows():
        print(f"{row['label']:<10}{d:%Y-%m-%d}".ljust(22) + "".join(
            f"{v:>12}" for v in (fmt.money(row['revenue'], r.currency), fmt.money(row['net_income'], r.currency))) +
            f"{fmt.eps(row['eps_diluted'], r.currency):>9}" + "".join(
            f"{fmt.money(row[k], r.currency):>12}" for k in ('ebitda', 'cash_from_operations', 'free_cash_flow')))
    print(f"\nPrice {fmt.eps(s['price'])}  MktCap {fmt.money(s['market_cap'])}  P/E {fmt.ratio(s['pe'])}  "
          f"Fwd P/E {fmt.ratio(s['forward_pe'])}  PEG {fmt.ratio(s['peg'])}  EY {fmt.pct(s['earnings_yield'])}")
    print(r.growth.map(fmt.pct).to_string())
    for n in r.notes:
        print("note:", n)
    out = a.out or f"{r.ticker}_fundamentals.xlsx"
    with open(out, "wb") as f:
        f.write(to_excel(r))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
