import torch
import torch.nn as nn

class PopArt(nn.Module):
    def __init__(self, input_dim, output_dim, beta=0.999, epsilon=1e-5, device='cpu'):
        super(PopArt, self).__init__()
        self.beta = beta
        self.epsilon = epsilon
        self.device = device

        self.mean = torch.zeros(output_dim, device=device)
        self.var = torch.ones(output_dim, device=device)
        self.std = torch.ones(output_dim, device=device)

        self.linear = nn.Linear(input_dim, output_dim).to(device)

    def forward(self, x):
        output = self.linear(x)
        normalized_output = (output - self.mean) / self.std
        return normalized_output

    def denormalize(self, normalized_output):
        return normalized_output * self.std + self.mean

    def update(self, target_values):
        new_mean = self.beta * self.mean + (1 - self.beta) * target_values.mean()
        new_var = self.beta * self.var + (1 - self.beta) * target_values.var()
        
        old_std = self.std.clone()
        new_std = torch.sqrt(new_var + self.epsilon)

        self.mean = new_mean
        self.var = new_var
        self.std = new_std

        # Update weights and bias
        with torch.no_grad():
            self.linear.weight.data = self.linear.weight.data * old_std / new_std
            self.linear.bias.data = (self.linear.bias.data - new_mean) * old_std / new_std + new_mean

    def to(self, device):
        self.device = device
        self.mean = self.mean.to(device)
        self.var = self.var.to(device)
        self.std = self.std.to(device)
        self.linear = self.linear.to(device)
        return super().to(device)