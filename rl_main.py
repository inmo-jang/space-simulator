import asyncio
import argparse
import cProfile
import importlib

from modules.utils import set_config

# Parse command line arguments
parser = argparse.ArgumentParser(description='SPACE (Swarm Planning And Control Evaluation) Simulator')
parser.add_argument('--config', type=str, default='config.yaml', help='Path to the configuration file (default: --config=config.yaml)')
args = parser.parse_args()

# Load configuration and initialize the environment
set_config(args.config)
from modules.utils import config

# Dynamically import the environment module and Env class
try:
    env_module = importlib.import_module(config.get('scenario').get('environment') + ".env")
    Env = getattr(env_module, "Env")
    env = Env(config)

    # Initialize Env instance
    rlenv_module = importlib.import_module(config.get('scenario').get('environment') + ".pz_env")
    PZEnv = getattr(rlenv_module, "PZEnv")

    rlagent = importlib.import_module(config.get('scenario').get('environment') + ".pz_agent")
    PZAgent = getattr(rlagent, "PZAgent")
    
    pzenv = PZEnv(env = env, 
                  nearby_task_max_num = config.get('agents').get('nearby_task_max_num'), 
                  nearby_agent_max_num = config.get('agents').get('nearby_agent_max_num'), 
                  generate_rl_agent = PZAgent)

except ModuleNotFoundError as e:
    print(f"[ERROR] Failed to import module: {e}")
    exit(1)
except AttributeError as e:
    print(f"[ERROR] Failed to load class: {e}")
    exit(1)

"""
Main simulation loop
"""
async def game_loop():
    while pzenv.is_running():
        pzenv.handle_keyboard_events()

        if not env.game_paused and not env.mission_completed:
            await pzenv.step()

        pzenv.render()
        if pzenv.is_recording():
            pzenv.record_screen_frame()

    pzenv.close()

"""
Entry point for the simulator
"""
def main():
    asyncio.run(game_loop())

if __name__ == "__main__":
    main()
