"""Pytest configuration and shared fixtures."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

WORKTREE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

# Mock hardware dependencies that aren't installed in CI
sys.modules["pyttsx3"] = MagicMock()
sys.modules["webrtcvad"] = MagicMock()
sys.modules["openwakeword"] = MagicMock()
sys.modules["openwakeword.model"] = MagicMock()

from hub import memory


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    memory._DB_PATH = db_path
    memory.init_db()

    yield db_path

    memory._DB_PATH = None

    import time
    time.sleep(0.1)

    if db_path.exists():
        try:
            db_path.unlink()
        except PermissionError:
            pass


@pytest.fixture
def client(temp_db):
    """Create a FastAPI TestClient with a temporary database."""
    from fastapi.testclient import TestClient
    from hub.server import app

    return TestClient(app)
