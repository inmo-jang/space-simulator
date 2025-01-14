import pygame
import random
from modules.utils import config, generate_positions
dynamic_task_generation = config['tasks'].get('dynamic_task_generation', {})
max_generations = dynamic_task_generation.get('max_generations', 0) if dynamic_task_generation.get('enabled', False) else 0
tasks_per_generation = dynamic_task_generation.get('tasks_per_generation', 0) if dynamic_task_generation.get('enabled', False) else 0

from modules.base_task import BaseTask

# TODO: 아래 Refactoring 필요
screen_width = config['simulation']['screen_width']
container_colors = ['red', 'blue', 'yellow']
container_width = 80
container_height = 150

# 목적지 좌표를 생성 (1열에 2개씩 배치)
start_x = 300  # 첫 번째 열의 x 좌표 시작점
start_y = 300  # 첫 번째 행의 y 좌표 시작점
x_spacing = 130  # 열 간격
y_spacing = 350  # 행 간격

destination_positions = []
for i in range(7):  # 7행 (14개 컨테이너)
    destination_positions.append((start_x + i * x_spacing, start_y))          # 왼쪽 열
    destination_positions.append((start_x + i * x_spacing, start_y + y_spacing))  # 오른쪽 열

container_images = {
    'red': pygame.image.load('scenarios/harbor_logistics/assets/tasks/red.png'),
    'blue': pygame.image.load('scenarios/harbor_logistics/assets/tasks/blue.png'),
    'yellow': pygame.image.load('scenarios/harbor_logistics/assets/tasks/yellow.png'),
}

sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
class Task(BaseTask):
    def __init__(self, task_id, position):
        super().__init__(task_id, position)
        # self.radius = self.amount / config['simulation']['task_visualisation_factor']
        self.assigned_to = None
        random_index = random.randrange(len(container_colors))
        self.color = container_colors[random_index]
        self.position_to_deliver = destination_positions[random_index]
        
        # container 크기로 이미지를 조정
        container_width = 35
        container_height = 50        
        self.image = pygame.transform.scale(container_images[self.color], (container_width, container_height))

    def set_assigned_to(self, agent_id):
        self.assigned_to = agent_id


    # def reduce_amount(self, work_rate):
    #     self.amount -= work_rate * sampling_time
    #     if self.amount <= 0:
    #         self.set_done()

    def draw(self, screen):
        if self.assigned_to is None:
            screen.blit(self.image, (self.position[0] - container_width // 2, self.position[1] - container_height // 2))            


def generate_tasks(task_quantity=None, task_id_start = 0):
    if task_quantity is None:
        task_quantity = config['tasks']['quantity']        
    task_locations = config['tasks']['locations']

    tasks_positions = generate_positions(task_quantity,
                                        task_locations['x_min'],
                                        task_locations['x_max'],
                                        task_locations['y_min'],
                                        task_locations['y_max'],
                                        radius=task_locations['non_overlap_radius'])

    # Initialize tasks
    tasks = [Task(idx + task_id_start, pos) for idx, pos in enumerate(tasks_positions)]
    return tasks
