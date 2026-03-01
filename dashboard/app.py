import streamlit as st
import pandas as pd
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="AI Smart Traffic Dashboard", layout="wide")

# API URL
API_URL = "http://localhost:8000/dashboard_data"

def get_data():
    try:
        response = requests.get(API_URL, timeout=0.1)
        if response.status_code == 200:
            return response.json()
    except Exception:
        return None
    return None

# Sidebar
st.sidebar.title("Smart Traffic Control")
st.sidebar.markdown("---")
system_mode = st.sidebar.selectbox("System Mode", ["AI Controlled", "Fixed Timing", "Manual Override"])
st.sidebar.info(f"Connected to Data Bus: {API_URL}")

# Main Header
st.title("🚦 Smart Junction Real-Time Monitor")
st.markdown("AI-Powered Adaptive Traffic Control System")

# Layout
col1, col2 = st.columns([1, 2])

# Placeholder for Data
status_box = st.empty()
counts_metric = st.columns(4)
chart_placeholder = st.empty()

# Real-time Update Loop
while True:
    data = get_data()
    
    if data:
        counts = data["counts"]
        phase = data["current_phase"]
        
        # 1. Update Metrics
        with counts_metric[0]:
            st.metric("North (Queue)", counts["North"])
        with counts_metric[1]:
            st.metric("South (Queue)", counts["South"])
        with counts_metric[2]:
            st.metric("East (Queue)", counts["East"])
        with counts_metric[3]:
            st.metric("West (Queue)", counts["West"])

        # 2. Visual Junction Status
        with col1:
            st.subheader("Junction Phase")
            if phase == 0:
                st.success("NORTH-SOUTH GREEN")
                st.error("EAST-WEST RED")
            else:
                st.error("NORTH-SOUTH RED")
                st.success("EAST-WEST GREEN")
            
            st.info(f"Last Vision Sync: {datetime.fromtimestamp(data['last_vision_update']).strftime('%H:%M:%S')}")

        # 3. Queue Chart
        with col2:
            st.subheader("Approach Congestion")
            df = pd.DataFrame({
                "Approach": ["North", "South", "East", "West"],
                "Vehicles": [counts["North"], counts["South"], counts["East"], counts["West"]]
            })
            st.bar_chart(df.set_index("Approach"))

    else:
        st.warning("⚠️ Waiting for Data Bus connection... (Ensure api/main.py is running)")

    time.sleep(1)
    st.rerun()