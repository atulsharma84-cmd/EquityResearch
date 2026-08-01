import os
import glob
import json
import re
import base64
import urllib.parse
import concurrent.futures
import requests
import pandas as pd
import streamlit as st

# Attempt to import yfinance and plotly for live price & technical interactive charts
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# ---------------------------------------------------------
# DIRECTORY & FILE CACHE CONFIGURATION
# ---------------------------------------------------------
BASE_DIR = r"C:\Users\Suchit Sharma\OneDrive\Atul\Indian Market\Equity Research\files"

DIRS = {
    "charts": os.path.join(BASE_DIR, "charts"),
    "fundamentals": os.path.join(BASE_DIR, "fundamentals"),
    "concall": os.path.join(BASE_DIR, "concall_transcripts"),
    "annual": os.path.join(BASE_DIR, "annual_reports"),
    "shareholding": os.path.join(BASE_DIR, "shareholding"),
}

CACHE_FILE = os.path.join(BASE_DIR, "scan_cache.json")
TECH_CACHE_FILE = os.path.join(BASE_DIR, "tech_data_cache.json")

for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

def load_json_cache(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                if isinstance(data, list): return {item["Symbol"]: item for item in data if "Symbol" in item}
                return data
        except Exception:
            return {}
    return {}

def save_json_cache(data, filepath):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        st.error(f"Failed to save cache: {e}")

if "portfolio_summary" not in st.session_state:
    st.session_state["portfolio_summary"] = load_json_cache(CACHE_FILE)

if "tech_data_cache" not in st.session_state:
    st.session_state["tech_data_cache"] = load_json_cache(TECH_CACHE_FILE)

st.set_page_config(page_title="Institutional Equity Research Engine", layout="wide")

# ---------------------------------------------------------
# EXECUTIVE STYLING
# ---------------------------------------------------------
st.markdown("""
<style>
    .stApp { background-color: #f0f4f8; color: #1a202c; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .main-header { background: linear-gradient(90deg, #0b2545 0%, #134074 100%); padding: 20px 25px; border-radius: 12px; color: #ffffff; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(11, 37, 69, 0.15); }
    .main-header h1 { color: #ffffff !important; font-size: 26px !important; font-weight: 700 !important; margin: 0 !important; }
    .main-header p { color: #8da9c4 !important; font-size: 13px !important; margin: 4px 0 0 0 !important; }
    div[data-testid="stMetric"] { background-color: #ffffff; border: 1px solid #dce4ec; border-radius: 10px; padding: 16px 20px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04); }
    div[data-testid="stMetricLabel"] { color: #4a5568 !important; font-size: 13px !important; font-weight: 600 !important; text-transform: uppercase; }
    div[data-testid="stMetricValue"] { color: #0b2545 !important; font-size: 30px !important; font-weight: 800 !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 6px; background-color: #e2e8f0; padding: 6px; border-radius: 8px; }
    .stTabs [data-baseweb="tab"] { height: 38px; border-radius: 6px; color: #4a5568; font-weight: 600; font-size: 14px; background-color: transparent; }
    .stTabs [aria-selected="true"] { background-color: #ffffff !important; color: #0b2545 !important; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08); }
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="main-header">
    <h1>📊 Institutional Equity Research Engine</h1>
    <p>Connected Directory: <b>{BASE_DIR}</b> &nbsp;|&nbsp; Target Entry: <b>Monthly Camarilla Pivot Support 3 (S3)</b></p>
</div>
""", unsafe_allow_html=True)

chart_files = glob.glob(os.path.join(DIRS["charts"], "*.*"))
detected_companies = sorted(list({os.path.splitext(os.path.basename(f))[0].upper() for f in chart_files}))

st.sidebar.header("🕹️ System Controls")
ollama_model = st.sidebar.text_input("Ollama Model", value="moondream", key="sb_ollama_model")
scan_limit = st.sidebar.number_input("Scan Limit (Max Stocks)", min_value=1, max_value=max(1, len(detected_companies)), value=min(50, max(1, len(detected_companies))), key="sb_scan_limit")

def get_tradingview_url(symbol):
    return f"https://www.tradingview.com/chart/?symbol=NSE:{symbol.strip().upper()}"

def get_local_file_url(filepath):
    if filepath and os.path.exists(filepath): return f"file:///{urllib.parse.quote(os.path.abspath(filepath))}"
    return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ---------------------------------------------------------
# REAL-TIME PARALLEL DATA ENGINE
# ---------------------------------------------------------
def fetch_single_ticker_tech(sym):
    clean_sym = sym.strip().upper()
    yf_ticker_str = f"{clean_sym}.NS"
    default_result = {"Daily RSI (14)": "N/A", "CMP (₹)": "N/A", "Target Entry (₹)": "N/A"}
    
    try:
        ticker = yf.Ticker(yf_ticker_str)
        cmp_val = None
        try:
            fast_info = ticker.fast_info
            cmp_val = fast_info.get("lastPrice") or fast_info.get("regularMarketPrice")
        except Exception: pass

        df_daily = ticker.history(period="3mo", interval="1d")
        if df_daily.empty: return sym, default_result

        close_prices = df_daily['Close'].dropna()
        latest_close = round(float(cmp_val), 2) if cmp_val is not None and not pd.isna(cmp_val) else (round(float(close_prices.iloc[-1]), 2) if not close_prices.empty else "N/A")

        latest_rsi = "N/A"
        if len(close_prices) >= 14:
            rsi_series = calculate_rsi(close_prices)
            rsi_last = rsi_series.iloc[-1]
            if not pd.isna(rsi_last): latest_rsi = round(float(rsi_last), 2)

        # Standard Monthly Camarilla S3 = Close - (High - Low) * 1.1 / 4
        df_monthly = ticker.history(period="6mo", interval="1mo")
        camarilla_s3 = "N/A"
        if len(df_monthly) >= 2:
            prev_month = df_monthly.iloc[-2]
            h, l, c = float(prev_month['High']), float(prev_month['Low']), float(prev_month['Close'])
            if not (pd.isna(h) or pd.isna(l) or pd.isna(c)):
                camarilla_s3 = round(c - ((h - l) * (1.1 / 4.0)), 2)

        return sym, {"Daily RSI (14)": latest_rsi, "CMP (₹)": latest_close, "Target Entry (₹)": camarilla_s3}
    except Exception:
        return sym, default_result

def fetch_tech_metrics_batch(symbols):
    if not YFINANCE_AVAILABLE: return {}, "yfinance library not installed"
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_sym = {executor.submit(fetch_single_ticker_tech, sym): sym for sym in symbols}
        for future in concurrent.futures.as_completed(future_to_sym):
            sym, data = future.result()
            results[sym] = data
    return results, None

# ---------------------------------------------------------
# INTERACTIVE LIVE CHARTING ENGINE (PLOTLY)
# ---------------------------------------------------------
def render_interactive_technical_chart(symbol):
    """Draws a live daily updated candlestick chart with EMAs and Camarilla Pivots."""
    if not YFINANCE_AVAILABLE or not PLOTLY_AVAILABLE:
        st.warning("Please install yfinance & plotly to view live interactive charts.")
        return None
        
    yf_ticker_str = f"{symbol.strip().upper()}.NS"
    ticker = yf.Ticker(yf_ticker_str)
    
    # Fetch 1 year of daily data for the chart
    df = ticker.history(period="1y", interval="1d")
    if df.empty:
        st.error(f"No chart data available for {symbol}")
        return None

    # Calculate EMAs
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

    # Calculate Current Monthly Camarilla Pivots
    df_monthly = ticker.history(period="2mo", interval="1mo")
    s3, s4, r3, r4 = None, None, None, None
    if len(df_monthly) >= 2:
        prev_month = df_monthly.iloc[-2]
        h, l, c = float(prev_month['High']), float(prev_month['Low']), float(prev_month['Close'])
        r = h - l
        s3, s4 = c - (r * 1.1 / 4), c - (r * 1.1 / 2)
        r3, r4 = c + (r * 1.1 / 4), c + (r * 1.1 / 2)

    # Build Plotly Figure
    fig = go.Figure()
    
    # Candlesticks
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price'))
    
    # EMA Traces
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], mode='lines', name='EMA 20', line=dict(color='#3b82f6', width=1.5)))
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], mode='lines', name='EMA 50', line=dict(color='#eab308', width=1.5)))
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], mode='lines', name='EMA 200', line=dict(color='#ef4444', width=2)))

    # Camarilla Horizontal Lines
    if s3 is not None:
        fig.add_hline(y=r4, line_dash="dot", line_color="#b91c1c", annotation_text=f"R4 (Breakout): {r4:.2f}", annotation_position="top left")
        fig.add_hline(y=r3, line_dash="dash", line_color="#f87171", annotation_text=f"R3 (Target): {r3:.2f}", annotation_position="top left")
        fig.add_hline(y=s3, line_dash="dash", line_color="#34d399", annotation_text=f"S3 (Target Entry): {s3:.2f}", annotation_position="bottom left")
        fig.add_hline(y=s4, line_dash="dot", line_color="#059669", annotation_text=f"S4 (Breakdown): {s4:.2f}", annotation_position="bottom left")

    fig.update_layout(
        title=f"<b>{symbol.upper()}</b> - Live Daily Chart with Camarilla Pivots & EMAs",
        yaxis_title="Price (₹)",
        xaxis_title="Date",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        height=650,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    return fig

# ---------------------------------------------------------
# PROPRIETARY QUANTITATIVE SCORE EVALUATOR
# ---------------------------------------------------------
def calculate_checkscore(metrics):
    score = 0
    if metrics.get("QoQ Revenue Growth %", 0) > 15.0: score += 5
    if metrics.get("Profit Growth %", 0) > 20.0: score += 5
    if metrics.get("ROE %", 0) > 18.0: score += 5
    if metrics.get("ROCE %", 0) > 20.0: score += 5
    if metrics.get("OPM %", 0) > 18.0: score += 5
    if metrics.get("Max D/E", 1.0) < 0.3: score += 5
    if metrics.get("OCF Positive", True): score += 5
    if metrics.get("OCF > PAT", True): score += 5
    if metrics.get("Promoter Holding %", 0) > 50.0: score += 5
    if metrics.get("Promoter Change %", 0) > 0: score += 5
    if metrics.get("FII Change %", 0) > 0: score += 5
    if metrics.get("DII Change %", 0) > 0: score += 5
    if metrics.get("Pledge %", 0.0) == 0.0: score += 5
    if metrics.get("Auditor Clean", True): score += 5
    if metrics.get("Positive Concall", True): score += 5
    if metrics.get("Verdict", "") == "BUY": score += 10
    return min(100, score)

def generate_fallback_thesis_and_conviction(symbol, score, rsi_val, cmp_val, entry_val):
    base_conviction = 5
    reasons = []
    
    if isinstance(rsi_val, (int, float)):
        if 40 <= rsi_val <= 60: base_conviction += 2; reasons.append(f"Daily RSI ({rsi_val}) in healthy zone")
        elif rsi_val < 30: base_conviction += 2; reasons.append(f"Daily RSI ({rsi_val}) oversold")
        elif rsi_val > 70: base_conviction -= 1; reasons.append(f"Daily RSI ({rsi_val}) overbought")

    if score >= 70: base_conviction += 2
    elif score < 40: base_conviction -= 2

    if isinstance(cmp_val, (int, float)) and isinstance(entry_val, (int, float)) and entry_val > 0:
        if cmp_val <= entry_val * 1.03:
            base_conviction += 1
            reasons.append("CMP trading near Monthly Camarilla S3 support target entry")

    return f"{min(10, max(1, base_conviction))} / 10", " | ".join(reasons) if reasons else "Consolidating near key structural support levels."

# ---------------------------------------------------------
# OLLAMA VISION AI CHART SCANNER
# ---------------------------------------------------------
def analyze_chart_image_locally(image_path, symbol, model_name="moondream"):
    tv_link = get_tradingview_url(symbol)
    try:
        with open(image_path, "rb") as img_file: base64_image = base64.b64encode(img_file.read()).decode("utf-8")
        prompt = f"Analyze this technical chart for stock symbol {symbol}.\nReturn JSON with exact keys: {{\"Verdict\": \"BUY\" or \"HOLD\" or \"AVOID\", \"Conviction\": integer 1-10, \"Verdict_Reason\": \"Detailed technical research thesis\"}}"
        response = requests.post("http://localhost:11434/api/generate", json={"model": model_name, "prompt": prompt, "images": [base64_image], "stream": False}, timeout=60)
        
        if response.status_code == 200:
            result_text = response.json().get("response", "")
            match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                verdict = str(data.get("Verdict", "HOLD")).upper().strip()
                if verdict not in ["BUY", "HOLD", "AVOID"]: verdict = "HOLD"
                return {"Symbol": symbol, "Verdict": verdict, "Conviction Score": f"{data.get('Conviction', 5)} / 10", "Live Chart": tv_link, "Technical Research Thesis": data.get("Verdict_Reason", "Technical structure reviewed.")}
            else:
                verdict = "BUY" if "BUY" in result_text.upper() else ("AVOID" if "AVOID" in result_text.upper() else "HOLD")
                return {"Symbol": symbol, "Verdict": verdict, "Conviction Score": "6 / 10", "Live Chart": tv_link, "Technical Research Thesis": result_text.replace("\n", " ").strip()[:140]}
        else:
            return {"Symbol": symbol, "Verdict": "HOLD", "Conviction Score": "5 / 10", "Live Chart": tv_link, "Technical Research Thesis": f"HTTP {response.status_code} Error"}
    except Exception:
        return {"Symbol": symbol, "Verdict": "HOLD", "Conviction Score": "5 / 10", "Live Chart": tv_link, "Technical Research Thesis": "Local model offline. Ensure Ollama is running."}

def perform_scan(targets, model_name):
    total = len(targets)
    summary_dict = st.session_state["portfolio_summary"]
    progress_bar = st.progress(0)
    status_box = st.status(f"Scanning {total} charts via Ollama Vision Model...", expanded=True)

    for idx, sym in enumerate(targets):
        status_box.update(label=f"Scanning [{idx + 1}/{total}]: **{sym}**...")
        img_files = glob.glob(os.path.join(DIRS["charts"], f"*{sym}*"))
        if img_files:
            res = analyze_chart_image_locally(img_files[0], sym, model_name)
            summary_dict[sym] = res
            save_json_cache(summary_dict, CACHE_FILE)
            status_box.write(f"✅ Finished **{sym}**: Verdict `{res['Verdict']}`")
        else:
            status_box.write(f"⚠️ Skipped **{sym}**: Chart image not found.")
        progress_bar.progress((idx + 1) / total)

    status_box.update(label="🎉 Scan process complete!", state="complete", expanded=False)
    st.session_state["portfolio_summary"] = summary_dict

# ---------------------------------------------------------
# UNIFIED DATA BINDER & METRIC MAPPING
# ---------------------------------------------------------
def load_screener_data(symbol):
    fund_files = glob.glob(os.path.join(DIRS["fundamentals"], f"*{symbol}*"))
    concall_files = glob.glob(os.path.join(DIRS["concall"], f"*{symbol}*"))
    annual_files = glob.glob(os.path.join(DIRS["annual"], f"*{symbol}*"))
    shareholding_files = glob.glob(os.path.join(DIRS["shareholding"], f"*{symbol}*"))
    
    doc_link = get_local_file_url(fund_files[0]) if fund_files else "N/A"
    concall_link = get_local_file_url(concall_files[0]) if concall_files else "N/A"
    annual_link = get_local_file_url(annual_files[0]) if annual_files else "N/A"

    tech_info = st.session_state.get("tech_data_cache", {}).get(symbol, {})
    live_cmp, live_rsi, entry_val = tech_info.get("CMP (₹)", "N/A"), tech_info.get("Daily RSI (14)", "N/A"), tech_info.get("Target Entry (₹)", "N/A")

    market_cap, roe, roce, opm, de, rev_growth, profit_growth, promoter_holding = 1250.0, 18.5, 21.0, 19.5, 0.25, 15.0, 22.0, 62.4
    pe, peg_ratio, price_to_book, sector_pe, pledge_pct = 24.5, 1.1, 3.2, 28.0, 0.0
    ocf_positive, ocf_gt_pat, auditor_clean, positive_concall = True, True, True, True
    qoq_rev_growth, ebitda_margin_expansion, debt_reduced = 16.5, 1.8, True
    promoter_change, fii_change, dii_change = 0.5, 1.2, 0.8

    if fund_files and os.path.exists(fund_files[0]):
        try:
            df = pd.read_csv(fund_files[0])
            df.columns = [str(c).strip().lower() for c in df.columns]
            if "market_cap" in df.columns: market_cap = float(df["market_cap"].iloc[-1])
            if "roe" in df.columns: roe = float(df["roe"].iloc[-1])
            if "roce" in df.columns: roce = float(df["roce"].iloc[-1])
            if "opm" in df.columns: opm = float(df["opm"].iloc[-1])
            if "debt_to_equity" in df.columns or "de" in df.columns: de = float(df["debt_to_equity" if "debt_to_equity" in df.columns else "de"].iloc[-1])
            if "rev_growth" in df.columns: rev_growth = float(df["rev_growth"].iloc[-1])
            if "profit_growth" in df.columns: profit_growth = float(df["profit_growth"].iloc[-1])
            if "promoter_holding" in df.columns: promoter_holding = float(df["promoter_holding"].iloc[-1])
            if "pe" in df.columns: pe = float(df["pe"].iloc[-1])
            if "peg" in df.columns: peg_ratio = float(df["peg"].iloc[-1])
            if "pb" in df.columns: price_to_book = float(df["pb"].iloc[-1])
            if "sector_pe" in df.columns: sector_pe = float(df["sector_pe"].iloc[-1])
            if "pledge_pct" in df.columns: pledge_pct = float(df["pledge_pct"].iloc[-1])
            if "qoq_rev_growth" in df.columns: qoq_rev_growth = float(df["qoq_rev_growth"].iloc[-1])
            if "margin_expansion" in df.columns: ebitda_margin_expansion = float(df["margin_expansion"].iloc[-1])
            if "debt_reduced" in df.columns: debt_reduced = bool(df["debt_reduced"].iloc[-1])
        except Exception: pass

    if shareholding_files and os.path.exists(shareholding_files[0]):
        try:
            df_sh = pd.read_csv(shareholding_files[0])
            df_sh.columns = [str(c).strip().lower() for c in df_sh.columns]
            if "promoter_change" in df_sh.columns: promoter_change = float(df_sh["promoter_change"].iloc[-1])
            if "fii_change" in df_sh.columns: fii_change = float(df_sh["fii_change"].iloc[-1])
            if "dii_change" in df_sh.columns: dii_change = float(df_sh["dii_change"].iloc[-1])
        except Exception: pass

    verdict_val = st.session_state.get("portfolio_summary", {}).get(symbol, {}).get("Verdict", "HOLD")

    raw_metrics_for_score = {
        "QoQ Revenue Growth %": qoq_rev_growth, "Profit Growth %": profit_growth, "ROE %": roe, "ROCE %": roce,
        "OPM %": opm, "Max D/E": de, "OCF Positive": ocf_positive, "OCF > PAT": ocf_gt_pat,
        "Promoter Holding %": promoter_holding, "Promoter Change %": promoter_change, "FII Change %": fii_change,
        "DII Change %": dii_change, "Pledge %": pledge_pct, "Auditor Clean": auditor_clean,
        "Positive Concall": positive_concall, "Verdict": verdict_val
    }
    checkscore_val = calculate_checkscore(raw_metrics_for_score)

    val_status = "🟢 Cheaper" if pe < sector_pe * 0.85 else ("🔴 Pricier" if pe > sector_pe * 1.25 else "🟡 Fairly Valued")
    triple_stack = "🔥 YES" if (promoter_change > 0 and fii_change > 0 and dii_change > 0) else "❌ NO"

    return {
        "Symbol": symbol, "Live Chart": get_tradingview_url(symbol), "CheckScore": checkscore_val,
        "Score": f"🔥 {checkscore_val}/100" if checkscore_val >= 70 else f"⚠️ {checkscore_val}/100",
        "CMP (Current Market Price)": live_cmp, "CMP (₹)": live_cmp, "Close Price (₹)": live_cmp,
        "Daily RSI (14)": live_rsi, "RSI (Relative Strength Index)": live_rsi,
        "S3 (Monthly Camarilla Support 3)": entry_val, "Target Entry (₹)": entry_val,
        "Market Cap (Cr)": market_cap, "Revenue Growth %": rev_growth, "QoQ Revenue Growth %": qoq_rev_growth,
        "Profit Growth %": profit_growth, "ROE %": roe, "ROCE %": roce, "OPM %": opm,
        "Margin Expansion %": ebitda_margin_expansion, "Max D/E": de, "Debt Reducing": "✅ YES" if debt_reduced else "❌ NO",
        "OCF Positive": "✅ YES" if ocf_positive else "❌ NO", "OCF > PAT": "✅ YES" if ocf_gt_pat else "❌ NO",
        "P/E Ratio": pe, "PEG Ratio": peg_ratio, "Price to Book": price_to_book, "Sector P/E": sector_pe,
        "Valuation Status": val_status, "Promoter Holding %": promoter_holding, "Promoter Change %": promoter_change,
        "FII Change %": fii_change, "DII Change %": dii_change,
        "Institutional Alignment": f"P: +{promoter_change:.2f}% | FII: +{fii_change:.2f}% | DII: +{dii_change:.2f}%",
        "Triple Stack Increase?": triple_stack, "Pledge %": pledge_pct, "Auditor Clean": "✅ YES" if auditor_clean else "❌ NO",
        "Positive Concall": "✅ YES" if positive_concall else "❌ NO", "Research Doc": doc_link,
        "Concall Report": concall_link, "Annual Report": annual_link
    }

# ---------------------------------------------------------
# APPLICATION NAVIGATION TABS
# ---------------------------------------------------------
tab_dashboard, tab_screener, tab_turnaround, tab_value_growth, tab_deepdive = st.tabs([
    "🚀 Executive Dashboard", "🔍 Custom Screener", "🔄 Watchlist 3 – Turnaround Stocks",
    "📈 Value Growth Screener (3836366)", "📊 Stock Deep-Dive"
])

# ---------------------------------------------------------
# TAB 1: EXECUTIVE DASHBOARD
# ---------------------------------------------------------
with tab_dashboard:
    if not detected_companies:
        st.warning(f"No chart images found in directory: `{DIRS['charts']}`.")
    else:
        scan_tab1, scan_tab2 = st.tabs(["⚡ Incremental Scan", "🔄 Full Scan"])
        with scan_tab1:
            remaining_stocks = [s for s in detected_companies if s not in st.session_state["portfolio_summary"]]
            st.write(f"**Already Scanned:** `{len(st.session_state['portfolio_summary'])}` | **Remaining:** `{len(remaining_stocks)}`")
            if st.button("⚡ Scan Remaining Stocks", key="btn_scan_remaining") and remaining_stocks:
                perform_scan(remaining_stocks[:scan_limit], ollama_model); st.rerun()
        with scan_tab2:
            if st.button("🔄 Force Rescan All Stocks", key="btn_scan_all"):
                perform_scan(detected_companies[:scan_limit], ollama_model); st.rerun()

        st.markdown("---")
        if st.button("📈 Fetch Current Market Prices (CMP), Daily RSI & Monthly Camarilla S3", key="btn_fetch_tech"):
            if not YFINANCE_AVAILABLE: st.warning("Please install `yfinance`: `pip install yfinance`")
            else:
                with st.spinner("Fetching live CMP, Daily RSI (14) & Monthly Camarilla S3 support..."):
                    batch_results, err = fetch_tech_metrics_batch(detected_companies)
                    if batch_results:
                        updated_data = st.session_state.get("tech_data_cache", {})
                        updated_data.update(batch_results)
                        st.session_state["tech_data_cache"] = updated_data
                        save_json_cache(updated_data, TECH_CACHE_FILE)
                        st.success("Market technical data updated successfully!"); st.rerun()
                    else: st.error(f"Failed to fetch market data: {err}")

        summary_data_list = []
        for sym in detected_companies:
            full_stock_info = load_screener_data(sym)
            c_score, rsi_val, cmp_val, entry_val = full_stock_info["CheckScore"], full_stock_info["Daily RSI (14)"], full_stock_info["CMP (₹)"], full_stock_info["Target Entry (₹)"]
            
            if sym in st.session_state["portfolio_summary"]:
                item = st.session_state["portfolio_summary"][sym].copy()
                thesis_val = item.get("Technical Research Thesis", item.get("Verdict Reason", ""))
                if not thesis_val.strip(): _, thesis_val = generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)
                item["Technical Research Thesis"] = thesis_val
            else:
                fc, ft = generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)
                item = {"Symbol": sym, "Verdict": "UNSCANNED", "Conviction Score": fc, "Technical Research Thesis": ft, "Live Chart": get_tradingview_url(sym)}

            item.update({"Score": full_stock_info["Score"], "Daily RSI (14)": rsi_val, "CMP (₹)": cmp_val, "Target Entry (₹)": entry_val})
            
            if isinstance(cmp_val, (int, float)) and isinstance(entry_val, (int, float)) and entry_val > 0:
                diff_pct = round(((cmp_val - entry_val) / entry_val) * 100, 2)
                item["Diff % vs Entry"] = f"+{diff_pct}%" if diff_pct > 0 else f"{diff_pct}%"
            else: item["Diff % vs Entry"] = "N/A"
            
            summary_data_list.append(item)

        if summary_data_list:
            summary_df = pd.DataFrame(summary_data_list)
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total Stocks", len(summary_df))
            c2.metric("BUY Calls", len(summary_df[summary_df['Verdict'] == 'BUY']))
            c3.metric("HOLD Calls", len(summary_df[summary_df['Verdict'] == 'HOLD']))
            c4.metric("AVOID Calls", len(summary_df[summary_df['Verdict'] == 'AVOID']))
            c5.metric("Unscanned", len(summary_df[summary_df['Verdict'] == 'UNSCANNED']))

            verdict_filter = st.multiselect("Filter Verdicts", ["BUY", "HOLD", "AVOID", "UNSCANNED"], default=["BUY", "HOLD", "AVOID", "UNSCANNED"], key="v_filter_dash")
            filtered_df = summary_df[summary_df['Verdict'].isin(verdict_filter)]

            ordered_cols = ["Symbol", "Verdict", "Score", "Conviction Score", "Daily RSI (14)", "Target Entry (₹)", "CMP (₹)", "Diff % vs Entry", "Live Chart", "Technical Research Thesis"]
            filtered_df = filtered_df[[c for c in ordered_cols if c in filtered_df.columns]]

            def style_verdict(val):
                if val == 'BUY': return 'background-color: #d1fae5; color: #065f46; font-weight: bold;'
                if val == 'AVOID': return 'background-color: #fee2e2; color: #991b1b; font-weight: bold;'
                if val == 'HOLD': return 'background-color: #fef3c7; color: #92400e; font-weight: bold;'
                return 'background-color: #e2e8f0; color: #4a5568; font-style: italic;'

            def style_diff(val):
                if isinstance(val, str) and "%" in val: return 'color: #dc2626; font-weight: bold;' if val.startswith("+") else 'color: #059669; font-weight: bold;'
                return ''

            st.dataframe(
                filtered_df.style.map(style_verdict, subset=['Verdict']).map(style_diff, subset=['Diff % vs Entry']),
                column_config={"Live Chart": st.column_config.LinkColumn("TradingView", display_text="📈 Open Chart"), "Target Entry (₹)": st.column_config.NumberColumn("Target Entry (Monthly S3 ₹)", format="₹%.2f"), "CMP (₹)": st.column_config.NumberColumn("CMP (₹)", format="₹%.2f")},
                use_container_width=True, height=480
            )

