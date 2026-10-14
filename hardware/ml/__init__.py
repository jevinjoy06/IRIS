"""IRIS keyword spotter ML pipeline."""

from .features import extract_features
from .dataset import load_dataset, download_dataset
from .model import KeywordMLP
