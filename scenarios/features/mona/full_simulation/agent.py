import pygame
import math
import os
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent
from scenarios.features.mona.full_simulation.task import task_colors

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']
sampling_time = 1.0 / config['simulation']['sampling_freq']
agent_approaching_to_target_radius = config['agents']['target_approaching_radius']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate

        
        self.task_amount_done = 0.0        

        self._use_rotation_shim = False
        self._rotation_shim_aligned = True
        self._movement_commanded = False

    def follow(self, target):
        self._movement_commanded = True
        super().follow(target)

    def follow_rotation_shim(self, target):
        """
        Rotation Shim Controller
        ─────────────────────────────────────────────────────────────
        Phase 1 (not aligned): Rotate in place toward the target.
                                Velocity is zeroed – the agent does NOT move.
        Phase 2 (aligned):     Lock rotation to target heading and move
                                straight. No further rotation adjustment
                                is applied during translation.
        ─────────────────────────────────────────────────────────────
        """
        self._use_rotation_shim = True
        self._movement_commanded = True

        desired = target - self.position
        d = desired.length()

        if d == 0:
            self._rotation_shim_aligned = True
            return

        desired_angle = math.atan2(desired.y, desired.x)

        angle_diff = desired_angle - self.rotation
        while angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        while angle_diff < -math.pi:
            angle_diff += 2 * math.pi

        ALIGN_THRESHOLD = 0.05  # radians (~2.9°)

        if abs(angle_diff) > ALIGN_THRESHOLD:
            # Phase 1: Rotate only
            self._rotation_shim_aligned = False
            rot_step = math.copysign(min(abs(angle_diff), self.max_angular_speed), angle_diff)
            self.rotation += rot_step * sampling_time
            self.velocity = pygame.Vector2(0, 0)
            self.acceleration = pygame.Vector2(0, 0)
        else:
            # Phase 2: Move straight
            self._rotation_shim_aligned = True
            self.rotation = desired_angle

            if d < agent_approaching_to_target_radius:
                speed = self.max_speed * (d / agent_approaching_to_target_radius)
            else:
                speed = self.max_speed

            forward = pygame.Vector2(math.cos(self.rotation), math.sin(self.rotation))
            desired_vel = forward * speed
            steer = desired_vel - self.velocity
            steer = self.limit(steer, self.max_accel)
            self.applyForce(steer)

    def update(self, *args, **kwargs):
        result = super().update(*args, **kwargs)

        # Stop deceleration when no movement node ran this tick
        if not self._movement_commanded:
            if self.velocity.length_squared() > 0:
                if self.velocity.length() <= self.max_accel * sampling_time:
                    self.velocity = pygame.Vector2(0, 0)
                else:
                    brake = -self.velocity.normalize() * min(self.max_accel, self.velocity.length() / sampling_time)
                    self.velocity += brake * sampling_time

        # Rotation update
        if not self._use_rotation_shim:
            desired_rotation = math.atan2(self.velocity.y, self.velocity.x)
            rotation_diff = desired_rotation - self.rotation
            while rotation_diff > math.pi:
                rotation_diff -= 2 * math.pi
            while rotation_diff < -math.pi:
                rotation_diff += 2 * math.pi
            if abs(rotation_diff) > self.max_angular_speed:
                rotation_diff = math.copysign(self.max_angular_speed, rotation_diff)
            self.rotation += rotation_diff * sampling_time

        # Reset flags for next tick
        self._use_rotation_shim = False
        self._movement_commanded = False

        return result

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
    fixed_positions = config['agents'].get('fixed_positions', [])
    fixed_positions = [tuple(p) for p in fixed_positions]  # list → tuple

    num_fixed  = min(len(fixed_positions), agent_quantity)
    num_random = agent_quantity - num_fixed

    if num_random > 0:
        random_positions = generate_positions(
            num_random,
            agent_locations['x_min'],
            agent_locations['x_max'],
            agent_locations['y_min'],
            agent_locations['y_max'],
            radius=agent_locations['non_overlap_radius'],
            seed=seed,
        )
    else:
        random_positions = []

    agents_positions = fixed_positions[:num_fixed] + random_positions

    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree(behavior_tree_xml)

    return agents
