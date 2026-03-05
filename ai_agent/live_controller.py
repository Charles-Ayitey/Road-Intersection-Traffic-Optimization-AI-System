import os
import sys
import time
import logging
import requests
import numpy as np
import traci
from datetime import datetime
from stable_baselines3 import PPO

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_agent.sumo_env import SumoTrafficEnv
from ai_agent.max_pressure import should_override

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
log = logging.getLogger(__name__)

API_URL = "http://localhost:8000"
# Minimum pressure advantage the max-pressure controller must have over the
# model's chosen phase before it overrides.  Set higher to trust the model more,
# lower to lean on max pressure more aggressively.
MP_OVERRIDE_THRESHOLD = 5.0
# Search order: try refined model first, fall back to base training output
MODEL_SEARCH_PATHS = [
    os.path.join("models", "best_model_2.zip"),
    os.path.join("models", "ppo_traffic_agent_refined_4.zip"),  # final model (throughput reward)
    os.path.join("models", "best_model.zip"),                   # best eval checkpoint (throughput reward)
    os.path.join("models", "ppo_traffic_agent_refined_3.zip"),  # final model (throughput reward)
    os.path.join("models", "ppo_traffic_agent_refined_2.zip"),
    os.path.join("models", "ppo_traffic_agent_refined.zip"),
    os.path.join("models", "ppo_traffic_agent.zip"),
]
CONFIG_PATH = os.path.join("simulation", "junction.sumocfg")
FIXED_TIMING_INTERVAL = 30  # steps per phase in Fixed Timing mode

