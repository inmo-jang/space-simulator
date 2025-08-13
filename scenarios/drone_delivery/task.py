import pygame
import random
from modules.utils import config, generate_positions
from modules.base_task import BaseTask
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__)) 
ASSETS_DIR = os.path.join(PROJECT_ROOT, 'assets')
POINT_DIR = os.path.join(ASSETS_DIR, 'point')

start_image_path = os.path.join(POINT_DIR, 'pickup_point.png')
end_image_path = os.path.join(POINT_DIR, 'dropoff_point_rev.png')

start_image = pygame.image.load(start_image_path)
end_image = pygame.image.load(end_image_path)

resized_start_image = pygame.transform.scale(start_image, (65, 45))
resized_end_image = pygame.transform.scale(end_image, (65, 70))

dynamic_task_generation = config['tasks'].get('dynamic_task_generation', {})
max_generations = dynamic_task_generation.get('max_generations', 0) if dynamic_task_generation.get('enabled', False) else 0
tasks_per_generation = dynamic_task_generation.get('tasks_per_generation', 0) if dynamic_task_generation.get('enabled', False) else 0


sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
class Task(BaseTask):
    def __init__(self, task_id, pickup_position, delivery_position, color):
        super().__init__(task_id, pickup_position)
        self.pickup_position = pickup_position
        self.delivery_position = delivery_position
        self.amount = random.uniform(config['tasks']['amounts']['min'], config['tasks']['amounts']['max'])        
        self.radius = self.amount / config['simulation']['task_visualisation_factor']
        self.color = color
        self.assigned = False
        self.completed = False
        self.pickup_completed = False
        self.delivery_completed = False
        self.assigned_agent_id = None

    def set_assigned_agent_id(self, agent_id):
        self.assigned_agent_id = agent_id

       
    def draw(self, screen):
        if not self.pickup_completed:
            pygame.draw.ellipse(screen, self.color, pygame.Rect(self.position.x-25, self.position.y+10, int(50), int(15)))
            image_rect = resized_start_image.get_rect(center=(self.position.x, self.position.y))
            screen.blit(resized_start_image, image_rect.topleft)
        elif not self.delivery_completed:
            pygame.draw.ellipse(screen, self.color, pygame.Rect(self.delivery_position.x-30, self.delivery_position.y+15, int(60), int(15)))
            image_rect = resized_end_image.get_rect(center=(self.delivery_position.x, self.delivery_position.y))   
            screen.blit(resized_end_image, image_rect.topleft)

    def complete_pickup(self):
        self.pickup_completed = True
        self.check_completion()

    def complete_delivery(self):
        self.delivery_completed = True
        self.check_completion()
    
    def check_completion(self):    
        if self.pickup_completed and self.delivery_completed:
            self.completed = True

def generate_random_color():
        return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

def generate_tasks(task_quantity=None, task_id_start = 0):
    if task_quantity is None:
        task_quantity = config['tasks']['quantity']        
    task_locations = config['tasks']['locations']

    tasks_positions = generate_positions(task_quantity * 2,
                                        task_locations['x_min'],
                                        task_locations['x_max'],
                                        task_locations['y_min'],
                                        task_locations['y_max'],
                                        radius=task_locations['non_overlap_radius'])

    # Initialize tasks
    tasks = []
    for idx in range(0, len(tasks_positions), 2):
        pickup_position = pygame.Vector2(tasks_positions[idx])
        delivery_position = pygame.Vector2(tasks_positions[idx + 1])
        color = generate_random_color()
        task = Task(task_id_start + idx // 2, pickup_position, delivery_position, color)
        tasks.append(task)
    
    return tasks
