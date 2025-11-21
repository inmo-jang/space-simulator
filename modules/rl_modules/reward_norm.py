class RewardNormalizer:
    def __init__(self, epsilon=1e-8):
        self.mean = 0
        self.var = 1
        self.count = 1
        self.epsilon = epsilon 

    def normalize(self, reward):
        self.mean = 0.99 * self.mean + 0.01 * reward
        self.var = 0.99 * self.var + 0.01 * ((reward - self.mean) ** 2)
        return (reward - self.mean) / (self.var + self.epsilon) ** 0.5