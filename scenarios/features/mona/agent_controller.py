import math
import pygame
from modules.utils import config

SAMPLING_TIME = 1.0 / config['simulation']['sampling_freq']

class AgentController:

    def __init__(self, agent,
                 angle_align=0.04,     # 직진 시작 각도 오차(rad)
                 arrive_dist=5.0):     # 도착 거리(px)
        self.agent = agent
        self.ANGLE_ALIGN = angle_align
        self.ARRIVE_DIST = arrive_dist

        self.target = None
        self.aligned = False

    def set_target(self, pos_vec2):
        self.target = pygame.Vector2(pos_vec2)

    def has_target(self):
        return self.target is not None

    def clear_target(self):
        self.target = None
        self.aligned = False

    def apply_control(self, dt=SAMPLING_TIME, integrate=False):
        """목표를 향해 회전/가속을 계산.
        integrate=False: 가속만 적용(적분은 BaseAgent.update()가 수행)
        integrate=True : 여기서 바로 적분까지 수행
        """
        ag = self.agent
        if not self.has_target():
            return False

        # 1) 타깃 벡터/거리
        to_target = self.target - ag.position
        dist = to_target.length()

        # 2) 목표 헤딩과 각도 오차
        if dist > 1e-6:
            dir_unit = to_target.normalize()
        else:
            dir_unit = pygame.Vector2(math.cos(ag.rotation), math.sin(ag.rotation))

        desired_heading = math.atan2(dir_unit.y, dir_unit.x)
        delta = desired_heading - ag.rotation
        while delta <= -math.pi:
            delta += 2 * math.pi
        while delta > math.pi:
            delta -= 2 * math.pi

        # 3) 회전 (각속도 제한)
        max_dtheta = getattr(ag, 'max_angular_speed', 0.25) * dt
        dtheta = max(-max_dtheta, min(max_dtheta, delta))
        ag.rotation += dtheta

        # 정렬 판단
        self.aligned = abs(delta) < self.ANGLE_ALIGN

        # 4) 원하는 속도 -> 가속(steer)
        if self.aligned:
            move_dir = pygame.Vector2(math.cos(ag.rotation), math.sin(ag.rotation))
            desired_vel = move_dir * getattr(ag, 'max_speed', 0.25)
        else:
            desired_vel = pygame.Vector2(0, 0)

        steer = desired_vel - ag.velocity
        max_acc = getattr(ag, 'max_accel', 0.05)
        if steer.length_squared() > max_acc ** 2:
            steer.scale_to_length(max_acc)

        if not integrate:
            # 적분은 BaseAgent.update()에서 수행
            ag.applyForce(steer)
        else:
            # 즉시 적분(레거시 step 경로)
            ag.velocity += steer * dt
            max_spd = getattr(ag, 'max_speed', 0.25)
            if ag.velocity.length_squared() > max_spd ** 2:
                ag.velocity.scale_to_length(max_spd)
            ag.position += ag.velocity * dt
            ag.distance_moved += ag.velocity.length() * dt
            ag.memory_location.append((ag.position.x, ag.position.y))
            if len(ag.memory_location) > config['simulation']['agent_track_size']:
                ag.memory_location.pop(0)
            ag.acceleration *= 0

        # 5) 도착 판정
        if dist < self.ARRIVE_DIST and self.aligned:
            self.clear_target()
            ag.reset_movement()
            return True

        return True

    # 기존 API 유지(필요 시 사용)
    def step(self, dt=SAMPLING_TIME):
        return self.apply_control(dt, integrate=True)

