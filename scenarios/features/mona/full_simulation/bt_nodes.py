import random
import pygame
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, ReactiveSequence, ReactiveFallback, SyncAction, SyncCondition, GatherLocalInfo, AssignTask

# BT Node List
CUSTOM_ACTION_NODES = [
    'MoveToTarget',
    'ExecuteTask',
    'Explore',
    'Idle',
]

CUSTOM_CONDITION_NODES = [
    'IsTaskCompleted',
    'IsArrivedAtTarget',
]

BTNodeList.ACTION_NODES.extend(CUSTOM_ACTION_NODES)
BTNodeList.CONDITION_NODES.extend(CUSTOM_CONDITION_NODES)


# Scenario-specific config
from modules.utils import config
target_arrive_threshold = config['tasks']['threshold_done_by_arrival']
task_locations = config['tasks']['locations']
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq
agent_max_random_movement_duration = config.get('agents', {}).get('random_exploration_duration', None)
use_rotation_shim = config.get('agents', {}).get('use_rotation_shim', False)

def _move(agent, target):
    if use_rotation_shim:
        agent.follow_rotation_shim(target)
    else:
        agent.follow(target)


class IsTaskCompleted(SyncCondition):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            return Status.RUNNING

        task = agent.tasks_info[assigned_task_id]
        if task.completed is True:
            blackboard['assigned_task_id'] = None
            return Status.SUCCESS
        return Status.FAILURE


class IsArrivedAtTarget(SyncCondition):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned_task_id found in the blackboard!")

        distance = (agent.tasks_info[assigned_task_id].position - agent.position).length()
        if distance < agent.tasks_info[assigned_task_id].radius + target_arrive_threshold:
            return Status.SUCCESS
        return Status.FAILURE


class MoveToTarget(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned_task_id found in the blackboard!")

        _move(agent, agent.tasks_info[assigned_task_id].position)
        return Status.RUNNING


class ExecuteTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        assigned_task_id = blackboard.get('assigned_task_id')
        if assigned_task_id is None:
            raise ValueError(f"[{self.name}] Error: No assigned_task_id found in the blackboard!")

        agent.tasks_info[assigned_task_id].reduce_amount(agent.work_rate)
        agent.update_task_amount_done(agent.work_rate)
        _move(agent, agent.tasks_info[assigned_task_id].position)
        return Status.RUNNING


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
        _move(agent, self.random_waypoint)
        return Status.RUNNING

    def halt(self):
        self.random_move_time = float('inf')

class Idle(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        agent.velocity = pygame.Vector2(0, 0)
        agent.acceleration = pygame.Vector2(0, 0)
        # ★ rotation update 블록을 건너뛰게 함 (atan2(0,0)=0 회전 방지)
        agent._use_rotation_shim = True
        return Status.RUNNING