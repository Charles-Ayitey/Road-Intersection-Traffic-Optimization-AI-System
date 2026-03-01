# Development Log - Smart Traffic Junction System

This log records the chronological steps and technical actions taken during the development process.

---

### **Date: 2026-02-28**

#### **Step 1: Project Initialization & Environment Setup**
- **Action:** Analyzed `SmartTrafficSystem_DevelopmentPlan.docx`.
- **Action:** Created Python virtual environment (`.venv`).
- **Action:** Installed core dependencies (`ultralytics`, `opencv`, `stable-baselines3`, `traci`, etc.).

#### **Step 2: SUMO Integration (Phase 1)**
- **Action:** Verified SUMO installation and configured environment variables.
- **Action:** Generated 4-way junction model files in `simulation/`.
- **Outcome:** Successfully connected Python to SUMO via TraCI.

#### **Step 3: Computer Vision Pipeline (Phase 2)**
- **Action:** Developed `vision/detector.py` with YOLOv8n and `ZoneCounter`.
- **Action:** Verified spatial counting logic on `data/traffic_test.jpg` with 9 detections across ROI quadrants.
- **Outcome:** ROI logic confirmed; model successfully identifies and counts vehicles by location.

#### **Step 4: RL Environment Refinement (Phase 3)**
- **Action:** Updated `ai_agent/sumo_env.py` to handle realistic traffic light transitions.
  - Implemented **Yellow Phase** logic (3 seconds) to prevent abrupt light switches.
  - Set **Decision Interval** (`delta_time=5`) to allow traffic flow between agent actions.
- **Action:** Enhanced **Observation Space** to `[Queue_N, Queue_S, Queue_E, Queue_W, Current_Phase]`.
- **Action:** Refined **Reward Function** to `- (total_queues + 0.1 * total_waiting_time)`.
- **Outcome:** Environment is now more robust and provides a higher-quality training signal for the agent.

#### **Step 5: Cloud Training Preparation (Phase 3)**
- **Action:** Created `ai_agent/SmartTraffic_Training.ipynb` with automated SUMO/dependency installation for Google Colab.
- **Action:** Generated `traffic_project.zip` containing `ai_agent/` and `simulation/` for cloud upload.
- **Outcome:** Training pipeline is ready for GPU acceleration in the browser.

---

### **Date: 2026-03-01**

#### **Step 6: Full Codebase Audit & Bug Fixes**
- **Action:** Performed a complete codebase review across all 17 source files.
- **Findings:** Identified 7 defects and design gaps spanning model loading, error handling, operating modes, the dashboard, model versioning, and traffic realism.
- **Fixes applied (see `CHANGES.md` for full detail):**
  - `ai_agent/live_controller.py` — replaced hardcoded model path with a prioritised `MODEL_SEARCH_PATHS` fallback list; replaced `except: pass` blocks with `logging`-based warnings.
  - `api/main.py` — added `mode` and `manual_phase` state fields; added `POST /set_mode` and `POST /set_phase` endpoints.
  - `dashboard/app.py` — wired mode selector to API via `on_change` callback; added manual phase buttons; replaced deprecated `st.bar_chart` with Plotly `go.Bar`; added stale-feed warning banner.
  - `ai_agent/train.py` — dual saves on every run: timestamped archive copy + rolling `ppo_traffic_agent.zip` latest.
  - `vision/detector.py` — proper `requests.RequestException` handling; consistent `logging` module usage.
  - `simulation/junction.rou.xml` — rewrote uniform 300 veh/hr flows as 5-period time-varying profile (off-peak → morning rush → midday → evening rush → wind-down) with directional imbalance.
- **New file:** `CHANGES.md` — plain-language documentation of all six fix categories.
- **Outcome:** All 7 issues resolved; no Pylance errors on any modified file.

#### **Step 7: Mode Flickering Hotfix**
- **Problem observed:** Live run output showed mode oscillating between "AI Controlled" and "Fixed Timing" on every other step (steps 76–100) because Streamlit re-renders the entire page every second, causing the mode selector to re-push its value to the API on each cycle.
- **Fix:** Dashboard mode selector now uses a `st.selectbox(on_change=...)` callback pattern combined with a `session_state["last_pushed_mode"]` guard; the API call fires only when the value actually changes, not on every rerender.
- **File changed:** `dashboard/app.py`

