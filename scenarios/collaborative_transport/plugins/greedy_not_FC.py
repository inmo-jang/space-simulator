import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from plugins.greedy.greedy import *

class Greedy(FirstClaimGreedy):
    def __init__(self, agent):
        self.agent = agent
        self.assigned_task = None

    def decide(self, blackboard):
        '''
        Output: 
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''

        local_tasks_info = blackboard['local_tasks_info']        

        # Check if the existing task is done
        if self.assigned_task is not None and (self.assigned_task.completed):
            self.assigned_task = None

        # Give up the decision-making process if there is no task nearby
        if len(local_tasks_info) == 0: 
            self.assigned_task = None
            self.agent.message_to_share = {
                'agent_id': self.agent.agent_id,
                'assigned_task_id': None
            }            
            return None

       # Given that there is only one task nearby, then enforced to select this
        if ENFORCED_COLLABORATION and len(local_tasks_info) == 1:
            self.assigned_task = local_tasks_info[0]
            return self.assigned_task.task_id

        # Look for a task within situation awareness radius if there is no existing task
        available_tasks_info = local_tasks_info  

        _max_task_id, _max_utility = self.find_max_utility_task(available_tasks_info)
           
        if _max_utility == float('-inf'):
            return None

        self.assigned_task = self.agent.tasks_info[_max_task_id]

        self.agent.message_to_share = {
            'agent_id': self.agent.agent_id,
            'assigned_task_id': self.assigned_task.task_id
        }
            
        return self.assigned_task.task_id
    
    def compute_utility(self, task): # Individual Utility Function  
        if task is None:
            return float('-inf')
        if task.is_all_agents_ready() and not self.agent.agent_id in task.ready_agents: # When this agent is not yet arrived at the task, but this task becomes already ready
            return float('-inf')        

        distance = (self.agent.position - task.position).length()        
        return task.amount - W_FACTOR_COST * distance