# Development Challenges & Known Issues

This file records every significant obstacle, bug, and design weakness encountered during development — what caused it, how it was diagnosed, and what was done to address it.

---

## Resolved Challenges

---

### C-01 — Hardcoded Model Path Caused Immediate Crash on Startup
**File:** `ai_agent/live_controller.py`  
**Symptom:** The system would crash on launch with a `FileNotFoundError` if the expected model file was not present at an exact hardcoded path.  
**Root cause:** `model_path` was set to a single string `"models/ppo_traffic_agent_refined.zip"` with no fallback. Any deviation from that filename (different training run, renamed file, first-time setup) caused an unrecoverable crash before the system did anything useful.  
**Resolution:** Replaced the hardcoded path with a prioritised `MODEL_SEARCH_PATHS` list. The controller walks the list until it finds a file that exists, then loads it. If none are found, a clear human-readable error is raised directing the user to run `train.py` first.  
**Current search order:**
1. `models/ppo_traffic_agent_refined_2.zip`
2. `models/ppo_traffic_agent_refined.zip`
3. `models/ppo_traffic_agent.zip`

---

### C-02 — Silent Failures Masked Broken Components
**Files:** `ai_agent/live_controller.py`, `vision/detector.py`  
**Symptom:** The system appeared to run normally while the vision pipeline or controller was broken. No console output, no errors, no warnings.  
**Root cause:** Multiple `except: pass` and `except Exception: pass` blocks swallowed every possible exception, including network failures, model errors, and API unavailability. There was no `logging` setup, so even `print()` statements were inconsistent.  
**Resolution:** Replaced all bare `except` blocks with `requests.RequestException` (the correct exception type for HTTP failures). Added a `logging` module configuration to every component so failures produce timestamped warnings, e.g.:
```
2026-03-01 12:00:00 [WARNING] Vision API unavailable; using SUMO state.
```
Debug-level messages (minor failures, phase-post retries) use `log.debug()` so they are hidden during normal operation but visible when diagnosing problems.

---

### C-03 — Mode Selector Was Decorative (Had No Effect)
**Files:** `api/main.py`, `ai_agent/live_controller.py`, `dashboard/app.py`  
**Symptom:** Selecting "Fixed Timing" or "Manual Override" in the dashboard dropdown did nothing. The AI agent always ran regardless of what was selected.  
**Root cause:** The API had no concept of operating mode — there was no state field for it and no endpoint to change it. The dashboard rendered the selector but never sent its value anywhere. The controller never read it.  
**Resolution:**
- API: Added `mode` and `manual_phase` fields to the shared state dict; added `POST /set_mode` and `POST /set_phase` endpoints with input validation.
- Controller: Reads the current mode from the API at every control step. Routes to `_fixed_timing_action()`, `_manual_action_from_api()`, or PPO predict accordingly.
- Dashboard: Mode selector calls `POST /set_mode` via an `on_change` callback; Manual Override shows phase buttons that call `POST /set_phase`.

---

### C-04 — Mode Selector Caused Flickering Between Modes
**File:** `dashboard/app.py`  
**Symptom:** After C-03 was fixed, live run output showed the mode toggling between "AI Controlled" and "Fixed Timing" on every other control step (observed at steps 76–100). The system could not settle on a single mode.  
**Root cause:** Streamlit rerenders the entire page on every `st.rerun()` call (which fires every second). The mode selector was unconditionally calling `POST /set_mode` on every render cycle. Because the API received an alternating sequence of mode values from two render cycles in flight, the state oscillated.  
**Resolution:** The selectbox now uses an `on_change` callback combined with a `session_state["last_pushed_mode"]` guard. The HTTP call is made only when the new value differs from the value that was last successfully pushed, not on every rerender.

---

### C-05 — Loss of Historical Analytics
**File:** `api/main.py`
**Symptom:** Training metrics were saved in TensorBoard, but there was no history of past traffic flow, phases, or queue states over weeks or months.  Any system restart wiped out analytical data from the API endpoint.
**Root cause:** The API endpoint `traffic_system_state` was purely an in-memory Python dictionary.
**Resolution:** Implemented `sqlite3` in the API to log `data/traffic_history.db` with a `live_traffic_log` table storing `timestamp`, `north`, `south`, `east`, `west`, `current_phase`, and `mode`. Also resolved a logging swallowing issue in `launch_system.py`.

---

