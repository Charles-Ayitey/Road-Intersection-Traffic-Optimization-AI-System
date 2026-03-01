import os
import sys

# Add the current directory to sys.path so we can import sumo_env
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stable_baselines3 import PPO
from sumo_env import SumoTrafficEnv

def test_agent(num_steps=50):
    # Path to the simulation config
    config_path = os.path.join("simulation", "junction.sumocfg")
    
    # Initialize the environment
    # Using headless mode (sumo) for CLI testing
    env = SumoTrafficEnv(config_path, use_gui=False)
    
    # Load the trained model
    model_path = os.path.join("models", "ppo_traffic_agent.zip")
    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        return

    model = PPO.load(model_path, env=env)
    
    print(f"--- Starting Test with Trained Agent (Steps: {num_steps}) ---")
    obs, info = env.reset()
    total_reward = 0
    
    for i in range(num_steps):
        # Predict the action using the model
        action, _states = model.predict(obs, deterministic=True)
        
        # Take the step
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        
        phase_name = "North-South" if action == 0 else "East-West"
        print(f"Step {i+1}: Action={action} ({phase_name}), Queues (N,S,E,W)={obs}, Reward={reward}")
        
        if terminated or truncated:
            print("Simulation finished.")
            break
            
    print(f"--- Test Finished ---")
    print(f"Total Cumulative Reward: {total_reward}")
    print(f"Average Queue Length: {-total_reward / num_steps:.2f} vehicles")
    
    env.close()

if __name__ == "__main__":
    test_agent()
