from modules.base_env import BaseEnv
from modules.utils import ResultSaver
from scenarios.features.cenwrapper.task import generate_tasks
from scenarios.features.cenwrapper.agent import generate_agents
import pygame
import os
import csv
import time
import datetime
from modules.utils import config

# Global variable for save directory (subdirectory within output/assignments)
SAVE_SUB_DIR = config['setup']

class CustomResultSaver(ResultSaver):
    def __init__(self, config):
        super().__init__(config)
        self.case_name = self.extract_case_name(config)
        self.seed = config.get('simulation', {}).get('random_seed')
    def extract_case_name(self, config):
        case_name = config.get('case_name', None)
        return case_name

    def save_to_csv(self, data_type, data, column_names):
        # 부모 클래스의 save_to_csv 메서드를 먼저 호출
        original_csv_path = super().save_to_csv(data_type, data, column_names)
        
        # 새로운 파일명 생성
        file_name = f"{self.case_name}_seed{self.seed}_{data_type}.csv"
        
        # 새로운 파일 경로 생성 (같은 디렉토리에)
        directory = os.path.dirname(original_csv_path)
        new_csv_path = os.path.join(directory, file_name)
        
        # 파일명 변경
        os.rename(original_csv_path, new_csv_path)
        print(f"Saved {file_name} at {new_csv_path}")
        
        return new_csv_path
        
class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)

        # Set `generate_tasks` function for dynamic task generation
        self.generate_tasks = generate_tasks
        
        # Set data recording
        self.result_saver = CustomResultSaver(config)
        
        # Leader management settings
        self.leader_present = True
        self.removed_leader = None

        # Initialise
        self.reset()

    def reset(self):
        super().reset()

        # Initialize agents and tasks
        self.tasks = generate_tasks(seed=self.seed)
        self.agents = generate_agents(self.tasks, seed=self.seed)
        
        # Initialize data recording
        self.data_records = []
        
        # Static Mode Stability Check Init (wall-clock time 기준)
        self.static_start_real_time = time.time()
        self.last_signature_change_real_time = None
        self.last_assignment_signature = None

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
        agents_total_distance_moved = sum(agent.distance_moved for agent in self.agents if agent.type != 'Leader')
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

    def update_simulation(self):
        super().update_simulation()
        
        # Static Mode Logic (wall-clock time 기준, assigned_task_id 기준)
        if self.config['simulation'].get('mode', 'dynamic') == 'static':
            now = time.time()
            elapsed_real = now - self.static_start_real_time
            
            WARMUP_SEC = 1.0    # 실제 시간 warm-up (초)
            STABILITY_SEC = 1.0  # 실제 시간 stability (초)
            TIMEOUT_SEC = 2.5  # 실제 시간 timeout (초)
            
            # Warm-up: 실제 시간 기준으로 N초 경과 후에만 stability check
            if elapsed_real > WARMUP_SEC:
                # Collect current assignment signature
                current_signature = []
                all_assigned = True
                
                for agent in self.agents:
                    if agent.type == 'Follower':
                        planned = getattr(agent, 'planned_tasks', [])
                        if not planned:
                            all_assigned = False
                            self.last_signature_change_real_time = None
                            self.last_assignment_signature = None
                            break
                        current_signature.append((agent.agent_id, planned[0].task_id))
                
                if all_assigned:
                    current_signature.sort()
                    current_signature = tuple(current_signature)
                    
                    if self.last_assignment_signature == current_signature:
                        # Signature unchanged — check stability duration
                        stable_duration = now - self.last_signature_change_real_time
                        if stable_duration >= STABILITY_SEC:
                            print(f"[{self.simulation_time:.2f}] Assignments stable for {stable_duration:.1f}s (real). Saving and terminating.")
                            self.save_static_results()
                            self.running = False
                    else:
                        # Signature changed — reset timer
                        self.last_assignment_signature = current_signature
                        self.last_signature_change_real_time = now

            # Timeout: real-time based
            if elapsed_real > TIMEOUT_SEC:
                print(f"[{self.simulation_time:.2f}] Simulation timed out ({TIMEOUT_SEC:.0f}s real). Saving current assignments and terminating.")
                self.save_static_results()
                self.running = False
                
    def save_static_results(self):
        """
        Save assignment results:
        1. Distance-based cost CSV (existing)
        2. Assignment mapping CSV (agent_id → assigned_task_id)
        """
        # --- 1. Distance cost CSV (기존 로직 유지) ---
        data = []
        total_dist = 0.0
        
        for agent in self.agents:
            if agent.type == 'Follower':
                planned = getattr(agent, 'planned_tasks', [])
                if planned:
                    current_pos = agent.position
                    agent_path_dist = 0.0
                    for task in planned:
                        tpos = pygame.Vector2(task.position)
                        agent_path_dist += current_pos.distance_to(tpos)
                        current_pos = tpos
                    data.append([agent.agent_id, agent_path_dist])
                    total_dist += agent_path_dist
                else:
                    data.append([agent.agent_id, -1.0])
        
        data.append(['Total', total_dist])
        
        # Save to custom directory
        case_name = self.config.get('case_name', 'unknown')
        case_name = case_name.strip().lower().replace(' ', '_')
        seed = self.config['simulation'].get('random_seed', 0)
        
        assignments_dir = os.path.join("output/assignments", SAVE_SUB_DIR)
        os.makedirs(assignments_dir, exist_ok=True)
        
        file_name = f"{case_name}_{seed}_static_assignment_cost.csv"
        file_path = os.path.join(assignments_dir, file_name)
        
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Agent_ID', 'Distance_to_Task'])
            writer.writerows(data)
            
        print(f"[Static Cost] Saved: {file_path}")

        # --- 2. Assignment mapping CSV ---
        self._save_assignment_csv()

    def _save_assignment_csv(self):
        """
        Save assignment mapping CSV: {case_name}_{seed}_assignments.csv
        to output/assignments/
        """
        # Build case_name from config
        case_name = self.config.get('case_name', 'unknown')
        case_name = case_name.strip().lower().replace(' ', '_')
        seed = self.config['simulation'].get('random_seed', 0)
        
        # Prepare output directory
        assignments_dir = os.path.join("output/assignments", SAVE_SUB_DIR)
        os.makedirs(assignments_dir, exist_ok=True)
        
        # Build filename
        file_name = f"{case_name}_{seed}_assignments.csv"
        file_path = os.path.join(assignments_dir, file_name)
        
        # Collect assignment data
        rows = []
        for agent in self.agents:
            if agent.type == 'Follower':
                planned = getattr(agent, 'planned_tasks', [])
                task_id = planned[0].task_id if planned else None
                bundle = [t.task_id for t in planned] if planned else []
                rows.append([agent.agent_id, task_id, bundle])
        
        # Write CSV
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['agent_id', 'assigned_task_id', 'bundle'])
            writer.writerows(rows)
        
        print(f"[Static Assignment] Saved: {file_path}")