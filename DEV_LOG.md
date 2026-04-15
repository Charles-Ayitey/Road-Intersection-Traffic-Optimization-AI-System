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

---

### **Date: 2026-04-15**

#### **Step 7: Local Database Persistence**
- **Action:** Added `sqlite3` integration to `api/main.py` so that traffic states (queues, mode, phase) are saved instead of being kept only in volatile memory.
- **Action:** Created the `live_traffic_log` table inside `data/traffic_history.db`, which logs incoming `VisionUpdate` payloads.
- **Outcome:** The system is now capable of persisting historical simulation data for potential offline reinforcement learning or time-series analytics.
- **Action:** Fixed `launch_system.py` swallowing crash logs and updated `config.json`'s `active_scenario` to ensure video loops successfully processed simulated dataset videos.
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

### **Date: 2026-03-05**

#### **Step 12: Additional Model Integrations**
- **Action:** User returned from further Colab runs with `best_model.zip` and `best_model_2.zip` (best-checkpoint saves from the EvalCallback, outperforming the final-step saves).
- **Action:** Updated `MODEL_SEARCH_PATHS` in `ai_agent/live_controller.py` — `best_model_2.zip` placed at index 0, `best_model.zip` at index 2. Full search order:
  ```
  1. models/best_model_2.zip          ← best eval checkpoint, latest run
  2. models/ppo_traffic_agent_refined_4.zip
  3. models/best_model.zip
  4. models/ppo_traffic_agent_refined_3.zip
  5. models/ppo_traffic_agent_refined_2.zip
  6. models/ppo_traffic_agent_refined.zip
  7. models/ppo_traffic_agent.zip
  ```

#### **Step 13: `compute_pressure()` NoneType Fix**
- **Problem observed:** Every live step produced `TypeError: '>' not supported between instances of 'NoneType' and 'NoneType'` from `ai_agent/max_pressure.py`.
- **Root cause:** `compute_pressure()` contained a `try/except` block that returned `None` on success (missing explicit `return` statement). `should_override()` then called `max()` on a dict of `None` values.
- **Fix:** Added `return float(inbound - outbound)` at the end of the function; added `int(traci.lane.getLastStepHaltingNumber(l) or 0)` guard to each lane call; widened `except` from bare to `except Exception`.
- **File changed:** `ai_agent/max_pressure.py`

#### **Step 14: Step 2 — Upstream Induction Loop Detectors**
- **Action:** Created `simulation/junction.add.xml` with four E1 induction loops (`det_n`, `det_s`, `det_e`, `det_w`) placed at pos=33 (~60 m upstream of the stop line on each inbound lane), `freq="5"`.
- **Action:** Updated `simulation/junction.sumocfg` to load the additionals file via `<additional-files value="junction.add.xml"/>`.
- **Action:** Updated `ai_agent/sumo_env.py`:
  - Added `_write_add_xml()` — regenerates `junction.add.xml` at runtime with OS-correct null device (`/dev/null` vs `NUL`).
  - Added `self.detector_ids = ["det_n", "det_s", "det_e", "det_w"]`.
  - Expanded observation space from 5 to **9 elements**: `[Q_N, Q_S, Q_E, Q_W, Occ_N, Occ_S, Occ_E, Occ_W, phase]`.
  - `_get_obs()` now reads loop occupancy via `traci.inductionloop.getLastStepOccupancy()`.
- **Action:** Synced all changes into `ai_agent/colab_train.py`.
- **Outcome:** Agent receives upstream approach-saturation data that arrives before vehicles reach the stop line, giving it early warning of building queues.

#### **Step 15: Step 3 — Dynamic Phase Duration**
- **Action:** Changed `action_space` from `spaces.Discrete(2)` to `spaces.MultiDiscrete([2, 3])`.
  - `action[0]` = phase direction (0 = NS, 1 = EW)
  - `action[1]` = duration level (0 = 5 s, 1 = 15 s, 2 = 30 s) — mapped via `_DURATION_STEPS = [1, 3, 6]` simulation steps at `delta_time=5`.
- **Action:** Updated `ai_agent/live_controller.py`:
  - Decodes `dur_idx = int(action[1])` and logs `dur_label = ["5s", "15s", "30s"][dur_idx]` on every step.
  - Phase is now posted to the API **before** `env.step()` so the dashboard displays the chosen phase for the entire green duration, not just during the yellow transition.
  - `post_phase_to_api()` skips posting during yellow phases (1, 3) to avoid misleading the dashboard.
  - Request timeout raised from 0.1 s to 0.5 s.
- **Action:** Added `logging.basicConfig(..., force=True)` to prevent duplicate log lines when the logger is initialised twice (by `live_controller.py` and by `launch_system.py`).
- **Action:** Synced all changes into `ai_agent/colab_train.py`.
- **Outcome:** Agent can now hold a green for 5, 15, or 30 seconds rather than always using a fixed 30-second cycle.

#### **Step 16: Live Run Diagnostics — 5-Issue Batch Fix**
User ran 116-step live session and identified five issues:

**16a — EW Camera Zone Geometry**
- **Problem:** `config.json` `traffic_test` scenario had four quadrant zones all mapped to either `North` or `South`. East and West zones were structurally absent.
- **Fix:** Replaced the four quadrant polygons with four arm-shaped polygons aligned with the N/S/E/W approach lanes.

**16b — Dashboard Always Showing NS Green**
- **Problem (1):** An entire duplicate copy of `dashboard/app.py` had been appended to the end of the file by a previous edit operation. The duplicate contained different phase-display logic that was overwriting the correct implementation.
- **Problem (2):** Phase was posted to the API only during the 1.7 s yellow transition; the dashboard polled every 1 s and almost always missed EW phases.
- **Fix:** Removed the duplicate code block; moved phase posting to before `env.step()` (Step 15 above).

