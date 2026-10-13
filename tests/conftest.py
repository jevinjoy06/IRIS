"""Pytest configuration and fixtures for IRIS hub tools tests."""
import sys
from pathlib import Path

# Add worktree root to sys.path for imports
worktree_root = Path(__file__).parent.parent
sys.path.insert(0, str(worktree_root))
