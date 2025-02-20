import pygame
from modules.base_env import BaseEnv
import os
from modules.utils import pre_render_text, ResultSaver, ObjectToRender
from scenarios.drone_delivery.task import generate_tasks
from scenarios.drone_delivery.agent import generate_agents

class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)
        
        # Initialize the background and environment
        self.set_background()

        # Set `generate_tasks` function for dynamic task generation
        self.generate_tasks = generate_tasks
        
        # Set data recording
        self.result_saver = ResultSaver(config)

        # Initialise
        self.reset()

    def reset(self):
        super().reset()

        # Initialize agents and tasks
        self.tasks = generate_tasks()
        self.agents = generate_agents(self.tasks)
        
        # Initialize data recording
        self.data_records = []        

    def set_background(self):
        CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
        ASSETS_DIR = os.path.join(CURRENT_DIR, 'assets')
        BACKGROUND_DIR = os.path.join(ASSETS_DIR, 'background')
        POINT_DIR = os.path.join(ASSETS_DIR, 'point')

        background_point_image_path = os.path.join(BACKGROUND_DIR, 'city_view.png')
        final_image_path = os.path.join(POINT_DIR, 'final_point.png')

        background_image = pygame.image.load(background_point_image_path).convert_alpha()
        self.background_image = pygame.transform.scale(background_image, (1400, 1400))
        final_point_image = pygame.image.load(final_image_path).convert_alpha()
        self.final_point_image = pygame.transform.scale(final_point_image, (80, 80)) #size

    async def step(self):
        await super().step() # Execution of `step()` in `BaseEnv`           
            
        # NOTE: 아래는 재호님 구현 한 부분. Refactoring 필요
        # tasks_left = sum(1 for task in tasks if not task.completed)
        # if tasks_left == 0:
        #     all_agents_gathered = all(
        #         agent.position.distance_to(pygame.Vector2(700, 500)) < target_arrive_threshold
        #         for agent in agents
        # )
        #     if all_agents_gathered:
        #         mission_completed = not generation_enabled or generation_count == max_generations

    def draw_background(self): # Override
        self.screen.blit(self.background_image, (0, 0))
        self.screen.blit(self.final_point_image, (670, 460))

    def draw_tasks_info(self):
        super().draw_tasks_info()

        # Line btw the pick-up point to the delivery point
        for idx in range(0, len(self.tasks), 2):
            start_task = self.tasks[idx]
            end_task = self.tasks[idx + 1]
            if not end_task.completed:
                pygame.draw.line(self.screen, start_task.color, start_task.position, end_task.position, width=2)
            start_task.draw(self.screen)
            end_task.draw(self.screen) 
    
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

        # Save yaml: TODO - To debug
        # if self.save_config_yaml:                
            # self.result_saver.save_config_yaml()           

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
                  