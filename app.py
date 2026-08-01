import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Local Stock Analyzer", layout="wide")

st.title("📈 Stock Data & EMA Analyzer")
st.write("Upload your local stock data file (CSV or Excel) to analyze EMA trends.")

# --- File Upload Section ---
uploaded_file = st.sidebar.file_uploader("Upload Stock Report", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        # Load CSV or Excel
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        # Standardize column names
        df.columns = [col.strip().lower() for col in df.columns]

        # Ensure Date column exists and is parsed correctly
        date_col = next((col for col in df.columns if 'date' in col), None)
        close_col = next((col for col in df.columns if 'close' in col or 'price' in col), None)

        if not date_col or not close_col:
            st.error("Error: Could not identify 'Date' or 'Close/Price' columns in the uploaded report.")
        else:
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.sort_values(by=date_col)

            # --- Sidebar Controls ---
            st.sidebar.header("EMA Settings")
            short_ema_window = st.sidebar.slider("Short EMA Period", min_value=5, max_value=50, value=20)
            long_ema_window = st.sidebar.slider("Long EMA Period", min_value=20, max_value=200, value=50)

            # --- Calculate EMAs ---
            df[f'EMA_{short_ema_window}'] = df[close_col].ewm(span=short_ema_window, adjust=False).mean()
            df[f'EMA_{long_ema_window}'] = df[close_col].ewm(span=long_ema_window, adjust=False).mean()

            # Identify Crossover Signals (Bullish / Bearish)
            df['Signal'] = 0
            df.loc[df[f'EMA_{short_ema_window}'] > df[f'EMA_{long_ema_window}'], 'Signal'] = 1  # Bullish
            df['Crossover'] = df['Signal'].diff()

            # --- Interactive Chart ---
            st.subheader("Price Chart & EMAs")
            fig = go.Figure()

            # Price Line
            fig.add_trace(go.Scatter(x=df[date_col], y=df[close_col], mode='lines', name='Close Price', line=dict(color='gray', width=1)))

            # EMAs
            fig.add_trace(go.Scatter(x=df[date_col], y=df[f'EMA_{short_ema_window}'], mode='lines', name=f'EMA {short_ema_window}', line=dict(color='blue')))
            fig.add_trace(go.Scatter(x=df[date_col], y=df[f'EMA_{long_ema_window}'], mode='lines', name=f'EMA {long_ema_window}', line=dict(color='orange')))

            # Crossover Markers
            bullish_pts = df[df['Crossover'] == 1]
            bearish_pts = df[df['Crossover'] == -1]

            fig.add_trace(go.Scatter(x=bullish_pts[date_col], y=bullish_pts[close_col], mode='markers', name='Golden Cross (Buy)', marker=dict(color='green', size=10, symbol='triangle-up')))
            fig.add_trace(go.Scatter(x=bearish_pts[date_col], y=bearish_pts[close_col], mode='markers', name='Death Cross (Sell)', marker=dict(color='red', size=10, symbol='triangle-down')))

            fig.update_layout(xaxis_title="Date", yaxis_title="Price", hovermode="x unified", template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

            # --- Data Preview & Latest Values ---
            st.subheader("Recent Data & Signals")
            col1, col2, col3 = st.columns(3)
            latest_price = df[close_col].iloc[-1]
            latest_short_ema = df[f'EMA_{short_ema_window}'].iloc[-1]
            latest_long_ema = df[f'EMA_{long_ema_window}'].iloc[-1]

            col1.metric("Latest Close", f"{latest_price:.2f}")
            col2.metric(f"EMA {short_ema_window}", f"{latest_short_ema:.2f}")
            col3.metric(f"EMA {long_ema_window}", f"{latest_long_ema:.2f}")

            st.dataframe(df.tail(10))

    except Exception as e:
        st.error(f"Error processing file: {e}")
else:
    st.info("Please upload a CSV or Excel stock report using the sidebar to get started.")