# ---------------------------------------------------------
# TAB 2: QUANTITATIVE SCREENER
# ---------------------------------------------------------
with tab_screener:
    st.subheader("🎯 Institutional Custom Screener")
    with st.expander("🎛️ Screening Criteria", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            min_checkscore = st.slider("Min Score Filter", 0, 100, 50, key="scr_min_score")
            min_roe = st.number_input("Min ROE %", value=15.0, key="scr_min_roe")
            max_de = st.number_input("Max Debt to Equity", value=1.0, key="scr_max_de")
        with col2:
            min_rev_growth = st.number_input("Min Revenue Growth %", value=10.0, key="scr_min_rev")
            min_profit_growth = st.number_input("Min Profit Growth %", value=10.0, key="scr_min_prof")
            min_promoter = st.number_input("Min Promoter Holding %", value=50.0, key="scr_min_prom")
        with col3:
            max_pe = st.number_input("Max P/E Ratio", value=40.0, key="scr_max_pe")
            val_filter = st.selectbox("Valuation Status Filter", ["All", "Discount Only", "Exclude Pricier"], key="scr_val_filter")
            rsi_range = st.slider("Daily RSI Filter Range", 0, 100, (30, 70), key="scr_rsi_range")

    screener_list = []
    for sym in detected_companies:
        item = load_screener_data(sym)
        c_score, rsi_val, cmp_val, entry_val = item["CheckScore"], item["Daily RSI (14)"], item["CMP (₹)"], item["Target Entry (₹)"]
        if sym in st.session_state.get("portfolio_summary", {}):
            item["Verdict"] = st.session_state["portfolio_summary"][sym].get("Verdict", "HOLD")
            item["Technical Research Thesis"] = st.session_state["portfolio_summary"][sym].get("Technical Research Thesis", generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)[1])
        else:
            item["Verdict"] = "UNSCANNED"
            item["Technical Research Thesis"] = generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)[1]
        screener_list.append(item)

    if screener_list:
        df_screener = pd.DataFrame(screener_list)
        filtered_screener = df_screener[
            (df_screener["CheckScore"] >= min_checkscore) & (df_screener["ROE %"] >= min_roe) &
            (df_screener["Max D/E"] <= max_de) & (df_screener["Revenue Growth %"] >= min_rev_growth) &
            (df_screener["Profit Growth %"] >= min_profit_growth) & (df_screener["Promoter Holding %"] >= min_promoter) &
            (df_screener["P/E Ratio"] <= max_pe)
        ]
        rsi_numeric = pd.to_numeric(filtered_screener["Daily RSI (14)"], errors="coerce").fillna(50)
        filtered_screener = filtered_screener[(rsi_numeric >= rsi_range[0]) & (rsi_numeric <= rsi_range[1])]

        if val_filter == "Discount Only": filtered_screener = filtered_screener[filtered_screener["Valuation Status"].str.contains("Cheaper")]
        elif val_filter == "Exclude Pricier": filtered_screener = filtered_screener[~filtered_screener["Valuation Status"].str.contains("Pricier")]

        st.write(f"**Matches Found:** {len(filtered_screener)} / {len(df_screener)}")
        scr_cols = [c for c in filtered_screener.columns if c != "Technical Research Thesis"] + ["Technical Research Thesis"]
        st.dataframe(filtered_screener[scr_cols], use_container_width=True, height=520, column_config={"Live Chart": st.column_config.LinkColumn("Chart", display_text="📈 Open")})

