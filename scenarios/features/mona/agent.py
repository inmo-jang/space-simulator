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

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

mouse_target_position = None

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.agent_id = agent_id
        self.work_rate = work_rate

        
        self.task_amount_done = 0.0        
        
        # 컨트롤러 생성 (필요하면 게인 인자로 튜닝값 주입 가능)
        self.controller = AgentController(self)
        
        # --- MONA 연결 옵션 (mona.yaml 사용) ---
        mona_cfg = (config.get('mona') or {})
        robots_cfg = mona_cfg.get('robots')
        my_cfg = None
        if isinstance(robots_cfg, list) and robots_cfg:
            # (1) robots 항목에 agent_id 키가 있으면 우선 매칭
            for r in robots_cfg:
                try:
                    if int(r.get('agent_id')) == int(self.agent_id):
                        my_cfg = r
                        break
                except Exception:
                    pass
            # (2) 없으면 인덱스로 폴백(0→첫번째, 1→두번째 ...)
            if my_cfg is None and len(robots_cfg) > self.agent_id:
                my_cfg = robots_cfg[self.agent_id]
        # (3) robots가 없으면 단일 설정 그대로 사용
        if my_cfg is None:
            my_cfg = mona_cfg
        
        self.is_real_robot = bool(my_cfg.get('enabled', mona_cfg.get('enabled', False)))
        self._mona_host = my_cfg.get('host', mona_cfg.get('host', '127.0.0.1'))
        self._mona_port = int(my_cfg.get('port', mona_cfg.get('port', 8080)))
        
        self._mona = MonaClient.from_config(self.agent_id, mona_cfg) if self.is_real_robot else None

    def set_position(self, x: float, y: float, yaw: float | None = None):
        if yaw is not None:
            self.rotation = float(yaw)
        self.position.x = float(x)
        self.position.y = float(y)
            
    def set_target(self, pos_vec2):
        self.controller.set_target(pos_vec2)
        if self.is_real_robot and self._mona and self._mona.is_connected:
            # 클릭 타겟 기억(주기 재전송 옵션용)
            self._mona.remember_click_target((float(pos_vec2[0]), float(pos_vec2[1])))
            #즉시 1회 전송
            self._mona.send_g_to(
                (self.position.x, self.position.y),
                float(self.rotation),
                (float(pos_vec2[0]), float(pos_vec2[1])),
            )
            
        # BT에서 호출하는 이동 명령: 컨트롤만 적용(적분은 BaseAgent.update가 수행)
    def follow(self, target):
        # 목표 세팅
        self.controller.set_target(target)
        # 힘(가속)만 생성, 적분은 BaseAgent.update()
        self.controller.apply_control(integrate=False)

    def update(self):
        # 1) MONA 모드라면 먼저 연결 보장 시도
        if self.is_real_robot and self._mona:
            self._mona.ensure_connected()
            
        # 2) 실제 MONA가 '연결된 경우' → 모나로 명령만 전송하고 시뮬 물리는 건너뜀
        if self.is_real_robot and self._mona and self._mona.is_connected:
            # 주기 G 전송 옵션(0이면 아무 것도 하지 않음)
            self._mona.step_periodic_g(
                (self.position.x, self.position.y),
                float(self.rotation),
            )
            return
            
        # 3) 그 외(비활성/미연결) → 기존 시뮬레이터 흐름 유지
        #if self.controller.has_target():
        #    self.controller.step()  # 속도/가속도 명령만 생성(시뮬 이동)
        #else:
        #    super().update()
        
        # 3) SIM(혹은 미연결) → 적분은 BaseAgent.update가 일괄 수행
        #    (follow()에서 가속만 설정됨; 목표 없으면 정지 유지)
        if not self.controller.has_target():
            self.reset_movement()
        super().update()

    def draw(self, screen):
        tri_r = 10      # 삼각형 "size" 그대로
        circle_r = 40   # 반지름 40px(= 40mm; 1mm=1px)

        angle = self.rotation
        cx, cy = float(self.position.x), float(self.position.y)

        # 1) 원(지름 80mm) 그리기: 연한 회색 테두리
        pygame.draw.circle(screen, (0, 0, 0), (int(cx), int(cy)), int(circle_r), width=4)

        # 2) 기존 삼각형 그리기 (반지름 tri_r 원 위의 3점) — 원 안에 자연스럽게 들어감
        p1 = pygame.Vector2(cx + tri_r * math.cos(angle),          cy + tri_r * math.sin(angle))
        p2 = pygame.Vector2(cx + tri_r * math.cos(angle + 2.5),    cy + tri_r * math.sin(angle + 2.5))
        p3 = pygame.Vector2(cx + tri_r * math.cos(angle - 2.5),    cy + tri_r * math.sin(angle - 2.5))

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
