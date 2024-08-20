from modules.utils import config
# MY_PARAMETER = config['decision_making']['my_decision_making_plugin']['my_parameter']

# Define decision-making class
class MyDecisionMakingClass:
    def __init__(self, agent):
        self.agent = agent        
        self.assigned_task = None
        self.satisfied = False # Rename if necessary
        # Define any variables if necessary

    def decide(self, blackboard):
        # Place your decision-making code for each agent
        '''
        Output: 
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''        
        # Get local information from the blackboard
        local_tasks_info = blackboard['local_tasks_info']
        local_agents_info = blackboard['local_agents_info']

        # Post-process if the previously assigned task is done        
        if self.assigned_task is not None and self.assigned_task.completed:            
            # Implement your idea
            pass

        # Give up the decision-making process if there is no task nearby 
        if len(local_tasks_info) == 0: 
            return None
        
        # Local decision-making
        if not self.satisfied:
            # Implement your idea (local decision-making)


            # Broadcasting
            self.agent.message_to_share = {
                # Implement your idea (data to share)
            }
            self.satisfied = True
            return None
            
        # Conflict-mitigating
        if self.satisfied:
            # Implement your idea (conflict-mitigating)
            pass
            return self.assigned_task.task_id if self.assigned_task is not None else None


