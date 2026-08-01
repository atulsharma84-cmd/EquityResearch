"""
filter_shortlist.py — screen fundamentals_master.csv down to a shortlist
--------------------------------------------------------------------------
Filters stocks by threshold before you spend API calls analyzing them.
Adjust the thresholds below to your own criteria.

Usage:
    python filter_shortlist.py
    -> writes shortlist.txt (one symbol per line), ready for analyze_stock.py
"""

import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FUNDAMENTALS_PATH = os.path.join(BASE_DIR, "fundamentals", "fundamentals_master.csv")
SHORTLIST_PATH = os.path.join(BASE_DIR, "shortlist.txt")

# ---- Adjust these to your own criteria ----
MIN_ROE = 15
MAX_DEBT_TO_EQUITY = 0.5
MIN_REVENUE_GROWTH_3YR = 10
MIN_PROFIT_GROWTH_3YR = 10
MIN_PROMOTER_HOLDING = 40
MAX_PE = 60
# --------------------------------------------


def main():
    df = pd.read_csv(FUNDAMENTALS_PATH)

    filtered = df[
        (df["roe_pct"] >= MIN_ROE)
        & (df["debt_to_equity"].fillna(0) <= MAX_DEBT_TO_EQUITY)
        & (df["revenue_growth_3yr_pct"] >= MIN_REVENUE_GROWTH_3YR)
        & (df["profit_growth_3yr_pct"] >= MIN_PROFIT_GROWTH_3YR)
        & (df["promoter_holding_pct"] >= MIN_PROMOTER_HOLDING)
        & (df["pe_ratio"] <= MAX_PE)
    ]

    with open(SHORTLIST_PATH, "w") as f:
        f.write("\n".join(filtered["symbol"].tolist()))

    print(f"{len(filtered)} / {len(df)} stocks passed the screen -> {SHORTLIST_PATH}")
    print(filtered[["symbol", "roe_pct", "debt_to_equity", "revenue_growth_3yr_pct",
                     "profit_growth_3yr_pct", "promoter_holding_pct", "pe_ratio"]].to_string(index=False))


if __name__ == "__main__":
    main()
