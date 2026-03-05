import pygame
import math
import os
import time
from modules.utils import config
from modules.base_agent import BaseAgent
from scenarios.features.mona.puppet.sim.task import task_colors
from scenarios.features.mona.puppet.sim.mona_client import MonaClient

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate

        
        self.task_amount_done = 0.0        

        self._mona = None
        self.is_real_robot = False
        self._position_initialized = False  # 추가
        self._last_update_time = time.time()
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

    def set_position(self, x: float, y: float, yaw: float = None):
        if not self._position_initialized:
            self.position.x = float(x)
            self.position.y = float(y)
            if yaw is not None:
                self.rotation = float(yaw)
            self._position_initialized = True
            self._last_update_time = time.time() # 초기화 시점 기록
            return

        # 시간 차이 계산 (초 단위)
        current_time = time.time()
        dt = current_time - self._last_update_time
        self._last_update_time = current_time

        old_pos = pygame.Vector2(self.position.x, self.position.y)

        self.position.x = float(x)
        self.position.y = float(y)
        if yaw is not None:
            self.rotation = float(yaw)

        if self.is_real_robot:
            # 이동 거리 더하기
            distance = (self.position - old_pos).length()
            if distance > 0.0:
                self.distance_moved += distance
            
            # 3. 초당 17만큼 차감 로직 (이동 거리에서 뺌)
            # dt(경과 시간)만큼 비례해서 차감
            reduction = 2 * dt
            self.distance_moved -= reduction
            
            # 거리가 음수가 되지 않도록 방지
            if self.distance_moved < 0:
                self.distance_moved = 0.0

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

    # ==================== Rendering ====================

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


