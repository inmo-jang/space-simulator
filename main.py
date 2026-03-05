import asyncio
import argparse
import cProfile
import importlib
from threading import Thread

from modules.utils import set_config

# Parse command line arguments
parser = argparse.ArgumentParser(description='SPACE (Swarm Planning And Control Evaluation) Simulator')
parser.add_argument('--config', type=str, default='scenarios/features/mona/puppet/configs/puppet.yaml', help='Path to the configuration file (default: --config=config.yaml)')
args = parser.parse_args()

# Load configuration and initialize the environment
set_config(args.config)
from modules.utils import config


# Dynamically import the environment module and Env class
sim_module = importlib.import_module(config.get('scenario').get('environment') + ".sim.sim")
Sim = getattr(sim_module, "Sim")
# Initialize Env instance
sim = Sim(config)

from modules.bt_runner import BTRunner
bt_runner = BTRunner(config)
bt_runner.initialize(sim.agents)

async def game_loop():
    while sim.running:
        sim.handle_keyboard_events()

        if not sim.game_paused and not sim.mission_completed:
            await bt_runner.step()
            sim.update_simulation()
            # Record data if time recording mode is enabled
            if sim.save_timewise_result_csv:
                sim.record_timewise_result()

        sim.render()
        sim.update_display()
        if sim.recording:
            sim.record_screen_frame()

    sim.close()



def main():
    # bt_runner takes priority; fall back to simulation for configs that predate the bt_runner section
    _bt_runner_cfg = config.get('bt_runner', {})
    bt_viz_cfg = _bt_runner_cfg.get('bt_visualiser', config['simulation'].get('bt_visualiser', {}))
    if bt_viz_cfg.get('enabled', False):
        agent_id = bt_viz_cfg.get('agent_id', 0)
        if agent_id < len(sim.agents):
            from modules.bt_visualiser import visualise_bt
            agent = sim.agents[agent_id]
            Thread(
                target=visualise_bt,
                args=(agent.agent_id, agent.tree),
                daemon=True
            ).start()
        else:
            print(f"[Warning] BT visualiser: agent_id {agent_id} is out of range!")

    asyncio.run(game_loop())

if __name__ == "__main__":
    _bt_runner_cfg = config.get('bt_runner', {})
    _profiling = _bt_runner_cfg.get('profiling_mode', config['simulation'].get('profiling_mode', False))
    if _profiling:
        cProfile.run('main()', sort='cumulative')
    else:
        main()