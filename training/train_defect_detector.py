"""Train a small defect-detection CNN on synthetic data (CPU, a few minutes).

This is a demo-scale baseline, not a production model: 64x64 grayscale
patches, two conv layers, binary clean/defective labels. It exists to show
the training path end to end and to give the classical detector a learned
counterpart to compare against. No SOTA claims; check the printed
validation accuracy for what it is.

Run: python training/train_defect_detector.py [--epochs N] [--samples N]
Saves: training/defect_cnn.pt
"""
import argparse
import os

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split

SIZE = 64


def make_patch(rng, defective: bool) -> np.ndarray:
    img = np.full((SIZE, SIZE), 200, dtype=np.uint8)
    noise = rng.integers(-12, 13, size=(SIZE, SIZE)).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    if defective:
        kind = rng.integers(0, 3)
        if kind == 0:  # scratch
            x1, y1 = int(rng.integers(5, 25)), int(rng.integers(5, 59))
            x2, y2 = int(rng.integers(40, 59)), int(rng.integers(5, 59))
            cv2.line(img, (x1, y1), (x2, y2), 60, 2)
        elif kind == 1:  # dent
            cv2.ellipse(img, (32, 32),
                        (int(rng.integers(10, 20)), int(rng.integers(6, 12))),
                        int(rng.integers(0, 180)), 0, 360, 80, -1)
        else:  # spots
            for _ in range(int(rng.integers(2, 5))):
                cv2.circle(img, (int(rng.integers(8, 56)),
                                 int(rng.integers(8, 56))),
                           int(rng.integers(2, 5)), 60, -1)
    return img


class DefectCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, 16, 5, padding=2), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 5, padding=2), nn.ReLU(), nn.MaxPool2d(2),
            nn.Flatten(),
            nn.Linear(32 * 16 * 16, 64), nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(1)


def build_dataset(n: int, seed: int = 7):
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for i in range(n):
        defective = (i % 2 == 1)
        xs.append(make_patch(rng, defective))
        ys.append(1.0 if defective else 0.0)
    x = torch.tensor(np.stack(xs), dtype=torch.float32).unsqueeze(1) / 255.0
    y = torch.tensor(ys, dtype=torch.float32)
    return TensorDataset(x, y)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--samples", type=int, default=1000)
    p.add_argument("--batch", type=int, default=32)
    a = p.parse_args()

    torch.manual_seed(7)
    ds = build_dataset(a.samples)
    n_val = a.samples // 5
    train_ds, val_ds = random_split(ds, [a.samples - n_val, n_val])
    train_dl = DataLoader(train_ds, batch_size=a.batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=256)

    model = DefectCNN()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCEWithLogitsLoss()

    for epoch in range(a.epochs):
        model.train()
        total, correct, loss_sum = 0, 0, 0.0
        for xb, yb in train_dl:
            opt.zero_grad()
            out = model(xb)
            loss = loss_fn(out, yb)
            loss.backward()
            opt.step()
            loss_sum += loss.item() * len(xb)
            correct += ((out > 0).float() == yb).sum().item()
            total += len(xb)
        model.eval()
        v_total, v_correct = 0, 0
        with torch.no_grad():
            for xb, yb in val_dl:
                out = model(xb)
                v_correct += ((out > 0).float() == yb).sum().item()
                v_total += len(xb)
        print(f"epoch {epoch + 1}/{a.epochs} "
              f"train_loss={loss_sum / total:.4f} "
              f"train_acc={correct / total:.3f} "
              f"val_acc={v_correct / v_total:.3f}")

    os.makedirs("training", exist_ok=True)
    torch.save(model.state_dict(), "training/defect_cnn.pt")
    print("saved training/defect_cnn.pt")


if __name__ == "__main__":
    main()
