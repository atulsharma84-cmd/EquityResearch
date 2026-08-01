import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os

# --- Define Your Local Save Directory ---
SAVE_DIR = r"C:\Users\Suchit Sharma\Downloads\files"
os.makedirs(SAVE_DIR, exist_ok=True)

st.set_page_config(page_title="Local Stock Analyzer", layout="wide")

st.title("📈 Stock Data & EMA Analyzer")
st.write("Analyze local stock reports (CSV or Excel) and compute EMA crossovers.")

# --- Sidebar File Management ---
st.sidebar.header("📁 File Selection")

# 1. Option to upload a new file
uploaded_file = st.sidebar.file_uploader("Upload New Stock Report", type=["csv", "xlsx"])

if uploaded_file is not None:
    # Save uploaded file locally
    local_filepath = os.path.join(SAVE_DIR, uploaded_file.name)
    with open(local_filepath, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success(f"Saved: `{uploaded_file.name}`")

# 2. Get list of all CSV and Excel files in the directory
existing_files = [f for f in os.listdir(SAVE_DIR) if f.endswith(('.csv', '.xlsx'))]

selected_file = None
if existing_files:
    # Dropdown menu to pick from saved files
    selected_file_name = st.sidebar.selectbox(
        "Select Saved Stock Report",
        options=existing_files,
        index=existing_files.index(uploaded_file.name) if uploaded_file and uploaded_file.name in existing_files else 0
    )
    selected_file = os.path.join(SAVE_DIR, selected_file_name)
else:
    st.info("No saved stock files found in the directory. Please upload a CSV or Excel file to get started.")

# --- Main Analysis Section ---
if selected_file is not None:
    try:
        # Load CSV or Excel from the selected path
        if selected_file.endswith('.csv'):
            df = pd.read_csv(selected_file)
        else:
            df = pd.read_excel(selected_file)

        # Standardize column names
        df.columns = [col.strip().lower() for col in df.columns]

        # Identify key columns dynamically
        date_col = next((col for col in df.columns if 'date' in col), None)
        close_col = next((col for col in df.columns if 'close' in col or 'price' in col), None)

        if not date_col or not close_col:
            st.error("Error: Could not identify 'Date' or 'Close/Price' columns in the selected file.")
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

            # Identify Crossover Signals
            df['Signal'] = 0
            df.loc[df[f'EMA_{short_ema_window}'] > df[f'EMA_{long_ema_window}'], 'Signal'] = 1  # Bullish
            df['Crossover'] = df['Signal'].diff()

            # --- Interactive Chart ---
            st.subheader(f"Price Chart & EMAs (`{os.path.basename(selected_file)}`)")
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

            # --- Summary Metrics ---
            st.subheader("Recent Data & Signals")
            col1, col2, col3 = st.columns(3)
            latest_price = df[close_col].iloc[-1]
            latest_short_ema = df[f'EMA_{short_ema_window}'].iloc[-1]
            latest_long_ema = df[f'EMA_{long_ema_window}'].iloc[-1]

            col1.metric("Latest Close", f"{latest_price:.2f}")
            col2.metric(f"EMA {short_ema_window}", f"{latest_short_ema:.2f}")
            col3.metric(f"EMA {long_ema_window}", f"{latest_long_ema:.2f}")

            st.dataframe(df.tail(10))

            # --- Signal Export Section ---
            st.subheader("📥 Export Crossover Signals")
            signals_df = df[df['Crossover'].isin([1, -1])].copy()
            
            if not signals_df.empty:
                signals_df['Signal_Type'] = signals_df['Crossover'].map({1: 'BUY (Golden Cross)', -1: 'SELL (Death Cross)'})
                export_cols = [date_col, close_col, f'EMA_{short_ema_window}', f'EMA_{long_ema_window}', 'Signal_Type']
                signals_export = signals_df[export_cols]

                st.dataframe(signals_export, use_container_width=True)

                csv_data = signals_export.to_csv(index=False).encode('utf-8')

                st.download_button(
                    label="Download Crossover Signals CSV",
                    data=csv_data,
                    file_name="stock_ema_crossover_signals.csv",
                    mime="text/csv"
                )
            else:
                st.info("No EMA crossovers detected in the dataset with current parameters.")

    except Exception as e:
        st.error(f"Error reading file `{os.path.basename(selected_file)}`: {e}")