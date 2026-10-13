"""Pytest configuration and fixtures for IRIS Hub tests."""
import sys
import tempfile
from pathlib import Path

import pytest

# Add the worktree root to sys.path so imports work
WORKTREE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

from hub import memory


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Set the memory module to use this temp db
    memory._DB_PATH = db_path
    memory.init_db()

    yield db_path

    # Cleanup - reset the path first so no new connections are made
    memory._DB_PATH = None

    # Wait a moment for any pending connections to close
    import time
    time.sleep(0.1)

    # Try to remove the file
    if db_path.exists():
        try:
            db_path.unlink()
        except PermissionError:
            # If still locked, that's okay - temp file will be cleaned up by OS
            pass


@pytest.fixture
def client(temp_db):
    """Create a FastAPI TestClient with a temporary database."""
    from fastapi.testclient import TestClient
    from hub.server import app

    return TestClient(app)
