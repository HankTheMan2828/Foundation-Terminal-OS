"""Make the `foundationhub` package importable during tests without installing it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
