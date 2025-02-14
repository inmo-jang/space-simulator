import torch
import torch.nn as nn
import numpy as np

# The code is based on the MAPPO implementation from the repository: https://github.com/marlbenchmark/on-policy/

actor = None
critic = None
actor_optimizer = None
critic_optimizer = None

def get_models(hidden_size, layer_N, recurrent_N, local_obs_space, global_obs_space, action_space, device, lr, critic_lr, eps, weight_decay):
    global actor, critic, actor_optimizer, critic_optimizer
    if actor is None:
        actor = Actor(hidden_size, layer_N, recurrent_N, local_obs_space, action_space, device)
        critic = Critic(hidden_size, layer_N, recurrent_N, global_obs_space, device)
        actor_optimizer = torch.optim.Adam(actor.parameters(),
                                                lr=lr, eps=eps,
                                                weight_decay=weight_decay)
        critic_optimizer = torch.optim.Adam(critic.parameters(),
                                                 lr=critic_lr,
                                                 eps=eps,
                                                 weight_decay=weight_decay)
    return actor, critic, actor_optimizer, critic_optimizer

def get_shape_from_obs_space(obs_space):
    if obs_space.__class__.__name__ == 'Box':
        obs_shape = obs_space.shape
    elif obs_space.__class__.__name__ == 'list':
        obs_shape = obs_space
    else:
        raise NotImplementedError
    return obs_shape

def init(module, weight_init, bias_init, gain=1):
    weight_init(module.weight.data, gain=gain)
    if module.bias is not None:
        bias_init(module.bias.data)
    return module

class RNNLayer(nn.Module):
    def __init__(self, inputs_dim, outputs_dim, recurrent_N):
        super(RNNLayer, self).__init__()
        self._recurrent_N = recurrent_N
        self.input_dim = inputs_dim

        self.rnn = nn.GRU(inputs_dim, outputs_dim, num_layers=self._recurrent_N)
        for name, param in self.rnn.named_parameters():
            if 'bias' in name:
                nn.init.constant_(param, 0)
            elif 'weight' in name:
                nn.init.orthogonal_(param)
        self.norm = nn.LayerNorm(outputs_dim)

    def forward(self, x, hxs):#, masks):
        if not isinstance(hxs, torch.Tensor):
            hxs = torch.tensor(hxs, dtype=torch.float32, device=x.device)
        if x.dim() == 1:
            x = x.unsqueeze(0)
        if x.size(0) == hxs.size(0):
            x, hxs = self.rnn(x, hxs)
            x = x.squeeze(0)
        else:
            # x is a (T, N, -1) tensor that has been flatten to (T * N, -1)
            N = hxs.size(0)
            T = int(x.size(0) / N)

            # unflatten
            x = x.view(T, N, x.size(1))

            # x is a (T, N, -1) tensor
            hxs = hxs.transpose(1,0)
            rnn_scores, hxs = self.rnn(x, hxs)

            # flatten
            x = rnn_scores.reshape(T * N, -1)
            hxs = hxs.transpose(0, 1)

        x = self.norm(x)
        return x, hxs

class FixedCategorical(torch.distributions.Categorical):
    def sample(self):
        return super().sample().unsqueeze(-1)

    def log_probs(self, actions):
        return (
            super()
            .log_prob(actions.squeeze(-1))
            .view(actions.size(0), -1)
            .sum(-1)
            .unsqueeze(-1)
        )

class Categorical(nn.Module):
    def __init__(self, num_inputs, num_outputs, gain=0.01):
        super(Categorical, self).__init__()
        init_method = nn.init.orthogonal_
        self.linear = init(nn.Linear(num_inputs, num_outputs), init_method, lambda x: nn.init.constant_(x, 0), gain)

    def forward(self, x, action_masks = None):
        x = self.linear(x)
        if action_masks is not None:
            action_masks = torch.as_tensor(action_masks, dtype=torch.bool, device=x.device)
            x = x.masked_fill(action_masks == 0, -1e10)
        return FixedCategorical(logits=x)

