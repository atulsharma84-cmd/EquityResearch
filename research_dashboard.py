"""
research_dashboard.py — Nifty 500 dashboard with analyzed-stocks summary
----------------------------------------------------------------------------
Everything app.py does, PLUS a summary view that parses each generated
report for its Verdict (Buy/Hold/Avoid), Conviction score, and target price,
so you can scan all analyzed stocks at a glance instead of opening each
report individually.

Kept as a separate file from app.py on purpose — run whichever dashboard
you prefer, or both (on different ports).

Requires:
    pip install flask pandas anthropic pypdf markdown

Run:
    py -3.14 research_dashboard.py
Then open http://127.0.0.1:5001  (note: different port from app.py, so you
can run both at once if you want)
"""

import os
import re
import pandas as pd
from flask import Flask, request, render_template_string, send_file

import analyze_stock  # reuses gather_stock_data / analyze_symbol / PROMPT_TEMPLATE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FUNDAMENTALS_PATH = os.path.join(BASE_DIR, "fundamentals", "fundamentals_master.csv")
ANALYSIS_DIR = os.path.join(BASE_DIR, "analysis")
CHARTS_DIR = os.path.join(BASE_DIR, "charts")
os.makedirs(ANALYSIS_DIR, exist_ok=True)

app = Flask(__name__)

BASE_HTML = """
<!doctype html>
<html>
<head>
<title>Nifty 500 Research Dashboard</title>
<style>
  body { font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 0; background: #f7f7f8; color: #1a1a1a; }
  header { background: #1a1a1a; color: white; padding: 16px 24px; }
  header a { color: white; text-decoration: none; margin-right: 20px; font-size: 14px; }
  header a:hover { text-decoration: underline; }
  .container { padding: 24px; max-width: 1150px; margin: 0 auto; }
  table { border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }
  th { background: #fafafa; }
  tr:hover { background: #f5f5f5; }
  .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
  input[type=number] { width: 80px; padding: 4px; }
  label { display: inline-block; margin-right: 16px; font-size: 14px; }
  button, .btn { background: #d97757; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; text-decoration: none; display: inline-block; }
  button:hover, .btn:hover { background: #c2663f; }
  .stat { display: inline-block; margin-right: 32px; }
  .stat .num { font-size: 28px; font-weight: bold; }
  .stat .label { font-size: 12px; color: #666; }
  .analyze-btn { background: #4a7c59; padding: 4px 10px; font-size: 12px; }
  img { max-width: 100%; border-radius: 6px; }
  pre { white-space: pre-wrap; }
  .badge { padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; color: white; }
  .badge-buy { background: #2e7d32; }
  .badge-hold { background: #b8860b; }
  .badge-avoid { background: #c62828; }
  .badge-unknown { background: #888; }
  .conviction { font-weight: 600; }
</style>
</head>
<body>
<header>
  <a href="/">Analyzed Stocks Summary</a>
  <a href="/screen">Screen All Stocks</a>
</header>
<div class="container">
{{ content|safe }}
</div>
</body>
</html>
"""


def render(content):
    return render_template_string(BASE_HTML, content=content)


def parse_verdict(text):
    """Best-effort extraction of Verdict / Conviction / Interesting-price
    from the free-form 'FINAL VERDICT' section of a generated report."""
    result = {"verdict": None, "conviction": None, "interesting_price": None, "summary_line": None}

    # Isolate the FINAL VERDICT section (from its heading to the next heading or end)
    m = re.search(r"FINAL VERDICT(.*?)(?:\n#{1,3}\s|\Z)", text, re.IGNORECASE | re.DOTALL)
    section = m.group(1) if m else text  # fall back to whole text if heading not found

    verdict_match = re.search(r"\b(Buy|Hold|Avoid)\b", section, re.IGNORECASE)
    if verdict_match:
        result["verdict"] = verdict_match.group(1).capitalize()

    conviction_match = re.search(r"(\d{1,2})\s*/\s*10", section)
    if conviction_match:
        result["conviction"] = conviction_match.group(1)

    price_match = re.search(r"(?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d+)?", section)
    if price_match:
        result["interesting_price"] = price_match.group(0)

    # Grab a short trailing sentence as the one-line summary, if identifiable
    lines = [l.strip() for l in section.strip().split("\n") if l.strip()]
    if lines:
        candidates = [l for l in lines if 20 < len(l) < 220 and not l.lower().startswith(("buy", "hold", "avoid", "conviction"))]
        if candidates:
            result["summary_line"] = candidates[-1]

    return result


