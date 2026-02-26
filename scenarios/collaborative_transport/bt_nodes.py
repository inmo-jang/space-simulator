import random
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, ReactiveSequence, ReactiveFallback, SyncAction, SyncCondition, GatherLocalInfo, AssignTask
from modules.base_bt_nodes import AssignTask as _AssignTask
# BT Node List
CUSTOM_ACTION_NODES = [
    'WaitAgents',
    'MoveToBlockTask',
    'MoveToSlotTask',
    'MoveToVertex',
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
    'IsArrivedAtVertex',
    'IsAllAgentsAtVertex',
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

class Explore(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)
        self.random_move_time = float('inf')
        self.random_waypoint = (0, 0)

    def _update(self, agent, blackboard):
        if self.random_move_time > agent_max_random_movement_duration:
            self.random_waypoint = (
                random.randint(task_locations['x_min'], task_locations['x_max']),
                random.randint(task_locations['y_min'], task_locations['y_max'])
            )
            self.random_move_time = 0

        self.random_move_time += sampling_time
        agent.follow(self.random_waypoint)
        return Status.RUNNING

    def halt(self):
        self.random_move_time = float('inf')

class SelectVertex(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)   

    def _update(self, agent, blackboard):        
        block_task_id = blackboard.get('block_task_id')
        if block_task_id is None:
            raise ValueError(f"[{self.name}] Error: No block_task_id found in the blackboard!")

        block_task = agent.tasks_info[block_task_id]
        # Vertex assignment if available
        _vertex_id = block_task.include_to_assigned_agents(agent.agent_id)            
        if _vertex_id is True: # Already assigned to me
            pass
        elif _vertex_id is False: # NOTE: Debug purpose -- When agents more than required are arrived
            return Status.FAILURE
        else:
            blackboard['slot_task_id'] = block_task.matching_slot_id 
            agent.set_vertex_id(_vertex_id)

        # Debug
        if len(block_task.ready_agents) < len(block_task.assigned_agents):
            ValueError(f"[BUG]")

        return Status.SUCCESS


class AssignTask(_AssignTask):
    def __init__(self, name, agent):
        super().__init__(name, agent)   
        self.prev_task_id = None

    def _decide(self, agent, blackboard):
        result = super()._decide(agent, blackboard)                
        if result is Status.SUCCESS:            
            assigned_task_id = blackboard.get('assigned_task_id')
            blackboard['block_task_id'] = assigned_task_id # For MoveToBlockTask
            block_task = agent.tasks_info[assigned_task_id]
            agent.set_color_id(block_task.color_id)

            # 현재 task랑 이전 task가 다르면 set 업데이트(remove)
            if self.prev_task_id is not None and self.prev_task_id != assigned_task_id:
                prev_task = agent.tasks_info[self.prev_task_id]
                prev_task.remove_from_assigned_agents(agent.agent_id)
                prev_task.remove_from_ready_agents(agent.agent_id)

            # 현재 task 저장
            self.prev_task_id = assigned_task_id
        else:
            blackboard['block_task_id'] = None
            agent.set_color_id(None)

            # 현재 task가 None이면 이전 task의 set 업데이트(remove)
            if self.prev_task_id is not None:
                prev_task = agent.tasks_info[self.prev_task_id]
                prev_task.remove_from_assigned_agents(agent.agent_id)
                prev_task.remove_from_ready_agents(agent.agent_id)

            # 현재 task(None) 저장
            self.prev_task_id = None
        return result
        

class IsArrivedAtBlockTask(SyncCondition):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        block_task_id = blackboard.get('block_task_id')
        if block_task_id is None:
            raise ValueError(f"[{self.name}] Error: No block_task_id found in the blackboard!")

        block_task = agent.tasks_info[block_task_id]

        # For Debug - # While this agent is moving towards to the task
        if block_task.is_all_agents_ready() and not agent.agent_id in block_task.ready_agents: # Other agents already gathered for this task
            # Reset
            raise ValueError(f"[{self.name}] Error: This task should have not been selected in AssignTask!")

        distance = (block_task.position - agent.position).length()
        if distance < block_task.radius:  # arrive_threshold=0
            agent.reset_movement()
            block_task.include_to_ready_agents(agent.agent_id)
            return Status.SUCCESS
        return Status.FAILURE

class MoveToBlockTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        block_task_id = blackboard.get('block_task_id')
        if block_task_id is None:
            return Status.FAILURE

        agent.follow(agent.tasks_info[block_task_id].position)
        return Status.RUNNING


class IsArrivedAtVertex(_IsArrivedAtVertex): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='block_task_id')
        if result is Status.SUCCESS:
            block_task_id = blackboard.get('block_task_id')
            block_task = agent.tasks_info[block_task_id]            
            block_task.include_to_vertex_arrival_agents(agent.agent_id)
            agent.reset_movement()
            if agent.agent_id not in block_task.ready_agents:
                raise ValueError(f"[{self.name}] Error: Agent {agent.agent_id} must be in ready_agents!")
        return result

