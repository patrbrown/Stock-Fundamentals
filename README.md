# Stock Fundamentals

Pick a company (type a name like "Netflix" or a ticker like "NFLX") and get the last 20 quarters of
SEC-reported financials: revenue, gross profit, operating income, net income, EPS, EBITDA, cash from
operations, capex, free cash flow, margins and CAGR, plus a valuation panel, segment breakdowns and a
competitor comparison. Accounts are invite-only, and every equity requested is logged for the admin.

No API keys. Fundamentals come from the SEC's free EDGAR APIs, prices and analyst targets from Yahoo Finance.

## Run it on your computer (Windows)

1. Double-click **setup.bat** once (needs Python 3.10+ from python.org, "Add python.exe to PATH" ticked).
2. Double-click **run.bat**. It installs anything new after an update, then opens the app in your browser.
3. The first time, expand **Owner setup** and enter the setup code shown in the black console window
   (also saved in `data/admin_setup_code.txt`) to create your **admin** account. Only you can see it.
4. Admin → Settings: enter the name and email the SEC requires on every request (sent only to sec.gov).

Close the black console window to stop the app.

To put it online for friends, see **DEPLOY.md**.

## What's on the page

- **Charts:** 20 quarters per metric, labelled with fiscal quarter and calendar month. Hover a bar to
  see what makes it up: revenue by segment / product / region (from the filings' segment tables),
  operating income by segment, and the line items behind gross profit, net income, EPS, EBITDA,
  cash from operations and free cash flow.
- **Valuation & ratios:** P/E, forward P/E, PEG, earnings yield, EV/EBITDA, P/S, P/FCF, margins, ROE,
  ROIC, net debt, debt/equity, growth and CAGR, trailing 12-month return and the analyst-target
  expected 12-month return.
- **Competitor analysis** (bottom of the page): pre-filled with the leading companies in the same
  industry; add or remove any SEC filer. Shows ranks, a side-by-side table and comparison charts.
- **Admin:** usage (most-requested equities and competitors, requests per day, per-user activity,
  CSV export), users, invites, settings.

## How the numbers are built

| Metric | Source |
|---|---|
| Revenue, net income, EPS, operating income, cash from operations, capex | Reported in 10-Q / 10-K |
| Gross profit | Reported, or revenue − cost of revenue |
| EBITDA | Operating income + depreciation & amortization |
| Free cash flow | Cash from operations − capital expenditures |
| Fiscal Q4 | 10-K annual figure − 9-month year-to-date (hatched bars / †) |
| Segment splits | Each filing's XBRL segment facts (business segment, product/service, region) |
| TTM | Sum of the last four quarters |
| PEG | P/E ÷ TTM EPS growth year over year (%) |
| Expected 12-month return | Analyst mean price target ÷ price − 1 (Yahoo) |

Per-share numbers filed before a stock split are adjusted to today's share basis.

## Limits

- **US-listed companies** use SEC filings (20+ quarters), including foreign companies that report
  in US GAAP (e.g. ARM, filing 6-K/20-F).
- **Canadian listings (TSX/TSXV)** and cross-listed companies that report under IFRS (e.g. the big
  banks) use Yahoo Finance statements instead: about 5 quarters and 4 fiscal years. Pick
  "Canada: TSX / TSXV" in the sidebar and search by name, or type a symbol like SU.TO.
- **Currency:** every page shows the currency of the financials. Prices are matched to it (a
  CAD-reporting company looked up by its US ticker uses its .TO listing; otherwise the price is
  converted at Yahoo's FX rate). The competitor table converts money figures into the currency of
  the company you're viewing.
- Banks and insurers use different line items, so gross profit, EBITDA and FCF can be blank.
- Segment splits appear only for quarters whose filings tag them. The first load for a company reads
  ~20 filings (about 30 seconds); after that it's cached.

## Command line

```
.venv\Scripts\python.exe cli.py netflix
.venv\Scripts\python.exe cli.py DELL --quarters 20 --out DELL.xlsx
```

## Project layout

```
app.py                Entry point: sign-in gate and page navigation
ui/analyze.py         Main page: charts, ratios, tables, competitor section
ui/charts.py          Plotly chart builders
ui/breakdowns.py      Hover text for each chart
ui/auth_ui.py         Sign-in / sign-up / account screens, remember-me cookie
ui/admin.py           Usage analytics, users, invites, settings
core/report.py        build_report(ticker) -> CompanyReport (everything for one company)
core/fundamentals.py  Quarterly/annual extraction, Q4 derivation, split adjustment
core/segments.py      Segment / product / region splits from filing XBRL
core/peers.py         Competitor suggestions and comparison
core/metrics.py       CAGR table and valuation snapshot
core/market.py        Yahoo Finance: price, history, splits, forward P/E, analyst target, industry peers
core/sec_client.py    SEC API calls + disk cache, company search
core/db.py            Users, invites, sessions, request log (SQLite locally, Postgres when deployed)
core/auth.py          Password hashing, invites, sessions
core/export.py        Excel export
```
