import os

class BTRunner:
    def __init__(self, config):
        self.config = config
        self.agents = None

    def initialize(self, agents):
        self.agents = agents
        # Provide global info and create behavior tree
        for agent in self.agents:
            agent.set_global_info_agents(self.agents)
            scenario_path = self.config['scenario'].get('environment').replace('.', '/')
            behavior_tree_xml = f"{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}/{scenario_path}/{self.config['agents']['behavior_tree_xml']}"
            agent.create_behavior_tree(str(behavior_tree_xml))
         

    async def step(self):
        # Main bt_runner loop logic
        for agent in self.agents:
            await agent.run_tree()

    def close(self):
        if self.agent and hasattr(self.agent, 'tree'):
            self.agent.halt_tree()