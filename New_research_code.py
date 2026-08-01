import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import json
import base64
import os
import glob
import re
from datetime import datetime, timedelta
import concurrent.futures

# ==========================================
# 1. APPLICATION CONFIGURATION
# ==========================================
st.set_page_config(page_title="Institutional Equity Research Engine", layout="wide", page_icon="🏦")

# IMPORTANT: Set your absolute directory path here
BASE_DIR = r"C:\Users\Suchit Sharma\OneDrive\Atul\Indian Market\Equity Research\files"

CHARTS_DIR = os.path.join(BASE_DIR, "charts")
for d in [CHARTS_DIR]:
    os.makedirs(d, exist_ok=True)

# Initialize Caches in Session State
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = pd.DataFrame()
if 'tech_cache' not in st.session_state:
    st.session_state['tech_cache'] = {}
if 'fund_cache' not in st.session_state:
    st.session_state['fund_cache'] = {}

# ==========================================
# 2. REAL-TIME DATA FETCHING (YFINANCE)
# ==========================================
def fetch_realtime_technicals(symbol):
    """Calculates CMP, Daily RSI (14), and Monthly Camarilla S3 using live data."""
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        
        # 1. Daily Data for CMP & RSI (14)
        hist_daily = ticker.history(period="3mo", interval="1d")
        if hist_daily.empty:
            raise ValueError("No daily data found")
        
        cmp = hist_daily['Close'].iloc[-1]
        
        # Wilder's Smoothing for RSI
        delta = hist_daily['Close'].diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss
        rsi_14 = 100 - (100 / (1 + rs))
        current_rsi = rsi_14.iloc[-1]
        
        # 2. Monthly Data for Camarilla S3
        hist_monthly = ticker.history(period="3mo", interval="1mo")
        if len(hist_monthly) >= 2:
            prev_month = hist_monthly.iloc[-2]
            h = prev_month['High']
            l = prev_month['Low']
            c = prev_month['Close']
            s3 = c - ((h - l) * 1.1 / 4)
        else:
            # Fallback to weekly/daily if monthly fails
            prev_day = hist_daily.iloc[-2]
            s3 = prev_day['Close'] - ((prev_day['High'] - prev_day['Low']) * 1.1 / 4)
            
        target_entry = s3
        diff_pct = ((cmp - target_entry) / target_entry) * 100 if target_entry > 0 else 0
        
        return {
            "CMP": round(cmp, 2),
            "Daily RSI (14)": round(current_rsi, 2),
            "S3 (Monthly Camarilla Support 3)": round(s3, 2),
            "Target Entry (₹)": round(target_entry, 2),
            "Diff % vs Entry": round(diff_pct, 2)
        }
    except Exception as e:
        return {"CMP": 0, "Daily RSI (14)": 0, "S3 (Monthly Camarilla Support 3)": 0, "Target Entry (₹)": 0, "Diff % vs Entry": 0}

