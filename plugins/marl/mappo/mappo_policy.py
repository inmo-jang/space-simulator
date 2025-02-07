import torch
import torch.nn as nn
import torch.optim as optim
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
import numpy as np
from plugins.marl.mappo.actor_critic import Actor, Critic
from modules.separated_buffer import SeparateReplayBuffer
from modules.utils import config
import matplotlib.pyplot as plt
import wandb
import math

# MAPPOPolicy class encapsulates the MAPPO algorithm for training an agent with a shared policy
# The code is based on the MAPPO implementation from the repository: https://github.com/marlbenchmark/on-policy/

mappo_config = config['decision_making']['MAPPO']

if mappo_config['wandb'] is True:
    wandb.init(project="Space_MAPPO", name="Space_MAPPO_run")

class MAPPOPolicy:

    """Initialize the MAPPO policy with agent-specific configuration."""
    def __init__(self, agent):
        self.agent = agent
        self.device = torch.device(mappo_config['device'])

        self.clip_param = mappo_config['clip_param']
        self.ppo_epoch = mappo_config['ppo_epoch']
        self.num_mini_batch = mappo_config['num_mini_batch']
        self.value_loss_coef = mappo_config['value_loss_coef']
        self.entropy_coef = mappo_config['entropy_coef']
        self.max_grad_norm = mappo_config['max_grad_norm']

        self.learning_rate = mappo_config['lr']
        self.critic_lr = mappo_config['critic_lr']
        self.epsilon = mappo_config['epsilon']
        self.weight_decay = mappo_config['weight_decay']
        self.hidden_size = mappo_config['hidden_size']
        self.layer_N = mappo_config['layer_N']
        self.recurrent_N = mappo_config['recurrent_N']
        self.gamma = mappo_config['gamma']
        self.num_mini_batch = mappo_config['num_mini_batch']
        self.data_chunk_length = mappo_config['data_chunk_length']
        self.episode_length = mappo_config['episode_length']
        self.save_path = mappo_config['save_path']
        if 'load_path' in mappo_config.keys():
            self.load_path = mappo_config['load_path']
        else:
            self.load_path = None

        self.inited = False
       
    """Initialize components of the MAPPO agent. This is for initialization after other instances initialized."""
    def init(self):
        self.local_observation_space = self.agent.rl_agent.local_observation_space
        self.global_observation_space = self.agent.rl_agent.global_observation_space
        self.action_space = self.agent.rl_agent.action_space
        self.buffer = SeparateReplayBuffer(self.episode_length, self.local_observation_space, self.global_observation_space, self.action_space, self.hidden_size, self.recurrent_N, self.gamma)

        self.actor = Actor(self.hidden_size, self.layer_N, self.recurrent_N, self.local_observation_space, self.action_space, self.device)
        self.critic = Critic(self.hidden_size, self.layer_N, self.recurrent_N, self.global_observation_space, self.device)
        
        self.actor = DDP(self.actor)
        self.critic = DDP(self.critic)

        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(),
                                                lr=self.learning_rate, eps=self.epsilon,
                                                weight_decay=self.weight_decay)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(),
                                                 lr=self.critic_lr,
                                                 eps=self.epsilon,
                                                 weight_decay=self.weight_decay)

        # load parameters
        if self.load_path is not None:
            checkpoint = torch.load(self.load_path)
            self.actor.load_state_dict(checkpoint['actor_state_dict'])
            self.critic.load_state_dict(checkpoint['critic_state_dict'])
            self.actor_optimizer.load_state_dict(checkpoint['optimizer_actor_state_dict'])
            self.critic_optimizer.load_state_dict(checkpoint['optimizer_critic_state_dict'])

        self.inited = True

        self.step = 0


    """Calculate returns for the collected data."""
    @torch.no_grad()
    def compute(self):
        self.prep_rollout()
        next_values = self.get_value(self.buffer.share_obs[-1],
                                      self.buffer.available_actions[-1])
        self.buffer.compute_returns(next_values[0])
       
    """Insert data into the replay buffer."""
    def insert(self, data):
        obs, share_obs, rewards, available_actions, \
        values, actions, action_log_probs, rnn_states, rnn_states_critic = data
        #rnn_states = np.array(rnn_states)
        #rnn_states_critic = np.array(rnn_states_critic)
        actions = np.array(actions)
        action_log_probs = np.array(action_log_probs)
        values = np.array(values)
        action_masks = np.array([1 if len(available_actions) > i else 0 for i in range(self.action_space.n-1)])
        action_masks = np.insert(action_masks, 0, 1)

        self.buffer.insert(share_obs, obs, rnn_states, rnn_states_critic,
                           actions, action_log_probs, values, rewards, action_masks)

    """Prepare for training phase (set networks to train mode)."""
    def prep_training(self):
        self.actor.train()
        self.critic.train()

    """Prepare for rollout phase (set networks to evaluation mode)."""
    def prep_rollout(self):
        self.actor.eval()
        self.critic.eval()

    """Evaluate actions taken by the agent, calculate log probabilities and value."""
    def evaluate_actions(self, cent_obs, obs, rnn_states_actor, rnn_states_critic, action, 
                         available_actions=None):
        action_log_probs, dist_entropy = self.actor.module.evaluate_actions(obs,
                                                                     rnn_states_actor,
                                                                     action,
                                                                     available_actions)

        values, _ = self.critic(cent_obs, rnn_states_critic)
        return values, action_log_probs, dist_entropy

    """Compute the gradient norm for gradient clipping."""
    def get_grad_norm(self, it):
        sum_grad = 0
        for x in it:
            if x.grad is None:
                continue
            sum_grad += x.grad.norm() ** 2
        return math.sqrt(sum_grad)

    """Compute mean squared error loss."""
    def mse_loss(self, e):
        return e**2/2

    """Calculate the value loss for critic update."""
    def cal_value_loss(self, values, value_preds_batch, return_batch):
        value_pred_clipped = value_preds_batch + (values - value_preds_batch).clamp(-self.clip_param,
                                                                                        self.clip_param)
        error_clipped = return_batch - value_pred_clipped
        error_original = return_batch - values

        value_loss_clipped = self.mse_loss(error_clipped)
        value_loss_original = self.mse_loss(error_original)

        value_loss = value_loss_original

        value_loss = value_loss.mean()

        return value_loss

    """Perform PPO update for both actor and critic."""
    def ppo_update(self, sample):
        share_obs_batch, obs_batch, rnn_states_batch, rnn_states_critic_batch, actions_batch, \
        value_preds_batch, return_batch, old_action_log_probs_batch, \
        adv_targ, available_actions_batch = sample

        # Reshape to do in a single forward pass for all steps
        values, action_log_probs, dist_entropy = self.evaluate_actions(share_obs_batch,
                                                                       obs_batch,
                                                                       rnn_states_batch,
                                                                       rnn_states_critic_batch,
                                                                       actions_batch,
                                                                       available_actions_batch)

        # actor update
        # Convert tensors (ensure they are detached and on correct device)
        old_action_log_probs_batch = torch.tensor(old_action_log_probs_batch, dtype=torch.float32, device=self.device).detach()
        adv_targ = torch.tensor(adv_targ, dtype=torch.float32, device=self.device).detach()
        
        # Compute importance weights
        imp_weights = torch.exp(torch.clamp(action_log_probs - old_action_log_probs_batch, min=-10, max=10))
        
        # PPO Clipped Surrogate Objective
        surr1 = imp_weights * adv_targ
        surr2 = torch.clamp(imp_weights, 1.0 - self.clip_param, 1.0 + self.clip_param) * adv_targ
        policy_action_loss = -torch.min(surr1, surr2).mean()
        
        # Compute final policy loss
        policy_loss = policy_action_loss - dist_entropy * self.entropy_coef  # Entropy regularization
        
        # Backpropagation
        self.actor_optimizer.zero_grad()
        policy_loss.backward()
        
        # Gradient Clipping
        torch.nn.utils.clip_grad_norm_(self.actor.parameters(), max_norm=0.5)
        
        # Update step
        actor_grad_norm = self.get_grad_norm(self.actor.parameters())
        self.actor_optimizer.step()

        # critic update
        # Convert tensors (ensure they are detached and on correct device)
        value_preds_batch = torch.tensor(value_preds_batch, dtype=torch.float32, device=self.device).detach()
        return_batch = torch.tensor(return_batch, dtype=torch.float32, device=self.device).detach()
        
        # Compute value loss
        value_loss = self.cal_value_loss(values, value_preds_batch, return_batch)
        
        # Backpropagation
        self.critic_optimizer.zero_grad()
        (value_loss * self.value_loss_coef).backward()
        
        # Gradient Clipping
        torch.nn.utils.clip_grad_norm_(self.critic.parameters(), max_norm=0.5)
        
        # Update step
        critic_grad_norm = self.get_grad_norm(self.critic.parameters())
        self.critic_optimizer.step()

        if mappo_config['wandb'] is True:
            wandb.log({
                "Policy Loss": policy_loss.item(),
                "Value Loss": value_loss.item(),
                "Entropy": dist_entropy.mean().item(),
                "Actor Gradient Norm": actor_grad_norm,
                "Critic Gradient Norm": critic_grad_norm
            })

        return value_loss, critic_grad_norm, policy_loss, dist_entropy, actor_grad_norm, imp_weights

    """Train the agent using the PPO update."""
    def train(self):
        advantages = self.buffer.returns[:-1] - self.buffer.value_preds[:-1]
        advantages_copy = advantages.copy()
        mean_advantages = np.nanmean(advantages_copy)
        std_advantages = np.nanstd(advantages_copy)
        advantages = (advantages - mean_advantages) / (std_advantages + 1e-5)

        policy_losses, value_losses, entropies = [], [], []

        for _ in range(self.ppo_epoch):
            data_generator = self.buffer.recurrent_generator(advantages, self.num_mini_batch, self.data_chunk_length)

            for sample in data_generator:
                value_loss, critic_grad_norm, policy_loss, dist_entropy, actor_grad_norm, imp_weights \
                    = self.ppo_update(sample)

                policy_losses.append(policy_loss.item())
                value_losses.append(value_loss.item())
                entropies.append(dist_entropy.mean().item())
                
                if self.agent.agent_id == 0:
                    print(f"Policy Loss: {policy_loss.item()}, Value Loss: {value_loss.item()}, Entropy: {dist_entropy.mean().item()}")

        self.buffer.after_update()

        if self.agent.agent_id == 0 and mappo_config['plot'] is True:
            self.plot_training_stats(policy_losses, value_losses, entropies)

    """Plot training statistics"""
    def plot_training_stats(self, policy_losses, value_losses, entropies):
        fig, axs = plt.subplots(3, 1, figsize=(10, 12))

        axs[0].plot(policy_losses, label="Policy Loss", color='red')
        axs[0].set_title("Policy Loss")
        axs[0].set_xlabel("Iteration")
        axs[0].set_ylabel("Loss")
        axs[0].legend()

        axs[1].plot(value_losses, label="Value Loss", color='blue')
        axs[1].set_title("Value Loss")
        axs[1].set_xlabel("Iteration")
        axs[1].set_ylabel("Loss")
        axs[1].legend()

        axs[2].plot(entropies, label="Entropy", color='green')
        axs[2].set_title("Entropy")
        axs[2].set_xlabel("Iteration")
        axs[2].set_ylabel("Entropy")
        axs[2].legend()

        plt.tight_layout()
        plt.show()

    """Collect actions and values for the agent."""
    @torch.no_grad()
    def collect(self, blackboard):
        available_actions = blackboard['closest_tasks']
        action, action_log_prob, rnn_state = self.get_action(blackboard, available_actions)
        value, rnn_state_critic = self.get_value(blackboard['global_observation'], available_actions)

        return action, action_log_prob, rnn_state, value, rnn_state_critic

    """Save models' parameters."""
    def save_model(self):
        torch.save({
            'actor_state_dict': self.actor.state_dict(),
            'critic_state_dict': self.critic.state_dict(),
            'optimizer_actor_state_dict': self.actor_optimizer.state_dict(),
            'optimizer_critic_state_dict': self.critic_optimizer.state_dict()
            }, self.save_path)

    """Decide on an action based on the current state."""
    def decide(self, blackboard) -> int:
        if self.inited == False:
            self.init()
        action, action_log_prob, rnn_state, value, rnn_state_critic = self.collect(blackboard)
        available_actions = blackboard['closest_tasks']
        if 1 <= action <= len(available_actions):
            selected_task = available_actions[action - 1]
            selected_task_id = selected_task.task_id
        else:
            selected_task_id = None

        data = blackboard['local_observation'], blackboard['global_observation'],\
               blackboard['reward'], available_actions, \
               value, action, action_log_prob, rnn_state, rnn_state_critic

        self.insert(data)
        blackboard['reward'] = 0
        self.step = self.step + 1

        if self.step == self.episode_length:
            self.compute()
            self.prep_training()
            self.train()
            self.prep_rollout()
            self.step = 0
            self.save_model()
        
        return selected_task_id

    """Get action based on the current state and available actions."""
    def get_action(self, blackboard, available_actions):
        action_masks = [1 if len(available_actions) > i else 0 for i in range(self.action_space.n - 1)]
        action_masks = np.insert(action_masks, 0, 1)
        prev_rnn_state = self.buffer.rnn_states[-1]
        action, action_log_prob, rnn_state = self.actor(obs = blackboard['local_observation'],
                                                        rnn_states = prev_rnn_state,
                                                        action_masks = action_masks)
        return action, action_log_prob, rnn_state
        

    def get_value(self, cent_obs, available_actions):
        prev_rnn_state = self.buffer.rnn_states_critic[-1]
        value, rnn_state = self.critic(cent_obs = cent_obs, 
                                rnn_states = prev_rnn_state)
        return value, rnn_state