**16c — South Lane Congestion Bias**
- **Problem:** Reward treated cleared vehicles equally regardless of which lane was most congested, giving no extra credit for relieving the worst-affected approach.
- **Fix:** Per-lane clearing weight: `cleared_i × (1 + queue_before_i / max_queue_before)`. Lanes that were more congested at the start of the green phase contribute more to the reward than lightly-loaded lanes.

**16d — Missing / Duplicate Log Steps**
- **Problem:** Steps 112–113 appeared three times in the log. `logging.basicConfig` was called twice (once in `live_controller.py`, once implicitly via `launch_system.py`), creating two handlers and doubling (or tripling) output.
- **Fix:** Added `force=True` to `logging.basicConfig()` in `live_controller.py` (see Step 15).

**16e — Reward Volatility (swings of −10 to +26)**
- **Problem:** On 30-second green phases, `outbound_flow` accumulated vehicle counts across all 6 simulation steps. This inflated the outbound contribution by up to 6×, causing reward spikes on long phases.
- **Fix:** Normalised outbound flow: `outbound_flow / chunks` where `chunks = duration_steps / delta_time`. The outbound reward now represents average throughput per step rather than a raw total.
- **Files changed:** `ai_agent/sumo_env.py`, `ai_agent/colab_train.py`

#### **Step 17: Video Playlist Architecture — `video_list` Allowlist**
- **Problem identified:** The 34 Ghanaian training videos in `data/` are street-level footage unsuitable for top-down zone polygon counting. The auto-discover playlist exposed these files to the vision pipeline, producing zero or garbage counts for all arms.
- **Action:** Added `video_list` field to scenario configs in `config.json`. When present, `_discover_videos()` builds the playlist exclusively from the listed files instead of auto-scanning `data/`.
  - Priority chain: `scenario.video_list` → auto-discover `data/` → `config.source` fallback.
- **Action:** Set `video_list` in `traffic_test` to the five overhead-compatible intersection videos.
- **File changed:** `vision/detector.py` (`_discover_videos()` rewritten), `config.json`

#### **Step 18: Real Camera Integration**
- **Action:** Added `live_camera` scenario to `config.json` with an RTSP placeholder source, `reconnect_on_drop: true`, and 4-arm zone placeholders.
- **Action:** Refactored `vision/detector.py`:
  - Added `_is_live_source(source)` — returns `True` for RTSP URLs, HTTP streams, and integer webcam indices.
  - `process_video()` is now a router: calls `_process_live_stream()` for live sources, `_process_playlist()` for file playlists.
  - `_process_live_stream()` — outer reconnect loop with `RECONNECT_DELAY` (configurable); inner read loop skips yellow phases, logs reconnect events.
  - `_process_playlist()` — fixed to include `cap` initialisation; cycles through playlist with per-clip zone rescaling.
- **Action:** Created `vision/calibrate_zones.py` — interactive OpenCV zone calibration tool:
  - Opens the first frame of the configured source (video file, RTSP stream, or webcam).
  - Operator clicks 4+ points per arm to define zone polygons.
  - Controls: left-click (add point), right-click (undo), ENTER (close arm), R (reset arm), S (save), Q (quit).
  - Saves normalised (0–1) coordinates to `vision/zones_calibrated.json` and prints a paste-ready JSON snippet for `config.json`.
  - Usage: `python vision/calibrate_zones.py [--scenario NAME] [--source PATH] [--arms N S E W]`
- **Files changed / created:** `vision/detector.py`, `vision/calibrate_zones.py`, `config.json`

#### **Step 19: Dashboard Starvation Metrics & Quick Override Logic**
- **Action:** Added a `trigger_override` endpoint to `api/main.py`.
- **Action:** Updated `ai_agent/live_controller.py` to intercept the AI's predictions if a valid `active_override` exists in the dashboard state, forcing the requested phase.
- **Action:** Updated `dashboard/app.py` to calculate starvation time (time since a phase was last green) actively, and provided Quick Override buttons (🚨 15s) for instant operator intervention without permanently leaving AI Mode.

#### **Step 20: Visual Smoothing & Physics Fidelity (Presentation Polish)**
- **Problem observed:** SUMO's native 1-second simulation steps resulted in erratic, jumpy vehicle movements that looked unnatural on-screen.
- **Action:** Modified `simulation/junction.sumocfg` and `simulation/rl-tests.sumocfg` to lower `--step-length` to `0.1` seconds, creating 10 interpolation frames per simulation second.
- **Action:** Set `--time-to-teleport -1` to prevent vehicles from magically vanishing when stuck in queues.
- **Action:** In `simulation/junction.rou.xml`, switched the `car` vType to use the `IDM` (Intelligent Driver Model) car-following algorithm. Reduced `sigma` from 0.5 to 0.2 and `minGap` to 2.0 to tighten stop-and-go clusters and stop drivers from bouncing jerkily behind leaders.
- **Action:** Updated the green phase multipliers in `ai_agent/sumo_env.py` to accurately iterate `duration_steps * 10` due to the new 0.1s step scaling.
- **Outcome:** The SUMO GUI rendering is now cinematic, buttery smooth, and accurately mimics realistic car-following compressions without stutter steps.

---

*Log will be updated after every significant technical step.*
Modified Dashboard GUI to track Starvation metrics and Quick Override interactions
Added IDM car-following physics and 0.1s step interpolation to eliminate erratic vehicle jitter.
Added IDM physics and teleport settings to rl-tests.sumocfg
