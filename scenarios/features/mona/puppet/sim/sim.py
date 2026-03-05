from modules.base_sim import BaseSim
from modules.utils import ResultSaver, config, generate_positions
from scenarios.features.mona.puppet.sim.task import Task
from scenarios.features.mona.puppet.sim.agent import Agent
import pygame
import socket, json, threading


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

        
        t = threading.Thread(target=self._listen_whycon_udp, daemon=True)
        t.start()

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
                  
        
    def handle_keyboard_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
        
            # Q 키로 종료
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                    self.running = False

            # 마우스 클릭으로 태스크 생성
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self.agents:
                    continue
                click_pos = pygame.Vector2(event.pos)
                new_id = len(self.tasks)
                self.tasks.append(Task(new_id, click_pos))
                print(f"[{self.simulation_time:.2f}] Spawned Task {new_id} at ({int(click_pos.x)}, {int(click_pos.y)})")



    def _listen_whycon_udp(self):
        udp_port = int(getattr(self, "config", {}).get("mona", {}).get("udp_port", 9999))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", udp_port))
        print(f"[Env] WhyCon UDP listening on 0.0.0.0:{udp_port}")
        while True:
            try:
                data, _ = sock.recvfrom(2048)
                msg = json.loads(data)
                agent_id = int(msg.get("agent_id", 0))
                x = float(msg["x"]);
                y = float(msg["y"])
                yaw = msg.get("yaw", None)
                if 0 <= agent_id < len(self.agents):
                    ag = self.agents[agent_id]
                    if hasattr(ag, "set_position"):
                        ag.set_position(x, y, yaw)
            except Exception as e:
                print(f"[WhyCon UDP Error] {e}")