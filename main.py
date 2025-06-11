import asyncio
import argparse
import cProfile
import importlib
from threading import Thread

from modules.utils import set_config

# Parse command line arguments
parser = argparse.ArgumentParser(description='SPACE (Swarm Planning And Control Evaluation) Simulator')
parser.add_argument('--config', type=str, default='config.yaml', help='Path to the configuration file (default: --config=config.yaml)')
args = parser.parse_args()

# Load configuration and initialize the environment
set_config(args.config)
from modules.utils import config


# Dynamically import the environment module and Env class
env_module = importlib.import_module(config.get('scenario').get('environment') + ".env")
Env = getattr(env_module, "Env")
# Initialize Env instance
env = Env(config)

async def game_loop():
    while env.running:
        env.handle_keyboard_events()

        if not env.game_paused and not env.mission_completed:
            await env.step()
            # Record data if time recording mode is enabled
            if env.save_timewise_result_csv:
                env.record_timewise_result()

        env.render()
        env.update_display()
        if env.recording:
            env.record_screen_frame()

    env.close()



def main():
    bt_viz_cfg = config['simulation'].get('bt_visualiser', {})
    if bt_viz_cfg.get('enabled', False):
        agent_id = bt_viz_cfg.get('agent_id', 0)
        if agent_id < len(env.agents):
            from modules.bt_visualiser import visualise_bt
            agent = env.agents[agent_id]
            Thread(
                target=visualise_bt, 
                args=(agent.agent_id, agent.tree), 
                daemon=True
            ).start()
        else:
            print(f"[Warning] BT visualiser: agent_id {agent_id} is out of range!")
    
    asyncio.run(game_loop())

if __name__ == "__main__":
    if config['simulation']['profiling_mode']:
        cProfile.run('main()', sort='cumulative')
    else:
        main()