import os
from stable_baselines3 import PPO
from sumo_env import SumoTrafficEnv

def train():
    # randomise_demand=True means every episode gets different flow rates (50–900 veh/hr)
    # so the agent learns to handle any traffic condition, not just one fixed scenario
    env = SumoTrafficEnv("simulation/junction.sumocfg", use_gui=False, randomise_demand=True)
    
    # Define model
    # MlpPolicy is standard for observation vectors (queue lengths)
    model = PPO(
        "MlpPolicy", 
        env, 
        verbose=1, 
        learning_rate=0.0003,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        tensorboard_log="./data/ppo_traffic_tensorboard/"
    )
    
    # Train for 50,000 steps (can be increased for better performance)
    print("Starting training...")
    model.learn(total_timesteps=50000)
    
    # Save the model — versioned copy + rolling 'latest'
    os.makedirs("models", exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    versioned_path = f"models/ppo_traffic_agent_{timestamp}"
    model.save(versioned_path)
    print(f"Versioned model saved to {versioned_path}.zip")

    latest_path = "models/ppo_traffic_agent"
    model.save(latest_path)
    print(f"Latest model saved to {latest_path}.zip")
    
    env.close()

if __name__ == "__main__":
    train()