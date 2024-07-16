import pygame
import math
import copy
from modules.behavior_tree import Sequence, DecisionMakingNode, ConsensusCheckingNode, TaskExecutingNode
from modules.utils import config, generate_positions, generate_task_colors

# Load agent configuration
agent_max_speed = config['agents']['max_speed']
agent_max_accel = config['agents']['max_accel']
max_angular_speed = config['agents']['max_angular_speed']
agent_approaching_to_target_radius = config['agents']['target_approaching_radius']
agent_track_size = config['simulation']['agent_track_size']
work_rate = config['agents']['work_rate']
agent_communication_radius = config['agents']['communication_radius']
task_colors = generate_task_colors(config['tasks']['quantity'])
situation_awareness_radius = config.get('agents', {}).get('situation_awareness_radius', None)
font = pygame.font.Font(None, 15)
class Agent:
    def __init__(self, agent_id, position, tasks_info):
        self.agent_id = agent_id
        self.position = pygame.Vector2(position)
        self.velocity = pygame.Vector2(0, 0)
        self.acceleration = pygame.Vector2(0, 0)
        self.max_speed = agent_max_speed
        self.max_accel = agent_max_accel
        self.max_angular_speed = max_angular_speed
        self.work_rate = work_rate
        self.memory_location = []  # To draw track
        self.rotation = 0  # Initial rotation
        self.color = (0, 0, 255)  # Blue color
        self.blackboard = {}

        self.tasks_info = tasks_info # global info
        self.agents_info = None # global info
        self.communication_radius = agent_communication_radius
        self.neighbor_agents_id = set()
        self.message_to_share = None
        self.messages_received = []

    def create_behavior_tree(self):
        self.tree = self._create_behavior_tree()

    def _create_behavior_tree(self):
        return Sequence("Agent Tree", children=[
            DecisionMakingNode("DecisionMaking", self),
            ConsensusCheckingNode("ConsensusChecking", self),
            TaskExecutingNode("TaskExecuting", self)
        ])

    async def run_tree(self):
        return await self.tree.run(self, self.blackboard)

    def follow(self, target):
        # Calculate desired velocity
        desired = target - self.position
        d = desired.length()

        if d < agent_approaching_to_target_radius:
            # Apply arrival behavior
            desired.normalize_ip()
            desired *= self.max_speed * (d / agent_approaching_to_target_radius)  # Adjust speed based on distance
        else:
            desired.normalize_ip()
            desired *= self.max_speed

        steer = desired - self.velocity
        steer = self.limit(steer, self.max_accel)
        self.applyForce(steer)

    def applyForce(self, force):
        self.acceleration += force

    def update(self):
        # Update velocity and position
        self.velocity += self.acceleration
        self.velocity = self.limit(self.velocity, self.max_speed)
        self.position += self.velocity
        self.acceleration *= 0  # Reset acceleration

        # Memory of positions to draw track
        self.memory_location.append((self.position.x, self.position.y))
        if len(self.memory_location) > agent_track_size:
            self.memory_location.pop(0)

        # Update rotation
        desired_rotation = math.atan2(self.velocity.y, self.velocity.x)
        rotation_diff = desired_rotation - self.rotation
        while rotation_diff > math.pi:
            rotation_diff -= 2 * math.pi
        while rotation_diff < -math.pi:
            rotation_diff += 2 * math.pi

        # Limit angular velocity
        if abs(rotation_diff) > self.max_angular_speed:
            rotation_diff = math.copysign(self.max_angular_speed, rotation_diff)

        self.rotation += rotation_diff

    def reset_movement(self):
        self.velocity = pygame.Vector2(0, 0)
        self.acceleration = pygame.Vector2(0, 0)


    def limit(self, vector, max_value):
        if vector.length_squared() > max_value**2:
            vector.scale_to_length(max_value)
        return vector

    def local_broadcast(self, agents):
        self.neighbor_agents_id = set()
        communication_radius_squared = self.communication_radius ** 2

        for other_agent in agents:
            distance = (self.position - other_agent.position).length_squared()
            if distance <= communication_radius_squared:
                other_agent.receive_message(self.message_to_share)
                self.neighbor_agents_id.add(other_agent.agent_id)        

    def reset_messages_received(self):
        self.messages_received = []

    def receive_message(self, message):
        if message not in self.messages_received:
            self.messages_received.append(copy.copy(message))            

    def draw(self, screen):
        size = 10
        angle = self.rotation

        # Calculate the triangle points based on the current position and angle
        p1 = pygame.Vector2(self.position.x + size * math.cos(angle), self.position.y + size * math.sin(angle))
        p2 = pygame.Vector2(self.position.x + size * math.cos(angle + 2.5), self.position.y + size * math.sin(angle + 2.5))
        p3 = pygame.Vector2(self.position.x + size * math.cos(angle - 2.5), self.position.y + size * math.sin(angle - 2.5))

        self.update_color()
        pygame.draw.polygon(screen, self.color, [p1, p2, p3])


    def draw_tail(self, screen):
        # Draw track
        if len(self.memory_location) >= 2:
            pygame.draw.lines(screen, self.color, False, self.memory_location, 1)               
        

    def draw_communication_topology(self, screen, agents):
     # Draw lines to neighbor agents
        for neighbor_agent_id in self.neighbor_agents_id:
            neighbor_position = agents[neighbor_agent_id].position
            pygame.draw.line(screen, (200, 200, 200), (int(self.position.x), int(self.position.y)), (int(neighbor_position.x), int(neighbor_position.y)))

    def draw_agent_id(self, screen):
        # Draw assigned_task_id next to agent position
        text_surface = font.render(f"agent_id: {self.agent_id}", True, (50, 50, 50))
        screen.blit(text_surface, (self.position[0] + 10, self.position[1] - 10))

    def draw_assigned_task_id(self, screen):
        # Draw assigned_task_id next to agent position
        text_surface = font.render(f"task_id: {self.blackboard.get('assigned_task_id', None)}", True, (50, 50, 50))
        screen.blit(text_surface, (self.position[0] + 10, self.position[1]))

    def draw_situation_awareness_circle(self, screen):
        # Draw the situation awareness radius circle    
        if situation_awareness_radius:    
            pygame.draw.circle(screen, self.color, (self.position[0], self.position[1]), situation_awareness_radius, 1)


    def update_color(self):
        _assigned_task_id = self.blackboard['assigned_task_id']
        self.color = task_colors.get(_assigned_task_id, (20, 20, 20))  # Default to Dark Grey if no task is assigned

    def set_global_info_agents(self, agents_info):
        self.agents_info = agents_info

def generate_agents(tasks_info):
    agent_quantity = config['agents']['quantity']
    agent_locations = config['agents']['locations']

    agents_positions = generate_positions(agent_quantity,
                                      agent_locations['x_min'],
                                      agent_locations['x_max'],
                                      agent_locations['y_min'],
                                      agent_locations['y_max'],
                                      radius=agent_locations['non_overlap_radius'])

    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree()

    return agents
