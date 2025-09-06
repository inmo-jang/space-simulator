from modules.base_bt_nodes import Node, Status
from rclpy.action import ActionClient


class ROSConditionBTNode(Node):
    def __init__(self, name, agent, msg_types_topics):
        super().__init__(name)
        self.ros = agent.ros_bridge
        self._cache = {}
        for msg_type, topic, key in msg_types_topics:
            self.ros.node.create_subscription(
                msg_type, topic,
                lambda m, k=key: self._cache.__setitem__(k, m),
                1
            )

    async def run(self, agent, blackboard):
        if not self._cache:
            self.status = Status.RUNNING
        elif self._predicate(agent, blackboard):
            self.status = Status.SUCCESS
        else:
            self.status = Status.FAILURE
        return self.status

    def _predicate(self, agent, blackboard) -> bool: # 내 조건이 만족했는가?"를 판단하는 코드 구현
        raise NotImplementedError






