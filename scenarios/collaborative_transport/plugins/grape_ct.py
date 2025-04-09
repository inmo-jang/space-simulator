import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from plugins.grape.grape import *

class GRAPE_CT(GRAPE):
    def __init__(self, agent):
        super().__init__(agent)


    def compute_utility(self, task): # Individual Utility Function  
        if task is None:
            return float('-inf')

        self.partition.setdefault(task.task_id, set()) # Ensure the task_id key exists in the partition. Set tis value as empty set if it doesn't already exist (This is for dynamic task generation)
        num_collaborator = len(self.partition[task.task_id])
        if self.agent.agent_id not in self.partition[task.task_id]:
            num_collaborator += 1

        distance = (self.agent.position - task.position).length()              
        if task.num_sides < num_collaborator:
            utility = float('-inf')
        else:
            utility = task.amount * num_collaborator - distance        
        return utility