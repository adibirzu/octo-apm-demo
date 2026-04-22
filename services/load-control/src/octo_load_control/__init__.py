"""octo-load-control — named workload profile orchestrator."""

from .profiles import PROFILES, Profile, ProfileName
from .runs import Run, RunState

__all__ = ["PROFILES", "Profile", "ProfileName", "Run", "RunState"]
__version__ = "1.0.0"
