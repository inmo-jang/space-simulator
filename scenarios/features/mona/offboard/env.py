from modules.base_env import BaseEnv
from modules.utils import ResultSaver
from scenarios.features.mona.offboard.task import generate_tasks
from scenarios.features.mona.offboard.agent import generate_agents
from scenarios.features.mona.offboard.mona_controller import Mona_comm
import pygame
import socket, json, threading

class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)

        # MONA initialization + Communication setup (configuration, communication)
        self.mona_cfg = config.get("mona", {"enabled": False, "robots": []})
        self.mona_comm = Mona_comm(self.mona_cfg)  

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