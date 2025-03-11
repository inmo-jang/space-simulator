import pygame
import random
import math
from modules.utils import config, generate_positions, generate_task_colors
dynamic_task_generation = config['tasks'].get('dynamic_task_generation', {})
max_generations = dynamic_task_generation.get('max_generations', 0) if dynamic_task_generation.get('enabled', False) else 0
tasks_per_generation = dynamic_task_generation.get('tasks_per_generation', 0) if dynamic_task_generation.get('enabled', False) else 0

task_colors = generate_task_colors(config['tasks']['quantity'] + tasks_per_generation*max_generations)
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds

def get_random_num_sides():
    return random.randint(config['tasks']['shape']['side_num']['min'], config['tasks']['shape']['side_num']['max'])

def get_random_amount():
    return random.uniform(config['tasks']['amounts']['min'], config['tasks']['amounts']['max'])

from modules.base_task import BaseTask


class Task(BaseTask):
    def __init__(self, task_id, position, num_sides=None, amount=None, color_id = 0):
        super().__init__(task_id, position)
        self.num_sides = num_sides if num_sides is not None else get_random_num_sides()

        # self.amount = amount if amount is not None else get_random_amount()
        self.amount = config['tasks']['amounts']['fixed'] * self.num_sides  # 기본값 * 꼭짓점 수(task에 필요한 agent 수)로 amount 설정

        # self.radius = self.amount / config['simulation']['task_visualisation_factor']
        self.radius = self.amount * (0.95 ** self.num_sides) / config['simulation']['task_visualisation_factor'] # radius는 일단 적당히 설정...

        self.num_sides = num_sides if num_sides is not None else get_random_num_sides()
        self.line_width = 0 # 외곽선 두께 0이면 도형 내부 채움
        self.color = task_colors.get(color_id, (0, 0, 0))   # Default to black if task_id not found
        self.color_id = color_id

        self.assigned_agent_set = []
        self.arrived_agent_set = []

        self.points = self.vertex_points()
        self.vertex_index = []

        self.vertex_agent_num_completed = False

        self.agent_waiting_time = 0
    
    def remove_from_assigned_agent_set(self, agent_id):
        if agent_id in self.assigned_agent_set:
            self.assigned_agent_set.remove(agent_id)

        for item in self.vertex_index[:]:  # 슬라이싱으로 복사본 사용
            if item[0] == agent_id:
                self.vertex_index.remove(item)

    def add_assigned_agent_set(self, agent_id):
        
        if agent_id in self.assigned_agent_set:
            return None
        # if agent_id in self.assigned_agent_set:
        #     # 해당 agent의 vertex index 찾아서 반환
        #     for a_id, v_index in self.vertex_index:
        #         if a_id == agent_id:
        #             return v_index
        #     raise ValueError(f"Error: No vertex_idx matching agent!") 

        # 현재 할당된 인덱스들을 제외한 인덱스 중 첫 번째를 택하기 -> add 및 remove로 인덱스 길이 변경되어서 중복 할당 일어나지 않도록
        if len(self.assigned_agent_set) < self.num_sides:
            used_indices = { index for (_, index) in self.vertex_index }
            for idx in range(self.num_sides):
                if idx not in used_indices:
                    _vertex_index = idx
                    break
            self.assigned_agent_set.append(agent_id)
            self.vertex_index.append((agent_id, _vertex_index))
            return _vertex_index
        else:
            return None

    def remove_from_arrived_agent_set(self, agent_id):
        if agent_id in self.arrived_agent_set:
            self.arrived_agent_set.remove(agent_id)
        
    def add_arrived_agent_set(self, agent_id):
        if agent_id not in self.arrived_agent_set:
            self.arrived_agent_set.append(agent_id)

    
    def vertex_arrived_agent_num_check(self):
        if len(self.arrived_agent_set) == self.num_sides:
            diff = set(self.assigned_agent_set).difference(set(self.assigned_agent_set))
            if len(diff) == 0:
                return True
            else:
                raise ValueError(f"[ERROR]")
        else:
            return False

    def set_vertex_agent_num_done(self):
        self.vertex_agent_num_completed = True

    def get_vertex_points(self):
        points = self.points
        return points

    def vertex_points(self):
        angle_step = 2 * 3.1415 / self.num_sides  # 꼭짓점 간 각도
        center_x, center_y = self.position

        points = [
            (center_x + self.radius * math.cos(i * angle_step),
                center_y + self.radius * math.sin(i * angle_step))
            for i in range(self.num_sides)
        ]

        return points
    
    def draw(self, screen):
        points = self.points

        if not self.completed:
            pygame.draw.polygon(screen, self.color, points, self.line_width)

    def initialize_position_to_center(self, agents):
        arrived_agents = self.arrived_agent_set
        total_x, total_y = 0, 0
        num_agents = len(arrived_agents)

        for agent_id in arrived_agents:
            agent_obj = next((a for a in agents if a.agent_id == agent_id), None)
            if agent_obj:
                total_x += agent_obj.position[0]
                total_y += agent_obj.position[1]

        avg_x = total_x / num_agents
        avg_y = total_y / num_agents
        self.position = (avg_x, avg_y)

    def initialize_position_to_direction(self, agents):
        arrived_agents = self.arrived_agent_set
        total_x, total_y, total_vx, total_vy = 0, 0, 0, 0
        num_agents = 0

        for agent_obj in agents:
            if agent_obj.agent_id in arrived_agents:
                total_x += agent_obj.position[0]
                total_y += agent_obj.position[1]
                total_vx += agent_obj.velocity[0]
                total_vy += agent_obj.velocity[1]
                num_agents += 1

        if num_agents == 0:
            return

        avg_x = total_x / num_agents
        avg_y = total_y / num_agents
        avg_vx = total_vx / num_agents
        avg_vy = total_vy / num_agents

        speed = math.sqrt(avg_vx ** 2 + avg_vy ** 2)

        if speed > 0:
            direction = (avg_vx / speed, avg_vy / speed)
            new_x = avg_x + direction[0] * self.radius
            new_y = avg_y + direction[1] * self.radius
        else:
            new_x, new_y = avg_x, avg_y

        self.position = (new_x, new_y)


