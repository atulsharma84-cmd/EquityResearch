"""
Nifty 500 Data Pipeline — screener.in scraper
------------------------------------------------
Pulls, per stock:
  - Fundamentals (P/E, ROE, ROCE, D/E, promoter holding, growth rates, OCF)
  - Latest quarter shareholding pattern
  - Annual report PDF links (downloads last N years)
  - Concall transcript PDF links (downloads last N quarters)

Run this on your own machine (needs internet access). Requires:
    pip install requests beautifulsoup4 pandas lxml

Usage:
    python screener_scraper.py --symbols RELIANCE,TCS,INFY --years 3 --quarters 3
    python screener_scraper.py --symbols-file nifty500_symbols.txt --years 3 --quarters 3

nifty500_symbols.txt = one NSE symbol per line. Get the official list from:
  https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv
"""

import argparse
import os
import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIRS = {
    "annual_reports": os.path.join(BASE_DIR, "annual_reports"),
    "concalls": os.path.join(BASE_DIR, "concall_transcripts"),
    "fundamentals": os.path.join(BASE_DIR, "fundamentals"),
    "shareholding": os.path.join(BASE_DIR, "shareholding"),
}
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)


def get_soup(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def safe_float(text):
    if text is None:
        return None
    text = text.replace(",", "").replace("%", "").replace("₹", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def scrape_ratios(soup):
    """Top summary ratio block: Market Cap, P/E, ROCE, ROE, Book Value, Promoter Holding, etc."""
    out = {}
    for li in soup.select("#top-ratios li"):
        name = li.select_one(".name")
        value = li.select_one(".value")
        if name and value:
            key = name.get_text(strip=True).lower()
            key = key.replace(" ", "_").replace(".", "").replace("/", "").replace("+", "")
            out[key] = value.get_text(strip=True)
    return out


def scrape_shareholding(soup):
    """Latest quarter shareholding pattern from the #shareholding table."""
    table = soup.select_one("#shareholding table")
    if not table:
        return {}
    headers = [th.get_text(strip=True) for th in table.select("thead th")][1:]
    latest_col = headers[-1] if headers else None
    rows = {}
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        label = cells[0].get_text(strip=True).replace("+", "").strip()
        if len(cells) > 1:
            rows[label] = cells[-1].get_text(strip=True)  # last column = latest quarter
    rows["as_of_quarter"] = latest_col
    return rows


def scrape_annual_reports(soup, years=3):
    links = []
    section = soup.find(id="documents") or soup
    for a in section.find_all("a", href=True):
        text = a.get_text(strip=True)
        if re.search(r"Financial Year \d{4}", text):
            links.append((text, a["href"]))
    return links[:years]


def scrape_growth_and_cashflow(soup):
    """Compounded sales/profit growth (3yr), latest-year OCF, and Debt/Equity."""
    out = {}

    for header_text, key in [
        ("Compounded Sales Growth", "revenue_growth_3yr_pct"),
        ("Compounded Profit Growth", "profit_growth_3yr_pct"),
    ]:
        header = soup.find(string=re.compile(header_text))
        if header:
            table = header.find_parent().find_next("table")
            if table:
                for tr in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if len(cells) == 2 and "3 Years" in cells[0]:
                        out[key] = safe_float(cells[1])

    cf_section = soup.find(id="cash-flow")
    if cf_section:
        table = cf_section.find_next("table")
        if table:
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if cells and "Cash from Operating Activity" in cells[0].get_text():
                    values = [safe_float(td.get_text(strip=True)) for td in cells[1:]]
                    values = [v for v in values if v is not None]
                    if values:
                        out["latest_year_ocf_cr"] = values[-1]

    bs_section = soup.find(id="balance-sheet")
    if bs_section:
        table = bs_section.find_next("table")
        if table:
            borrowings, equity_cap, reserves = None, None, None
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if not cells:
                    continue
                label = cells[0].get_text(strip=True)
                values = [safe_float(td.get_text(strip=True)) for td in cells[1:]]
                values = [v for v in values if v is not None]
                if not values:
                    continue
                if "Borrowings" in label:
                    borrowings = values[-1]
                elif label == "Equity Capital":
                    equity_cap = values[-1]
                elif label == "Reserves":
                    reserves = values[-1]
            if borrowings is not None and equity_cap is not None and reserves is not None:
                total_equity = equity_cap + reserves
                if total_equity:
                    out["debt_to_equity"] = round(borrowings / total_equity, 2)

    return out


def scrape_concalls(soup, quarters=3):
    """Concall transcript PDF links, most recent first."""
    links = []
    for a in soup.find_all("a", href=True, title="Raw Transcript"):
        links.append((a.get_text(strip=True) or "Transcript", a["href"]))
    return links[:quarters]


def download_file(url, dest_path):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"  ! failed to download {url}: {e}")
        return False


def process_symbol(symbol, years, quarters, fundamentals_rows):
    print(f"\n== {symbol} ==")
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    try:
        soup = get_soup(url)
    except Exception as e:
        # fall back to standalone page if consolidated doesn't exist
        try:
            url = f"https://www.screener.in/company/{symbol}/"
            soup = get_soup(url)
        except Exception as e2:
            print(f"  ! could not fetch {symbol}: {e2}")
            return

    ratios = scrape_ratios(soup)
    shareholding = scrape_shareholding(soup)
    growth_cf = scrape_growth_and_cashflow(soup)

    row = {
        "symbol": symbol,
        "market_cap_cr": safe_float(ratios.get("market_cap")),
        "current_price": safe_float(ratios.get("current_price")),
        "pe_ratio": safe_float(ratios.get("stock_pe")),
        "book_value": safe_float(ratios.get("book_value")),
        "roce_pct": safe_float(ratios.get("roce")),
        "roe_pct": safe_float(ratios.get("roe")),
        "dividend_yield_pct": safe_float(ratios.get("dividend_yield")),
        "promoter_holding_pct": safe_float(shareholding.get("Promoters")),
        "revenue_growth_3yr_pct": growth_cf.get("revenue_growth_3yr_pct"),
        "profit_growth_3yr_pct": growth_cf.get("profit_growth_3yr_pct"),
        "latest_year_ocf_cr": growth_cf.get("latest_year_ocf_cr"),
        "debt_to_equity": growth_cf.get("debt_to_equity"),
        "as_of_quarter": shareholding.get("as_of_quarter"),
    }
    fundamentals_rows.append(row)

    # shareholding snapshot per stock
    pd.DataFrame([shareholding]).to_csv(
        os.path.join(DIRS["shareholding"], f"{symbol}_shareholding.csv"), index=False
    )

    # annual reports
    ar_dir = os.path.join(DIRS["annual_reports"], symbol)
    os.makedirs(ar_dir, exist_ok=True)
    for label, link in scrape_annual_reports(soup, years=years):
        fname = re.sub(r"[^\w\-]", "_", label) + ".pdf"
        dest = os.path.join(ar_dir, fname)
        if not os.path.exists(dest):
            print(f"  downloading annual report: {label}")
            download_file(link, dest)
            time.sleep(1)  # be polite

    # concall transcripts
    cc_dir = os.path.join(DIRS["concalls"], symbol)
    os.makedirs(cc_dir, exist_ok=True)
    for i, (label, link) in enumerate(scrape_concalls(soup, quarters=quarters)):
        fname = f"{i+1}_{re.sub(r'[^\\w\\-]', '_', label)}.pdf"
        dest = os.path.join(cc_dir, fname)
        if not os.path.exists(dest):
            print(f"  downloading concall transcript: {label}")
            download_file(link, dest)
            time.sleep(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", help="comma-separated NSE symbols, e.g. RELIANCE,TCS,INFY")
    ap.add_argument("--symbols-file", help="text file, one NSE symbol per line")
    ap.add_argument("--years", type=int, default=3, help="years of annual reports to fetch")
    ap.add_argument("--quarters", type=int, default=3, help="quarters of concall transcripts to fetch")
    args = ap.parse_args()

    symbols = []
    if args.symbols:
        symbols.extend([s.strip() for s in args.symbols.split(",") if s.strip()])
    if args.symbols_file:
        with open(args.symbols_file) as f:
            symbols.extend([line.strip() for line in f if line.strip()])

    if not symbols:
        print("Provide --symbols or --symbols-file. See --help.")
        return

    fundamentals_rows = []
    for symbol in symbols:
        process_symbol(symbol, args.years, args.quarters, fundamentals_rows)
        time.sleep(2)  # be polite to screener.in — don't hammer the server

    if fundamentals_rows:
        out_path = os.path.join(DIRS["fundamentals"], "fundamentals_master.csv")
        new_df = pd.DataFrame(fundamentals_rows)
        if os.path.exists(out_path):
            old_df = pd.read_csv(out_path)
            new_df = pd.concat([old_df, new_df]).drop_duplicates(subset="symbol", keep="last")
        new_df.to_csv(out_path, index=False)
        print(f"Saved master fundamentals table ({len(new_df)} rows) -> {out_path}")


if __name__ == "__main__":
    main()


