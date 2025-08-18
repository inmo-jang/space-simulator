import pygame
import random
from modules.utils import config, generate_positions
dynamic_task_generation = config['tasks'].get('dynamic_task_generation', {})
max_generations = dynamic_task_generation.get('max_generations', 0) if dynamic_task_generation.get('enabled', False) else 0
tasks_per_generation = dynamic_task_generation.get('tasks_per_generation', 0) if dynamic_task_generation.get('enabled', False) else 0

from modules.base_task import BaseTask

# TODO: 아래 Refactoring 필요
screen_width = config['simulation']['screen_width']
task_colors = [
    'red', 
    'blue', 
    'yellow', 
    'green', 
    'lime', 
    'teal', 
    'purple', 
    'pink', 
    'coral', 
    'skyblue', 
    'black', 
    'white', 
    'gray', 
    'brown'
]

# container 크기로 이미지를 조정
task_width = 35
task_height = 50   

# 목적지 좌표를 생성 (1열에 2개씩 배치)
start_x = 300  # 첫 번째 열의 x 좌표 시작점
start_y = 300  # 첫 번째 행의 y 좌표 시작점
x_spacing = 130  # 열 간격
y_spacing = 350  # 행 간격

destination_positions = []
for i in range(7):  # 7행 (14개 컨테이너)
    destination_positions.append((start_x + i * x_spacing, start_y))          # 왼쪽 열
    destination_positions.append((start_x + i * x_spacing, start_y + y_spacing))  # 오른쪽 열

task_images = {
    'red': pygame.image.load('scenarios/harbor_logistics/assets/tasks/red.png'),
    'blue': pygame.image.load('scenarios/harbor_logistics/assets/tasks/blue.png'),
    'yellow': pygame.image.load('scenarios/harbor_logistics/assets/tasks/yellow.png'),
    'green': pygame.image.load('scenarios/harbor_logistics/assets/tasks/green.png'),
    'lime': pygame.image.load('scenarios/harbor_logistics/assets/tasks/lime.png'),
    'teal': pygame.image.load('scenarios/harbor_logistics/assets/tasks/teal.png'),
    'purple': pygame.image.load('scenarios/harbor_logistics/assets/tasks/purple.png'),
    'pink': pygame.image.load('scenarios/harbor_logistics/assets/tasks/pink.png'),
    'coral': pygame.image.load('scenarios/harbor_logistics/assets/tasks/coral.png'),
    'skyblue': pygame.image.load('scenarios/harbor_logistics/assets/tasks/skyblue.png'),
    'black': pygame.image.load('scenarios/harbor_logistics/assets/tasks/black.png'),
    'white': pygame.image.load('scenarios/harbor_logistics/assets/tasks/white.png'),
    'gray': pygame.image.load('scenarios/harbor_logistics/assets/tasks/gray.png'),
    'brown': pygame.image.load('scenarios/harbor_logistics/assets/tasks/brown.png')
}



sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
class Task(BaseTask):
    def __init__(self, task_id, position, ship_id):
        super().__init__(task_id, position)
        # self.radius = self.amount / config['simulation']['task_visualisation_factor']
        self.assigned_to = None
        random_index = random.randrange(len(task_colors))
        self.color = task_colors[random_index]
        self.position_to_deliver = destination_positions[random_index]
             
        self.image = pygame.transform.scale(task_images[self.color], (task_width, task_height))
        self.ship_id = ship_id  # Ship ID 추가

    def set_assigned_to(self, agent_id):
        self.assigned_to = agent_id


    # def reduce_amount(self, work_rate):
    #     self.amount -= work_rate * sampling_time
    #     if self.amount <= 0:
    #         self.set_done()

    def draw(self, screen):
        if self.assigned_to is None:
            screen.blit(self.image, (self.position[0] - task_width // 2, self.position[1] - task_height // 2))            


def generate_tasks(task_quantity=None, task_id_start = 0, seed=None):
    if task_quantity is None:
        task_quantity = config['tasks']['quantity']
    tasks_per_group = task_quantity // 2 #task개수를 선박의 개수만큼 나눔

    task_locations1 = config['tasks']['locations1']
    tasks_positions1 = generate_positions(tasks_per_group,
                                        task_locations1['x_min'],
                                        task_locations1['x_max'],
                                        task_locations1['y_min'],
                                        task_locations1['y_max'],
                                        radius=task_locations1['non_overlap_radius'], seed=seed)

    task_locations2 = config['tasks']['locations2']
    tasks_positions2 = generate_positions(tasks_per_group,
                                        task_locations2['x_min'],
                                        task_locations2['x_max'],
                                        task_locations2['y_min'],
                                        task_locations2['y_max'],
                                        radius=task_locations2['non_overlap_radius'], seed=seed)

    # Task 생성 시 Ship ID를 포함
    tasks = []
    for idx, pos in enumerate(tasks_positions1):
        tasks.append(Task(task_id=idx + task_id_start, position=pos, ship_id='Ship1'))
    for idx, pos in enumerate(tasks_positions2):
        tasks.append(Task(task_id=idx + task_id_start + len(tasks_positions1), position=pos, ship_id='Ship2'))
    
    return tasks
