from modules.base_env import BaseEnv
from modules.utils import ResultSaver
from scenarios.features.cenwrapper.task import generate_tasks
from scenarios.features.cenwrapper.agent import generate_agents
import pygame

class Env(BaseEnv):
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
    
    def draw_agents_info(self):
        super().draw_agents_info()
        
        if self.rendering_options.get('leader_communication_topology'):
            for agent in self.agents:
                agent.draw_leader_communication_topology(self.screen, self.agents)
        
        for agent in self.agents:
            if agent.type == 'Leader' and self.rendering_options.get('leader_communication_radius_circle'): # Draw leader agent's communication radius circle
                agent.draw_leader_communication_radius_circle(self.screen)
            if agent.type != 'Leader' and self.rendering_options.get('agent_communication_radius_circle'): # Draw each follower's communication radius circle
                agent.draw_communication_radius_circle(self.screen)
    
    def handle_keyboard_events(self):
        """
        키보드 이벤트 처리 : 'l' 키로 leader agent 제거/생성
        """
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
                        self.frames = [] # Clear any existing frames
                        self.last_frame_time = self.simulation_time
                        print("Recording started...") 
                    else:
                        self.recording = False
                        print("Recording stopped.")
                        self.result_saver.save_gif(self.frames) 
                elif event.key == pygame.K_r:
                    print("Scenario reset!")
                    self.reset()
                elif event.key == pygame.K_l:
                    self.toggle_leader()
    
    def toggle_leader(self):
        """
        leader agent 제거/생성 trigger
        """
        if self.leader_present:
            self.remove_leader()
        else:
            self.respawn_leader()
    
    def remove_leader(self):
        """
        leader agent를 시뮬레이션에서 제거
        """
        leader_agents = [agent for agent in self.agents if agent.type == 'Leader']
        if leader_agents:
            self.removed_leader = leader_agents[0]
            self.agents = [agent for agent in self.agents if agent.type != 'Leader']
            self.leader_present = False

            for agent in self.agents:
                agent.set_global_info_agents(self.agents)

    def respawn_leader(self):
        """
        leader agent를 다시 시뮬레이션에 추가
        """
        if self.removed_leader:
            self.agents.append(self.removed_leader)
            self.leader_present = True
            
            for agent in self.agents:
                agent.set_global_info_agents(self.agents)