from enum import Enum
import math
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, SyncAction, LocalSensingNode, DecisionMakingNode
from plugins.path_planner.plugin_manager import planner_manager

# BT Node List
CUSTOM_ACTION_NODES = [
    'GoToShip',
    'PickItem',
    'GoToDestination',
    'PlaceItem',
    'DecideShip',
    'GoToChargingStation',
    'ChargeBattery'
]

CUSTOM_CONDITION_NODES = [
    'IsFinishedTask',
    'IsHoldingItem',
    'IsArrivedAtShip',
    'IsArrivedAtDestination',
    'IsArrivedAtChargingStation',
    'IsBatteryLow'
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

        
class IsArrivedAtChargingStation(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)

    def _check(self, agent, blackboard):
        status = blackboard.get('status', None)
        if status == "AtChargingStation":  # 충전소에 도착했는지 확인
            blackboard['waypoints'] = None  # 경로 초기화
            print(f"Agent {agent.agent_id}: Arrived at charging station.")
            return Status.SUCCESS
        return Status.FAILURE


class IsBatteryLow(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)
        self.battery_threshold = 20  # 배터리 임계값 (%)

    def _check(self, agent, blackboard):

        if blackboard.get('fulled', False):
            return Status.FAILURE

        if agent.battery <= self.battery_threshold or blackboard.get('is_charging', False) :
            print(f"Agent {agent.agent_id}: Battery is low ({agent.battery}%). Moving to the charging station.")
            blackboard['is_going_to_charging_station'] = True
            blackboard['waypoints'] = None  # 기존 경로 초기화
            return Status.SUCCESS
        
        return Status.FAILURE

# Action nodes
class DecideShip(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._decide)

    def _decide(self, agent, blackboard):
        import random
        
         # Ship을 한번만 선택
        if blackboard.get('ship_selected', False):
            return Status.SUCCESS
        
        # Ship 선택: Ship1 또는 Ship2
        chosen_ship = random.choice(['Ship1', 'Ship2'])
        blackboard['chosen_ship'] = chosen_ship
        blackboard['ship_selected'] = True
        print(f"Agent {agent.agent_id}: Decided to go to {chosen_ship}")
        return Status.SUCCESS

class GoToShip(SyncAction):
    def __init__(self, name, agent, planner_name='xy'):
        super().__init__(name, self._move)
        self.waypoint_follower = WaypointFollower(agent, target_arrive_threshold)
        self.path_planner = planner_manager.get_planner(planner_name, agent)
            
    def _move(self, agent, blackboard):

        if blackboard.get('is_going_to_charging_station', False):
            #print(f"Agent {agent.agent_id}: Currently heading to charging station.")
            return Status.FAILURE
        if blackboard.get('is_charging', False):
            #print(f"Agent {agent.agent_id}: Currently charging.")
            return Status.FAILURE
        # 충전소 경로 초기화 확인
        if blackboard.get('charging_station_waypoints', None) is not None:
            #print(f"Agent {agent.agent_id}: Still has charging station waypoints.")
            return Status.FAILURE

        waypoints = blackboard.get('waypoints', None)

        # 선택된 Ship 위치 가져오기
        chosen_ship = blackboard.get('chosen_ship', None)
        if chosen_ship is None:
            print(f"Agent {agent.agent_id}: No ship selected!")
            return Status.FAILURE
        
        # Ship 위치 설정
        if waypoints is None:
            if chosen_ship == 'Ship1':
                position_to_pickup = (
                    (task_locations1['x_min'] + task_locations1['x_max']) / 2,
                    (task_locations1['y_min'] + task_locations1['y_max']) / 2,
                )
            elif chosen_ship == 'Ship2':
                position_to_pickup = (
                    (task_locations2['x_min'] + task_locations2['x_max']) / 2,
                    (task_locations2['y_min'] + task_locations2['y_max']) / 2,
                )
            else:
                print(f"Agent {agent.agent_id}: Unknown ship {chosen_ship}")
                return Status.FAILURE
            
            self.path_planner.set_target_position(position_to_pickup)
            waypoints = self.path_planner.generate('xy')
            self.waypoint_follower.set_waypoints(waypoints)
            blackboard['waypoints'] = waypoints

        # Waypoint Following
        result = self.waypoint_follower.move()
        #print("goingtoship")
        if result == Status.SUCCESS:
            blackboard['status'] = "AtShip"
            blackboard['waypoints'] = None # Reset

        return result

class GoToDestination(SyncAction):
    def __init__(self, name, agent, planner_name="xy"):
        super().__init__(name, self._move)
        self.waypoint_follower = WaypointFollower(agent, target_arrive_threshold)
        self.path_planner = planner_manager.get_planner(planner_name, agent)

    def _move(self, agent, blackboard):

        if blackboard.get('is_going_to_charging_station', False):
            return Status.FAILURE
        if blackboard.get('is_charging', False):
            return Status.FAILURE

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

class GoToChargingStation(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._move)
        self.agent = agent
        self.target_arrive_threshold = target_arrive_threshold

        # 에이전트 ID에 따라 충전소 위치 계산
        x = config['charging_station_position']['x']
        y = config['charging_station_position']['y']
        offset_x = config['charging_station_position']['offset_x']

        self.charging_station_position = (
            x + agent.agent_id * offset_x,
            y
        )
        #print(f"Agent {self.agent.agent_id}: Target charging station position: {self.charging_station_position}")

    def calculate_waypoints(self, start_position, end_position):
        """현재 위치에서 목표 위치(충전소)까지 경로를 생성, Waypoints를 최소화하여 효율적으로 설정"""
        path = []

        current_x, current_y = start_position
        target_x, target_y = end_position

        # x축 Waypoint 추가 (x좌표만 맞추기)
        if current_x != target_x:
            path.append((target_x, current_y))  # x좌표만 변경된 지점

        # y축 Waypoint 추가 (y좌표 맞추기)
        if current_y != target_y:
            path.append((target_x, target_y))  # 최종 충전소 위치

        return path

    def _move(self, agent, blackboard):

        if blackboard.get('is_charging', False):  # 충전 중일 때는 이동 금지
            return Status.FAILURE
        
        # 충전소로 가는 중 상태 설정
        blackboard['is_going_to_charging_station'] = True

        # 충전소 경로 확인 및 초기화
        charging_station_waypoints = blackboard.get('charging_station_waypoints', None)
        
        if charging_station_waypoints is None or not charging_station_waypoints:  # 기존 경로가 없거나 비어있을 때만 새 경로 생성
            current_position = agent.position
            charging_station_waypoints = self.calculate_waypoints(current_position, self.charging_station_position)
            blackboard['charging_station_waypoints'] = charging_station_waypoints
                    
        # Waypoints 따라 이동
        if charging_station_waypoints:
            next_waypoint2 = charging_station_waypoints[0]
            distance = math.sqrt(
                (next_waypoint2[0] - agent.position[0])**2 +
                (next_waypoint2[1] - agent.position[1])**2
            )
            
            if distance < self.target_arrive_threshold:
                charging_station_waypoints.pop(0)
                blackboard['charging_station_waypoints'] = charging_station_waypoints

                # waypoints2가 비어있으면 충전소 도착 처리
                if not charging_station_waypoints:  
                    print(f"Agent {agent.agent_id}: Arrived at charging station.")
                    blackboard['status'] = "AtChargingStation"
                    blackboard['charging_station_waypoints'] = None  # 초기화
                    blackboard['is_going_to_charging_station'] = False
                    return Status.SUCCESS  # 성공 상태 반환
        
            agent.follow(next_waypoint2)
            return Status.RUNNING

        return Status.FAILURE

# class PathPlanner():
#     def __init__(self, agent):
#         self.agent = agent
#         self.target_position = None

#     def set_target_position(self, target_position):
#         self.target_position = target_position

#     def generate(self, option='xy'):
#         """
#         Generates waypoints following the Manhattan grid, adding waypoints only at turns.
#         The `option` parameter controls the order of movement:
#         - 'xy' (default): Move in x-direction first, then y-direction.
#         - 'yx': Move in y-direction first, then x-direction.
#         """
#         waypoints = []
#         agent_position = self.agent.position

#         # Current agent coordinates
#         current_x, current_y = agent_position
#         # Target coordinates
#         target_x, target_y = self.target_position

#         if option == 'xy':
#             # Move in x-direction first, then y-direction
#             if current_x != target_x:
#                 waypoints.append((target_x, current_y))
#             if current_y != target_y:
#                 waypoints.append((target_x, target_y))
#         elif option == 'yx':
#             # Move in y-direction first, then x-direction
#             if current_y != target_y:
#                 waypoints.append((current_x, target_y))
#             if current_x != target_x:
#                 waypoints.append((target_x, target_y))

#         return waypoints
    




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

        self.agent.update_battery()
        self.agent.follow(next_waypoint)  # Command the agent to follow the current waypoint

        return Status.FAILURE  # Keep RUNNING if not all waypoints have been visited







class PickItem(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._action)

    def _action(self, agent, blackboard):
        # 선택된 Ship 가져오기
        chosen_ship = blackboard.get('chosen_ship', None)
        if chosen_ship is None:
            print(f"Agent {agent.agent_id}: No ship selected!")
            return Status.FAILURE

        # 선택된 Ship에서 할당되지 않은 작업 가져오기
        unassigned_tasks = [
            task for task in agent.get_unassigned_tasks() if task.ship_id == chosen_ship
        ]
        if len(unassigned_tasks) == 0:  # 선택된 Ship에 할당 가능한 작업이 없을 때
            return Status.FAILURE
        
        assigned_task = unassigned_tasks[-1]
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
        blackboard['ship_selected'] = False

        agent.task_color = None
        agent.update_image()

        return Status.SUCCESS

class ChargeBattery(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._charge)
        self.charge_rate = 1  # 충전 속도 (% per step)

    def _charge(self, agent, blackboard):
        # 충전 상태 확인
        if blackboard.get('status') != "AtChargingStation":
            blackboard['is_charging'] = False  # 충전 상태 해제
            return Status.FAILURE

        # 충전 진행
        if agent.battery < 100:
            blackboard['is_charging'] = True
            agent.battery += self.charge_rate
            agent.battery = min(agent.battery, 100)  # 배터리 100% 제한
            print(f"Agent {agent.agent_id}: Charging... Battery at {agent.battery}%.")
            return Status.RUNNING

        # 충전 완료 처리 (100%)
        if agent.battery == 100:
            print(f"Agent {agent.agent_id}: Fully charged (100%). Returning to task.")
            blackboard['is_charging'] = False  # 충전 상태 해제
            blackboard['charging_station_waypoints'] = None  # 충전 경로 초기화
            blackboard['is_going_to_charging_station'] = False
            blackboard['status'] = None  # 충전소 상태 초기화
            return Status.SUCCESS
