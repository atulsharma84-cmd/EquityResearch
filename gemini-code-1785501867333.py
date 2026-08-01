import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
from google import genai

# --- Configuration ---
SAVE_DIR = r"C:\Users\Suchit Sharma\Downloads\files"
os.makedirs(SAVE_DIR, exist_ok=True)

st.set_page_config(page_title="Institutional Equity Research Terminal", layout="wide")

st.title("🏦 Institutional Equity Research Engine")
st.caption("Comprehensive 5-Dimensional Fundamental, Management, Valuation, and Technical Analysis")

# --- Sidebar Inputs ---
st.sidebar.header("1. Target Company Setup")
company_name = st.sidebar.text_input("Company Symbol / Name", value="RELIANCE")

# Gemini API Key for Qualitative Analysis
gemini_api_key = st.sidebar.text_input("Gemini API Key (For Transcript & MD&A Analysis)", type="password")

st.sidebar.header("2. Data Ingestion")
uploaded_financials = st.sidebar.file_uploader("Upload Stock Data / Ratios (CSV/Excel)", type=["csv", "xlsx"])
mda_concall_text = st.sidebar.text_area("Paste Concall Transcript / MD&A Highlights", height=150, placeholder="Paste snippets from concall, shareholder pattern notes, or management disclosures...")

# Load Saved Files Dropdown
existing_files = [f for f in os.listdir(SAVE_DIR) if f.endswith(('.csv', '.xlsx'))]
selected_file = None

if uploaded_financials:
    local_path = os.path.join(SAVE_DIR, uploaded_financials.name)
    with open(local_path, "wb") as f:
        f.write(uploaded_financials.getbuffer())
    selected_file = local_path
elif existing_files:
    chosen_name = st.sidebar.selectbox("Or Pick Saved File", existing_files)
    selected_file = os.path.join(SAVE_DIR, chosen_name)

