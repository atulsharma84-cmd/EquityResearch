"""
Technical chart generator — 50 EMA, 200 EMA, RSI(14), Volume
--------------------------------------------------------------
Produces one PNG per stock, saved to charts/<SYMBOL>.png.
This replaces manually screenshotting TradingView: it's scriptable,
reproducible, and works for all 500 stocks in one run.

Requires:
    pip install yfinance pandas mplfinance ta

Usage:
    python chart_generator.py --symbols RELIANCE,TCS,INFY
    python chart_generator.py --symbols-file nifty500_symbols.txt
"""

import argparse
import os
import time
import pandas as pd
import yfinance as yf
import mplfinance as mpf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHART_DIR = os.path.join(BASE_DIR, "charts")
os.makedirs(CHART_DIR, exist_ok=True)


def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def make_chart(symbol):
    ticker = f"{symbol}.NS"
    df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
    if df.empty:
        print(f"  ! no data for {symbol}")
        return

    # Recent yfinance versions return MultiIndex columns (e.g. ('Open', 'RELIANCE.NS'))
    # even for a single ticker — flatten to plain 'Open', 'High', etc.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Force OHLCV to numeric in case of stray dtype issues, and drop any bad rows
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    if df.empty:
        print(f"  ! no usable data for {symbol} after cleaning")
        return

    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    df["RSI14"] = compute_rsi(df["Close"])

    add_plots = [
        mpf.make_addplot(df["EMA50"], color="orange", width=1.0),
        mpf.make_addplot(df["EMA200"], color="blue", width=1.0),
        mpf.make_addplot(df["RSI14"], panel=2, color="purple", ylabel="RSI(14)"),
        mpf.make_addplot([70] * len(df), panel=2, color="grey", linestyle="--", width=0.6),
        mpf.make_addplot([30] * len(df), panel=2, color="grey", linestyle="--", width=0.6),
    ]

    out_path = os.path.join(CHART_DIR, f"{symbol}.png")
    mpf.plot(
        df,
        type="candle",
        style="yahoo",
        addplot=add_plots,
        volume=True,
        panel_ratios=(6, 2, 2),
        title=f"{symbol} — Daily, 50/200 EMA, RSI(14)",
        savefig=dict(fname=out_path, dpi=150, bbox_inches="tight"),
    )
    print(f"  saved {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", help="comma-separated NSE symbols")
    ap.add_argument("--symbols-file", help="text file, one NSE symbol per line")
    args = ap.parse_args()

    symbols = []
    if args.symbols:
        symbols.extend([s.strip() for s in args.symbols.split(",") if s.strip()])
    if args.symbols_file:
        with open(args.symbols_file) as f:
            symbols.extend([line.strip() for line in f if line.strip()])

    if not symbols:
        print("Provide --symbols or --symbols-file.")
        return

    for symbol in symbols:
        print(f"== {symbol} ==")
        try:
            make_chart(symbol)
        except Exception as e:
            print(f"  ! error for {symbol}: {e}")
        time.sleep(1)


if __name__ == "__main__":
    main()