# System Improvements & Bug Fixes

**Date:** 2026-03-01  
**Scope:** All five phases of the Smart Traffic Junction System

---

## Overview

After a full codebase review, several bugs and missing features were identified and fixed. The changes fall into six categories: model loading, error visibility, operating modes, the dashboard, model versioning, and traffic simulation realism.

---

## 1. Model Loading — Added Fallback Search (`ai_agent/live_controller.py`)

**Problem:**  
The live controller was hardcoded to load a file called `ppo_traffic_agent_refined.zip`. This file was produced during cloud (Google Colab) training and may not always be present on a local machine. If it was missing, the entire system would crash immediately on startup with no helpful message.

**Fix:**  
The controller now searches for models in order:
1. `models/ppo_traffic_agent_refined.zip` (cloud-trained, best version)
2. `models/ppo_traffic_agent.zip` (locally trained fallback)

If neither file exists, the system raises a clear error message telling you to run `train.py` first, instead of crashing with a confusing Python traceback.

---

## 2. Silent Errors — Replaced Bare `except: pass` Blocks

**Problem:**  
Several places in the code were catching all errors and doing nothing with them (`except: pass` or `except Exception: pass`). This meant that if the vision detector failed to send data to the API, or if the live controller lost its connection, the failure would be completely invisible — the system would appear to keep running normally while actually broken.

**Files changed:** `ai_agent/live_controller.py`, `vision/detector.py`

**Fix:**  
- All network calls now catch `requests.RequestException` specifically (the correct exception type for HTTP failures) rather than swallowing every possible error.
- A proper `logging` module is used throughout, replacing `print()` statements. Failed API calls now produce a timestamped warning in the console, e.g.:  
  `2026-03-01 12:00:00 [WARNING] Vision API unavailable; using SUMO state.`
- Debug-level messages (e.g. minor phase-post failures) are logged at `DEBUG` level so they don't clutter normal output but can be seen when diagnosing issues.

---

## 3. Operating Modes — Wired Up the Mode Selector

**Problem:**  
The dashboard had a dropdown with three modes — "AI Controlled", "Fixed Timing", and "Manual Override" — but selecting a different mode had no effect whatsoever. The live controller always used the AI and ignored the selector entirely.

**Files changed:** `api/main.py`, `ai_agent/live_controller.py`, `dashboard/app.py`

**Fix — API (`api/main.py`):**  
- Added `mode` and `manual_phase` fields to the shared system state.
- Added a `POST /set_mode` endpoint so the dashboard can tell the API which mode is active.
- Added a `POST /set_phase` endpoint so the dashboard can directly command a traffic phase (used in Manual Override).

**Fix — Controller (`ai_agent/live_controller.py`):**  
On every control step, the controller now reads the current mode from the API and behaves accordingly:

| Mode | Behaviour |
|---|---|
| **AI Controlled** | PPO model makes the decision (original behaviour) |
| **Fixed Timing** | Alternates North-South and East-West every 30 steps, like a traditional timer |
| **Manual Override** | Reads the phase set by the dashboard operator and applies it to the simulation |

**Fix — Dashboard (`dashboard/app.py`):**  
- When the mode selector is changed, the new mode is immediately sent to the API via `POST /set_mode`.
- When "Manual Override" is selected, two buttons appear in the sidebar: **"Set NORTH-SOUTH Green"** and **"Set EAST-WEST Green"**, which send commands directly to the running simulation.

---

## 4. Dashboard Improvements (`dashboard/app.py`)

### 4a. Deprecated API Warning

**Problem:**  
The dashboard was generating a deprecation warning on every single page refresh:  
`Please replace use_container_width with width. use_container_width will be removed after 2025-12-31.`  
This warning repeated thousands of times, filling `dashboard_log.txt` with 5,000+ lines of noise.

**Fix:**  
Replaced `st.bar_chart()` (which internally triggered the warning) with an explicit Plotly `go.Bar` chart rendered via `st.plotly_chart()`. The chart now also has colour-coded bars for each approach direction.