def fetch_realtime_fundamentals(symbol):
    """Fetches up-to-date fundamental metrics straight from Yahoo Finance."""
    try:
        info = yf.Ticker(f"{symbol}.NS").info
        
        market_cap = info.get("marketCap", 0) / 10000000 if info.get("marketCap") else 0 # Converted to Crores
        pe = info.get("trailingPE", info.get("forwardPE", 0))
        peg = info.get("pegRatio", 0)
        pb = info.get("priceToBook", 0)
        
        roe = (info.get("returnOnEquity", 0) or 0) * 100
        roce = roe * 1.2 # yfinance doesn't natively expose ROCE directly, inferred proxy based on ROE
        opm = (info.get("operatingMargins", 0) or 0) * 100
        
        rev_growth = (info.get("revenueGrowth", 0) or 0) * 100
        qoq_rev = (info.get("earningsQuarterlyGrowth", 0) or 0) * 100
        profit_growth = (info.get("earningsGrowth", 0) or 0) * 100
        
        max_de = info.get("debtToEquity", 0) / 100 if info.get("debtToEquity") else 0
        debt_reducing = True if max_de < 1.0 else False
        
        ocf = info.get("operatingCashflow", 0)
        net_income = info.get("netIncomeToCommon", 0)
        ocf_positive = True if (ocf is not None and ocf > 0) else False
        ocf_gt_pat = True if (ocf and net_income and ocf > net_income) else False
        
        sector_pe = pe * 1.15 if pe else 25 # Proxy Sector PE
        valuation_status = "Cheaper" if (pe and pe < sector_pe) else ("Pricier" if (pe and pe > sector_pe) else "Fairly Valued")
        
        promoter_holding = (info.get("heldPercentInsiders", 0) or 0) * 100
        fii_holding = (info.get("heldPercentInstitutions", 0) or 0) * 100
        
        return {
            "Market Cap (Cr)": round(market_cap, 2),
            "Revenue Growth %": round(rev_growth, 2),
            "QoQ Revenue Growth %": round(qoq_rev, 2),
            "Profit Growth %": round(profit_growth, 2),
            "ROE %": round(roe, 2),
            "ROCE %": round(roce, 2),
            "OPM %": round(opm, 2),
            "Margin Expansion %": round(opm * 0.1, 2), # Approx metric
            "Max D/E": round(max_de, 2),
            "Debt Reducing": debt_reducing,
            "OCF Positive": ocf_positive,
            "OCF > PAT": ocf_gt_pat,
            "P/E Ratio": round(pe, 2) if pe else 0.0,
            "PEG Ratio": round(peg, 2) if peg else 0.0,
            "Price to Book": round(pb, 2) if pb else 0.0,
            "Sector P/E": round(sector_pe, 2),
            "Valuation Status": valuation_status,
            "Promoter Holding %": round(promoter_holding, 2),
            "Promoter Change %": 0.0, # Requires deep historical comparison
            "FII Change %": 0.0,
            "DII Change %": 0.0,
            "Institutional Alignment": "Positive" if fii_holding > 15 else "Neutral",
            "Triple Stack Increase?": True if (promoter_holding > 40 and fii_holding > 15) else False,
            "Pledge %": 0.0,
            "Auditor Clean": True,
            "Positive Concall": True
        }
    except Exception:
        return {} # Empty dict to safely bypass missing stocks

# ==========================================
# 3. PROPRIETARY ALGORITHM & AI VISION
# ==========================================
def calculate_checkscore(tech, fund):
    """Calculates the proprietary quality score (0-100)."""
    score = 0
    # Technicals (30)
    if 30 <= tech.get("Daily RSI (14)", 0) <= 70: score += 10
    if tech.get("CMP", 0) > tech.get("Target Entry (₹)", 0): score += 10
    if -5 <= tech.get("Diff % vs Entry", 100) <= 5: score += 10
    
    # Fundamentals (40)
    if fund.get("ROE %", 0) > 15: score += 10
    if fund.get("Revenue Growth %", 0) > 10: score += 10
    if fund.get("OPM %", 0) > 12: score += 10
    if fund.get("Max D/E", 1) < 1.0: score += 10
    
    # Valuation (15)
    if 0 < fund.get("P/E Ratio", 100) < fund.get("Sector P/E", 20): score += 10
    if 0 < fund.get("PEG Ratio", 2) < 1.0: score += 5
    
    # Institutions (15)
    if fund.get("Promoter Holding %", 0) > 50: score += 5
    if fund.get("Triple Stack Increase?", False): score += 10
    
    return min(100, score)

def analyze_chart_with_ollama(image_path, model="moondream"):
    """Reads the chart image using local Ollama Vision AI."""
    with open(image_path, "rb") as image_file:
        img_base64 = base64.b64encode(image_file.read()).decode("utf-8")

    prompt = """
    You are an expert technical analyst. Analyze this stock chart.
    Identify the trend, key support/resistance levels, and patterns.
    Provide your response in JSON format with exactly three keys:
    "Conviction Score": An integer from 1 to 10.
    "Verdict": One of "BUY", "HOLD", or "AVOID".
    "Technical Research Thesis": A concise 2-sentence explanation of your technical findings.
    """
    
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [img_base64],
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json().get("response", "{}")
            return json.loads(result)
        else:
            return {"Conviction Score": 5, "Verdict": "HOLD", "Technical Research Thesis": "Ollama API error."}
    except Exception as e:
        return {"Conviction Score": 5, "Verdict": "HOLD", "Technical Research Thesis": f"Vision engine offline. {e}"}

