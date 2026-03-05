# =============================================================
# Smart Traffic Junction System — Colab Training Script
# Run the shell commands below in separate Colab cells first,
# then run this script as a single cell.
# =============================================================
#
# STEP 1 — Run in a Colab cell (install dependencies):
#
#   !sudo add-apt-repository ppa:sumo/stable -y
#   !sudo apt-get update -q
#   !sudo apt-get install -y sumo sumo-tools
#   !pip install -q stable-baselines3[extra] gymnasium
#
# STEP 2 — Upload and unzip the project:
#
#   from google.colab import files
#   files.upload()          # upload traffic_project.zip
#   !unzip -q traffic_project.zip -d .
#
# STEP 3 — Run this script:
#
#   exec(open("colab_train.py").read())
#   OR just paste the whole file into a cell.
# =============================================================

import os
import sys
import random

# ── Ubuntu / Colab paths ──────────────────────────────────────
os.environ["SUMO_HOME"] = "/usr/share/sumo"
SUMO_TOOLS = "/usr/share/sumo/tools"
if SUMO_TOOLS not in sys.path:
    sys.path.append(SUMO_TOOLS)

import traci
import shutil
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback

# Duration multipliers: level 0 = 5 s, level 1 = 15 s, level 2 = 30 s
_DURATION_STEPS = [1, 3, 6]

# ── Environment ───────────────────────────────────────────────
class SumoTrafficEnv(gym.Env):
    """
    4-way junction RL environment.
    When randomise_demand=True, each episode gets randomised
    vehicle flow rates so the agent learns to handle any traffic
    condition — not just one fixed scenario.
    """

    def __init__(self, sumocfg_path, delta_time=5, randomise_demand=True):
        super().__init__()
        # Always use forward slashes — Linux requirement
        self.sumocfg_path = sumocfg_path.replace("\\", "/")
        self.sim_dir      = os.path.dirname(os.path.abspath(sumocfg_path))
        self.delta_time   = delta_time
        self.randomise    = randomise_demand
        self.sumo_binary  = "sumo"

        # Action: MultiDiscrete([2, 3])
        #   dim 0 — phase    : 0=NS, 1=EW
        #   dim 1 — duration : 0=5 s, 1=15 s, 2=30 s
        self.action_space = spaces.MultiDiscrete([2, 3])

        # Obs (9): [Q_N, Q_S, Q_E, Q_W, Occ_N, Occ_S, Occ_E, Occ_W, phase]
        self.observation_space = spaces.Box(
            low=np.zeros(9, dtype=np.float32),
            high=np.array([100,100,100,100, 100,100,100,100, 1], dtype=np.float32),
            dtype=np.float32
        )

        self.tls_id        = "center"
        self.lanes         = ["n2c_0", "s2c_0", "e2c_0", "w2c_0"]
        self.outbound_lanes = ["c2n_0", "c2s_0", "c2e_0", "c2w_0"]
        self.detector_ids  = ["det_n", "det_s", "det_e", "det_w"]
        self.current_phase = 0
        self.yellow_dur    = 3
        self._write_add_xml()

    # ── Upstream detector setup ───────────────────────────────
    def _write_add_xml(self):
        """Write junction.add.xml with the OS-correct null device."""
        null_dev = os.devnull.replace("\\", "/")
        add_path = os.path.join(self.sim_dir, "junction.add.xml")
        with open(add_path, "w") as f:
            f.write(f"""<additionals>
    <inductionLoop id="det_n" lane="n2c_0" pos="33" freq="5" file="{null_dev}"/>
    <inductionLoop id="det_s" lane="s2c_0" pos="33" freq="5" file="{null_dev}"/>
    <inductionLoop id="det_e" lane="e2c_0" pos="33" freq="5" file="{null_dev}"/>
    <inductionLoop id="det_w" lane="w2c_0" pos="33" freq="5" file="{null_dev}"/>
</additionals>
""")

    # ── Domain randomisation ──────────────────────────────────
    def _write_random_routes(self):
        """
        Overwrite junction.rou.xml with random per-direction flows.
        Gives the agent varied scenarios in every training episode.
        """
        ns = random.randint(50, 900)
        sn = random.randint(50, 900)
        ew = random.randint(50, 900)
        we = random.randint(50, 900)
        xml = f"""<routes>
    <vType id="car" accel="2.6" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="13.89"/>
    <route id="n2s" edges="n2c c2s"/>
    <route id="s2n" edges="s2c c2n"/>
    <route id="e2w" edges="e2c c2w"/>
    <route id="w2e" edges="w2c c2e"/>
    <flow id="f_n2s" begin="0" end="3600" vehsPerHour="{ns}" route="n2s" type="car"/>
    <flow id="f_s2n" begin="0" end="3600" vehsPerHour="{sn}" route="s2n" type="car"/>
    <flow id="f_e2w" begin="0" end="3600" vehsPerHour="{ew}" route="e2w" type="car"/>
    <flow id="f_w2e" begin="0" end="3600" vehsPerHour="{we}" route="w2e" type="car"/>
</routes>
"""
        route_file = os.path.join(self.sim_dir, "junction.rou.xml")
        with open(route_file, "w") as f:
            f.write(xml)

    # ── Gymnasium interface ───────────────────────────────────
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        try:
            traci.close()
        except Exception:
            pass

        if self.randomise:
            self._write_random_routes()

        traci.start([
            self.sumo_binary, "-c", self.sumocfg_path,
            "--no-warnings", "--waiting-time-memory", "1000",
            "--seed", str(seed) if seed is not None else "42",
            "--start"
        ])
        self.current_phase = 0
        traci.trafficlight.setPhase(self.tls_id, 0)
        return self._get_obs(), {}

    def _get_obs(self):
        queues   = [traci.lane.getLastStepHaltingNumber(l) for l in self.lanes]
        try:
            upstream = [traci.inductionloop.getLastStepOccupancy(d) for d in self.detector_ids]
        except Exception:
            upstream = [0.0, 0.0, 0.0, 0.0]
        ai_phase = 0 if self.current_phase in [0, 1] else 1
        return np.array(queues + upstream + [float(ai_phase)], dtype=np.float32)

    def step(self, action):
        if hasattr(action, '__len__'):
            phase_action   = int(action[0])
            duration_steps = _DURATION_STEPS[int(action[1])] * self.delta_time
        else:
            phase_action   = int(action)
            duration_steps = self.delta_time

        target = 0 if phase_action == 0 else 2

        if target != self.current_phase:
            yellow = 1 if self.current_phase == 0 else 3
            traci.trafficlight.setPhase(self.tls_id, yellow)
            for _ in range(self.yellow_dur):
                traci.simulationStep()
            self.current_phase = target
            traci.trafficlight.setPhase(self.tls_id, target)

        # Snapshot queues before running the green phase
        queues_before = [traci.lane.getLastStepHaltingNumber(l) for l in self.lanes]

        for _ in range(duration_steps):
            traci.simulationStep()

        obs             = self._get_obs()
        queues_after    = obs[:4]
        # Per-lane congestion weight: clearing a heavily backed-up lane earns more
        max_q = max(queues_before) if max(queues_before) > 0 else 1
        vehicles_cleared = sum(
            max(0, int(b) - int(a)) * (1.0 + int(b) / max_q)
            for b, a in zip(queues_before, queues_after)
        )
        # Normalise outbound_flow by number of delta_time chunks in this phase
        chunks          = duration_steps / self.delta_time
        outbound_flow   = sum(
            traci.lane.getLastStepVehicleNumber(l) for l in self.outbound_lanes
        ) / chunks
        remaining_queue = float(np.sum(queues_after))
        overflow        = sum(max(0, int(q) - 10) ** 2 for q in queues_after)
        reward          = (
            (vehicles_cleared + 0.5 * outbound_flow)
            - 0.3 * remaining_queue
            - 0.5 * overflow
        )
        terminated = traci.simulation.getMinExpectedNumber() <= 0
        truncated  = traci.simulation.getTime() > 3600
        return obs, reward, terminated, truncated, {}

    def close(self):
        try:
            traci.close()
        except Exception:
            pass


