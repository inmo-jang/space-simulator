from modules.base_bt_nodes import Node, Status
from rclpy.action import ActionClient


class ConditionWithROSTopics(Node):
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
        # For PA-BT
        self.is_expanded = False
        self.type = "Condition"

    async def run(self, agent, blackboard):
        if not self._cache:
            self.status = Status.RUNNING
        elif self._predicate(agent, blackboard):
            self.status = Status.SUCCESS
        else:
            self.status = Status.FAILURE
        
        # For PA-BT
        blackboard[self.name] = {'status': self.status, 'is_expanded': self.is_expanded} 

        return self.status

    def _predicate(self, agent, blackboard) -> bool: # 내 조건이 만족했는가?"를 판단하는 코드 구현
        raise NotImplementedError

    def set_expanded(self): # For PA-BT
        self.is_expanded = True


class ActionWithROSAction(Node):
    """
    심플 ROS Action 클라이언트 베이스.
      - action_spec: (ActionType, action_name)
      - _fingerprint(): 목표 바뀜 판정 (None이면 실행 불가)
      - _build_goal(): Goal 생성
      - _interpret_result(): 완료 시 SUCCESS/FAILURE 매핑
    """
    def __init__(self, name, agent, action_spec):
        super().__init__(name)
        self.ros = agent.ros_bridge
        action_type, action_name = action_spec
        self.client = ActionClient(self.ros.node, action_type, action_name)

        self._goal_handle = None
        self._result_future = None
        self._phase = 'idle'       # 'idle' -> 'sending' -> 'running'

        # For PA-BT
        self.type = "Action"

    def _build_goal(self, agent, blackboard):
        # 하위 클래스에서 구현
        # Action Request가 보내질 때 실행되는 함수
        raise NotImplementedError   

    def _on_running(self, agent, blackboard):
        # 하위 클래스에서 구현
        # Action Request가 한 번 시작되고 나면서 BT가 Tick이 될 때 실행되는 함수
        # 예) ROS Action Server로 요청을 하고 난 이후, 실시간으로 위치가 바뀌는 Target에 대한 정보를 ROS Topic으로 공유
        pass

    def _interpret_result(self, result, agent, blackboard, status_code=None):
        # 하위 클래스에서 구현  
        # Action Request가 종료되면 호출되는 함수
        return Status.SUCCESS                    

    async def run(self, agent, blackboard):
        # Action Request 송신
        if self._phase == 'idle':
            if not self.client.wait_for_server(timeout_sec=0.0): # 서버가 아직 준비가 안된 상황 고려
                self.status = Status.RUNNING
                return self.status

            goal = self._build_goal(agent, blackboard)
            if goal is None:
                self.status = Status.FAILURE
                return self.status

            self.client.send_goal_async(goal).add_done_callback(self._on_goal_response)
            self._phase = 'sending'
            self.status = Status.RUNNING
            return self.status

        # Action Request를 송신했으나 아직 Acceptance Receipt를 못 받은 상황
        if self._phase == 'sending':
            self.status = Status.RUNNING
            return self.status

        # Action Request를 수신하여 진행되는 도중
        if self._phase == 'running':
            if self._result_future and self._result_future.done():
                res = self._result_future.result()   # <- get_result 응답
                self.status = self._interpret_result(res.result, agent, blackboard, res.status)
                self._phase = 'idle'
                return self.status
            self._on_running(agent, blackboard)
            self.status = Status.RUNNING
            return self.status

        self.status = Status.RUNNING
        return self.status

    def _on_goal_response(self, future):
        self._goal_handle = future.result()
        if not self._goal_handle.accepted:
            self._phase = 'idle'
            return
        self._result_future = self._goal_handle.get_result_async()
        self._phase = 'running'

    def halt(self):
        if self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()
        self._phase = 'idle'


class ActionWithROSService(Node):
    """
    심플 ROS Service 클라이언트 베이스.
      - service_spec: (SrvType, service_name)
      - _build_request(): 서비스 요청 메시지 생성
      - _interpret_response(): 응답을 SUCCESS/FAILURE로 매핑
    """
    def __init__(self, name, agent, service_spec):
        super().__init__(name)
        self.ros = agent.ros_bridge
        srv_type, srv_name = service_spec
        self.client = self.ros.node.create_client(srv_type, srv_name)

        self._future = None
        self._sent = False

        # For PA-BT
        self.type = "Action"

    def _build_request(self, agent, blackboard):
        # 하위 클래스에서 구현
        raise NotImplementedError

    def _interpret_response(self, response, agent, blackboard):
        # 하위 클래스에서 필요 시 오버라이드
        return Status.SUCCESS

    async def run(self, agent, blackboard):
        # 서비스가 아직 준비 안 되었으면 다음 틱에 재시도
        if not self.client.wait_for_service(timeout_sec=0.0):
            self.status = Status.RUNNING
            return self.status

        # 최초 1회 호출
        if not self._sent:
            req = self._build_request(agent, blackboard)
            if req is None:
                self.status = Status.FAILURE
                return self.status
            self._future = self.client.call_async(req)
            self._sent = True
            self.status = Status.RUNNING
            return self.status

        # 응답 도착 확인
        if self._future and self._future.done():
            resp = self._future.result()
            self.status = self._interpret_response(resp, agent, blackboard)
            self._sent = False
            return self.status

        # 아직 응답 대기 중
        self.status = Status.RUNNING
        return self.status

    def halt(self):
        # 서비스는 취소 개념이 없으므로 플래그만 초기화
        self._sent = False