### C-05 — Deprecated Streamlit API Flooded the Log File
**File:** `dashboard/app.py`  
**Symptom:** `dashboard_log.txt` grew to 5,000+ lines containing only the same deprecation warning repeated:
```
Please replace use_container_width with width. use_container_width will be removed after 2025-12-31.
```
**Root cause:** `st.bar_chart()` internally used the deprecated `use_container_width` parameter on every page rerender (once per second). The application ran for hours during testing.  
**Resolution:** Replaced `st.bar_chart()` with an explicit Plotly `go.Bar` chart rendered via `st.plotly_chart(fig, use_container_width=True)`. The deprecation warning no longer fires.

---

### C-06 — Stale Vision Data Shown Without Warning
**File:** `dashboard/app.py`  
**Symptom:** If the vision detector crashed or was disconnected, the dashboard continued displaying the last known queue counts indefinitely with no indication they were outdated. An operator would have no way to know the data was hours old.  
**Root cause:** The dashboard read the API state and rendered whatever it found. There was no timestamp comparison or freshness check.  
**Resolution:** The API state includes a `last_update` timestamp. The dashboard compares it against the current time on every cycle. If the gap exceeds `STALE_THRESH = 5.0` seconds, a yellow warning banner is displayed. The event log also records the staleness onset.

---

### C-07 — Training Data Was Too Uniform to Produce a Useful Agent
**Files:** `simulation/junction.rou.xml`, `ai_agent/sumo_env.py`, `ai_agent/train.py`  
**Symptom:** The trained agent always selected the NORTH-SOUTH phase regardless of actual queue lengths. Reward scores worsened during peak-hour simulation runs. A fixed timer performed comparably.  
**Root cause:** The original simulation used exactly 300 vehicles/hour from all four directions at all times. A perfectly balanced, static load is trivially solved by any strategy. The agent learned to always prefer one phase because the training environment never presented a scenario where the other phase was more beneficial.  
**Resolution — Static profile fix:** Replaced the uniform flow with a 5-period time-varying day profile in `junction.rou.xml` featuring directional imbalance (heavy N-S in the morning, heavy E-W in the evening).  
**Resolution — Domain randomisation:** `sumo_env.py` now has a `randomise_demand` flag. When enabled, `_generate_random_routes()` overwrites `junction.rou.xml` at the start of each training episode with random flows (50–900 veh/hr independently per direction). `train.py` enables this for all training runs. The agent can no longer memorise a fixed schedule.

---

### C-08 — Training Overwrote Previous Models With No History
**File:** `ai_agent/train.py`  
**Symptom:** Every `train.py` run saved to `models/ppo_traffic_agent.zip`, silently overwriting the previous version. There was no way to roll back if a new run performed worse than the previous one.  
**Root cause:** Single hardcoded `model.save()` call with a fixed filename.  
**Resolution:** Training now saves two copies:
1. A timestamped archive, e.g. `models/ppo_traffic_agent_20260301_143022.zip` — never overwritten.
2. A rolling latest copy at `models/ppo_traffic_agent.zip` — always points to the most recent run.

---

### C-09 — Windows/Linux Path Incompatibility Broke Colab Training
**Files:** `ai_agent/sumo_env.py`, `pack_for_colab.py`  
**Symptom:** SUMO threw a file-not-found error when `colab_train.py` was run on Google Colab (Ubuntu), even though the zip contained the correct files.  
**Root cause:** Python `os.path.join` on Windows produces backslash-separated paths (e.g. `simulation\junction.sumocfg`). SUMO on Linux does not accept backslashes.  
**Resolution:**
- `sumo_env.py`: added `.replace("\\", "/")` to the config path before passing it to SUMO.
- `pack_for_colab.py`: the `to_zip_path()` helper converts all Windows-style separators to forward slashes when writing archive entries.

---

### C-10 — Single Video Source Limited Training Diversity
**File:** `vision/detector.py`  
**Symptom:** The vision pipeline always processed the same video file. Fine-tuning with only one clip produced a model that over-fitted to the visual characteristics of that scene (lighting, camera angle, vehicle types).  
**Root cause:** `video_source` was a single string from `config.json`; no mechanism to cycle through multiple clips.  
**Resolution:** `_discover_videos()` auto-scans the `data/` directory for any video file (`.mp4 .avi .mov .mkv .webm`). A playlist is built at startup. When a clip ends, the detector advances to the next entry and loops. Zone scaling is reapplied when resolution changes between clips.

---

