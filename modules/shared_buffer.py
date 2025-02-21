import torch
import numpy as np
import torch.nn.functional as F
from modules.utils import config

# The following code is modified from https://github.com/marlbenchmark/on-policy/
# It implements a replay buffer for multi-agent reinforcement learning (MARL).

"""Flattens the input tensor x over the first two dimensions."""
def _flatten(T, N, x):
    return x.reshape(T * N, *x.shape[2:])

"""Reshapes the input tensor x to be one-dimensional over the first axis."""
def _cast(x, last_index):
    if last_index < 0:
        x = [item for sublist in x if len(sublist) > abs(last_index) for item in sublist[:last_index]]
    else:
        x = [item for sublist in x if len(sublist) > abs(last_index) for item in sublist]
    if isinstance(x[0], torch.Tensor):
        x = torch.stack(x).squeeze()
    else:
        x = torch.tensor(np.array(x), dtype=torch.float32).detach()
    if len(x.shape) < 2:
        x = x.reshape(-1,1)
    return x

"""Extracts the observation space shape based on its type."""
def get_shape_from_obs_space(obs_space):
    if obs_space.__class__.__name__ == 'Box':
        obs_shape = obs_space.shape
    elif obs_space.__class__.__name__ == 'list':
        obs_shape = obs_space
    else:
        raise NotImplementedError
    return obs_shape

"""Extracts the action space shape based on its type."""
def get_shape_from_act_space(act_space):
    if act_space.__class__.__name__ == 'Discrete':
        act_shape = 1
    elif act_space.__class__.__name__ == "MultiDiscrete":
        act_shape = act_space.shape
    elif act_space.__class__.__name__ == "Box":
        act_shape = act_space.shape[0]
    elif act_space.__class__.__name__ == "MultiBinary":
        act_shape = act_space.shape[0]
    else:  # agar
        act_shape = act_space[0].shape[0] + 1
    return act_shape

