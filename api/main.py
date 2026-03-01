from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict
import time

app = FastAPI()

def get_empty_state():
    return {
        "counts": {"North": 0, "South": 0, "East": 0, "West": 0},
        "current_phase": 0,
        "last_vision_update": 0.0,
        "last_agent_action": 0,
        "system_status": "Starting..."
    }

traffic_system_state = get_empty_state()

class VisionUpdate(BaseModel):
    counts: Dict[str, int]
    timestamp: float

class AgentAction(BaseModel):
    action: int
    phase: int

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