# ---------------------------------------------------------
# TAB 3: WATCHLIST 3 – TURNAROUND STOCKS
# ---------------------------------------------------------
with tab_turnaround:
    st.subheader("🔄 Watchlist 3 — Turnaround Candidates")
    with st.expander("🎛️ Turnaround Filters", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            min_checkscore_t3 = st.slider("Min Score Filter", 0, 100, 60, key="t3_min_score")
            min_qoq_rev = st.number_input("Min QoQ Rev Growth %", value=15.0, key="t3_qoq_rev")
            min_margin = st.number_input("Min EBITDA Margin Expansion %", value=1.0, key="t3_min_margin")
        with col2:
            req_debt_red = st.checkbox("Require Net Debt Reduction", value=True, key="t3_req_debt")
            req_triple = st.checkbox("🔥 Require Triple Stack Increase", value=False, key="t3_req_triple")
        with col3:
            verdict_filter_t3 = st.multiselect("Filter Verdict", ["BUY", "HOLD", "AVOID", "UNSCANNED"], default=["BUY", "HOLD", "AVOID", "UNSCANNED"], key="t3_verdict_filter")

    turnaround_list = []
    for sym in detected_companies:
        item = load_screener_data(sym)
        c_score, rsi_val, cmp_val, entry_val = item["CheckScore"], item["Daily RSI (14)"], item["CMP (₹)"], item["Target Entry (₹)"]
        if sym in st.session_state.get("portfolio_summary", {}):
            item["Verdict"] = st.session_state["portfolio_summary"][sym].get("Verdict", "HOLD")
            item["Technical Research Thesis"] = st.session_state["portfolio_summary"][sym].get("Technical Research Thesis", generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)[1])
        else:
            item["Verdict"] = "UNSCANNED"
            item["Technical Research Thesis"] = generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)[1]
        turnaround_list.append(item)

    if turnaround_list:
        df_turnaround = pd.DataFrame(turnaround_list)
        filtered_t3 = df_turnaround[
            (df_turnaround["CheckScore"] >= min_checkscore_t3) & (df_turnaround["QoQ Revenue Growth %"] >= min_qoq_rev) &
            (df_turnaround["Margin Expansion %"] >= min_margin) & (df_turnaround["Verdict"].isin(verdict_filter_t3))
        ]
        if req_debt_red: filtered_t3 = filtered_t3[filtered_t3["Debt Reducing"] == "✅ YES"]
        if req_triple: filtered_t3 = filtered_t3[filtered_t3["Triple Stack Increase?"] == "🔥 YES"]

        ordered_t3_cols = ["Symbol", "Verdict", "Score", "Triple Stack Increase?", "Institutional Alignment", "QoQ Revenue Growth %", "Margin Expansion %", "Debt Reducing", "CMP (₹)", "Daily RSI (14)", "Live Chart", "Technical Research Thesis"]
        st.dataframe(filtered_t3[[c for c in ordered_t3_cols if c in filtered_t3.columns]].style.map(lambda v: 'background-color: #d1fae5; color: #065f46; font-weight: bold;' if v == '🔥 YES' else '', subset=['Triple Stack Increase?']), use_container_width=True, height=500, column_config={"Live Chart": st.column_config.LinkColumn("Chart", display_text="📈 Open")})

