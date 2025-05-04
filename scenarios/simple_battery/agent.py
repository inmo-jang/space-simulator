import pygame
import math
import os
from modules.utils import config, generate_positions, generate_random_values 
from modules.base_agent import BaseAgent
from scenarios.simple_battery.task import task_colors

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']
battery_consumption_rate = config['agents']['battery']['consumption_rate_per_unit_distance']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info, battery_level):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate
        self.battery_level = battery_level
        self.available = True
        
        self.task_amount_done = 0.0        

    def draw(self, screen):
        if not self.available:
            return 
        
        size = 10
        angle = self.rotation

        # Calculate the triangle points based on the current position and angle
        p1 = pygame.Vector2(self.position.x + size * math.cos(angle), self.position.y + size * math.sin(angle))
        p2 = pygame.Vector2(self.position.x + size * math.cos(angle + 2.5), self.position.y + size * math.sin(angle + 2.5))
        p3 = pygame.Vector2(self.position.x + size * math.cos(angle - 2.5), self.position.y + size * math.sin(angle - 2.5))

        self.update_color()
        pygame.draw.polygon(screen, self.color, [p1, p2, p3])

    def draw_work_done(self, screen):
        if not self.available:
            return 
                
        # Draw assigned_task_id next to agent position
        text_surface = self.font.render(f"batt: {self.battery_level:.1f}", True, (50, 50, 50))
        screen.blit(text_surface, (self.position[0] + 10, self.position[1] + 10))
        text_surface = self.font.render(f"work: {self.task_amount_done:.1f}", True, (50, 50, 50))
        screen.blit(text_surface, (self.position[0] + 10, self.position[1] + 20))


    def update_color(self):        
        self.color = task_colors.get(self.assigned_task_id, (20, 20, 20))  # Default to Dark Grey if no task is assigned


    def update(self):
        _previous_distance_moved = self.distance_moved
        super().update()
        _current_distance_moved = self.distance_moved
        self.battery_level -= battery_consumption_rate*(_current_distance_moved - _previous_distance_moved)
        if self.battery_level < 0:
            self.available = False
        return 

    def get_agents_nearby(self, radius=None):
        local_agents_info = super().get_agents_nearby(radius)
        local_available_agents_info = [agent for agent in local_agents_info if agent.available]
        return local_available_agents_info 

def generate_agents(tasks_info):
    agent_quantity = config['agents']['quantity']
    agent_locations = config['agents']['locations']

    agents_positions = generate_positions(agent_quantity,
                                      agent_locations['x_min'],
                                      agent_locations['x_max'],
                                      agent_locations['y_min'],
                                      agent_locations['y_max'],
                                      radius=agent_locations['non_overlap_radius'])

    agents_battery = config['agents']['battery']
    agents_battery_levels = generate_random_values(agent_quantity, 
                                                   agents_battery['min'], 
                                                   agents_battery['max'])


    # Initialize agents
    agents = [Agent(idx, pos, tasks_info, agents_battery_levels[idx]) for idx, pos in enumerate(agents_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree(behavior_tree_xml)

    return agents
