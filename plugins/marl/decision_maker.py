from modules.utils import config

if config['decision_making'] == 'mappo':
    from plugins.marl.mappo.mappo_policy import get_policy
else:
    assert False, 'Not implemented yet'

class DecisionMaker:
    def __init__(self, agent):
        self.agent = agent

    """Decide on an action based on the current state."""
    def decide(self, blackboard) -> int:
        selected_task_id = get_policy(self.agent.rl_agent.local_observation_space, 
                                      self.agent.rl_agent.global_observation_space, 
                                      self.agent.rl_agent.action_space)\
                                    .get_action(self.agent.agent_id, blackboard)

        return selected_task_id