#### **Step 8: Multi-Video Training Pipeline**
- **Action:** Extended `vision/detector.py` with `_discover_videos()` — auto-scans the `data/` directory for `.mp4 .avi .mov .mkv .webm` files and builds a playlist. On video EOF the detector advances to the next clip automatically.
- **Action:** Extended `ai_agent/sumo_env.py` with `randomise_demand` parameter and `_generate_random_routes()` method. When enabled, each training episode overwrites `junction.rou.xml` with fresh random flows (50–900 veh/hr per direction), preventing the agent from memorising a fixed schedule. Added `sumocfg_path.replace("\\", "/")` for cross-platform path safety.
- **Action:** Updated `ai_agent/train.py` to pass `randomise_demand=True` to the training environment.
- **Outcome:** Agent is now exposed to a far wider distribution of traffic conditions every run.

#### **Step 9: Google Colab Training Package**
- **Action:** Created `colab_train.py` — a self-contained training script designed to run on Google Colab's GPU runtime. Contains an inline `SumoTrafficEnv` class (no local imports required), hardcoded Ubuntu SUMO paths (`/usr/share/sumo`), domain randomisation ON for training and OFF for evaluation, `EvalCallback` saving the best checkpoint every 25 k steps, 300 k total training steps, final output as `ppo_traffic_agent_refined.zip`.
- **Action:** Created `pack_for_colab.py` — builds `traffic_project.zip` from simulation configs, `data/` media files, and `colab_train.py`. Uses `to_zip_path()` to convert Windows backslashes to forward slashes so paths resolve correctly on Ubuntu.
- **Action:** Ran `pack_for_colab.py` after user added 34 Ghanaian traffic videos to `data/`. Produced `traffic_project.zip` containing 44 files (~80 MB).
- **Outcome:** Zip confirmed complete; uploaded to Colab for GPU training.

#### **Step 10: New Trained Model Integration (`ppo_traffic_agent_refined_2.zip`)**
- **Action:** User returned from Colab with `models/ppo_traffic_agent_refined_2.zip` (second training iteration).
- **Action:** Updated `MODEL_SEARCH_PATHS` in `ai_agent/live_controller.py` — new model inserted as index 0 (highest priority); previous model entries remain as fallbacks:
  ```
  1. models/ppo_traffic_agent_refined_2.zip  ← new
  2. models/ppo_traffic_agent_refined.zip
  3. models/ppo_traffic_agent.zip
  ```

#### **Step 11: Production-Grade Dashboard Rewrite**
- **Motivation:** Original dashboard lacked real-time health monitoring, trend history, alerting, and event logging — insufficient for a real deployment.
- **Full rewrite of `dashboard/app.py`** adding:
  - **Constants:** `HISTORY_LEN=60` (seconds of rolling history), `STALE_THRESH=5.0` s, `QUEUE_ALERT=10` vehicles.
  - **Session state management:** `_init_state()` initialises `session_state` with per-direction `deque` history buffers, `timestamps`, `alert_log`, and `phase_start` / `last_phase` trackers.
  - **System health panel (sidebar):** Independent 🟢/🔴 liveness indicators for API server, Vision Pipeline, and AI Controller. Uses a dedicated `check_api_health()` probe.
  - **6-column KPI strip:** Live N / S / E / W queue counts + Total Vehicles + Phase Active timer (seconds since last phase change).
  - **Bar chart with alert line:** Plotly `go.Bar` with a dashed red threshold line at `QUEUE_ALERT`.
  - **60-second history trend:** Plotly `go.Scatter` for all four directions, updates every cycle.
  - **Event log:** `deque(maxlen=20)` captures phase switches, mode changes, and high-queue alerts with timestamps.
  - **Mode selector fix retained:** `on_change` callback + `last_pushed_mode` guard (from Step 7) carried over into the rewrite.
- **Outcome:** No Pylance errors; dashboard is suitable for operational monitoring.

---

*Log will be updated after every significant technical step.*
