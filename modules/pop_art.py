import torch
import torch.nn as nn

class PopArt(nn.Module):
    def __init__(self, input_dim, output_dim, beta=0.999):
        super(PopArt, self).__init__()
        self.beta = beta  
        self.mean = torch.zeros(output_dim)  
        self.var = torch.ones(output_dim)  
        self.std = torch.ones(output_dim)  

        self.linear = nn.Linear(input_dim, output_dim)

    def forward(self, x):
        output = self.linear(x)
        norm_output = (output - self.mean) / self.std
        return norm_output

    def update(self, target_values):
        new_mean = self.beta * self.mean + (1 - self.beta) * target_values.mean()
        new_var = self.beta * self.var + (1 - self.beta) * target_values.var()

        self.mean = new_mean
        self.var = new_var
        self.std = torch.sqrt(new_var + 1e-5)
