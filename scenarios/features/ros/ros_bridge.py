# ros_bridge.py
import threading
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node as RclNode


class ROSBridge:
    """
    단일 ROS 노드와 executor를 관리하는 싱글톤.
    모든 BT 노드들이 bridge.node를 통해 ROS와 통신한다.
    """

    _instance = None

    def __init__(self, node_name='space_bt_bridge', namespace=''):
        if ROSBridge._instance is not None:
            raise RuntimeError("ROSBridge is a singleton. Use ROSBridge.get().")

        # rclpy 초기화
        rclpy.init(args=None)

        # node 생성
        self.node = RclNode(node_name=node_name, namespace=namespace)

        # executor 생성
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)

        # spin을 백그라운드에서 돌리는 스레드
        self._spin_thread = threading.Thread(target=self._spin, daemon=True)
        self._spin_thread.start()

        ROSBridge._instance = self

    def _spin(self):
        try:
            self.executor.spin()
        except Exception as e:
            print(f"[ROSBridge] Spin thread stopped: {e}")

    @classmethod
    def get(cls, node_name='space_bt_bridge', namespace=''):
        """
        싱글톤 인스턴스를 반환. 최초 호출 시에만 생성된다.
        """
        if cls._instance is None:
            cls._instance = ROSBridge(node_name=node_name, namespace=namespace)
        return cls._instance

    def shutdown(self):
        """Stop executor thread and shutdown rclpy cleanly."""
        try:
            self.executor.shutdown()
        except Exception:
            pass
        try:
            self.node.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass
        ROSBridge._instance = None  # allow re-init later

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.shutdown()