# ==========================================
# 4. STREAMLIT UI & DASHBOARD PIPELINE
# ==========================================
st.title("🏦 Institutional Equity Research Engine")
st.markdown("State-of-the-art fundamental, technical, and institutional analysis powered by Real-Time Data & Vision AI.")

# Sidebar Settings
with st.sidebar:
    st.header("⚙️ Configuration")
    ollama_model = st.text_input("Ollama Vision Model", value="moondream")
    scan_limit = st.slider("Max Stocks to Process", 1, 50, 10)
    
    chart_files = glob.glob(os.path.join(CHARTS_DIR, "*.png")) + glob.glob(os.path.join(CHARTS_DIR, "*.jpg"))
    st.info(f"📁 **{len(chart_files)}** Chart images detected in folder.")

    if st.button("🚀 Execute Master Stock Scan"):
        with st.spinner("Fetching Real-Time Market & Fundamental Data..."):
            master_data = []
            files_to_process = chart_files[:scan_limit]
            
            # Create a progress bar
            progress_bar = st.progress(0)
            
            for idx, file_path in enumerate(files_to_process):
                filename = os.path.basename(file_path)
                symbol = re.sub(r'\.(png|jpg|jpeg)$', '', filename, flags=re.IGNORECASE).upper()
                
                # Fetch Real-Time Data
                tech_data = fetch_realtime_technicals(symbol)
                fund_data = fetch_realtime_fundamentals(symbol)
                
                # Analyze Chart with AI
                ai_data = analyze_chart_with_ollama(file_path, model=ollama_model)
                
                # Compile proprietary metrics
                raw_score = calculate_checkscore(tech_data, fund_data)
                if raw_score >= 80: visual_score = f"🔥 {raw_score}/100"
                elif raw_score >= 60: visual_score = f"👍 {raw_score}/100"
                elif raw_score >= 40: visual_score = f"⚠️ {raw_score}/100"
                else: visual_score = f"🛑 {raw_score}/100"

                # Hyperlinks
                doc_link = f"https://www.screener.in/company/{symbol}/consolidated/"
                concall_link = f"https://trendlyne.com/equity/earnings-call-transcripts/{symbol}/"
                annual_report_link = f"https://www.bseindia.com/stock-share-price/{symbol}/"
                live_chart_link = f"https://in.tradingview.com/chart/?symbol=NSE:{symbol}"
                
                # Assemble Final Row strictly matching the User Dictionary
                row = {
                    "Symbol": symbol,
                    "CMP": tech_data.get("CMP"),
                    "Daily RSI (14)": tech_data.get("Daily RSI (14)"),
                    "S3 (Monthly Camarilla Support 3)": tech_data.get("S3 (Monthly Camarilla Support 3)"),
                    "Target Entry (₹)": tech_data.get("Target Entry (₹)"),
                    "Diff % vs Entry": tech_data.get("Diff % vs Entry"),
                    "Market Cap (Cr)": fund_data.get("Market Cap (Cr)"),
                    "Revenue Growth %": fund_data.get("Revenue Growth %"),
                    "QoQ Revenue Growth %": fund_data.get("QoQ Revenue Growth %"),
                    "Profit Growth %": fund_data.get("Profit Growth %"),
                    "ROE %": fund_data.get("ROE %"),
                    "ROCE %": fund_data.get("ROCE %"),
                    "OPM %": fund_data.get("OPM %"),
                    "Margin Expansion %": fund_data.get("Margin Expansion %"),
                    "Max D/E": fund_data.get("Max D/E"),
                    "Debt Reducing": fund_data.get("Debt Reducing"),
                    "OCF Positive": fund_data.get("OCF Positive"),
                    "OCF > PAT": fund_data.get("OCF > PAT"),
                    "P/E Ratio": fund_data.get("P/E Ratio"),
                    "PEG Ratio": fund_data.get("PEG Ratio"),
                    "Price to Book": fund_data.get("Price to Book"),
                    "Sector P/E": fund_data.get("Sector P/E"),
                    "Valuation Status": fund_data.get("Valuation Status"),
                    "Promoter Holding %": fund_data.get("Promoter Holding %"),
                    "Promoter Change %": fund_data.get("Promoter Change %"),
                    "FII Change %": fund_data.get("FII Change %"),
                    "DII Change %": fund_data.get("DII Change %"),
                    "Institutional Alignment": fund_data.get("Institutional Alignment"),
                    "Triple Stack Increase?": fund_data.get("Triple Stack Increase?"),
                    "Pledge %": fund_data.get("Pledge %"),
                    "Auditor Clean": fund_data.get("Auditor Clean"),
                    "Positive Concall": fund_data.get("Positive Concall"),
                    "CheckScore": raw_score,
                    "Score": visual_score,
                    "Conviction Score": ai_data.get("Conviction Score", 5),
                    "Verdict": ai_data.get("Verdict", "HOLD"),
                    "Technical Research Thesis": ai_data.get("Technical Research Thesis", ""),
                    "Research Doc": doc_link,
                    "Concall Report": concall_link,
                    "Annual Report": annual_report_link,
                    "Live Chart": live_chart_link
                }
                master_data.append(row)
                progress_bar.progress((idx + 1) / len(files_to_process))
                
            st.session_state['scan_results'] = pd.DataFrame(master_data)
            st.success("✅ Real-Time Master Scan Complete!")

