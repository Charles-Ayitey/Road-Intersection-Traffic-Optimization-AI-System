import os
import sys
import time
import requests
import numpy as np
from stable_baselines3 import PPO

# Add parent directory to sys.path to import SumoTrafficEnv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_agent.sumo_env import SumoTrafficEnv

# Configuration
API_URL = "http://localhost:8000"
MODEL_PATH = os.path.join("models", "ppo_traffic_agent_refined.zip")
CONFIG_PATH = os.path.join("simulation", "junction.sumocfg")

class LiveRLController:
    def __init__(self, model_path, config_path):
        self.model_path = model_path
        self.config_path = config_path
        self.env = SumoTrafficEnv(self.config_path, use_gui=True)
        self.model = PPO.load(self.model_path)
        print(f"✅ AI Brain Loaded: {self.model_path}")

    def get_state_from_api(self):
        try:
            response = requests.get(f"{API_URL}/get_state", timeout=0.5)
            if response.status_code == 200:
                return np.array(response.json()["observation"], dtype=np.float32)
        except Exception: pass
        return None

    def post_phase_to_api(self, phase_id):
        try:
            # phase_id: 0=NS_G, 1=NS_Y, 2=EW_G, 3=EW_Y
            payload = {"action": 0, "phase": int(phase_id)}
            requests.post(f"{API_URL}/set_action", json=payload, timeout=0.1)
        except: pass

    def run(self, steps=1000):
        print("\n" + "="*60)
        print("🚦 STARTING LIVE SMART TRAFFIC CONTROL (GHANA EDITION)")
        print("="*60)
        
        obs_sim, _ = self.env.reset()
        
        for i in range(steps):
            # 1. Fetch State
            obs_vision = self.get_state_from_api()
            current_obs = obs_vision if obs_vision is not None else obs_sim
            
            # 2. AI Decision
            action, _ = self.model.predict(current_obs, deterministic=True)
            action_name = "NORTH-SOUTH" if action == 0 else "EAST-WEST"
            
            # 3. Execute Step (Environment handles Yellow automatically)
            obs_sim, reward, term, trunc, _ = self.env.step(action, callback=self.post_phase_to_api)
            
            # 4. Detailed Console Log
            q = current_obs[:4]
            log_msg = (
                f"Step {i+1:3} | "
                f"ACTION: {action_name:11} | "
                f"QUEUES [N:{int(q[0]):2} S:{int(q[1]):2} E:{int(q[2]):2} W:{int(q[3]):2}] | "
                f"REWARD: {reward:7.2f}"
            )
            print(log_msg)
            
            # Final sync of the Green phase to API
            self.post_phase_to_api(self.env.current_phase)
            
            time.sleep(0.5) 
            if term or trunc: break
                
        self.env.close()
        print("="*60 + "\nTest Complete.\n")

if __name__ == "__main__":
    controller = LiveRLController(MODEL_PATH, CONFIG_PATH)
    controller.run()
