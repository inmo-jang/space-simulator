import random


# Define decision-making class
class MyDecisionMakingClass:
    def __init__(self, agent):
        self.agent = agent        

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
        
        tasks_remaining = [task.task_id for task in self.agent.tasks_info if not task.completed]
        if len(tasks_remaining) > 0:
            return random.choice(tasks_remaining)
        else:
            return None


