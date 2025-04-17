import math
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from plugins.grape.grape import *

WAITING_TIME_FACTOR = 1.1   # 임시로 지정

class GRAPE_CT(GRAPE):
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
        max_waiting_time = task.get_max_waiting_time(self.agent.agents_info)

        # Default Utility
        utility = task.amount / (num_collaborator) - COST_WEIGHT_FACTOR * distance * (num_collaborator ** SOCIAL_INHIBITION_FACTOR)         

        # GRAPE with waiting time
        waiting_time_term = math.pow(WAITING_TIME_FACTOR, max_waiting_time)
        if task.num_sides >= num_collaborator:
            utility = (task.amount + waiting_time_term)/num_collaborator - distance
        else:
            utility = float('-inf')

        return utility