### 4b. Stale Vision Feed Indicator

**Problem:**  
If the vision detector stopped sending data, the dashboard would continue showing the last known counts with no indication they were outdated.

**Fix:**  
The dashboard now checks how long ago the last vision update arrived. If it has been more than 5 seconds, a yellow warning banner appears: *"Vision feed is stale (>5 s)."*

### 4c. Structural Cleanup

- Removed an unused `while True` loop (replaced with the correct `st.rerun()` call at the bottom of the script).
- Removed unused imports (`pandas`).
- Dashboard now displays the active mode in the subtitle so the operator always knows which mode is running.

---

## 5. Model Versioning (`ai_agent/train.py`)

**Problem:**  
Every time `train.py` was run, it saved the model to the same filename (`models/ppo_traffic_agent.zip`), overwriting the previous version. There was no way to go back to an earlier model if a new training run performed worse.

**Fix:**  
Training now saves two copies on every run:
1. **Versioned copy** with a timestamp in the filename, e.g. `models/ppo_traffic_agent_20260301_143022.zip` — this is never overwritten and acts as a history.
2. **Latest copy** at `models/ppo_traffic_agent.zip` — this is what the live controller's fallback path picks up automatically.

---

## 6. Realistic Traffic Flows (`simulation/junction.rou.xml`)

**Problem:**  
The simulation sent exactly 300 vehicles per hour from all four directions at all times. This perfectly balanced, unchanging load is not representative of real traffic and does not challenge the AI agent — a simple fixed timer would perform equally well.

**Fix:**  
The 1-hour simulation (3,600 seconds) is now divided into five time periods that mimic a real day:

| Period | Time | Pattern | Vehicles/hour (N, S, E, W) |
|---|---|---|---|
| Off-peak | 0–600 s | Balanced low | 150, 150, 150, 150 |
| Morning rush | 600–1800 s | Heavy North-South | 700, 600, 200, 200 |
| Midday | 1800–2700 s | Moderate balanced | 350, 350, 300, 300 |
| Evening rush | 2700–3400 s | Heavy East-West | 250, 250, 650, 700 |
| Wind-down | 3400–3600 s | Low balanced | 100, 100, 100, 100 |

This gives the AI agent a genuine challenge — it must learn to shift priority to whichever axis is most congested at each point in the simulation, rather than being able to score a perfect reward with a fixed-timing strategy.

---

## Files Changed

| File | What Changed |
|---|---|
| `ai_agent/live_controller.py` | Model fallback, logging, mode-aware action selection, new model as top priority |
| `api/main.py` | Added `mode`, `manual_phase` state; `/set_mode` and `/set_phase` endpoints |
| `dashboard/app.py` | Full rewrite — health panel, KPI strip, history trend, event log, alert threshold, phase timer, mode-flicker fix |
| `ai_agent/sumo_env.py` | `randomise_demand` flag, `_generate_random_routes()`, cross-platform path normalisation |
| `ai_agent/train.py` | Timestamped + latest model saves; domain randomisation enabled |
| `vision/detector.py` | Proper exception handling, video auto-discovery, playlist cycling |
| `simulation/junction.rou.xml` | Time-varying unbalanced traffic flows |

---

## 7. Mode Selector Flickering Fix (`dashboard/app.py`)

**Problem:**  
After the mode selector was wired up (change 3 above), a new bug emerged in live testing: the mode oscillated between "AI Controlled" and "Fixed Timing" on every other control step. Because Streamlit rerenders the entire page every second, the mode selector was re-pushing its value to the API on each cycle. This caused the API state to toggle back and forth.

**Fix:**  
The `st.selectbox` now uses an `on_change` callback paired with a `session_state["last_pushed_mode"]` guard. The `POST /set_mode` call fires only when the selected value actually differs from the last value that was pushed — not on every rerender.

---

## 8. Domain Randomisation for Training (`ai_agent/sumo_env.py`, `ai_agent/train.py`)

**Problem:**  
The simulation always ran the same traffic profile (or the fixed 5-period day after change 6). The agent could potentially memorise the schedule rather than learn a general policy.

