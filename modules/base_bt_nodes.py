from enum import Enum
import random
# BT Node List
class BTNodeList:
    CONTROL_NODES = [        
        'Sequence',
        'Fallback',
        'ReactiveSequence',
        'ReactiveFallback',
        'Parallel'
    ]

    ACTION_NODES = [
        'LocalSensingNode',
        'DecisionMakingNode',
        'GatherLocalInfo',
        'AssignTask'        
    ]

    CONDITION_NODES = [
    ]

# Status enumeration for behavior tree nodes
class Status(Enum):
    SUCCESS = 1
    FAILURE = 2
    RUNNING = 3

# Base class for all behavior tree nodes
class Node:
    def __init__(self, name):
        self.name = name
        self.type = None
        self.status = None

    async def run(self, agent, blackboard):
        raise NotImplementedError
    
    def halt(self):
        pass

    def reset(self):
        self.status = None
        if hasattr(self, "children"):
            for child in self.children:
                child.reset()
    

# Sequence node: Runs child nodes in sequence until one fails
class Sequence(Node):
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children
        self.current_child_index = 0  

    async def run(self, agent, blackboard):
        while self.current_child_index < len(self.children):
            status = await self.children[self.current_child_index].run(agent, blackboard)
            self.status = status

            if status == Status.RUNNING:
                return Status.RUNNING  
            elif status == Status.FAILURE:
                self.halt_children()
                self.current_child_index = 0  
                return Status.FAILURE
            elif status == Status.SUCCESS:
                self.current_child_index += 1  

        self.current_child_index = 0  
        self.halt_children()
        return Status.SUCCESS

    def halt_children(self):
        for child in self.children:
            child.halt() 

    def halt(self):
        self.current_child_index = 0

class ReactiveSequence(Node):
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children

    async def run(self, agent, blackboard):
        for child in self.children:
            status = await child.run(agent, blackboard)
            self.status = status
            if status == Status.FAILURE:
                self.halt_children()
                return Status.FAILURE  
            if status == Status.RUNNING:
                return Status.RUNNING  
        self.halt_children()
        return Status.SUCCESS  

    def halt_children(self):
        for child in self.children:
            child.halt()  

# Fallback node: Runs child nodes in sequence until one succeeds
class Fallback(Node):
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children
        self.current_child_index = 0  

    async def run(self, agent, blackboard):
        while self.current_child_index < len(self.children):
            status = await self.children[self.current_child_index].run(agent, blackboard)
            self.status = status

            if status == Status.RUNNING:
                return Status.RUNNING  
            elif status == Status.SUCCESS:
                self.halt_children()
                self.current_child_index = 0  
                return Status.SUCCESS
            elif status == Status.FAILURE:
                self.current_child_index += 1  

        self.current_child_index = 0  
        self.halt_children()
        return Status.FAILURE

    def halt_children(self):
        for child in self.children:
            child.halt()  

    def halt(self):
        self.current_child_index = 0            

class ReactiveFallback(Node):
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children

    async def run(self, agent, blackboard):
        for child in self.children:
            status = await child.run(agent, blackboard)
            self.status = status
            if status == Status.SUCCESS:
                self.halt_children()
                return Status.SUCCESS  
            if status == Status.RUNNING:
                return Status.RUNNING  
        
        self.halt_children()
        return Status.FAILURE  

    def halt_children(self):
        for child in self.children:
            child.halt()  

# Parallel node: Ticks all children sequentially in the same tick and returns by success_count / failure_count
class Parallel(Node):
    def __init__(self, name, children, success_count=None, failure_count=None):
        """
        success_count: number of SUCCESS children required for overall SUCCESS
                       (default: len(children))
        failure_count: number of FAILURE children causing overall FAILURE
                       (default: None → failures alone don't decide FAILURE)
        """
        super().__init__(name)
        self.children = children
        self.success_count = len(children) if success_count is None else success_count
        self.failure_count = failure_count  # None means ignore failures in final decision

    async def run(self, agent, blackboard):
        successes = 0
        failures = 0
        any_running = False

        # Tick all children sequentially within the same tick
        for child in self.children:
            status = await child.run(agent, blackboard)
            self.status = status  # update to latest child's status

            if status == Status.SUCCESS:
                successes += 1
            elif status == Status.FAILURE:
                failures += 1
            elif status == Status.RUNNING:
                any_running = True

        # Final decision after evaluating all children
        if successes >= self.success_count:
            self.halt_children()
            return Status.SUCCESS

        if self.failure_count is not None and failures >= self.failure_count:
            self.halt_children()
            return Status.FAILURE

        if any_running:
            return Status.RUNNING

        # All finished, thresholds not satisfied → FAILURE
        self.halt_children()
        return Status.FAILURE

    def halt_children(self):
        for child in self.children:
            child.halt()

    def halt(self):
        self.halt_children()


# Synchronous action node
class SyncAction(Node):
    def __init__(self, name, action):
        super().__init__(name)
        self.action = action
        self.type = "Action"

    async def run(self, agent, blackboard):
        result = self.action(agent, blackboard)
        blackboard[self.name] = result
        self.status = result
        return result

