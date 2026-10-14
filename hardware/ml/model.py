"""Simple MLP keyword spotter for FPGA deployment."""

import torch
import torch.nn as nn


class KeywordMLP(nn.Module):
    """
    Two-layer MLP for keyword spotting.

    Architecture:
        Input (40) -> Linear(40→64) -> ReLU -> Linear(64→2) -> Output
    """

    def __init__(self, in_features=40, hidden=64, classes=2):
        """
        Initialize the MLP.

        Args:
            in_features: input feature dimension (default 40 for log-mel features)
            hidden: hidden layer size (default 64)
            classes: number of output classes (default 2 for binary classification)
        """
        super().__init__()
        self.fc1 = nn.Linear(in_features, hidden)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(hidden, classes)

    def forward(self, x):
        """
        Forward pass.

        Args:
            x: (batch_size, in_features) input tensor

        Returns:
            (batch_size, classes) logits
        """
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        return x

    def get_weights(self):
        """
        Extract weight matrices for quantization.

        Returns:
            dict: {'w1': (40, 64), 'b1': (64,), 'w2': (64, 2), 'b2': (2,)}
        """
        return {
            'w1': self.fc1.weight.data,  # (64, 40)
            'b1': self.fc1.bias.data,     # (64,)
            'w2': self.fc2.weight.data,   # (2, 64)
            'b2': self.fc2.bias.data,     # (2,)
        }
