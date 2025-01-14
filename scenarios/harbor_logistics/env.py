import pygame
from modules.base_env import BaseEnv
from modules.utils import ResultSaver, ObjectToRender
from scenarios.harbor_logistics.task import generate_tasks
from scenarios.harbor_logistics.agent import generate_agents

class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)

        # Initialize the background and environment
        self.set_background()

        # Initialize agents and tasks
        self.tasks = generate_tasks()
        self.agents = generate_agents(self.tasks)
        self.generate_tasks = generate_tasks

        # Initialize data recording
        self.data_records = []
        self.result_saver = ResultSaver(config)

    def set_background(self):
        assets_path = 'scenarios/harbor_logistics/assets'                
        # Load the background image
        background_port = pygame.image.load(assets_path + '/background/ground.png')
        self.background_port = pygame.transform.scale(background_port, (self.screen_width, self.screen_height))  # Resize

        # Load sea background image for ship area
        sea_background = pygame.image.load(assets_path + '/background/sea.png')
        self.background_sea = pygame.transform.scale(sea_background, (170, 1200))  # Resize

        # Ship
        self.ship1 = ObjectToRender(image_path=assets_path + '/background/ship.png', position=(70, 200), width=230, height=100, rotation=90)
        self.ship2 = ObjectToRender(image_path=assets_path + '/background/ship.png', position=(70, 500), width=230, height=100, rotation=90)

        # Load container images
        self.container_images = {
            'red': pygame.image.load(assets_path + '/tasks/red.png'),
            'blue': pygame.image.load(assets_path + '/tasks/blue.png'),
            'yellow': pygame.image.load(assets_path + '/tasks/yellow.png')
        }     

        # Resize container images
        container_width = 80
        container_height = 150
        for color in self.container_images:
            self.container_images[color] = pygame.transform.scale(self.container_images[color], (container_width, container_height))
        # Define spacing between containers
        container_spacing = 150  # 간격 값을 150으로 설정

        # Define container positions with updated spacing
        self.container_positions = [(self.screen_width - 100, 110 + i * (container_height + container_spacing)) for i in range(len(self.container_images))]

    async def step(self):
        await super().step() # Execution of `step()` in `BaseEnv`        

        # NOTE: 아래는 민지님 구현 한 부분. 이해 필요. 
        # if tasks_left == 0 and len(tasks) < max_task_count:
        #     new_task = generate_tasks(task_id_start=len(tasks))
        #     tasks.append(new_task)
        #     print(f"New Task {new_task.task_id_start} generated at {new_task.position}")
        # elif len(tasks) == max_task_count and tasks_left == 0:
        #     mission_completed = True  # 모든 작업이 완료되면 미션 종료

    def draw_background(self):
        # Draw Port background
        self.screen.blit(self.background_port, (0, 0))  
        # Draw Sea background under the ship
        self.screen.blit(self.background_sea, (0, self.screen_height - 1200))  # 배경 위치 조정            
        
        # Draw ship
        self.ship1.draw(self.screen)
        self.ship2.draw(self.screen)             

        # Draw containers
        for i, (color, position) in enumerate(zip(self.container_images, self.container_positions)):
            self.screen.blit(self.container_images[color], position)
        
    def draw_agents_info(self):
        super().draw_agents_info()
        # Draw agents
        for agent in self.agents:                    
            if self.rendering_options.get('agent_tail'): # Draw each agent's trajectory tail
                pass
                # TODO: 아래는 민지님 코드
                # agent.draw_path_to_assigned_tasks(screen) 
                # agent.draw_path_to_destination(screen)                      

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
        # tasks_total_amount_left = sum(task.amount for task in self.tasks) TODO: Refactor
        tasks_total_amount_left = 0
        
        self.data_records.append([
            self.simulation_time, 
            agents_total_distance_moved,
            agents_total_task_amount_done,
            remaining_tasks,
            tasks_total_amount_left
        ])        
                 