# --- Main Engine ---
if selected_file:
    try:
        # 1. Load Data
        df = pd.read_csv(selected_file) if selected_file.endswith('.csv') else pd.read_excel(selected_file)
        df.columns = [col.strip().lower() for col in df.columns]

        date_col = next((c for c in df.columns if 'date' in c), None)
        close_col = next((c for c in df.columns if 'close' in c or 'price' in c), None)
        vol_col = next((c for c in df.columns if 'volume' in c or 'vol' in c), None)

        if not date_col or not close_col:
            st.error("Uploaded file requires at least 'Date' and 'Close/Price' columns.")
            st.stop()

        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values(by=date_col)

        # 2. Compute Technicals
        df['EMA_20'] = df[close_col].ewm(span=20, adjust=False).mean()
        df['EMA_50'] = df[close_col].ewm(span=50, adjust=False).mean()
        df['EMA_200'] = df[close_col].ewm(span=200, adjust=False).mean()

        # Define Analysis Tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Technical Structure", 
            "📑 Fundamental Quality", 
            "🎙️ Management & Concall DNA", 
            "🏷️ Valuation Reality", 
            "⚡ Final Verdict Scorecard"
        ])

        # ---------------- TAB 1: TECHNICAL STRUCTURE ----------------
        with tab1:
            st.subheader(f"Technical Trend Analysis — {company_name}")
            
            # Identify Wyckoff / Trend Cycle
            latest_close = df[close_col].iloc[-1]
            ema_20 = df['EMA_20'].iloc[-1]
            ema_50 = df['EMA_50'].iloc[-1]
            ema_200 = df['EMA_200'].iloc[-1]

            if latest_close > ema_20 > ema_50 > ema_200:
                trend_phase = "MARKUP PHASE (Strong Uptrend)"
            elif latest_close < ema_20 < ema_50 < ema_200:
                trend_phase = "MARKDOWN PHASE (Downtrend)"
            elif abs(ema_20 - ema_50) / ema_50 < 0.02:
                trend_phase = "ACCUMULATION / DISTRIBUTION PHASE (Consolidation)"
            else:
                trend_phase = "TRANSITIONAL / MIXED PHASE"

            st.info(f"**Wyckoff Cycle Status:** {trend_phase}")

            # Plot Price & EMAs
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df[date_col], y=df[close_col], name="Close Price", line=dict(color="white", width=1)))
            fig.add_trace(go.Scatter(x=df[date_col], y=df['EMA_20'], name="20 EMA", line=dict(color="cyan")))
            fig.add_trace(go.Scatter(x=df[date_col], y=df['EMA_50'], name="50 EMA", line=dict(color="orange")))
            fig.add_trace(go.Scatter(x=df[date_col], y=df['EMA_200'], name="200 EMA", line=dict(color="magenta")))

            fig.update_layout(template="plotly_dark", xaxis_title="Date", yaxis_title="Price", hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

        # ---------------- TAB 2: FUNDAMENTAL QUALITY ----------------
        with tab2:
            st.subheader("Fundamental Integrity & Red Flag Check")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Current Price", f"₹{latest_close:.2f}")
            c2.metric("200 EMA Support", f"₹{ema_200:.2f}")
            c3.metric("20/50 EMA Spread", f"{(ema_20 - ema_50):.2f}")

            st.markdown("""
            ### Quality Scorecard Checklist
            * **Cash Flow Conversion:** Check if `Operating Cash Flow (CFO)` tracks `Net Profit (PAT)`. If PAT grows while CFO turns negative, flag aggressive revenue recognition.
            * **Debt & Capital:** Examine short-term vs. long-term borrowings. Rising debt alongside stagnant Asset Turnover indicates inefficient capex.
            * **DuPont ROE Decomposition:** Break down ROE into **Net Margin × Asset Turnover × Financial Leverage** to ensure ROE isn't boosted by excess debt.
            """)

        # ---------------- TAB 3: MANAGEMENT & CONCALL DNA ----------------
        with tab3:
            st.subheader("Qualitative Analysis (Concalls, MD&A, Shareholding)")
            
            if mda_concall_text and gemini_api_key:
                if st.button("Run AI Qualitative Analysis"):
                    with st.spinner("Analyzing management tone and disclosures..."):
                        client = genai.Client(api_key=gemini_api_key)
                        prompt = f"""
                        Act as a 20-year experienced equity research analyst. Analyze the following transcript/MD&A text for {company_name}:
                        
                        TEXT:
                        {mda_concall_text}

                        Tear this down across:
                        1. Management Tone (Confident vs Defensive)
                        2. Overpromising vs Execution Track Record
                        3. Red Flags (Promoter pledge, stake reductions, vague evasive answers)
                        """
                        response = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=prompt
                        )
                        st.markdown(response.text)
            else:
                st.warning("Enter a Gemini API Key in the sidebar and paste transcript text to trigger qualitative AI insights.")

        # ---------------- TAB 4: VALUATION REALITY ----------------
        with tab4:
            st.subheader("Valuation Framework")
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                pe_ratio = st.number_input("Current P/E Ratio", value=25.0)
                hist_pe = st.number_input("5-Year Historical Avg P/E", value=20.0)
            with col_v2:
                peer_pe = st.number_input("Sector Peer Avg P/E", value=22.0)
                earnings_growth = st.number_input("Expected PAT Growth (%)", value=15.0)

            peg = pe_ratio / earnings_growth if earnings_growth > 0 else 0
            st.metric("PEG Ratio", f"{peg:.2f}", delta="Favorable (< 1.0)" if peg < 1 else "Premium ( > 1.0)")

        # ---------------- TAB 5: FINAL VERDICT SCORECARD ----------------
        with tab5:
            st.subheader("Institutional Research Summary")
            
            v_col1, v_col2, v_col3 = st.columns(3)
            verdict = v_col1.selectbox("Final Call", ["BUY", "HOLD", "AVOID"])
            conviction = v_col2.slider("Conviction Score", 1, 10, 7)
            target_entry = v_col3.number_input("Margin of Safety Entry Price", value=float(latest_close * 0.9))

            one_liner = st.text_input("One-Line Investment Thesis Summary", value=f"Solid business momentum in {trend_phase}, wait for consolidation near support.")

            st.markdown("---")
            st.markdown(f"""
            ### 📋 Final Scorecard: {company_name}
            - **VERDICT:** `{verdict}`
            - **CONVICTION SCORE:** `{conviction} / 10`
            - **MARGIN OF SAFETY ENTRY:** `₹{target_entry:.2f}`
            - **THESIS SUMMARY:** *{one_liner}*
            """)

    except Exception as e:
        st.error(f"Error executing analysis pipeline: {e}")
else:
    st.info("Select or upload a stock file in the sidebar to run the analysis engine.")