import pygame
import math
import os
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent, bt_module
from scenarios.pa_bt_test.task import task_colors
from modules.base_bt_nodes import Status, BTNodeList, SyncCondition

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate

        
        self.task_amount_done = 0.0        

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


    def find_failed_conditions(self):
        """
        Find failed conditions from the agent's behavior tree blackboard.
        """
        failed_conditions = []
        for node_name, info in self.blackboard.items():
            # info가 딕셔너리인지 확인
            if isinstance(info, dict):
                # 키가 없을 때 기본값을 반환하도록 get() 메서드 사용
                status = info.get('status', None)
                is_expanded = info.get('is_expanded', None)  # 기본값은 True로 설정
                if status == Status.FAILURE and is_expanded == False:
                    failed_conditions.append(node_name)
        return failed_conditions


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
