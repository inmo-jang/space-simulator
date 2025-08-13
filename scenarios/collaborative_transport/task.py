import pygame
import random
from modules.utils import config, generate_positions, generate_task_colors
dynamic_task_generation = config['tasks'].get('dynamic_task_generation', {})
max_generations = dynamic_task_generation.get('max_generations', 0) if dynamic_task_generation.get('enabled', False) else 0
tasks_per_generation = dynamic_task_generation.get('tasks_per_generation', 0) if dynamic_task_generation.get('enabled', False) else 0

task_colors = generate_task_colors(config['tasks']['quantity'] + tasks_per_generation*max_generations)

from modules.base_task import BaseTask
import math

class Task(BaseTask):
    def __init__(self, task_id, position, num_sides, amount, color_id = 0):
        super().__init__(task_id, position)
        self.num_sides = num_sides
        self.amount = amount

        # for visualisation
        self.radius = self.amount * (0.95 ** self.num_sides) / config['simulation']['task_visualisation_factor']         
        self.color = task_colors.get(color_id, (0, 0, 0))
        self.color_id = color_id


        # Participating agent management
        self.assigned_agents = {} # Dictionary for agent_id, vertex_id
        self.ready_agents = set()
        self.vertex_arrival_agents = set()      

        # Vertex
        self.available_vertex_id = { index for index in range(0, self.num_sides) }
        self.vertex_positions = self.generate_vertex_positions()
        
        # for waiting time utility
        self.max_waiting_time = 0.0 

    def get_max_waiting_time(self, agents):
        max_waiting_time = 0
        for agent_id in self.ready_agents:
            waiting_time = agents[agent_id].waiting_time.get(self.task_id, 0.0)
            if waiting_time > max_waiting_time:
                max_waiting_time = waiting_time

        return max_waiting_time
    
    def get_mean_waiting_time(self, agents):
        total_waiting_time = 0
        if len(self.ready_agents) == 0:
            return 0
        
        for agent_id in self.ready_agents:
            waiting_time = agents[agent_id].waiting_time.get(self.task_id, 0.0)
            total_waiting_time += waiting_time            
        

        return total_waiting_time/len(self.ready_agents)

    def get_max_waiting_time(self, agents):
        waiting_time_dict = {}

        for agent in agents:
            if agent.agent_id in self.assigned_agents:
                waiting_time = agent.waiting_time.get(self.task_id, 0.0)
            else:
                waiting_time = 0.0
            waiting_time_dict[agent.agent_id] = waiting_time

        if waiting_time_dict:
            self.max_waiting_time = max(waiting_time_dict.values())
        else:
            self.max_waiting_time = 0.0

        return self.max_waiting_time

    def generate_vertex_positions(self):
        angle_step = 2 * math.pi / self.num_sides  # 꼭짓점 간 각도
        center_x, center_y = self.position

        points = [
            (center_x + self.radius * math.cos(i * angle_step),
                center_y + self.radius * math.sin(i * angle_step))
            for i in range(self.num_sides)
        ]

        return points

    def get_vertex_positions(self):
        return self.vertex_positions

    def include_to_assigned_agents(self, agent_id):        
        if agent_id in self.assigned_agents:
            return True # Already included

        if len(self.assigned_agents) < self.num_sides: # extra room
            _vertex_id = self.available_vertex_id.pop()
            self.assigned_agents[agent_id] = _vertex_id
            return _vertex_id
        else:
            return False

    def remove_from_assigned_agents(self, agent_id):
        _vertex_id = self.assigned_agents.get(agent_id, None)
        if _vertex_id is not None:
            self.available_vertex_id.add(_vertex_id)
            self.assigned_agents.pop(agent_id)

    def include_to_ready_agents(self, agent_id):
        if agent_id not in self.ready_agents and len(self.ready_agents) < self.num_sides:
            self.ready_agents.add(agent_id)

    def remove_from_ready_agents(self, agent_id):
        if agent_id in self.ready_agents:
            self.ready_agents.remove(agent_id)

    def is_all_agents_ready(self):
        if len(self.ready_agents) == self.num_sides:
            return True
        else:
            return False
        
    def include_to_vertex_arrival_agents(self, agent_id):
        if agent_id not in self.vertex_arrival_agents:
            self.vertex_arrival_agents.add(agent_id)

    def is_all_agents_vertex_arrival(self):
        if len(self.vertex_arrival_agents) == self.num_sides:
            return True
        else:
            return False        

    def initialize_position_to_center(self, agents):
        agent_positions = [
            a.position for a in agents
            if a.agent_id in self.ready_agents
        ]        
        avg_x = sum(x for x, _ in agent_positions) / len(agent_positions)
        avg_y = sum(y for _, y in agent_positions) / len(agent_positions)

        self.position = (avg_x, avg_y)        

    def draw_task_id(self, screen):
        if not self.completed:
            text_surface = self.font.render(f"task_id {self.task_id}: {self.amount:.2f}", True, (250, 250, 250))
            screen.blit(text_surface, (self.position[0], self.position[1]))

