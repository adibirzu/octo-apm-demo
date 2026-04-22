"""Add project root to sys.path so server module is importable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
