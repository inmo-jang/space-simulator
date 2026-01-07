import pygame
import math
import os
import time
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent
from scenarios.features.mona.task import task_colors
from scenarios.features.mona.mona_client import MonaClient
from scenarios.features.mona.MessageCodec import MessageCodec

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']
COMMUNICATION_RADIUS = config['agents']['communication_radius']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id: int, position: tuple, tasks_info: list):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate

        # Shared message to send to MONA (can be updated each tick)
        self.message_to_share = {}

        self._vis_keep_sec = 0.1         # Line persistence duration (adjustable 0.5~1.5)
        self._last_peer_ids = set()      # Last received peer id set
        self._last_peer_toa  = 0.0       # Last receive time (Time of Arrival, epoch sec)
        
        self.task_amount_done = 0.0        
        
        self._cfg_comm_radius = COMMUNICATION_RADIUS
        
        self._mona = None
        self.is_real_robot = False
        self._init_robot_connection()

    def _init_robot_connection(self):
        """Initialize connection to real robot if configured."""
        mona_cfg = config.get('mona', {})
        
        if not mona_cfg.get('enabled', False):
            return
        
        robot_cfg = self._find_robot_config(mona_cfg)
        if robot_cfg is None:
            print(f"[Warning] Agent {self.agent_id}: No robot config found")
            return
        
        self.is_real_robot = True
        self._mona = MonaClient(
            host=robot_cfg.get('host', '127.0.0.1'),
            port=robot_cfg.get('port', 8080),
            px_to_mm=mona_cfg.get('px_to_mm', 1.0),
            distance_scale=mona_cfg.get('distance_scale', 1.0)
        )
        print(f"[Agent {self.agent_id}] Connected to {robot_cfg['host']}:{robot_cfg['port']}")

    def _find_robot_config(self, mona_cfg: dict) -> dict:
        """Find robot configuration for this agent."""
        for robot in mona_cfg.get('robots', []):
            if int(robot.get('agent_id', -1)) == self.agent_id:
                return robot
        return None

    # ==================== Position Control ====================

    def set_position(self, x: float, y: float, yaw: float = None):
        """Set agent position (called by WhyCon tracker)."""
        self.position.x = float(x)
        self.position.y = float(y)
        if yaw is not None:
            self.rotation = float(yaw)

    def follow(self, target):
        """
        Follow a target position (called by BT nodes).
        
        - Simulation mode: Uses BaseAgent physics
        - Real robot mode: Sends UDP command to robot
        """
        if self._is_robot_connected():
            self._send_move_command(target)
        else:
            super().follow(target)

    # ==================== Update Loop ====================

    def update(self):
        """
        Update agent state each frame.
        
        - Real robot mode: Sends stop if no task assigned
        - Simulation mode: BaseAgent handles physics
        """
        if not self._is_robot_connected():
            super().update()
            return
        
        if self.assigned_task_id is None:
            self._mona.send_stop()

    def _send_move_command(self, target):
        """Send movement command to real robot."""
        self._mona.send_g_to(
            current_position=(self.position.x, self.position.y),
            current_heading=self.rotation,
            target_position=(float(target[0]), float(target[1]))
        )

    def _is_robot_connected(self) -> bool:
        """Check if connected to a real robot."""
        return self.is_real_robot and self._mona and self._mona.is_connected


    def update(self, *args, **kwargs):
        result = super().update(*args, **kwargs)

        mc = getattr(self, "mona_comm", None)
        if mc is not None:
            compressed = MessageCodec.encode(self.agent_id, self.message_to_share, self.tasks_info)
            mc.set_message(self, msg_override=compressed)

        self.local_message_receive()
        return result

    def local_message_receive(self):
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

        if peer_ids:
            self._last_peer_ids, self._last_peer_toa = peer_ids, now

        # 인근 에이전트 목록 갱신 (시뮬레이션 로직)
        self._update_nearby_agents(now)
        
    def _update_nearby_agents(self, now):
        """물리적 통신 반경 내의 에이전트 필터링 로직"""
        visual_peers = self._last_peer_ids if (now - self._last_peer_toa) < self._vis_keep_sec else set()
        
        if self._cfg_comm_radius > 0:
            r_sq = self._cfg_comm_radius ** 2
            self.agents_nearby = [ag for ag in (self.agents_info or [])
                                  if ag.agent_id in visual_peers and ag.agent_id != self.agent_id
                                  and (self.position - ag.position).length_squared() <= r_sq]
        else:
            self.agents_nearby = [ag for ag in (self.agents_info or [])
                                  if ag.agent_id in visual_peers and ag.agent_id != self.agent_id]
        
        if self.agents_nearby:
            dist = max((self.position - ag.position).length() for ag in self.agents_nearby)
            self.communication_radius = min(dist, self._cfg_comm_radius) if self._cfg_comm_radius > 0 else dist
        else:
            self.communication_radius = 0
            
    def draw(self, screen):
        """Draw agent with circle and directional triangle."""
        # 1. Circle
        pygame.draw.circle(
            screen, (0, 0, 0),
            (int(self.position.x), int(self.position.y)),
            40,
            width=4
        )
        # 2. Triangle
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
