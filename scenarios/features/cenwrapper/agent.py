import pygame
import math
import os
from modules.utils import config, generate_agent_positions 
from modules.base_agent import BaseAgent
from scenarios.features.cenwrapper.task import task_colors

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

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
    
    def draw_communication_radius_circle(self, screen):
        # Draw the communication radius circle
        if self.communication_radius > 0:
            pygame.draw.circle(screen, self.color, (self.position[0], self.position[1]), self.communication_radius, 1)
            
    def draw_leader_communication_radius_circle(self, screen):
         if self.communication_radius > 0:
            circle_color = (255, 0, 0) 
            line_width = 3
            pygame.draw.circle(screen, circle_color, (int(self.position.x), int(self.position.y)), self.communication_radius, line_width)
            
    def draw_leader_communication_topology(self, screen, agents):
     # Draw lines from leader to neighbor agents
        if self.type == "Leader":
            neighbor_agents = self.agents_nearby
            for neighbor_agent in neighbor_agents:
                neighbor_position = agents[neighbor_agent.agent_id].position
                pygame.draw.line(screen, (255, 0, 0), (int(self.position.x), int(self.position.y)), (int(neighbor_position.x), int(neighbor_position.y)))




def generate_agents(tasks_info, seed=None):
    agent_types_cfg = config['agents']['types']
    agent_locations = config['agents']['locations']
    
    # Build sequences from types: agent_type list and per-agent BT xml list
    agent_types_sequence = []
    behavior_tree_xml_sequence = []
    
    for agent_type, type_cfg in agent_types_cfg.items():
        if agent_type != 'Leader':
            count = int(type_cfg['quantity'])
            bt_xml = type_cfg['behavior_tree_xml']
            agent_types_sequence.extend([str(agent_type)] * count)
            behavior_tree_xml_sequence.extend([bt_xml] * count)
    
    if 'Leader' in agent_types_cfg:
        leader_cfg = agent_types_cfg['Leader']
        count = int(leader_cfg['quantity'])
        bt_xml = leader_cfg['behavior_tree_xml']
        agent_types_sequence.extend(['Leader'] * count)
        behavior_tree_xml_sequence.extend([bt_xml] * count)
    
    total_quantity = len(agent_types_sequence)

    agents_positions = generate_agent_positions(total_quantity,
                                      agent_locations['x_min'],
                                      agent_locations['x_max'],
                                      agent_locations['y_min'],
                                      agent_locations['y_max'],
                                      radius=agent_locations['non_overlap_radius'],
                                      seed=seed)

    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]

    # 제외할 key 목록 지정
    exclude_keys = ["behavior_tree_xml",
                    "quantity",                    
                    ]   

    # Assign agent_type before building trees
    for agent, agent_type in zip(agents, agent_types_sequence):
        agent.set_agent_type(agent_type)

        # config 내 모든 key:value를 Agent의 attribute로 붙여줌
        type_config = agent_types_cfg[agent_type]
        for key, value in type_config.items():
            if key not in exclude_keys:
                setattr(agent, key, value)    

    # Provide the global info
    for agent in agents:
        agent.set_global_info_agents(agents)

    # Create per-agent behavior tree from its type config
    for agent, bt_xml in zip(agents, behavior_tree_xml_sequence):
        behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{bt_xml}"
        agent.create_behavior_tree(behavior_tree_xml)

    return agents
