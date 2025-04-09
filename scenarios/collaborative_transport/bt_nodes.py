import math
import random
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, ReactiveSequence, ReactiveFallback, SyncAction, GatherLocalInfo, AssignTask
from modules.base_bt_nodes import _IsTaskCompleted, _ExecuteTask, _ExploreArea
# BT Node List
CUSTOM_ACTION_NODES = [
    'WaitAgents',
    'MoveToBlockTask',
    'MoveToSlotTask',
    'LiftBlockTask',
    'PlaceDownBlockTask',
    'SelectVertex',
    'ExecuteTask',
    'Explore'
]

CUSTOM_CONDITION_NODES = [
    'IsTaskCompleted',
    'IsAllAgents',
    'IsArrivedAtBlockTask',
    'IsArrivedAtSlotTask',
    'IsBlockTaskLifted',
    'IsSlotTaskCompleted'
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


class _MoveToVertex(SyncAction): # Base Node
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard, task_id_key):
        _task_id = blackboard.get(task_id_key)
        if _task_id is None:
            raise ValueError(f"[{self.name}] Error: No {_task_id} found in the blackboard!")
        
        """ at vertex point """
        task = agent.tasks_info[_task_id]
        vertex_positions = task.get_vertex_positions()
        if agent.assigned_vertex_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned_vertex_id found!")            
        vertex_position = vertex_positions[agent.assigned_vertex_id]

        agent.follow(vertex_position)
        
        return Status.RUNNING

class _IsArrivedAtVertex(SyncAction): # Base Node
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard, task_id_key):
        _task_id = blackboard.get(task_id_key)
        if _task_id is None:
            raise ValueError(f"[{self.name}] Error: No {_task_id} found in the blackboard!")

        agent_position = agent.position

        """ at vertex point """
        task = agent.tasks_info[_task_id]
        vertex_positions = task.get_vertex_positions()
        if agent.assigned_vertex_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned_vertex_id found!")            
        vertex_position = vertex_positions[agent.assigned_vertex_id]

        # Calculate norm2 distance
        distance = (vertex_position - agent_position).length()

        if distance <= target_arrive_threshold: # Agent reached the task position   
            return Status.SUCCESS
        
        return Status.FAILURE

class GatherLocalInfo(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._local_sensing)

    def _local_sensing(self, agent, blackboard):        
        blackboard['local_tasks_info'] = agent.get_block_tasks_nearby(with_completed_task = False)
        blackboard['local_agents_info'] = agent.local_message_receive()

        return Status.SUCCESS

class Explore(_ExploreArea): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, agent_max_random_movement_duration=agent_max_random_movement_duration, exploration_area=task_locations, sampling_time=sampling_time)
        return result

class SelectVertex(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)   

    def _update(self, agent, blackboard):        
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned_task_id found in the blackboard!")

        current_block_task_id = blackboard.get('block_task_id', None)
        if assigned_task_id is not current_block_task_id: # New decision
            # Release existing one
            if current_block_task_id is not None:
                current_block_task = agent.tasks_info[current_block_task_id]
                current_block_task.remove_from_assigned_agents(agent.agent_id)
                current_block_task.remove_from_ready_agents(agent.agent_id)
                
            # Set new one
            new_block_task = agent.tasks_info[assigned_task_id]
            _vertex_id = new_block_task.include_to_assigned_agents(agent.agent_id)
            if _vertex_id is False:                
                # Due to sequential process of agent.run_tree(), some leaving agents may be not fully left yet
                # print(f"[{self.name}] Error: _vertex_id is None. some leaving agents may be not fully left yet")                            
                return Status.RUNNING                
            else:
                blackboard['block_task_id'] = assigned_task_id
                blackboard['slot_task_id'] = new_block_task.matching_slot_id                        
                agent.set_assigned_task_id(assigned_task_id)
                agent.set_color_id(new_block_task.color_id)
                agent.set_vertex_id(_vertex_id)            
                return Status.SUCCESS 
        else:            
            return Status.SUCCESS

class IsArrivedAtBlockTask(_IsArrivedAtVertex): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='block_task_id')
        if result is Status.SUCCESS:
            block_task_id = blackboard.get('block_task_id')
            block_task = agent.tasks_info[block_task_id]
            block_task.include_to_ready_agents(agent.agent_id)
            agent.reset_movement()
        return result

class MoveToBlockTask(_MoveToVertex):
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='block_task_id')
        return result
        

    
class IsAllAgents(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        block_task_id = blackboard.get('block_task_id')
        if block_task_id is None:
            raise ValueError(f"[{self.name}] Error: No block_task_id found in the blackboard!")

        block_task = agent.tasks_info[block_task_id]
        if block_task.is_all_agents_ready():
            return Status.SUCCESS
        else:
            return Status.FAILURE

class WaitAgents(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        agent.update_waiting_time(sampling_time)
        agent.update_cumulative_waiting_time(sampling_time)
        return Status.RUNNING

class IsBlockTaskLifted(_IsTaskCompleted): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='block_task_id')
        return result

class LiftBlockTask(_ExecuteTask): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='block_task_id')
        return result

    
class IsSlotTaskCompleted(_IsTaskCompleted): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='slot_task_id')
        if result is Status.SUCCESS:
            block_task_id = blackboard.get('block_task_id')
            block_task = agent.tasks_info[block_task_id]
            block_task.set_delivered()
            agent.set_assigned_task_id(None)
            agent.set_color_id(None)            
        return result

class IsArrivedAtSlotTask(_IsArrivedAtVertex): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='slot_task_id')
        if result is Status.SUCCESS:
            agent.reset_movement() # TODO: Remove if not necessary
        return result
    
class MoveToSlotTask(_MoveToVertex):
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='slot_task_id')
        return result        

class PlaceDownBlockTask(_ExecuteTask): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='slot_task_id')
        return result    


