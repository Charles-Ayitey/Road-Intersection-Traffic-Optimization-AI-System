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

