from modules.base_env import BaseEnv
from modules.utils import ResultSaver
from scenarios.features.mona.task import generate_tasks
from scenarios.features.mona.agent import generate_agents
import pygame
import socket, json, threading

class Env(BaseEnv):
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
        # BaseEnv와 동일한 이벤트 루프에 "마우스 클릭"만 추가
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    self.running = False
                elif event.key == pygame.K_p:
                    self.game_paused = not self.game_paused
                elif event.key == pygame.K_s:
                    if not self.recording:
                        self.recording = True
                        self.frames = []
                        self.last_frame_time = self.simulation_time
                        print("Recording started...") 
                    else:
                        self.recording = False
                        print("Recording stopped.")
                        self.result_saver.save_gif(self.frames) 
                elif event.key == pygame.K_r:
                    print("Scenario reset!")
                    self.reset()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self.agents:
                    continue
                click_pos = pygame.Vector2(event.pos)

                # 가장 가까운 agent 선택
                nearest = min(
                    self.agents,
                    key=lambda a: (a.position - click_pos).length_squared()
                )

                #  컨트롤러에게 타겟 전달
                nearest.set_target(click_pos)

                # 선택: 바로 속도/가속 초기화하고 출발시키고 싶으면
                # nearest.reset_movement()

                print(f"[{self.simulation_time:.2f}] Agent {nearest.agent_id} → {tuple(map(int, click_pos))}")

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
                    if hasattr(ag, "set_marker_target"):
                        ag.set_marker_target(x, y, yaw)
            except Exception as e:
                print(f"[WhyCon UDP Error] {e}")
                  
