"""
Max Pressure Controller
=======================
A provably throughput-optimal, model-free fallback strategy.

Principle
---------
For each candidate phase, pressure is defined as:
    pressure = sum(inbound queues) - sum(outbound queues)

The phase with the highest pressure is served next.  When the
inbound queue on an approach is large and the downstream lane is
clear, pressure is high — meaning there is both demand to serve
AND room to put vehicles.  This naturally prevents spillback and
queue overflow without needing a hand-tuned reward.

Usage in live_controller.py
----------------------------
    from ai_agent.max_pressure import max_pressure_action, compute_pressure

    mp_action, pressures = max_pressure_action()
    # mp_action: 0 = NORTH-SOUTH, 1 = EAST-WEST
    # pressures: dict of {0: float, 1: float} for logging
"""

import logging
import traci
from traci.exceptions import FatalTraCIError

log = logging.getLogger(__name__)

# Inbound approach lanes  → the lanes where vehicles queue before the junction
# Outbound departure lanes → the lanes vehicles enter after clearing the junction
# Action 0 = NORTH-SOUTH phase (SUMO phase 0):  N and S approaches green
# Action 1 = EAST-WEST   phase (SUMO phase 2):  E and W approaches green
PHASE_LANE_MAP = {
    0: {  # NORTH-SOUTH
        "in":  ["n2c_0", "s2c_0"],
        "out": ["c2n_0", "c2s_0"],
    },
    1: {  # EAST-WEST
        "in":  ["e2c_0", "w2c_0"],
        "out": ["c2e_0", "c2w_0"],
    },
}


def compute_pressure(action: int) -> float:
    """
    Pressure for a given action (0=NS, 1=EW).

    Returns a float.  Positive means vehicles are queuing inbound
    with room downstream; negative means downstream is congested.
    """
    in_lanes  = PHASE_LANE_MAP[action]["in"]
    out_lanes = PHASE_LANE_MAP[action]["out"]

    try:
        inbound  = sum(int(traci.lane.getLastStepHaltingNumber(l) or 0) for l in in_lanes)
        outbound = sum(int(traci.lane.getLastStepHaltingNumber(l) or 0) for l in out_lanes)
    except Exception as e:
        log.debug(f"compute_pressure: TraCI unavailable ({e}); returning 0.0")
        return 0.0

    return float(inbound - outbound)

def max_pressure_action() -> tuple[int, dict]:
    """
    Returns (best_action, pressures_dict).

    best_action  : 0 (NORTH-SOUTH) or 1 (EAST-WEST)
    pressures    : {0: <float>, 1: <float>} — useful for dashboard/logging
    """
    pressures = {action: compute_pressure(action) for action in PHASE_LANE_MAP}
    best = max(pressures, key=pressures.get)
    return best, pressures


def should_override(model_action: int, threshold: float = 5.0) -> tuple[bool, int, dict]:
    """
    Decides whether to override the model's chosen action with max pressure.

    Override triggers when:
      - The max pressure recommendation differs from the model's action, AND
      - The pressure difference between the two phases exceeds `threshold`
        (avoids flip-flopping when pressures are nearly equal).

    Returns:
      (override: bool, recommended_action: int, pressures: dict)
    """
    try:
        mp_action, pressures = max_pressure_action()
    except (FatalTraCIError, ConnectionResetError, OSError) as e:
        log.debug(f"should_override: TraCI unavailable ({e}); skipping override")
        return False, model_action, {0: 0.0, 1: 0.0}

    if mp_action == model_action:
        return False, model_action, pressures

    pressure_diff = pressures[mp_action] - pressures[model_action]

    if pressure_diff >= threshold:
        log.warning(
            f"Max pressure override: model→{'NS' if model_action == 0 else 'EW'} "
            f"(p={pressures[model_action]:.1f})  →  "
            f"mp→{'NS' if mp_action == 0 else 'EW'} "
            f"(p={pressures[mp_action]:.1f})  Δ={pressure_diff:.1f}"
        )
        return True, mp_action, pressures

    return False, model_action, pressures
