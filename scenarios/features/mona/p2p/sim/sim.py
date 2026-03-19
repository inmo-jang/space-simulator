from modules.base_sim import BaseSim
from modules.utils import ResultSaver, config, generate_positions
from scenarios.features.mona.p2p.sim.task import Task
from scenarios.features.mona.p2p.sim.agent import Agent
from scenarios.features.mona.p2p.sim.mona_controller import Mona_comm

def generate_tasks(task_quantity=None, task_id_start=0, seed=None):
    if task_quantity is None:
        task_quantity = config['tasks']['quantity']
    task_locations = config['tasks']['locations']

    tasks_positions = generate_positions(task_quantity,
                                        task_locations['x_min'],
                                        task_locations['x_max'],
                                        task_locations['y_min'],
                                        task_locations['y_max'],
                                        radius=task_locations['non_overlap_radius'],
                                        seed=seed)

    tasks = [Task(idx + task_id_start, pos) for idx, pos in enumerate(tasks_positions)]
    return tasks


def generate_agents(tasks_info, seed=None):
    agent_quantity = config['agents']['quantity']
    agent_locations = config['agents']['locations']
    fixed_positions = config['agents'].get('fixed_positions', [])
    fixed_positions = [tuple(p) for p in fixed_positions]  # list → tuple
    fixed_angles = config['agents'].get('fixed_angles', [])  # radians

    num_fixed  = min(len(fixed_positions), agent_quantity)
    num_random = agent_quantity - num_fixed

    if num_random > 0:
        random_positions = generate_positions(
                                      num_random,
                                      agent_locations['x_min'],
                                      agent_locations['x_max'],
                                      agent_locations['y_min'],
                                      agent_locations['y_max'],
                                      radius=agent_locations['non_overlap_radius'],
                                      seed=seed)
    else:
        random_positions = []

    agents_positions = fixed_positions[:num_fixed] + random_positions

    agents = []
    for idx, pos in enumerate(agents_positions):
        angle = fixed_angles[idx] if idx < len(fixed_angles) else 0
        agents.append(Agent(idx, pos, tasks_info, rotation=angle))
    return agents


class Sim(BaseSim):
    def __init__(self, config):
        super().__init__(config)

        # Set `generate_tasks` function for dynamic task generation
        self.generate_tasks = generate_tasks
        
        # Set data recording
        self.result_saver = ResultSaver(config)

        # MONA initialization + Communication setup (configuration, communication)
        self.mona_cfg = config.get("mona", {"enabled": False, "robots": []})
        self.mona_comm = Mona_comm(self.mona_cfg)  

        # Initialise
        self.reset()

    def reset(self):
        super().reset()

        # Initialize agents and tasks
        self.tasks = generate_tasks(seed=self.seed)
        self.agents = generate_agents(self.tasks, seed=self.seed)
        
        # Initialize data recording
        self.data_records = []

        # --- Mona_comm ---
        for agent in self.agents:
            agent.mona_comm = self.mona_comm

    def save_results(self):
        # Save gif
        if self.save_gif and self.rendering_mode == "Screen":        
            self.recording = False
            print("Recording stopped.")
            self.result_saver.save_gif(self.frames)          
     

        # Save time series data
        if self.save_timewise_result_csv:        
            csv_file_path = self.result_saver.save_to_csv("timewise", self.data_records, ['time', 'agents_total_distance_moved', 'agents_total_task_amount_done', 'remaining_tasks', 'tasks_total_amount_left'])          
            self.result_saver.plot_timewise_result(csv_file_path)
        
        # Save agent-wise data            
        if self.save_agentwise_result_csv:        
            variables_to_save = ['agent_id', 'task_amount_done', 'distance_moved']
            agentwise_results = self.result_saver.get_agentwise_results(self.agents, variables_to_save)                        
            csv_file_path = self.result_saver.save_to_csv('agentwise', agentwise_results, variables_to_save)
            
            self.result_saver.plot_boxplot(csv_file_path, variables_to_save[1:])

        # Save yaml
        if self.save_config_yaml:                
            self.result_saver.save_config_yaml()   

    def record_timewise_result(self):
        agents_total_distance_moved = sum(agent.distance_moved for agent in self.agents)
        agents_total_task_amount_done = sum(agent.task_amount_done for agent in self.agents)
        remaining_tasks = len([task for task in self.tasks if not task.completed])
        tasks_total_amount_left = sum(task.amount for task in self.tasks)
        
        self.data_records.append([
            self.simulation_time, 
            agents_total_distance_moved,
            agents_total_task_amount_done,
            remaining_tasks,
            tasks_total_amount_left
        ])        
                  