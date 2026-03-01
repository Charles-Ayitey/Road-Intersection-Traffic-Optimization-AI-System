import os
from stable_baselines3 import PPO
from sumo_env import SumoTrafficEnv

def train():
    # Initialize environment
    env = SumoTrafficEnv("simulation/junction.sumocfg", use_gui=False)
    
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
    
    # Save the model
    os.makedirs("models", exist_ok=True)
    model_path = "models/ppo_traffic_agent"
    model.save(model_path)
    print(f"Model saved to {model_path}")
    
    env.close()

if __name__ == "__main__":
    train()