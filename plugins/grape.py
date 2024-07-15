import random
import copy
from modules.utils import config

USE_GLOBAL_SA = config['agents']['GRAPE']['global_situational_awareness']
KEEP_MOVING_DURING_CONVERGENCE = config['agents']['GRAPE']['execute_movements_during_convergence']
INITIALIZE_PARTITION = config['agents']['GRAPE']['initialize_partition']
REINITIALIZE_PARTITION = config['agents']['GRAPE']['reinitialize_partition_on_completion']

class GRAPE:
    def __init__(self, agent):
        self.agent = agent        
        self.satisfied = False
        self.evolution_number = 0  # Initialize evolution_number
        self.time_stamp = 0  # Initialize time_stamp            
        self.partition = {task.task_id: set() for task in self.agent.tasks_info}  # Initialize partition with emptysets        
        self.assigned_task = None
        if INITIALIZE_PARTITION == "Distance":
            self.partition = self.initialize_partition_by_distance(self.agent.agents_info, self.agent.tasks_info, self.partition)
            self.assigned_task = self.agent.tasks_info[self.get_assigned_task_id_from_partition(self.partition)] # WARNING: This is global info      

        self.current_utilities = {}
    

    def initialize_partition_by_distance(self, agents_info, tasks_info, partition):
        for agent in agents_info:
            task_distance = {task.task_id: float('inf') if task.completed else (agent.position - task.position).length() for task in tasks_info}
            preferred_task_id = min(task_distance, key=task_distance.get)
            partition[preferred_task_id].add(agent.agent_id)
        return partition

    def get_neighbor_agents_info(self):
        _neighbor_agents_info = [neighbor_agent for neighbor_agent in self.agent.agents_info if neighbor_agent.agent_id in self.partition[self.assigned_task.task_id]]
        return _neighbor_agents_info

    def decide(self, blackboard):
        '''
        Output: 
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''           
        # Check if the existing task is done
        if USE_GLOBAL_SA:
            if self.assigned_task is not None and self.assigned_task.completed: 
                _neighbour_agents_info = self.get_neighbor_agents_info()    
                self.partition[self.assigned_task.task_id] = set()  # Empty the previous task's coalition                  
                self.assigned_task = None

                if REINITIALIZE_PARTITION == "Distance":                                    
                    self.partition = self.initialize_partition_by_distance(_neighbour_agents_info, self.agent.tasks_info, self.partition)                    
                    self.assigned_task = self.agent.tasks_info[self.get_assigned_task_id_from_partition(self.partition)] # WARNING: This is global info

                self.neutralize_assignment(blackboard) # TODO: Should be renamed?
        else:
            if 'task_completed' in blackboard and blackboard['task_completed'] is True: # TODO: Should be debugged
                self.neutralize_assignment(blackboard)


            
        # GRAPE algorithm for each agent (Phase 1)        
        if not self.satisfied:
            _max_task_id, _max_utility = self.find_max_utility_task()
            if _max_utility > self.compute_utility(self.assigned_task):                
                self.update_partition(_max_task_id)
                self.evolution_number += 1
                self.time_stamp = random.uniform(0, 1) 
                self.assigned_task = self.agent.tasks_info[self.get_assigned_task_id_from_partition(self.partition)] # WARNING: This is global info                    
            
            self.satisfied = True

            # Broadcasting # NOTE: Implemented separately
            self.agent.message_to_share = {
                'agent_id': self.agent.agent_id,
                'partition': self.partition, 
                'evolution_number': self.evolution_number,
                'time_stamp': self.time_stamp
                }
            
            return None

        
        # D-Mutex (Phase 2)            
        self.evolution_number, self.time_stamp, self.partition, self.satisfied = self.distributed_mutex(self.agent.messages_received)                
        self.agent.reset_messages_received()

        _assigned_task_id = self.get_assigned_task_id_from_partition(self.partition)
        self.assigned_task = self.agent.tasks_info[_assigned_task_id] if _assigned_task_id is not None else None

        if not self.satisfied:
            if not KEEP_MOVING_DURING_CONVERGENCE:
                self.agent.reset_movement()  # Neutralise the agent's current movement during converging to a Nash stable partition

        return _assigned_task_id



    def neutralize_assignment(self, blackboard): # WARNING: Only used when a task is finished
        self.satisfied = False
        blackboard['task_completed'] = None
        blackboard['assigned_task_id'] = None

    def discard_myself_from_coalition(self, task):
        if task is not None:
            self.partition[task.task_id].discard(self.agent.agent_id)


    
    def update_partition(self, preferred_task_id):                
        self.discard_myself_from_coalition(self.assigned_task)            
        self.partition[preferred_task_id].add(self.agent.agent_id)

    def find_max_utility_task(self):
        _current_utilities = {
            task.task_id: self.compute_utility(task) if not task.completed else float('-inf')
            for task in self.agent.tasks_info
        }

        _max_task_id = max(_current_utilities, key=_current_utilities.get)
        _max_utility = _current_utilities[_max_task_id]

        self.current_utilities = _current_utilities

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
                _evolution_number = copy.deepcopy(message['evolution_number'])
                _time_stamp = copy.deepcopy(message['time_stamp'])
                _partition = copy.deepcopy(message['partition'])
                _satisfied = False
        
        return _evolution_number, _time_stamp, _partition, _satisfied
                

    def get_assigned_task_id_from_partition(self, partition):
        return next((task_id for task_id, coalition_members_id in partition.items() if self.agent.agent_id in coalition_members_id), None)
