import pygame
from modules.utils import config
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
class BaseTask:
    def __init__(self, task_id, position):
        self.task_id = task_id
        self.position = pygame.Vector2(position)
        self.completed = False
        self.amount = 0.0
        self.radius = 0.0
        self.font = pygame.font.Font(None, 15)

    def set_done(self):
        self.completed = True

    def reduce_amount(self, work_rate):
        self.amount -= work_rate * sampling_time
        if self.amount <= 0:
            self.set_done()

    def draw(self, screen):
        if not self.completed:
            pygame.draw.circle(screen, self.color, self.position, int(5))

    def draw_task_id(self, screen):
        if not self.completed:
            text_surface = self.font.render(f"task_id {self.task_id}", True, (50, 50, 50))
            screen.blit(text_surface, (self.position[0], self.position[1]))
