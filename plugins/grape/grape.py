import random
import copy
from modules.utils import config

KEEP_MOVING_DURING_CONVERGENCE = config['decision_making']['GRAPE'].get('execute_movements_during_convergence', False) # TODO: Remove later as this is just for backward compatibility
LOCAL_CONVERGENCE = config['decision_making']['GRAPE'].get('local_convergence', False)
INITIALIZE_PARTITION = config['decision_making']['GRAPE']['initialize_partition']
REINITIALIZE_PARTITION = config['decision_making']['GRAPE']['reinitialize_partition_on_completion']
COST_WEIGHT_FACTOR = config['decision_making']['GRAPE']['cost_weight_factor']
SOCIAL_INHIBITION_FACTOR = config['decision_making']['GRAPE']['social_inhibition_factor']

class GRAPE:
    def __init__(self, agent):
        self.agent = agent        
        self.satisfied = False
        self.evolution_number = 0  # Initialize evolution_number
        self.time_stamp = 0  # Initialize time_stamp            
        self.partition = {}  # Initialize partition with emptysets        
        self.assigned_task = None           

        self.current_utilities = {}
        self.agent.message_to_share = { # Message Initialization
            'agent_id': self.agent.agent_id,
            'partition': self.partition, 
            'evolution_number': self.evolution_number,
            'time_stamp': self.time_stamp
            } 


    def initialize_partition_by_distance(self, agents_info, tasks_info, partition):
        for agent in agents_info:
            task_distance = {task.task_id: float('inf') if task.completed else (agent.position - task.position).length() for task in tasks_info}
            if len(task_distance) > 0:
                preferred_task_id = min(task_distance, key=task_distance.get)
                self.partition.setdefault(preferred_task_id, set()) # Ensure the task_id key exists in the partition. Set tis value as empty set if it doesn't already exist (This is for dynamic task generation)
                partition[preferred_task_id].add(agent.agent_id)
        return partition

    def get_neighbor_agents_info_in_partition(self, partition):
        _neighbor_agents_info = [neighbor_agent for neighbor_agent in self.agent.agents_info if neighbor_agent.agent_id in partition[self.assigned_task.task_id]]
        return _neighbor_agents_info

    def decide(self, blackboard):
        '''
        Output: 
            - `task_id`, if task allocation works well
            - `None`, otherwise
        '''           

        previous_assigned_task_id = self.assigned_task.task_id if self.assigned_task is not None else None  # For Debug

        local_tasks_info = blackboard.get('local_tasks_info', {})

        # D-Mutex (Phase 1)
        self.evolution_number, self.time_stamp, self.partition, self.satisfied = self.distributed_mutex(self.agent.messages_received)
        self.assigned_task = self.get_assigned_task_from_partition(self.partition, local_tasks_info)
        
        # Check if the existing task is done or not available anymore (e.g., completed by others, disappeared due to dynamic environment, etc.)        
        if self.assigned_task is None and previous_assigned_task_id is not None and previous_assigned_task_id not in local_tasks_info:
            # _neighbor_agents_info = self.get_neighbor_agents_info_in_partition(self.partition)    
            # Default routine
            self.partition[previous_assigned_task_id] = set()  # Empty the previous task's coalition                  
            self.assigned_task = None
            self.satisfied = False
            

        # Give up the decision-making process if there is no task nearby 
        if len(local_tasks_info) == 0: 
            return None


        # GRAPE algorithm for each agent (Phase 2)
        candidates = list(local_tasks_info.values())        
        _max_task_id, _max_utility = self.find_max_utility_task(candidates)
        
        if _max_utility == float('-inf'): # Somehow, there is no selectable task, i.e., void task
            return None
                
        _current_utility = self.compute_utility(self.assigned_task)
        if _max_utility > _current_utility: 
            self.update_partition(_max_task_id)
            self.evolution_number += 1
            self.time_stamp = random.uniform(0, 1)      
            self.assigned_task = self.get_assigned_task_from_partition(self.partition, local_tasks_info) # New assignment
            self.satisfied = True

            # Broadcasting # NOTE: Implemented separately
            self.agent.message_to_share = {
                'agent_id': self.agent.agent_id,
                'assigned_task_id': self.assigned_task.task_id if self.assigned_task is not None else None,
                'partition': self.partition, 
                'evolution_number': self.evolution_number,
                'time_stamp': self.time_stamp
                }
            
            # NOTE: Since the assigned task has changed, this indicates that convergence has not yet been reached, so it returns None
            return None
                    

        return copy.deepcopy(self.assigned_task.task_id) if self.assigned_task is not None else None




    def discard_myself_from_coalition(self, task):
        if task is not None:
            self.partition[task.task_id].discard(self.agent.agent_id)


    
    def update_partition(self, preferred_task_id):                
        self.discard_myself_from_coalition(self.assigned_task)            
        self.partition[preferred_task_id].add(self.agent.agent_id)

    def find_max_utility_task(self, tasks_info):
        _current_utilities = {
            task.task_id : self.compute_utility(task) for task in tasks_info
        }

        _max_task_id = max(_current_utilities, key=_current_utilities.get)
        _max_utility = _current_utilities[_max_task_id]

        self.current_utilities = _current_utilities

        return _max_task_id, _max_utility

    def compute_utility(self, task): # Individual Utility Function  
        if task is None:
            return float('-inf')

        self.partition.setdefault(task.task_id, set()) # Ensure the task_id key exists in the partition. Set tis value as empty set if it doesn't already exist (This is for dynamic task generation)
        num_collaborator = len(self.partition[task.task_id])
        if self.agent.agent_id not in self.partition[task.task_id]:
            num_collaborator += 1

        distance = (self.agent.position - task.position).length()              
        utility = task.amount / (num_collaborator) - COST_WEIGHT_FACTOR * distance * (num_collaborator ** SOCIAL_INHIBITION_FACTOR) 
        return utility

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
        
        _final_partition = {k: set(v) for k, v in _partition.items()}
        return _evolution_number, _time_stamp, _final_partition, _satisfied
                

    def get_assigned_task_from_partition(self, partition, tasks_info):

        active_partition = {task_id: members for task_id, members in partition.items() if task_id in tasks_info}
        _assigned_task_id = next(
            (task_id for task_id, members in active_partition.items()
             if self.agent.agent_id in members),
            None
        )
        return tasks_info.get(_assigned_task_id)
