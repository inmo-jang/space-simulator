import pygame
import math
import os
from modules.utils import config 
from modules.base_agent import BaseAgent

# Load agent configuration (Scenario Specific)
work_rate = config['agents']['work_rate']

# Load behavior tree
behavior_tree_xml = f"{os.path.dirname(os.path.abspath(__file__))}/{config['agents']['behavior_tree_xml']}"

class Agent(BaseAgent):
    def __init__(self, agent_id, ros_bridge, ros_namespace=None):
        super().__init__(agent_id, (0, 0), None)
        self.ros_bridge = ros_bridge
        self.ros_namespace = ros_namespace  # ROS 네임스페이스 저장

    def __repr__(self):
        return f"<Agent id={self.agent_id}, ns={self.ros_namespace}>"

def generate_agents(seed=None, ros_bridge=None):
    agent_namespaces = config['agents'].get('namespaces', [])

    # Initialize agents
    agents = [Agent(idx, ros_bridge, ros_namespace) for idx, ros_namespace in enumerate(agent_namespaces)]

    # Provide global info and create BT
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree(behavior_tree_xml)

    return agents
