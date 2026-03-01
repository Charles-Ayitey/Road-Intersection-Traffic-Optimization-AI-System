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
HISTORY_LEN  = 60   # data points kept per direction (~60 seconds)
STALE_THRESH = 5.0  # seconds before vision is considered stale
QUEUE_ALERT  = 10   # vehicles — threshold for a high-queue alert

# ── Session state initialisation ──────────────────────────────
def _init_state():
    defaults = {
        "last_pushed_mode": "AI Controlled",
        "history": {d: deque([0] * HISTORY_LEN, maxlen=HISTORY_LEN) for d in ["North", "South", "East", "West"]},
        "timestamps":    deque(maxlen=HISTORY_LEN),
        "alert_log":     deque(maxlen=20),
        "phase_start":   time.time(),
        "last_phase":    -1,
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

def check_api_health():
    try:
        requests.get(f"{API_BASE}/", timeout=0.3)
        return True
    except Exception:
        return False

def _log_alert(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state["alert_log"].appendleft(f"[{ts}]  {msg}")

# ── Sidebar ───────────────────────────────────────────────────
st.sidebar.title("🚦 Smart Traffic Control")
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
    "System Mode", MODES,
    index=current_mode_index,
    key="mode_selector",
    on_change=on_mode_change
)

if system_mode == "Manual Override":
    st.sidebar.markdown("---")
    st.sidebar.subheader("Manual Phase Control")
    if st.sidebar.button("🟢 Set NORTH-SOUTH Green", use_container_width=True):
        set_phase(0)
        _log_alert("Manual override → NORTH-SOUTH Green")
    if st.sidebar.button("🟢 Set EAST-WEST Green", use_container_width=True):
        set_phase(2)
        _log_alert("Manual override → EAST-WEST Green")

st.sidebar.markdown("---")

# System health in sidebar
st.sidebar.markdown("### System Health")
api_alive    = check_api_health()
vision_stale = True
controller_ok = False

if data_for_sidebar:
    last_sync_s   = data_for_sidebar.get("last_vision_update", 0)
    vision_stale  = (time.time() - last_sync_s) > STALE_THRESH
    controller_ok = data_for_sidebar.get("system_status") == "Active"

def dot(ok): return "🟢" if ok else "🔴"

st.sidebar.markdown(
    f"{dot(api_alive)} **API / Data Bus**  \n"
    f"{dot(not vision_stale)} **Vision Pipeline**  \n"
    f"{dot(controller_ok)} **AI Controller**"
)
st.sidebar.caption(f"`{API_BASE}`")

# ── Main header ───────────────────────────────────────────────
st.title("Smart Junction Real-Time Monitor")
st.markdown(
    f"AI-Powered Adaptive Traffic Control  |  **Mode: {system_mode}**  |  "
    f"{'🟢 System Active' if controller_ok else '🔴 System Inactive'}"
)
st.markdown("---")

# ── Fetch live data & update history ─────────────────────────
data = get_data()

if data:
    counts    = data["counts"]
    phase     = data["current_phase"]
    last_sync = data.get("last_vision_update", 0)

    # Update rolling history
    st.session_state["timestamps"].append(datetime.now().strftime("%H:%M:%S"))
    for d in ["North", "South", "East", "West"]:
        st.session_state["history"][d].append(counts[d])

    # Phase change detection
    if phase != st.session_state["last_phase"]:
        st.session_state["phase_start"] = time.time()
        st.session_state["last_phase"]  = phase
        label = "NORTH-SOUTH" if phase in [0, 1] else "EAST-WEST"
        _log_alert(f"Phase switched → {label} Green")

    # High-queue alerts
    for d, v in counts.items():
        if v >= QUEUE_ALERT:
            _log_alert(f"⚠ High queue on {d}: {v} vehicles")

    phase_secs = int(time.time() - st.session_state["phase_start"])

    # ── Row 1: KPI strip ──────────────────────────────────────
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    total_q = sum(counts.values())
    with k1: st.metric("North Queue",     counts["North"])
    with k2: st.metric("South Queue",     counts["South"])
    with k3: st.metric("East Queue",      counts["East"])
    with k4: st.metric("West Queue",      counts["West"])
    with k5: st.metric("Total Vehicles",  total_q)
    with k6: st.metric("Phase Active",    f"{phase_secs}s")

    st.markdown("---")

    # ── Row 2: Phase status | Bar chart ───────────────────────
    col_phase, col_bar = st.columns([1, 2])

    with col_phase:
        st.subheader("Junction Phase")
        if phase in [0, 1]:
            st.success("🟢 NORTH-SOUTH GREEN")
            st.error("🔴 EAST-WEST RED")
            phase_name = "NORTH-SOUTH"
        else:
            st.error("🔴 NORTH-SOUTH RED")
            st.success("🟢 EAST-WEST GREEN")
            phase_name = "EAST-WEST"

        st.info(f"Active for **{phase_secs}s** ({phase_name})")

        if last_sync > 0:
            st.caption(f"Last vision sync: {datetime.fromtimestamp(last_sync).strftime('%H:%M:%S')}")
        if (time.time() - last_sync) > STALE_THRESH:
            st.warning("⚠ Vision feed stale (>5 s)")

    with col_bar:
        st.subheader("Current Queue Lengths")
        bar_fig = go.Figure(go.Bar(
            x=["North", "South", "East", "West"],
            y=[counts["North"], counts["South"], counts["East"], counts["West"]],
            marker_color=["#2196F3", "#4CAF50", "#FF9800", "#E91E63"],
            text=[counts["North"], counts["South"], counts["East"], counts["West"]],
            textposition="outside"
        ))
        bar_fig.add_hline(
            y=QUEUE_ALERT, line_dash="dash", line_color="red",
            annotation_text="Alert threshold", annotation_position="bottom right"
        )
        bar_fig.update_layout(
            xaxis_title="Approach", yaxis_title="Vehicles",
            margin=dict(l=10, r=10, t=10, b=10), height=280,
            yaxis_range=[0, max(max(counts.values()) + 5, QUEUE_ALERT + 5)]
        )
        st.plotly_chart(bar_fig, use_container_width=True)

    st.markdown("---")

    # ── Row 3: Historical trend ────────────────────────────────
    st.subheader("Queue History (last 60 s)")
    hist = st.session_state["history"]
    ts   = list(st.session_state["timestamps"])
    while len(ts) < HISTORY_LEN:
        ts.insert(0, "")

    trend_fig = go.Figure()
    colors = {"North": "#2196F3", "South": "#4CAF50", "East": "#FF9800", "West": "#E91E63"}
    for d, col in colors.items():
        trend_fig.add_trace(go.Scatter(
            x=ts, y=list(hist[d]),
            mode="lines", name=d, line=dict(color=col, width=2)
        ))
    trend_fig.add_hline(y=QUEUE_ALERT, line_dash="dash", line_color="red", line_width=1)
    trend_fig.update_layout(
        xaxis_title="Time", yaxis_title="Vehicles",
        margin=dict(l=10, r=10, t=10, b=10), height=220,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(showticklabels=False)
    )
    st.plotly_chart(trend_fig, use_container_width=True)

    st.markdown("---")

    # ── Row 4: Event log ──────────────────────────────────────
    st.subheader("Event Log")
    log_entries = list(st.session_state["alert_log"])
    if log_entries:
        for entry in log_entries:
            st.caption(entry)
    else:
        st.caption("No events yet.")

else:
    st.warning("⚠ Waiting for Data Bus connection... (Ensure api/main.py is running)")

time.sleep(1)
st.rerun()

API_BASE = "http://localhost:8000"

def get_data():
    try:
        r = requests.get(f"{API_BASE}/dashboard_data", timeout=0.5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
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

# ── Sidebar ───────────────────────────────────────────────────────────
st.sidebar.title("Smart Traffic Control")
st.sidebar.markdown("---")

MODES = ["AI Controlled", "Fixed Timing", "Manual Override"]
data_for_sidebar = get_data()
current_mode_index = MODES.index(data_for_sidebar["mode"]) if data_for_sidebar else 0

# Use session_state so the selectbox is the source of truth for user input.
# Only push to the API when the user actually changes the selector.
if "last_pushed_mode" not in st.session_state:
    st.session_state["last_pushed_mode"] = MODES[current_mode_index]

def on_mode_change():
    new_mode = st.session_state["mode_selector"]
    if new_mode != st.session_state["last_pushed_mode"]:
        set_mode(new_mode)
        st.session_state["last_pushed_mode"] = new_mode

system_mode = st.sidebar.selectbox(
    "System Mode",
    MODES,
    index=current_mode_index,
    key="mode_selector",
    on_change=on_mode_change
)

st.sidebar.info(f"Data Bus: {API_BASE}")

if system_mode == "Manual Override":
    st.sidebar.markdown("---")
    st.sidebar.subheader("Manual Phase Control")
    if st.sidebar.button("Set NORTH-SOUTH Green"):
        set_phase(0)
    if st.sidebar.button("Set EAST-WEST Green"):
        set_phase(2)

# ── Main Page ──────────────────────────────────────────────────────────
st.title("Smart Junction Real-Time Monitor")
st.markdown(f"AI-Powered Adaptive Traffic Control System  |  **Mode: {system_mode}**")

counts_cols = st.columns(4)
col_phase, col_chart = st.columns([1, 2])

# ── Live data ──────────────────────────────────────────────────────────
data = get_data()

if data:
    counts = data["counts"]
    phase  = data["current_phase"]

    for col, direction in zip(counts_cols, ["North", "South", "East", "West"]):
        col.metric(f"{direction} Queue", counts[direction])

    with col_phase:
        st.subheader("Junction Phase")
        if phase in [0, 1]:
            st.success("NORTH-SOUTH GREEN")
            st.error("EAST-WEST RED")
        else:
            st.error("NORTH-SOUTH RED")
            st.success("EAST-WEST GREEN")

        last_sync = data["last_vision_update"]
        if last_sync > 0:
            st.info(f"Last Vision Sync: {datetime.fromtimestamp(last_sync).strftime('%H:%M:%S')}")
        else:
            st.warning("No vision data yet.")

        if (time.time() - last_sync) > 5.0:
            st.warning("Vision feed is stale (>5 s).")

    with col_chart:
        st.subheader("Approach Congestion")
        fig = go.Figure(go.Bar(
            x=["North", "South", "East", "West"],
            y=[counts["North"], counts["South"], counts["East"], counts["West"]],
            marker_color=["#2196F3", "#4CAF50", "#FF9800", "#E91E63"]
        ))
        fig.update_layout(
            xaxis_title="Approach",
            yaxis_title="Vehicles",
            margin=dict(l=20, r=20, t=20, b=20),
            height=300
        )
        # use_container_width replaced with width param (Streamlit ≥ 2026)
        st.plotly_chart(fig, use_container_width=True)

else:
    st.warning("Waiting for Data Bus connection... (Ensure api/main.py is running)")

time.sleep(1)
st.rerun()