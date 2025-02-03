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
        self.returns = np.zeros_like(self.value_preds)

        self.available_actions = np.ones((self.episode_length + 1, act_space.n),dtype=np.float32)

        act_shape = get_shape_from_act_space(act_space)

        self.actions = np.zeros((self.episode_length, act_shape), dtype=np.float32)
        self.action_log_probs = np.zeros((self.episode_length, act_shape), dtype=np.float32)
        self.rewards = np.zeros((self.episode_length, 1), dtype=np.float32)

        self.buffer_index = 0

    """Inserts a new transition into the replay buffer."""
    def insert(self, share_obs, obs, rnn_states_actor, rnn_states_critic, actions, action_log_probs,
               value_preds, rewards, available_actions=None):

        self.share_obs[self.buffer_index + 1] = share_obs.copy()
        self.obs[self.buffer_index + 1] = obs.copy()
        self.rnn_states[self.buffer_index + 1] = rnn_states_actor.copy()
        self.rnn_states_critic[self.buffer_index + 1] = rnn_states_critic.copy()
        self.actions[self.buffer_index] = actions.copy()
        self.action_log_probs[self.buffer_index] = action_log_probs.copy()
        self.value_preds[self.buffer_index] = value_preds.copy()
        self.rewards[self.buffer_index] = rewards
        self.available_actions[self.buffer_index + 1] = available_actions.copy()
        self.buffer_index = (self.buffer_index + 1) % self.episode_length

    """Updates the buffer after policy optimization to maintain continuity."""
    def after_update(self):
        self.share_obs[0] = self.share_obs[-1].copy()
        self.obs[0] = self.obs[-1].copy()
        self.rnn_states[0] = self.rnn_states[-1].copy()
        self.rnn_states_critic[0] = self.rnn_states_critic[-1].copy()
        self.available_actions[0] = self.available_actions[-1].copy()

    """Computes the discounted returns using the given next value."""
    def compute_returns(self, next_value):
        self.returns[-1] = next_value
        for step in reversed(range(self.rewards.shape[0])):
            self.returns[step] = self.returns[step + 1] * self.gamma + self.rewards[step]

    """Generates mini-batches for training using recurrent states."""
    def recurrent_generator(self, advantages, num_mini_batch, data_chunk_length):
        episode_length = self.rewards.shape[0]
        batch_size = episode_length
        data_chunks = batch_size // data_chunk_length  # [C=r*T*M/L]
        mini_batch_size = data_chunks // num_mini_batch

        rand = torch.randperm(data_chunks).numpy()
        sampler = [rand[i * mini_batch_size:(i + 1) * mini_batch_size] for i in range(num_mini_batch)]

        share_obs = _cast(self.share_obs[:-1])
        obs = _cast(self.obs[:-1])

        actions = _cast(self.actions)
        action_log_probs = _cast(self.action_log_probs)
        advantages = _cast(advantages)
        value_preds = _cast(self.value_preds[:-1])
        returns = _cast(self.returns[:-1])
        rnn_states = self.rnn_states[:-1].reshape(-1, *self.rnn_states.shape[1:])
        rnn_states_critic = self.rnn_states_critic[:-1].reshape(-1,
                                                                *self.rnn_states_critic.shape[1:])

        available_actions = _cast(self.available_actions[:-1])

        for indices in sampler:
            share_obs_batch = []
            obs_batch = []
            rnn_states_batch = []
            rnn_states_critic_batch = []
            actions_batch = []
            available_actions_batch = []
            value_preds_batch = []
            return_batch = []
            old_action_log_probs_batch = []
            adv_targ = []

            for index in indices:
                ind = index * data_chunk_length
                # size [T+1 N M Dim]-->[T N M Dim]-->[N,M,T,Dim]-->[N*M*T,Dim]-->[L,Dim]
                share_obs_batch.append(share_obs[ind:ind + data_chunk_length])
                obs_batch.append(obs[ind:ind + data_chunk_length])
                actions_batch.append(actions[ind:ind + data_chunk_length])
                available_actions_batch.append(available_actions[ind:ind + data_chunk_length])
                value_preds_batch.append(value_preds[ind:ind + data_chunk_length])
                return_batch.append(returns[ind:ind + data_chunk_length])
                old_action_log_probs_batch.append(action_log_probs[ind:ind + data_chunk_length])
                adv_targ.append(advantages[ind:ind + data_chunk_length])
                # size [T+1 N M Dim]-->[T N M Dim]-->[N M T Dim]-->[N*M*T,Dim]-->[1,Dim]
                rnn_states_batch.append(rnn_states[ind])
                rnn_states_critic_batch.append(rnn_states_critic[ind])
            L, N = data_chunk_length, mini_batch_size

            # These are all from_numpys of size (L, N, Dim)           
            share_obs_batch = np.stack(share_obs_batch, axis=1)
            obs_batch = np.stack(obs_batch, axis=1)

            actions_batch = np.stack(actions_batch, axis=1)
            available_actions_batch = np.stack(available_actions_batch, axis=1)
            value_preds_batch = np.stack(value_preds_batch, axis=1)
            return_batch = np.stack(return_batch, axis=1)
            old_action_log_probs_batch = np.stack(old_action_log_probs_batch, axis=1)
            adv_targ = np.stack(adv_targ, axis=1)

            # States is just a (N, -1) from_numpy
            rnn_states_batch = np.stack(rnn_states_batch).reshape(N, *self.rnn_states.shape[1:])
            rnn_states_critic_batch = np.stack(rnn_states_critic_batch).reshape(N, *self.rnn_states_critic.shape[1:])

            # Flatten the (L, N, ...) from_numpys to (L * N, ...)
            share_obs_batch = _flatten(L, N, share_obs_batch)
            obs_batch = _flatten(L, N, obs_batch)
            actions_batch = _flatten(L, N, actions_batch)
            available_actions_batch = _flatten(L, N, available_actions_batch)
            value_preds_batch = _flatten(L, N, value_preds_batch)
            return_batch = _flatten(L, N, return_batch)
            old_action_log_probs_batch = _flatten(L, N, old_action_log_probs_batch)
            adv_targ = _flatten(L, N, adv_targ)

            yield share_obs_batch, obs_batch, rnn_states_batch, rnn_states_critic_batch, actions_batch,\
                  value_preds_batch, return_batch, old_action_log_probs_batch, adv_targ, available_actions_batch

