import rclpy
from rclpy.node import Node
from std_msgs.msg import Header
from socket import socket, AF_INET, SOCK_DGRAM
import json

from whycode_interfaces.msg import MarkerArray  # 메시지 타입

class MarkerListener(Node):
    def __init__(self):
        super().__init__('marker_listener')
        self.subscription = self.create_subscription(
            MarkerArray,
            '/whycode_node/markers',
            self.listener_callback,
            10
        )
        self.sock = socket(AF_INET, SOCK_DGRAM)
        self.udp_ip = '127.0.0.1'
        self.udp_port = 9999

        # 화면 중심 좌표 (픽셀 기준) - config.yaml에서 정의된 screen 크기
        self.screen_center_x = 700  # screen_width = 1400
        self.screen_center_y = 400  # screen_height = 800
        self.scale = 1000  # m → pixel 변환 배율

    def listener_callback(self, msg):
        for marker in msg.markers:
            if marker.id == 2:  # 특정 마커 ID만 처리
                y = marker.position.position.y
                z = marker.position.position.z
                yaw = marker.rotation.x  # Yaw 값 가져오기
                
                sim_x, sim_y = self.convert_to_sim(y, z)
                data = {
                    "agent_id": 0,
                    "x": sim_x,
                    "y": sim_y,
                    "yaw": -yaw  # yaw 값 추가!
                }
                self.sock.sendto(json.dumps(data).encode(), (self.udp_ip, self.udp_port))
                self.get_logger().info(f"Sent: {data}")

    def convert_to_sim(self, y, z):
        # 시뮬레이터 기준 중앙 정렬 변환: (0,0)일 때 화면 중심으로 오도록
        sim_x = -0.28 * y * self.scale + self.screen_center_x
        sim_y = -0.28 * z * self.scale + self.screen_center_y
        return sim_x, sim_y

def main(args=None):
    rclpy.init(args=args)
    node = MarkerListener()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()

