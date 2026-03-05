# 🧠 Smart Traffic System: Architectural Audit & Evolution Strategy
**Author:** Gemini CLI  
**Date:** March 5, 2026  
**Project:** Smart Traffic Junction System

This document outlines the critical "pain points" identified during a comprehensive codebase audit and proposes specific technical solutions to move the system toward a production-ready state.

---

## 🚩 Critical Pain Points

### 1. **Episodic Memory Loss (Dashboard Persistence)**
- **Problem:** The Streamlit dashboard uses in-memory `deque` objects. Refreshing the browser or restarting the script wipes all historical data, alerts, and performance trends.
- **Impact:** Impossible to perform post-incident analysis or long-term performance auditing without a screen recorder.

### 2. **"Single-Minded" Architecture (Multi-Junction Support)**
- **Problem:** The API, Controller, and Simulation logic are hardcoded for a single intersection ID (`center`).
- **Impact:** Scaling to a city-wide grid would require duplicating the entire software stack for every intersection, preventing "Green Wave" coordination.

### 3. **The "Open Door" API (Security)**
- **Problem:** `api/main.py` has zero authentication. Anyone on the local network can send a POST request to override traffic lights.
- **Impact:** High vulnerability to "denial-of-service" attacks (e.g., setting all directions to Red) or malicious control.

### 4. **Fragile Process Lifecycle (Orchestration)**
- **Problem:** `launch_system.py` starts 4 subprocesses but never monitors them. If the Vision Pipeline crashes (e.g., camera disconnect), the AI Controller continues blindly with stale data.
- **Impact:** Unreliable for "lights-out" 24/7 operation.

### 5. **Static Vision Calibration**
- **Problem:** ROI zones are defined in a static JSON. If a camera shifts by 5 degrees due to wind or vibration, the counts become inaccurate.
- **Impact:** Gradual "drift" in accuracy leading to sub-optimal traffic decisions.

---

## 🛠️ Proposed Solutions

### **A. Persistent Data Layer (Solves Issue 1)**
- **Action:** Integrate a lightweight **SQLite** database into the Data Bus (API).
- **Technical Detail:** 
    - Use `SQLAlchemy` or `aiosqlite` in `api/main.py`.
    - Every 5 seconds, commit the current state (counts, phase, reward) to a `history` table.
    - Update `dashboard/app.py` to query the last 24 hours of data on startup.

### **B. Coordinated "Network" Mode (Solves Issue 2)**
- **Action:** Refactor the API state from a single dictionary to a map of junction IDs.
- **Technical Detail:** 
    - API state: `{"junctions": {"J1": {...}, "J2": {...}}}`.
    - Update the AI Controller to accept a `--junction-id` argument.
    - This allows multiple controllers to register with one Data Bus, enabling future "Multi-Agent RL" (MARL) where agents talk to each other.

### **C. JWT-Based Control Guard (Solves Issue 3)**
- **Action:** Add **FastAPI Security** dependencies.
- **Technical Detail:** 
    - Implement a simple API Key or Bearer Token requirement for `/set_mode` and `/set_action` endpoints.
    - Store the key in a `.env` file (never in `config.json`).
    - The Dashboard and AI Controller will include this header in their requests.

### **D. Health-Aware Orchestration (Solves Issue 4)**
- **Action:** Rewrite `launch_system.py` using a supervisor pattern.
- **Technical Detail:** 
    - Use a loop that checks `proc.poll()` for all 4 subprocesses.
    - Implement "Auto-Restart" with exponential backoff (max 5 retries).
    - If a component fails permanently, the API should broadcast a `SYSTEM_ERROR` state, forcing all traffic lights to a "Safe Flash Yellow" mode.

### **E. In-Dashboard Calibration (Solves Issue 5)**
- **Action:** Move `calibrate_zones.py` logic into a Streamlit component.
- **Technical Detail:** 
    - Use `streamlit-webrtc` or a simple image-canvas component.
    - Allow an operator to "Live Adjust" ROI boundaries while seeing the YOLOv8 detections overlaid.
    - Changes should be pushed to the API and saved to `config.json` immediately.

---

## 📈 Suggested Roadmap

| Priority | Task | Target Component |
| :--- | :--- | :--- |
| **High** | **Process Supervision** | `launch_system.py` |
| **High** | **API Authentication** | `api/main.py` |
| **Medium** | **SQLite Persistence** | `api/main.py` |
| **Medium** | **Multi-Junction Schema** | `api/main.py` |
| **Low** | **Dashboard Calibration** | `dashboard/app.py` |

---
*End of Analysis*
