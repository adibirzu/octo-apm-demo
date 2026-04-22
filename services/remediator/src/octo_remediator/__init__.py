"""Alarm-driven remediation service.

Receives OCI alarm notifications (webhook) + load-control run events,
matches against a catalog of playbooks, and executes the match —
auto-applied for tier-low actions (cache flush), approval-gated for
tier-high actions (scale a Deployment, restart a pod).
"""

from .playbooks.base import Playbook, RemediationTier, RemediationRun, RemediationState

__all__ = ["Playbook", "RemediationTier", "RemediationRun", "RemediationState"]
__version__ = "1.0.0"