def load_all_verdicts():
    rows = []
    if not os.path.exists(ANALYSIS_DIR):
        return rows
    for fname in sorted(os.listdir(ANALYSIS_DIR)):
        if not fname.endswith("_analysis.md"):
            continue
        symbol = fname[: -len("_analysis.md")]
        with open(os.path.join(ANALYSIS_DIR, fname), encoding="utf-8") as f:
            text = f.read()
        parsed = parse_verdict(text)
        parsed["symbol"] = symbol
        rows.append(parsed)
    return rows


@app.route("/")
def summary():
    verdicts = load_all_verdicts()

    sort_order = {"Buy": 0, "Hold": 1, "Avoid": 2, None: 3}
    verdicts.sort(key=lambda v: (sort_order.get(v["verdict"], 3), -(int(v["conviction"]) if v["conviction"] else 0)))

    rows = ""
    for v in verdicts:
        badge_class = {
            "Buy": "badge-buy", "Hold": "badge-hold", "Avoid": "badge-avoid"
        }.get(v["verdict"], "badge-unknown")
        badge_text = v["verdict"] or "Unparsed"
        rows += f"""<tr>
            <td><a href="/report/{v['symbol']}">{v['symbol']}</a></td>
            <td><span class="badge {badge_class}">{badge_text}</span></td>
            <td class="conviction">{v['conviction'] or '-'}/10</td>
            <td>{v['interesting_price'] or '-'}</td>
            <td style="font-size:13px;color:#555">{v['summary_line'] or ''}</td>
        </tr>"""

    if not verdicts:
        body = ("<p>No analyzed stocks yet. Go to <a href='/screen'>Screen All Stocks</a>, "
                "pick candidates, and click Analyze.</p>")
    else:
        body = f"""<table>
            <tr><th>Symbol</th><th>Verdict</th><th>Conviction</th><th>Interesting Price</th><th>Summary</th></tr>
            {rows}
        </table>"""

    content = f"""
    <div class="card">
      <div class="stat"><div class="num">{len(verdicts)}</div><div class="label">Stocks analyzed</div></div>
      <div class="stat"><div class="num">{sum(1 for v in verdicts if v['verdict']=='Buy')}</div><div class="label">Buy calls</div></div>
      <div class="stat"><div class="num">{sum(1 for v in verdicts if v['verdict']=='Avoid')}</div><div class="label">Avoid calls</div></div>
    </div>
    <div class="card"><h2>Analyzed Stocks — Verdict Summary</h2>{body}</div>
    """
    return render(content)