class LiveRLController:
    def __init__(self, config_path):
        self.config_path = config_path
        self.env = SumoTrafficEnv(self.config_path, use_gui=True)
        self.model = self._load_model()

    def _load_model(self):
        for path in MODEL_SEARCH_PATHS:
            if os.path.exists(path):
                model = PPO.load(path)
                self.model_path = path
                log.info(f"AI Brain Loaded: {path}")
                return model
        raise FileNotFoundError(
            f"No trained model found. Searched: {MODEL_SEARCH_PATHS}\n"
            "Run ai_agent/train.py first to generate a model."
        )

    def _get_mode(self):
        try:
            r = requests.get(f"{API_URL}/dashboard_data", timeout=0.5)
            r.raise_for_status()
            return r.json().get("mode", "AI Controlled")
        except requests.RequestException:
            return "AI Controlled"  # safe default

    def get_state_from_api(self):
        try:
            r = requests.get(f"{API_URL}/get_state", timeout=0.5)
            r.raise_for_status()
            return np.array(r.json()["observation"], dtype=np.float32)
        except requests.RequestException as e:
            log.warning(f"Vision API unavailable ({e}); using SUMO state.")
        return None

    def _merge_obs(self, obs_vision, obs_sim):
        """Merge vision and SUMO observations per direction.

        The camera covers only part of the junction, so vision often reports
        E=0 / W=0 even when vehicles are queuing on those approaches.  We
        use vision counts where vision actively detects vehicles (> 0) and
        fall back to SUMO's ground-truth counts for any direction that vision
        reports as zero.  This prevents the agent from being blind to E/W
        queues and always choosing NORTH-SOUTH.
        """
        if obs_vision is None:
            return obs_sim
        merged = obs_sim.copy()     # starts with full 9-element SUMO obs
        for i in range(4):          # indices 0-3: queue counts from vision if non-zero
            if obs_vision[i] > 0:
                merged[i] = obs_vision[i]
        # Indices 4-7 (upstream occupancy) and 8 (phase) are always from SUMO
        merged[8] = obs_sim[8]
        return merged

    def post_phase_to_api(self, phase_id):
        # Skip transient yellow phases (1, 3) — the dashboard only needs to
        # know the active green phase (0=NS, 2=EW); yellow is too brief to display.
        if int(phase_id) not in (0, 2):
            return
        try:
            requests.post(f"{API_URL}/set_action", json={"action": 0, "phase": int(phase_id)}, timeout=0.5)
        except requests.RequestException as e:
            log.debug(f"Phase post failed: {e}")

    def _fixed_timing_action(self, step):
        """Alternate NS/EW every FIXED_TIMING_INTERVAL steps, medium duration."""
        phase = 0 if (step // FIXED_TIMING_INTERVAL) % 2 == 0 else 1
        return np.array([phase, 1], dtype=np.int64)  # duration_level 1 = 15 s

    def _manual_action_from_api(self):
        """Read the phase the dashboard operator has set, medium duration."""
        try:
            r = requests.get(f"{API_URL}/dashboard_data", timeout=0.5)
            r.raise_for_status()
            phase = 0 if r.json().get("manual_phase", 0) in [0, 1] else 1
        except requests.RequestException:
            phase = 0
        return np.array([phase, 1], dtype=np.int64)  # duration_level 1 = 15 s

    def _save_results(self, records, start_time, model_path, override_count=0):
        """Write a summary report to results/simulation_<timestamp>.txt."""
        os.makedirs("results", exist_ok=True)
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join("results", f"simulation_{timestamp}.txt")

        total_steps = len(records)
        rewards      = [r["reward"]   for r in records]
        q_n          = [r["q_n"]       for r in records]
        q_s          = [r["q_s"]       for r in records]
        q_e          = [r["q_e"]       for r in records]
        q_w          = [r["q_w"]       for r in records]
        mode_counts  = {}
        for r in records:
            mode_counts[r["mode"]] = mode_counts.get(r["mode"], 0) + 1

        with open(out_path, "w") as f:
            # ── Header ──────────────────────────────────────────────
            f.write("=" * 70 + "\n")
            f.write("  SMART TRAFFIC JUNCTION SYSTEM — SIMULATION RESULTS\n")
            f.write("=" * 70 + "\n")
            f.write(f"  Run started : {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Run ended   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Model       : {model_path}\n")
            f.write(f"  Config      : {self.config_path}\n")
            f.write("=" * 70 + "\n\n")

            # ── Summary statistics ──────────────────────────────────
            f.write("SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Total steps          : {total_steps}\n")
            f.write(f"  Total reward         : {sum(rewards):.2f}\n")
            f.write(f"  Average reward/step  : {sum(rewards)/total_steps:.2f}\n")
            f.write(f"  Best  reward (step)  : {max(rewards):.2f}  (step {rewards.index(max(rewards))+1})\n")
            f.write(f"  Worst reward (step)  : {min(rewards):.2f}  (step {rewards.index(min(rewards))+1})\n")
            f.write(f"  Max pressure overrides: {override_count} steps ({100*override_count/total_steps:.1f}%)\n")
            f.write("\n")
            f.write("  Average queue lengths:\n")
            f.write(f"    North : {sum(q_n)/total_steps:.2f}  (peak {max(q_n)})\n")
            f.write(f"    South : {sum(q_s)/total_steps:.2f}  (peak {max(q_s)})\n")
            f.write(f"    East  : {sum(q_e)/total_steps:.2f}  (peak {max(q_e)})\n")
            f.write(f"    West  : {sum(q_w)/total_steps:.2f}  (peak {max(q_w)})\n")
            f.write("\n")
            f.write("  Mode breakdown:\n")
            for mode, count in sorted(mode_counts.items()):
                f.write(f"    {mode:20}: {count} steps ({100*count/total_steps:.1f}%)\n")
            f.write("\n")

            # ── Per-step log ────────────────────────────────────────
            f.write("PER-STEP LOG\n")
            f.write("-" * 80 + "\n")
            f.write(f"{'Step':>5}  {'Mode':<18} {'Action':<13} {'Dur':>5} {'N':>4} {'S':>4} {'E':>4} {'W':>4}  {'Reward':>9}\n")
            f.write("-" * 80 + "\n")
            for r in records:
                f.write(
                    f"{r['step']:>5}  {r['mode']:<18} {r['action']:<13} "
                    f"{r.get('duration', '?'):>5} "
                    f"{r['q_n']:>4} {r['q_s']:>4} {r['q_e']:>4} {r['q_w']:>4}  "
                    f"{r['reward']:>9.2f}\n"
                )
            f.write("-" * 80 + "\n")

        log.info(f"Results saved → {out_path}")
        return out_path

    def run(self, steps=1000):
        log.info("=" * 60)
        log.info("STARTING LIVE SMART TRAFFIC CONTROL (GHANA EDITION)")
        log.info("=" * 60)

        start_time = datetime.now()
        records = []
        override_count = 0
        obs_sim, _ = self.env.reset()

        for i in range(steps):
            overridden = False   # reset each step; set True by max pressure if triggered
            mode = self._get_mode()
            obs_vision = self.get_state_from_api()
            current_obs = self._merge_obs(obs_vision, obs_sim)

            # Choose action based on operating mode
            if mode == "Fixed Timing":
                action = self._fixed_timing_action(i)
            elif mode == "Manual Override":
                action = self._manual_action_from_api()
            else:  # AI Controlled (default)
                action, _ = self.model.predict(current_obs, deterministic=True)

                # Max pressure override: only the phase dimension is overridden;
                # the model's chosen duration is preserved.
                try:
                    if traci.isLoaded():
                        overridden, mp_phase, pressures = should_override(
                            int(action[0]), threshold=MP_OVERRIDE_THRESHOLD
                        )
                        if overridden:
                            action = np.array([mp_phase, action[1]], dtype=np.int64)
                            override_count += 1
                except Exception as mp_err:
                    log.warning(f"Max pressure check failed (TraCI gone?): {mp_err}")

            phase_idx   = int(action[0])
            dur_idx     = int(action[1]) if hasattr(action, '__len__') else 1
            action_name = "NORTH-SOUTH" if phase_idx == 0 else "EAST-WEST"
            dur_label   = ["5s", "15s", "30s"][dur_idx]
            # Post the intended green phase to the API BEFORE running the
            # simulation step so the dashboard shows it for the full step duration.
            self.post_phase_to_api(phase_idx * 2)
            obs_sim, reward, term, trunc, _ = self.env.step(action, callback=self.post_phase_to_api)

            q = current_obs[:4]
            records.append({
                "step"      : i + 1,
                "mode"      : mode,
                "action"    : action_name,
                "duration"  : dur_label,
                "q_n"       : int(q[0]),
                "q_s"       : int(q[1]),
                "q_e"       : int(q[2]),
                "q_w"       : int(q[3]),
                "reward"    : float(reward),
                "mp_override": overridden if mode == "AI Controlled" else False,
            })

            log.info(
                f"Step {i+1:3} | Mode: {mode:16} | ACTION: {action_name:11} [{dur_label}] | "
                f"QUEUES [N:{int(q[0]):2} S:{int(q[1]):2} E:{int(q[2]):2} W:{int(q[3]):2}] | "
                f"REWARD: {reward:7.2f}"
                + (" [MP]" if records[-1]["mp_override"] else "")
            )

            self.post_phase_to_api(self.env.current_phase)
            time.sleep(0.5)

            if term or trunc:
                log.info("Simulation episode complete.")
                break

        self.env.close()
        if records:
            self._save_results(records, start_time, self.model_path, override_count)
        log.info("=" * 60 + "\nTest Complete.\n")


if __name__ == "__main__":
    controller = LiveRLController(CONFIG_PATH)
    controller.run()
