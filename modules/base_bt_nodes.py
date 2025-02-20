from enum import Enum
# BT Node List
class BTNodeList:
    CONTROL_NODES = [        
        'Sequence',
        'Fallback',
        'ReactiveSequence',
        'ReactiveFallback',

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

    async def run(self, agent, blackboard):
        raise NotImplementedError
    
    def halt(self):
        pass

# Sequence node: Runs child nodes in sequence until one fails
class Sequence(Node):
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children
        self.current_child_index = 0  

    async def run(self, agent, blackboard):
        while self.current_child_index < len(self.children):
            status = await self.children[self.current_child_index].run(agent, blackboard)

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



# Synchronous action node
class SyncAction(Node):
    def __init__(self, name, action):
        super().__init__(name)
        self.action = action

    async def run(self, agent, blackboard):
        result = self.action(agent, blackboard)
        blackboard[self.name] = result
        return result

class SyncCondition(Node):
    def __init__(self, name, condition):
        super().__init__(name)
        self.condition = condition
        self.is_expanded = False

    async def run(self, agent, blackboard):
        result = self.condition(agent, blackboard)
        blackboard[self.name] = {'status': result, 'is_expanded': self.is_expanded} 
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