# ── Training ──────────────────────────────────────────────────
def run_training():
    config_path = "simulation/junction.sumocfg"

    if not os.path.exists(config_path):
        print(
            "ERROR: simulation/junction.sumocfg not found.\n"
            "Make sure you uploaded and unzipped traffic_project.zip first.\n"
            "Expected structure after unzip:\n"
            "  simulation/junction.sumocfg\n"
            "  simulation/junction.net.xml\n"
            "  simulation/junction.rou.xml\n"
            "  simulation/junction.nod.xml\n"
            "  simulation/junction.edg.xml"
        )
        return

    print("=== Environment check ===")
    print(f"  SUMO binary : {shutil.which('sumo') or 'NOT FOUND — check installation'}")
    print(f"  Config file : {os.path.abspath(config_path)}")
    print(f"  Domain rand : enabled (50–900 veh/hr per direction, randomised each episode)")
    print()

    # Training env — domain randomisation ON
    train_env = SumoTrafficEnv(config_path, randomise_demand=True)

    # Eval env — fixed moderate load so metrics are comparable across runs
    eval_env = SumoTrafficEnv(config_path, randomise_demand=False)

    # Evaluate every 25,000 steps and keep the best checkpoint
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path="./models/",
        log_path="./logs/",
        eval_freq=25_000,
        n_eval_episodes=3,
        deterministic=True,
        verbose=1
    )

    model = PPO(
        "MlpPolicy",
        train_env,
        verbose=1,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        tensorboard_log="./logs/",
    )

    TOTAL_STEPS = 300_000
    print(f"Starting training ({TOTAL_STEPS:,} steps)...")
    model.learn(total_timesteps=TOTAL_STEPS, callback=eval_callback, tb_log_name="ppo_traffic_v2")

    # Save as 'refined' so the live controller finds it immediately
    model.save("ppo_traffic_agent_refined")
    print()
    print("Training complete!")
    print("  Final model  : ppo_traffic_agent_refined.zip  <- download this")
    print("  Best model   : models/best_model.zip          <- download this too")
    print()
    print("Download both and place in the models/ folder on your local machine.")

    train_env.close()
    eval_env.close()


if __name__ == "__main__":
    run_training()