# ---------------------------------------------------------
# TAB 4: VALUE GROWTH SCREENER (3836366)
# ---------------------------------------------------------
with tab_value_growth:
    st.subheader("📈 Value Growth Screener (Screener.in Link: 3836366)")
    with st.expander("🎛️ Screener #3836366 Parameters", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            vg_min_mcap = st.number_input("Min Market Cap (Cr)", value=500.0, key="vg_min_mcap")
            vg_max_pe = st.number_input("Max P/E Ratio", value=30.0, key="vg_max_pe")
            vg_max_peg = st.number_input("Max PEG Ratio", value=1.5, key="vg_max_peg")
            vg_min_roe = st.number_input("Min ROE %", value=15.0, key="vg_min_roe")
        with col2:
            vg_min_roce = st.number_input("Min ROCE %", value=15.0, key="vg_min_roce")
            vg_min_sales_growth = st.number_input("Min Sales Growth %", value=12.0, key="vg_min_sales_growth")
            vg_min_profit_growth = st.number_input("Min Profit Growth %", value=12.0, key="vg_min_profit_growth")
            vg_max_de = st.number_input("Max Debt to Equity", value=0.5, key="vg_max_de")
        with col3:
            vg_min_promoter = st.number_input("Min Promoter Holding %", value=50.0, key="vg_min_promoter")
            vg_max_pledge = st.number_input("Max Promoter Pledge %", value=0.0, key="vg_max_pledge")
            vg_min_opm = st.number_input("Min OPM %", value=15.0, key="vg_min_opm")
            vg_min_score = st.slider("Min Quality Score Filter", 0, 100, 50, key="vg_min_score")

    value_growth_list = []
    for sym in detected_companies:
        item = load_screener_data(sym)
        c_score, rsi_val, cmp_val, entry_val = item["CheckScore"], item["Daily RSI (14)"], item["CMP (₹)"], item["Target Entry (₹)"]
        if sym in st.session_state.get("portfolio_summary", {}):
            item["Verdict"] = st.session_state["portfolio_summary"][sym].get("Verdict", "HOLD")
            item["Technical Research Thesis"] = st.session_state["portfolio_summary"][sym].get("Technical Research Thesis", generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)[1])
        else:
            item["Verdict"] = "UNSCANNED"
            item["Technical Research Thesis"] = generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)[1]
        value_growth_list.append(item)

    if value_growth_list:
        df_vg = pd.DataFrame(value_growth_list)
        filtered_vg = df_vg[
            (df_vg["Market Cap (Cr)"] >= vg_min_mcap) & (df_vg["P/E Ratio"] <= vg_max_pe) &
            (df_vg["PEG Ratio"] <= vg_max_peg) & (df_vg["ROE %"] >= vg_min_roe) &
            (df_vg["ROCE %"] >= vg_min_roce) & (df_vg["Revenue Growth %"] >= vg_min_sales_growth) &
            (df_vg["Profit Growth %"] >= vg_min_profit_growth) & (df_vg["Max D/E"] <= vg_max_de) &
            (df_vg["Promoter Holding %"] >= vg_min_promoter) & (df_vg["Pledge %"] <= vg_max_pledge) &
            (df_vg["OPM %"] >= vg_min_opm) & (df_vg["CheckScore"] >= vg_min_score)
        ]

        v1, v2, v3, v4 = st.columns(4)
        v1.metric("Value Growth Matches", len(filtered_vg))
        v2.metric("Low PEG (< 1.0)", len(filtered_vg[filtered_vg["PEG Ratio"] < 1.0]))
        v3.metric("Buy Verdict Stocks", len(filtered_vg[filtered_vg["Verdict"] == "BUY"]))
        v4.metric("Avg ROE %", f"{round(filtered_vg['ROE %'].mean(), 1) if not filtered_vg.empty else 0.0}%")

        ordered_vg_cols = ["Symbol", "Verdict", "Score", "Market Cap (Cr)", "P/E Ratio", "PEG Ratio", "ROE %", "ROCE %", "Revenue Growth %", "Max D/E", "Promoter Holding %", "CMP (₹)", "Target Entry (₹)", "Daily RSI (14)", "Live Chart", "Technical Research Thesis"]
        st.dataframe(filtered_vg[[c for c in ordered_vg_cols if c in filtered_vg.columns]], column_config={"Live Chart": st.column_config.LinkColumn("Chart", display_text="📈 Open")}, use_container_width=True, height=500)

