"""
update_and_analyze.py — one command for the periodic refresh cycle
----------------------------------------------------------------------
1. Re-runs run_pipeline.py to refresh data (new quarterly filings, updated
   ratios, fresh charts) — skips anything unchanged/already done unless
   you pass --force
2. Re-runs filter_shortlist.py to regenerate today's shortlist
3. Runs analyze_stock.py against the shortlist to produce fresh reports

This is the script to schedule (see README for Windows Task Scheduler setup).

Usage:
    python update_and_analyze.py
    python update_and_analyze.py --force-data-refresh
"""

import argparse
import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # use whichever python is running this script


def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"  ! command exited with code {result.returncode} — continuing anyway")


def main():
    ap = argparse.ArgumentParser()
    args = ap.parse_args()

    # 1. Refresh data — call the scrapers directly (not run_pipeline.py) so
    # fundamentals/ratios/shareholding get re-fetched every period even for
    # symbols already marked "done" in progress.csv. PDF downloads are still
    # skipped automatically if the file already exists on disk.
    run([PY, "screener_scraper.py", "--symbols-file", "nifty500_symbols.txt"])
    run([PY, "chart_generator.py", "--symbols-file", "nifty500_symbols.txt"])

    # 2. Re-screen
    run([PY, "filter_shortlist.py"])

    # 3. Analyze the shortlist
    shortlist_path = os.path.join(BASE_DIR, "shortlist.txt")
    if os.path.exists(shortlist_path) and os.path.getsize(shortlist_path) > 0:
        run([PY, "analyze_stock.py", "--symbols-file", "shortlist.txt"])
    else:
        print("Shortlist is empty — no stocks passed the screen, skipping analysis step.")


if __name__ == "__main__":
    main()
