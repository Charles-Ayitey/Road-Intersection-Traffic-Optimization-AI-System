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
        print(f"Loaded refined RL model from {self.model_path}")

    def get_state_from_api(self):
        try:
            response = requests.get(f"{API_URL}/get_state", timeout=0.5)
            if response.status_code == 200:
                return np.array(response.json()["observation"], dtype=np.float32)
        except Exception as e:
            print(f"Error connecting to API: {e}")
        return None

    def post_phase_to_api(self, phase_id):
        """Update the API with the actual 0-3 phase ID for the 3-color lights"""
        try:
            payload = {"action": 0, "phase": int(phase_id)} # Action field kept for compatibility
            requests.post(f"{API_URL}/set_action", json=payload, timeout=0.1)
        except:
            pass

    def run(self, steps=1000):
        print("--- Starting Live AI Traffic Control (3-Color Support) ---")
        obs_sim, _ = self.env.reset()
        
        for i in range(steps):
            # 1. Get State from Vision (API)
            obs_vision = self.get_state_from_api()
            current_obs = obs_vision if obs_vision is not None else obs_sim
            
            # 2. Predict next action (0: NS, 1: EW)
            action, _ = self.model.predict(current_obs, deterministic=True)
            
            # 3. Apply action to Simulation
            # Use the callback to push YELLOW phases to the dashboard immediately
            obs_sim, reward, term, trunc, _ = self.env.step(action, callback=self.post_phase_to_api)
            
            # 4. Final sync of the Green phase
            self.post_phase_to_api(self.env.current_phase)
            
            print(f"Step {i+1}: Queues {current_obs[:4]} | Reward {reward:.2f}")
            time.sleep(0.5) 
            
            if term or trunc: break
                
        self.env.close()

if __name__ == "__main__":
    controller = LiveRLController(MODEL_PATH, CONFIG_PATH)
    controller.run()
