import random
import pygame
from modules.utils import config
MODE = config['decision_making']['LocalSearch']['mode']
W_FACTOR_COST = config['decision_making']['LocalSearch']['weight_factor_cost']

class LocalSearch: # Task selection within each agent's `situation_awareness_radius`
    def __init__(self, agent):
        self.agent = agent
        self.assigned_task = None

    def decide(self, blackboard):
        # Place your decision-making code for each agent
        '''
        Output: 
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''        
        # Give up the decision-making process if there is no task nearby 
        local_tasks_info = self.agent.get_tasks_nearby(with_completed_task=False)
        if len(local_tasks_info) == 0: 
            return None

        # Check if the existing task is done
        if self.assigned_task is not None and self.assigned_task.completed:
            self.assigned_task = None
            
        # Look for a task within situation awareness radius if there is no existing assigned task
        if self.assigned_task is None:
            if MODE == "Random": # Choose a task randomly
                target_task_id = random.choice(local_tasks_info).task_id
            
            elif MODE == "MinDist": # Choose the closest task                
                target_task_id = self.find_min_dist_task(local_tasks_info)
            
            elif MODE == "MaxUtil": # Choose the task providing the maximum utility                
                target_task_id = self.find_max_utility_task(local_tasks_info)
                
            self.assigned_task = self.agent.tasks_info[target_task_id]            
        
        return self.assigned_task.task_id  
        

    def find_min_dist_task(self, tasks_info):
        _tasks_distance = {
            task.task_id: self.compute_distance(task) if not task.completed else float('inf')
            for task in tasks_info
        }
        _min_task_id = min(_tasks_distance, key=_tasks_distance.get)
        return _min_task_id

    def find_max_utility_task(self, tasks_info):
        _current_utilities = {
            task.task_id: self.compute_utility(task) if not task.completed else float('-inf')
            for task in tasks_info
        }

        _max_task_id = max(_current_utilities, key=_current_utilities.get)        

        return _max_task_id
    
    def compute_utility(self, task): # Individual Utility Function  
        if task is None:
            return float('-inf')

        distance = (self.agent.position - task.position).length()        
        return task.amount - W_FACTOR_COST * distance
    
    def compute_distance(self, task): # Individual Utility Function  
        if task is None:
            return float('inf')

        distance = (self.agent.position - task.position).length()        
        return distance
        