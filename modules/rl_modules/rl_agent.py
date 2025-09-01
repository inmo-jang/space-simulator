from gym import spaces
import numpy as np

class SpaceRLAgent:

    """
    Initialize the RL agent.

    :param local_obs_size: Dimension of local observation space.
    :param global_obs_size: Dimension of global observation space.
    :param nearby_task_max_num: Maximum number of nearby tasks (used for action space size).
    """
    def __init__(self, 
                 local_obs_size:int, 
                 global_obs_size:int, 
                 action_size:int):
        self.local_observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(local_obs_size,), dtype=np.float32)
        self.global_observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(global_obs_size,), dtype=np.float32)

        # the first element is no-op
        self.action_space = spaces.Discrete(action_size + 1)
                                                
                                                
                                                
                                                
                                                
