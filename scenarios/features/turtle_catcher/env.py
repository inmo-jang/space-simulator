import os
import math
import pygame
from modules.base_env import BaseEnv
from modules.utils import config, generate_positions
from scenarios.features.turtle_catcher.agent import Agent

# ── TargetTurtle ──────────────────────────────────────────────────────────────
# Analogous to turtle_target in turtlesim (py_bt_ros):
#   position.x / position.y  <->  turtlesim.Pose.x / .y
#   completed                 <->  /kill service called (topic disappears)
# Keyboard control: WASD  or  arrow keys

_target_speed = config.get('target', {}).get('speed', 150.0)  # pixels/sec
_screen_w = config['simulation']['screen_width']
_screen_h = config['simulation']['screen_height']


class TargetTurtle:
    SIZE = 12

    def __init__(self, position):
        self.position = pygame.Vector2(position)
        self.rotation = 0.0        # radians – for visual direction indicator
        self.completed = False
        self.color = (220, 80, 0)  # orange
        self._font = pygame.font.Font(None, 18)

    def update(self, keys, sampling_time):
        if self.completed:
            return
        speed = _target_speed * sampling_time
        dx, dy = 0.0, 0.0
        if keys[pygame.K_w] or keys[pygame.K_UP]:    dy -= speed
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  dy += speed
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  dx -= speed
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dx += speed
        self.position.x = max(self.SIZE, min(_screen_w - self.SIZE, self.position.x + dx))
        self.position.y = max(self.SIZE, min(_screen_h - self.SIZE, self.position.y + dy))
        if dx != 0 or dy != 0:
            self.rotation = math.atan2(dy, dx)

    def draw(self, screen):
        if self.completed:
            return
        cx, cy, s, a = int(self.position.x), int(self.position.y), self.SIZE, self.rotation
        pts = [(cx + s * math.cos(a + da), cy + s * math.sin(a + da)) for da in (0, 2.5, -2.5)]
        pygame.draw.polygon(screen, self.color, pts)
        screen.blit(self._font.render("TARGET (WASD)", True, (80, 30, 0)), (cx + s + 4, cy - 8))

    def draw_task_id(self, _screen):
        pass  # BaseEnv.draw_tasks_info() compatibility


# ── Env ───────────────────────────────────────────────────────────────────────

_agent_locations = config['agents']['locations']
_behavior_tree_xml = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    config['agents']['behavior_tree_xml'],
)


class Env(BaseEnv):
    def __init__(self, config):
        super().__init__(config)
        self.reset()

    def reset(self):
        super().reset()
        self.target = TargetTurtle((_screen_w // 2, _screen_h // 2))
        self.agents = self._generate_agents(seed=self.seed)
        self.tasks = [self.target]  # BaseEnv.update_simulation() completion check

    def _generate_agents(self, seed=None):
        positions = generate_positions(
            1,
            _agent_locations['x_min'], _agent_locations['x_max'],
            _agent_locations['y_min'], _agent_locations['y_max'],
            radius=_agent_locations.get('non_overlap_radius', 0),
            seed=seed,
        )
        agents = [Agent(0, positions[0], self.target)]
        for agent in agents:
            agent.set_global_info_agents(agents)
            agent.create_behavior_tree(_behavior_tree_xml)
        return agents

    async def step(self):
        keys = pygame.key.get_pressed()
        self.target.update(keys, self.sampling_time)
        for agent in self.agents:
            await agent.run_tree()
            agent.update()
        self.update_simulation()

    def save_results(self):
        pass
