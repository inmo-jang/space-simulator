import pygame
import math
import os
import time
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent
from scenarios.features.mona.task import task_colors

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate

        # --- Mona로 보낼 공유 메시지(틱마다 업데이트 가능) ---
        self.message_to_share = {}

        self._vis_keep_sec = 1.0         # 선 유지 시간 (원하면 0.5~1.5 조절)
        self._last_peer_ids = set()      # 마지막으로 들린 peer id 집합
        self._last_peer_toa  = 0.0        # 마지막 수신 시각 (Time of Arrival, epoch sec)
        
        self.task_amount_done = 0.0        

    def draw(self, screen):
        size = 10
        angle = self.rotation

        # Calculate the triangle points based on the current position and angle
        p1 = pygame.Vector2(self.position.x + size * math.cos(angle), self.position.y + size * math.sin(angle))
        p2 = pygame.Vector2(self.position.x + size * math.cos(angle + 2.5), self.position.y + size * math.sin(angle + 2.5))
        p3 = pygame.Vector2(self.position.x + size * math.cos(angle - 2.5), self.position.y + size * math.sin(angle - 2.5))

        self.update_color()
        pygame.draw.polygon(screen, self.color, [p1, p2, p3])

    def update_color(self):        
        self.color = task_colors.get(self.assigned_task_id, (20, 20, 20))  # Default to Dark Grey if no task is assigned

    def update(self, *args, **kwargs):
        """
        한 틱마다 호출되는 agent 갱신 함수
        - 먼저 BaseAgent.update()를 실행하여 기존 동작 유지
        - 그 다음 MONA로 message_to_share(dict)을 JSON 한 줄로 전송함 (set_message 이용)
        """
        result = super().update(*args, **kwargs)

        # --- MONA로 메시지 전송 트리거 ---
        # getattr : self에 mona_comm 없어도 error 없이 None 반환시킴
        mc = getattr(self, "mona_comm", None)
        if mc is not None:
            mc.set_message(self)  # self.message_to_share가 dict면 JSON 한 줄 전송

        return result

    def local_message_receive(self):
        """
        MONA에서 받은 모니터 JSON(dict)의 'received_messages'를 기반으로
        이웃을 결정. 새 수신이 없을 땐 _vis_keep_sec 동안 마지막 이웃을 유지해
        회색 선이 깜빡이지 않게 한다.
        """
        now = time.time()
        peer_ids = set()

        # 1) 실제 수신 시도 (있으면 peer_ids 채움)
        mc = getattr(self, "mona_comm", None)
        monitor = mc.get_message(self.agent_id) if mc is not None else None
        if isinstance(monitor, dict):
            recv = monitor.get("received_messages") or {}
            for k, v in recv.items():
                aid = None
                if isinstance(v, dict) and "agent_id" in v:
                    aid = v.get("agent_id")
                else:
                    aid = k
                try:
                    peer_ids.add(int(aid))  # "0","1"처럼 숫자 문자열만 사용
                except Exception:
                    pass  # "A","B" 등은 현재 제외 (매핑 원하면 나중에 추가)

        # 2) 새 수신이 있으면 캐시 업데이트
        if peer_ids:
            self._last_peer_ids = peer_ids
            self._last_peer_toa  = now

        # 3) 시각화에 쓸 최종 peer 집합 결정 (시각화 부드럽게 유지)
        # 마지막  peer 집합 기준으로 _vis_keep_sec 동안 선을 유지함.
        if self._last_peer_ids and (now - self._last_peer_toa) < self._vis_keep_sec:
            visual_peer_ids = self._last_peer_ids
        else:
            visual_peer_ids = set()  # TTL 지났으면 지움

        # 4) agent 객체로 매핑 → 회색 선 대상 확정
        all_agents = self.agents_info or []
        self.agents_nearby = [
            ag for ag in all_agents
            if ag.agent_id in visual_peer_ids and ag.agent_id != self.agent_id
        ]

        # 5) 통신 반경 : mona의 거리를 기반으로 하되, yaml의 반경을 영향받아 사용됨.
        if self.agents_nearby:
            observed = max((self.position - ag.position).length() for ag in self.agents_nearby)
            cfg_cap = getattr(self, "_cfg_comm_radius", 0) or 0
            # cfg_cap > 0 이면 '최대 반경'으로 동작, 0/음수면 캡 없이 observed 그대로 사용
            self.communication_radius = min(observed, cfg_cap) if cfg_cap > 0 else observed
        else:
            self.communication_radius = 0

        # BT 노드의 협업 결정에서 messages_received 입력으로 사용하므로 유지
        self.reset_messages_received()
        for other in self.agents_nearby:
            self.receive_message(other.message_to_share)

        return self.agents_nearby



def generate_agents(tasks_info, seed=None):
    agent_quantity = config['agents']['quantity']
    agent_locations = config['agents']['locations']

    agents_positions = generate_positions(agent_quantity,
                                      agent_locations['x_min'],
                                      agent_locations['x_max'],
                                      agent_locations['y_min'],
                                      agent_locations['y_max'],
                                      radius=agent_locations['non_overlap_radius'],
                                      seed=seed)

    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree(behavior_tree_xml)

    return agents
