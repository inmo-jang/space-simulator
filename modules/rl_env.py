import pygame
from abc import *
from pettingzoo import AECEnv
import gym.spaces
import numpy as np
from modules.base_env import BaseEnv
from typing import Type, TypeVar

T = TypeVar('T')

class SpaceRLEnv(AECEnv, metaclass=ABCMeta):
    """
    Multi-agent reinforcement learning environment.
    It wraps around a BaseEnv and manages agent interactions.
    """

    """
    Initialize the RL environment.

    :param env: The base environment to wrap.
    :param nearby_task_max_num: Maximum number of nearby tasks considered.
    :param nearby_agent_max_num: Maximum number of nearby agents considered.
    :param generate_rl_agent: Function/class to generate RL agents.
    """
    def __init__(self,
                 env: BaseEnv,
                 nearby_task_max_num: int,
                 nearby_agent_max_num: int,
                 generate_rl_agent: type[T]):
        self.env = env
        self.rl_agent_generator = generate_rl_agent
        self.reset()

        self.nearby_task_max_num = nearby_task_max_num
        self.nearby_agent_max_num = nearby_agent_max_num

    """Reset the environment and reinitialize the agent list."""
    def reset(self):
        self.env.reset()
        self.agents = self.env.agents
        self.tasks = self.env.tasks
        for agent in self.agents:
            agent.rl_agent = self.rl_agent_generator() 
            agent.blackboard['reward'] = 0

    """
    Execute one step in the environment.
    This method should be awaited since it is asynchronous.
    """
    async def step(self):
        self.prev_env_step()
        await self.env.step()
        self.post_env_step()
    
    """Post-processing after an environment step (to be overridden in subclasses)."""
    def post_env_step(self):
        pass
    
    """Pre-processing before an environment step (e.g., updating rewards and observations)."""
    def prev_env_step(self):
        for agent in self.agents:
            # Get recent local observation
            agent.blackboard['local_tasks_info'] = agent.get_tasks_nearby(with_completed_task = False)
            agent.blackboard['local_agents_info'] = agent.local_message_receive()
            # Get observation for RL
            self.observe(agent)
            # Get reward
        self.get_reward()

    """Check if the environment is still running."""
    def is_running(self) -> bool:
        return self.env.running

    """Pass keyboard events to the underlying environment."""
    def handle_keyboard_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.env.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    self.env.running = False
                elif event.key == pygame.K_p:
                    self.env.game_paused = not self.env.game_paused
                elif event.key == pygame.K_s:
                    if not self.env.recording:
                        self.env.recording = True
                        self.env.frames = [] # Clear any existing frames
                        self.env.last_frame_time = self.env.simulation_time
                        print("Recording started...") 
                    else:
                        self.env.recording = False
                        print("Recording stopped.")
                        self.env.result_saver.save_gif(self.frames) 
                elif event.key == pygame.K_r:
                    print("Scenario reset!")
                    self.reset()           

    """Render the environment."""
    def render(self):
        self.env.render()

    """Check if the environment is currently recording."""
    def is_recording(self) -> bool:
        return self.env.recording

    """Check if the game is currently paused."""
    def is_game_paused(self) -> bool:
        return self.env.game_paused

    """Check if the mission has been completed."""
    def is_mission_completed(self) -> bool:
        return self.env.mission_completed

    """Record the current screen frame if recording is supported."""
    def record(self):
        self.env.record_screen_frame()

    """Close the environment and release any resources."""
    def close(self):
        self.env.close()

    """Abstract method to compute observations for a given agent."""
    @abstractmethod
    def observe(self, agent):
        raise NotImplementedError

    """Abstract method to compute rewards for a given agent."""
    @abstractmethod
    def get_reward(self, agent):
        raise NotImplementedError
