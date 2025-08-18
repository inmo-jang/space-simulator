import pygame
from modules.base_env import BaseEnv
from modules.utils import ResultSaver, ObjectToRender
from scenarios.harbor_logistics.task import generate_tasks
from scenarios.harbor_logistics.agent import generate_agents
from scenarios.harbor_logistics.grid_graph import GridGraph

class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)

        # Initialize the background and environment
        self.set_background()

        # Set `generate_tasks` function for dynamic task generation
        self.generate_tasks = generate_tasks

        # Set data recording
        self.result_saver = ResultSaver(config)

        # Set grid size
        self.grid_size = config['grid']['size']

        # 이동 가능한 노드 생성
        self.grid_nodes = self.generate_grid_nodes()

        # 그래프 생성
        self.grid_graph = GridGraph(self.grid_nodes, self.grid_size)

        # Initialise
        self.reset()


    def reset(self):
        super().reset()

        # Initialize agents and tasks
        self.tasks = generate_tasks(seed=self.seed)
        self.agents = generate_agents(self.tasks, self.grid_graph, seed=self.seed)
        
        # Initialize data recording
        self.data_records = []     

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

        # Resize container images
        destination_width = 80
        destination_height = 300
        for color in self.destination_images:
            self.destination_images[color] = pygame.transform.scale(
                self.destination_images[color], (destination_width, destination_height)
            )
        # Define destination positions (1열에 7개씩 2행)
            start_x = 300  # 첫 번째 열의 x 좌표 시작점
            start_y = 300  # 첫 번째 행의 y 좌표 시작점
            x_spacing = 120  # 열 간격
            y_spacing = 360  # 행 간격

        self.destination_positions = []
        for i in range(7):  # 7개 열
            self.destination_positions.append((start_x + i * x_spacing, start_y))       # 첫 번째 행
            self.destination_positions.append((start_x + i * x_spacing, start_y + y_spacing))  # 두 번째 행

    def disable_obstacle_nodes(self, grid_nodes):
        """
        장애물 위치와 크기를 기반으로 노드 비활성화
        """
        obstacles = set()

        # Ship 장애물
        ship1_rect = pygame.Rect(
            self.ship1.position[0] - self.ship1.width // 2, 
            self.ship1.position[1] - self.ship1.height // 2, 
            self.ship1.width, 
            self.ship1.height
        )
        ship2_rect = pygame.Rect(
            self.ship2.position[0] - self.ship2.width // 2, 
            self.ship2.position[1] - self.ship2.height // 2, 
            self.ship2.width, 
            self.ship2.height
        )

        # Destination 장애물
        for pos in self.destination_positions:
            dest_rect = pygame.Rect(
                pos[0] - 40,  # 중심으로 보정
                pos[1] - 150, 
                80,  # Destination 너비
                300  # Destination 높이
            )
            obstacles.update(node for node in grid_nodes if dest_rect.collidepoint(node))

        # Ship 장애물 영역에 포함된 노드 비활성화
        obstacles.update(node for node in grid_nodes if ship1_rect.collidepoint(node) or ship2_rect.collidepoint(node))

        # Sea 장애물
        sea_rect = pygame.Rect(
            0,  # Sea의 x 시작점
            self.screen_height - 1200,  # Sea의 y 시작점 (기준)
            170,  # Sea의 너비
            1200  # Sea의 높이
        )
        obstacles.update(node for node in grid_nodes if sea_rect.collidepoint(node))

        # 장애물 제거
        return grid_nodes - obstacles

    
    def generate_grid_nodes(self):
        """
        기본 그리드를 생성
        전체 화면 크기를 기반으로 바둑판 격자 생성
        """
        grid_nodes = set()
        for y in range(0, self.screen_height, self.grid_size):
            for x in range(0, self.screen_width, self.grid_size):
                grid_nodes.add((x, y))  # 좌표는 픽셀 단위로 저장
        grid_nodes = self.disable_obstacle_nodes(grid_nodes)
        return grid_nodes
            
    async def step(self):
        await super().step() # Execution of `step()` in `BaseEnv`        

        # NOTE: 아래는 민지님 구현 한 부분. 이해 필요. 
        # if tasks_left == 0 and len(tasks) < max_task_count:
        #     new_task = generate_tasks(task_id_start=len(tasks))
        #     tasks.append(new_task)
        #     print(f"New Task {new_task.task_id_start} generated at {new_task.position}")
        # elif len(tasks) == max_task_count and tasks_left == 0:
        #     mission_completed = True  # 모든 작업이 완료되면 미션 종료

    def draw_grid(self):
        """
        이동 가능한 노드를 화면에 시각화
        """
        for node in self.grid_nodes:
            x, y = node
            pygame.draw.rect(
                self.screen,
                (200, 200, 200),
                pygame.Rect(
                    x - self.grid_size // 2,  # X 좌표 보정
                    y - self.grid_size // 2,  # Y 좌표 보정
                    self.grid_size, 
                    self.grid_size
                ),
                1  # 테두리 두께
            )



    def draw_background(self):
        # Draw Port background
        self.screen.blit(self.background_port, (0, 0))  
        # Draw Sea background under the ship
        self.screen.blit(self.background_sea, (0, self.screen_height - 1200))  # 배경 위치 조정            

        # Draw ship
        self.ship1.draw(self.screen)
        self.ship2.draw(self.screen)             

        # Draw containers
        for color, position in zip(self.destination_images, self.destination_positions):
            if not isinstance(position, tuple) or len(position) != 2:
                print(f"Invalid position: {position}")  # 디버깅 출력
                continue
            image = self.destination_images[color]
            self.screen.blit(image, (position[0] - image.get_width() // 2, position[1] - image.get_height() // 2))

        # Draw charging station
        self.screen.blit(self.charging_station, 
                        (self.charging_station_position[0] - self.charging_station.get_width() // 2,
                        self.charging_station_position[1] - self.charging_station.get_height() // 2))    
        self.draw_grid()
        self.draw_graph_on_pygame() 

        # Draw charging station
        self.screen.blit(self.charging_station, 
                        (self.charging_station_position[0] - self.charging_station.get_width() // 2,
                        self.charging_station_position[1] - self.charging_station.get_height() // 2))    


    def draw_graph_on_pygame(self):
        """
        Pygame 창에 그리드 기반 그래프를 시각화
        """
        # 노드 시각화
        for node in self.grid_graph.graph.nodes:
            pygame.draw.circle(self.screen, (0, 0, 255), node, 3)  # 파란 점

        # 엣지 시각화
        for edge in self.grid_graph.graph.edges:
            pygame.draw.line(self.screen, (100, 100, 100), edge[0], edge[1], 1)  # 회색 선


    def draw_agents_info(self):
        super().draw_agents_info()
        # Draw agents
        for agent in self.agents:                    
            if self.rendering_options.get('agent_tail'): # Draw each agent's trajectory tail
                pass
            if self.rendering_options.get('agent_path_visualization', False):            
                agent.draw_waypoints(self.screen)
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

        # Save yaml
        if self.save_config_yaml:                
            self.result_saver.save_config_yaml()           

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
                 