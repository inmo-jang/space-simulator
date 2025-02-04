import math
import random
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, ReactiveSequence, ReactiveFallback, SyncAction, GatherLocalInfo, AssignTask

# BT Node List
CUSTOM_ACTION_NODES = [
    'MoveToTarget',
    'ExecuteTask',
    'Explore'
]

CUSTOM_CONDITION_NODES = [
    'IsTaskCompleted',
    'IsArrivedAtTarget',
]

# BT Node List
BTNodeList.ACTION_NODES.extend(CUSTOM_ACTION_NODES)
BTNodeList.CONDITION_NODES.extend(CUSTOM_CONDITION_NODES)


# Scenario-specific Action/Condition Nodes
from modules.utils import config
target_arrive_threshold = config['tasks']['threshold_done_by_arrival']
task_locations = config['tasks']['locations']
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
agent_max_random_movement_duration = config.get('agents', {}).get('random_exploration_duration', None)


class IsTaskCompleted(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")
        
        task = agent.tasks_info[assigned_task_id]
        if task.completed is True:
            blackboard['assigned_task_id'] = None
            # agent.set_assigned_task_id(None)
            return Status.SUCCESS  
        return Status.FAILURE  
    
class IsArrivedAtTarget(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")

        agent_position = agent.position
        task_position = agent.tasks_info[assigned_task_id].position
        # Calculate norm2 distance
        distance = math.sqrt((task_position[0] - agent_position[0])**2 + (task_position[1] - agent_position[1])**2)

        if distance < agent.tasks_info[assigned_task_id].radius + target_arrive_threshold: # Agent reached the task position                                                
            return Status.SUCCESS  
        return Status.FAILURE  
        
class MoveToTarget(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")
        
        # Move towards the task position
        task_position = agent.tasks_info[assigned_task_id].position        
        agent.follow(task_position)  

        return Status.RUNNING 
    
class ExecuteTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")
        
        # Task Execution
        agent.tasks_info[assigned_task_id].reduce_amount(agent.work_rate)
        agent.update_task_amount_done(agent.work_rate) 

        # Move towards the task position (gradually)
        task_position = agent.tasks_info[assigned_task_id].position
        agent.follow(task_position)  


        return Status.RUNNING 

class Explore(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._random_explore)
        self.random_move_time = float('inf')
        self.random_waypoint = (0, 0)

    def _random_explore(self, agent, blackboard):
        # Move towards a random position
        if self.random_move_time > agent_max_random_movement_duration:
            self.random_waypoint = self.get_random_position(task_locations['x_min'], task_locations['x_max'], task_locations['y_min'], task_locations['y_max'])
            self.random_move_time = 0 # Initialisation
        
        self.random_move_time += sampling_time   
        agent.follow(self.random_waypoint)         
        return Status.RUNNING
        
    def get_random_position(self, x_min, x_max, y_min, y_max):
        pos = (random.randint(x_min, x_max),
                random.randint(y_min, y_max))
        return pos
    
    def halt(self):
        self.random_move_time = float('inf')
        