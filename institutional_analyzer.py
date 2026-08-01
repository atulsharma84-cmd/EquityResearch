import os
import glob
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google import genai

# Define base folder path
BASE_DIR = r"C:\Users\Suchit Sharma\Downloads\files"

DIRS = {
    "charts": os.path.join(BASE_DIR, "charts"),
    "fundamentals": os.path.join(BASE_DIR, "fundamentals"),
    "concall": os.path.join(BASE_DIR, "concall_transcripts"),
    "annual": os.path.join(BASE_DIR, "annual_reports"),
    "shareholding": os.path.join(BASE_DIR, "shareholding"),
}

# Ensure directories exist
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

st.set_page_config(page_title="Institutional Equity Research Terminal", layout="wide")

st.title("🏦 Institutional Equity Research Engine")
st.caption("Automated Multi-Stock Scanning & Executive Portfolio Dashboard")

# --- HELPER FUNCTIONS ---
def find_matching_file(folder_path, symbol):
    """Finds CSV/Excel files that match the company symbol name."""
    files = glob.glob(os.path.join(folder_path, f"*{symbol}*"))
    return files[0] if files else None

def read_data(file_path):
    if not file_path or not os.path.exists(file_path):
        return None
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.csv':
        return pd.read_csv(file_path)
    elif ext in ['.xlsx', '.xls']:
        return pd.read_excel(file_path)
    return None

def analyze_stock_backend(symbol):
    """Runs automated background calculations for a given stock symbol."""
    chart_file = find_matching_file(DIRS["charts"], symbol)
    if not chart_file:
        return None
    
    df = read_data(chart_file)
    if df is None or not isinstance(df, pd.DataFrame):
        return None
    
    df.columns = [str(c).strip().lower() for c in df.columns]
    date_col = next((c for c in df.columns if any(k in c for k in ['date', 'time', 'day'])), None)
    close_col = next((c for c in df.columns if any(k in c for k in ['close', 'price', 'ltp'])), None)
    
    if not date_col or not close_col:
        return None
    
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(by=date_col)
    
    df['EMA_20'] = df[close_col].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df[close_col].ewm(span=50, adjust=False).mean()
    df['EMA_200'] = df[close_col].ewm(span=200, adjust=False).mean()

    latest_close = float(df[close_col].iloc[-1])
    ema_20 = float(df['EMA_20'].iloc[-1])
    ema_50 = float(df['EMA_50'].iloc[-1])
    ema_200 = float(df['EMA_200'].iloc[-1])

    # Automated Logic Engine for Verdicts & Scores
    if latest_close > ema_20 > ema_50 > ema_200:
        verdict = "BUY"
        conviction = 8
        trend_summary = "Strong Markup Phase — Healthy momentum across all EMAs."
        target_entry = latest_close * 0.95  # 5% pullback entry
    elif latest_close < ema_20 < ema_50 < ema_200:
        verdict = "AVOID"
        conviction = 3
        trend_summary = "Markdown Phase — Heavy selling pressure below 200 EMA."
        target_entry = ema_200 * 0.85
    elif abs(ema_20 - ema_50) / ema_50 < 0.02:
        verdict = "HOLD"
        conviction = 6
        trend_summary = "Accumulation Zone — Consolidating sideways near key support."
        target_entry = ema_200
    else:
        verdict = "HOLD"
        conviction = 5
        trend_summary = "Transitional Structure — Waiting for range breakout/retest."
        target_entry = ema_200

    return {
        "Symbol": symbol,
        "Verdict": verdict,
        "Conviction (out of 10)": conviction,
        "Current Price (₹)": round(latest_close, 2),
        "Target Entry (₹)": round(target_entry, 2),
        "200 EMA Support (₹)": round(ema_200, 2),
        "One-Line Thesis": trend_summary
    }

# --- DETECT ALL STOCKS IN CHARTS FOLDER ---
chart_files = glob.glob(os.path.join(DIRS["charts"], "*.*"))
detected_companies = sorted(list({os.path.splitext(os.path.basename(f))[0].upper() for f in chart_files}))

# --- SIDEBAR & VIEW SELECTOR ---
st.sidebar.header("1. View Mode")
view_mode = st.sidebar.radio("Select View", ["🚀 Master Portfolio Dashboard", "🔍 Individual Deep-Dive"])
gemini_api_key = st.sidebar.text_input("Gemini API Key (Optional)", type="password")

