import pygame
import math
import copy
import os
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent

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
        self.previous_distance = None
        self.accumulated_distance = 0  # 누적 변화량
    
    def update_battery(self, current_distance):
        """배터리 상태를 업데이트, 이동 거리에 따라 배터리 소모량을 계산"""
        if self.blackboard.get('status') != "AtChargingStation":
            if self.previous_distance is not None:
                distance_change = abs(self.previous_distance - current_distance)
                self.accumulated_distance += distance_change

                # 누적 변화량이 100 이상일 때 배터리 감소
                while self.accumulated_distance >= 100:
                    self.battery = max(0, self.battery - 1)  # 배터리 감소
                    self.accumulated_distance -= 100
                    #print(f"[DEBUG] Agent {self.agent_id}: Battery decreased. Current battery = {self.battery}%")

            # 현재 거리를 이전 거리로 저장
            self.previous_distance = current_distance

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
    

def generate_agents(tasks_info):
    agent_quantity = config['agents']['quantity']
    agent_locations = config['agents']['locations']

    agents_positions = generate_positions(agent_quantity,
                                      agent_locations['x_min'],
                                      agent_locations['x_max'],
                                      agent_locations['y_min'],
                                      agent_locations['y_max'],
                                      radius=agent_locations['non_overlap_radius'])

    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree(behavior_tree_xml)

    return agents
