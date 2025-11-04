#!/usr/bin/env python3
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, GoalResponse, CancelResponse

from geometry_msgs.msg import Twist, PoseStamped
from turtlesim.msg import Pose as TPose
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import Empty


def angle_norm(a: float) -> float:
    """wrap angle to [-pi, pi]"""
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


class TurtleNavigateServer(Node):
    """
    Action Server: {ns}/navigate_to_pose  (ex: /turtle1/navigate_to_pose)
      - Subscribe: {ns}/pose   (turtlesim/Pose)
      - Publish:   {ns}/cmd_vel (geometry_msgs/Twist)
    """

    def __init__(self, ns: str = "/turtle1"):
        super().__init__("turtle_navigate_server")

        # topics & action names
        self.ns = ns.rstrip("/")
        self.pose_topic = f"{self.ns}/pose"
        self.cmd_topic = f"{self.ns}/cmd_vel"
        self.action_name = f"{self.ns}/navigate_to_pose"

        # I/O
        self.sub_pose = self.create_subscription(
            TPose, self.pose_topic, self._on_pose, 10)
        self.sub_goal = self.create_subscription(
            PoseStamped, f"{self.ns}/goal_pose", self._on_goal_pose, 10
        )
        self.pub_cmd = self.create_publisher(Twist, self.cmd_topic, 10)
        self.server = ActionServer(
            self,
            NavigateToPose,
            self.action_name,
            execute_callback=self.execute_cb,
            goal_callback=self.goal_cb,
            cancel_callback=self.cancel_cb,
        )

        # state
        self.current_pose: TPose | None = None
        self._goal_xy = None  # 최신 목표 (x,y)        
        self.get_logger().info(f"Action server ready: {self.action_name}")
        self.get_logger().info(f"Subscribing {self.pose_topic} | Publishing {self.cmd_topic}")

        # simple controller params
        self.pos_tol = 0.015       # 도착 판정(m)
        self.yaw_tol = 0.012       # 회전 허용 오차(rad)
        self.k_ang = 4.0          # 각속도 게인
        self.k_lin = 1.2          # 선속도 게인
        self.max_lin = 2.0
        self.max_ang = 4.0
        self.dt = 1.0 / 30.0      # 제어 주기(초)

    # --- Callbacks ---

    def _on_pose(self, msg: TPose):
        self.current_pose = msg

    def _on_goal_pose(self, msg: PoseStamped):
        self._goal_xy = (float(msg.pose.position.x), float(msg.pose.position.y))        

    def goal_cb(self, goal_request: NavigateToPose.Goal):
        # 간단히 항상 수락
        return GoalResponse.ACCEPT

    def cancel_cb(self, goal_handle):
        # 취소 요청 수락
        return CancelResponse.ACCEPT

    # --- Core execution ---

    async def execute_cb(self, goal_handle):
        goal: NavigateToPose.Goal = goal_handle.request

        # 목표 추출
        x_t = float(goal.pose.pose.position.x)
        y_t = float(goal.pose.pose.position.y)
        # 목표 yaw (헤딩은 크게 중요치 않으니 0으로 두되, 필요하면 쿼터니언에서 추출 가능)
        # 여기서는 위치만 맞추면 성공으로 정의

        # 시작 시간
        start = self.get_clock().now()

        # 제어 루프
        feedback = NavigateToPose.Feedback()
        result = NavigateToPose.Result()
        # (Humble의 result 필드는 std_msgs/Empty)
        # https://docs.ros.org/en/humble/p/nav2_msgs/action/NavigateToPose.html

        self.get_logger().info(f"New goal -> ({x_t:.2f}, {y_t:.2f})")

        while rclpy.ok():
            # 취소 처리
            if goal_handle.is_cancel_requested:
                self._publish_stop()
                goal_handle.canceled()
                result.result = Empty()
                self.get_logger().info("Goal canceled.")
                return result

            # 현재 위치가 없으면 대기
            if self.current_pose is None:
                time.sleep(self.dt)
                continue

            # 액션이 RUNNING인 동안 토픽으로 최신 목표가 들어오면 그걸 사용
            if self._goal_xy is not None:
                x_t, y_t = self._goal_xy

            x = self.current_pose.x
            y = self.current_pose.y
            th = self.current_pose.theta

            # 거리/각도 계산
            dx = x_t - x
            dy = y_t - y
            dist = math.hypot(dx, dy)
            desired_yaw = math.atan2(dy, dx)
            yaw_err = angle_norm(desired_yaw - th)

            cmd = Twist()

            # 1) 회전 우선
            if abs(yaw_err) > self.yaw_tol:
                cmd.angular.z = max(-self.max_ang, min(self.k_ang * yaw_err, self.max_ang))
                cmd.linear.x = 0.0
            else:
                # 2) 직진 (헤딩 유지 위해 약간의 각속도 보정)
                cmd.linear.x = max(0.0, min(self.k_lin * dist, self.max_lin))
                cmd.angular.z = max(-self.max_ang, min(self.k_ang * yaw_err, self.max_ang))

            # 도착 판정
            if dist <= self.pos_tol:
                self._publish_stop()
                goal_handle.succeed()
                result.result = Empty()
                self.get_logger().info("Goal reached.")
                return result

            # 발행
            self.pub_cmd.publish(cmd)

            # 피드백
            feedback.current_pose = self._pose_to_stamped(x, y, th)
            now = self.get_clock().now()
            nav_time = (now - start).to_msg()
            feedback.navigation_time = nav_time
            # 매우 러프한 남은 시간 추정
            est_sec = dist / max(1e-3, cmd.linear.x) if cmd.linear.x > 1e-3 else 0.0
            feedback.estimated_time_remaining.sec = int(est_sec)
            feedback.estimated_time_remaining.nanosec = int((est_sec - int(est_sec)) * 1e9)
            feedback.number_of_recoveries = 0
            feedback.distance_remaining = float(dist)
            goal_handle.publish_feedback(feedback)

            time.sleep(self.dt)

    # --- helpers ---

    def _publish_stop(self):
        self.pub_cmd.publish(Twist())

    def _pose_to_stamped(self, x, y, yaw) -> PoseStamped:
        ps = PoseStamped()
        ps.header.frame_id = "map"  # turtlesim에선 의미만 부여
        ps.header.stamp = self.get_clock().now().to_msg()
        ps.pose.position.x = float(x)
        ps.pose.position.y = float(y)
        # yaw -> quaternion (z,w)
        ps.pose.orientation.z = math.sin(yaw * 0.5)
        ps.pose.orientation.w = math.cos(yaw * 0.5)
        return ps


def main():
    rclpy.init()
    # 기본 네임스페이스: /turtle1
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ns", type=str, default="/turtle1", help="turtle namespace (e.g., /turtle1)")
    args = parser.parse_args()

    node = TurtleNavigateServer(ns=args.ns)

    # 멀티스레드 실행기로 execute_cb 루프와 서브스크립션을 동시에 처리
    from rclpy.executors import MultiThreadedExecutor
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