# =========================================================
# VIEW 1: MASTER PORTFOLIO DASHBOARD (ALL STOCKS SUMMARY)
# =========================================================
if view_mode == "🚀 Master Portfolio Dashboard":
    st.subheader("📊 Portfolio Final Verdict Engine")
    st.markdown("All detected stocks scanned automatically in the background:")

    if not detected_companies:
        st.warning("No CSV/Excel files found in `C:\\Users\\Suchit Sharma\\Downloads\\files\\charts\\`.")
    else:
        with st.spinner("Processing technicals & calculating verdicts across all stocks..."):
            summary_data = []
            for sym in detected_companies:
                res = analyze_stock_backend(sym)
                if res:
                    summary_data.append(res)

        if summary_data:
            summary_df = pd.DataFrame(summary_data)

            # High-Level Metric Tiles
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Stocks Analyzed", len(summary_df))
            c2.metric("BUY Opportunities", len(summary_df[summary_df['Verdict'] == 'BUY']))
            c3.metric("HOLD Watches", len(summary_df[summary_df['Verdict'] == 'HOLD']))
            c4.metric("AVOID Warnings", len(summary_df[summary_df['Verdict'] == 'AVOID']))

            st.markdown("---")

            # Quick Verdict Filter Button
            verdict_filter = st.multiselect("Filter by Verdict", options=["BUY", "HOLD", "AVOID"], default=["BUY", "HOLD", "AVOID"])
            filtered_df = summary_df[summary_df['Verdict'].isin(verdict_filter)]

            # Styling the table with color coding
            def style_verdict(val):
                if val == 'BUY':
                    return 'background-color: #1e4620; color: #00ff7f; font-weight: bold;'
                elif val == 'AVOID':
                    return 'background-color: #4a1515; color: #ff4d4d; font-weight: bold;'
                return 'background-color: #4a3e15; color: #ffd700; font-weight: bold;'

            styled_table = filtered_df.style.map(style_verdict, subset=['Verdict']).format({
                "Current Price (₹)": "{:.2f}",
                "Target Entry (₹)": "{:.2f}",
                "200 EMA Support (₹)": "{:.2f}"
            })

            st.dataframe(styled_table, use_container_width=True, height=400)
        else:
            st.error("No valid stock chart data could be parsed.")

# =========================================================
# VIEW 2: INDIVIDUAL DEEP-DIVE
# =========================================================
else:
    selected_company = st.sidebar.selectbox("Select Ticker for Deep-Dive", detected_companies if detected_companies else ["RELIANCE"])
    
    st.subheader(f"Deep-Dive Research — {selected_company}")
    
    chart_file = find_matching_file(DIRS["charts"], selected_company)
    if chart_file:
        df_chart = read_data(chart_file)
        if isinstance(df_chart, pd.DataFrame):
            df_chart.columns = [str(c).strip().lower() for c in df_chart.columns]
            date_col = next((c for c in df_chart.columns if any(k in c for k in ['date', 'time', 'day'])), None)
            close_col = next((c for c in df_chart.columns if any(k in c for k in ['close', 'price', 'ltp'])), None)
            
            if date_col and close_col:
                df_chart[date_col] = pd.to_datetime(df_chart[date_col])
                df_chart = df_chart.sort_values(by=date_col)
                
                df_chart['EMA_20'] = df_chart[close_col].ewm(span=20, adjust=False).mean()
                df_chart['EMA_50'] = df_chart[close_col].ewm(span=50, adjust=False).mean()
                df_chart['EMA_200'] = df_chart[close_col].ewm(span=200, adjust=False).mean()

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_chart[date_col], y=df_chart[close_col], name="Close Price", line=dict(color="white")))
                fig.add_trace(go.Scatter(x=df_chart[date_col], y=df_chart['EMA_20'], name="20 EMA", line=dict(color="cyan")))
                fig.add_trace(go.Scatter(x=df_chart[date_col], y=df_chart['EMA_50'], name="50 EMA", line=dict(color="orange")))
                fig.add_trace(go.Scatter(x=df_chart[date_col], y=df_chart['EMA_200'], name="200 EMA", line=dict(color="magenta")))

                fig.update_layout(template="plotly_dark", title=f"{selected_company} Price Structure", xaxis_title="Date", yaxis_title="Price")
                st.plotly_chart(fig, use_container_width=True)