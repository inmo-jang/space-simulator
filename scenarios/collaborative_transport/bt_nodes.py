import math
import random
from modules.utils import config
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, ReactiveSequence, ReactiveFallback, SyncAction, GatherLocalInfo, AssignTask

# BT Node List
CUSTOM_ACTION_NODES = [
    'MoveToVertex',
    'WaitAgents',
    'MoveToBlockTarget',
    'MoveToSlotTarget',
    'SaveArrivedAgentOnTask',
    'LiftBlockTask',
    'PlaceDownBlockTask',
    'Explore'
]

CUSTOM_CONDITION_NODES = [
    'IsAllAgents',
    'IsArrivedAtBlockTarget',
    'IsArrivedAtSlotTarget',
    'IsBlockTaskLifted',
    'IsSlotTaskCompleted'
]

# BT Node List
BTNodeList.ACTION_NODES.extend(CUSTOM_ACTION_NODES)
BTNodeList.CONDITION_NODES.extend(CUSTOM_CONDITION_NODES)


# Scenario-specific Action/Condition Nodes
target_arrive_threshold = config['tasks']['threshold_done_by_arrival']
task_locations = config['tasks']['locations']
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
agent_max_random_movement_duration = config.get('agents', {}).get('random_exploration_duration', None)


class IsSlotTaskCompleted(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('slot_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")
        
        task = agent.tasks_info[assigned_task_id]
        if task.completed is True:
            assigned_block_task_id = blackboard.get('assigned_task_id')
            block_task = agent.tasks_info[assigned_block_task_id]
            block_task.set_delivered()
            agent.set_assigned_task_id(None)
            agent.set_color_id(None)
            return Status.SUCCESS  
        return Status.FAILURE 
    
class IsArrivedAtSlotTarget(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('slot_task_id')

        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")

        agent_position = agent.position
        
        task = agent.tasks_info[assigned_task_id]
        vertex_points = task.get_vertex_points()
        vertex_position = vertex_points[agent.target_vertex_idx]        

        # Calculate norm2 distance
        distance = math.sqrt((vertex_position[0] - agent_position[0])**2 + (vertex_position[1] - agent_position[1])**2)

        if distance <= target_arrive_threshold: # Agent reached the task position 
            agent.reset_movement()
            return Status.SUCCESS
        
        return Status.FAILURE
    
class IsBlockTaskLifted(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            # raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")
            return Status.FAILURE 
        
        task = agent.tasks_info[assigned_task_id]
        if task.completed is True:
            return Status.SUCCESS

        return Status.FAILURE 

class IsArrivedAtBlockTarget(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')

        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")

        agent_position = agent.position

        task = agent.tasks_info[assigned_task_id]
        vertex_points = task.get_vertex_points()
        if agent.target_vertex_idx is None:
            raise ValueError(f"[{self.name}] Error: No target_vertex_idx found in the blackboard!")            
        vertex_position = vertex_points[agent.target_vertex_idx]

        # Calculate norm2 distance
        distance = math.sqrt((vertex_position[0] - agent_position[0])**2 + (vertex_position[1] - agent_position[1])**2)

        if distance <= target_arrive_threshold: # Agent reached the task position   
            task.add_arrived_agent_set(agent.agent_id)
            agent.reset_movement()
            return Status.SUCCESS
        
        return Status.FAILURE


class IsAllAgents(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")

        task = agent.tasks_info[assigned_task_id]
        if task.vertex_arrived_agent_num_check():
            return Status.SUCCESS
        else:
            return Status.FAILURE
    
###################################################################
    
class WaitAgents(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)
        self.last_assigned_task_id = None

    def _update(self, agent, blackboard):
        return Status.RUNNING

# Load additional configuration and import decision-making class dynamically
import importlib
decision_making_module_path = config['decision_making']['plugin']
module_path, class_name = decision_making_module_path.rsplit('.', 1)
decision_making_module = importlib.import_module(module_path)
decision_making_class = getattr(decision_making_module, class_name)

# base_bt_nodes.py의 GatherLocalInfo()가 오버라이드 되었음
class GatherLocalInfo(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._local_sensing) 

    def _local_sensing(self, agent, blackboard):        
        blackboard['local_all_tasks_info'] = agent.get_all_tasks_nearby(with_completed_task = False)
        blackboard['local_tasks_info'] = agent.get_tasks_nearby(with_completed_task = False)
        blackboard['local_agents_info'] = agent.local_message_receive()

        return Status.SUCCESS

# base_bt_nodes.py의 AssignTask()가 오버라이드 되었음
class AssignTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._decide)
        self.decision_maker = decision_making_class(agent)

    def _decide(self, agent, blackboard):
        assigned_task_id = self.decision_maker.decide(blackboard)
        current_assigned_task_id = blackboard.get('assigned_task_id', None)

        if assigned_task_id is None:
            # Release existing one
            if current_assigned_task_id is not None:
                current_task = agent.tasks_info[current_assigned_task_id]
                current_task.remove_from_assigned_agent_set(agent.agent_id)
                current_task.remove_from_arrived_agent_set(agent.agent_id)
                blackboard['assigned_task_id'] = None
                blackboard['slot_task_id'] = None
                agent.set_assigned_task_id(None)
                agent.set_color_id(None)

            return Status.FAILURE

        # Check if new decision is the same as before
        if current_assigned_task_id == assigned_task_id:
            return Status.SUCCESS
        
        # If new decision is new 
        task = agent.tasks_info[assigned_task_id]

        vertex_idx = task.add_assigned_agent_set(agent.agent_id)
        if vertex_idx is None:
            return Status.FAILURE

        # Release existing one
        if current_assigned_task_id is not None:
            current_task = agent.tasks_info[current_assigned_task_id]
            current_task.remove_from_assigned_agent_set(agent.agent_id)
            current_task.remove_from_arrived_agent_set(agent.agent_id)

        # Set  
        blackboard['assigned_task_id'] = assigned_task_id
        blackboard['slot_task_id'] = task.matching_slot_id
        agent.set_assigned_task_id(assigned_task_id)
        agent.set_color_id(task.color_id)
        agent.set_target_vertex_idx(vertex_idx)

        return Status.SUCCESS


class MoveToBlockTarget(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")
        
        """ at vertex point """
        task = agent.tasks_info[assigned_task_id]
        vertex_points = task.get_vertex_points()
        if agent.target_vertex_idx is None:
            raise ValueError(f"[{self.name}] Error: No target_vertex_idx found in the blackboard!")            
        vertex_position = vertex_points[agent.target_vertex_idx]

        agent.follow(vertex_position)
        
        return Status.RUNNING
    

class MoveToSlotTarget(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('slot_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")

        """ at vertex point """
        task = agent.tasks_info[assigned_task_id]
        vertex_points = task.get_vertex_points()
        if agent.target_vertex_idx is None:
            raise ValueError(f"[{self.name}] Error: No target_vertex_idx found in the blackboard!")            
        vertex_position = vertex_points[agent.target_vertex_idx]
        
        agent.follow(vertex_position)
        
        return Status.RUNNING

class LiftBlockTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")
        
        # Task Execution
        agent.tasks_info[assigned_task_id].reduce_amount(agent.work_rate)
        agent.update_task_amount_done(agent.work_rate)

        return Status.RUNNING 

class PlaceDownBlockTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('slot_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned task found in the blackboard!")
        
        # Task Execution
        agent.tasks_info[assigned_task_id].reduce_amount(agent.work_rate)
        agent.update_task_amount_done(agent.work_rate) 

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