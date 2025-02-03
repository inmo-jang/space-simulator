from modules.utils import config
from modules.rl_agent import SpaceRLAgent
from scenarios.simple.agent import Agent

class PZAgent(SpaceRLAgent):

    """
    Initialize using configuration values.
    """
    def __init__(self):
        # Load configurations
        self.nearby_agent_max_num = config.get('agents').get('nearby_agent_max_num')
        self.nearby_task_max_num = config.get('agents').get('nearby_task_max_num')
        self.agent_num = config.get('agents').get('quantity')
        self.task_num = config.get('tasks').get('quantity')

        # Handle dynamic task generation
        if config.get('tasks').get('dynamic_task_generation').get('enabled') is True:
            task_gen_config = config.get('tasks').get('dynamic_task_generation')
            self.task_num += task_gen_config.get('max_generations') * task_gen_config.get('tasks_per_generation') 

        # (x,y) for agents, (x,y) and remained amount for tasks
        local_obs_size = 2 * self.nearby_agent_max_num + 2 * self.nearby_task_max_num + self.nearby_task_max_num
        # (x,y) and previous action for agents, (x,y) and remained amount for tasks
        global_obs_size = 2 * self.agent_num + self.agent_num + 2 * self.task_num + self.task_num
        super(PZAgent, self).__init__(local_obs_size, global_obs_size, self.nearby_task_max_num)
