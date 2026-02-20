import math
import random
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, ReactiveSequence, ReactiveFallback, SyncAction, SyncCondition, GatherLocalInfo, AssignTask, Parallel
from modules.base_bt_nodes import _IsTaskCompleted, _IsArrivedAtTask, _MoveToTask, _ExecuteTaskWhileFollowing, _ExploreArea
import importlib
import time
import pygame
import numpy as np
from enum import Enum

# BT Node List
CUSTOM_ACTION_NODES = [
    'MoveToTarget',
    'ExecuteTask',
    'Explore',
    'TeachBT',
    'AssignCenTask',
    'Halt',
    'Hungarian',
    'SGA',
    'CenGRAPE',
    'HungarianModeA',
    'HungarianModeB'
]

CUSTOM_CONDITION_NODES = [
    'IsTaskCompleted',
    'IsArrivedAtTarget',
    'IsTaskAssigned',
    'IsConnectedWithLeader'
]

CUSTOM_DECORATOR_NODES = [
    'CentralisationWrapper'
]

# BT Node List
BTNodeList.ACTION_NODES.extend(CUSTOM_ACTION_NODES)
BTNodeList.CONDITION_NODES.extend(CUSTOM_CONDITION_NODES)
BTNodeList.DECORATOR_NODES.extend(CUSTOM_DECORATOR_NODES)

# Scenario-specific Action/Condition Nodes
from modules.utils import config
target_arrive_threshold = config['tasks']['threshold_done_by_arrival']
task_locations = config['tasks']['locations']
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
agent_max_random_movement_duration = config.get('agents', {}).get('random_exploration_duration', None)
decision_making_module_path = config['decision_making']['plugin']
module_path, class_name = decision_making_module_path.rsplit('.', 1)
decision_making_module = importlib.import_module(module_path)
decision_making_class = getattr(decision_making_module, class_name)
leader_communication_radius = config['agents']['types']['Leader'].get('communication_radius', 0)  # 0 means "global" / for IsConnectedWithLeader
communication_time_endurance = config.get('agents', {}).get('communication_time_endurance', 1.0)  # in seconds
# ====================================================================================
# Assignment CenMRTA Algorithm
# ====================================================================================
if config['decision_making'].get('CBBA'):
    from scenarios.features.cenwrapper.sga import SGA
elif config['decision_making'].get('GRAPE'):
    from scenarios.features.cenwrapper.cen_grape import CenGRAPE
elif config['decision_making'].get('Hungarian'):
    from scenarios.features.cenwrapper.hungarian import Hungarian

# ===========================================================================
# ---------------------------- Condition Nodes ------------------------------
# ===========================================================================

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


