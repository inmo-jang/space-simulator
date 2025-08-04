import pygame
import math
import os
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent
from scenarios.simple.task import task_colors

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate
        self.task_amount_done = 0.0
        self.external_pose = None  # 외부 pose를 위한 변수 추가

    def set_external_pose(self, x, y, yaw):
        """외부에서 실시간 위치를 설정하는 함수"""
        self.external_pose = (x, y, yaw)

    def update(self, *args, **kwargs):
        if self.external_pose:
            self.position.x = self.external_pose[0]
            self.position.y = self.external_pose[1]
            self.rotation = self.external_pose[2]
        #else: 
            #super().update(*args, **kwargs) #기존 bt_nodes의 update 부분을 삭제

    def draw(self, screen):
        size = 10
        angle = self.rotation

        # Calculate the triangle points based on the current position and angle
        p1 = pygame.Vector2(self.position.x + size * math.cos(angle), self.position.y + size * math.sin(angle))
        p2 = pygame.Vector2(self.position.x + size * math.cos(angle + 2.5), self.position.y + size * math.sin(angle + 2.5))
        p3 = pygame.Vector2(self.position.x + size * math.cos(angle - 2.5), self.position.y + size * math.sin(angle - 2.5))

        self.update_color()
        pygame.draw.polygon(screen, self.color, [p1, p2, p3])

    def update_color(self):        
        self.color = task_colors.get(self.assigned_task_id, (20, 20, 20))  # Default to Dark Grey if no task is assigned


def generate_agents(tasks_info, seed=None):
    agent_quantity = config['agents']['quantity']
    agent_locations = config['agents']['locations']

    agents_positions = generate_positions(agent_quantity,
                                          agent_locations['x_min'],
                                          agent_locations['x_max'],
                                          agent_locations['y_min'],
                                          agent_locations['y_max'],
                                          radius=agent_locations['non_overlap_radius'],
                                          seed=seed)

    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree(behavior_tree_xml)

    return agents
