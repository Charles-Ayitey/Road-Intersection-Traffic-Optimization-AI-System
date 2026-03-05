import shutil
import os
import sys
import random
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import traci

# Duration multipliers for each duration-level action.
# Level 0 = 1 × delta_time = 5 s  (short green — high-flow phases)
# Level 1 = 3 × delta_time = 15 s (medium — default)
# Level 2 = 6 × delta_time = 30 s (long    — heavy-load phases)
_DURATION_STEPS = [1, 3, 6]

class SumoTrafficEnv(gym.Env):
    def __init__(self, sumocfg_path, use_gui=False, delta_time=5, randomise_demand=False):
        super(SumoTrafficEnv, self).__init__()

        self.sumocfg_path = sumocfg_path
        # Normalise to forward slashes for cross-platform SUMO compatibility
        self.sumocfg_path = self.sumocfg_path.replace("\\", "/")
        self.sim_dir = os.path.dirname(os.path.abspath(sumocfg_path))
        self.use_gui = use_gui
        self.delta_time = delta_time
        self.randomise_demand = randomise_demand

        binary_name = "sumo-gui" if use_gui else "sumo"
        self.sumo_binary = shutil.which(binary_name)

        if not self.sumo_binary:
            if 'SUMO_HOME' in os.environ:
                self.sumo_binary = os.path.join(os.environ['SUMO_HOME'], 'bin', binary_name)
                if os.name == 'nt' and not self.sumo_binary.endswith('.exe'):
                    self.sumo_binary += ".exe"
            else:
                self.sumo_binary = 'sumo'

        if 'SUMO_HOME' in os.environ:
            tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
            if tools not in sys.path:
                sys.path.append(tools)

        # Action space — two independent discrete dimensions:
        #   dim 0: phase selection  0=NORTH-SOUTH, 1=EAST-WEST
        #   dim 1: duration level   0=5 s, 1=15 s, 2=30 s
        self.action_space = spaces.MultiDiscrete([2, 3])

        # Observation space (9 elements):
        #   [Q_N, Q_S, Q_E, Q_W,          ← stop-line queue counts (0-100 veh)
        #    Occ_N, Occ_S, Occ_E, Occ_W,  ← upstream loop occupancy (0-100 %)
        #    phase]                         ← current AI phase (0=NS, 1=EW)
        self.observation_space = spaces.Box(
            low=np.zeros(9, dtype=np.float32),
            high=np.array([100, 100, 100, 100, 100, 100, 100, 100, 1], dtype=np.float32),
            dtype=np.float32
        )

        self.tls_id = "center"
        # Inbound approach lanes (vehicles queuing before the stop line)
        self.lanes = ["n2c_0", "s2c_0", "e2c_0", "w2c_0"]
        # Outbound departure lanes (vehicles leaving the junction)
        self.outbound_lanes = ["c2n_0", "c2s_0", "c2e_0", "c2w_0"]
        # Upstream induction loop detectors (~60 m before stop line)
        self.detector_ids = ["det_n", "det_s", "det_e", "det_w"]
        self.current_phase = 0
        self.yellow_duration = 3
        # Write junction.add.xml with the correct null-device path for the
        # current OS so SUMO doesn't try to create a literal 'nul' file.
        self._write_add_xml()

    def _write_add_xml(self):
        """Write simulation/junction.add.xml with the OS-correct null device.

        SUMO's E1 (inductionLoop) detectors must point to an output file; we
        direct output to the null device so no disk I/O accumulates during
        training/live runs.  os.devnull is 'nul' on Windows and '/dev/null'
        on Linux/macOS.
        """
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

    def _generate_random_routes(self):
        """
        Overwrite junction.rou.xml with randomised per-direction flow rates.
        Called at the start of every episode when randomise_demand=True.
        This exposes the agent to a wide range of traffic conditions during training.
        """
        flows = {
            "n2s": random.randint(50, 900),
            "s2n": random.randint(50, 900),
            "e2w": random.randint(50, 900),
            "w2e": random.randint(50, 900),
        }
        xml = f"""<routes>
    <vType id="car" accel="2.6" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="13.89" guiShape="passenger"/>
    <route id="n2s" edges="n2c c2s"/>
    <route id="s2n" edges="s2c c2n"/>
    <route id="e2w" edges="e2c c2w"/>
    <route id="w2e" edges="w2c c2e"/>

    <flow id="f_n2s" begin="0" end="3600" vehsPerHour="{flows['n2s']}" route="n2s" type="car"/>
    <flow id="f_s2n" begin="0" end="3600" vehsPerHour="{flows['s2n']}" route="s2n" type="car"/>
    <flow id="f_e2w" begin="0" end="3600" vehsPerHour="{flows['e2w']}" route="e2w" type="car"/>
    <flow id="f_w2e" begin="0" end="3600" vehsPerHour="{flows['w2e']}" route="w2e" type="car"/>
</routes>
"""
        route_path = os.path.join(self.sim_dir, "junction.rou.xml")
        with open(route_path, "w") as f:
            f.write(xml)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        try: traci.close()
        except: pass

        if self.randomise_demand:
            self._generate_random_routes()

        sumo_cmd = [
            self.sumo_binary, "-c", self.sumocfg_path,
            "--no-warnings", "--waiting-time-memory", "1000",
            "--seed", str(seed) if seed is not None else "42",
            "--start"
        ]

        traci.start(sumo_cmd)
        self.current_phase = 0
        traci.trafficlight.setPhase(self.tls_id, 0)
        return self._get_obs(), {}

    def _get_obs(self):
        queues = [traci.lane.getLastStepHaltingNumber(l) for l in self.lanes]
        try:
            upstream = [traci.inductionloop.getLastStepOccupancy(d) for d in self.detector_ids]
        except Exception:
            upstream = [0.0, 0.0, 0.0, 0.0]  # safe fallback if detectors not loaded
        ai_phase = 0 if self.current_phase in [0, 1] else 1
        return np.array(queues + upstream + [float(ai_phase)], dtype=np.float32)

    def step(self, action, callback=None):
        """
        Extended step that takes a MultiDiscrete action [phase, duration_level].

        action[0] : 0 = NORTH-SOUTH, 1 = EAST-WEST
        action[1] : 0 = 5 s (1×delta_time), 1 = 15 s (3×delta_time),
                    2 = 30 s (6×delta_time)

        Also accepts a plain int 0/1 for backward-compat with manual/fixed-timing.
        """
        if hasattr(action, '__len__'):
            phase_action   = int(action[0])
            duration_steps = _DURATION_STEPS[int(action[1])] * self.delta_time
        else:
            phase_action   = int(action)
            duration_steps = self.delta_time  # default medium

        target_sumo_phase = 0 if phase_action == 0 else 2
        
        # 1. Handle Yellow Transition
        if target_sumo_phase != self.current_phase:
            # NS Green -> NS Yellow (1) or EW Green -> EW Yellow (3)
            yellow_phase = 1 if self.current_phase == 0 else 3
            self.current_phase = yellow_phase
            traci.trafficlight.setPhase(self.tls_id, yellow_phase)
            
            # Report Yellow to API via callback
            if callback: callback(self.current_phase)
            
            for _ in range(self.yellow_duration):
                traci.simulationStep()
            
            # 2. Switch to Target Green
            self.current_phase = target_sumo_phase
            traci.trafficlight.setPhase(self.tls_id, target_sumo_phase)
            if callback: callback(self.current_phase)

        # 3. Snapshot queues BEFORE running green — needed for throughput calculation
        queues_before = [traci.lane.getLastStepHaltingNumber(l) for l in self.lanes]

        # 4. Run Green Duration (variable: 5 s / 15 s / 30 s)
        for _ in range(duration_steps):
            traci.simulationStep()

        obs = self._get_obs()
        queues_after = obs[:4]

        # ── Throughput reward ────────────────────────────────────────────────
        # Per-lane congestion weights: clearing a heavily backed-up lane earns
        # proportionally more reward than clearing a lightly used approach.
        # This corrects the NS-always bias when one direction has persistent
        # high queues — the agent is incentivised to address that direction.
        max_q = max(queues_before) if max(queues_before) > 0 else 1
        vehicles_cleared = sum(
            max(0, int(b) - int(a)) * (1.0 + int(b) / max_q)
            for b, a in zip(queues_before, queues_after)
        )
        # Normalise outbound_flow per delta_time chunk so longer duration phases
        # don't auto-earn higher reward just from more elapsed wall time.
        chunks = duration_steps / self.delta_time
        outbound_flow = sum(
            traci.lane.getLastStepVehicleNumber(l) for l in self.outbound_lanes
        ) / chunks
        # remaining_queue: linear penalty for queue length still waiting
        remaining_queue = float(np.sum(queues_after))
        # overflow_penalty: quadratic penalty for any approach above 10 vehicles
        # to strongly discourage runaway build-up.
        overflow_penalty = sum(max(0, int(q) - 10) ** 2 for q in queues_after)

        reward = (
            (vehicles_cleared + 0.5 * outbound_flow)   # throughput gains
            - 0.3 * remaining_queue                     # queue cost
            - 0.5 * overflow_penalty                    # overflow deterrent
        )
        terminated = traci.simulation.getMinExpectedNumber() <= 0
        truncated = traci.simulation.getTime() > 3600
        
        return obs, reward, terminated, truncated, {}

    def close(self):
        try: traci.close()
        except: pass
