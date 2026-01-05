import pygame
import math
import os
import time
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent
from scenarios.features.mona.task import task_colors
from scenarios.features.mona.MessageCodec import MessageCodec

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']
COMMUNICATION_RADIUS = config['agents']['communication_radius']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"


class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate

        # Shared message to send to MONA (can be updated each tick)
        self.message_to_share = {}
        self._vis_keep_sec = 0.1         # Line persistence duration (adjustable 0.5~1.5)
        self._last_peer_ids = set()      # Last received peer id set
        self._last_peer_toa  = 0.0       # Last receive time (Time of Arrival, epoch sec)  
        self._cfg_comm_radius = COMMUNICATION_RADIUS
        
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
        result = super().update(*args, **kwargs)

        mc = getattr(self, "mona_comm", None)
        if mc is not None:
            # Codec을 사용하여 압축 메시지 생성
            compressed = MessageCodec.encode(self.agent_id, self.message_to_share, self.tasks_info)
            mc.set_message(self, msg_override=compressed)

        self.local_message_receive()
        return result

    def local_message_receive(self):
        """수신된 데이터를 복원하고 통신 시각화 상태 업데이트"""
        now = time.time()
        peer_ids = set()
        self.reset_messages_received()

        mc = getattr(self, "mona_comm", None)
        monitor = mc.get_message(self.agent_id) if mc is not None else None
             
        if isinstance(monitor, dict):
            received_dict = monitor.get("received_messages") or {}
            for payload in received_dict.values():
                # Codec을 사용하여 데이터 복원
                restored_msg = MessageCodec.decode(payload)
                if restored_msg and restored_msg["agent_id"] is not None:
                    self.receive_message(restored_msg)
                    peer_ids.add(int(restored_msg["agent_id"]))

        # 수신 성공 시 피어 정보 업데이트
        if peer_ids:
            self._last_peer_ids, self._last_peer_toa = peer_ids, now

        # 인근 에이전트 목록 갱신 (시뮬레이션 로직)
        self._update_nearby_agents(now)
        
    def _update_nearby_agents(self, now):
        """물리적 통신 반경 내의 에이전트 필터링 로직"""
        visual_peers = self._last_peer_ids if (now - self._last_peer_toa) < self._vis_keep_sec else set()
        
        # 통신 반경 필터링 로직 수행
        if self._cfg_comm_radius > 0:
            r_sq = self._cfg_comm_radius ** 2
            self.agents_nearby = [ag for ag in (self.agents_info or [])
                                  if ag.agent_id in visual_peers and ag.agent_id != self.agent_id
                                  and (self.position - ag.position).length_squared() <= r_sq]
        else:
            self.agents_nearby = [ag for ag in (self.agents_info or [])
                                  if ag.agent_id in visual_peers and ag.agent_id != self.agent_id]
        
        # 시각화용 통신 거리 계산
        if self.agents_nearby:
            dist = max((self.position - ag.position).length() for ag in self.agents_nearby)
            self.communication_radius = min(dist, self._cfg_comm_radius) if self._cfg_comm_radius > 0 else dist
        else:
            self.communication_radius = 0

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
