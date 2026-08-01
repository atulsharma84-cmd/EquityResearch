"""
run_pipeline.py — one-command Nifty 500 data pull
-----------------------------------------------------
Does everything in sequence:
  1. Downloads the official Nifty 500 constituent list (if not already present)
  2. Runs screener_scraper.py for fundamentals, shareholding, annual reports, concalls
  3. Runs chart_generator.py for technical charts
  4. Logs progress + errors to pipeline.log, and skips stocks already completed
     so you can safely stop and resume

Requires:
    pip install requests beautifulsoup4 pandas lxml yfinance mplfinance

Usage:
    python run_pipeline.py                     # full Nifty 500
    python run_pipeline.py --limit 20           # first 20 stocks, for a test run
    python run_pipeline.py --years 3 --quarters 3
    python run_pipeline.py --skip-charts        # skip chart_generator step
    python run_pipeline.py --skip-docs          # skip screener_scraper step
"""

import argparse
import logging
import os
import sys
import time
import requests
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NIFTY500_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
SYMBOLS_FILE = os.path.join(BASE_DIR, "nifty500_symbols.txt")
LOG_FILE = os.path.join(BASE_DIR, "pipeline.log")
PROGRESS_FILE = os.path.join(BASE_DIR, "progress.csv")  # tracks which symbols are done

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def fetch_nifty500_list():
    """Download the official symbol list if we don't already have it."""
    if os.path.exists(SYMBOLS_FILE):
        log.info(f"Using existing symbol list: {SYMBOLS_FILE}")
        return

    log.info("Fetching official Nifty 500 constituent list...")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(NIFTY500_URL, headers=headers, timeout=30)
        r.raise_for_status()
        tmp_path = os.path.join(BASE_DIR, "_nifty500_raw.csv")
        with open(tmp_path, "wb") as f:
            f.write(r.content)
        df = pd.read_csv(tmp_path)
        symbol_col = next((c for c in df.columns if "symbol" in c.lower()), None)
        if not symbol_col:
            raise ValueError(f"Couldn't find a Symbol column in {df.columns.tolist()}")
        symbols = df[symbol_col].dropna().astype(str).str.strip().tolist()
        with open(SYMBOLS_FILE, "w") as f:
            f.write("\n".join(symbols))
        log.info(f"Saved {len(symbols)} symbols -> {SYMBOLS_FILE}")
    except Exception as e:
        log.error(f"Auto-fetch of Nifty 500 list failed ({e}).")
        log.error(f"Download it manually from {NIFTY500_URL} and save the Symbol "
                   f"column as {SYMBOLS_FILE}, one symbol per line, then re-run.")
        sys.exit(1)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        return set(pd.read_csv(PROGRESS_FILE)["symbol"].astype(str))
    return set()


def mark_done(symbol):
    done = load_progress()
    done.add(symbol)
    pd.DataFrame({"symbol": sorted(done)}).to_csv(PROGRESS_FILE, index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only process first N symbols (for testing)")
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--quarters", type=int, default=3)
    ap.add_argument("--skip-charts", action="store_true")
    ap.add_argument("--skip-docs", action="store_true")
    args = ap.parse_args()

    fetch_nifty500_list()
    with open(SYMBOLS_FILE) as f:
        symbols = [line.strip() for line in f if line.strip()]
    if args.limit:
        symbols = symbols[: args.limit]

    done = load_progress()
    remaining = [s for s in symbols if s not in done]
    log.info(f"{len(symbols)} total symbols, {len(done)} already done, {len(remaining)} remaining")

    # Import here so fetch_nifty500_list() runs even if these modules aren't ready yet
    if not args.skip_docs:
        import screener_scraper
    if not args.skip_charts:
        import chart_generator

    fundamentals_rows = []
    for i, symbol in enumerate(remaining, 1):
        log.info(f"[{i}/{len(remaining)}] {symbol}")
        try:
            if not args.skip_docs:
                screener_scraper.process_symbol(symbol, args.years, args.quarters, fundamentals_rows)
            if not args.skip_charts:
                chart_generator.make_chart(symbol)
            mark_done(symbol)
        except Exception as e:
            log.error(f"  ! {symbol} failed: {e}")
        time.sleep(2)  # stay polite to screener.in / yfinance

    if fundamentals_rows:
        out_path = os.path.join(BASE_DIR, "fundamentals", "fundamentals_master.csv")
        new_df = pd.DataFrame(fundamentals_rows)
        if os.path.exists(out_path):
            old_df = pd.read_csv(out_path)
            new_df = pd.concat([old_df, new_df]).drop_duplicates(subset="symbol", keep="last")
        new_df.to_csv(out_path, index=False)
        log.info(f"Fundamentals master table updated -> {out_path}")

    log.info("Run complete. Re-run the same command any time to pick up where you left off "
              "(already-completed symbols are skipped via progress.csv).")


if __name__ == "__main__":
    main()
