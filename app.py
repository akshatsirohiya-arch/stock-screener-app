import pandas as pd
import streamlit as st

st.set_page_config(page_title="Stock Screener Dashboard", layout="wide")

@st.cache_data(ttl=300)
def load_data():
    try:
        return pd.read_parquet("latest_stocks.parquet")
    except Exception:
        return pd.DataFrame()

df = load_data()

st.title("⚡ Cloud Stock Screener & Filter Engine")

if df.empty:
    st.info("Cloud Agent is initializing data. Please refresh in a moment.")
else:
    st.caption(f"📅 Data Last Updated by Cloud Agent: {df['Last Updated'].iloc[0]}")

    st.sidebar.header("Filter Criteria")
    selected_industries = st.sidebar.multiselect("Industry", options=df["Industry"].unique())
    is_near_high = st.sidebar.selectbox("90% of 52W High?", ["All", "Yes", "No"])
    near_breakout = st.sidebar.selectbox("Near Breakout", ["All", "YES", "NO"])
    vol_spike = st.sidebar.selectbox("Volume Spike", ["All", "YES", "NO"])
    higher_150d = st.sidebar.selectbox("Price > 150D MA", ["All", "YES", "NO"])
    min_score = st.sidebar.slider("Min Breakout Score", 0, 3, 0)

    filtered = df.copy()
    if selected_industries:
        filtered = filtered[filtered["Industry"].isin(selected_industries)]
    if is_near_high != "All":
        filtered = filtered[filtered["90% of 52W High"] == is_near_high]
    if near_breakout != "All":
        filtered = filtered[filtered["Near Breakout"] == near_breakout]
    if vol_spike != "All":
        filtered = filtered[filtered["Volume Spike"] == vol_spike]
    if higher_150d != "All":
        filtered = filtered[filtered["Higher than 150D"] == higher_150d]

    filtered = filtered[filtered["Breakout Score"] >= min_score]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tracked", len(df))
    col2.metric("Matching Candidates", len(filtered))
    col3.metric("Top Signals (Score = 3)", len(df[df["Breakout Score"] == 3]))

    st.dataframe(filtered, use_container_width=True)
