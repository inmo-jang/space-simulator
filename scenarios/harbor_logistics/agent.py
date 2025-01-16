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