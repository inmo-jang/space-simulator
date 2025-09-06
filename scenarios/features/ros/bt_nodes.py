import math
import random
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, ReactiveSequence, ReactiveFallback, SyncAction, GatherLocalInfo, AssignTask
from modules.base_bt_nodes import _IsTaskCompleted, _IsArrivedAtTask, _MoveToTask, _ExecuteTaskWhileFollowing, _ExploreArea
# BT Node List
CUSTOM_ACTION_NODES = [
    'MoveToTarget',
    'ExecuteTask',
    'Explore'
]

CUSTOM_CONDITION_NODES = [
    'IsNearbyTarget',
]

# BT Node List
BTNodeList.ACTION_NODES.extend(CUSTOM_ACTION_NODES)
BTNodeList.CONDITION_NODES.extend(CUSTOM_CONDITION_NODES)


from turtlesim.msg import Pose as TPose
from std_srvs.srv import SetBool
from scenarios.features.ros.base_bt_nodes_ros import ROSConditionBTNode, ROSServiceBTNode


class IsNearbyTarget(ROSConditionBTNode):
    def __init__(self, name, agent, default_thresh=0.5):
        ns = agent.ros_namespace or ""  # 네임스페이스 없으면 루트
        super().__init__(name, agent, [
            (TPose, f"{ns}/pose", 'self'),
            (TPose, "/turtle_target/pose", 'target'),
        ])
        self.default_thresh = default_thresh


    def _predicate(self, agent, blackboard):
        cache = self._cache  # 베이스 설계대로 내부 캐시 사용
        if "self" not in cache or "target" not in cache:
            return False

        a = cache["self"]
        b = cache["target"]

        thresh = blackboard.get("nearby_threshold", self.default_thresh)
        dist = math.hypot(a.x - b.x, a.y - b.y)
        blackboard["distance_to_target"] = dist
        return dist <= float(thresh)


