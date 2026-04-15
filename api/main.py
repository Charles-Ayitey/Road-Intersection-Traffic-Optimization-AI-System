from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict
import time
import logging
import sqlite3
import aiosqlite
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# --- SQLite Setup ---
os.makedirs("data", exist_ok=True)
DB_PATH = "data/traffic_history.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS live_traffic_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            north INTEGER,
            south INTEGER,
            east INTEGER,
            west INTEGER,
            current_phase INTEGER,
            mode TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()
# --------------------

app = FastAPI()

def get_empty_state():
    now = time.time()
    return {
        "counts": {"North": 0, "South": 0, "East": 0, "West": 0},
        "current_phase": 0,
        "last_vision_update": 0.0,
        "last_agent_action": 0,
        "system_status": "Starting...",
        "mode": "AI Controlled",
        "manual_phase": 0,
        "last_green_ts": {"0": now, "2": now},
        "active_override": {"phase": None, "expires_at": 0.0}
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

class OverrideRequest(BaseModel):
    phase: int
    duration: int

def record_phase_change(new_phase: int):
    # Only update the timestamp if we are literally changing into this phase
    # Actually, we want to track "since it was last green".
    # So if it's currently green, the wait time is 0.
    # Therefore, we continuously update the TS for the CURRENT green phase.
    pass # Wait, it's better to update last_green_ts continuously for the active phase.

@app.get("/")
def read_root():
    return {"status": "Online", "latency": time.time() - traffic_system_state["last_vision_update"]}

@app.get("/reset")
def reset_state():
    global traffic_system_state
    traffic_system_state = get_empty_state()
    return {"status": "cleared"}

@app.post("/update_counts")
async def update_counts(data: VisionUpdate):
    global traffic_system_state
    for direction, count in data.counts.items():
        if direction in traffic_system_state["counts"]:
            traffic_system_state["counts"][direction] = count
    traffic_system_state["last_vision_update"] = data.timestamp
    traffic_system_state["system_status"] = "Active"
    
    # Update the last green timestamp for whichever phase is currently active
    current_phase = str(traffic_system_state["current_phase"])
    traffic_system_state["last_green_ts"][current_phase] = data.timestamp
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO live_traffic_log (timestamp, north, south, east, west, current_phase, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.timestamp,
                traffic_system_state["counts"]["North"],
                traffic_system_state["counts"]["South"],
                traffic_system_state["counts"]["East"],
                traffic_system_state["counts"]["West"],
                traffic_system_state["current_phase"],
                traffic_system_state["mode"]
            ))
            await db.commit()
    except Exception as e:
        log.error(f"Failed to log to SQLite: {e}")

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

@app.post("/trigger_override")
def trigger_override(data: OverrideRequest):
    """Used for temporary Quick Overrides (like pedestrian or emergency) without fully breaking AI mode."""
    global traffic_system_state
    if data.phase not in [0, 2]:
        return {"status": "error", "message": "Phase must be 0 (NS Green) or 2 (EW Green)"}
    
    expires = time.time() + data.duration
    traffic_system_state["active_override"]["phase"] = data.phase
    traffic_system_state["active_override"]["expires_at"] = expires
    
    log.info(f"Quick override triggered for Phase {data.phase} for {data.duration} seconds.")
    return {"status": "ok", "expires_at": expires}

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

@app.get("/history")
async def get_history(limit: int = 100):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM live_traffic_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return {"status": "ok", "data": [dict(row) for row in rows]}
    except Exception as e:
        log.error(f"Failed to fetch history from SQLite: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
