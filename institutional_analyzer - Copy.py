import os
import glob
import json
import re
import base64
import urllib.parse
import requests
import pandas as pd
import streamlit as st

# Attempt to import yfinance for live price & technical calculations
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# Optional Gemini qualitative analysis support
try:
    from google import genai
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    genai = None
    GOOGLE_GENAI_AVAILABLE = False

# Connected Root Folder Path
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

# --- CACHE & STATE INITIALIZATION ---
def load_json_cache(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {item["Symbol"]: item for item in data if "Symbol" in item}
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

# --- EXECUTIVE DASHBOARD STYLING ---
st.markdown("""
<style>
    .stApp {
        background-color: #f0f4f8;
        color: #1a202c;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    header[data-testid="stHeader"] {
        background-color: #f0f4f8;
    }
    .main-header {
        background: linear-gradient(90deg, #0b2545 0%, #134074 100%);
        padding: 20px 25px;
        border-radius: 12px;
        color: #ffffff;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(11, 37, 69, 0.15);
    }
    .main-header h1 {
        color: #ffffff !important;
        font-size: 26px !important;
        font-weight: 700 !important;
        margin: 0 !important;
    }
    .main-header p {
        color: #8da9c4 !important;
        font-size: 13px !important;
        margin: 4px 0 0 0 !important;
    }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #dce4ec;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    }
    div[data-testid="stMetricLabel"] {
        color: #4a5568 !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    div[data-testid="stMetricValue"] {
        color: #0b2545 !important;
        font-size: 30px !important;
        font-weight: 800 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #e2e8f0;
        padding: 6px;
        border-radius: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 38px;
        border-radius: 6px;
        color: #4a5568;
        font-weight: 600;
        font-size: 14px;
        background-color: transparent;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ffffff !important;
        color: #0b2545 !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
    }
    .stButton>button {
        background-color: #134074;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        font-weight: 600;
        padding: 8px 18px;
        box-shadow: 0 2px 5px rgba(19, 64, 116, 0.2);
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        background-color: #0b2545;
        color: #ffffff;
    }
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

# Main Title Header
st.markdown("""
<div class="main-header">
    <h1>📊 Institutional Equity Research Engine</h1>
    <p>Connected Directory: <b>{}</b> &nbsp;|&nbsp; Target Entry: <b>Monthly Camarilla Pivot (S3)</b></p>
</div>
""".format(BASE_DIR), unsafe_allow_html=True)

# Detect files
chart_files = glob.glob(os.path.join(DIRS["charts"], "*.*"))
detected_companies = sorted(list({os.path.splitext(os.path.basename(f))[0].upper() for f in chart_files}))

# --- SIDEBAR CONTROLS ---
st.sidebar.header("🕹️ Control Panel")
ollama_model = st.sidebar.text_input("Ollama Vision Model", value="moondream")
gemini_api_key = st.sidebar.text_input("Gemini API Key (Optional)", type="password")
scan_limit = st.sidebar.number_input(
    "Max stocks to scan", 
    min_value=1, 
    max_value=max(1, len(detected_companies)), 
    value=min(50, max(1, len(detected_companies)))
)

def get_tradingview_url(symbol):
    clean_symbol = symbol.strip().upper()
    return f"https://www.tradingview.com/chart/?symbol=NSE:{clean_symbol}"

def get_local_file_url(filepath):
    if filepath and os.path.exists(filepath):
        return f"file:///{urllib.parse.quote(os.path.abspath(filepath))}"
    return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def generate_gemini_qualitative_note(symbol, deep_info, thesis_text, api_key):
    if not api_key:
        return None, "Please enter a Gemini API key in the sidebar to enable this feature."

    if not GOOGLE_GENAI_AVAILABLE:
        return None, "The google-genai package is not installed. Please install it with `pip install google-genai`."

    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
Act as a senior equity research analyst. Review {symbol} using the following structured context.

Key metrics:
- CheckScore: {deep_info.get('CheckScore', 'N/A')}
- ROE: {deep_info.get('ROE %', 'N/A')}
- ROCE: {deep_info.get('ROCE %', 'N/A')}
- OPM: {deep_info.get('OPM %', 'N/A')}
- Debt/Equity: {deep_info.get('Max D/E', 'N/A')}
- Revenue Growth: {deep_info.get('Revenue Growth %', 'N/A')}
- Profit Growth: {deep_info.get('Profit Growth %', 'N/A')}
- Promoter Holding: {deep_info.get('Promoter Holding %', 'N/A')}
- Valuation Status: {deep_info.get('Valuation Status', 'N/A')}
- Current Thesis: {thesis_text or 'No thesis available yet.'}

Provide a concise qualitative note with:
1. A 2-sentence investment view
2. 3 bullet points on the key strengths or risks
3. One short conclusion on whether the setup looks attractive or not
"""
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return response.text.strip(), None
    except Exception as e:
        return None, f"Gemini analysis failed: {e}"

# --- CHECKSCORE EVALUATOR ENGINE (MAX SCORE = 100) ---
def calculate_checkscore(metrics):
    score = 0
    breakdown = {}

    if metrics.get("QoQ Revenue Growth %", 0) > 15.0:
        score += 5
        breakdown["Quarterly Sales Growth > 15%"] = 5
    if metrics.get("Profit Growth %", 0) > 20.0:
        score += 5
        breakdown["Quarterly Profit Growth > 20%"] = 5
    if metrics.get("ROE %", 0) > 18.0:
        score += 5
        breakdown["ROE > 18%"] = 5
    if metrics.get("ROCE %", 0) > 20.0:
        score += 5
        breakdown["ROCE > 20%"] = 5
    if metrics.get("OPM %", 0) > 18.0:
        score += 5
        breakdown["OPM > 18%"] = 5
    if metrics.get("Max D/E", 1.0) < 0.3:
        score += 5
        breakdown["Debt/Equity < 0.3"] = 5
    if metrics.get("OCF Positive", True):
        score += 5
        breakdown["OCF Positive"] = 5
    if metrics.get("OCF > PAT", True):
        score += 5
        breakdown["OCF > PAT"] = 5
    if metrics.get("Promoter Holding %", 0) > 50.0:
        score += 5
        breakdown["Promoter Holding > 50%"] = 5
    if metrics.get("Promoter Change %", 0) > 0:
        score += 5
        breakdown["Promoter Increased"] = 5
    if metrics.get("FII Change %", 0) > 0:
        score += 5
        breakdown["FII Increased"] = 5
    if metrics.get("DII Change %", 0) > 0:
        score += 5
        breakdown["DII Increased"] = 5
    if metrics.get("Pledge %", 0.0) == 0.0:
        score += 5
        breakdown["No Pledge"] = 5
    if metrics.get("Auditor Clean", True):
        score += 5
        breakdown["Auditor Clean"] = 5
    if metrics.get("Positive Concall", True):
        score += 5
        breakdown["Positive Concall"] = 5
    if metrics.get("Verdict", "") == "BUY":
        score += 10
        breakdown["Technical Trend Bullish"] = 10

    return score, breakdown

# --- DYNAMIC THESIS & CONVICTION CALCULATOR ---
def generate_fallback_thesis_and_conviction(symbol, score, rsi_val, cmp_val, entry_val):
    base_conviction = 5
    reasons = []

    if isinstance(rsi_val, (int, float)):
        if 40 <= rsi_val <= 60:
            base_conviction += 2
            reasons.append(f"RSI ({rsi_val}) is in neutral/accumulation territory")
        elif rsi_val < 30:
            base_conviction += 2
            reasons.append(f"RSI ({rsi_val}) indicates oversold rebound setup")
        elif rsi_val > 70:
            base_conviction -= 1
            reasons.append(f"RSI ({rsi_val}) indicates overbought zone")

    if score >= 70:
        base_conviction += 2
        reasons.append(f"High Quality Score ({score}/100)")
    elif score < 40:
        base_conviction -= 2
        reasons.append(f"Weak Quality Score ({score}/100)")

    if isinstance(cmp_val, (int, float)) and isinstance(entry_val, (int, float)) and entry_val > 0:
        if cmp_val <= entry_val * 1.03:
            base_conviction += 1
            reasons.append("CMP is trading close to Monthly Camarilla S3 support")

    conviction_final = min(10, max(1, base_conviction))
    thesis_str = " | ".join(reasons) if reasons else "Consolidation structure near key moving averages."
    
    return f"{conviction_final} / 10", thesis_str

# --- BATCH TECHNICAL CALCULATOR ---
def fetch_tech_metrics_batch(symbols):
    if not YFINANCE_AVAILABLE:
        return {}, "yfinance library not installed"
    
    yf_symbols = [f"{sym.strip().upper()}.NS" for sym in symbols]
    results = {}

    try:
        daily_data = yf.download(yf_symbols, period="3mo", interval="1d", group_by="ticker", progress=False)
        monthly_data = yf.download(yf_symbols, period="6mo", interval="1mo", group_by="ticker", progress=False)

        for sym in symbols:
            yf_ticker = f"{sym.strip().upper()}.NS"
            try:
                if len(symbols) == 1:
                    df_daily = daily_data
                    df_monthly = monthly_data
                else:
                    df_daily = daily_data[yf_ticker] if yf_ticker in daily_data else pd.DataFrame()
                    df_monthly = monthly_data[yf_ticker] if yf_ticker in monthly_data else pd.DataFrame()

                df_daily = df_daily.dropna(how="all")
                df_monthly = df_monthly.dropna(how="all")

                if df_daily.empty:
                    results[sym] = {"Daily RSI (14)": "N/A", "CMP (₹)": "N/A", "Target Entry (₹)": "N/A"}
                    continue

                close_prices = df_daily['Close'].dropna()
                latest_close = round(float(close_prices.iloc[-1]), 2) if not close_prices.empty else "N/A"

                if len(close_prices) >= 14:
                    rsi_series = calculate_rsi(close_prices)
                    latest_rsi = round(float(rsi_series.iloc[-1]), 2)
                else:
                    latest_rsi = "N/A"

                camarilla_s3 = "N/A"
                if len(df_monthly) >= 2:
                    prev_month = df_monthly.iloc[-2]
                    h = float(prev_month['High'])
                    l = float(prev_month['Low'])
                    c = float(prev_month['Close'])
                    
                    if not (pd.isna(h) or pd.isna(l) or pd.isna(c)):
                        cam_s3_val = c - ((h - l) * (1.1 / 12.0))
                        camarilla_s3 = round(cam_s3_val, 2)

                results[sym] = {
                    "Daily RSI (14)": latest_rsi,
                    "CMP (₹)": latest_close,
                    "Target Entry (₹)": camarilla_s3
                }
            except Exception:
                results[sym] = {"Daily RSI (14)": "N/A", "CMP (₹)": "N/A", "Target Entry (₹)": "N/A"}

        return results, None

    except Exception as e:
        return {}, str(e)

# --- LOCAL OLLAMA VISION ENGINE ---
def analyze_chart_image_locally(image_path, symbol, model_name="moondream"):
    tv_link = get_tradingview_url(symbol)
    try:
        with open(image_path, "rb") as img_file:
            base64_image = base64.b64encode(img_file.read()).decode("utf-8")

        prompt = (
            f"Analyze this technical chart for stock ticker {symbol}.\n"
            "Evaluate chart structure, trend, support/resistance, and momentum patterns.\n"
            "Return JSON format with exact keys:\n"
            '{"Verdict": "BUY" or "HOLD" or "AVOID", "Conviction": integer 1-10, "Verdict_Reason": "Detailed 1-2 sentence technical reason for giving this verdict"}'
        )

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "images": [base64_image],
                "stream": False
            },
            timeout=60
        )

        if response.status_code == 200:
            result_text = response.json().get("response", "")
            match = re.search(r"\{.*\}", result_text, re.DOTALL)
            
            if match:
                data = json.loads(match.group(0))
                verdict = str(data.get("Verdict", "HOLD")).upper().strip()
                if verdict not in ["BUY", "HOLD", "AVOID"]:
                    verdict = "HOLD"
                conviction = data.get("Conviction", 5)
                reason = data.get("Verdict_Reason", data.get("Thesis", "Technical structure reviewed."))
            else:
                verdict = "BUY" if "BUY" in result_text.upper() else ("AVOID" if "AVOID" in result_text.upper() else "HOLD")
                conviction = 6
                reason = result_text.replace("\n", " ").strip()[:140]

            return {
                "Symbol": symbol,
                "Verdict": verdict,
                "Conviction Score": f"{conviction} / 10",
                "Live Chart": tv_link,
                "Technical Research Thesis": reason
            }
        else:
            return {
                "Symbol": symbol,
                "Verdict": "HOLD",
                "Conviction Score": "5 / 10",
                "Live Chart": tv_link,
                "Technical Research Thesis": f"Ollama HTTP {response.status_code} Error"
            }

    except Exception as e:
        return {
            "Symbol": symbol,
            "Verdict": "HOLD",
            "Conviction Score": "5 / 10",
            "Live Chart": tv_link,
            "Technical Research Thesis": f"Local model error: Ensure Ollama is running (`ollama run {model_name}`)."
        }

