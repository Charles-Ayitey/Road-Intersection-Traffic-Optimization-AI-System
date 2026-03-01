import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import plotly.express as px

st.set_page_config(page_title="AI Smart Traffic", layout="wide")

# API URL
API_URL = "http://localhost:8000/dashboard_data"

def get_data():
    try:
        response = requests.get(API_URL, timeout=0.1)
        if response.status_code == 200:
            return response.json()
    except Exception: return None
    return None

# --- SESSION STATE ---
if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=['Time', 'Total Queue', 'Timestamp'])
if 'last_api_reset' not in st.session_state:
    st.session_state.last_api_reset = 0.0

# --- SIDEBAR (Static) ---
st.sidebar.title("🛠️ Settings")
refresh_rate = st.sidebar.slider("Update Speed (s)", 0.5, 5.0, 1.0)
st.sidebar.markdown("---")
if st.sidebar.button("Manual Clear History"):
    st.session_state.history = pd.DataFrame(columns=['Time', 'Total Queue', 'Timestamp'])

# --- HEADER (Static) ---
st.title("🚦 AI Smart Traffic Command Center")
st.markdown("---")

# --- CONTAINERS (Static) ---
col1, col2 = st.columns([1, 1.5])
with col1:
    st.subheader("📍 Junction View")
    junction_ui = st.empty()
with col2:
    st.subheader("📈 Congestion Trend (Interactive Zoom)")
    chart_ui = st.empty()

# --- REFRESH LOOP ---
while True:
    data = get_data()
    
    if data:
        # AUTO-RESET CHECK: If API was reset, clear local history
        # (API last_vision_update will be 0 after reset)
        if data["last_vision_update"] < st.session_state.last_api_reset:
            st.session_state.history = pd.DataFrame(columns=['Time', 'Total Queue', 'Timestamp'])
        st.session_state.last_api_reset = data["last_vision_update"]

        counts = data["counts"]
        phase_id = data["current_phase"]
        total_q = sum(counts.values())
        
        # 1. Update Plot Data
        new_row = {
            'Time': datetime.now().strftime('%H:%M:%S'), 
            'Total Queue': total_q,
            'Timestamp': time.time()
        }
        st.session_state.history = pd.concat([st.session_state.history, pd.DataFrame([new_row])], ignore_index=True)
        if len(st.session_state.history) > 100: 
            st.session_state.history = st.session_state.history.iloc[1:]

        # 2. Render Junction (Optimized HTML)
        ns_light = "🔴"
        ew_light = "🔴"
        if phase_id == 0: ns_light, ew_light = "🟢", "🔴"
        elif phase_id == 1: ns_light, ew_light = "🟡", "🔴"
        elif phase_id == 2: ns_light, ew_light = "🔴", "🟢"
        elif phase_id == 3: ns_light, ew_light = "🔴", "🟡"

        junction_html = f"""
        <div style="background:#111; padding:20px; border-radius:15px; border:2px solid #333; text-align:center; color:white;">
            <div style="margin-bottom:15px;"><b>North: {counts['North']}</b><br><span style="font-size:40px">{ns_light}</span></div>
            <div style="display:flex; justify-content:space-around; align-items:center;">
                <div><b>West: {counts['West']}</b><br><span style="font-size:40px">{ew_light}</span></div>
                <div style="font-size:30px">🇬🇭</div>
                <div><b>East: {counts['East']}</b><br><span style="font-size:40px">{ew_light}</span></div>
            </div>
            <div style="margin-top:15px;"><span style="font-size:40px">{ns_light}</span><br><b>South: {counts['South']}</b></div>
        </div>
        """
        junction_ui.markdown(junction_html, unsafe_allow_html=True)

        # 3. Render Chart (FLICKER FREE WITH ZOOM PERSISTENCE)
        fig = px.line(st.session_state.history, x='Time', y='Total Queue', template="plotly_dark", height=450)
        
        # CRITICAL: uirevision ensures zoom and pan stay even when data is updated
        fig.update_layout(
            uirevision='constant_string', 
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#333")
        )
        fig.update_traces(line_color='#4F8BF9', line_width=3)
        
        chart_ui.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})

    else:
        junction_ui.warning("Waiting for Data Bus Connection...")

    time.sleep(refresh_rate)
