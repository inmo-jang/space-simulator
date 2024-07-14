import random
import copy
from modules.utils import config

USE_GLOBAL_SA = config['agents']['GRAPE']['global_situational_awareness']

class GRAPE:
    def __init__(self, agent, tasks_info):
        self.agent = agent
        self.tasks_info = tasks_info
        self.satisfied = False
        self.evolution_number = 0  # Initialize evolution_number
        self.time_stamp = 0  # Initialize time_stamp                
        self.partition = {task.task_id: set() for task in tasks_info}  # Initialize partition with emptysets        
        self.assigned_task = None

        

    def decide(self, blackboard):
        '''
        Output: 
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''           
        _assigned_task_id = None # Initialization
        
        # Check if the existing task is done
        if USE_GLOBAL_SA:
            if self.assigned_task is not None and self.assigned_task.completed: 
                self.neutralize_assignment(blackboard)
        else:
            if 'task_completed' in blackboard and blackboard['task_completed'] is True: 
                self.neutralize_assignment(blackboard)


            
        # GRAPE algorithm for each agent         
        if not self.satisfied:
            _max_task_id, _max_utility = self.find_max_utility_task()
            if _max_utility > self.compute_utility(self.assigned_task):                
                self.update_partition(_max_task_id)
                self.evolution_number += 1
                self.time_stamp = random.uniform(0, 1) 
            
            self.satisfied = True

            # Broadcasting # NOTE: Implemented separately
            self.agent.message_to_share = {
                'agent_id': self.agent.agent_id,
                'partition': self.partition, 
                'evolution_number': self.evolution_number,
                'time_stamp': self.time_stamp
                }
            
            return None

        
        # D-Mutex             
        self.evolution_number, self.time_stamp, self.partition, self.satisfied = self.distributed_mutex(self.agent.messages_received)                
        self.agent.reset_messages_received()

        if not self.satisfied:
            return None

        _assigned_task_id = self.get_assigned_task_id_from_partition(self.partition) 
        if _assigned_task_id is None:
            self.assigned_task = None            
            self.satisfied = False # self.get_assigned_task_id_from_partition(self.partition) 를 했는데, 초반에는 agent가 없는 partition일 수 있음
        else:
            self.assigned_task = self.tasks_info[_assigned_task_id]       
            
        
        return _assigned_task_id

    def neutralize_assignment(self, blackboard):
        self.discard_myself_from_coalition(self.assigned_task) # remove myself from the completed coalition
        self.assigned_task = None
        self.satisfied = False
        blackboard['task_completed'] = False

    def discard_myself_from_coalition(self, task):
        if task is not None:
            self.partition[task.task_id].discard(self.agent.agent_id)


    
    def update_partition(self, preferred_task_id):                
        self.discard_myself_from_coalition(self.assigned_task)            
        self.partition[preferred_task_id].add(self.agent.agent_id)


    def find_max_utility_task(self):
        _max_task_id = None
        _max_utility = float('-inf')        
        for task in self.tasks_info:
            if not task.completed:
                _utility = self.compute_utility(task)
                
                # Update max _utility task
                if _utility > _max_utility:
                    _max_utility = _utility
                    _max_task_id = task.task_id
        
        return _max_task_id, _max_utility

    def compute_utility(self, task): # Individual Utility Function  
        if task is None:
            return float('-inf')


        num_collaborator = len(self.partition[task.task_id])
        if self.agent.agent_id not in self.partition[task.task_id]:
            num_collaborator += 1

        distance = (self.agent.position - task.position).length()
        weight_factor_cost = 1.0
        return task.amount / (num_collaborator) - weight_factor_cost * distance

    def distributed_mutex(self, messages_received):        
        _satisfied = True
        _evolution_number = self.evolution_number
        _partition = self.partition
        _time_stamp = self.time_stamp
        
        for message in messages_received:
            if message['evolution_number'] > _evolution_number or (message['evolution_number'] == _evolution_number and message['time_stamp'] > _time_stamp):
                _evolution_number = message['evolution_number']
                _time_stamp = message['time_stamp']
                _partition = message['partition']
                _satisfied = False
        
        return _evolution_number, _time_stamp, _partition, _satisfied
                

    def get_assigned_task_id_from_partition(self, partition):
        for task_id, agents in partition.items():
            if self.agent.agent_id in agents:
                return task_id
        return None