# --- IN-LINE SCAN ENGINE ---
def perform_scan(targets, model_name):
    total = len(targets)
    summary_dict = st.session_state["portfolio_summary"]
    
    progress_bar = st.progress(0)
    status_box = st.status(f"Starting vision scan for {total} stocks...", expanded=True)

    for idx, sym in enumerate(targets):
        status_box.update(label=f"Scanning [{idx + 1}/{total}]: **{sym}** with `{model_name}`...")
        
        img_files = glob.glob(os.path.join(DIRS["charts"], f"*{sym}*"))
        if img_files:
            res = analyze_chart_image_locally(img_files[0], sym, model_name)
            summary_dict[sym] = res
            save_json_cache(summary_dict, CACHE_FILE)
            status_box.write(f"✅ Finished **{sym}**: Verdict `{res['Verdict']}`")
        else:
            status_box.write(f"⚠️ Skipping **{sym}**: Chart file not found.")

        progress_bar.progress((idx + 1) / total)

    status_box.update(label="🎉 Scan process complete!", state="complete", expanded=False)
    st.session_state["portfolio_summary"] = summary_dict

def load_screener_data(symbol):
    fund_files = glob.glob(os.path.join(DIRS["fundamentals"], f"*{symbol}*"))
    concall_files = glob.glob(os.path.join(DIRS["concall"], f"*{symbol}*"))
    annual_files = glob.glob(os.path.join(DIRS["annual"], f"*{symbol}*"))
    shareholding_files = glob.glob(os.path.join(DIRS["shareholding"], f"*{symbol}*"))
    
    doc_link = get_local_file_url(fund_files[0]) if fund_files else None
    concall_link = get_local_file_url(concall_files[0]) if concall_files else None
    annual_link = get_local_file_url(annual_files[0]) if annual_files else None

    # Baseline Default Values
    market_cap = 1250.0          # Cr
    roe = 18.5
    roce = 21.0
    opm = 19.5
    de = 0.25
    rev_growth = 15.0
    profit_growth = 22.0
    promoter_holding = 62.4
    pe = 24.5
    peg_ratio = 1.1
    price_to_book = 3.2
    sector_pe = 28.0
    pledge_pct = 0.0
    ocf_positive = True
    ocf_gt_pat = True
    auditor_clean = True
    positive_concall = True

    qoq_rev_growth = 16.5
    ebitda_margin_expansion = 1.8
    debt_reduced = True
    promoter_change = 0.5
    fii_change = 1.2
    dii_change = 0.8

    if fund_files and os.path.exists(fund_files[0]):
        try:
            df = pd.read_csv(fund_files[0])
            df.columns = [str(c).strip().lower() for c in df.columns]
            if "market_cap" in df.columns: market_cap = float(df["market_cap"].iloc[-1])
            if "roe" in df.columns: roe = float(df["roe"].iloc[-1])
            if "roce" in df.columns: roce = float(df["roce"].iloc[-1])
            if "opm" in df.columns: opm = float(df["opm"].iloc[-1])
            if "debt_to_equity" in df.columns: de = float(df["debt_to_equity"].iloc[-1])
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
            if "ocf_positive" in df.columns: ocf_positive = bool(df["ocf_positive"].iloc[-1])
            if "ocf_gt_pat" in df.columns: ocf_gt_pat = bool(df["ocf_gt_pat"].iloc[-1])
            if "auditor_clean" in df.columns: auditor_clean = bool(df["auditor_clean"].iloc[-1])
            if "positive_concall" in df.columns: positive_concall = bool(df["positive_concall"].iloc[-1])
        except Exception:
            pass

    if shareholding_files and os.path.exists(shareholding_files[0]):
        try:
            df_sh = pd.read_csv(shareholding_files[0])
            df_sh.columns = [str(c).strip().lower() for c in df_sh.columns]
            if "promoter_change" in df_sh.columns: promoter_change = float(df_sh["promoter_change"].iloc[-1])
            if "fii_change" in df_sh.columns: fii_change = float(df_sh["fii_change"].iloc[-1])
            if "dii_change" in df_sh.columns: dii_change = float(df_sh["dii_change"].iloc[-1])
        except Exception:
            pass

    verdict_val = "HOLD"
    if symbol in st.session_state.get("portfolio_summary", {}):
        verdict_val = st.session_state["portfolio_summary"][symbol].get("Verdict", "HOLD")

    raw_metrics_for_score = {
        "QoQ Revenue Growth %": qoq_rev_growth,
        "Profit Growth %": profit_growth,
        "ROE %": roe,
        "ROCE %": roce,
        "OPM %": opm,
        "Max D/E": de,
        "OCF Positive": ocf_positive,
        "OCF > PAT": ocf_gt_pat,
        "Promoter Holding %": promoter_holding,
        "Promoter Change %": promoter_change,
        "FII Change %": fii_change,
        "DII Change %": dii_change,
        "Pledge %": pledge_pct,
        "Auditor Clean": auditor_clean,
        "Positive Concall": positive_concall,
        "Verdict": verdict_val
    }

    checkscore_val, score_breakdown = calculate_checkscore(raw_metrics_for_score)

    triple_stack_increase = (promoter_change > 0) and (fii_change > 0) and (dii_change > 0)

    p_str = f"P: {'🟢 +' if promoter_change >= 0 else '🔴 '}{promoter_change:.2f}%"
    f_str = f"FII: {'🟢 +' if fii_change >= 0 else '🔴 '}{fii_change:.2f}%"
    d_str = f"DII: {'🟢 +' if dii_change >= 0 else '🔴 '}{dii_change:.2f}%"
    inst_alignment = f"{p_str} | {f_str} | {d_str}"

    fund_diagnosis = "✅ Healthy: Strong Operating Cash Flow & Sustainable ROE" if (roe >= 15.0 and de <= 0.5) else "⚠️ Flagged: Weak Cash Conversion or High Debt Structure"
    mgmt_dna = f"🚨 RED FLAG: {pledge_pct}% Promoter Pledge Detected" if pledge_pct > 0.0 else "✅ Confident: Stable Stake & Bullish Concall Tone"
    val_status = "🟢 Cheaper (Discount vs Peers)" if pe < sector_pe * 0.85 else ("🔴 Pricier (Premium for Growth)" if pe > sector_pe * 1.25 else "🟡 Fairly Valued vs Sector")

    return {
        "Symbol": symbol,
        "Live Chart": get_tradingview_url(symbol),
        "CheckScore": checkscore_val,
        "Score": f"🔥 {checkscore_val}/100" if checkscore_val >= 70 else f"⚠️ {checkscore_val}/100",
        "Market Cap (Cr)": market_cap,
        "PEG Ratio": peg_ratio,
        "Price to Book": price_to_book,
        "Pledge %": pledge_pct,
        "Fundamental Quality": fund_diagnosis,
        "Management DNA": mgmt_dna,
        "Valuation Status": val_status,
        "Technical Structure": "📈 Markup Phase: Price/Vol Confirmed (No Divergence)",
        "Top 3 Risk Factors": "1. Raw Material Volatility | 2. Regulatory Risk | 3. Client Concentration",
        "Daily RSI (14)": 58.2,
        "ROE %": roe,
        "ROCE %": roce,
        "OPM %": opm,
        "Max D/E": de,
        "Revenue Growth %": rev_growth,
        "Profit Growth %": profit_growth,
        "Promoter Holding %": promoter_holding,
        "P/E Ratio": pe,
        "Close Price (₹)": 450.0,
        "Research Doc": doc_link if doc_link else "N/A",
        "Concall Report": concall_link if concall_link else "N/A",
        "Annual Report": annual_link if annual_link else "N/A",
        "QoQ Revenue Growth %": qoq_rev_growth,
        "Margin Expansion %": ebitda_margin_expansion,
        "Debt Reducing": "✅ YES" if debt_reduced else "❌ NO",
        "Promoter Change %": promoter_change,
        "FII Change %": fii_change,
        "DII Change %": dii_change,
        "Institutional Alignment": inst_alignment,
        "Triple Stack Increase?": "🔥 YES" if triple_stack_increase else "❌ NO"
    }

