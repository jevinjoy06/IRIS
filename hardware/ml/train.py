"""Training script for keyword spotter MLP."""

import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path
import sys

from model import KeywordMLP
from dataset import load_dataset


def train_epoch(model, train_loader, criterion, optimizer, device):
    """
    Train for one epoch.

    Returns:
        average loss
    """
    model.train()
    total_loss = 0.0
    for batch_idx, (X, y) in enumerate(train_loader):
        X, y = X.to(device), y.to(device)

        optimizer.zero_grad()
        logits = model(X)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

    return total_loss / len(train_loader)


def eval_epoch(model, val_loader, device):
    """
    Evaluate on validation set.

    Returns:
        accuracy (0.0 to 1.0)
    """
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for X, y in val_loader:
            X, y = X.to(device), y.to(device)
            logits = model(X)
            predictions = logits.argmax(dim=1)
            correct += (predictions == y).sum().item()
            total += y.size(0)

    return correct / total if total > 0 else 0.0


def main():
    parser = argparse.ArgumentParser(description="Train keyword spotter MLP")
    parser.add_argument("--keyword", type=str, default="yes",
                        help="Keyword to detect (default: yes)")
    parser.add_argument("--epochs", type=int, default=30,
                        help="Number of epochs (default: 30)")
    parser.add_argument("--lr", type=float, default=0.001,
                        help="Learning rate (default: 0.001)")
    parser.add_argument("--batch", type=int, default=64,
                        help="Batch size (default: 64)")
    parser.add_argument("--output", type=str, default="hardware/ml/weights.pt",
                        help="Output path for model (default: hardware/ml/weights.pt)")
    args = parser.parse_args()

    # Determine device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # Load dataset
    print(f"\nLoading dataset for keyword: {args.keyword}")
    X_train, y_train, X_val, y_val = load_dataset(keyword=args.keyword)

    # Create PyTorch datasets
    train_dataset = torch.utils.data.TensorDataset(
        torch.from_numpy(X_train).float(),
        torch.from_numpy(y_train).long()
    )
    val_dataset = torch.utils.data.TensorDataset(
        torch.from_numpy(X_val).float(),
        torch.from_numpy(y_val).long()
    )

    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=args.batch, shuffle=True
    )
    val_loader = torch.utils.data.DataLoader(
        val_dataset, batch_size=args.batch, shuffle=False
    )

    # Create model
    model = KeywordMLP(in_features=40, hidden=64, classes=2).to(device)
    print(f"Model: {model}")

    # Loss and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    # Training loop
    print(f"\nTraining for {args.epochs} epochs...")
    best_val_acc = 0.0
    best_model_state = None

    for epoch in range(args.epochs):
        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        val_acc = eval_epoch(model, val_loader, device)

        print(f"Epoch {epoch + 1:3d}/{args.epochs}: loss={train_loss:.4f}, val_acc={val_acc:.4f}")

        # Save best model
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_model_state = model.state_dict().copy()

    # Load and save best model
    if best_model_state is not None:
        model.load_state_dict(best_model_state)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), output_path)
    print(f"\nBest model saved to {output_path}")
    print(f"Final validation accuracy: {best_val_acc:.4f}")


if __name__ == "__main__":
    main()