class BlockTask(Task):
    def __init__(self, task_id, position, num_sides, amount, color_id):
        super().__init__(task_id, position, num_sides, amount, color_id)
        self.block_delivered = False
        self.matching_slot_id = self.task_id + 1

        self.pre_generate_surface(alpha=128)    # 0~255 중 0은 투명, 128은 반투명, 255는 불투명

    def pre_generate_surface(self, alpha):  # pygame.draw()를 한 번만 하고 draw()에서는 screen.blit()으로 띄우기만 하기 위함
        r, g, b = self.color[:3]
        self.color = (r, g, b, alpha)

        self.transparent_surface = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        self.transparent_surface.fill((0, 0, 0, 0))
        
        center_x, center_y = self.radius, self.radius
        angle_step = 2 * math.pi / self.num_sides
        points = [
            (center_x + self.radius * math.cos(i * angle_step),
             center_y + self.radius * math.sin(i * angle_step))
            for i in range(self.num_sides)
        ]
        pygame.draw.polygon(self.transparent_surface, self.color, points, 0)
    
    def set_delivered(self):
        self.block_delivered = True

    def draw(self, screen):
        if not self.block_delivered:
            screen.blit(self.transparent_surface, (self.position[0] - self.radius, self.position[1] - self.radius))

    def draw_task_id(self, screen):
        if not self.block_delivered:
            font = pygame.font.Font(None, 15)
            text_surface = font.render(f"task_id {self.task_id}", True, (50, 50, 50))
            screen.blit(text_surface, (self.position[0], self.position[1]))

class SlotTask(Task):
    def __init__(self, task_id, position, num_sides, amount, color_id):
        super().__init__(task_id, position, num_sides, amount, color_id)
        self.line_width = 2  

def generate_tasks(task_quantity=None, task_id_start=0):
    if task_quantity is None:
        task_quantity = config['tasks']['quantity']        
    task_locations = config['tasks']['locations']

    block_tasks_positions = generate_positions(task_quantity // 2,
                                        task_locations['x_min'],
                                        task_locations['x_max'],
                                        task_locations['y_min'],
                                        task_locations['y_max'],
                                        radius=task_locations['non_overlap_radius'])
    
    slot_tasks_positions = generate_positions(task_quantity // 2,
                                        task_locations['x_min'],
                                        task_locations['x_max'],
                                        task_locations['y_min'],
                                        task_locations['y_max'],
                                        radius=task_locations['non_overlap_radius'])

    # Initialize tasks in interleaved order
    tasks = []
    for idx, (block_pos, slot_pos) in enumerate(zip(block_tasks_positions, slot_tasks_positions)):
        shared_num_sides = get_random_num_sides()
        shared_amount = get_random_amount()
        block_task = BlockTask(task_id_start + idx, block_pos, shared_num_sides, shared_amount, task_id_start+idx)
        slot_task = SlotTask(task_id_start + idx + 1, slot_pos, shared_num_sides, shared_amount, task_id_start+idx)
        tasks.append(block_task)
        tasks.append(slot_task)
        task_id_start += 1

    return tasks

