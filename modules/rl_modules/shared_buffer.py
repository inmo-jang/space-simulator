import torch
import numpy as np
import torch.nn.functional as F
from modules.utils import config
from threading import Lock

# The following code is modified from https://github.com/marlbenchmark/on-policy/
# It implements a replay buffer for multi-agent reinforcement learning (MARL).

lock = Lock()

def _remove_last_data(x, last_index):
    if last_index < 0:
        x = [sublist[:last_index] for sublist in x if len(sublist) > abs(last_index)]
    else:
        x = [sublist if len(sublist) > abs(last_index) else list() for sublist in x]
    return x

"""Reshapes the input tensor x to be one-dimensional over the first axis."""
def _cast(x, last_index, max_timesteps, pad_value = 0.0):
    x = _remove_last_data(x, last_index)
    if isinstance(x[0][0], torch.Tensor): 
        x = [torch.stack(sublist + [torch.full_like(sublist[0], pad_value) for _ in range(max_timesteps - len(sublist))])
             if len(sublist) < max_timesteps else torch.stack(sublist) for sublist in x]
        x = torch.stack(x)  # (num_agents, max_timesteps, feature_dim)
    else:
        if isinstance(x[0], list):
            x = [sublist + [[pad_value] * len(sublist[0])] * (max_timesteps - len(sublist)) 
                 if len(sublist) < max_timesteps else sublist for sublist in x]
        elif isinstance(x[0], np.ndarray):
            if len(x[0].shape) == 1:
                x = [np.concatenate([sublist, np.full((max_timesteps - sublist.shape[0]), pad_value)]) 
                     if sublist.shape[0] < max_timesteps else sublist for sublist in x]
            else:
                x = [np.concatenate([sublist, np.full((max_timesteps - sublist.shape[0], sublist.shape[1]), pad_value)])
                        if sublist.shape[0] < max_timesteps else sublist for sublist in x]
        x = torch.tensor(np.array(x, dtype=np.float32))  # (num_agents, max_timesteps, feature_dim)

    if 2 <= len(x.shape) < 3:
        x = x.reshape(x.shape[0], x.shape[1], 1)
    return x.transpose(1,0)

def pad_hidden_state(hidden_states, last_index, recurrent_N, max_batch_size, pad_value=0.0):
    hidden_states = _remove_last_data(hidden_states, last_index)

    hidden_dim = hidden_states[0][0].shape[1]
    for agent_id, agent_states in enumerate(hidden_states):  
        pad = [torch.full((recurrent_N, hidden_dim), pad_value) for _ in range(max_batch_size - len(agent_states))]
        hidden_states[agent_id] = torch.stack(agent_states + pad)
    return torch.stack(hidden_states, dim=0).transpose(1,0)

