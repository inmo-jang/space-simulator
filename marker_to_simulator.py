import rclpy
from rclpy.node import Node

from socket import socket, AF_INET, SOCK_DGRAM
import json

from whycode_interfaces.msg import MarkerArray  # 메시지 타입

class MarkerListener(Node):
    # ----- Simulator canvas size (px) -----
    SIM_WIDTH_PX  = 1260
    SIM_HEIGHT_PX = 660
    # Outer margins (px)
    MARGIN_X = 40
    MARGIN_Y = 40 

    # ----- Measured WhyCon ranges (meters) -----
    WHYCON_Y_MAX =  2.14   # left-most
    WHYCON_Y_MIN = -2.185   # right-most
    WHYCON_Z_MAX =  1.125   # top-most
    WHYCON_Z_MIN = -1.085   # bottom-most

    def __init__(self):
        super().__init__('marker_listener')

        self.AX = - self.SIM_WIDTH_PX  / (self.WHYCON_Y_MAX - self.WHYCON_Y_MIN)
        self.BX = - self.AX * self.WHYCON_Y_MAX
        
        self.AY = - self.SIM_HEIGHT_PX / (self.WHYCON_Z_MAX - self.WHYCON_Z_MIN)
        self.BY = - self.AY * self.WHYCON_Z_MAX
        
        self.CX = self.SIM_WIDTH_PX  / 2.0
        self.CY = self.SIM_HEIGHT_PX / 2.0

        # ROS 구독
        self.subscription = self.create_subscription(
            MarkerArray,
            '/whycode_node/markers',
            self.listener_callback,
            10
        )

        # UDP 송신
        self.sock = socket(AF_INET, SOCK_DGRAM)
        self.udp_ip = '127.0.0.1'
        self.udp_port = 9999

        # 마커 ID → agent_id
        self.marker_to_agent = {
            6: 0,
            1: 1,
            2: 2,
        }

        self.get_logger().info(
            f"MarkerListener started. Tracking markers: {list(self.marker_to_agent.keys())} "
            f"→ Sending to {self.udp_ip}:{self.udp_port}"
        )

    def listener_callback(self, msg):
        for marker in msg.markers:
            agent_id = self.marker_to_agent.get(marker.id)
            if agent_id is None:
                # 매핑에 없는 ID는 무시
                continue

            # WhyCon 좌표 (meters)
            cam_y = float(marker.position.position.y)  # → sim X
            cam_z = float(marker.position.position.z)  # → sim Y
            yaw   = -1 * float(marker.rotation.x)      # 부호/단위(Radian)

            # Simulator 좌표 (pixels)
            sim_x, sim_y = self.convert_to_sim(cam_y, cam_z)

            # UDP 페이로드(키 순서 고정: agent_id → x → y → yaw)
            data = {"agent_id": agent_id, "x": sim_x, "y": sim_y, "yaw": yaw}
            self.sock.sendto(json.dumps(data).encode(), (self.udp_ip, self.udp_port))
            self.get_logger().info(f"Sent: {data}")

    def convert_to_sim(self, y, z):
        """
        WhyCon y,z (meters) → Simulator x,y (pixels)
        - y = +2.13m(좌) → x = 40px,    y = -2.21m(우) → x = 1260px
        - z = +1.18m(위) → y = 40px,    z = -1.07m(아래) → y = 660px
        """
        x_px = self.AX * y + self.BX
        y_px = self.AY * z + self.BY
        
        # shift into the full screen coords by margins
        x_px += self.MARGIN_X
        y_px += self.MARGIN_Y
        return x_px, y_px

def main(args=None):
    rclpy.init(args=args)
    node = MarkerListener()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