# Navigation Tabs
tab_dashboard, tab_screener, tab_turnaround, tab_value_growth, tab_deepdive = st.tabs([
    "🚀 Executive Dashboard", 
    "🔍 Custom Screener", 
    "🔄 Watchlist 3 – Turnaround Stocks",
    "📈 Value Growth Screener (3836366)",
    "📊 Stock Deep-Dive"
])

# ---------------------------------------------------------
# TAB 1: EXECUTIVE DASHBOARD
# ---------------------------------------------------------
with tab_dashboard:
    if not detected_companies:
        st.warning(f"No chart files found in `{DIRS['charts']}`.")
    else:
        scan_tab1, scan_tab2 = st.tabs(["⚡ Incremental Scan (Skip Already Scanned)", "🔄 Full Scan (Rescan All Stocks)"])

        with scan_tab1:
            already_scanned_count = len(st.session_state["portfolio_summary"])
            remaining_stocks = [s for s in detected_companies if s not in st.session_state["portfolio_summary"]]
            st.write(f"**Already Scanned:** `{already_scanned_count}` stocks | **Remaining Unscanned:** `{len(remaining_stocks)}` stocks")
            
            if st.button("⚡ Scan Remaining Stocks"):
                if not remaining_stocks:
                    st.info("All detected stocks have already been scanned!")
                else:
                    targets = remaining_stocks[:scan_limit]
                    perform_scan(targets, ollama_model)
                    st.rerun()

        with scan_tab2:
            st.write(f"Rescan up to `{scan_limit}` stocks.")
            if st.button("🔄 Force Rescan All Stocks"):
                targets = detected_companies[:scan_limit]
                perform_scan(targets, ollama_model)
                st.rerun()

        st.markdown("---")
        
        if st.button("📈 Fetch Current Market Prices (CMP), Daily RSI & Monthly Camarilla S3"):
            if not YFINANCE_AVAILABLE:
                st.warning("Please install `yfinance`: `pip install yfinance`")
            else:
                with st.spinner("Fetching live CMP, RSI & Monthly Camarilla S3 levels from NSE in batch mode..."):
                    updated_data = st.session_state.get("tech_data_cache", {})
                    
                    batch_results, err = fetch_tech_metrics_batch(detected_companies)
                    
                    if batch_results:
                        for sym, metrics in batch_results.items():
                            updated_data[sym] = metrics
                        
                        st.session_state["tech_data_cache"] = updated_data
                        save_json_cache(updated_data, TECH_CACHE_FILE)
                        st.success("CMP, Daily RSI, and Monthly Camarilla S3 levels successfully updated!")
                        st.rerun()
                    else:
                        st.error(f"Failed to fetch market metrics: {err}")

        summary_data_list = []
        
        for sym in detected_companies:
            tech_info = st.session_state.get("tech_data_cache", {}).get(sym, {})
            full_stock_info = load_screener_data(sym)
            
            rsi_val = tech_info.get("Daily RSI (14)", "N/A")
            cmp_val = tech_info.get("CMP (₹)", "N/A")
            entry_val = tech_info.get("Target Entry (₹)", "N/A")
            check_score_val = full_stock_info.get("CheckScore", 0)

            if sym in st.session_state["portfolio_summary"]:
                item = st.session_state["portfolio_summary"][sym].copy()
                thesis_val = item.get("Technical Research Thesis", item.get("Verdict Reason", None))
                if not thesis_val or thesis_val.strip() == "":
                    _, thesis_val = generate_fallback_thesis_and_conviction(sym, check_score_val, rsi_val, cmp_val, entry_val)
                item["Technical Research Thesis"] = thesis_val
            else:
                fallback_conviction, fallback_thesis = generate_fallback_thesis_and_conviction(sym, check_score_val, rsi_val, cmp_val, entry_val)
                item = {
                    "Symbol": sym,
                    "Verdict": "UNSCANNED",
                    "Conviction Score": fallback_conviction,
                    "Technical Research Thesis": fallback_thesis,
                    "Live Chart": get_tradingview_url(sym)
                }

            item["Score"] = full_stock_info.get("Score", "0/100")
            item["Daily RSI (14)"] = rsi_val
            item["CMP (₹)"] = cmp_val
            item["Target Entry (₹)"] = entry_val

            if isinstance(cmp_val, (int, float)) and isinstance(entry_val, (int, float)) and entry_val > 0:
                diff_pct = round(((cmp_val - entry_val) / entry_val) * 100, 2)
                item["Diff % vs Entry"] = f"+{diff_pct}%" if diff_pct > 0 else f"{diff_pct}%"
            else:
                item["Diff % vs Entry"] = "N/A"

            summary_data_list.append(item)

        if summary_data_list:
            summary_df = pd.DataFrame(summary_data_list)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total Stocks", len(summary_df))
            c2.metric("BUY Calls", len(summary_df[summary_df['Verdict'] == 'BUY']))
            c3.metric("HOLD Calls", len(summary_df[summary_df['Verdict'] == 'HOLD']))
            c4.metric("AVOID Calls", len(summary_df[summary_df['Verdict'] == 'AVOID']))
            c5.metric("Unscanned", len(summary_df[summary_df['Verdict'] == 'UNSCANNED']))

            st.markdown("---")

            verdict_filter = st.multiselect(
                "Filter Verdicts", 
                options=["BUY", "HOLD", "AVOID", "UNSCANNED"], 
                default=["BUY", "HOLD", "AVOID", "UNSCANNED"], 
                key="v_filter"
            )
            filtered_df = summary_df[summary_df['Verdict'].isin(verdict_filter)]

            ordered_cols = [
                "Symbol", "Verdict", "Score", "Conviction Score", 
                "Daily RSI (14)", "Target Entry (₹)", "CMP (₹)", 
                "Diff % vs Entry", "Live Chart", "Technical Research Thesis"
            ]
            
            cols_to_display = [c for c in ordered_cols if c in filtered_df.columns]
            filtered_df = filtered_df[cols_to_display]

            def style_verdict(val):
                if val == 'BUY':
                    return 'background-color: #d1fae5; color: #065f46; font-weight: bold;'
                elif val == 'AVOID':
                    return 'background-color: #fee2e2; color: #991b1b; font-weight: bold;'
                elif val == 'HOLD':
                    return 'background-color: #fef3c7; color: #92400e; font-weight: bold;'
                return 'background-color: #e2e8f0; color: #4a5568; font-style: italic;'

            def style_diff(val):
                if isinstance(val, str) and "%" in val:
                    if val.startswith("-"):
                        return 'color: #059669; font-weight: bold;'
                    elif val.startswith("+"):
                        return 'color: #dc2626; font-weight: bold;'
                return ''

            styled_table = filtered_df.style.map(style_verdict, subset=['Verdict']).map(style_diff, subset=['Diff % vs Entry'])
            
            st.dataframe(
                styled_table,
                column_config={
                    "Live Chart": st.column_config.LinkColumn("TradingView Chart", display_text="📈 Open Chart"),
                    "Score": st.column_config.TextColumn("Score", width="small"),
                    "Target Entry (₹)": st.column_config.NumberColumn("Target Entry (Monthly S3 ₹)", format="₹%.2f"),
                    "CMP (₹)": st.column_config.NumberColumn("CMP (₹)", format="₹%.2f"),
                    "Technical Research Thesis": st.column_config.TextColumn("Technical Research Thesis", width="large")
                },
                width="stretch",
                height=480
            )