class IsTaskAssigned(SyncCondition):
    """
    - agent에게 task가 할당되었는지 여부 판단
    """
    def __init__(self, name, agent):
        super().__init__(name, self._is_assigned)
    
    def _is_assigned(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id', None)
        if assigned_task_id is not None:
            return Status.SUCCESS
        else:
            return Status.FAILURE


# class IsConnectedWithLeader(SyncCondition):
#     """
#     - Leader agent와 통신이 가능한지 여부 판단
#     """
#     def __init__(self, name, agent):
#         super().__init__(name, self._is_connected)
#         self.connection_lost_time = None
    
#     def _is_connected(self, agent, blackboard):
#         current_time = time.time()
#         agents = agent.get_agents_nearby()
        
#         # 통신 기반 방식
#         # communication_success = False
#         # for msg in agent.messages_received:
#         #     task_allocations = msg.get('task_allocations', {})
#         #     if task_allocations:
#         #         communication_success = True
#         #         break
        
#         # leader agent 유무 판별
#         communication_success = any(a.type == 'Leader' for a in agents)
        
#         if communication_success:
#             self.connection_lost_time = None
#             return Status.SUCCESS
#         else:
#             if self.connection_lost_time is None:
#                 self.connection_lost_time = current_time

#             elapsed_time = current_time - self.connection_lost_time
#             if elapsed_time >= communication_time_endurance:
#                 return Status.FAILURE
#             else:
#                 return Status.RUNNING
class IsConnectedWithLeader(SyncCondition):
    """
    - Leader agent와 통신이 가능한지 여부 판단 (거리 기반)
    """
    def __init__(self, name, agent):
        super().__init__(name, self._is_connected)
        self.leader_agent = agent.agents_info[-1]
    
    def _is_connected(self, agent, blackboard):
        if self.leader_agent is not None and self.leader_agent.type == 'Leader':
            distance = agent.position.distance_to(self.leader_agent.position)
        else:
            agents_info = getattr(agent, 'agents_info', {})
            self.leader_agent = None  # Initialize as None first
            for agent_info in agents_info:
                if agent_info.type == 'Leader':
                    self.leader_agent = agent_info
                    distance = agent.position.distance_to(self.leader_agent.position)
                    break
        
        if self.leader_agent is None:
            return Status.FAILURE
        
        if distance < leader_communication_radius:
            return Status.SUCCESS
        else:
            return Status.FAILURE


# ===========================================================================
# ---------------------------- Action Nodes ---------------------------------
# =========================================================================== 


class MoveToTarget(_MoveToTask): 
    def __init__(self, name, agent):
        super().__init__(name, agent)   

    def _update(self, agent, blackboard): 
        result = super()._update(agent, blackboard, task_id_key='assigned_task_id')
        return result
        
        
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
        result = super()._update(agent, blackboard, agent_max_random_movement_duration=agent_max_random_movement_duration, exploration_area=task_locations, sampling_time=sampling_time)
        return result


class TeachBT(SyncAction):
    """
    - central unit의 MRTA 할당 결과를 follower agent에게 전달
    """
    def __init__(self, name, agent):
        super().__init__(name, self._teach)

    def _teach(self, agent, blackboard):
        task_allocations = blackboard.get('task_allocations', {})
        
        agent.message_to_share['task_allocations'] = task_allocations
        agent.broadcast_message(to_all = False)
        
        return Status.SUCCESS


class AssignCenTask(SyncAction):
    """
    - follower agent가 central unit의 MRTA 할당 결과를 수신 및 자신의 task로 할당
    """
    def __init__(self, name, agent):
        super().__init__(name, self._assign)
        
    def _assign(self, agent, blackboard):
        latest_task_allocations = {}
        latest_timestamp = 0
        
        for msg in agent.messages_received:
            _task_allocatinos = msg.get('task_allocations', {})
            if _task_allocatinos and isinstance(_task_allocatinos, dict):
                msg_timestamp = _task_allocatinos.get('timestamp', 0)
                if msg_timestamp > latest_timestamp:
                    latest_timestamp = msg_timestamp
                    latest_task_allocations = _task_allocatinos
  
        blackboard['assigned_task_id'] = latest_task_allocations.get(agent.agent_id, None)
        agent.assigned_task_id = blackboard['assigned_task_id'] 

        # if blackboard['assigned_task_id'] is None:
        #     return Status.FAILURE
        # else:
        return Status.SUCCESS


class Halt(SyncAction):
    """
    - agent의 모든 움직임을 멈춤
    """
    def __init__(self, name, agent):
        super().__init__(name, self._halt)
    
    def _halt(self, agent, blackboard):
        agent.reset_movement()
        return Status.RUNNING


# ===========================================================================
# ---------------------------- Decorator Nodes ------------------------------
# ===========================================================================


class CentralisationWrapper(Node):
    """
    - MRTA 할당의 중앙화 wrapper
    - Leader agent가 전체 agent를 순회하며 각각의 입장에서 MRTA를 시뮬레이션
    """
    def __init__(self, name, child):
        super().__init__(name)
        self.type = "CentralisationWrapper"
        self.children = [child]
        self.previous_allocations = {}
        
    async def run(self, agent, blackboard):
        agents = getattr(agent, 'agents_nearby', [])

        current_tick_allocations = {}
        _blackboard = {}
        _blackboard['local_tasks_info'] = agent.blackboard.get('local_tasks_info', {}) # 리더의 local_tasks_info를 사용
        _blackboard['local_agents_info'] = agent.blackboard.get('local_agents_info', {}) # 리더의 local_agents_info를 사용
        _blackboard['messages_received'] = agent.blackboard.get('messages_received', []) # 리더의 messages_received를 사용
        
        for target_agent in agents:
            if target_agent.type == 'Leader':
                continue
            
            # _blackboard['messages_received'] = target_agent.blackboard.get('messages_received', [])
            child_status = await self.children[0].run(target_agent, _blackboard)

            assigned_task_id = _blackboard.get('assigned_task_id', None)
            if assigned_task_id is not None:
                current_tick_allocations[target_agent.agent_id] = assigned_task_id
            else:
                current_tick_allocations[target_agent.agent_id] = None
                
                
        agent.reset_messages_received()
        consensus_reached = self._is_consensus_reached(current_tick_allocations)
        
        if consensus_reached:
            blackboard['task_allocations'] = {k: v for k, v in current_tick_allocations.items()}
            blackboard['task_allocations']['timestamp'] = time.time()
            blackboard['consensus_reached'] = True
            
            return Status.SUCCESS
        
        else:
            self.previous_allocations = current_tick_allocations.copy()
            
            blackboard['consensus_reached'] = False
            
            return Status.RUNNING
    
    def _is_consensus_reached(self, current_allocations):
        """
        현재 할당 결과와 이전 할당 결과를 비교하여 consensus 도달 여부 판단
        """
        if not self.previous_allocations:
            return False  
        
        for agent_id in current_allocations:
            if agent_id not in self.previous_allocations:
                return False
            if current_allocations[agent_id] != self.previous_allocations[agent_id]:
                return False
            
        return True