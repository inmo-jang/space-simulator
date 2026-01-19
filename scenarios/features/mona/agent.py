import pygame
import math
from modules.utils import config, generate_positions 
from modules.base_agent import BaseAgent
from scenarios.features.mona.task import task_colors

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']
sampling_time = 1.0 / config['simulation']['sampling_freq']


class Agent(BaseAgent):
    def __init__(self, agent_id, position, tasks_info):
        super().__init__(agent_id, position, tasks_info)
        self.work_rate = work_rate
        
        # MONA: Check if this agent corresponds to a real robot
        self._init_robot_status()

    def _init_robot_status(self):
        """Check if this agent corresponds to a real robot."""
        mona_cfg = config.get('mona', {})
        if not mona_cfg.get('enabled', False):
            return
        
        for robot in mona_cfg.get('robots', []):
            if int(robot.get('agent_id', -1)) == self.agent_id:
                self.is_real_robot = True
                print(f"[Agent {self.agent_id}] Linked to robot at {robot['host']}:{robot['port']}")
                return

    def process_work(self, tasks: list) -> dict:
        # Only real robots can do work
        if not self.is_real_robot:
            return None
    
        # Must have an assigned task
        if self.assigned_task_id is None:
            return None
    
        # Find the assigned task
        assigned_task = None
        for task in tasks:
            if task.task_id == self.assigned_task_id:
                assigned_task = task
                break
    
        # If assigned task not found or already completed
        if assigned_task is None or assigned_task.completed:
            return None
        
        # Get threshold from config
        arrive_threshold = config['tasks'].get('threshold_done_by_arrival', 10.0)
        work_per_step = self.work_rate * sampling_time
    
        # Check if agent is within work range of assigned task
        distance = (self.position - assigned_task.position).length()
        work_range = assigned_task.radius + arrive_threshold
    
        if distance > work_range:
            return None  # Not close enough to work
    
        # Do work on assigned task
        work_done = min(work_per_step, assigned_task.amount)
        assigned_task.amount -= work_done
        if assigned_task.amount <= 0:
            assigned_task.set_done()
    
        # Update agent statistics
        self.update_task_amount_done(work_done)
    
        return {
            'task_id': assigned_task.task_id,
            'work_done': work_done,
            'task_completed': assigned_task.completed
        }

    def set_planned_tasks_from_ids(self, task_ids: list, all_tasks: list):
        """Set planned_tasks from task ID list."""
        self.planned_tasks = []
        task_map = {task.task_id: task for task in all_tasks}
        for tid in task_ids:
            if tid in task_map and not task_map[tid].completed:
                self.planned_tasks.append(task_map[tid])

    def set_nearby_agents_from_ids(self, agent_ids: list, all_agents: list):
        """Set agents_nearby from agent ID list."""
        self.agents_nearby = []
        agent_map = {agent.agent_id: agent for agent in all_agents}
        for aid in agent_ids:
            if aid in agent_map and aid != self.agent_id:
                self.agents_nearby.append(agent_map[aid])

    def update(self):
        """Override update - real robots get position from WhyCon, not simulation."""
        if self.is_real_robot:
            # Position is set externally via set_position()
            pass
        else:
            # Simulation agents use base update
            super().update()

    # ==================== Drawing Methods ====================

    def draw(self, screen):
        """Draw agent with circle (for real robots) and directional triangle."""
        # Draw circle for real robots
        if self.is_real_robot:
            pygame.draw.circle(
                screen, (0, 0, 0),
                (int(self.position.x), int(self.position.y)),
                40,
                width=4
            )
        
        # Draw triangle (direction indicator)
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

    # Provide the global info
    for agent in agents:
        agent.set_global_info_agents(agents)

    return agents