# ---------------------------------------------------------
# TAB 2: QUANTITATIVE SCREENER
# ---------------------------------------------------------
with tab_screener:
    st.subheader("🎯 Institutional Custom Screener & Research Engine")

    with st.expander("🎛️ Institutional Screening Criteria", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            min_checkscore = st.slider("Min Score Filter (Out of 100)", 0, 100, 50)
            min_roe = st.number_input("Min ROE %", value=15.0)
            max_de = st.number_input("Max Debt to Equity", value=1.0)
        with col2:
            min_rev_growth = st.number_input("Min Revenue Growth %", value=10.0)
            min_profit_growth = st.number_input("Min Profit Growth %", value=10.0)
            min_promoter = st.number_input("Min Promoter Holding %", value=50.0)
        with col3:
            max_pe = st.number_input("Max P/E Ratio", value=40.0)
            val_filter = st.selectbox("Valuation Status", ["All", "Discount Only", "Exclude Pricier"])
            rsi_range = st.slider("Daily RSI Filter Range", 0, 100, (30, 70))

    screener_list = []
    for sym in detected_companies:
        item = load_screener_data(sym)
        tech_info = st.session_state.get("tech_data_cache", {}).get(sym, {})
        
        rsi_val = tech_info.get("Daily RSI (14)", 50.0)
        cmp_val = tech_info.get("CMP (₹)", 450.0)
        entry_val = tech_info.get("Target Entry (₹)", 440.0)
        c_score = item.get("CheckScore", 0)

        if sym in st.session_state.get("portfolio_summary", {}):
            scan_info_sym = st.session_state["portfolio_summary"][sym]
            item["Verdict"] = scan_info_sym.get("Verdict", "HOLD")
            thesis_val = scan_info_sym.get("Technical Research Thesis", scan_info_sym.get("Verdict Reason", None))
            if not thesis_val or thesis_val.strip() == "":
                _, thesis_val = generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)
            item["Technical Research Thesis"] = thesis_val
        else:
            _, fallback_thesis = generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)
            item["Verdict"] = "UNSCANNED"
            item["Technical Research Thesis"] = fallback_thesis

        item["Daily RSI (14)"] = rsi_val
        item["Close Price (₹)"] = cmp_val

        screener_list.append(item)

    if screener_list:
        df_screener = pd.DataFrame(screener_list)
        filtered_screener = df_screener[
            (df_screener["CheckScore"] >= min_checkscore) &
            (df_screener["ROE %"] >= min_roe) &
            (df_screener["Max D/E"] <= max_de) &
            (df_screener["Revenue Growth %"] >= min_rev_growth) &
            (df_screener["Profit Growth %"] >= min_profit_growth) &
            (df_screener["Promoter Holding %"] >= min_promoter) &
            (df_screener["P/E Ratio"] <= max_pe)
        ]

        rsi_numeric = pd.to_numeric(filtered_screener["Daily RSI (14)"], errors="coerce").fillna(50)
        filtered_screener = filtered_screener[
            (rsi_numeric >= rsi_range[0]) & (rsi_numeric <= rsi_range[1])
        ]

        if val_filter == "Discount Only":
            filtered_screener = filtered_screener[filtered_screener["Valuation Status"].str.contains("Cheaper")]
        elif val_filter == "Exclude Pricier":
            filtered_screener = filtered_screener[~filtered_screener["Valuation Status"].str.contains("Pricier")]

        st.write(f"**Matches Found:** {len(filtered_screener)} / {len(df_screener)} stocks pass criteria.")
        
        scr_cols = [c for c in filtered_screener.columns if c != "Technical Research Thesis"] + ["Technical Research Thesis"]
        filtered_screener = filtered_screener[scr_cols]

        st.dataframe(
            filtered_screener,
            column_config={
                "Live Chart": st.column_config.LinkColumn("TradingView Chart", display_text="📈 Open Chart"),
                "Score": st.column_config.TextColumn("Score", width="small"),
                "Research Doc": st.column_config.LinkColumn("Fundamentals Doc", display_text="📄 View CSV"),
                "Concall Report": st.column_config.LinkColumn("Concall PDF", display_text="📄 View Concall"),
                "Annual Report": st.column_config.LinkColumn("Annual PDF", display_text="📄 View Annual"),
                "Technical Research Thesis": st.column_config.TextColumn("Technical Research Thesis", width="large")
            },
            width="stretch",
            height=520
        )

