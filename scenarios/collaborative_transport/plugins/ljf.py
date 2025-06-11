import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from greedy_not_FC import *

class LJF(Greedy):
    def compute_utility(self, task): # Individual Utility Function  
        if task is None:
            return float('-inf')
        if task.is_all_agents_ready() and not self.agent.agent_id in task.ready_agents: # When this agent is not yet arrived at the task, but this task becomes already ready
            return float('-inf')

        return task.amount