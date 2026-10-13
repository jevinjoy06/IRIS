"""Pytest configuration and shared fixtures."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

# Mock hardware dependencies that aren't installed in CI
sys.modules["pyttsx3"] = MagicMock()
sys.modules["webrtcvad"] = MagicMock()
sys.modules["openwakeword"] = MagicMock()
sys.modules["openwakeword.model"] = MagicMock()
