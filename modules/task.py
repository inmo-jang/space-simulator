import pygame
from modules.utils import config, generate_positions

class Task:
    def __init__(self, task_id, position):
        self.task_id = task_id
        self.position = position        
        self.completed = False

    def set_done(self):
        self.completed = True

    def debug_draw(self, screen):
        if not self.completed:
            font = pygame.font.Font(None, 20)
            text_surface = font.render(f"Task {self.task_id}", True, (255, 0, 0))
            screen.blit(text_surface, (self.position[0] - 10, self.position[1] - 20))

    def draw(self, screen):
        if not self.completed:
            pygame.draw.circle(screen, (255, 0, 0), self.position, 5)


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
