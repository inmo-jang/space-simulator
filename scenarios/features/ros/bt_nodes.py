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
from scenarios.features.ros.base_bt_nodes_ros import ROSConditionBTNode, ROSActionBTNode


class IsNearbyTarget(ROSConditionBTNode):
    def __init__(self, name, agent, default_thresh=0.1):
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
        blackboard["target"] = b  # <- target pose 캐시를 블랙보드에 기록
        return dist <= float(thresh)

# bt_nodes.py (발췌)
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose

class MoveToTarget(ROSActionBTNode):
    def __init__(self, name, agent):
        ns = agent.ros_namespace or ""  # 네임스페이스 없으면 루트
        super().__init__(name, agent, 
            (NavigateToPose, f"{ns}/navigate_to_pose")
        )
        # RUNNING일 때 목표를 흘려 보낼 퍼블리셔
        goal_topic = f"{ns}/goal_pose" if ns else "/goal_pose"
        self.goal_pub = self.ros.node.create_publisher(PoseStamped, goal_topic, 10)


    # --- helpers ---
    def _get_xy(self, bb):
        tgt = bb.get('target')
        if isinstance(tgt, TPose):
            return tgt.x, tgt.y
        return None


    def _build_goal(self, agent, bb):
        xy = self._get_xy(bb)
        if xy is None:
            return None
        x, y = xy

        ps = PoseStamped()
        ps.header.frame_id = 'map'
        ps.header.stamp = self.ros.node.get_clock().now().to_msg()
        ps.pose.position.x = x
        ps.pose.position.y = y
        ps.pose.orientation.w = 1.0  # yaw = 0

        goal = NavigateToPose.Goal()
        goal.pose = ps
        return goal

    # ★ RUNNING일 때만 최신 목표를 퍼블리시
    def _on_running(self, agent, bb):
        xy = self._get_xy(bb)
        if xy is None: return
        x, y = xy
        ps = PoseStamped()
        ps.header.frame_id = 'map'
        ps.header.stamp = self.ros.node.get_clock().now().to_msg()
        ps.pose.position.x = x; ps.pose.position.y = y
        ps.pose.orientation.w = 1.0
        self.goal_pub.publish(ps)

    def _interpret_result(self, result, agent, bb, status_code=None):
        # status_code는 action_msgs/GoalStatus의 상수와 매칭됨
        if status_code == GoalStatus.STATUS_SUCCEEDED:
            bb['nav_result'] = 'succeeded'
            return Status.SUCCESS
        elif status_code == GoalStatus.STATUS_CANCELED:
            bb['nav_result'] = 'canceled'
            return Status.FAILURE
        else:
            # STATUS_ABORTED 등 기타 코드
            bb['nav_result'] = 'aborted'
            return Status.FAILURE
