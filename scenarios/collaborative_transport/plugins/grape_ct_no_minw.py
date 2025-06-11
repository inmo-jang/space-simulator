import math
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))
from modules.utils import config

from plugins.grape.grape import *

WAITING_TIME_TOLERANCE = config['decision_making']['CT']['waiting_time_tolerance']
# MIN_WAITING_FACTOR = config['decision_making']['CT']['min_waiting_factor']
# MIN_WAITING_TIME = MIN_WAITING_FACTOR * WAITING_TIME_TOLERANCE

class GRAPE_CT_(GRAPE):
    def __init__(self, agent):
        super().__init__(agent)


    def compute_utility(self, task): # Individual Utility Function  
        if task is None:
            return float('-inf')
        if task.is_all_agents_ready() and not self.agent.agent_id in task.ready_agents: # When this agent is not yet arrived at the task, but this task becomes already ready
            return float('-inf')

        self.partition.setdefault(task.task_id, set()) # Ensure the task_id key exists in the partition. Set tis value as empty set if it doesn't already exist (This is for dynamic task generation)
        num_collaborator = len(self.partition[task.task_id])
        if self.agent.agent_id not in self.partition[task.task_id]:
            num_collaborator += 1

        distance = (self.agent.position - task.position).length()              
        # max_waiting_time = task.get_max_waiting_time(self.agent.agents_info)
        waiting_time = task.get_mean_waiting_time(self.agent.agents_info)
        
        # # min waiting time threshold
        # waiting_time = max(waiting_time, MIN_WAITING_TIME)
        # waiting_time = 0 if waiting_time == MIN_WAITING_TIME else waiting_time


        # # Default Utility
        # utility = task.amount / (num_collaborator) - COST_WEIGHT_FACTOR * distance * (num_collaborator ** SOCIAL_INHIBITION_FACTOR)         

        # GRAPE with waiting time        

        deficiency_ratio = (task.num_sides - len(task.ready_agents))/task.num_sides # 낮을 수록 이미 많은 agents가 모였다는 것임. 
        deficiency_ratio += 0.1
        deficiency_ratio_inverse = 1/deficiency_ratio

        try:
            virtual_amount = math.pow(deficiency_ratio_inverse, waiting_time / WAITING_TIME_TOLERANCE)
        except OverflowError:
            utility = float('inf')
            return utility

        utility = (task.amount + virtual_amount)/num_collaborator - COST_WEIGHT_FACTOR * distance

        return utility