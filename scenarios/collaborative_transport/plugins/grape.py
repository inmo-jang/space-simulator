import math
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))
from modules.utils import config

from plugins.grape.grape import GRAPE as _GRAPE

COST_WEIGHT_FACTOR = config['decision_making']['GRAPE']['cost_weight_factor']
SOCIAL_INHIBITION_FACTOR = config['decision_making']['GRAPE']['social_inhibition_factor']

class GRAPE(_GRAPE):

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
        utility = task.amount / (num_collaborator) - COST_WEIGHT_FACTOR * distance * (num_collaborator ** SOCIAL_INHIBITION_FACTOR) 
        return utility