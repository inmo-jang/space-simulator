import pygame
import math
import copy
import os
import random
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent
from .path_planner.plugin_manager import planner_manager

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)

        self.work_rate = work_rate

        self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent.png')  # 기본 이미지
        self.image = pygame.transform.scale(self.image, (50, 50))  # 크기 조정
        self.task_color = None  # 현재 운반 중인 task 색상 (없으면 None)

        # 배터리 관련 속성
        self.battery = 100.0  # 초기 배터리 상태 (100%)
        self.default_spending_rate = config['battery']['default_spending_rate']
        self.task_spending_rate = config['battery']['task_spending_rate']

        # TTC 필요값
        self.safe_distance = 30  # 안전 거리 
        self.ttc_threshold = 3   # Time-To-Collision(TTC) 임계값


    def set_path_planner(self, grid_graph):
        self.grid_graph = grid_graph
        self.path_planner = planner_manager.get_planner(config['planner']['algorithm'], self.grid_graph)


    def update_battery(self):

        if self.blackboard.get('is_charging', False):
        # 충전 중일 경우 배터리 감소 없음
            return
        
        """배터리 상태를 업데이트, 작업 여부에 따라 소모량 변경"""
        # 작업 여부에 따른 소모 속도 설정
        if self.blackboard.get('assigned_task_id'):
            battery_spending_rate = self.task_spending_rate
        else:
            battery_spending_rate = self.default_spending_rate

        
        # FULLED 상태 처리
        if self.blackboard.get('is_charging', False):
            self.battery = max(0, self.battery - battery_spending_rate)
            #print(f"Agent {self.agent_id}: FULLED status active. Battery decreased by {battery_spending_rate:.2f}%. Current battery: {self.battery:.2f}%.")
            return  # FULLED 상태에서도 정상적으로 배터리 감소 후 종료
        
        self.battery = max(0, self.battery - battery_spending_rate)
        #print(f"Agent {self.agent_id}: Battery decreased by {battery_spending_rate:.2f}%")

    def update_image(self):
        """현재 상태에 따라 이미지를 업데이트"""
        if self.task_color == 'red':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_red_container.png')
        elif self.task_color == 'blue':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_blue_container.png')
        elif self.task_color == 'yellow':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_yellow_container.png')
        elif self.task_color == 'green':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_green_container.png')
        elif self.task_color == 'lime':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_lime_container.png')
        elif self.task_color == 'teal':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_teal_container.png')
        elif self.task_color == 'purple':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_purple_container.png')
        elif self.task_color == 'pink':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_pink_container.png')
        elif self.task_color == 'coral':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_coral_container.png')
        elif self.task_color == 'skyblue':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_skyblue_container.png')
        elif self.task_color == 'black':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_black_container.png')
        elif self.task_color == 'white':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_white_container.png')
        elif self.task_color == 'gray':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_gray_container.png')
        elif self.task_color == 'brown':
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent_with_brown_container.png')
        else:
            self.image = pygame.image.load('scenarios/harbor_logistics/assets/agents/agent.png')  # 기본 이미지
        # 이미지 크기 조정
        self.image = pygame.transform.scale(self.image, (50, 50))

    def draw_waypoints(self, screen):
        """
        Visualize the agent's waypoints on the screen.
        """
        if 'waypoints' in self.blackboard and self.blackboard['waypoints']:
            waypoints = self.blackboard['waypoints']

            # Define unique colors for each agent based on agent_id
            color_list = [
                (255, 0, 0),   # Red
                (0, 0, 255),   # Blue
                (0, 255, 0),   # Green
                (255, 165, 0), # Orange
                (128, 0, 128), # Purple
                (255, 192, 203), # Pink
                (0, 255, 255), # Cyan
                (255, 255, 0)  # Yellow
            ]
            agent_color = color_list[self.agent_id % len(color_list)]  # Assign a unique color to each agent

            # Draw lines connecting waypoints
            for i in range(len(waypoints) - 1):
                pygame.draw.line(screen, agent_color, waypoints[i], waypoints[i + 1], 2)

            # Draw the final destination as a white circle
            pygame.draw.circle(screen, (255, 255, 255), waypoints[-1], 5)

    def check_collision(self, agents):
        """
        개선된 충돌 감지 로직: 
        1) 주변 에이전트 탐색
        2) 내 앞쪽에 있는지 내적으로 확인
        3) Time-To-Collision(TTC) 계산 후 속도 조절
        """
        neighbors = self.get_agents_nearby()

        for neighbor in neighbors:
            dx = neighbor.position.x - self.position.x
            dy = neighbor.position.y - self.position.y
            dvx = self.velocity.x - neighbor.velocity.x
            dvy = self.velocity.y - neighbor.velocity.y

            # 상대 속도가 없으면 충돌 없음
            rel_speed_sq = dvx**2 + dvy**2
            if rel_speed_sq == 0:
                continue

            # 내적 계산 (앞쪽인지 확인)
            dot_product = dx * dvx + dy * dvy
            if dot_product >= 0:  # 뒤에 있는 경우 무시
                continue

            # TTC 계산
            ttc = -dot_product / rel_speed_sq
            if ttc < 0 or ttc > self.ttc_threshold:  # 3초 이상이면 신경 안 씀
                continue

            # 충돌 가능성이 높다면 감속
            print(f" [Agent {self.agent_id}] 충돌 위험 감지! 속도 줄이기 (TTC={ttc:.2f})")
            self.velocity.x *= 0.3
            self.velocity.y *= 0.3
            return True  # 감속 후 충돌 감지됨

        return False  # 충돌 위험 없음




    def draw(self, screen):
        rotated_image = pygame.transform.rotate(self.image, -math.degrees(self.rotation))
        new_rect = rotated_image.get_rect(center=(self.position.x, self.position.y))
        screen.blit(rotated_image, new_rect.topleft)

        # 렌더링 옵션에서 배터리 상태 표시 활성화 확인
        if config['simulation']['rendering_options'].get('agent_battery_status', True):
            # 배터리 상태를 항상 100으로 표시
            font = pygame.font.SysFont(None, 15)  # 폰트 설정
            battery_text = f"{int(self.battery)}%"
            text_surface = font.render(battery_text, True, (0, 0, 0))  # 흰색 텍스트
            text_rect = text_surface.get_rect()
            text_rect.topleft = (self.position.x + 30, self.position.y - 20)  # 에이전트 옆에 표시
            screen.blit(text_surface, text_rect)

def generate_agents(tasks_info, grid_graph, seed=None):
    agent_quantity = config['agents']['quantity']
    
    # Generate agents positions
    grid_nodes = list(grid_graph.graph.nodes) # 그리드 노드 리스트 가져오기

    if seed is not None:
        random.seed(seed)
    selected_positions = random.sample(grid_nodes, agent_quantity) # 에이전트 수만큼 랜덤하게 그리드 노드 선택 (중복 방지)
    
    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(selected_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree(behavior_tree_xml)
        agent.set_path_planner(grid_graph)
    return agents