import math
import random
import time     #추가
import pygame   #추가
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, ReactiveSequence, ReactiveFallback, SyncAction, GatherLocalInfo, AssignTask
from modules.base_bt_nodes import _IsTaskCompleted, _IsArrivedAtTask, _MoveToTask, _ExecuteTaskWhileFollowing, _ExploreArea
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
mona_cfg = (config.get('mona') or {})
G_INTERVAL_SEC = float(mona_cfg.get('g_interval_sec', 0.10))      # G 전송 주기(초)
target_arrive_threshold = config['tasks']['threshold_done_by_arrival']
task_locations = config['tasks']['locations']
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
agent_max_random_movement_duration = config.get('agents', {}).get('random_exploration_duration', None)


class IsTaskCompleted(_IsTaskCompleted): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id')
        if result is Status.SUCCESS:
            blackboard['assigned_task_id'] = None
        return result


class IsArrivedAtTarget(_IsArrivedAtTask): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id', arrive_threshold=target_arrive_threshold)
        if result is Status.SUCCESS:
            pass
        return result
    
    
class MoveToTarget(_MoveToTask): 
    def __init__(self, name, agent):
        super().__init__(name, agent)
        self._last_g_ts = 0.0

    def _update(self, agent, blackboard):
        mona_connected = bool(
            getattr(agent, "is_real_robot", False)
            and getattr(agent, "_mona", None)
            and agent._mona.is_connected
        )

        # 1) SIM(미연결) → 기존 기반 동작(follow)만 수행하고 바로 반환
        if not mona_connected:
            return super()._update(agent, blackboard, task_id_key='assigned_task_id')

        # 2) MONA(연결) → 시뮬 물리 이동은 건너뛰고, 목표 갱신 + 주기적 G 전송
        task_id = blackboard.get('assigned_task_id')
        if task_id is not None and (0 <= int(task_id) < len(agent.tasks_info)):
            task = agent.tasks_info[int(task_id)]
            pos = task.position  # pygame.Vector2 또는 (x, y)

            # 컨트롤러 타깃을 매 틱 동기화 (실기/시뮬 모두 동일 기준 사용)
            if hasattr(pos, "x"):
                tx, ty = float(pos.x), float(pos.y)
            else:
                tx, ty = float(pos[0]), float(pos[1])
            agent.controller.set_target((tx, ty))

            # 주기적으로 G 전송
            interval = G_INTERVAL_SEC
            now = time.monotonic()
            if (now - self._last_g_ts) >= interval:
                agent._mona.send_g_to(
                    (agent.position.x, agent.position.y),
                    float(agent.rotation),
                    (tx, ty),
                )
                self._last_g_ts = now

        return Status.RUNNING



class ExecuteTask(_ExecuteTaskWhileFollowing): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id')
        return result
                

class Explore(_ExploreArea): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        return super()._update(agent, blackboard,
                               agent_max_random_movement_duration=config.get('agents', {}).get('random_exploration_duration', None),
                               exploration_area=task_locations, 
                               sampling_time=sampling_time)