class MoveToVertex(_MoveToVertex):
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='block_task_id')
        return result
        

class IsAllAgentsAtVertex(SyncAction): 
    def __init__(self, name, agent):
        super().__init__(name, self._update)   

    def _update(self, agent, blackboard): 
        block_task_id = blackboard.get('block_task_id')
        if block_task_id is None:
            raise ValueError(f"[{self.name}] Error: No block_task_id found in the blackboard!")
        
        block_task = agent.tasks_info[block_task_id]
        if block_task.is_all_agents_vertex_arrival(): 
            if agent.agent_id not in block_task.vertex_arrival_agents:
                raise ValueError(f"[{self.name}] Error: Agent {agent.agent_id} must be in vertex_arrival_agents!")
            return Status.SUCCESS            
        return Status.FAILURE
    
class IsAllAgents(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        block_task_id = blackboard.get('block_task_id')
        if block_task_id is None:
            raise ValueError(f"[{self.name}] Error: No block_task_id found in the blackboard!")

        block_task = agent.tasks_info[block_task_id]
        if block_task.is_all_agents_ready():            
            if agent.agent_id not in block_task.ready_agents:
                raise ValueError(f"[{self.name}] Error: Agent {agent.agent_id} must be in ready_agents!")
            return Status.SUCCESS # Go to the next phase
        else:
            return Status.FAILURE

class WaitAgents(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        agent.update_waiting_time(sampling_time)
        agent.update_cumulative_waiting_time(sampling_time)
        return Status.RUNNING

class IsBlockTaskLifted(SyncCondition):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        block_task_id = blackboard.get('block_task_id')
        if block_task_id is None:
            return Status.RUNNING

        task = agent.tasks_info[block_task_id]
        if task.completed is True:
            return Status.SUCCESS
        return Status.FAILURE

class LiftBlockTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        block_task_id = blackboard.get('block_task_id')
        if block_task_id is None:
            raise ValueError(f"[{self.name}] Error: No block_task_id found in the blackboard!")

        agent.tasks_info[block_task_id].reduce_amount(agent.work_rate)
        agent.update_task_amount_done(agent.work_rate)
        return Status.RUNNING


class IsSlotTaskCompleted(SyncCondition):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        slot_task_id = blackboard.get('slot_task_id')
        if slot_task_id is None:
            return Status.RUNNING

        task = agent.tasks_info[slot_task_id]
        if task.completed is True:
            block_task_id = blackboard.get('block_task_id')
            block_task = agent.tasks_info[block_task_id]
            block_task.set_delivered()
            agent.set_assigned_task_id(None)
            agent.set_color_id(None)
            return Status.SUCCESS
        return Status.FAILURE

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

class PlaceDownBlockTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        slot_task_id = blackboard.get('slot_task_id')
        if slot_task_id is None:
            raise ValueError(f"[{self.name}] Error: No slot_task_id found in the blackboard!")

        agent.tasks_info[slot_task_id].reduce_amount(agent.work_rate)
        agent.update_task_amount_done(agent.work_rate)
        return Status.RUNNING
