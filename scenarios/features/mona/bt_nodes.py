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
        self._arrived_latched = False   # ← 도착 엣지 검출용

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id',
                                 arrive_threshold=target_arrive_threshold)

        task_id = blackboard.get('assigned_task_id', None)

        if result is Status.SUCCESS:
            # (1) task가 없을 땐 아무것도 안 함: 스팸 방지
            if task_id is None:
                self._arrived_latched = True   # 상태만 유지
                return result

            # (2) 도착 "전이" 프레임에만 1회 실행
            if not self._arrived_latched:
                if hasattr(agent, "controller"):
                    agent.controller.clear_target()

                mona = getattr(agent, "_mona", None)
                if bool(getattr(agent, "is_real_robot", False) and mona and mona.is_connected):
                    try:
                        mona.cancel_all(send_stop=True)   # ← 여기서만 STOP 1회
                    except Exception:
                        pass
                self._arrived_latched = True
        else:
            # 실패가 되면 래치 해제 → 다음 번 성공 때만 다시 1회 실행
            self._arrived_latched = False

        return result

class MoveToTarget(_MoveToTask):
    """
    경로/할당이 실시간으로 바뀔 때 즉시 선점하여 불필요한 이동을 차단.
    - task_id 또는 목표 좌표가 임계 이상 바뀌면: cancel_all + set_target(curr)
    - ACK 게이팅 기반으로 한 번에 하나의 G만 전송
    """
    def __init__(self, name, agent):
        super().__init__(name, agent)
        self._last_task_id = None
        self._last_target  = None  # (x, y)

    def _update(self, agent, blackboard):
        base_status = super()._update(agent, blackboard, task_id_key='assigned_task_id')

        mona = getattr(agent, "_mona", None)
        mona_connected = bool(agent.is_real_robot and mona and mona.is_connected)
        if not mona_connected:
            return base_status

        # 도착이면 성공
        if base_status is Status.SUCCESS:
            return Status.SUCCESS

        # 최신 타깃
        curr_task_id = blackboard.get('assigned_task_id')
        curr_target  = agent.controller.target if agent.controller.has_target() else None
        curr_target  = (float(curr_target[0]), float(curr_target[1])) if curr_target else None

        # 경로 흔들림 민감도(px) — 필요시 30~60 사이로 조정
        REPLAN_DIST_THRESH = 10.0

        need_preempt = False
        if self._last_task_id is not None and curr_task_id is not None and curr_task_id != self._last_task_id:
            need_preempt = True
        if self._last_target is not None and curr_target is not None:
            dx = curr_target[0] - self._last_target[0]
            dy = curr_target[1] - self._last_target[1]
            if (dx*dx + dy*dy) ** 0.5 > REPLAN_DIST_THRESH:
                need_preempt = True

        if need_preempt:
            # 1) 모나 즉시 정지/큐 비움
            try:
                mona.cancel_all(send_stop=True)
            except Exception:
                pass
            # 2) 컨트롤러 타깃 확정(최신으로 덮기)
            if curr_target:
                agent.controller.set_target(curr_target)

        # 최신 값 갱신
        self._last_task_id = curr_task_id
        self._last_target  = curr_target

        # ACK 게이팅 기반 전송
        if self._last_target:
            mona.send_g_to(
                (float(agent.position.x), float(agent.position.y)),
                float(agent.rotation),
                self._last_target,
            )
            mona.try_flush_queue()

        return Status.RUNNING


class ExecuteTask(_ExecuteTaskWhileFollowing):
    """
    Work 중에는 절대 움직이지 않도록 첫 RUNNING 프레임에 완전 정지.
    Work 종료 시에는 플래그만 리셋(다음 타깃 설정은 상위 로직/할당자에 맡김).
    """
    def __init__(self, name, agent):
        super().__init__(name, agent)
        self._in_work = False

    def _update(self, agent, blackboard):
        status = super()._update(agent, blackboard, task_id_key='assigned_task_id')

        if status is Status.RUNNING and not self._in_work:
            # Work 시작 프레임: 완전 정지 보장
            self._in_work = True
            if hasattr(agent, "controller"):
                agent.controller.clear_target()
            mona = getattr(agent, "_mona", None)
            if bool(agent.is_real_robot and mona and mona.is_connected):
                try:
                    mona.cancel_all(send_stop=True)
                except Exception:
                    pass

        if status is not Status.RUNNING:
            # 종료/중단 시 플래그 리셋
            self._in_work = False

        return status
                

class Explore(_ExploreArea): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        return super()._update(agent, blackboard,
                               agent_max_random_movement_duration=config.get('agents', {}).get('random_exploration_duration', None),
                               exploration_area=task_locations, 
                               sampling_time=sampling_time)