class BlockTask(Task):
    def __init__(self, task_id, position, num_sides, amount, color_id):
        super().__init__(task_id, position, num_sides, amount, color_id)
        self.delivered = False
        self.matching_slot_id = self.task_id + 1
        self.task_type = "block"

        self.pre_generate_surface(alpha=128)    # 0~255 중 0은 투명, 128은 반투명, 255는 불투명

    def pre_generate_surface(self, alpha):  # pygame.draw()를 한 번만 하고 draw()에서는 screen.blit()으로 띄우기만 하기 위함
        r, g, b = self.color[:3]
        self.color = (r, g, b, alpha)

        self.shape_for_render = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        self.shape_for_render.fill((0, 0, 0, 0)) # Initialise as transparent
        
        center_x, center_y = self.radius, self.radius
        angle_step = 2 * math.pi / self.num_sides
        points = [
            (center_x + self.radius * math.cos(i * angle_step),
             center_y + self.radius * math.sin(i * angle_step))
            for i in range(self.num_sides)
        ]
        pygame.draw.polygon(self.shape_for_render, self.color, points, 0)
    
    def set_delivered(self):
        self.delivered = True

    def draw(self, screen):
        if not self.delivered:
            screen.blit(self.shape_for_render, (self.position[0] - self.radius, self.position[1] - self.radius))

    def draw_task_id(self, screen):
        if not self.delivered:
            text_surface = self.font.render(f"task_id {self.task_id}", True, (50, 50, 50))
            screen.blit(text_surface, (self.position[0], self.position[1]))


class SlotTask(Task):
    def __init__(self, task_id, position, num_sides, amount, color_id):
        super().__init__(task_id, position, num_sides, amount, color_id)
        self.line_width = 2  
        self.task_type = "slot"

    def draw(self, screen):
        points = self.vertex_positions
        if not self.completed:
            pygame.draw.polygon(screen, self.color, points, self.line_width)        

def get_random_num_sides():
    return random.randint(config['tasks']['shape']['side_num']['min'], config['tasks']['shape']['side_num']['max'])

def get_random_amount():
    return random.uniform(config['tasks']['amounts']['min'], config['tasks']['amounts']['max'])

def generate_tasks(task_quantity=None, task_id_start = 0, seed=None):
    if task_quantity is None:
        task_quantity = config['tasks']['quantity']        
    task_locations = config['tasks']['locations']

    block_tasks_positions = generate_positions(task_quantity // 2,
                                        task_locations['x_min'],
                                        task_locations['x_max'],
                                        task_locations['y_min'],
                                        task_locations['y_max'],
                                        radius=task_locations['non_overlap_radius'],
                                        seed=seed)
    
    slot_tasks_positions = generate_positions(task_quantity // 2,
                                        task_locations['x_min'],
                                        task_locations['x_max'],
                                        task_locations['y_min'],
                                        task_locations['y_max'],
                                        radius=task_locations['non_overlap_radius'],
                                        seed=seed + 1)

    # Initialize tasks
    tasks = []
    for idx, (block_pos, slot_pos) in enumerate(zip(block_tasks_positions, slot_tasks_positions)):
        num_sides = get_random_num_sides()
        # task_amount = get_random_amount()
        task_amount = config['tasks']['amounts']['fixed'] * num_sides
        block_task = BlockTask(task_id_start + idx, block_pos, num_sides, task_amount, task_id_start+idx)
        slot_task = SlotTask(task_id_start + idx + 1, slot_pos, num_sides, task_amount, task_id_start+idx)
        tasks.append(block_task)
        tasks.append(slot_task)
        task_id_start += 1
    return tasks