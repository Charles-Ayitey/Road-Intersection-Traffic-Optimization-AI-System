import shutil
import os
import sys
import random
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import traci

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

        self.action_space = spaces.Discrete(2)

        # Obs: [Q_N, Q_S, Q_E, Q_W, Current_Phase_ID]
        self.observation_space = spaces.Box(
            low=np.array([0, 0, 0, 0, 0], dtype=np.float32),
            high=np.array([100, 100, 100, 100, 3], dtype=np.float32),
            dtype=np.float32
        )

        self.tls_id = "center"
        self.lanes = ["n2c_0", "s2c_0", "e2c_0", "w2c_0"]
        self.current_phase = 0
        self.yellow_duration = 3

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
        ai_phase = 0 if self.current_phase in [0, 1] else 1
        return np.array(queues + [float(ai_phase)], dtype=np.float32)

    def step(self, action, callback=None):
        """
        Modified step that takes an optional callback to report 
        intermediate phases (like Yellow) to the API.
        """
        target_sumo_phase = 0 if action == 0 else 2
        
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

        # 3. Run Green Duration
        for _ in range(self.delta_time):
            traci.simulationStep()
            
        obs = self._get_obs()
        queues = obs[:4]
        # Waiting time is cumulative (seconds per lane). Cap each lane at 60 s so
        # one very patient vehicle doesn't dominate and escalate the reward into
        # the hundreds — that obscures the queue-length signal the agent needs.
        waiting = sum(min(traci.lane.getWaitingTime(l), 60.0) for l in self.lanes)
        # Linear queue penalty
        queue_penalty = float(np.sum(queues))
        # Extra quadratic penalty for any approach queue above 10 vehicles to
        # strongly discourage catastrophic build-up (previously the linear term
        # treated queue=15 only slightly worse than queue=10).
        overflow_penalty = sum(max(0, int(q) - 10) ** 2 for q in queues)
        reward = -(queue_penalty + 0.05 * waiting + 0.5 * overflow_penalty)
        terminated = traci.simulation.getMinExpectedNumber() <= 0
        truncated = traci.simulation.getTime() > 3600
        
        return obs, reward, terminated, truncated, {}

    def close(self):
        try: traci.close()
        except: pass
