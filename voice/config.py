"""Load voice/config.json and configure environment."""
import json
import os
from pathlib import Path


def load_config() -> dict:
    cfg_path = Path(__file__).parent / "config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(
            "voice/config.json not found — copy config.json.template and fill in your keys."
        )
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    os.environ.setdefault("KERAS_BACKEND", cfg.get("keras_backend", "torch"))
    return cfg
