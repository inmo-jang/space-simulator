from modules.rl_env import SpaceRLEnv
import numpy as np
import torch.distributed as dist
import pygame

class PZEnv(SpaceRLEnv):

    """
    Initialize.
    """
    def __init__(self, **kwarg):
        super(PZEnv, self).__init__(**kwarg)
        # Initialize previous states
        self.prev_distance_moved = {agent: 0.0 for agent in self.agents}
        self.prev_task_amount_done = {agent: 0.0 for agent in self.agents}
        self.reward = 0.0
        # Initialize distributed training process
        if dist.is_available() and not dist.is_initialized():
            dist.init_process_group(backend="gloo", rank=0, world_size=1)

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
        closest_agents = self.get_closest_items(agent.position, agent.blackboard['local_agents_info'], top_k=agent.rl_agent.nearby_agent_max_num) if 'local_agent_info' in agent.blackboard.keys() else list()
        closest_tasks = self.get_closest_items(agent.position, agent.blackboard['local_tasks_info'], top_k=agent.rl_agent.nearby_task_max_num) if 'local_tasks_info' in agent.blackboard.keys() else list()

        # Process agent positions
        agent_positions = np.array([a.position.xy for a in closest_agents]).flatten()
        agent.blackboard['closest_agents'] = closest_agents
        if len(closest_agents) < agent.rl_agent.nearby_agent_max_num * 2:
            pad_size = agent.rl_agent.nearby_agent_max_num * 2 - len(agent_positions)
            agent_positions = np.pad(agent_positions, (0, pad_size), mode='constant', constant_values=0)

        # Process task positions and remaining amounts
        task_positions = np.array([t.position.xy for t in closest_tasks]).flatten()
        task_remaining = np.array([t.amount for t in closest_tasks])
        agent.blackboard['closest_tasks'] = closest_tasks
        if len(closest_tasks) < agent.rl_agent.nearby_task_max_num * 2:
            position_pad_size =  agent.rl_agent.nearby_task_max_num * 2 - len(task_positions)
            task_pad_size = agent.rl_agent.nearby_task_max_num - len(task_remaining)
            task_positions = np.pad(task_positions, (0, position_pad_size), mode='constant', constant_values=0)
            task_remaining = np.pad(task_remaining, (0, task_pad_size), mode='constant', constant_values=0)


        observation = np.concatenate([agent_positions, task_positions, task_remaining])
        return observation, closest_tasks, closest_agents

    """
    Get the global state representation.
    """
    def global_state(self):
        agent_positions = np.array([agent.position.xy for agent in self.agents]).flatten()

        prev_agent_actions = np.array([agent.blackboard['assigned_task_id'] if 'assigned_task_id' in agent.blackboard.keys() else -1.0 for agent in self.agents]).flatten()
        
        for i, action in enumerate(prev_agent_actions):
            if action is None:
                prev_agent_actions[i] = -1.0
            else:
                prev_agent_actions[i] = float(prev_agent_actions[i])

        task_positions = np.array([self.tasks[i].position.xy if len(self.tasks) > i else pygame.Vector2(0,0) for i in range(self.agents[0].rl_agent.task_num)]).flatten()

        task_remaining = np.array([self.tasks[i].amount if len(self.tasks) > i else 0.0 for i in range(self.agents[0].rl_agent.task_num)])

        global_observation = np.concatenate([agent_positions, prev_agent_actions, task_positions, task_remaining])
        return global_observation

    """
    Update an agent's observation.
    """
    def observe(self, agent):
        global_state = self.global_state()
        agent.blackboard['local_observation'], agent.blackboard['local_tasks'], _ = self.local_observe(agent)
        agent.blackboard['global_observation'] = global_state

    """
    Compute the reward for the given agent.
    """
    def get_reward(self, agent) -> float:
        for agent in self.agents:
            self.reward += self.prev_distance_moved[agent] - agent.distance_moved
            self.prev_distance_moved[agent] = agent.distance_moved
            self.reward += agent.task_amount_done - self.prev_task_amount_done[agent]
            self.prev_task_amount_done[agent] = agent.task_amount_done

        if self.env.mission_completed is True:
            self.reward -= self.env.simuilation_time

        for agent in self.agents:
            agent.blackboard['reward'] = self.reward
