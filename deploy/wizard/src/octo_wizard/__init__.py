"""Interactive provisioning wizard for octo-apm-demo.

Discovers the operator's tenancy (compartments, regions, OKE clusters,
ATPs, VCNs, OCIR namespaces) and drives the existing deploy/ scripts
based on their answers.
"""

from .discovery import Discovery, TenancyInventory
from .plan import DeploymentPlan, PlanAction

__all__ = ["Discovery", "TenancyInventory", "DeploymentPlan", "PlanAction"]
__version__ = "1.0.0"