class SharedReplayBuffer(object):

    """
    Initializes the replay buffer with placeholders for observations, actions, rewards, etc.
    """
    def __init__(self, num_agents, gamma, train_threshold, recurrent_N, hidden_size):
        self.gamma = gamma
        self.num_agents = num_agents
        self.train_threshold = train_threshold

        # Initialize the buffer as list not numpy for supporting various length btw agents
        self.buffer_reset()
        self.advantages = [list() for _ in range(num_agents)]
        self.returns = [list() for _ in range(num_agents)]

        self.rnn_states = [[torch.zeros((recurrent_N, hidden_size), dtype=torch.float32)] for _ in range(num_agents)]
         
        self.rnn_states_critic = [[torch.zeros((recurrent_N, hidden_size), dtype=torch.float32)] for _ in range(num_agents)]

        self.buffer_index = [-1 for _ in range(self.num_agents)]

    def buffer_reset(self):
        # Initialize the buffer as list not numpy for supporting various length btw agents
        self.share_obs = [list() for _ in range(self.num_agents)]
        self.obs = [list() for _ in range(self.num_agents)]
        self.value_preds = [list() for _ in range(self.num_agents)]
        self.done = [list() for _ in range(self.num_agents)]
        self.actions = [list() for _ in range(self.num_agents)]
        self.action_masks = [list() for _ in range(self.num_agents)]
        self.action_log_probs = [list() for _ in range(self.num_agents)]
        self.rewards = [list() for _ in range(self.num_agents)]

    def check_train_ready(self):
        total_data_num = sum(self.buffer_index)
        return total_data_num >= self.train_threshold

    """Inserts a new transition into the replay buffer."""
    def insert(self, agent_id, share_obs, obs, rnn_states_actor, rnn_states_critic, actions, action_log_probs,
               value_preds, rewards, action_masks=None):
        self.share_obs[agent_id].append(share_obs.copy())
        self.obs[agent_id].append(obs.copy())
        self.rnn_states[agent_id].append(rnn_states_actor.clone().detach())
        self.rnn_states_critic[agent_id].append(rnn_states_critic.clone().detach())
        self.value_preds[agent_id].append(value_preds.clone().detach())
        self.actions[agent_id].append(actions.clone().detach())
        self.action_log_probs[agent_id].append(action_log_probs.clone().detach())
        self.action_masks[agent_id].append(action_masks.copy())
        if self.buffer_index[agent_id] >= 0:
            self.rewards[agent_id].append(rewards)
        self.buffer_index[agent_id] = self.buffer_index[agent_id] + 1

    """Updates the buffer after policy optimization to maintain continuity."""
    def after_update(self):
        self.buffer_reset()
        self.rnn_states = [[self.rnn_states[i][-1].clone()] for i in range(self.num_agents)]
        self.rnn_states_critic = [[self.rnn_states_critic[i][-1].clone()] for i in range(self.num_agents)]
        self.buffer_index = [-1 for _ in range(self.num_agents)]

    """Computes the discounted returns using the given next value."""
    def compute_returns(self, next_value):
        for agent_id in range(self.num_agents):
            last_advantage = 0
            self.value_preds[agent_id][-1] = next_value[agent_id]
            self.advantages[agent_id] = np.array([0.0 for _ in range(len(self.rewards[agent_id]))])
            for step in reversed(range(len(self.rewards[agent_id]))):
                delta = (
                    self.rewards[agent_id][step]
                    + self.gamma * self.value_preds[agent_id][step + 1]
                    - self.value_preds[agent_id][step]
                )
                self.advantages[agent_id][step] = last_advantage = (
                    delta + self.gamma * 0.95 * last_advantage
                )
            mean_adv = np.mean(self.advantages[agent_id])
            std_adv = np.std(self.advantages[agent_id]) + 1e-5 
            self.advantages[agent_id] = (np.array(self.advantages[agent_id]) - mean_adv) / std_adv
            self.returns[agent_id] = np.reshape(self.advantages[agent_id], (-1,1)) + np.array(self.value_preds[agent_id][:-1])
        
    """Generates mini-batches for training using recurrent states."""
    def recurrent_generator(self, num_mini_batch, data_chunk_length):
        batch_size = self.train_threshold
        data_chunks = batch_size // data_chunk_length  # [C = r*T*M/L]
        mini_batch_size = data_chunks // num_mini_batch
        rand = torch.randperm(data_chunks)
        sampler = [rand[i * mini_batch_size:(i + 1) * mini_batch_size] for i in range(num_mini_batch)]

        share_obs = _cast(self.share_obs, -1)
        obs = _cast(self.obs, -1)
        actions = _cast(self.actions, -1)
        action_log_probs = _cast(self.action_log_probs, -1)
        advantages = _cast(self.advantages, 0)
        value_preds = _cast(self.value_preds, -1)
        returns = _cast(self.returns, 0)
        action_masks = _cast(self.action_masks, -1)
        rnn_states = _cast(self.rnn_states, -2)
        rnn_states = rnn_states.view(1, batch_size, *rnn_states.shape[1:])
        rnn_states_critic = _cast(self.rnn_states_critic, -2)
        rnn_states_critic = rnn_states_critic.view(1, batch_size, *rnn_states_critic.shape[1:])

        for indices in sampler:
            share_obs_batch, obs_batch, rnn_states_batch, rnn_states_critic_batch = [], [], [], []
            actions_batch, action_masks_batch, value_preds_batch, return_batch = [], [], [], []
            old_action_log_probs_batch, adv_targ = [], []

            for index in indices:
                ind = index * data_chunk_length
                # size [T+1 N M Dim]-->[T N M Dim]-->[N,M,T,Dim]-->[N*M*T,Dim]-->[L,Dim]
                share_obs_batch.append(share_obs[ind:ind + data_chunk_length])
                obs_batch.append(obs[ind:ind + data_chunk_length])
                actions_batch.append(actions[ind:ind + data_chunk_length])
                action_masks_batch.append(action_masks[ind:ind + data_chunk_length])
                value_preds_batch.append(value_preds[ind:ind + data_chunk_length])
                return_batch.append(returns[ind:ind + data_chunk_length])
                old_action_log_probs_batch.append(action_log_probs[ind:ind + data_chunk_length])
                adv_targ.append(advantages[ind:ind + data_chunk_length])
                # size [T+1 N M Dim]-->[T N M Dim]-->[N M T Dim]-->[N*M*T,Dim]-->[1,Dim]
                rnn_states_batch.append(rnn_states[:, ind])
                rnn_states_critic_batch.append(rnn_states_critic[:, ind])

            L, N = data_chunk_length, mini_batch_size

            share_obs_batch = torch.stack(share_obs_batch, dim=1).reshape(L * N, -1)
            obs_batch = torch.stack(obs_batch, dim=1).reshape(L * N, -1)
            actions_batch = torch.stack(actions_batch, dim=1).reshape(L * N, -1)
            action_masks_batch = torch.stack(action_masks_batch, dim=1).reshape(L * N, -1)
            value_preds_batch = torch.stack(value_preds_batch, dim=1).reshape(L * N, -1)
            return_batch = torch.stack(return_batch, dim=1).reshape(L * N, -1)
            old_action_log_probs_batch = torch.stack(old_action_log_probs_batch, dim=1).reshape(L * N, -1)
            adv_targ = torch.stack(adv_targ, dim=1).reshape(L * N, -1)
            rnn_states_batch = torch.stack(rnn_states_batch, dim=1).contiguous()
            rnn_states_critic_batch = torch.stack(rnn_states_critic_batch, dim=1).contiguous()
            rnn_states_batch = rnn_states_batch[:, :1, :]
            rnn_states_critic_batch = rnn_states_critic_batch[:, :1, :]

            yield share_obs_batch, obs_batch, rnn_states_batch, rnn_states_critic_batch, \
                  actions_batch, value_preds_batch, return_batch, \
                  old_action_log_probs_batch, adv_targ, action_masks_batch
