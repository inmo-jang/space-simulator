from modules.utils import config, merge_dicts
# MY_PARAMETER = config['decision_making']['my_decision_making_plugin']['my_parameter']

# Define decision-making class
class CBAA:
    def __init__(self, agent):
        self.agent = agent       
        self.assigned_task = None
        self.satisfied = False # Rename if necessary

        # Define any variables if necessary
        self.x = {} # task assignment (key: task id; value: 0 or 1)
        self.y = {} # winning bid list (key: task id; value: bid value)


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
            self.assigned_task = None
            self.satisfied = False
            self.x = {} 
            self.y = {} 


        # Give up the decision-making process if there is no task nearby 
        if len(local_tasks_info) == 0: 
            return None
        
        # Local decision-making
        if not self.satisfied:
            # Implement your idea (local decision-making)

            # Line 5
            selectable_tasks = {}
            task_rewards = {}
            for task in local_tasks_info:
                task_reward = self.calculate_score(task)
                if task.task_id not in self.y or task_reward > self.y[task.task_id]:
                    selectable_tasks[task.task_id] = task
                    task_rewards[task.task_id] = task_reward

                
            # Line 6-10
            if selectable_tasks:
                best_task_id = max(task_rewards, key=task_rewards.get) # Line 7
                self.x[best_task_id] = 1 # Line 8
                self.y[best_task_id] = task_rewards[best_task_id] # Line 9

                self.assigned_task = selectable_tasks[best_task_id]


                # Broadcasting
                self.agent.message_to_share = {
                    # Implement your idea (data to share)
                    'agent_id': self.agent.agent_id,
                    'winning_bids': self.y
                }
                self.satisfied = True

            else:
                self.agent.message_to_share = {}                                
            return None
            
        # Conflict-mitigating
        if self.satisfied:
            # Implement your idea (conflict-mitigating)
            best_task_id = self.assigned_task.task_id

            # Line 4~5
            winner_agent_candidates = {self.agent.agent_id: self.y[best_task_id]} # Initialization with myself            
            for other_agent_message in self.agent.messages_received:
                if other_agent_message:
                    y_k = other_agent_message.get('winning_bids')
                    self.y = merge_dicts(self.y, y_k) # Line 4: Winning Bid Update
                    if y_k.get(best_task_id): 
                         k_agent_id = other_agent_message.get('agent_id')
                         winner_agent_candidates[k_agent_id] = y_k[best_task_id]
            
            winner_agent_id = max(winner_agent_candidates, key=winner_agent_candidates.get)


            # Line 6~8
            if winner_agent_id != self.agent.agent_id:
                self.x[best_task_id] = 0 # Line 
                self.satisfied = False
                self.assigned_task = None

            # Reset Message
            self.agent.reset_messages_received()

            return self.assigned_task.task_id if self.assigned_task is not None else None


    def calculate_score(self, task):
        distance_to_task = self.agent.position.distance_to(task.position)
        # Time-discounted reward
        LAMBDA = 0.999
        expected_reward = LAMBDA**(distance_to_task/self.agent.max_speed + task.amount/self.agent.work_rate)*task.amount          
        return expected_reward
    
    def update_dict_based_on_comparison(my_dict, other_dict):
        my_dict_updated = {}
        
        for key, value in my_dict.items():            
            if key not in other_dict or value > other_dict[key]:
                my_dict_updated[key] = value
        
        return my_dict_updated    