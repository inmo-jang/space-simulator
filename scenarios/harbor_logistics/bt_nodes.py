from enum import Enum
import math
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, SyncAction, LocalSensingNode, DecisionMakingNode


# BT Node List
CUSTOM_ACTION_NODES = [
    'GoToShip',
    'PickItem',
    'GoToDestination',
    'PlaceItem'
]

CUSTOM_CONDITION_NODES = [
    'IsFinishedTask',
    'IsHoldingItem',
    'IsArrivedAtShip',
    'IsArrivedAtDestination'
]

BTNodeList.ACTION_NODES.extend(CUSTOM_ACTION_NODES)
BTNodeList.CONDITION_NODES.extend(CUSTOM_CONDITION_NODES)


# Scenario-specific Action/Condition Nodes
from modules.utils import config
target_arrive_threshold = config['tasks']['threshold_done_by_arrival']
task_locations1 = config['tasks']['locations1']
task_locations2 = config['tasks']['locations2']
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
agent_max_random_movement_duration = config.get('agents', {}).get('random_exploration_duration', None)


# Condition nodes
class IsFinishedTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)        

    def _check(self, agent, blackboard):        
        task_completed = blackboard.get('task_completed', False)        
        if task_completed is False:            
            return Status.FAILURE        
        else:      
            print(f"Agent {agent.agent_id}: Task completed!")   
            blackboard['task_completed'] = False
            blackboard['assigned_task_id'] = None
            return Status.SUCCESS

class IsHoldingItem(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)        

    def _check(self, agent, blackboard):        
        assigned_task_id = blackboard.get('assigned_task_id', None)
        if assigned_task_id is None:            
            return Status.FAILURE        
        else:            
            return Status.SUCCESS

class IsArrivedAtShip(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)        

    def _check(self, agent, blackboard):        
        status = blackboard.get('status', None)
        if status == "AtShip":            
            blackboard['waypoints'] = None # Reset
            return Status.SUCCESS       
        else:            
            return Status.FAILURE

class IsArrivedAtDestination(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)        

    def _check(self, agent, blackboard):        
        status = blackboard.get('status', None)
        if status == "AtDestination":            
            blackboard['waypoints'] = None # Reset
            return Status.SUCCESS       
        else:            
            return Status.FAILURE


# Action nodes
class GoToShip(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._move)
        self.waypoint_follower = WaypointFollower(agent, target_arrive_threshold)
        self.path_planner = PathPlanner(agent)
        self.agent_id = agent.agent_id
        task_locations1 = config['tasks']['locations1']
        task_locations2 = config['tasks']['locations2']

        # 에이전트 ID에 따라 pickup 위치 결정
        if self.agent_id % 2 == 1:  # 홀수 에이전트
            self.position_to_pickup = (
                (task_locations1['x_min'] + task_locations1['x_max']) / 2,
                (task_locations1['y_min'] + task_locations1['y_max']) / 2,
            )
        else:  # 짝수 에이전트
            self.position_to_pickup = (
                (task_locations2['x_min'] + task_locations2['x_max']) / 2,
                (task_locations2['y_min'] + task_locations2['y_max']) / 2,
            )
            
    def _move(self, agent, blackboard):
        waypoints = blackboard.get('waypoints', None)

        # Path Generation
        if waypoints is None:
            self.path_planner.set_target_position(self.position_to_pickup)
            waypoints = self.path_planner.generate('xy')
            self.waypoint_follower.set_waypoints(waypoints)
            blackboard['waypoints'] = waypoints

        # Waypoint Following
        result = self.waypoint_follower.move()
        if result == Status.SUCCESS:
            blackboard['status'] = "AtShip"
            blackboard['waypoints'] = None # Reset

        return result

