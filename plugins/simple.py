import random
import pygame
from modules.utils import config

preferred_task_radius = config['decision_making']['LocalRandomSearch'].get('preferred_task_radius', None)
max_random_movement_duration = config['decision_making']['LocalRandomSearch'].get('max_random_movement_duration', 1.0)
task_locations = config['tasks']['locations']

sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds

class LocalRandomSearch: # Random selection within `preferred_task_radius`
    def __init__(self, agent):
        self.agent = agent
        self.random_move_time = float('inf')
        self.random_pos = pygame.Vector2(0, 0)

    def decide(self, blackboard):
        # Place your decision-making code for each agent
        '''
        Output: 
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''        
        if 'assigned_task_id' in blackboard:
            if blackboard['assigned_task_id'] is not None:
                return blackboard['assigned_task_id']
        
        if preferred_task_radius:
            tasks_remaining = [
                task.task_id 
                for task in self.agent.tasks_info 
                if not task.completed and (self.agent.position - task.position).length() <= preferred_task_radius
            ]
        else:
            tasks_remaining = [task.task_id for task in self.agent.tasks_info if not task.completed]


        
        if len(tasks_remaining) > 0:
            return random.choice(tasks_remaining)
        

        else: # Random Walk
            # Move towards a random position
            if self.random_move_time > max_random_movement_duration:
                self.random_pos = self.get_random_position(task_locations['x_min'], task_locations['x_max'], task_locations['y_min'], task_locations['y_max'])
                self.random_move_time = 0 # Initialisation
            
            self.agent.follow(self.random_pos)                
            self.random_move_time += sampling_time            
            return None

    def get_random_position(self, x_min, x_max, y_min, y_max):
        pos = (random.randint(x_min, x_max),
                random.randint(y_min, y_max))
        return pos