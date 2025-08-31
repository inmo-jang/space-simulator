import math
import pygame
from modules.utils import config

SAMPLING_TIME = 1.0 / config['simulation']['sampling_freq']

class AgentController:
    """
    PID 없이: 목표 각도까지 회전만 하고, 각도 오차가 충분히 작아지면 직진.
    - 회전 속도는 agent.max_angular_speed로 클램프
    - 직진 속도는 agent.max_speed
    - 도착 조건 만족 시 target 해제 및 정지
    """
    def __init__(self, agent,
                 angle_align=0.08,     # 직진 시작 각도 오차(rad)
                 arrive_dist=5.0):     # 도착 거리(px)
        self.agent = agent
        self.ANGLE_ALIGN = angle_align
        self.ARRIVE_DIST = arrive_dist

        self.target = None
        self.aligned = False

    def set_target(self, pos_vec2):
        self.target = pygame.Vector2(pos_vec2)
        self.aligned = False  # 새 목표 -> 처음엔 회전부터

    def has_target(self):
        return self.target is not None

    def clear_target(self):
        self.target = None
        self.aligned = False

    def step(self, dt=SAMPLING_TIME):
        if not self.has_target():
            return False  # 컨트롤러가 할 일 없음

        ag = self.agent

        # 1) 목표 각도 계산
        desired = math.atan2(self.target.y - ag.position.y,
                             self.target.x - ag.position.x)
        err = desired - ag.rotation

        # [-pi, pi]로 래핑
        while err > math.pi: err -= 2 * math.pi
        while err < -math.pi: err += 2 * math.pi

        # 2) 각도 정렬 여부 판단
        self.aligned = (abs(err) < self.ANGLE_ALIGN)

        # 3) 회전
        max_rot_step = ag.max_angular_speed * dt
        # 회전은 부호만 유지한 채 최대 회전 속도 범위 내로
        rot_step = max(-max_rot_step, min(max_rot_step, err))
        ag.rotation += rot_step

        # 4) 이동
        if self.aligned:
            # 각도 맞으면 직진
            direction = pygame.Vector2(math.cos(ag.rotation), math.sin(ag.rotation))
            ag.velocity = direction * ag.max_speed
        else:
            # 각도 안 맞으면 제자리 회전만
            ag.velocity = pygame.Vector2(0, 0)

        # 상태 적분 (BaseAgent.update()와 동일한 방식)
        ag.position += ag.velocity * dt
        ag.distance_moved += ag.velocity.length() * dt
        ag.memory_location.append((ag.position.x, ag.position.y))
        if len(ag.memory_location) > config['simulation']['agent_track_size']:
            ag.memory_location.pop(0)
        ag.acceleration *= 0  # 외력 없음

        # 5) 도착 체크: 충분히 가까우면 멈추고 타깃 해제
        if (self.target - ag.position).length() < self.ARRIVE_DIST and self.aligned:
            self.clear_target()
            ag.reset_movement()
            return True

        return True