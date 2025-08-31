import pygame
import math
import os
import json
import time
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent
from scenarios.features.mona.task import task_colors
from scenarios.features.mona.agent_controller import AgentController
from scenarios.features.mona.mona_client import MonaClient

sampling_time = 1.0 / config['simulation']['sampling_freq']

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

mouse_target_position = None

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate

        
        self.task_amount_done = 0.0        
        
        # 컨트롤러 생성 (필요하면 게인 인자로 튜닝값 주입 가능)
        self.controller = AgentController(self)
        
        # --- MONA 연결 옵션 (mona.yaml 사용) ---
        mona_cfg = (config.get('mona') or {})
        self.is_real_robot = bool(mona_cfg.get('enabled', False))
        self._mona_host = mona_cfg.get('host', '127.0.0.1')
        self._mona_port = int(mona_cfg.get('port', 8080))
        self._mona = None
        self._connect_attempted = False  # ← 추가
        #self._last_try = 0.0
        #self._reconnect_interval = float(mona_cfg.get('reconnect_interval_sec', 2.0))

        self._marker_target = None  # pygame.Vector2 | None
        self._marker_yaw = None  # float | None
        
        # 픽셀-미터 스케일 (1000 px = 1 m → 1 px = 1 mm)
        self._px_to_mm = 1.0  # 1 pixel == 1 mm
        
    # ---- 유틸: (-π, π] 래핑
    @staticmethod
    def _wrap_pi(a: float) -> float:
        while a <= -math.pi:
            a += 2 * math.pi
        while a > math.pi:
            a -= 2 * math.pi
        return a
        
    def _compute_g_command(self, target: pygame.Vector2) -> tuple[float, float]:
        dx = float(target.x - self.position.x)
        dy = float(target.y - self.position.y)

        # 이 좌표계(+y 아래)에서는 atan2(dy, dx)가 "시계방향 +, 반시계 -" 규약과 정합
        desired_heading = math.atan2(dy, dx)  # rad, cw+
        curr = float(self.rotation)           # rad, cw+

        delta_rad = self._wrap_pi(desired_heading - curr)  # rad, cw+/ccw-
        delta_deg = math.degrees(delta_rad)                # deg

        dist_px = math.hypot(dx, dy)
        dist_mm = dist_px * self._px_to_mm                 # 1 px = 1 mm

        return (delta_deg, dist_mm)

    # ---- MONA로 G 명령 전송 (지속 연결 가정)
    def _send_mona_g(self, target: pygame.Vector2) -> None:
        if not (self._mona and self._mona.is_connected):
            return
        deg, mm = self._compute_g_command(target)
        # 필요 시 아주 작은 명령 무시
        if abs(deg) < 1.0 and mm < 5.0:
            return
        payload = f"G {deg:.3f} {mm:.1f}\n"
        self._mona.send(payload)
        print(f"[MONA] G sent: {payload.strip()}")

    def _ensure_mona(self):
        """주기적으로(기본 2초) 연결 시도. 성공 시 self._mona 유지."""
        if not self.is_real_robot or self._connect_attempted:
            return
        self._connect_attempted = True  # ← 이번 프레임에 1회만 시도
        self._mona = MonaClient(self._mona_host, self._mona_port, timeout=2.0)
        ok = self._mona.connect()
        if not ok:
            self._mona = None

    def set_marker_target(self, x: float, y: float, yaw: float | None = None, mirror_on_screen: bool = True):
        self.controller.set_target(pygame.Vector2(float(x), float(y)))
        if yaw is not None:
            self.rotation = float(yaw)
        # 실로봇 연결 중에도 화면이 즉시 따라오게 하려면:
        if mirror_on_screen:
            self.position.x = float(x)
            self.position.y = float(y)
            
    def set_target(self, pos_vec2):
        self.controller.set_target(pos_vec2)
        if self.is_real_robot and self._mona and self._mona.is_connected:
            self._send_mona_g(pygame.Vector2(pos_vec2))
            
    # ---- MONA 연결 시 주기 전송 없도록 비워둠(지속 연결 펌웨어는 G 한 번이면 수행)
    def _mona_step(self):
        return  # 움직임 명령은 클릭 시 1회 전송으로 충분

    def update(self):
        # 1) MONA 모드라면 먼저 연결 보장 시도
        if self.is_real_robot:
            self._ensure_mona()
        # 2) 실제 MONA가 '연결된 경우' → 모나로 명령만 전송하고 시뮬 물리는 건너뜀
        if self.is_real_robot and self._mona and self._mona.is_connected:
            self._mona_step()
            return
        # 3) 그 외(비활성/미연결) → 기존 시뮬레이터 흐름 유지
        if self.controller.has_target():
            self.controller.step()  # 속도/가속도 명령만 생성(시뮬 이동)
        else:
            super().update()

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
