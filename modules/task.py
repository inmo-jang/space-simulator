import pygame
import random
from modules.utils import config, generate_positions

class Task:
    def __init__(self, task_id, position):
        self.task_id = task_id
        self.position = position        
        self.amount = random.uniform(config['tasks']['amounts']['min'], config['tasks']['amounts']['max'])
        self.radius = self.amount / config['simulation']['task_visualisation_factor']
        self.completed = False

    def set_done(self):
        self.completed = True

    def reduce_amount(self, work_rate):
        self.amount -= work_rate
        if self.amount <= 0:
            self.set_done()

    def debug_draw(self, screen):
        if not self.completed:
            font = pygame.font.Font(None, 20)
            text_surface = font.render(f"Task {self.task_id}: {self.amount:.2f}", True, (255, 255, 255))
            screen.blit(text_surface, (self.position[0] - 10, self.position[1] - 20))

    def draw(self, screen):
        self.radius = self.amount / config['simulation']['task_visualisation_factor']        
        if not self.completed:
            pygame.draw.circle(screen, (255, 0, 0), self.position, int(self.radius))


def generate_tasks():
    task_quantity = config['tasks']['quantity']
    task_locations = config['tasks']['locations']

    tasks_positions = generate_positions(task_quantity,
                                        task_locations['x_min'],
                                        task_locations['x_max'],
                                        task_locations['y_min'],
                                        task_locations['y_max'],
                                        radius=task_locations['non_overlap_radius'])

    # Initialize tasks
    tasks = [Task(idx, pos) for idx, pos in enumerate(tasks_positions)]
    return tasks