@app.route("/screen")
def screen():
    if not os.path.exists(FUNDAMENTALS_PATH):
        return render("<div class='card'><p>No fundamentals data found yet. Run "
                       "<code>py -3.14 run_pipeline.py</code> first.</p></div>")

    df = pd.read_csv(FUNDAMENTALS_PATH)

    min_roe = float(request.args.get("min_roe", 15))
    max_de = float(request.args.get("max_de", 0.5))
    min_rev_growth = float(request.args.get("min_rev_growth", 10))
    min_profit_growth = float(request.args.get("min_profit_growth", 10))
    min_promoter = float(request.args.get("min_promoter", 40))
    max_pe = float(request.args.get("max_pe", 60))

    filtered = df[
        (df["roe_pct"].fillna(-999) >= min_roe)
        & (df["debt_to_equity"].fillna(999) <= max_de)
        & (df["revenue_growth_3yr_pct"].fillna(-999) >= min_rev_growth)
        & (df["profit_growth_3yr_pct"].fillna(-999) >= min_profit_growth)
        & (df["promoter_holding_pct"].fillna(-999) >= min_promoter)
        & (df["pe_ratio"].fillna(999) <= max_pe)
    ].sort_values("roe_pct", ascending=False)

    existing_reports = {f[:-len("_analysis.md")] for f in os.listdir(ANALYSIS_DIR)} if os.path.exists(ANALYSIS_DIR) else set()

    rows = ""
    for _, r in filtered.iterrows():
        sym = r["symbol"]
        has_report = sym in existing_reports
        action = (f'<a class="btn" style="padding:4px 10px;font-size:12px" href="/report/{sym}">View report</a>'
                  if has_report else
                  f'<button class="analyze-btn" onclick="analyzeStock(\'{sym}\')">Analyze</button>')
        rows += f"""<tr id="row-{sym}">
            <td>{sym}</td>
            <td>{r.get('roe_pct', '')}</td>
            <td>{r.get('debt_to_equity', '')}</td>
            <td>{r.get('revenue_growth_3yr_pct', '')}</td>
            <td>{r.get('profit_growth_3yr_pct', '')}</td>
            <td>{r.get('promoter_holding_pct', '')}</td>
            <td>{r.get('pe_ratio', '')}</td>
            <td id="action-{sym}">{action}</td>
        </tr>"""

    content = f"""
    <div class="card">
      <form method="get">
        <label>Min ROE % <input type="number" step="0.1" name="min_roe" value="{min_roe}"></label>
        <label>Max D/E <input type="number" step="0.1" name="max_de" value="{max_de}"></label>
        <label>Min Revenue Growth % <input type="number" step="0.1" name="min_rev_growth" value="{min_rev_growth}"></label>
        <label>Min Profit Growth % <input type="number" step="0.1" name="min_profit_growth" value="{min_profit_growth}"></label>
        <label>Min Promoter Holding % <input type="number" step="0.1" name="min_promoter" value="{min_promoter}"></label>
        <label>Max P/E <input type="number" step="0.1" name="max_pe" value="{max_pe}"></label>
        <button type="submit">Apply filter</button>
      </form>
    </div>
    <div class="card">
      <p>{len(filtered)} / {len(df)} stocks pass this filter.</p>
      <table>
        <tr><th>Symbol</th><th>ROE %</th><th>D/E</th><th>Rev Growth %</th><th>Profit Growth %</th><th>Promoter %</th><th>P/E</th><th>Action</th></tr>
        {rows}
      </table>
    </div>
    <script>
    function analyzeStock(symbol) {{
        document.getElementById('action-' + symbol).innerHTML = 'Analyzing... (this can take 30-60s)';
        fetch('/analyze/' + symbol, {{ method: 'POST' }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    document.getElementById('action-' + symbol).innerHTML =
                        '<a class="btn" style="padding:4px 10px;font-size:12px" href="/report/' + symbol + '">View report</a>';
                }} else {{
                    document.getElementById('action-' + symbol).innerHTML = 'Failed: ' + data.error;
                }}
            }});
    }}
    </script>
    """
    return render(content)


@app.route("/analyze/<symbol>", methods=["POST"])
def analyze(symbol):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"success": False, "error": "ANTHROPIC_API_KEY not set"}, 400
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        analyze_stock.analyze_symbol(symbol, client)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


@app.route("/chart/<symbol>")
def chart(symbol):
    path = os.path.join(CHARTS_DIR, f"{symbol}.png")
    if os.path.exists(path):
        return send_file(path)
    return "Not found", 404


@app.route("/report/<symbol>")
def report(symbol):
    path = os.path.join(ANALYSIS_DIR, f"{symbol}_analysis.md")
    if not os.path.exists(path):
        return render(f"<div class='card'><p>No report for {symbol} yet.</p></div>")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        import markdown
        html = markdown.markdown(text)
    except ImportError:
        html = f"<pre>{text}</pre>"

    chart_path = f"/chart/{symbol}"
    chart_exists = os.path.exists(os.path.join(CHARTS_DIR, f"{symbol}.png"))
    chart_html = f'<img src="{chart_path}">' if chart_exists else ""

    content = f"<div class='card'>{chart_html}{html}</div>"
    return render(content)


if __name__ == "__main__":
    print("\nOpen http://127.0.0.1:5001 in your browser\n")
    app.run(debug=False, port=5001)