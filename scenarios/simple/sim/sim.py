from modules.base_sim import BaseSim
from modules.utils import ResultSaver, config, generate_positions, pre_render_text
from scenarios.simple.sim.task import Task
from scenarios.simple.sim.agent import Agent


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

    agents_positions = generate_positions(agent_quantity,
                                          agent_locations['x_min'],
                                          agent_locations['x_max'],
                                          agent_locations['y_min'],
                                          agent_locations['y_max'],
                                          radius=agent_locations['non_overlap_radius'],
                                          seed=seed)

    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]
    return agents


class Sim(BaseSim):
    def __init__(self, config):
        super().__init__(config)

        # Set `generate_tasks` function for dynamic task generation
        self.generate_tasks = generate_tasks
        
        # Set data recording
        self.result_saver = ResultSaver(config)

        # Initialise
        self.reset()

    def reset(self):
        super().reset()

        # Initialize agents and tasks
        self.tasks = generate_tasks(seed=self.seed)
        self.agents = generate_agents(self.tasks, seed=self.seed)
        
        # Initialize data recording
        self.data_records = []

    def save_results(self):
        pass

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
                  

    def draw_status_overlay(self):
        # Display task quantity, assigned tasks, and elapsed simulation time
        # NOTE: 'Assigned' count is only valid in CBBA mode (other plugins may not update planned_tasks consistently)
        assigned_tasks = len({task.task_id for agent in self.agents for task in agent.planned_tasks})
        task_time_text = pre_render_text(f'Tasks left: {self.tasks_left}; Assigned: {assigned_tasks}; Time: {self.simulation_time:.2f}s', 36, (0, 0, 0))
        self.screen.blit(task_time_text, (self.screen_width - 450, 20))

        # Check communication connectivity (BFS)
        visited = {0}
        queue = [0]
        while queue:
            for n in self.agents[queue.pop(0)].agents_nearby:
                if n.agent_id not in visited:
                    visited.add(n.agent_id)
                    queue.append(n.agent_id)
        if len(visited) == len(self.agents):
            conn_text = pre_render_text('Connected', 28, (0, 150, 0))
        else:
            conn_text = pre_render_text('Not Connected', 28, (200, 0, 0))
        self.screen.blit(conn_text, (self.screen_width - 450, 50))