"""Playbook registry.

Each playbook is a single class inheriting :class:`Playbook` with:
- A human-readable name + description.
- A ``matches(alarm)`` predicate that decides if this playbook fires.
- An ``execute(ctx)`` coroutine that actually performs the remediation.
- A ``tier`` class attribute (LOW | MEDIUM | HIGH) that determines
  whether it runs automatically or requires approval.

Adding a playbook: drop a module in this package, export a subclass,
register in :data:`CATALOG` at the bottom of this file.
"""

from typing import Sequence

from .base import Playbook
from .cache_flush import CacheFlushPlaybook
from .restart_deployment import RestartDeploymentPlaybook
from .scale_hpa import ScaleHPAPlaybook

CATALOG: Sequence[Playbook] = (
    CacheFlushPlaybook(),
    ScaleHPAPlaybook(),
    RestartDeploymentPlaybook(),
)


__all__ = ["CATALOG", "Playbook"]