class SharedReplayBuffer(object):

    """
    Initializes the replay buffer with placeholders for observations, actions, rewards, etc.
    """
    def __init__(self, num_agents, gamma, train_threshold, recurrent_N, hidden_size):
        self.gamma = gamma
        self.num_agents = num_agents
        self.train_threshold = train_threshold
        self.recurrent_N = recurrent_N
        self.hidden_size = hidden_size

        # Initialize the buffer as list not numpy for supporting various length btw agents
        self.buffer_reset()

        self.rnn_states = [[torch.zeros((recurrent_N, hidden_size), dtype=torch.float32)] for _ in range(num_agents)]
         
        self.rnn_states_critic = [[torch.zeros((recurrent_N, hidden_size), dtype=torch.float32)] for _ in range(num_agents)]


    def buffer_reset(self):
        # Initialize the buffer as list not numpy for supporting various length btw agents
        with lock:
            self.done = [True for _ in range(self.num_agents)]
            self.share_obs = [list() for _ in range(self.num_agents)]
            self.obs = [list() for _ in range(self.num_agents)]
            self.value_preds = [list() for _ in range(self.num_agents)]
            self.done = [list() for _ in range(self.num_agents)]
            self.actions = [list() for _ in range(self.num_agents)]
            self.action_masks = [list() for _ in range(self.num_agents)]
            self.action_log_probs = [list() for _ in range(self.num_agents)]
            self.rewards = [list() for _ in range(self.num_agents)]
            self.advantages = [list() for _ in range(self.num_agents)]
            self.returns = [list() for _ in range(self.num_agents)]

    def check_train_ready(self):
        return True in [len(self.rewards[agent_id])>=self.train_threshold for agent_id in range(self.num_agents)]
        #total_data_num = sum(len(self.rewards[agent_id]) for agent_id in range(self.num_agents))
        #return total_data_num >= self.train_threshold

    def rnn_reset(self):
        for agent in range(self.num_agents):
            self.rnn_states[agent][-1] = torch.zeros((self.recurrent_N, self.hidden_size), dtype=torch.float32)
            self.rnn_states_critic[agent][-1] = torch.zeros((self.recurrent_N, self.hidden_size), dtype=torch.float32)

    """Inserts a new transition into the replay buffer."""
    def insert(self, agent_id, share_obs, obs, rnn_states_actor, rnn_states_critic, actions, action_log_probs,
               value_preds, rewards, action_masks=None):
        with lock:
            self.share_obs[agent_id].append(share_obs.copy())
            self.obs[agent_id].append(obs.copy())
            self.rnn_states[agent_id].append(rnn_states_actor.clone().detach())
            self.rnn_states_critic[agent_id].append(rnn_states_critic.clone().detach())
            self.value_preds[agent_id].append(value_preds.clone().detach())
            self.actions[agent_id].append(actions.clone().detach())
            self.action_log_probs[agent_id].append(action_log_probs.clone().detach())
            self.action_masks[agent_id].append(action_masks.copy())
            if self.done[agent_id] is False:
                self.rewards[agent_id].append(rewards)
            else:
                self.done[agent_id] = False

    """Updates the buffer after policy optimization to maintain continuity."""
    def after_update(self):
        self.buffer_reset()
        self.rnn_states = [[self.rnn_states[i][-1].clone().detach()] for i in range(self.num_agents)]
        self.rnn_states_critic = [[self.rnn_states_critic[i][-1].clone().detach()] for i in range(self.num_agents)]

    """Computes the discounted returns using the given next value."""
    def compute_returns(self, next_value):
        for agent_id in range(self.num_agents):
            if len(self.rewards[agent_id]) <= 0:
                continue
            last_advantage = 0
            if len(self.rewards[agent_id]) == len(self.value_preds[agent_id]):
                self.value_preds[agent_id].append(next_value[agent_id])
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
        all_advantages = np.concatenate([self.advantages[agent_id] for agent_id in range(self.num_agents)])
        mean_adv = np.mean(all_advantages)
        std_adv = np.std(all_advantages) + 1e-8

        for agent_id in range(self.num_agents):
            self.advantages[agent_id] = (np.array(self.advantages[agent_id]) - mean_adv) / std_adv
            self.returns[agent_id] = np.reshape(self.advantages[agent_id], (-1,1)) + np.array(self.value_preds[agent_id][:-1])

    """Generates mini-batches for training using recurrent states."""
    def recurrent_generator(self, num_mini_batch, data_chunk_length):
        batch_size = self.train_threshold
        data_chunks = batch_size // data_chunk_length  # [C = r*T*M/L]
        mini_batch_size = data_chunks // num_mini_batch
        rand = torch.arange(data_chunks)
        sampler = [rand[i * mini_batch_size:(i + 1) * mini_batch_size] for i in range(num_mini_batch)]

        valid_mask = [[1 if index <= len(agent_data) else 0 for index in range(self.train_threshold)] for agent_data in self.advantages]
        valid_mask = _cast(valid_mask, 0, self.train_threshold)
        share_obs = _cast(self.share_obs, -1, self.train_threshold)
        obs = _cast(self.obs, -1, self.train_threshold)
        actions = _cast(self.actions, -1, self.train_threshold)
        action_log_probs = _cast(self.action_log_probs, -1, self.train_threshold)
        advantages = _cast(self.advantages, 0, self.train_threshold)
        value_preds = _cast(self.value_preds, -1, self.train_threshold)
        returns = _cast(self.returns, 0, self.train_threshold)
        action_masks = _cast(self.action_masks, -1, self.train_threshold)
        rnn_states = pad_hidden_state(self.rnn_states, -2, self.recurrent_N, self.train_threshold, 0.0)
        rnn_states_critic = pad_hidden_state(self.rnn_states_critic, -2, self.recurrent_N, self.train_threshold, 0.0)

        print(share_obs.shape, obs.shape, actions.shape, action_log_probs.shape, advantages.shape, value_preds.shape, returns.shape, action_masks.shape, rnn_states.shape, rnn_states_critic.shape)

        for indices in sampler:
            valid_mask_batch = []
            share_obs_batch, obs_batch, rnn_states_batch, rnn_states_critic_batch = [], [], [], []
            actions_batch, action_masks_batch, value_preds_batch, return_batch = [], [], [], []
            old_action_log_probs_batch, adv_targ = [], []

            for index in indices:
                ind = index * data_chunk_length
                # size [T+1 N M Dim]-->[T N M Dim]-->[N,M,T,Dim]-->[N*M*T,Dim]-->[L,Dim]
                valid_mask_batch.append(valid_mask[ind:ind + data_chunk_length])
                share_obs_batch.append(share_obs[ind:ind + data_chunk_length])
                obs_batch.append(obs[ind:ind + data_chunk_length])
                actions_batch.append(actions[ind:ind + data_chunk_length])
                action_masks_batch.append(action_masks[ind:ind + data_chunk_length])
                value_preds_batch.append(value_preds[ind:ind + data_chunk_length])
                return_batch.append(returns[ind:ind + data_chunk_length])
                old_action_log_probs_batch.append(action_log_probs[ind:ind + data_chunk_length])
                adv_targ.append(advantages[ind:ind + data_chunk_length])
                # size [T+1 N M Dim]-->[T N M Dim]-->[N M T Dim]-->[N*M*T,Dim]-->[1,Dim]
                rnn_states_batch.append(rnn_states[ind])
                rnn_states_critic_batch.append(rnn_states_critic[ind])

            L, N = data_chunk_length, mini_batch_size
            
            valid_mask_batch = torch.stack(valid_mask_batch, dim=1).reshape(self.num_agents, L * N, -1)
            share_obs_batch = torch.stack(share_obs_batch, dim=1).reshape(self.num_agents, L * N, -1)
            obs_batch = torch.stack(obs_batch, dim=1).reshape(self.num_agents, L * N, -1)
            actions_batch = torch.stack(actions_batch, dim=1).reshape(self.num_agents, L * N, -1)
            action_masks_batch = torch.stack(action_masks_batch, dim=1).reshape(self.num_agents, L * N, -1)
            value_preds_batch = torch.stack(value_preds_batch, dim=1).reshape(self.num_agents, L * N, -1)
            return_batch = torch.stack(return_batch, dim=1).reshape(self.num_agents, L * N, -1)
            old_action_log_probs_batch = torch.stack(old_action_log_probs_batch, dim=1).reshape(self.num_agents, L * N, -1)
            adv_targ = torch.stack(adv_targ, dim=1).reshape(self.num_agents, L * N, -1)
            rnn_states_batch = torch.stack(rnn_states_batch, dim=1).contiguous().reshape(self.num_agents, N, *rnn_states_batch[0][0].shape[1:])
            rnn_states_critic_batch = torch.stack(rnn_states_critic_batch, dim=1).contiguous().reshape(self.num_agents, N, *rnn_states_critic_batch[0][0].shape[1:])

            yield valid_mask_batch, share_obs_batch, obs_batch, rnn_states_batch, rnn_states_critic_batch, \
                  actions_batch, value_preds_batch, return_batch, \
                  old_action_log_probs_batch, adv_targ, action_masks_batch