### C-11 — Dashboard Insufficient for Real Operational Use
**File:** `dashboard/app.py`  
**Symptom:** The original dashboard showed only a static bar chart of current queue lengths. There was no way to tell if any system component was alive, no historical trend, no alerting, and no audit trail of what the system had done.  
**Resolution:** Full rewrite adding:
- Per-component health indicators (API, Vision Pipeline, AI Controller) with 🟢/🔴 status.
- 6-column KPI strip with live queue counts, total vehicles, and phase age.
- 60-second rolling history trend chart (Plotly `go.Scatter`).
- Alert threshold line at `QUEUE_ALERT = 10` vehicles.
- Event log (`deque(maxlen=20)`) recording phase switches, mode changes, and high-queue alerts with timestamps.
- Phase active timer showing seconds since the last phase change.

---

---

### C-12 — Vision Pipeline Blind Spots Caused Agent to Always Choose NORTH-SOUTH
**File:** `ai_agent/live_controller.py`  
**Symptom observed:** Live run (steps 196–717) showed E=0, W=0 for every single step, and the agent selected NORTH-SOUTH 100% of the time. South queue grew to 19 without the agent ever switching.  
**Root cause:** The observation selection logic was all-or-nothing — `current_obs = obs_vision if obs_vision is not None else obs_sim`. The vision detector's ROI zones are calibrated for the camera angle, which only captures the N/S approaches. E and W zones returned 0 consistently even though SUMO had vehicles queuing on those lanes. The agent, seeing `[N, S, 0, 0, phase]`, correctly (from its perspective) always picked NORTH-SOUTH.  
**Resolution:** Replaced the all-or-nothing pick with a per-direction merge in `_merge_obs()`. For each of the four queue positions, vision counts are used when vision actively detects vehicles (`> 0`), and SUMO's ground-truth count is used where vision returns zero. Phase (index 4) always comes from SUMO. The agent now has an accurate picture of all four approaches even when the camera doesn't cover all of them.

---

### C-13 — Escalating Reward / Runaway Queue Build-up
**Files:** `ai_agent/sumo_env.py`, `ai_agent/live_controller.py`, `colab_train.py`  
**Symptom observed:** Reward in the live run oscillated in a sawtooth pattern — starting around -4, escalating to ~-93 over ~18 steps, then suddenly recovering. South queue reached 19 and North queue reached 18 with no phase switch.  
**Root cause — reward formula:** The reward used `0.1 * cumulative_waiting_time`, where `getWaitingTime()` is a SUMO accumulator in seconds. A vehicle waiting 18 steps × 5 s = 90 s contributed `0.1 × 90 = 9` to the penalty by itself. With 10 vehicles each waiting similarly, this produced a reward of ~-100 independent of the current queue state. The agent learned to optimise the wrong signal.  
**Root cause — no queue-overflow penalty:** The linear `-sum(queues)` term treated a queue of 15 as only marginally worse than a queue of 10. There was no strong signal to avoid catastrophic buildup.  
**Resolution — reward function (both `sumo_env.py` and `colab_train.py`):**
- Waiting time is now capped at 60 s per lane before summing, so a single long-waiting vehicle cannot dominate the signal.
- The waiting time coefficient is reduced from `0.1` to `0.05`.
- A quadratic overflow penalty `0.5 * sum(max(0, queue - 10)^2)` is added. This means a queue of 15 contributes `0.5 * 25 = 12.5` extra, making the agent strongly averse to allowing any approach to exceed 10 vehicles.

**Resolution — safety valve override (`live_controller.py`):**
- Added a `MAX_QUEUE_OVERRIDE = 15` constant.
- In AI Controlled mode, after the model picks an action, the controller checks whether the opposing direction's total queue exceeds this threshold AND is larger than the currently served direction. If so, it overrides the model's action and logs a warning. This is a runtime guardrail — it prevents catastrophic buildup during deployment while the model is retrained with the improved reward.

## Open / Ongoing Issues

---

### I-01 — Agent Performance on Unseen Real-World Conditions
**Status:** Partially mitigated  
**Description:** The PPO agent was trained on synthetic SUMO flows, even with domain randomisation. Real pedestrian activity, non-standard vehicle types (tuk-tuks, motorbikes), and occluded cameras produce observation distributions the agent has never encountered. The agent may default to one phase or oscillate when queues are ambiguous.  
**Mitigation so far:** 34 real Ghanaian traffic videos added to the training data; domain randomisation enabled.  
**Remaining risk:** SUMO-derived queue observations do not include vision uncertainty — the agent sees clean integer counts even when detection confidence is low.  
**Suggested next step:** Add a confidence weight to the queue observation so the agent can learn to be more conservative when detection is uncertain.

---

