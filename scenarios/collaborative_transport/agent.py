import pygame
import math
import os
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent
from scenarios.collaborative_transport.task import task_colors, BlockTask, SlotTask

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate


        self.task_amount_done = 0.0
        self.target_vertex_idx = None
        self.task_color_id = None

    def set_target_vertex_idx(self, target_vertex_idx):
        self.target_vertex_idx = target_vertex_idx

    def draw(self, screen):
        size = 10
        angle = self.rotation

        # Calculate the triangle points based on the current position and angle
        p1 = pygame.Vector2(self.position.x + size * math.cos(angle), self.position.y + size * math.sin(angle))
        p2 = pygame.Vector2(self.position.x + size * math.cos(angle + 2.5), self.position.y + size * math.sin(angle + 2.5))
        p3 = pygame.Vector2(self.position.x + size * math.cos(angle - 2.5), self.position.y + size * math.sin(angle - 2.5))

        self.update_color()
        pygame.draw.polygon(screen, self.color, [p1, p2, p3])


    def set_color_id(self, task_color_id):
        self.task_color_id = task_color_id

    def update_color(self):        
        self.color = task_colors.get(self.task_color_id, (20, 20, 20))  # Default to Dark Grey if no task is assigned
    
    def find_matching_slot_task(self, local_block_task, local_tasks_info):
        slot_task_id = local_block_task.task_id + 1   # block에 '알맞은 짝의' slot이 존재하는지 id로 판단...
        for task in local_tasks_info:
            if task.task_id == slot_task_id and isinstance(task, SlotTask):
                return task
        return None
    
    # base_agent.py의 get_tasks_nearby()를 수정
    def get_all_tasks_nearby(self, radius = None, with_completed_task = True):
        _situation_awareness_radius = self.situation_awareness_radius if radius is None else radius
        if _situation_awareness_radius > 0:
            situation_awareness_radius_squared = _situation_awareness_radius ** 2
            if with_completed_task: # Default
                local_tasks_info = [
                    task 
                    for task in self.tasks_info 
                    if (self.position - task.position).length_squared() <= situation_awareness_radius_squared
                ]                
            else:
                local_tasks_info = [
                    task 
                    for task in self.tasks_info 
                    if not (task.completed or task.vertex_agent_num_completed) and (self.position - task.position).length_squared() <= situation_awareness_radius_squared
                ]                                
        else:
            if with_completed_task: # Default
                local_tasks_info = self.tasks_info
            else:
                local_tasks_info = [
                    task 
                    for task in self.tasks_info 
                    if not (task.completed or task.vertex_agent_num_completed)
                ]                                                
        
        return local_tasks_info  

    # base_agent.py의 get_tasks_nearby()를 오버라이드
    def get_tasks_nearby(self, radius = None, with_completed_task = True): # block task만 선택
        local_tasks_info = self.get_all_tasks_nearby(radius, with_completed_task)

        local_block_tasks_info = [task for task in local_tasks_info if isinstance(task, BlockTask)]

        return local_block_tasks_info
    
def generate_agents(tasks_info):
    agent_quantity = config['agents']['quantity']
    agent_locations = config['agents']['locations']

    agents_positions = generate_positions(agent_quantity,
                                      agent_locations['x_min'],
                                      agent_locations['x_max'],
                                      agent_locations['y_min'],
                                      agent_locations['y_max'],
                                      radius=agent_locations['non_overlap_radius'])

    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree(behavior_tree_xml)

    return agents