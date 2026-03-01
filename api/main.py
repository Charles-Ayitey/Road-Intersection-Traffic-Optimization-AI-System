from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI()

def get_empty_state():
    return {
        "counts": {"North": 0, "South": 0, "East": 0, "West": 0},
        "current_phase": 0,
        "last_vision_update": 0.0,
        "last_agent_action": 0,
        "system_status": "Starting...",
        "mode": "AI Controlled",
        "manual_phase": 0
    }

traffic_system_state = get_empty_state()

class VisionUpdate(BaseModel):
    counts: Dict[str, int]
    timestamp: float

class AgentAction(BaseModel):
    action: int
    phase: int

class ModeUpdate(BaseModel):
    mode: str  # "AI Controlled" | "Fixed Timing" | "Manual Override"

class PhaseUpdate(BaseModel):
    phase: int  # 0 = NS Green, 2 = EW Green

@app.get("/")
def read_root():
    return {"status": "Online", "latency": time.time() - traffic_system_state["last_vision_update"]}

@app.get("/reset")
def reset_state():
    global traffic_system_state
    traffic_system_state = get_empty_state()
    return {"status": "cleared"}

@app.post("/update_counts")
def update_counts(data: VisionUpdate):
    global traffic_system_state
    for direction, count in data.counts.items():
        if direction in traffic_system_state["counts"]:
            traffic_system_state["counts"][direction] = count
    traffic_system_state["last_vision_update"] = data.timestamp
    traffic_system_state["system_status"] = "Active"
    return {"status": "ok"}

@app.post("/set_mode")
def set_mode(data: ModeUpdate):
    global traffic_system_state
    valid_modes = {"AI Controlled", "Fixed Timing", "Manual Override"}
    if data.mode not in valid_modes:
        return {"status": "error", "message": f"Invalid mode. Choose from: {valid_modes}"}
    traffic_system_state["mode"] = data.mode
    log.info(f"Mode changed to: {data.mode}")
    return {"status": "ok", "mode": data.mode}

@app.post("/set_phase")
def set_phase(data: PhaseUpdate):
    """Used by the dashboard in Manual Override mode to directly command a phase."""
    global traffic_system_state
    if data.phase not in [0, 2]:
        return {"status": "error", "message": "Phase must be 0 (NS Green) or 2 (EW Green)"}
    traffic_system_state["manual_phase"] = data.phase
    log.info(f"Manual phase set to: {data.phase}")
    return {"status": "ok", "manual_phase": data.phase}

@app.get("/get_state")
def get_state():
    counts = traffic_system_state["counts"]
    return {
        "observation": [counts["North"], counts["South"], counts["East"], counts["West"], traffic_system_state["current_phase"]],
        "is_stale": (time.time() - traffic_system_state["last_vision_update"]) > 5.0
    }

@app.post("/set_action")
def set_action(data: AgentAction):
    global traffic_system_state
    traffic_system_state["current_phase"] = data.phase
    return {"status": "ok"}

@app.get("/dashboard_data")
def dashboard_data():
    return traffic_system_state

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
