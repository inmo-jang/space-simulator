import pygame
import math
import copy
import os
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__)) 
ASSETS_DIR = os.path.join(PROJECT_ROOT, 'assets')
DRONE_DIR = os.path.join(ASSETS_DIR, 'drone')
drone_image_path_1 = os.path.join(DRONE_DIR, 'drone_1.png')
drone_image_path_2 = os.path.join(DRONE_DIR, 'drone_2.png')
drone_image_path_3 = os.path.join(DRONE_DIR, 'drone_3.png')

drone_1_image = pygame.image.load(drone_image_path_1)
drone_2_image = pygame.image.load(drone_image_path_2)
drone_3_image = pygame.image.load(drone_image_path_3)

# Load agent configuration
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"


class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate
        self.decision_maker = None
        self.visible = True

        self.task_amount_done = 0.0
        self.end_task_id = None
        self.reached_gathering_point = False

        # Load rotating blade images
        self.drone_images = [
            drone_1_image, drone_2_image, drone_3_image
            # Add more images for smoother rotation if available
        ]
        self.blade_image_index = 0
        self.frame_count = 0
        self.rotation_speed = 5  # Adjust for how fast you want the blades to rotate

        self.color = (140,140,140) # Override
  
    def set_end_task_id(self, task_id):
        self.end_task_id = task_id
        self.assigned_task_id = task_id

    def draw(self, screen, paused = False):
           
         # Cycling through blade images for animation
        if not paused:
            self.frame_count += 1
            if self.frame_count % self.rotation_speed == 0:
                self.blade_image_index = (self.blade_image_index + 1) % len(self.drone_images)

        drone_image = self.drone_images[self.blade_image_index]

        resized_blade_image = pygame.transform.scale(drone_image, (50, 45))  # Adjust size here
        rotated_blade_image = pygame.transform.rotate(resized_blade_image, -math.degrees(self.rotation))

        blade_image_rect = rotated_blade_image.get_rect(center=(self.position.x, self.position.y))
        screen.blit(rotated_blade_image, blade_image_rect.topleft)

        # Optionally, draw other elements like the rotating blades on top
        # self.update_color()

    def update_mission_status(self, gathering_point, target_arrive_threshold):
        self.reached_gathering_point = (gathering_point - self.position).length() <= target_arrive_threshold

def generate_agents(tasks_info, gathering_point=(700, 500)):
    agent_quantity = config['agents']['quantity']

    agents_positions = [pygame.math.Vector2(gathering_point) for _ in range(agent_quantity)]


    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree(behavior_tree_xml)

    return agents
