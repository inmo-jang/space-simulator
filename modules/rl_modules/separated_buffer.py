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
def _cast(x):
    return x.reshape(-1, *x.shape[1:])

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

class SeparateReplayBuffer(object):

    """
    Initializes the replay buffer with placeholders for observations, actions, rewards, etc.
    """
    def __init__(self, episode_length, obs_space, cent_obs_space, act_space, hidden_size, recurrent_N, gamma):
        self.episode_length = episode_length
        self.hidden_size = hidden_size
        self.recurrent_N = recurrent_N
        self.gamma = gamma

        obs_shape = get_shape_from_obs_space(obs_space)
        share_obs_shape = get_shape_from_obs_space(cent_obs_space)

        if type(obs_shape[-1]) == list:
            obs_shape = obs_shape[:1]

        if type(share_obs_shape[-1]) == list:
            share_obs_shape = share_obs_shape[:1]

        self.share_obs = np.zeros((self.episode_length + 1,*share_obs_shape),
                                  dtype=np.float32)
        self.obs = np.zeros((self.episode_length + 1, *obs_shape), dtype=np.float32)

        self.rnn_states = np.zeros((self.episode_length + 1, self.recurrent_N, self.hidden_size),
                                   dtype=np.float32)
        self.rnn_states_critic = np.zeros_like(self.rnn_states)

        self.value_preds = np.zeros((self.episode_length + 1, 1), dtype=np.float32)


        act_shape = get_shape_from_act_space(act_space)

        self.actions = np.zeros((self.episode_length, act_shape), dtype=np.float32)
        self.action_masks = np.zeros((self.episode_length, act_space.n),dtype=np.float32)
        self.action_log_probs = np.zeros((self.episode_length, act_shape), dtype=np.float32)
        self.rewards = np.zeros((self.episode_length, 1), dtype=np.float32)
        self.advantages = np.zeros_like(self.rewards)
        self.returns = np.zeros_like(self.rewards)

        self.buffer_index = 0

    """Inserts a new transition into the replay buffer."""
    def insert(self, share_obs, obs, rnn_states_actor, rnn_states_critic, actions, action_log_probs,
               value_preds, rewards, action_masks=None):
        self.share_obs[self.buffer_index + 1] = share_obs.copy()
        self.obs[self.buffer_index + 1] = obs.copy()
        self.rnn_states[self.buffer_index + 1] = rnn_states_actor.clone()
        self.rnn_states_critic[self.buffer_index + 1] = rnn_states_critic.clone()
        self.value_preds[self.buffer_index] = value_preds.copy()
        self.actions[self.buffer_index] = actions.copy()
        self.action_log_probs[self.buffer_index] = action_log_probs.copy()
        self.rewards[self.buffer_index] = rewards
        self.action_masks[self.buffer_index] = action_masks.copy()
        self.buffer_index = (self.buffer_index + 1) % self.episode_length

    """Updates the buffer after policy optimization to maintain continuity."""
    def after_update(self):
        self.share_obs[0] = self.share_obs[-1].copy()
        self.obs[0] = self.obs[-1].copy()
        self.rnn_states[0] = self.rnn_states[-1].copy()
        self.rnn_states_critic[0] = self.rnn_states_critic[-1].copy()

    """Computes the discounted returns using the given next value."""
    def compute_returns(self, next_value):
        last_advantage = 0

        for step in reversed(range(self.rewards.shape[0])):
            delta = (
                self.rewards[step]
                + self.gamma * self.value_preds[step + 1]
                - self.value_preds[step]
            )
            self.advantages[step] = last_advantage = (
                delta + self.gamma * 0.95 * last_advantage
            )

        mean_adv = np.mean(self.advantages)
        std_adv = np.std(self.advantages) + 1e-5 
        self.advantages = (self.advantages - mean_adv) / std_adv
        
        self.returns = self.advantages + self.value_preds[:-1]
        
    """Generates mini-batches for training using recurrent states."""
    def recurrent_generator(self, num_mini_batch, data_chunk_length):
        episode_length = self.rewards.shape[0]
        assert episode_length % data_chunk_length == 0, "episode_length should be a multiple of data_chunk_length"
        
        batch_size = episode_length
        data_chunks = batch_size // data_chunk_length  # [C = r*T*M/L]
        mini_batch_size = data_chunks // num_mini_batch

        rand = torch.randperm(data_chunks)
        sampler = [rand[i * mini_batch_size:(i + 1) * mini_batch_size] for i in range(num_mini_batch)]

        share_obs = torch.tensor(self.share_obs[:-1], dtype=torch.float32)
        obs = torch.tensor(self.obs[:-1], dtype=torch.float32)
        actions = torch.tensor(self.actions, dtype=torch.float32)
        action_log_probs = torch.tensor(self.action_log_probs, dtype=torch.float32)
        advantages = torch.tensor(self.advantages, dtype=torch.float32)
        value_preds = torch.tensor(self.value_preds[:-1], dtype=torch.float32)
        returns = torch.tensor(self.returns, dtype=torch.float32)
        rnn_states = torch.tensor(self.rnn_states[:-1], dtype=torch.float32)
        rnn_states_critic = torch.tensor(self.rnn_states_critic[:-1], dtype=torch.float32)
        rnn_states = rnn_states[:-1].reshape(-1, *rnn_states.shape[1:]).detach()
        rnn_states_critic = rnn_states_critic[:-1].reshape(-1, *rnn_states_critic.shape[1:]).detach()
        action_masks = torch.tensor(self.action_masks, dtype=torch.float32)

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
                rnn_states_batch.append(rnn_states[ind])
                rnn_states_critic_batch.append(rnn_states_critic[ind])

            L, N = data_chunk_length, mini_batch_size

            share_obs_batch = torch.stack(share_obs_batch, dim=1).reshape(L * N, -1)
            obs_batch = torch.stack(obs_batch, dim=1).reshape(L * N, -1)
            actions_batch = torch.stack(actions_batch, dim=1).reshape(L * N, -1)
            action_masks_batch = torch.stack(action_masks_batch, dim=1).reshape(L * N, -1)
            value_preds_batch = torch.stack(value_preds_batch, dim=1).reshape(L * N, -1)
            return_batch = torch.stack(return_batch, dim=1).reshape(L * N, -1)
            old_action_log_probs_batch = torch.stack(old_action_log_probs_batch, dim=1).reshape(L * N, -1)
            adv_targ = torch.stack(adv_targ, dim=1).reshape(L * N, -1)
            rnn_states_batch = torch.stack(rnn_states_batch).reshape(N, *self.rnn_states.shape[1:])
            rnn_states_critic_batch = torch.stack(rnn_states_critic_batch).reshape(N, *self.rnn_states_critic.shape[1:])

            yield share_obs_batch, obs_batch, rnn_states_batch, rnn_states_critic_batch, \
                  actions_batch, value_preds_batch, return_batch, \
                  old_action_log_probs_batch, adv_targ, action_masks_batch