class GoToDestination(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._move)
        self.waypoint_follower = WaypointFollower(agent, target_arrive_threshold)
        self.path_planner = PathPlanner(agent)

    def _move(self, agent, blackboard):
        waypoints = blackboard.get('waypoints', None)

        # Path Generation
        if waypoints is None:
            assigned_task_id = blackboard.get('assigned_task_id')  
            position_to_deliver = agent.tasks_info[assigned_task_id].position_to_deliver        
            self.path_planner.set_target_position(position_to_deliver)
            waypoints = self.path_planner.generate('xy')
            blackboard['waypoints'] = waypoints
            self.waypoint_follower.set_waypoints(waypoints)

        # Waypoint Following        
        result = self.waypoint_follower.move()
        if result == Status.SUCCESS:
            blackboard['status'] = "AtDestination"
            blackboard['waypoints'] = None # Reset

        return result

class PathPlanner():
    def __init__(self, agent):
        self.agent = agent
        self.target_position = None

    def set_target_position(self, target_position):
        self.target_position = target_position

    def generate(self, option='xy'):
        """
        Generates waypoints following the Manhattan grid, adding waypoints only at turns.
        The `option` parameter controls the order of movement:
        - 'xy' (default): Move in x-direction first, then y-direction.
        - 'yx': Move in y-direction first, then x-direction.
        """
        waypoints = []
        agent_position = self.agent.position

        # Current agent coordinates
        current_x, current_y = agent_position
        # Target coordinates
        target_x, target_y = self.target_position

        if option == 'xy':
            # Move in x-direction first, then y-direction
            if current_x != target_x:
                waypoints.append((target_x, current_y))
            if current_y != target_y:
                waypoints.append((target_x, target_y))
        elif option == 'yx':
            # Move in y-direction first, then x-direction
            if current_y != target_y:
                waypoints.append((current_x, target_y))
            if current_x != target_x:
                waypoints.append((target_x, target_y))

        return waypoints
    




class WaypointFollower():
    def __init__(self, agent, target_arrive_threshold):
        self.next_waypoint_index = 0  # Initialize the index for the next waypoint
        self.waypoints = None
        self.agent = agent
        self.target_arrive_threshold = target_arrive_threshold

    def reset(self):
        self.next_waypoint_index = 0
        self.waypoints = None

    def set_waypoints(self, waypoints):
        self.waypoints = waypoints

    def move(self):

        agent_position = self.agent.position
        next_waypoint = self.waypoints[self.next_waypoint_index]
        # Calculate the Euclidean distance to the next waypoint
        distance = math.sqrt((next_waypoint[0] - agent_position[0])**2 + 
                             (next_waypoint[1] - agent_position[1])**2)

        if distance < self.target_arrive_threshold:
            self.next_waypoint_index += 1  # Move to the next waypoint
            if self.next_waypoint_index >= len(self.waypoints):
                self.reset()
                return Status.SUCCESS  # Return SUCCESS when all waypoints are visited

        self.agent.follow(next_waypoint)  # Command the agent to follow the current waypoint

        return Status.RUNNING  # Keep RUNNING if not all waypoints have been visited







class PickItem(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._action)

    def _action(self, agent, blackboard):
        unassigned_tasks = agent.get_unassigned_tasks()
        if len(unassigned_tasks) == 0: # TODO: 모든 job 끝나면 일단 Pick-up position에서 대기
            return Status.FAILURE
        
        # assigned_task = random.choice(unassigned_tasks)
        assigned_task = unassigned_tasks[-1] # Pick the last (화면 렌더링과 연관)
        assigned_task.set_assigned_to(agent.agent_id)
        agent.set_assigned_task_id(assigned_task.task_id)
        blackboard['assigned_task_id'] = agent.assigned_task_id

        agent.task_color = assigned_task.color
        agent.update_image()

        return Status.SUCCESS


class PlaceItem(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._action)

    def _action(self, agent, blackboard):
        agent.tasks_info[agent.assigned_task_id].set_done()
        agent.set_assigned_task_id(None)
        blackboard['assigned_task_id'] = None

        agent.task_color = None
        agent.update_image()

        return Status.SUCCESS
    