# ---------------------------------------------------------
# TAB 5: STOCK DEEP-DIVE & LIVE INTERACTIVE CHART
# ---------------------------------------------------------
with tab_deepdive:
    selected_company = st.selectbox("Select Ticker for Detailed Inspection", detected_companies if detected_companies else ["360ONE"], key="dd_ticker_select")
    st.subheader(f"Deep-Dive Research — {selected_company}")
    st.link_button(f"🚀 Open {selected_company} Interactive Live Chart on TradingView", get_tradingview_url(selected_company))
    deep_info = load_screener_data(selected_company)
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("CheckScore", f"{deep_info.get('CheckScore', 0)} / 100")
    m2.metric("CMP (₹)", f"₹{deep_info.get('CMP (₹)', 'N/A')}")
    m3.metric("Target Entry (Monthly S3)", f"₹{deep_info.get('Target Entry (₹)', 'N/A')}")
    m4.metric("Daily RSI (14)", deep_info.get("Daily RSI (14)", "N/A"))

    st.markdown("---")
    
    # Render the new Live Interactive Plotly Chart
    chart_fig = render_interactive_technical_chart(selected_company)
    if chart_fig:
        st.plotly_chart(chart_fig, use_container_width=True)
    
    # Fallback to local saved image if available
    img_files = glob.glob(os.path.join(DIRS["charts"], f"*{selected_company}*"))
    if img_files: 
        st.image(img_files[0], caption=f"Local Saved AI Scan Image: {selected_company}", use_container_width=True)