"""
analyze_stock.py — automated equity research teardown
-----------------------------------------------------
Reads a stock's local data (fundamentals row, annual report PDF, concall
transcripts, shareholding pattern) and sends it to Claude via the Anthropic
API using the "seasoned equity research analyst" framework, then saves the
report as markdown.

Requires:
    pip install anthropic pypdf pandas

Set your API key first (get one at https://console.anthropic.com):
    setx ANTHROPIC_API_KEY "your-key-here"
    (close and reopen terminal after setx, then it's permanent)

Usage:
    python analyze_stock.py --symbol RELIANCE
    python analyze_stock.py --symbols-file shortlist.txt
"""

import argparse
import os
import glob
import time
import pandas as pd
from pypdf import PdfReader
import anthropic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYSIS_DIR = os.path.join(BASE_DIR, "analysis")
os.makedirs(ANALYSIS_DIR, exist_ok=True)

# Cap extracted text per document type to stay within a reasonable prompt size
# and keep API cost predictable. Adjust if you want deeper coverage.
MAX_CHARS_ANNUAL_REPORT = 120_000
MAX_CHARS_PER_TRANSCRIPT = 30_000

MODEL = "claude-sonnet-4-6"  # update if you want a different model

PROMPT_TEMPLATE = """Act as a seasoned equity research analyst with 20 years of experience across fundamental analysis, technical analysis, and behavioral finance. I am providing you with the following documents for {company_name}: annual financial statements, Management Discussion & Analysis, concall transcripts, key ratios from Screener, and the latest shareholding pattern.

Tear this company apart across these dimensions:

FUNDAMENTALS
Is this business genuinely healthy or just looks good on surface? Dig into revenue quality, margin trajectory, cash flow vs reported profits, debt structure, and ROE sustainability. Flag any accounting red flags.

MANAGEMENT DNA
Read between the lines of the concall transcripts and MDA. Is management confident or defensive? Are they overpromising and underdelivering? Any change in language tone vs last year? Promoter pledge or stake reduction is an automatic red flag — call it out.

VALUATION REALITY
Is the market pricing in perfection? Compare current P/E against historical context and what the ratios imply. Tell me if I am paying a premium for growth that may never come.

TECHNICAL STRUCTURE
Note: no live chart image is provided in this automated run — comment on trend structure only if inferable from the data given, otherwise state that technical read requires the chart separately.

RISK FACTORS
What are the 3 things that could destroy this thesis? Sector risk, company-specific risk, macro risk.

FINAL VERDICT
Buy, Hold, or Avoid. Conviction score out of 10. Price at which this becomes interesting if not now. One line that summarizes this stock.

Do not give me a balanced, diplomatic answer. I want the truth — even if it is uncomfortable.

=== FUNDAMENTALS (from Screener) ===
{fundamentals}

=== SHAREHOLDING PATTERN (latest quarter) ===
{shareholding}

=== ANNUAL REPORT / MDA EXTRACT ===
{annual_report_text}

=== CONCALL TRANSCRIPT EXTRACTS ===
{transcript_text}
"""


def extract_pdf_text(path, max_chars):
    try:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
            if len(text) >= max_chars:
                break
        return text[:max_chars]
    except Exception as e:
        return f"[Could not extract text from {os.path.basename(path)}: {e}]"


def gather_stock_data(symbol):
    data = {"company_name": symbol}

    # Fundamentals row
    fpath = os.path.join(BASE_DIR, "fundamentals", "fundamentals_master.csv")
    if os.path.exists(fpath):
        df = pd.read_csv(fpath)
        row = df[df["symbol"] == symbol]
        data["fundamentals"] = row.to_string(index=False) if not row.empty else "Not found"
    else:
        data["fundamentals"] = "Not found"

    # Shareholding
    spath = os.path.join(BASE_DIR, "shareholding", f"{symbol}_shareholding.csv")
    if os.path.exists(spath):
        data["shareholding"] = pd.read_csv(spath).to_string(index=False)
    else:
        data["shareholding"] = "Not found"

    # Most recent annual report PDF
    ar_dir = os.path.join(BASE_DIR, "annual_reports", symbol)
    ar_text = ""
    if os.path.isdir(ar_dir):
        pdfs = sorted(glob.glob(os.path.join(ar_dir, "*.pdf")), reverse=True)
        if pdfs:
            ar_text = extract_pdf_text(pdfs[0], MAX_CHARS_ANNUAL_REPORT)
    data["annual_report_text"] = ar_text or "No annual report found locally."

    # Concall transcripts (all available, most recent first, capped per doc)
    cc_dir = os.path.join(BASE_DIR, "concall_transcripts", symbol)
    transcript_chunks = []
    if os.path.isdir(cc_dir):
        pdfs = sorted(glob.glob(os.path.join(cc_dir, "*.pdf")))
        for p in pdfs:
            txt = extract_pdf_text(p, MAX_CHARS_PER_TRANSCRIPT)
            transcript_chunks.append(f"--- {os.path.basename(p)} ---\n{txt}")
    data["transcript_text"] = "\n\n".join(transcript_chunks) or "No transcripts found locally."

    return data


def analyze_symbol(symbol, client):
    print(f"== {symbol} ==")
    data = gather_stock_data(symbol)
    prompt = PROMPT_TEMPLATE.format(**data)

    message = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    report_text = "".join(block.text for block in message.content if block.type == "text")

    out_path = os.path.join(ANALYSIS_DIR, f"{symbol}_analysis.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Equity Research Teardown — {symbol}\n")
        f.write(f"_Generated {time.strftime('%Y-%m-%d %H:%M')}_\n\n")
        f.write(report_text)

    print(f"  saved -> {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", help="single NSE symbol")
    ap.add_argument("--symbols", help="comma-separated NSE symbols")
    ap.add_argument("--symbols-file", help="text file, one symbol per line — e.g. a shortlist")
    args = ap.parse_args()

    symbols = []
    if args.symbol:
        symbols.append(args.symbol)
    if args.symbols:
        symbols.extend([s.strip() for s in args.symbols.split(",") if s.strip()])
    if args.symbols_file:
        with open(args.symbols_file) as f:
            symbols.extend([line.strip() for line in f if line.strip()])

    if not symbols:
        print("Provide --symbol, --symbols, or --symbols-file.")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY environment variable not set.")
        print('Set it with: setx ANTHROPIC_API_KEY "your-key-here"  (then reopen terminal)')
        return

    client = anthropic.Anthropic(api_key=api_key)

    for symbol in symbols:
        try:
            analyze_symbol(symbol, client)
        except Exception as e:
            print(f"  ! {symbol} failed: {e}")
        time.sleep(1)


if __name__ == "__main__":
    main()