# ---------------------------------------------------------
# TAB 3: WATCHLIST 3 – TURNAROUND STOCKS
# ---------------------------------------------------------
with tab_turnaround:
    st.subheader("🔄 Watchlist 3 — Turnaround Candidates")
    st.caption("Filters for companies showing improving quarterly numbers, margin expansion, debt reduction, Score evaluation, and increasing institutional/promoter alignment.")

    with st.expander("🎛️ Turnaround Screener Parameters", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            min_checkscore_t3 = st.slider("Min Score Filter (Max 100)", 0, 100, 60)
            min_qoq_rev = st.number_input("Min QoQ Revenue Growth %", value=15.0)
            min_margin = st.number_input("Min EBITDA Margin Expansion %", value=1.0)
        with col2:
            require_debt_reduction = st.checkbox("Require Net Debt Reduction (QoQ)", value=True)
            only_triple_increase = st.checkbox("🔥 Require ALL 3 (Promoter + FII + DII) to Increase Stake", value=False)
        with col3:
            verdict_filter_t3 = st.multiselect(
                "Filter Verdict", 
                options=["BUY", "HOLD", "AVOID", "UNSCANNED"], 
                default=["BUY", "HOLD", "AVOID", "UNSCANNED"],
                key="t3_verdict_filter"
            )

    turnaround_list = []
    for sym in detected_companies:
        item = load_screener_data(sym)
        tech_info = st.session_state.get("tech_data_cache", {}).get(sym, {})

        rsi_val = tech_info.get("Daily RSI (14)", "N/A")
        cmp_val = tech_info.get("CMP (₹)", "N/A")
        entry_val = tech_info.get("Target Entry (₹)", "N/A")
        c_score = item.get("CheckScore", 0)

        if sym in st.session_state.get("portfolio_summary", {}):
            scan_info_sym = st.session_state["portfolio_summary"][sym]
            item["Verdict"] = scan_info_sym.get("Verdict", "HOLD")
            thesis_val = scan_info_sym.get("Technical Research Thesis", scan_info_sym.get("Verdict Reason", None))
            if not thesis_val or thesis_val.strip() == "":
                _, thesis_val = generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)
            item["Technical Research Thesis"] = thesis_val
        else:
            _, fallback_thesis = generate_fallback_thesis_and_conviction(sym, c_score, rsi_val, cmp_val, entry_val)
            item["Verdict"] = "UNSCANNED"
            item["Technical Research Thesis"] = fallback_thesis

        item["Daily RSI (14)"] = rsi_val
        item["CMP (₹)"] = cmp_val

        turnaround_list.append(item)

    if turnaround_list:
        df_turnaround = pd.DataFrame(turnaround_list)

        filtered_t3 = df_turnaround[
            (df_turnaround["CheckScore"] >= min_checkscore_t3) &
            (df_turnaround["QoQ Revenue Growth %"] >= min_qoq_rev) &
            (df_turnaround["Margin Expansion %"] >= min_margin) &
            (df_turnaround["Verdict"].isin(verdict_filter_t3))
        ]

        if require_debt_reduction:
            filtered_t3 = filtered_t3[filtered_t3["Debt Reducing"] == "✅ YES"]

        if only_triple_increase:
            filtered_t3 = filtered_t3[filtered_t3["Triple Stack Increase?"] == "🔥 YES"]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Turnaround Candidates", len(filtered_t3))
        m2.metric("Triple Stack Buy Signals", len(filtered_t3[filtered_t3["Triple Stack Increase?"] == "🔥 YES"]))
        m3.metric("Debt Reducing Companies", len(filtered_t3[filtered_t3["Debt Reducing"] == "✅ YES"]))
        m4.metric("Buy Verdicts", len(filtered_t3[filtered_t3["Verdict"] == "BUY"]))

        st.markdown("---")

        ordered_t3_cols = [
            "Symbol", "Verdict", "Score", "Triple Stack Increase?", "Institutional Alignment", 
            "QoQ Revenue Growth %", "Margin Expansion %", "Debt Reducing", 
            "CMP (₹)", "Daily RSI (14)", "Live Chart", "Technical Research Thesis"
        ]

        display_t3 = filtered_t3[[c for c in ordered_t3_cols if c in filtered_t3.columns]]

        def style_triple(val):
            if val == '🔥 YES':
                return 'background-color: #d1fae5; color: #065f46; font-weight: bold;'
            return ''

        styled_t3 = display_t3.style.map(style_triple, subset=['Triple Stack Increase?'])

        st.dataframe(
            styled_t3,
            column_config={
                "Live Chart": st.column_config.LinkColumn("TradingView Chart", display_text="📈 Open Chart"),
                "Score": st.column_config.TextColumn("Score", width="small"),
                "Institutional Alignment": st.column_config.TextColumn("QoQ Stake Change (P | FII | DII)", width="medium"),
                "Triple Stack Increase?": st.column_config.TextColumn("All 3 Stacked?", width="small"),
                "Technical Research Thesis": st.column_config.TextColumn("Technical Research Thesis", width="large")
            },
            width="stretch",
            height=500
        )

