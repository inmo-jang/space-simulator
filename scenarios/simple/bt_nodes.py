import math
import random

# 기본 BT 노드 구성
from modules.base_bt_nodes import (
    BTNodeList, Status, Node, Sequence, Fallback,
    ReactiveSequence, ReactiveFallback, SyncAction,
    GatherLocalInfo, AssignTask,
    _IsTaskCompleted, _IsArrivedAtTask, _MoveToTask,
    _ExecuteTaskWhileFollowing, _ExploreArea
)

# ESP32 보드로 socket 메시지를 보내기 위한 함수 import
from modules.socket_com import send_to_board

# 사용자 정의 노드 리스트 확장
CUSTOM_ACTION_NODES = [
    'MoveToTarget',
    'ExecuteTask',
    'Explore'
]

CUSTOM_CONDITION_NODES = [
    'IsTaskCompleted',
    'IsArrivedAtTarget',
]

# BT Node 등록
BTNodeList.ACTION_NODES.extend(CUSTOM_ACTION_NODES)
BTNodeList.CONDITION_NODES.extend(CUSTOM_CONDITION_NODES)

# 시나리오 관련 설정 로딩
from modules.utils import config
target_arrive_threshold = config['tasks']['threshold_done_by_arrival']
task_locations = config['tasks']['locations']
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
agent_max_random_movement_duration = config.get('agents', {}).get('random_exploration_duration', None)


# [조건 노드] Task 완료 여부 확인
class IsTaskCompleted(_IsTaskCompleted): 
    def __init__(self, name, agent):
        super().__init__(name, agent)

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id')
        if result is Status.SUCCESS:
            blackboard['assigned_task_id'] = None
        return result


# [조건 노드] 목표 지점(Task 위치)에 도달했는지 확인
class IsArrivedAtTarget(_IsArrivedAtTask): 
    def __init__(self, name, agent):
        super().__init__(name, agent)

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id', arrive_threshold=target_arrive_threshold)
        return result


# [행동 노드] 목표 Task로 이동
class MoveToTarget(_MoveToTask): 
    def __init__(self, name, agent):
        super().__init__(name, agent)

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id')

        # [ESP32로 명령 전송하는 제어부]
        # agent가 Task를 향해 이동 중일 때, ESP32 보드로 "MOVE x y" 명령 전송
        if result == Status.RUNNING and blackboard.get('assigned_task_id') is not None:
            task_id = blackboard['assigned_task_id']
            task_pos = agent.tasks_info[task_id].position  # 목표 task의 위치 (x, y)
            msg = f"MOVE {int(task_pos[0])} {int(task_pos[1])}"
            send_to_board(agent.agent_id + 1, msg)  # ESP32 ID는 agent_id + 1로 매핑
        return result


# [행동 노드] Task를 수행 (작업량 감소)
class ExecuteTask(_ExecuteTaskWhileFollowing): 
    def __init__(self, name, agent):
        super().__init__(name, agent)

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id')
        return result


# [행동 노드] 미할당 상태에서 탐색 행동 (랜덤 이동)
class Explore(_ExploreArea): 
    def __init__(self, name, agent):
        super().__init__(name, agent)

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard,
                                 agent_max_random_movement_duration=agent_max_random_movement_duration,
                                 exploration_area=task_locations,
                                 sampling_time=sampling_time)
        return result
