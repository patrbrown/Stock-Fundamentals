"""Which XBRL tags feed each metric, in priority order.

Companies don't all use the same tag for the same line item (and many switched tags
around 2018), so each metric lists fallbacks. The first tag with a value for a
given period wins. To fix a company whose numbers look wrong, add or reorder tags here.
"""

# Flow items: reported over a period (income statement, cash flow statement)
FLOW = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "RevenuesNetOfInterestExpense",
    ],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfServices",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": [
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
    ],
    "eps_diluted": [
        "EarningsPerShareDiluted",
        "EarningsPerShareBasicAndDiluted",
        "EarningsPerShareBasic",
    ],
    "diluted_shares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAmortizationAndOther",
        "Depreciation",
    ],
    "cash_from_operations": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    ],
}

# Instant items: a balance at a point in time (balance sheet, cover page)
INSTANT = {
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "Cash",
    ],
    "short_term_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "total_debt": ["LongTermDebt", "DebtLongtermAndShorttermCombinedAmount", "DebtInstrumentCarryingAmount"],
    "debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "debt_current": ["LongTermDebtCurrent", "DebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "short_term_borrowings": ["ShortTermBorrowings", "CommercialPaper"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
}

# Cover-page share count (dei namespace)
SHARES_OUTSTANDING = ["EntityCommonStockSharesOutstanding"]

# Display names, units and formatting for every metric the app shows
METRICS = {
    "revenue": ("Revenue", "money"),
    "gross_profit": ("Gross Profit", "money"),
    "operating_income": ("Operating Income", "money"),
    "net_income": ("Net Income", "money"),
    "eps_diluted": ("EPS (diluted)", "eps"),
    "ebitda": ("EBITDA", "money"),
    "cash_from_operations": ("Cash from Operations", "money"),
    "capex": ("Capital Expenditures", "money"),
    "free_cash_flow": ("Free Cash Flow", "money"),
    "depreciation_amortization": ("Depreciation & Amortization", "money"),
    "gross_margin": ("Gross Margin", "pct"),
    "operating_margin": ("Operating Margin", "pct"),
    "net_margin": ("Net Margin", "pct"),
    "fcf_margin": ("FCF Margin", "pct"),
    "revenue_yoy": ("Revenue Growth YoY", "pct"),
    "eps_yoy": ("EPS Growth YoY", "pct"),
    "diluted_shares": ("Diluted Shares", "shares"),
    "cash": ("Cash & Equivalents", "money"),
    "total_debt": ("Total Debt", "money"),
    "equity": ("Shareholders' Equity", "money"),
    "price": ("Share Price (quarter end)", "eps"),
    "pe_ttm": ("P/E Ratio (TTM, at quarter end)", "ratio"),
}