class SyncCondition(Node):
    def __init__(self, name, condition):
        super().__init__(name)
        self.condition = condition
        self.is_expanded = False
        self.type = "Condition"

    async def run(self, agent, blackboard):
        result = self.condition(agent, blackboard)
        blackboard[self.name] = {'status': result, 'is_expanded': self.is_expanded} 
        self.status = result
        return result

    def set_expanded(self):
        self.is_expanded = True

# Load additional configuration and import decision-making class dynamically
import importlib
from modules.utils import config
decision_making_module_path = config['decision_making']['plugin']
module_path, class_name = decision_making_module_path.rsplit('.', 1)
decision_making_module = importlib.import_module(module_path)
decision_making_class = getattr(decision_making_module, class_name)

# Local Sensing node
class LocalSensingNode(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._local_sensing)

    def _local_sensing(self, agent, blackboard):        
        blackboard['local_tasks_info'] = agent.get_tasks_nearby(with_completed_task = False)
        blackboard['local_agents_info'] = agent.local_message_receive()

        return Status.SUCCESS
    
# Decision-making node
class DecisionMakingNode(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._decide)
        self.decision_maker = decision_making_class(agent)

    def _decide(self, agent, blackboard):
        assigned_task_id = self.decision_maker.decide(blackboard)      
        agent.set_assigned_task_id(assigned_task_id)  
        blackboard['assigned_task_id'] = assigned_task_id
        if assigned_task_id is None:            
            return Status.FAILURE        
        else:                        
            return Status.SUCCESS

# Local Sensing node
class GatherLocalInfo(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._local_sensing)

    def _local_sensing(self, agent, blackboard):        
        blackboard['local_tasks_info'] = agent.get_tasks_nearby(with_completed_task = False)
        blackboard['local_agents_info'] = agent.local_message_receive()

        return Status.SUCCESS
    
# Decision-making node
class AssignTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._decide)
        self.decision_maker = decision_making_class(agent)

    def _decide(self, agent, blackboard):
        assigned_task_id = self.decision_maker.decide(blackboard)      
        agent.set_assigned_task_id(assigned_task_id)  
        blackboard['assigned_task_id'] = assigned_task_id
        if assigned_task_id is None:            
            return Status.FAILURE        
        else:                        
            return Status.SUCCESS    


class _IsTaskCompleted(SyncCondition):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard, task_id_key = 'task_id'):        
        _task_id = blackboard.get(task_id_key)
        if _task_id is None:
            raise ValueError(f"[{self.name}] Error: No {task_id_key} found in the blackboard!")
        
        task = agent.tasks_info[_task_id]
        if task.completed is True:
            # blackboard[task_id_key] = None
            # agent.set_assigned_task_id(None)
            return Status.SUCCESS  
        return Status.FAILURE          
    
class _IsArrivedAtTask(SyncCondition):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard, task_id_key = 'task_id', arrive_threshold = 10.0):
        _task_id = blackboard.get(task_id_key)
        if _task_id is None:
            raise ValueError(f"[{self.name}] Error: No {task_id_key} found in the blackboard!")

        agent_position = agent.position
        task_position = agent.tasks_info[_task_id].position
        # Calculate norm2 distance
        distance = (task_position - agent_position).length()

        if distance < agent.tasks_info[_task_id].radius + arrive_threshold: # Agent reached the task position                                                
            return Status.SUCCESS  
        return Status.FAILURE      
    
class _MoveToTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard, task_id_key = 'task_id'):
        _task_id = blackboard.get(task_id_key)
        if _task_id is None:
            raise ValueError(f"[{self.name}] Error: No {task_id_key} found in the blackboard!")
        
        # Move towards the task position
        task_position = agent.tasks_info[_task_id].position        
        agent.follow(task_position)  

        return Status.RUNNING     
    
class _ExecuteTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard, task_id_key = 'task_id'):
        _task_id = blackboard.get(task_id_key)
        if _task_id is None:
            raise ValueError(f"[{self.name}] Error: No {_task_id} found in the blackboard!")
        
        # Task Execution
        agent.tasks_info[_task_id].reduce_amount(agent.work_rate)
        agent.update_task_amount_done(agent.work_rate) 

        return Status.RUNNING     
        
class _ExecuteTaskWhileFollowing(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard, task_id_key = 'task_id'):
        _task_id = blackboard.get(task_id_key)
        if _task_id is None:
            raise ValueError(f"[{self.name}] Error: No {_task_id} found in the blackboard!")
        
        # Task Execution
        agent.tasks_info[_task_id].reduce_amount(agent.work_rate)
        agent.update_task_amount_done(agent.work_rate) 

        # Move towards the task position (gradually)
        task_position = agent.tasks_info[_task_id].position
        agent.follow(task_position)  

        return Status.RUNNING     
    
class _ExploreArea(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)
        self.random_move_time = float('inf')
        self.random_waypoint = (0, 0)

    def _update(self, agent, blackboard, agent_max_random_movement_duration = 1000, exploration_area = {'x_min': 0, 'x_max': 1400, 'y_min': 0, 'y_max': 1000}, sampling_time = 1.0):
        # Move towards a random position
        if self.random_move_time > agent_max_random_movement_duration:
            self.random_waypoint = self.get_random_position(exploration_area['x_min'], exploration_area['x_max'], exploration_area['y_min'], exploration_area['y_max'])
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