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

        # Charging Station
        charging_station = pygame.image.load(assets_path + '/background/charging_station_6.png')
        self.charging_station = pygame.transform.scale(charging_station, (200, 200))  # Resize
        self.charging_station = pygame.transform.rotate(charging_station, -90)  # Rotate 90 degrees
        self.charging_station_position = (1280, 700)

        # Define colors for destinations
        destination_colors = [
            'red', 'blue', 'yellow', 'green', 'lime', 
            'teal', 'purple', 'pink', 'coral', 'skyblue', 
            'black', 'white', 'gray', 'brown'
        ]

        # Load images for each destination color
        self.destination_images = {
            color: pygame.image.load(f'{assets_path}/tasks/{color}.png') for color in destination_colors
        }

        # Resize all destination images
        destination_width = 80
        destination_height = 300
        for color in self.destination_images:
            self.destination_images[color] = pygame.transform.scale(
                self.destination_images[color], (destination_width, destination_height)
            )
        
        # Define destination positions (1열에 7개씩 2행)
            start_x = 300  # 첫 번째 열의 x 좌표 시작점
            start_y = 300  # 첫 번째 행의 y 좌표 시작점
            x_spacing = 130  # 열 간격
            y_spacing = 350  # 행 간격

            self.destination_positions = []
            for i in range(7):  # 7개 열
                self.destination_positions.append((start_x + i * x_spacing, start_y))       # 첫 번째 행
                self.destination_positions.append((start_x + i * x_spacing, start_y + y_spacing))  # 두 번째 행
        
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

        # Draw charging station
        self.screen.blit(self.charging_station, 
                        (self.charging_station_position[0] - self.charging_station.get_width() // 2,
                        self.charging_station_position[1] - self.charging_station.get_height() // 2))    

        # Draw containers
        for color, position in zip(self.destination_images, self.destination_positions):
            if not isinstance(position, tuple) or len(position) != 2:
                print(f"Invalid position: {position}")  # 디버깅 출력
                continue
            image = self.destination_images[color]
            self.screen.blit(image, (position[0] - image.get_width() // 2, position[1] - image.get_height() // 2))
            
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
                 