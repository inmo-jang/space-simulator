from modules.rl_env import SpaceRLEnv
import numpy as np
import pygame
import os

class PZEnv(SpaceRLEnv):

    """
    Initialize.
    """
    def __init__(self, **kwarg):
        super(PZEnv, self).__init__(**kwarg)
        self.reset()
        

    def reset(self):
        super().reset()
        # Initialize previous states
        self.prev_distance_moved = {agent: 0.0 for agent in self.agents}
        self.prev_task_amount_done = {agent: 0.0 for agent in self.agents}
        self.prev_simulation_time = 0
        self.prev_tasks_left = sum(1 for task in self.env.tasks if not task.completed)
        self.reward = 0.0

    """
    Find the closest items based on distance.
    """
    def get_closest_items(self, reference_position, items, top_k=10):
        distances = [(item, reference_position.distance_to(item.position)) for item in items]
        distances.sort(key=lambda x: x[1]) 
        closest_items = [item[0] for item in distances[:min(top_k, len(distances))]]
        return closest_items

    """
    Get the local observation for an agent.
    """
    def local_observe(self, agent):
        closest_agents = self.get_closest_items(agent.position, agent.blackboard['local_agents_info'], top_k=agent.rl_agent.nearby_agent_max_num - 1 ) if 'local_agents_info' in agent.blackboard.keys() else list()
        closest_agents.insert(0,agent)
        closest_tasks = self.get_closest_items(agent.position, agent.blackboard['local_tasks_info'], top_k=agent.rl_agent.nearby_task_max_num) if 'local_tasks_info' in agent.blackboard.keys() else list()

        # Process agent positions
        agent_positions = np.array([a.position.xy for a in closest_agents]).flatten()
        if len(closest_agents) < agent.rl_agent.nearby_agent_max_num:
            pad_size = agent.rl_agent.nearby_agent_max_num * 2 - len(agent_positions)
            agent_positions = np.pad(agent_positions, (0, pad_size), mode='constant', constant_values=0)

        # Process task positions and remaining amounts
        task_positions = np.array([t.position.xy for t in closest_tasks]).flatten()
        task_remaining = np.array([t.amount for t in closest_tasks])
        agent.blackboard['closest_tasks'] = closest_tasks
        if len(closest_tasks) < agent.rl_agent.nearby_task_max_num:
            position_pad_size =  agent.rl_agent.nearby_task_max_num * 2 - len(task_positions)
            task_pad_size = agent.rl_agent.nearby_task_max_num - len(task_remaining)
            task_positions = np.pad(task_positions, (0, position_pad_size), mode='constant', constant_values=0)
            task_remaining = np.pad(task_remaining, (0, task_pad_size), mode='constant', constant_values=0)

        observation = np.concatenate([agent_positions, task_positions, task_remaining])
        return observation

    """
    Get the global state representation.
    """
    def global_state(self):
        agent_positions = np.array([agent.position.xy for agent in self.agents]).flatten()

        prev_agent_actions = np.array([float(agent.blackboard.get('assigned_task_id', -1.0)) if agent.blackboard.get('assigned_task_id') is not None else -1.0 for agent in self.agents])
        
        task_positions = np.array([self.tasks[i].position.xy if len(self.tasks) > i else (0.0,0.0) for i in range(self.agents[0].rl_agent.task_num)]).flatten()

        task_remaining = np.array([self.tasks[i].amount if len(self.tasks) > i else 0.0 for i in range(self.agents[0].rl_agent.task_num)])

        observation = np.concatenate([agent_positions, prev_agent_actions, task_positions, task_remaining])
        return observation

    """
    Update an agent's observation.
    """
    def observe(self, agent):
        agent.blackboard['global_observation'] = self.global_state()
        agent.blackboard['local_observation'] = self.local_observe(agent)

    """
    Compute the reward for the given agent.
    """
    def get_reward(self) -> float:
        reward = 0
        for agent in self.agents:
            #reward += self.prev_distance_moved[agent] - agent.distance_moved
            #self.prev_distance_moved[agent] = agent.distance_moved
            reward += (agent.task_amount_done - self.prev_task_amount_done[agent])*10
            self.prev_task_amount_done[agent] = agent.task_amount_done
        
        current_tasks_left = sum(1 for task in self.env.tasks if not task.completed)
        reward += (self.prev_tasks_left - current_tasks_left) * 100
        self.prev_tasks_left = current_tasks_left
        reward += self.prev_simulation_time - self.env.simulation_time
        self.prev_simulation_time = self.env.simulation_time

        for agent in self.agents:
            agent.blackboard['reward'] += reward
