from enum import Enum
import math

# Status enumeration for behavior tree nodes
class Status(Enum):
    SUCCESS = 1
    FAILURE = 2
    RUNNING = 3

# Base class for all behavior tree nodes
class Node:
    def __init__(self, name):
        self.name = name

    async def run(self, agent, blackboard):
        raise NotImplementedError

# Sequence node: Runs child nodes in sequence until one fails
class Sequence(Node):
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children

    async def run(self, agent, blackboard):
        for child in self.children:
            status = await child.run(agent, blackboard)
            if status == Status.RUNNING:
                continue
            if status != Status.SUCCESS:
                return status
        return Status.SUCCESS

# Fallback node: Runs child nodes in sequence until one succeeds
class Fallback(Node):
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children

    async def run(self, agent, blackboard):
        for child in self.children:
            status = await child.run(agent, blackboard)
            if status == Status.RUNNING:
                continue
            if status != Status.FAILURE:
                return status
        return Status.FAILURE

# Synchronous action node
class SyncAction(Node):
    def __init__(self, name, action):
        super().__init__(name)
        self.action = action

    async def run(self, agent, blackboard):
        result = self.action(agent, blackboard)
        blackboard[self.name] = result
        return result

# Load additional configuration and import decision-making class dynamically
import importlib
from modules.utils import config
from plugins.my_decision_making_plugin import *
target_arrive_threshold = config['tasks']['threshold_done_by_arrival']

decision_making_module_path = config['agents']['decision_making_module_path']
module_path, class_name = decision_making_module_path.rsplit('.', 1)
decision_making_module = importlib.import_module(module_path)
decision_making_class = getattr(decision_making_module, class_name)

# Decision-making node
class DecisionMakingNode(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._decide)
        self.decision_maker = decision_making_class(agent, agent.tasks_info)

    def _decide(self, agent, blackboard):
        assigned_task_id = self.decision_maker.decide(blackboard)
        blackboard['assigned_task_id'] = assigned_task_id
        return Status.SUCCESS

# Consensus checking node
class ConsensusCheckingNode(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check_consensus)

    def _check_consensus(self, agent, blackboard):
        if 'assigned_task_id' not in blackboard:
            return Status.FAILURE
        
        assigned_task_id = blackboard['assigned_task_id']

        if assigned_task_id is None:
            return Status.FAILURE
        
        task_position = agent.tasks_info[assigned_task_id].position
        blackboard['task_position'] = task_position
        return Status.SUCCESS

# Task executing node
class TaskExecutingNode(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._execute_task)

    def _execute_task(self, agent, blackboard):
        task_position = blackboard.get('task_position')
        if task_position:
            agent_position = agent.position
            # Calculate norm2 distance
            distance = math.sqrt((task_position[0] - agent_position[0])**2 + (task_position[1] - agent_position[1])**2)
            
            assigned_task_id = blackboard['assigned_task_id']            
            if distance < agent.tasks_info[assigned_task_id].radius + target_arrive_threshold: # Agent reached the task position                                
                agent.tasks_info[assigned_task_id].reduce_amount(agent.work_rate)
                if agent.tasks_info[assigned_task_id].completed:                    
                    blackboard['task_completed'] = True
                    blackboard['assigned_task_id'] = None
                    return Status.SUCCESS

            # Move towards the task position
            agent.follow(task_position)

        return Status.RUNNING