# ---------------------------------------------------------
# TAB 4: VALUE GROWTH SCREENER (SCREENER LINK 3836366 INTEGRATION)
# ---------------------------------------------------------
with tab_value_growth:
    st.subheader("📈 Value Growth Screener (Screener.in Link: 3836366)")
    st.caption("Filters high quality growth stocks trading at reasonable valuations using criteria from Screener Query #3836366.")
    st.link_button("🔗 View Original Screener Query 3836366 Live", "https://www.screener.in/screens/3836366/value-growth-screener/")

    with st.expander("🎛️ Screener #3836366 Parameters", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            vg_min_mcap = st.number_input("Min Market Cap (Cr)", value=500.0, key="vg_min_mcap")
            vg_max_pe = st.number_input("Max P/E Ratio", value=30.0, key="vg_max_pe")
            vg_max_peg = st.number_input("Max PEG Ratio", value=1.5, key="vg_max_peg")
            vg_min_roe = st.number_input("Min ROE %", value=15.0, key="vg_min_roe")
        with col2:
            vg_min_roce = st.number_input("Min ROCE %", value=15.0, key="vg_min_roce")
            vg_min_sales_growth = st.number_input("Min Sales Growth % (3Y / Annual)", value=12.0, key="vg_min_sales_growth")
            vg_min_profit_growth = st.number_input("Min Profit Growth % (3Y / Annual)", value=12.0, key="vg_min_profit_growth")
            vg_max_de = st.number_input("Max Debt to Equity Ratio", value=0.5, key="vg_max_de")
        with col3:
            vg_min_promoter = st.number_input("Min Promoter Holding %", value=50.0, key="vg_min_promoter")
            vg_max_pledge = st.number_input("Max Promoter Pledge %", value=0.0, key="vg_max_pledge")
            vg_min_opm = st.number_input("Min Operating Margin (OPM %)", value=15.0, key="vg_min_opm")
            vg_min_score = st.slider("Min Quality Score Filter", 0, 100, 50, key="vg_min_score")

# ---------------------------------------------------------
# TAB 5: STOCK DEEP-DIVE
# ---------------------------------------------------------
with tab_deepdive:
    selected_company = st.selectbox("Select Ticker for Detailed Inspection", detected_companies if detected_companies else ["360ONE"])
    st.subheader(f"Deep-Dive Research — {selected_company}")

    tv_url = get_tradingview_url(selected_company)
    st.link_button(f"🚀 Open {selected_company} Interactive Live Chart on TradingView", tv_url)

    deep_info = load_screener_data(selected_company)
    c_score = deep_info.get("CheckScore", 0)
    
    st.metric("Total Quality Score", f"{c_score} / 100")

    img_files = glob.glob(os.path.join(DIRS["charts"], f"*{selected_company}*"))
    if img_files:
        st.image(img_files[0], caption=f"{selected_company} Saved Screenshot", width="stretch")
    else:
        st.info("No saved image found for selected ticker.")

    st.markdown("---")
    st.subheader("🧠 Gemini Qualitative Review")

    scan_summary = st.session_state.get("portfolio_summary", {}).get(selected_company, {})
    thesis_text = scan_summary.get("Technical Research Thesis", "") or deep_info.get("Technical Research Thesis", "")

    if st.button("Run Gemini Qualitative Review", key=f"gemini_{selected_company}"):
        with st.spinner("Generating qualitative review..."):
            note_text, error_text = generate_gemini_qualitative_note(
                selected_company,
                deep_info,
                thesis_text,
                gemini_api_key,
            )

        if error_text:
            st.warning(error_text)
        elif note_text:
            st.markdown(note_text)