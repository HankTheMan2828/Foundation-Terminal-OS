"""Make the `foundationmedia` package importable during tests without
installing it (mirrors games/conftest.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
