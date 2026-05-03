# 🚦 Road Intersection Traffic Optimization AI System

An AI-driven adaptive traffic signal controller that combines **Reinforcement Learning (PPO)** and **Computer Vision (YOLOv8)** to minimize congestion at a 4-way road intersection. The system uses the [SUMO](https://sumo.dlr.de/) traffic simulator for environment modelling and training, and exposes a real-time monitoring dashboard with live camera support.

---

## 📊 Current Project State

**Overall Status: Phase 7 — Vision & Camera Integration (mostly complete)**

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Environment & Simulation Setup | ✅ Complete |
| 2 | Computer Vision Pipeline | ✅ Complete |
| 3 | AI Agent Development (PPO, 300k steps) | ✅ Complete |
| 4 | System Integration (API + Controller) | ✅ Complete |
| 5 | Real-time Dashboard | ✅ Complete |
| 6 | Observation & Reward Hardening | ✅ Complete |
| 7 | Vision & Camera Integration | 🟡 Mostly complete |
| — | Multi-junction / MARL | 🔲 Deferred |

### What is implemented

- **SUMO simulation** — 4-way junction with time-varying traffic demand and 4 upstream induction-loop detectors (`simulation/junction.*`)
- **YOLOv8n detector** — zone-based vehicle counting across N/S/E/W arms; multi-video playlist and live RTSP camera support (`vision/detector.py`)
- **PPO agent** — 9-element observation space (4 queue lengths + 4 occupancy readings + current phase), `MultiDiscrete` action space (direction × green duration), per-lane congestion-weighted reward (`ai_agent/sumo_env.py`, `ai_agent/live_controller.py`)
- **Max-pressure fallback** — deterministic controller used if the RL model is unavailable (`ai_agent/max_pressure.py`)
- **FastAPI data bus** — shared state store; mode selection (`AI / Fixed-timing / Manual Override`) and phase override endpoints (`api/main.py`)
- **Streamlit dashboard** — live KPI strip, 60-second rolling Plotly charts, system health panel, alert log, stale-feed warnings (`dashboard/app.py`)
- **Interactive zone calibration** — click-to-define ROI tool that outputs paste-ready JSON for `config.json` (`vision/calibrate_zones.py`)
- **Google Colab training pipeline** — self-contained `colab_train.py` and `SmartTraffic_Training.ipynb` for GPU-accelerated retraining
- **7 trained model checkpoints** stored in `models/`

### What remains

| Item | Notes |
|------|-------|
| Retrain with new reward formula | `best_model_2.zip` was trained before per-lane weighting and outbound-flow normalisation were added. Run `pack_for_colab.py` then re-train in Colab. |
| API authentication | No auth on any endpoint — see [GEMINI_ANALYSIS_AND_PROPOSALS.md](GEMINI_ANALYSIS_AND_PROPOSALS.md) for a JWT/API-key proposal. |
| Process health monitoring | `launch_system.py` does not restart crashed sub-processes. |
| Dashboard persistence | History is in-memory only; restarting the dashboard wipes all data. |
| Multi-junction support | Architecture is currently hardcoded for one intersection. |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      launch_system.py                        │
│  (starts all four components and shuts them down together)   │
└──────┬──────────────┬───────────────┬───────────────────────┘
       │              │               │
       ▼              ▼               ▼
┌────────────┐ ┌────────────┐ ┌─────────────────┐
│ vision/    │ │ ai_agent/  │ │  dashboard/     │
│ detector   │ │ live_      │ │  app.py         │
│ .py        │ │ controller │ │  (Streamlit)    │
│ (YOLOv8)   │ │ .py (PPO)  │ │  :8501          │
└─────┬──────┘ └─────┬──────┘ └────────┬────────┘
      │              │                 │
      └──────┬───────┘                 │
             ▼                         │
     ┌───────────────┐                 │
     │  api/main.py  │◄────────────────┘
     │  (FastAPI)    │
     │  :8000        │
     └───────────────┘
```

**Data flow:**

1. **Vision detector** reads video frames (or a live camera stream), counts vehicles per approach zone, and POSTs counts to the API every ~2 seconds.
2. **AI controller** reads the current counts + system state from the API, runs a PPO inference step (or max-pressure / fixed-timing depending on mode), then applies the chosen phase to the SUMO simulation via TraCI and POSTs the result back to the API.
3. **Dashboard** polls the API on a 2-second interval to display live KPIs, trend charts, and system health.

---

## 📁 Repository Layout

```
.
├── ai_agent/
│   ├── live_controller.py    # Real-time PPO inference + SUMO control loop
│   ├── sumo_env.py           # Gymnasium environment wrapper
│   ├── train.py              # Local training script
│   ├── colab_train.py        # Self-contained Google Colab training script
│   ├── max_pressure.py       # Deterministic fallback controller
│   ├── test_agent.py         # Quick sanity-check (50 steps)
│   └── SmartTraffic_Training.ipynb
├── api/
│   └── main.py               # FastAPI data bus (shared state + mode endpoints)
├── dashboard/
│   └── app.py                # Streamlit monitoring dashboard
├── data/                     # Traffic videos (overhead intersections + training footage)
├── docs/                     # Copies of the documentation files below
├── models/                   # Trained PPO checkpoints + YOLOv8n weights
├── simulation/
│   ├── junction.net.xml      # 4-way junction network
│   ├── junction.rou.xml      # Time-varying traffic routes
│   ├── junction.add.xml      # Upstream induction-loop detectors
│   ├── junction.sumocfg      # SUMO run configuration
│   └── test_traci.py         # TraCI connectivity test
├── vision/
│   ├── detector.py           # YOLOv8 zone-based vehicle counter
│   └── calibrate_zones.py    # Interactive ROI calibration tool
├── config.json               # Active scenario, zone geometry, model paths
├── launch_system.py          # One-command system startup
├── pack_for_colab.py         # Packages project for Colab upload
├── PROGRESS.md               # Phase-by-phase completion checklist
├── CHANGES.md                # Detailed changelog of all improvements
├── DEV_LOG.md                # Chronological development log
├── CHALLENGES.md             # Resolved issues and known problems
└── GEMINI_ANALYSIS_AND_PROPOSALS.md  # Architecture audit & roadmap
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- [SUMO](https://sumo.dlr.de/docs/Downloads.php) installed with `SUMO_HOME` set
- Dependencies:

```bash
pip install ultralytics opencv-python stable-baselines3 fastapi uvicorn \
            streamlit requests gymnasium traci plotly
```

### Run the full system

```bash
python launch_system.py
```

This starts four processes in order:
1. FastAPI data bus on `http://localhost:8000`
2. YOLOv8 vision detector (reads the active scenario from `config.json`)
3. Streamlit dashboard on `http://localhost:8501`
4. PPO live controller (blocks; Ctrl-C shuts everything down)

Open `http://127.0.0.1:8501` in your browser to view the dashboard.

### Run components individually

```bash
# API only
python api/main.py

# Vision detector only
python vision/detector.py

# Dashboard only
streamlit run dashboard/app.py

# AI controller only
python ai_agent/live_controller.py

# Quick agent test (no camera required)
python ai_agent/test_agent.py
```

### Train a new model (local)

```bash
python ai_agent/train.py
```

### Train in Google Colab (recommended — GPU)

```bash
python pack_for_colab.py          # builds traffic_project.zip
# upload traffic_project.zip to Colab and run SmartTraffic_Training.ipynb
```

### Calibrate camera zones

```bash
python vision/calibrate_zones.py
# Click the four corners of each approach arm, press 's' to save
```

---

## ⚙️ Configuration

All runtime settings live in `config.json`:

| Key | Description |
|-----|-------------|
| `active_scenario` | Which scenario's zones and video list to use (e.g. `"traffic_test"`) |
| `yolo_model` | Path to the YOLOv8 weights file |
| `confidence_threshold` | Detection confidence cutoff (default `0.3`) |
| `api_url` | Endpoint the vision detector POSTs counts to |
| `scenarios` | Named scenario objects, each with `source`/`video_list` and `zones` |

**Switching to a live camera:**

1. Set `"active_scenario": "live_camera"` in `config.json`.
2. Replace the `source` value in the `live_camera` scenario with your RTSP URL, webcam index, or HTTP stream URL.
3. Run `python vision/calibrate_zones.py` with the live feed to update the zone polygons.

---

## 📈 Trained Models

Models are loaded in priority order (first found wins):

| Priority | File | Notes |
|----------|------|-------|
| 1 | `models/best_model_2.zip` | Best eval checkpoint (latest Colab run) |
| 2 | `models/best_model.zip` | Best eval checkpoint (earlier run) |
| 3 | `models/ppo_traffic_agent_refined_4.zip` | Final step — latest Colab run |
| 4 | `models/ppo_traffic_agent_refined_3.zip` | Final step — earlier run |
| 5 | `models/ppo_traffic_agent_refined_2.zip` | |
| 6 | `models/ppo_traffic_agent_refined.zip` | Initial Colab-trained model |
| 7 | `models/ppo_traffic_agent.zip` | Local training baseline |

> **Note:** The current best models were trained before the per-lane congestion-weighting and outbound-flow normalisation were added to the reward function. A re-training run in Colab is recommended for optimal performance.

---

## 📚 Documentation

| File | Contents |
|------|----------|
| [PROGRESS.md](PROGRESS.md) | Phase-by-phase completion checklist |
| [CHANGES.md](CHANGES.md) | Detailed changelog of every improvement |
| [DEV_LOG.md](DEV_LOG.md) | Chronological development log (step-by-step) |
| [CHALLENGES.md](CHALLENGES.md) | Resolved issues and known problems |
| [GEMINI_ANALYSIS_AND_PROPOSALS.md](GEMINI_ANALYSIS_AND_PROPOSALS.md) | Architecture audit and next-steps roadmap |

---

## 🛣️ Roadmap

Short-term (next sprint):
- [ ] Retrain PPO agent with updated reward formula
- [ ] Add API-key / JWT authentication to `api/main.py`
- [ ] Health-aware process supervision in `launch_system.py` (auto-restart crashed workers)

Medium-term:
- [ ] SQLite persistence layer for dashboard history
- [ ] In-dashboard zone recalibration UI

Long-term (deferred):
- [ ] Multi-junction API schema and Multi-Agent RL (MARL)
- [ ] Green-wave coordination across junctions
