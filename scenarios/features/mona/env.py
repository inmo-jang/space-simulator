import socket
import json
import threading
import time
from modules.base_env import BaseEnv
from modules.utils import ResultSaver, config
from scenarios.features.mona.task import generate_tasks, Task
from scenarios.features.mona.agent import generate_agents
import pygame
from scenarios.features.mona.mona_controller import MonaController


class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)

        # Set `generate_tasks` function for dynamic task generation
        self.generate_tasks = generate_tasks
        
        # Set data recording
        self.result_saver = ResultSaver(config)

        # Initialise
        self.reset()

        # MONA configuration
        self.mona_cfg = config.get("mona", {"enabled": False, "robots": []})
        
        # Controller for sending data to MONAs
        self.mona_controller = MonaController(self.mona_cfg)
        
        # Data records for statistics
        self.data_records = []
        
        # MONA status listener port
        self.mona_status_port = self.mona_cfg.get("mona_status_port", 9001)
        
        # Start WhyCon UDP listener
        self._start_whycon_listener()
        
        # Start MONA status listener
        self._start_mona_status_listener()

    def reset(self):
        super().reset()

        # Initialize agents and tasks
        self.tasks = generate_tasks(seed=self.seed)
        self.agents = generate_agents(self.tasks, seed=self.seed)
        
        # Initialize data recording
        self.data_records = []
        
        print(f"[Env] Reset: {len(self.agents)} agents, {len(self.tasks)} tasks")

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
                  
    def _start_whycon_listener(self):
        """Start UDP listener for WhyCon position updates."""
        udp_port = self.mona_cfg.get("whycon_listen_port", 9999)
        
        thread = threading.Thread(
            target=self._listen_whycon_udp,
            args=(udp_port,),
            daemon=True
        )
        thread.start()

    def _listen_whycon_udp(self, port: int):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        print(f"[Env] WhyCon UDP listening on 0.0.0.0:{port}")
        
        while True:
            try:
                data, _ = sock.recvfrom(2048)
                msg = json.loads(data)
                
                agent_id = int(msg.get("agent_id", -1))
                x = float(msg["x"])
                y = float(msg["y"])
                yaw = msg.get("yaw", None)
                
                if 0 <= agent_id < len(self.agents):
                    self.agents[agent_id].set_position(x, y, yaw)
                    
            except Exception as e:
                print(f"[WhyCon UDP Error] {e}")

    def _start_mona_status_listener(self):
        """Start UDP listener for MONA status updates."""
        thread = threading.Thread(
            target=self._listen_mona_status_udp,
            args=(self.mona_status_port,),
            daemon=True
        )
        thread.start()

    def _listen_mona_status_udp(self, port: int):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        print(f"[Env] MONA Status UDP listening on 0.0.0.0:{port}")
        
        while True:
            try:
                data, addr = sock.recvfrom(2048)
                msg = json.loads(data)
                
                if msg.get("type") != "status":
                    continue
                
                agent_id = int(msg.get("id", -1))
                if agent_id < 0 or agent_id >= len(self.agents):
                    continue
                
                agent = self.agents[agent_id]
                
                # Update assigned task
                assigned = msg.get("assigned", -1)
                agent.assigned_task_id = assigned if assigned >= 0 else None
                
                # Update bundle (planned tasks)
                bundle = msg.get("bundle", [])
                agent.set_planned_tasks_from_ids(bundle, self.tasks)
                
                # Update nearby agents (ESP-NOW connections)
                nearby_ids = msg.get("nearby", [])
                agent.set_nearby_agents_from_ids(nearby_ids, self.agents)
                
            except Exception as e:
                # Silently ignore parsing errors to avoid spam
                pass

    async def step(self):
        for agent in self.agents:
            result = agent.process_work(self.tasks)
            if result and result.get('task_completed'):
                print(f"[{self.simulation_time:.2f}] Task {result['task_id']} completed by Agent {agent.agent_id}")
        
        # Broadcast updates to all MONA robots
        # Note: Completed tasks are automatically excluded from broadcast
        self.mona_controller.broadcast_to_all(self.agents, self.tasks)
        
        # Update simulation
        self.update_simulation()

    def update_simulation(self):
        """Update simulation state."""
        self.simulation_time += self.sampling_time
        self.tasks_left = sum(1 for task in self.tasks if not task.completed)
        
        if self.tasks_left == 0:
            self.mission_completed = not self.generation_enabled or self.generation_count == self.max_generations
        
        # Dynamic task generation
        if self.generation_enabled:
            self.generate_tasks_if_needed()
        
        # Stop if maximum simulation time reached
        if self.max_simulation_time > 0 and self.simulation_time > self.max_simulation_time:
            self.running = False
    
    
    def handle_keyboard_events(self):
        """Handle keyboard and mouse events."""
        for event in pygame.event.get():
            # Window close
            if event.type == pygame.QUIT:
                self.running = False
            
            # Mouse click -> Spawn task
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                click_pos = pygame.Vector2(event.pos)
                new_id = len(self.tasks)
                self.tasks.append(Task(new_id, click_pos))
                print(f"[{self.simulation_time:.2f}] Spawned Task {new_id} at ({int(click_pos.x)}, {int(click_pos.y)})")
            
            # Keyboard shortcuts
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    self.running = False
                elif event.key == pygame.K_p:
                    self.game_paused = not self.game_paused
                elif event.key == pygame.K_r:
                    print("Scenario reset!")
                    self.reset()

    def close(self):
        """Clean up resources."""
        # Close MONA controller
        self.mona_controller.close()
        
        # Call parent close
        super().close()