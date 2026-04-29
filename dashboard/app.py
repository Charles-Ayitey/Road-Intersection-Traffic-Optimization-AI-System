import streamlit as st
import requests
import time
import plotly.graph_objects as go
from collections import deque
from datetime import datetime

st.set_page_config(
    page_title="AI Smart Traffic Dashboard",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_BASE = "http://localhost:8000"
HISTORY_LEN  = 60
STALE_THRESH = 5.0
QUEUE_ALERT  = 10

# ── Session state initialisation ──────────────────────────────
def _init_state():
    defaults = {
        "last_pushed_mode": "AI Controlled",
        "phase_start":   time.time(),
        "last_phase":    -1,
        "alert_log":     deque(maxlen=20),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── API helpers ───────────────────────────────────────────────
def get_data():
    try:
        r = requests.get(f"{API_BASE}/dashboard_data", timeout=0.5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None

def set_mode(mode: str):
    try:
        requests.post(f"{API_BASE}/set_mode", json={"mode": mode}, timeout=1.0)
    except Exception:
        pass

def set_phase(phase: int):
    try:
        requests.post(f"{API_BASE}/set_phase", json={"phase": phase}, timeout=1.0)
    except Exception:
        pass

def trigger_override(phase: int, duration: int):
    try:
        requests.post(f"{API_BASE}/trigger_override", json={"phase": phase, "duration": duration}, timeout=1.0)
    except Exception:
        pass

def check_api_health():
    try:
        requests.get(f"{API_BASE}/", timeout=0.3)
        return True
    except Exception:
        return False

def _log_alert(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state["alert_log"].appendleft(f"[{ts}]  {msg}")

# ── SIDEBAR: CONTROL PANEL ────────────────────────────────────
st.sidebar.title("🚦 Control Panel")
st.sidebar.markdown("Control traffic system parameters and modes")
st.sidebar.markdown("---")

MODES = ["AI Controlled", "Fixed Timing", "Manual Override"]
data_for_sidebar = get_data()
current_mode_index = MODES.index(data_for_sidebar["mode"]) if data_for_sidebar else 0

def on_mode_change():
    new_mode = st.session_state["mode_selector"]
    if new_mode != st.session_state["last_pushed_mode"]:
        set_mode(new_mode)
        _log_alert(f"Mode changed → {new_mode}")
        st.session_state["last_pushed_mode"] = new_mode

system_mode = st.sidebar.selectbox(
    "System Mode",
    MODES,
    index=current_mode_index,
    key="mode_selector",
    on_change=on_mode_change
)

st.sidebar.markdown("---")

# Manual control section
if system_mode == "Manual Override":
    st.sidebar.subheader("Manual Control")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("🟢 NS Green", use_container_width=True):
            set_phase(0)
            _log_alert("Manual override → NORTH-SOUTH Green")
    with col2:
        if st.button("🟢 EW Green", use_container_width=True):
            set_phase(2)
            _log_alert("Manual override → EAST-WEST Green")
    st.sidebar.markdown("---")

# Quick overrides
st.sidebar.subheader("Quick Overrides")
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("🚨 NS 15s", help="Force North-South for 15 seconds", use_container_width=True):
        trigger_override(0, 15)
        _log_alert("Quick Override → NS (15s)")
with col2:
    if st.button("🚨 EW 15s", help="Force East-West for 15 seconds", use_container_width=True):
        trigger_override(2, 15)
        _log_alert("Quick Override → EW (15s)")

st.sidebar.markdown("---")

# System health
st.sidebar.subheader("System Health")
api_alive    = check_api_health()
vision_stale = True
controller_ok = False

if data_for_sidebar:
    last_sync_s   = data_for_sidebar.get("last_vision_update", 0)
    vision_stale  = (time.time() - last_sync_s) > STALE_THRESH
    controller_ok = data_for_sidebar.get("system_status") == "Active"

def dot(ok): return "🟢" if ok else "🔴"

st.sidebar.markdown(
    f"**API / Data Bus:** {dot(api_alive)}  \n"
    f"**Vision Pipeline:** {dot(not vision_stale)}  \n"
    f"**AI Controller:** {dot(controller_ok)}"
)
st.sidebar.caption(f"API: {API_BASE}")

# ── MAIN VIEW: MONITORING DASHBOARD ───────────────────────────
st.markdown(
    f"<style>.block-container {{ max-width: 1400px; }}</style>",
    unsafe_allow_html=True
)

# Header
col_header1, col_header2 = st.columns([3, 1])
with col_header1:
    st.title("🚦 Smart Junction Monitor")
    st.markdown(f"**Mode:** {system_mode} | **Status:** {'🟢 Active' if controller_ok else '🔴 Inactive'}")
with col_header2:
    st.markdown("")
    st.markdown(f"<p style='text-align: right; font-size: 14px;'>Last update: {datetime.now().strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)

st.markdown("---")

# Fetch live data
data = get_data()

if data:
    counts    = data["counts"]
    phase     = data["current_phase"]
    last_sync = data.get("last_vision_update", 0)

    # Phase change detection
    if phase != st.session_state["last_phase"]:
        st.session_state["phase_start"] = time.time()
        st.session_state["last_phase"]  = phase
        label = "NORTH-SOUTH" if phase in [0, 1] else "EAST-WEST"
        _log_alert(f"Phase switched → {label} Green")

    phase_secs = int(time.time() - st.session_state["phase_start"])
    
    # ══════════════════════════════════════════════════════════
    # LEFT SIDE: PHASE STATUS & CONTROL
    # ══════════════════════════════════════════════════════════
    
    left_col, divider_col, right_col = st.columns([1, 0.05, 2])
    
    with left_col:
        st.subheader("Current Phase")
        st.markdown("###")  # Spacing
        
        if phase in [0, 1]:
            st.success("🟢 NORTH-SOUTH\n **GREEN**", icon="✓")
            st.error("🔴 EAST-WEST\n **RED**")
        else:
            st.error("🔴 NORTH-SOUTH\n **RED**")
            st.success("🟢 EAST-WEST\n **GREEN**", icon="✓")
        
        st.markdown("###")
        st.metric("Active Duration", f"{phase_secs}s", label_visibility="collapsed")
        
        active_override = data.get("active_override", {})
        if active_override.get("phase") is not None and active_override.get("expires_at", 0) > time.time():
            rem = int(active_override["expires_at"] - time.time())
            ovr_name = "NS" if active_override["phase"] == 0 else "EW"
            st.warning(f"🚨 Override active: {ovr_name} ({rem}s)")
        
        if (time.time() - last_sync) > STALE_THRESH:
            st.error("⚠️ Vision feed stale")
        elif last_sync > 0:
            sync_time = datetime.fromtimestamp(last_sync).strftime('%H:%M:%S')
            st.success(f"✓ Vision active\n({sync_time})")
    
    with divider_col:
        st.markdown(
            """
            <div style='
                border-left: 3px solid #ccc;
                height: 100%;
                display: flex;
                align-items: center;
            '></div>
            """,
            unsafe_allow_html=True
        )
    
    # ══════════════════════════════════════════════════════════
    # RIGHT SIDE: QUEUE METRICS & CHART
    # ══════════════════════════════════════════════════════════
    
    with right_col:
        st.subheader("Queue Status")
        
        # Queue metrics in 2x2 grid
        m1, m2 = st.columns(2)
        m3, m4 = st.columns(2)
        
        with m1:
            st.metric("North", counts["North"], delta="Alert" if counts["North"] >= QUEUE_ALERT else None, delta_color="off")
        with m2:
            st.metric("South", counts["South"], delta="Alert" if counts["South"] >= QUEUE_ALERT else None, delta_color="off")
        with m3:
            st.metric("East", counts["East"], delta="Alert" if counts["East"] >= QUEUE_ALERT else None, delta_color="off")
        with m4:
            st.metric("West", counts["West"], delta="Alert" if counts["West"] >= QUEUE_ALERT else None, delta_color="off")
        
        st.markdown("###")  # Spacing
        
        # Bar chart
        bar_fig = go.Figure(go.Bar(
            x=["North", "South", "East", "West"],
            y=[counts["North"], counts["South"], counts["East"], counts["West"]],
            marker_color=["#2196F3", "#4CAF50", "#FF9800", "#E91E63"],
            text=[counts["North"], counts["South"], counts["East"], counts["West"]],
            textposition="outside"
        ))
        bar_fig.add_hline(
            y=QUEUE_ALERT, line_dash="dash", line_color="red",
            annotation_text=f"Alert ({QUEUE_ALERT})", annotation_position="bottom right"
        )
        bar_fig.update_layout(
            xaxis_title="Approach",
            yaxis_title="Vehicles",
            margin=dict(l=20, r=20, t=20, b=20),
            height=300,
            showlegend=False,
            yaxis_range=[0, max(max(counts.values()) + 5, QUEUE_ALERT + 5)]
        )
        st.plotly_chart(bar_fig, use_container_width=True)
    
    # ══════════════════════════════════════════════════════════
    # EVENTS LOG
    # ══════════════════════════════════════════════════════════
    
    st.markdown("---")
    st.subheader("Activity Log")
    log_entries = list(st.session_state["alert_log"])
    if log_entries:
        for entry in log_entries:
            st.caption(entry)
    else:
        st.caption("_No events yet_")

else:
    st.error("⚠️ Unable to connect to API")
    st.info(f"Ensure the API server is running at {API_BASE}")

time.sleep(1)
st.rerun()