class ACTLayer(nn.Module):
    def __init__(self, action_space, inputs_dim):
        super(ACTLayer, self).__init__()
        self.action_type = action_space.__class__.__name__

        action_dim = action_space.n
        self.action_out = Categorical(inputs_dim, action_dim)

    def forward(self, x, action_masks=None):
        action_logits = self.action_out(x, action_masks)
        actions = action_logits.sample()
        action_log_probs = action_logits.log_probs(actions)

        return actions, action_log_probs

    def get_probs(self, x, available_actions=None):
        action_logits = self.action_out(x, available_actions)
        action_probs = torch.softmax(action_logits.logits, dim=-1)

        return action_probs

    def evaluate_actions(self, x, action, action_masks=None):
        action_logits = self.action_out(x, action_masks)
        action_log_probs = action_logits.log_probs(action)
        dist_entropy = action_logits.entropy().mean()

        return action_log_probs, dist_entropy

class MLPBase(nn.Module):
    def __init__(self, hidden_size, obs_shape, layer_N):
        super(MLPBase, self).__init__()
        obs_dim = obs_shape[0]
        self.feature_norm = nn.LayerNorm(obs_dim)
        self.mlp = MLPLayer(obs_dim, hidden_size, layer_N)

    def forward(self, x):
        x = np.array(x, dtype=np.float32)
        x = torch.tensor(x, dtype=torch.float32)
        x = self.feature_norm(x.clone().detach())
        x = self.mlp(x)

        return x

class MLPLayer(nn.Module):
    def __init__(self, input_dim, hidden_size, layer_N):
        super(MLPLayer, self).__init__()
        self._layer_N = layer_N

        active_func = nn.ReLU()
        init_method = nn.init.orthogonal_
        gain = nn.init.calculate_gain('relu')

        def init_(m):
            return init(m, init_method, lambda x: nn.init.constant_(x, 0), gain=gain)

        self.fc1 = nn.Sequential(
            init_(nn.Linear(input_dim, hidden_size)), active_func, nn.LayerNorm(hidden_size))
        self.fc2 = nn.ModuleList([nn.Sequential(init_(
            nn.Linear(hidden_size, hidden_size)), active_func, nn.LayerNorm(hidden_size)) for i in range(self._layer_N)])

    def forward(self, x):
        x = self.fc1(x)
        for i in range(self._layer_N):
            x = self.fc2[i](x)
        return x

class Actor(nn.Module):
    def __init__(self, hidden_size, layer_N, recurrent_N, obs_space, action_space, device=torch.device("cpu")):
        super(Actor, self).__init__()
        self.hidden_size = hidden_size

        obs_shape = get_shape_from_obs_space(obs_space)

        self.base = MLPBase(hidden_size, obs_shape, layer_N)
        self.rnn = RNNLayer(hidden_size, hidden_size, recurrent_N)
        self.act = ACTLayer(action_space, hidden_size)

        self.to(device)

    def forward(self, obs, rnn_states, action_masks):#masks, action_masks):
        actor_features = self.base(obs)
        actor_features, rnn_states = self.rnn(actor_features, rnn_states)#, masks)
        actions, action_log_probs = self.act(actor_features, action_masks)
        return actions, action_log_probs, rnn_states

    def evaluate_actions(self, obs, rnn_states, action, action_masks):#masks, action_masks):
        actor_features = self.base(obs)

        actor_features, rnn_states = self.rnn(actor_features, rnn_states)#, masks)

        action_log_probs, dist_entropy = self.act.evaluate_actions(actor_features, action, action_masks)

        return action_log_probs, dist_entropy


class Critic(nn.Module):
    def __init__(self, hidden_size, layer_N, recurrent_N, cent_obs_space, device=torch.device("cpu")):
        super(Critic, self).__init__()
        init_method = nn.init.orthogonal_

        cent_obs_shape = get_shape_from_obs_space(cent_obs_space)
        self.base = MLPBase(hidden_size, cent_obs_shape, layer_N)

        self.rnn = RNNLayer(hidden_size, hidden_size, recurrent_N)

        self.v_out = init(nn.Linear(hidden_size, 1), init_method, lambda x: nn.init.constant_(x, 0))

        self.to(device)

    def forward(self, cent_obs, rnn_states):#, masks):
        critic_features = self.base(cent_obs)
        critic_features, rnn_states = self.rnn(critic_features, rnn_states)#, masks)
        values = self.v_out(critic_features)

        return values, rnn_states
