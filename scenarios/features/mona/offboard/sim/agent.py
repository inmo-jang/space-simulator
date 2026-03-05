import pygame
import math
import os
import time
from modules.utils import config
from modules.base_agent import BaseAgent
from scenarios.features.mona.offboard.sim.task import task_colors
from scenarios.features.mona.offboard.sim.mona_client import MonaClient

# Dynamic timestamp offset for message compression
TIMESTAMP_OFFSET = int(time.time())

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']
COMMUNICATION_RADIUS = config['agents']['communication_radius']

# Compression scale factor for CBBA bids
BID_SCALE_FACTOR = 1000.0

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}/{config['agents']['behavior_tree_xml']}"

def _is_numeric_key(key) -> bool:
    try:
        int(key)
        return True
    except (ValueError, TypeError):
        return False

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate

        # P2P (CBBA 통신) 관련
        self.message_to_share = {}
        self._vis_keep_sec = 0.1
        self._last_peer_ids = set()
        self._last_peer_toa = 0.0
        self._cfg_comm_radius = COMMUNICATION_RADIUS

        
        self.task_amount_done = 0.0        

        # Puppet (실제 로봇 이동 제어) 관련
        self._mona = None
        self.is_real_robot = False
        self._position_initialized = False
        self._last_update_time = time.time()
        self._init_robot_connection()

    # ==================== Robot Connection ====================

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

    def _is_robot_connected(self) -> bool:
        """Check if connected to a real robot."""
        return self.is_real_robot and self._mona and self._mona.is_connected

    # ==================== Position (WhyCon) ====================

    def set_position(self, x: float, y: float, yaw: float = None):
        if not self._position_initialized:
            self.position.x = float(x)
            self.position.y = float(y)
            if yaw is not None:
                self.rotation = float(yaw)
            self._position_initialized = True
            self._last_update_time = time.time() # 초기화 시점 기록
            return

        old_pos = pygame.Vector2(self.position.x, self.position.y)

        self.position.x = float(x)
        self.position.y = float(y)
        if yaw is not None:
            self.rotation = float(yaw)

        if self.is_real_robot:
            NOISE_THRESHOLD = 1.0  # pixels
            distance = (self.position - old_pos).length()
            if distance > NOISE_THRESHOLD:
                self.distance_moved += distance

    # ==================== Movement ====================

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

    def _send_move_command(self, target):
        """Send movement command to real robot."""
        self._mona.send_g_to(
            current_position=(self.position.x, self.position.y),
            current_heading=self.rotation,
            target_position=(float(target[0]), float(target[1]))
        )

    # ==================== Update Loop ====================

    def update(self, *args, **kwargs):
        """
        매 스텝 실행되는 업데이트.

        [Puppet Part]  실제 로봇이면 물리 시뮬레이션 스킵,
                       태스크 없을 때 정지 명령 전송.
        [P2P Part]     CBBA 메시지를 TCP로 ESP32에 전송하고,
                       ESP32로부터 수신한 peer 메시지를 복원.
        """
        # ------ [1] Puppet: 물리 업데이트 or 정지 명령 ------
        if self._is_robot_connected():
            # 실제 로봇: 위치는 WhyCon이 주입. 이동은 follow()에서 처리.
            # 태스크가 없으면 정지 명령 전송.
            if self.assigned_task_id is None:
                self._mona.send_stop()
        else:
            # 시뮬레이션: BaseAgent 물리 계산
            super().update(*args, **kwargs)

        # ------ [2] P2P: CBBA 메시지 ESP32로 TCP 전송 ------
        mc = getattr(self, "mona_comm", None)
        if mc is not None:
            compressed_msg = self._build_compressed_cbba_message()
            mc.set_message(self, msg_override=compressed_msg)

        # ------ [3] P2P: ESP32로부터 peer 메시지 수신 ------
        self.local_message_receive()

    # ==================== CBBA Message Compression ====================

    def _build_compressed_cbba_message(self) -> dict:
        """
        Compress CBBA data for ESP-NOW 250byte limit compliance.
        """
        original_msg = getattr(self, "message_to_share", {})
        if not original_msg:
            return {}
        
        y_dict = original_msg.get('winning_bids', {})
        z_dict = original_msg.get('winning_agents', {})
        
        compressed_y = {}
        compressed_z = {}

        for task in self.tasks_info:
            if not task.completed:
                tid = task.task_id  # enumerate 인덱스 대신 실제 task_id 사용
                val_y = y_dict.get(tid, y_dict.get(str(tid)))
                if val_y is not None and float(val_y) > 0:
                    compressed_y[tid] = int(round(float(val_y) * BID_SCALE_FACTOR))
                
                val_z = z_dict.get(tid, z_dict.get(str(tid)))
                if val_z is not None and val_z != -1:
                    compressed_z[tid] = int(val_z)

        s_data = original_msg.get('message_received_time_stamp', {})
        compressed_s = {}
        for ag_id, ts in s_data.items():
            if ts is not None and isinstance(ts, (int, float)):
                compressed_s[ag_id] = int(ts) - TIMESTAMP_OFFSET

        return {
            "id": int(self.agent_id),
            "y": compressed_y,
            "z": compressed_z,
            "s": compressed_s
        }

    def local_message_receive(self):
        """수신된 데이터를 복원하고 통신 시각화 상태 업데이트.

        mona.enabled = False 이면 base 클래스의 시뮬레이션 통신으로 fallback한다.
        """
        mc = getattr(self, "mona_comm", None)
        if mc is None or not mc.enabled:
            # 순수 시뮬레이션 모드: base_agent의 로컬 메시지 수신으로 처리
            return super().local_message_receive()

        now = time.time()
        peer_ids = set()
        self.reset_messages_received()

        monitor = mc.get_message(self.agent_id)
             
        if isinstance(monitor, dict):
            recv = monitor.get("received_messages") or {}
            
            for k, v in recv.items():
                if isinstance(v, dict) and "y" in v:
                    restored_msg = {}
                    restored_msg["agent_id"] = v.get("id", v.get("agent_id"))

                    sender_id = restored_msg.get("agent_id")
                    if sender_id is None:
                        continue

                    # ★ 거리 필터링
                    if self._cfg_comm_radius > 0:
                        sender_agent = next(
                            (ag for ag in (self.agents_info or []) if ag.agent_id == int(sender_id)),
                            None
                        )
                        if sender_agent and (self.position - sender_agent.position).length_squared() > self._cfg_comm_radius ** 2:
                            continue  # 범위 밖이면 무시

                    # 1. Restore Winning Bids
                    y_raw = v["y"]
                    if isinstance(y_raw, list):
                        restored_msg["winning_bids"] = {
                            i: (val / BID_SCALE_FACTOR) 
                            for i, val in enumerate(y_raw) 
                            if isinstance(val, (int, float)) and val > 0
                        }
                    elif isinstance(y_raw, dict):
                        restored_msg["winning_bids"] = {
                            int(tid): (val / BID_SCALE_FACTOR) 
                            for tid, val in y_raw.items() 
                            if isinstance(val, (int, float)) and _is_numeric_key(tid)
                        }
                    else:
                        restored_msg["winning_bids"] = {}
                    
                    # 2. Restore Winning Agents - type check + numeric key validation enhanced
                    if "z" in v:
                        z_raw = v["z"]
                        if isinstance(z_raw, list):
                            restored_msg["winning_agents"] = {
                                i: val 
                                for i, val in enumerate(z_raw) 
                                if isinstance(val, (int, float)) and val != -1
                            }
                        elif isinstance(z_raw, dict):
                            restored_msg["winning_agents"] = {
                                int(tid): val 
                                for tid, val in z_raw.items() 
                                if isinstance(val, (int, float)) and _is_numeric_key(tid)
                            }
                        else:
                            restored_msg["winning_agents"] = {}
                    else:
                        restored_msg["winning_agents"] = {}
                    
                    # 3. Restore Timestamps - type check + numeric key validation enhanced
                    if "s" in v and v["s"]:
                        compressed_s = v["s"]
                        if isinstance(compressed_s, dict):
                            restored_msg["message_received_time_stamp"] = {
                                str(ag_id): (int(ts) + TIMESTAMP_OFFSET) 
                                for ag_id, ts in compressed_s.items()
                                if isinstance(ts, (int, float)) and _is_numeric_key(ag_id)
                            }
                        else:
                            restored_msg["message_received_time_stamp"] = {}
                    else:
                        restored_msg["message_received_time_stamp"] = {}

                    # ★ receive_message 1회만 호출
                    self.receive_message(restored_msg)
                    try:
                        peer_ids.add(int(sender_id))
                    except (ValueError, TypeError):
                        pass

        # 수신 성공 시 피어 정보 업데이트
        if peer_ids:
            self._last_peer_ids, self._last_peer_toa = peer_ids, now

        if self._last_peer_ids and (now - self._last_peer_toa) < self._vis_keep_sec:
            visual_peer_ids = self._last_peer_ids
        else:
            visual_peer_ids = set()

        all_agents = self.agents_info or []
        if self._cfg_comm_radius > 0:
            # If communication_radius is set: apply distance filtering
            comm_radius_sq = self._cfg_comm_radius ** 2
            self.agents_nearby = [
                ag for ag in all_agents
                if ag.agent_id in visual_peer_ids 
                and ag.agent_id != self.agent_id
                and (self.position - ag.position).length_squared() <= comm_radius_sq
            ]
        else:
            # If communication_radius is 0: no distance filtering (global)
            self.agents_nearby = [
                ag for ag in all_agents
                if ag.agent_id in visual_peer_ids and ag.agent_id != self.agent_id
            ]
        if self.agents_nearby:
            observed = max((self.position - ag.position).length() for ag in self.agents_nearby)
            cfg_cap = getattr(self, "_cfg_comm_radius", 0) or 0
            self.communication_radius = min(observed, cfg_cap) if cfg_cap > 0 else observed
        else:
            self.communication_radius = 0

        return self.agents_nearby
  

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


