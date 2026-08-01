# Nifty 500 Swing Trading Data Pipeline

## Why this approach instead of manual downloading

Manually downloading 500 stocks × (2-3 annual reports + 2-3 transcripts + 10
chart screenshots + fundamentals + shareholding) is thousands of files — not
practical by hand, and not something that can be done screenshot-by-screenshot
either. This pipeline gets the same data programmatically:

- **Annual reports, MDA, concall transcripts** → screener.in company pages
  link directly to the BSE-hosted PDFs. `screener_scraper.py` scrapes and
  downloads these per stock.
- **Fundamentals (P/E, ROE, D/E, growth, OCF, promoter holding)** → same
  scraper, pulled from screener.in's ratio/financial tables into one master
  CSV — far more reliable than reading numbers off a screenshot.
- **Shareholding pattern** → latest quarter table on screener.in, saved per
  stock as CSV.
- **Technical charts (50/200 EMA, RSI, volume)** → `chart_generator.py`
  pulls price data via yfinance and draws the chart itself — no TradingView
  screenshotting, and it's exactly reproducible for all 500 names.

## Setup (run on your own machine — needs internet access)

```bash
pip install requests beautifulsoup4 pandas lxml yfinance mplfinance
```

Get the official Nifty 500 list:
https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv
Save the "Symbol" column as `nifty500_symbols.txt`, one symbol per line.

## Run — one command, does everything

```bash
pip install requests beautifulsoup4 pandas lxml yfinance mplfinance

# test on the first 10 stocks first
python run_pipeline.py --limit 10

# full Nifty 500 run
python run_pipeline.py
```

`run_pipeline.py` auto-downloads the official Nifty 500 list, then runs
fundamentals + shareholding + annual reports + concalls + charts for every
symbol, in one pass. It logs everything to `pipeline.log` and tracks
completed symbols in `progress.csv` — if it gets interrupted (network drop,
you close the terminal, whatever), just re-run the exact same command and it
picks up where it left off instead of starting over.

Flags:
- `--limit N` — only process the first N symbols (good for a test run)
- `--years N` / `--quarters N` — how many years of annual reports / quarters
  of concalls to pull (default 3 / 3)
- `--skip-charts` — skip technical chart generation
- `--skip-docs` — skip fundamentals/reports/transcripts, charts only

## Run — individual scripts (if you want more control)


```bash
# Fundamentals + shareholding + annual reports + concall transcripts
python screener_scraper.py --symbols-file nifty500_symbols.txt --years 3 --quarters 3

# Technical charts
python chart_generator.py --symbols-file nifty500_symbols.txt
```

For a quick test first, run both against a handful of symbols:
```bash
python screener_scraper.py --symbols RELIANCE,TCS,INFY
python chart_generator.py --symbols RELIANCE,TCS,INFY
```

## Output layout

```
nifty500_pipeline/
├── fundamentals/
│   └── fundamentals_master.csv      # one row per stock: P/E, ROE, D/E, growth, OCF, promoter holding
├── shareholding/
│   └── <SYMBOL>_shareholding.csv    # latest quarter breakdown (promoters/FII/DII/public)
├── annual_reports/
│   └── <SYMBOL>/
│       └── Financial_Year_2026.pdf  # MDA is inside this same PDF
├── concall_transcripts/
│   └── <SYMBOL>/
│       └── 1_Transcript.pdf
└── charts/
    └── <SYMBOL>.png                 # candlestick + 50/200 EMA + RSI(14) + volume
```

## Notes / things to adjust before a full 500-stock run

- **Be polite to screener.in** — the scraper already sleeps between requests.
  Don't remove those delays; hammering the site risks getting your IP blocked.
  A full 500-stock run will take a while (budget a few hours).
- **screener.in free tier** has some rate limits; if you hit issues, consider
  their premium plan or spacing the run across sessions.
- Some smaller-cap Nifty 500 names may not have a `consolidated` page — the
  scraper falls back to the standalone page automatically.
- `chart_generator.py` uses `.NS` suffix (NSE). A few Nifty 500 stocks may
  trade primarily on BSE only — swap to `.BO` for those if a symbol returns
  no data.
- Once you have `fundamentals_master.csv`, that's your screener for shortlisting
  candidates before pulling the deeper documents (reports/transcripts/charts)
  only for stocks that pass your filters — much faster than doing everything
  for all 500 upfront.