### I-02 — No Persistent Storage for Dashboard History
**Status:** Open  
**Description:** All history buffers (`deque` objects) are held in Streamlit `session_state`, which is lost when the browser tab is closed or the app restarts. There is no database or file-backed storage.  
**Impact:** Operators cannot review what happened earlier in a session after a page refresh. Incident investigation is limited to whatever is in the current tab's memory.  
**Suggested next step:** Write each API poll result to a lightweight SQLite database (`history.db`) which the dashboard can query for the rolling window.

---

### I-03 — Single Traffic Junction Only
**Status:** Open  
**Description:** The entire system is built around one 4-way junction (`center` TLS node). The architecture does not support coordinated control of multiple intersections or green-wave progression along a corridor.  
**Impact:** Not suitable for arterial or network-level deployment without significant redesign.  
**Suggested next step:** Parameterise `sumo_env.py` with a junction ID list; extend the observation space to include neighbouring junction queues.

---

### I-04 — API Has No Authentication
**Status:** Open  
**Description:** `api/main.py` exposes `/set_mode` and `/set_phase` with no authentication, rate limiting, or input sanitisation beyond basic type validation. Any process on the local network can change the operating mode or override traffic phases.  
**Impact:** Acceptable for a local development environment; unacceptable for any networked deployment.  
**Suggested next step:** Add HTTP Basic Auth or an API key header check using FastAPI's `Security` dependency.

---

### I-05 — Vision Zone Coordinates Are Hardcoded for One Camera
**Status:** Partially resolved (2026-03-05)  
**Description:** The ROI polygon coordinates in `vision/detector.py` are tuned for a specific camera resolution and mounting angle. They are not automatically recalibrated when a new video source has different framing.  
**Impact:** Queue counts will be inaccurate for any camera that does not match the original calibration, quietly degrading reward signals and KPI displays.  
**Resolution so far:**
- Zone coordinates are now stored in `config.json` under each scenario's `zones` array as normalised (0–1) polygon points, applied at runtime via `ZoneCounter.scale_polygon(w, h)` based on the actual frame dimensions.
- `vision/calibrate_zones.py` provides an interactive OpenCV tool for clicking zone corners on a camera frame and exporting paste-ready JSON.
- `_process_playlist()` resets `self.polygons_scaled = False` when advancing to a new video so zones are rescaled for the new resolution automatically.
**Remaining risk:** Zone polygons in `config.json` are still manually maintained — there is no automated QA check that verifies a polygon actually covers an approach lane rather than an empty area of the frame.

---

### C-14 — `compute_pressure()` Returned `None`, Breaking Max-Pressure Override
**File:** `ai_agent/max_pressure.py`  
**Symptom observed:** Every live-run step logged `TypeError: '>' not supported between instances of 'NoneType' and 'NoneType'` from inside `should_override()`.  
**Root cause:** `compute_pressure()` had a `try/except` block where the success path fell through to the end of the function without an explicit `return`. Python implicitly returned `None`. `should_override()` called `max()` on the resulting `{phase_id: None}` dict, which crashed on the comparison.  
**Resolution:** Added `return float(inbound - outbound)` at the end of the try block; added `int(traci.lane.getLastStepHaltingNumber(l) or 0)` guard on each lane call to handle lanes where TraCI returns `None`; widened the `except` from bare to `except Exception` so unexpected TraCI errors are caught without silently swallowing all failures.

---

### C-15 — Dashboard Always Displayed NS Green Regardless of Actual Phase
**File:** `dashboard/app.py`, `ai_agent/live_controller.py`  
**Symptom observed:** Live run of 116 steps showed "NS Green" in the dashboard for every step even though the controller was alternating between NS and EW.
**Root cause (1 — duplicate code):** A previous automated edit had appended an entire second copy of `dashboard/app.py` to the bottom of the file. The duplicate contained an older, simpler phase-display block that evaluated after the correct one on every rerender, unconditionally overwriting it back to NS.  
**Root cause (2 — posting timing):** The controller posted the phase to the API only during the yellow transition (≈1.7 s). The dashboard polled every 1 s and almost always caught the tail of the yellow window, reading "phase 1 (yellow)" before EW had been written.  
**Resolution:** Removed the duplicate code block from `app.py`. Moved the `post_phase_to_api()` call to **before** `env.step()` so the API records the upcoming green phase for the full duration of the green. `post_phase_to_api()` now skips yellow phases (1, 3) entirely to avoid confusing the dashboard.

---