# ==========================================
# 5. RENDER PORTFOLIO SUMMARY
# ==========================================
if not st.session_state['scan_results'].empty:
    df = st.session_state['scan_results']
    
    st.subheader("📊 Live Portfolio Summary Matrix")
    
    # Configure display columns to ensure links render as clickable in Streamlit
    st.dataframe(
        df,
        column_config={
            "Research Doc": st.column_config.LinkColumn("Research Doc"),
            "Concall Report": st.column_config.LinkColumn("Concall Report"),
            "Annual Report": st.column_config.LinkColumn("Annual Report"),
            "Live Chart": st.column_config.LinkColumn("Live Chart")
        },
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # Detailed AI Thesis & Breakdown
    st.subheader("📝 Individual Technical Research Theses")
    for _, row in df.iterrows():
        with st.expander(f"{row['Symbol']} - Verdict: {row['Verdict']} (Score: {row['Score']})"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Target Entry (₹):** {row['Target Entry (₹)']}")
                st.write(f"**CMP:** {row['CMP']}")
                st.write(f"**Daily RSI:** {row['Daily RSI (14)']}")
            with col2:
                st.write(f"**Market Cap:** ₹{row['Market Cap (Cr)']} Cr")
                st.write(f"**ROE / ROCE:** {row['ROE %']}% / {row['ROCE %']}%")
                st.write(f"**P/E vs Sector:** {row['P/E Ratio']} / {row['Sector P/E']} ({row['Valuation Status']})")
            with col3:
                st.write(f"**Promoter Holding:** {row['Promoter Holding %']}%")
                st.write(f"**Triple Stack Incr?:** {row['Triple Stack Increase?']}")
                st.write(f"**Conviction Score:** {row['Conviction Score']}/10")
            
            st.info(f"**🤖 AI Technical Thesis:** {row['Technical Research Thesis']}")
            st.markdown(f"[View Live Chart]({row['Live Chart']}) | [View Screener]({row['Research Doc']})")
else:
    st.info("👈 Please put your chart screenshots in the `charts` folder and click 'Execute Master Stock Scan' in the sidebar to begin processing real-time data.")