**Fix:**  
- `SumoTrafficEnv` now accepts a `randomise_demand` flag.
- When enabled, `_generate_random_routes()` is called at the start of every episode and writes a fresh `junction.rou.xml` with random flows between 50–900 vehicles/hour independently for each of the four approach directions.
- `train.py` runs with `randomise_demand=True` so the training agent faces a different scenario every episode.
- Cross-platform fix: `sumocfg_path.replace("\\", "/")` prevents path errors when the same config is used on both Windows and Ubuntu.

---

## 9. Multi-Video Support (`vision/detector.py`)

**Problem:**  
The detector was hardcoded to a single video source. Testing and training were limited to one traffic scenario.

**Fix:**  
- `_discover_videos()` automatically scans the `data/` directory for video files (`.mp4 .avi .mov .mkv .webm`) and builds an ordered playlist.
- On end-of-file, the detector advances to the next video in the playlist and loops back to the start after the last one.
- Zone scaling is re-applied when the resolution changes between clips.

---

## 10. Google Colab Training Package

**New files added:**

**`colab_train.py`**  
A self-contained training script for Google Colab's GPU runtime. Key features:
- Inline `SumoTrafficEnv` class — does not import any local project files.
- Hardcoded Ubuntu SUMO path (`/usr/share/sumo`).
- Domain randomisation ON for the training environment, OFF for the evaluation environment.
- `EvalCallback` saves the best checkpoint automatically every 25 k steps.
- 300 k total training steps; final model saved as `ppo_traffic_agent_refined.zip`.

**`pack_for_colab.py`**  
Builds `traffic_project.zip` for upload to Colab:
- Includes all SUMO simulation configs, all media files in `data/`, and `colab_train.py`.
- `to_zip_path()` converts Windows backslashes to forward slashes so all paths resolve correctly on Ubuntu Linux.

---

## 11. New Trained Model (`models/ppo_traffic_agent_refined_2.zip`)

The second Colab training iteration (`ppo_traffic_agent_refined_2.zip`) has been added as the top-priority entry in `MODEL_SEARCH_PATHS` inside `ai_agent/live_controller.py`. The search order is now:

1. `models/ppo_traffic_agent_refined_2.zip` ← trained with domain randomisation + 34 real traffic videos
2. `models/ppo_traffic_agent_refined.zip`
3. `models/ppo_traffic_agent.zip`

---

## 12. Production-Grade Dashboard (`dashboard/app.py`)

A full rewrite replacing the original 124-line prototype with an operational monitoring interface:

| Feature | Detail |
|---|---|
| **System health panel** | Sidebar shows 🟢/🔴 liveness dots for API, Vision Pipeline, and AI Controller independently |
| **KPI strip** | 6-column row: N / S / E / W queue counts, Total Vehicles, Phase Active (seconds) |
| **Bar chart with alert line** | Plotly `go.Bar`; dashed red threshold line at `QUEUE_ALERT = 10` vehicles |
| **60-second history trend** | Plotly `go.Scatter` rolling window for all four directions |
| **Event log** | `deque(maxlen=20)` captures phase switches, mode changes, and high-queue alerts with timestamps |
| **Phase timer** | Tracks seconds since last phase change; resets on each detected transition |
| **Stale feed warning** | Yellow banner if vision data has not arrived within `STALE_THRESH = 5.0` seconds |
| **Session persistence** | `_init_state()` initialises all buffers in `session_state` so history survives rerenders |

---
---

# Changes — 2026-03-05

**Scope:** Observation hardening, dynamic phase duration, live-run diagnostics, video architecture, real-camera integration.

---

## 13. New Model Checkpoints Integrated (`ai_agent/live_controller.py`)

`MODEL_SEARCH_PATHS` updated with best-checkpoint saves from the EvalCallback — these consistently outperform the final-step saves because they record the agent at its peak evaluation score rather than its last training state.

