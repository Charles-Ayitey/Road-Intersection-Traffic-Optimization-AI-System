import shutil
import os
import sys
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import traci

class SumoTrafficEnv(gym.Env):
    def __init__(self, sumocfg_path, use_gui=False, delta_time=5):
        super(SumoTrafficEnv, self).__init__()
        
        self.sumocfg_path = sumocfg_path
        self.use_gui = use_gui
        self.delta_time = delta_time
        
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
        self.current_phase = 0 # Actual SUMO Phase (0, 1, 2, 3)
        self.yellow_duration = 3

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        try: traci.close()
        except: pass
            
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
        
        # Map SUMO phases (0,1,2,3) back to binary (0,1) for the AI Model's observation
        # 0: NS Green, 1: NS Yellow -> Both seen as 0 (North-South active)
        # 2: EW Green, 3: EW Yellow -> Both seen as 1 (East-West active)
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
        reward = -float(np.sum(obs[:4]) + 0.1 * sum([traci.lane.getWaitingTime(l) for l in self.lanes]))
        terminated = traci.simulation.getMinExpectedNumber() <= 0
        truncated = traci.simulation.getTime() > 3600
        
        return obs, reward, terminated, truncated, {}

    def close(self):
        try: traci.close()
        except: pass
