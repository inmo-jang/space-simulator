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
        """
        Process work on nearby tasks.
        
        Work condition: agent is within (task.radius + threshold_done_by_arrival) of task center
        This uses the task radius as the work boundary.
        
        Args:
            tasks: List of all tasks
            
        Returns:
            dict with 'task_id' and 'work_done' if work was performed, None otherwise
        """
        # Only real robots can do work
        if not self.is_real_robot:
            return None
        
        # Get threshold from config
        arrive_threshold = config['tasks'].get('threshold_done_by_arrival', 10.0)
        work_per_step = self.work_rate * sampling_time
        
        # Find the closest incomplete task within work range
        closest_task = None
        closest_distance = float('inf')
        
        for task in tasks:
            if task.completed:
                continue
            
            # Calculate distance from agent to task
            distance = (self.position - task.position).length()
            
            # Work condition: distance < task.radius + threshold (task 반경 기준!)
            work_range = task.radius + arrive_threshold
            
            if distance <= work_range and distance < closest_distance:
                closest_task = task
                closest_distance = distance
        
        # If agent is within range of a task, do work
        if closest_task is not None:
            # Calculate actual work done (cannot exceed remaining amount)
            work_done = min(work_per_step, closest_task.amount)
            
            # Reduce task amount
            closest_task.amount -= work_done
            if closest_task.amount <= 0:
                closest_task.set_done()
            
            # Update agent statistics
            self.update_task_amount_done(work_done)
            
            return {
                'task_id': closest_task.task_id,
                'work_done': work_done,
                'task_completed': closest_task.completed
            }
        
        return None

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