### C-16 — South-Lane Congestion Bias in Reward Function
**Files:** `ai_agent/sumo_env.py`, `ai_agent/colab_train.py`  
**Symptom observed:** In long live runs, South-lane queue consistently grew to 15–19 vehicles without the agent switching away, even when E/W queues were manageable.  
**Root cause:** The reward treated every cleared vehicle identically: `vehicles_cleared = sum(queues_before) - sum(queues_after)`. Clearing 3 vehicles from a congested approach (queue 18) counted the same as clearing 3 from a light approach (queue 2). The agent had no incentive to prioritise the worst-congested lane.  
**Resolution:** Per-lane congestion weight applied at reward time: `cleared_i × (1 + queue_before_i / max_queue_before)`. Lanes with heavier congestion at the start of the green phase contribute proportionally more to the reward. A lane at maximum queue provides twice the reward-per-vehicle compared to an empty lane.

---

### C-17 — Duplicate Log Lines (Steps Appearing 2–3× in Output)
**File:** `ai_agent/live_controller.py`  
**Symptom observed:** Steps 112–113 appeared three times in the console and log file.  
**Root cause:** `logging.basicConfig()` was called once inside `live_controller.py` and once implicitly by `launch_system.py` when it imported the module. Python's logging system added a second (or third) `StreamHandler` on each call, causing every log record to be emitted once per handler.  
**Resolution:** Added `force=True` to the `logging.basicConfig()` call in `live_controller.py`. With `force=True`, the root logger's existing handlers are removed before the new configuration is applied, ensuring exactly one handler is registered regardless of import order.

---

### C-18 — Reward Volatility from Outbound Flow Inflation on Long Phases
**Files:** `ai_agent/sumo_env.py`, `ai_agent/colab_train.py`  
**Symptom observed:** Reward swings of −10 to +26 within steps 23–40 of a live run with no corresponding change in queue state.  
**Root cause:** On a 30-second green phase (`action[1]=2`, `duration_steps=6`), `outbound_flow` accumulated vehicle counts across all 6 simulation steps (`delta_time=5` each). The reward term `0.5 * outbound_flow` therefore received a value 6× larger than on a 5-second phase, inflating the reward proportionally to phase length regardless of actual throughput rate.  
**Resolution:** Normalised outbound flow: `outbound_flow / chunks` where `chunks = duration_steps / delta_time`. The outbound reward component now represents **average throughput per 5-second step** rather than a raw total, making rewards comparable across all three duration levels.

---

### C-19 — East/West Detector Always Returned 0 (Wrong Zone Geometry)
**File:** `config.json`  
**Symptom observed:** E=0, W=0 on every step of the 116-step live run.  
**Root cause:** The `traffic_test` scenario had four zone polygons configured as left/right/top/bottom screen quadrants with `map_to` fields set to `North`, `North`, `South`, `South`. There were no zones at all mapped to `East` or `West`. Even a perfectly working vision pipeline would always count 0 for both eastern approaches.  
**Resolution:** Replaced the four quadrant polygons with four arm-shaped polygons that extend along each of the four approach directions from the intersection centre outward, with `map_to` correctly set to `North`, `South`, `East`, and `West` respectively.

---

### C-20 — Street-Level Training Videos Corrupting Top-Down Zone Counts
**Files:** `vision/detector.py`, `config.json`  
**Symptom:** After the 34 Ghanaian traffic videos were added to `data/`, the auto-discover playlist included street-level footage. Top-down N/S/E/W zone polygons do not correspond to any meaningful region of a street-level perspective, producing 0 or random counts for all arms.  
**Root cause:** `_discover_videos()` scanned all video files in `data/` without discriminating by camera perspective. The 34 training videos are real-world street-level footage recorded for RL training diversity; they are not overhead intersection views compatible with polygon-based zone counting.  
**Resolution:** Added a `video_list` field to scenario configurations in `config.json`. When present, `_discover_videos()` builds the playlist exclusively from the listed files. The `traffic_test` scenario now explicitly lists only the five overhead-compatible intersection videos. The auto-discover fallback and SUMO training videos are no longer mixed into the vision pipeline.

---

### I-06 — `launch_system.py` Has No Restart Logic
**Status:** Open  
**Description:** If any subprocess (SUMO, FastAPI, vision detector, live controller) crashes, `launch_system.py` does not restart it. The entire system silently degrades as components drop out one by one.  
**Impact:** Extended runs (overnight, continuous deployment) will eventually lose components without alerting anyone.  
**Suggested next step:** Wrap each subprocess in a restart loop with exponential back-off and a max-retry limit; surface crash events to the dashboard event log.
