import rclpy
from rclpy.node import Node
import json
import os
from std_msgs.msg import Header
from whycode_interfaces.msg import MarkerArray

class WhyConBridge(Node):
    def __init__(self):
        super().__init__('whycon_bridge')
        self.subscription = self.create_subscription(
            MarkerArray,
            '/whycode_node/markers',
            self.listener_callback,
            10
        )
        self.origin_map = {}  # 각 마커 id에 대해 초기 y/z 좌표 저장
        self.get_logger().info("[WhyConBridge] Subscribed to /whycode_node/markers")

    def convert_to_simulator(self, y_m, z_m,
                             origin_y, origin_z,
                             screen_width=1400,
                             screen_height=1000,
                             scale=1000.0):  # 1m = 1000px
        dx = (y_m - origin_y) * scale
        dy = -(z_m - origin_z) * scale  # ✅ Y축 반전
        x_px = screen_width / 2 + dx
        y_px = screen_height / 2 + dy
        return x_px, y_px

    def listener_callback(self, msg):
        for marker in msg.markers:
            try:
                agent_id = marker.id
                y_m = marker.position.position.y  # → simulator x
                z_m = marker.position.position.z  # → simulator y
                yaw = marker.rotation.x

                if agent_id not in self.origin_map:
                    self.origin_map[agent_id] = (y_m, z_m)
                    self.get_logger().info(f"[Agent {agent_id}] Set origin at y={y_m:.3f}, z={z_m:.3f}")

                origin_y, origin_z = self.origin_map[agent_id]
                x_px, y_px = self.convert_to_simulator(y_m, z_m, origin_y, origin_z)

                pose_data = {
                    "id": agent_id,
                    "x": x_px,
                    "y": y_px,
                    "yaw": yaw
                }

                with open(f"/tmp/agent_pose_{agent_id}.json", 'w') as f:
                    json.dump(pose_data, f)

                self.get_logger().debug(
                    f"[Agent {agent_id}] Δy={y_m - origin_y:.3f}m, Δz={z_m - origin_z:.3f}m → px=({x_px:.1f}, {y_px:.1f})"
                )

            except Exception as e:
                self.get_logger().warn(f"[WhyConBridge] Failed to process marker {marker.id}: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = WhyConBridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