Full search order:
```
1. models/best_model_2.zip          ← best eval checkpoint, latest training run
2. models/ppo_traffic_agent_refined_4.zip
3. models/best_model.zip
4. models/ppo_traffic_agent_refined_3.zip
5. models/ppo_traffic_agent_refined_2.zip
6. models/ppo_traffic_agent_refined.zip
7. models/ppo_traffic_agent.zip
```

---

## 14. `compute_pressure()` NoneType Fix (`ai_agent/max_pressure.py`)

The max-pressure fallback controller crashed on every step because `compute_pressure()` had a missing `return` statement. The function returned `None` instead of the pressure differential, then `should_override()` called `max()` on a dict of `None` values.

**Changes:**
- Added `return float(inbound - outbound)` at the correct position in the function body.
- Added `int(traci.lane.getLastStepHaltingNumber(l) or 0)` guard so a `None` TraCI response is treated as 0 rather than causing a downstream crash.
- Widened bare `except` to `except Exception` — failures are now caught and logged rather than silently swallowed.

---

## 15. Step 2 — Upstream Induction Loop Detectors

**New file:** `simulation/junction.add.xml`  
Four E1 induction loops, one per inbound lane, at pos=33 (~60 m upstream of the stop line). Frequency: 5 seconds.

**`simulation/junction.sumocfg`**  
Added `<additional-files value="junction.add.xml"/>` to load the detector definitions.

**`ai_agent/sumo_env.py`** (and synced into `ai_agent/colab_train.py`):
- `_write_add_xml()` regenerates `junction.add.xml` at runtime with the OS-appropriate null device (`/dev/null` on Linux, `NUL` on Windows).
- `self.detector_ids = ["det_n", "det_s", "det_e", "det_w"]`
- Observation space expanded from 5 to **9 elements**: `[Q_N, Q_S, Q_E, Q_W, Occ_N, Occ_S, Occ_E, Occ_W, phase]`.
- Occupancy values come from `traci.inductionloop.getLastStepOccupancy(det_id)`.

---

## 16. Step 3 — Dynamic Phase Duration

**`ai_agent/sumo_env.py`** (and synced into `ai_agent/colab_train.py`):
- `action_space` changed from `Discrete(2)` to `MultiDiscrete([2, 3])`.
  - `action[0]` = phase direction (0 = NS, 1 = EW).
  - `action[1]` = duration level → `_DURATION_STEPS = [1, 3, 6]` steps at `delta_time=5`.

**`ai_agent/live_controller.py`**:
- `dur_idx = int(action[1])`; `dur_label = ["5s", "15s", "30s"][dur_idx]` logged per step.
- Phase posted to API **before** `env.step()` so dashboard shows the correct green for the full duration.
- `post_phase_to_api()` skips yellow phases (1, 3).
- Request timeout increased from 0.1 s to 0.5 s.
- `logging.basicConfig(force=True)` prevents duplicate log lines from double initialisation.

---

## 17. Per-Lane Congestion-Weighted Reward + Outbound Normalisation

**`ai_agent/sumo_env.py`** and **`ai_agent/colab_train.py`** — reward function updated:

Previous formula:
```
reward = vehicles_cleared + 0.5*outbound_flow - 0.3*remaining_queue - 0.5*overflow
```

New formula:
```
reward = cleared_weighted + 0.5*(outbound_flow / chunks) - 0.3*remaining_queue - 0.5*overflow

where:
  cleared_weighted = Σ  cleared_i × (1 + queue_before_i / max_queue_before)
  chunks           = duration_steps / delta_time
```

The congestion weight means that clearing a vehicle from a queue of 18 contributes roughly twice the reward of clearing the same vehicle from a queue of 2. The outbound normalisation divides by the number of simulation substeps executed during the green phase so that a 30-second green does not receive 6× the outbound bonus of a 5-second green.

---

## 18. EW Zone Geometry Fix (`config.json`)

The `traffic_test` scenario previously had four quadrant polygons (`top-left/top-right/bottom-left/bottom-right`), all mapped to `North` or `South`. East and West were absent. All four zones replaced with four arm-shaped polygons extending along each approach direction from the intersection centre, with `map_to` set to `North`, `South`, `East`, and `West`.

