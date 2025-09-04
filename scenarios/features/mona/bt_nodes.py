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
ARRIVE_MM      = float(mona_cfg.get('arrive_threshold_mm', 30.0)) # 도착 거리(mm)
ARRIVE_DEG     = float(mona_cfg.get('arrive_heading_deg', 8.0))   # 도착 헤딩(도)
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
        # 1) 기반 동작(타깃 세팅/도착 판정)은 그대로 사용
        base_status = super()._update(agent, blackboard, task_id_key='assigned_task_id')

        mona_connected = bool(agent.is_real_robot and agent._mona and agent._mona.is_connected)
        if not mona_connected:
            # 시뮬만 돌리는 경우엔 기존 동작 그대로
            return base_status

        # 2) MONA 연결: 도착이면 성공 리턴
        if base_status is Status.SUCCESS:
            return Status.SUCCESS

        # 3) 주기적으로 G 전송 (controller.target 기준 폐루프 보정)
        #interval = getattr(agent, '_g_interval', G_INTERVAL_SEC)
        interval = G_INTERVAL_SEC
        if agent.controller.has_target():
            # 추가: 현재 목표 대비 오차 계산
            #deg, mm = agent._compute_g_command(agent.controller.target)
            t = agent.controller.target
            deg, mm = agent._mona.compute_g(
                (agent.position.x, agent.position.y),
                float(agent.rotation),
                (float(t[0]), float(t[1])),
            )

            # 추가: 도착 임계치 이내면 '전송하지 않음' (=멈춤)
            # 180도면 각도는 무시되는 셈이니 mm만 체크해도 충분
            if mm < ARRIVE_MM:
                return Status.RUNNING

            now = time.monotonic()
            if (now - self._last_g_ts) >= interval:
                #agent._send_mona_g(agent.controller.target)
                agent._mona.send_g_to(
                    (agent.position.x, agent.position.y),
                    float(agent.rotation),
                    (float(t[0]), float(t[1])),
                )
                self._last_g_ts = now

        return Status.RUNNING

class ExecuteTask(_ExecuteTaskWhileFollowing): 
    def __init__(self, name, agent):
        super().__init__(name, agent)  
        self._last_g_ts = 0.0 

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id')
        
        mona_connected = bool(agent.is_real_robot and agent._mona and agent._mona.is_connected)
        if mona_connected and agent.controller.has_target():
            # 추가: 도착 임계치 이내면 전송하지 않음
            #deg, mm = agent._compute_g_command(agent.controller.target)
            # 도착 임계치 이내면 전송하지 않음 (MonaClient 사용)
            t = agent.controller.target
            deg, mm = agent._mona.compute_g(
                (agent.position.x, agent.position.y),
                float(agent.rotation),
                (float(t[0]), float(t[1])),
            )
            if mm < ARRIVE_MM:
                return result

            #interval = getattr(agent, '_g_interval', G_INTERVAL_SEC)
            interval = G_INTERVAL_SEC
            now = time.monotonic()
            if (now - self._last_g_ts) >= interval:
                #agent._send_mona_g(agent.controller.target)
                agent._mona.send_g_to(
                    (agent.position.x, agent.position.y),
                    float(agent.rotation),
                    (float(t[0]), float(t[1])),
                )
                self._last_g_ts = now

        return result
                

class Explore(_ExploreArea): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        return super()._update(agent, blackboard,
                               agent_max_random_movement_duration=config.get('agents', {}).get('random_exploration_duration', None),
                               exploration_area=task_locations, 
                               sampling_time=sampling_time)
