import math
import pygame
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, ReactiveSequence, ReactiveFallback, SyncAction, SyncCondition

# BT Node List  (same names as py_bt_ros version)
CUSTOM_ACTION_NODES = [
    'MoveTo',
    'KillTarget',
]

CUSTOM_CONDITION_NODES = [
    'IsNearby',
    'IsTargetClear',
]

BTNodeList.ACTION_NODES.extend(CUSTOM_ACTION_NODES)
BTNodeList.CONDITION_NODES.extend(CUSTOM_CONDITION_NODES)


class IsNearby(SyncCondition):
    """
    Check if the catcher agent is within threshold distance of the target.

    Parameters
    ----------
    target_pose_topic : str
        Accepted for interface compatibility with py_bt_ros; ignored in sim.
    threshold : float
        Distance threshold in pixels.
    """
    def __init__(self, name, agent, target_pose_topic=None, threshold=30):
        super().__init__(name, self._update)
        self.threshold = float(threshold)

    def _update(self, agent, blackboard):
        target = agent.target
        if target is None or target.completed:
            return Status.FAILURE
        # Store target position in blackboard so MoveTo can read it.
        # pygame.Vector2 has .x and .y → compatible with is_nearby() and py_bt_ros.
        blackboard["target"] = target.position
        dist = math.hypot(agent.position.x - target.position.x, agent.position.y - target.position.y)
        return Status.SUCCESS if dist < self.threshold else Status.FAILURE


class MoveTo(SyncAction):
    """
    Move the catcher agent toward blackboard["target"].

    Parameters
    ----------
    action : str
        Accepted for interface compatibility with py_bt_ros; ignored in sim.
    goal_pose_topic : str
        Accepted for interface compatibility with py_bt_ros; ignored in sim.
    """
    def __init__(self, name, agent, action=None, goal_pose_topic=None):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        target_pos = blackboard.get("target")
        if target_pos is None:
            return Status.FAILURE
        agent.follow(pygame.Vector2(target_pos.x, target_pos.y))
        return Status.RUNNING


class KillTarget(SyncAction):
    """Mark the target as caught (completed)."""
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        target = agent.target
        if target is not None:
            target.completed = True
            blackboard["target"] = None
        return Status.SUCCESS


class IsTargetClear(SyncCondition):
    """Return SUCCESS if the target has already been caught."""
    def __init__(self, name, agent):
        super().__init__(name, self._update)

    def _update(self, agent, blackboard):
        target = agent.target
        if target is None or target.completed:
            blackboard["target"] = None
            return Status.SUCCESS
        return Status.FAILURE