---

## 19. Dashboard Duplicate-Code and Phase-Display Fix (`dashboard/app.py`)

A previous automated edit had appended an entire second copy of `app.py` to the end of the file. The duplicate tail contained a simplified phase-display block that unconditionally overrode the correct implementation on every page rerender, locking the display to "NS Green". The duplicate was removed, leaving a single clean implementation.

---

## 20. Video Playlist Architecture — `video_list` Allowlist

**`config.json`**:  
Added `video_list` field to scenario configurations. When present, the playlist is built from exactly these files (relative paths from the project root). The `traffic_test` scenario lists only the five overhead-compatible intersection videos.

**`vision/detector.py`** — `_discover_videos()` rewritten with the following priority chain:
1. `scenario.video_list` — if specified, use only these files.
2. Auto-discover all video files in `data/` — used only when no `video_list` is set.
3. Fall back to `scenario.source` — used when `data/` is empty.

This prevents the 34 Ghanaian street-level training videos from being ingested by the vision pipeline's top-down zone counter.

---

## 21. Real Camera Integration

**`config.json`** — new `live_camera` scenario:
```json
"live_camera": {
    "source": "rtsp://USERNAME:PASSWORD@CAMERA_IP:554/stream",
    "reconnect_on_drop": true,
    "zones": [ ... 4 arm-shaped placeholder polygons ... ]
}
```
Replace the RTSP placeholder with the actual camera address; use `calibrate_zones.py` to generate the zone polygons.

**`vision/detector.py`** — refactored video processing:

| Method | Purpose |
|---|---|
| `_is_live_source(source)` | Returns `True` for RTSP URLs, HTTP streams, and integer webcam indices |
| `process_video(show)` | Router — calls `_process_live_stream()` or `_process_playlist()` |
| `_process_live_stream(show)` | Outer reconnect loop + inner frame-read loop; logs reconnect events; honours `reconnect_on_drop` from config |
| `_process_playlist(show)` | Cycles through the video list; rescales zones when clip resolution changes |

**New file:** `vision/calibrate_zones.py`  
Interactive OpenCV tool for defining zone polygons on a camera frame.

```bash
# Use active_scenario source from config.json
python vision/calibrate_zones.py

# Specific scenario
python vision/calibrate_zones.py --scenario live_camera

# Custom source
python vision/calibrate_zones.py --source rtsp://192.168.1.100:554/stream
python vision/calibrate_zones.py --source 0   # webcam index
```

| Control | Action |
|---|---|
| Left-click | Add point to current zone |
| Right-click | Undo last point |
| ENTER / N | Close polygon, advance to next arm |
| R | Reset current arm |
| S | Save all zones and exit |
| Q / ESC | Quit without saving |

Output: `vision/zones_calibrated.json` + paste-ready JSON printed to terminal.

---

## Files Changed — 2026-03-05

| File | What Changed |
|---|---|
| `ai_agent/live_controller.py` | New model paths; dynamic duration decoding; phase-before-step posting; skip yellows; 0.5 s timeout; `force=True` logging |
| `ai_agent/max_pressure.py` | Missing `return`; `int(... or 0)` guard; widened `except Exception` |
| `ai_agent/sumo_env.py` | 9-element obs; `_write_add_xml()`; `MultiDiscrete([2,3])` action; per-lane weighted reward; outbound normalisation |
| `ai_agent/colab_train.py` | Fully synced with all `sumo_env.py` changes |
| `simulation/junction.add.xml` | **New** — 4 E1 induction loops |
| `simulation/junction.sumocfg` | Added `<additional-files>` reference |
| `config.json` | EW arm zones; `video_list` allowlist; `live_camera` scenario |
| `dashboard/app.py` | Duplicate code block removed |
| `vision/detector.py` | `_discover_videos()` with priority chain; `_is_live_source()`; `process_video()` router; `_process_live_stream()`; `_process_playlist()` fixed |
| `vision/calibrate_zones.py` | **New** — interactive zone calibration tool |

