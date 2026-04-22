"""Deployment plan model + rendering.

The wizard asks the operator a handful of questions; those answers
become a ``DeploymentPlan``. The plan is **printable** (shown back
to the operator before any side effect) and **executable** (each
PlanAction maps to one existing deploy-script invocation).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class RuntimeChoice(str, enum.Enum):
    OKE_EXISTING = "oke-existing"
    OKE_NEW = "oke-new"
    VM_EXISTING = "vm-existing"
    VM_NEW = "vm-new"


class DBChoice(str, enum.Enum):
    ATP_EXISTING = "atp-existing"
    ATP_NEW = "atp-new"
    POSTGRES_DEV = "postgres-dev"


@dataclass
class PlanAction:
    kind: str                # "script" | "terraform" | "kubectl"
    command: str
    description: str
    requires_confirmation: bool = False
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class DeploymentPlan:
    runtime: RuntimeChoice
    db: DBChoice
    compartment_id: str
    compartment_name: str
    region: str
    dns_domain: str
    ocir_namespace: str
    existing_cluster_id: str = ""
    existing_atp_id: str = ""
    enable_apm: bool = True
    enable_waf: bool = True
    enable_stack_monitoring: bool = True
    actions: list[PlanAction] = field(default_factory=list)

    def compose(self) -> list[PlanAction]:
        """Fill ``actions`` in execution order."""
        env_base = {
            "DNS_DOMAIN": self.dns_domain,
            "OCI_COMPARTMENT_ID": self.compartment_id,
            "OCIR_REGION": self.region,
            "OCIR_TENANCY": self.ocir_namespace,
        }

        self.actions = []

        # 1. Pre-flight
        self.actions.append(PlanAction(
            kind="script",
            command="./deploy/pre-flight-check.sh",
            description="Validate required env + detect placeholder leaks",
            env={**env_base, "OCIR_REPO": f"{self.region}.ocir.io/{self.ocir_namespace}/octo-drone-shop"},
        ))

        # 2. Bootstrap (OCIR repo, namespaces, secrets)
        self.actions.append(PlanAction(
            kind="script",
            command="./deploy/init-tenancy.sh",
            description="Create OCIR repo + K8s namespace + bootstrap Secrets",
            env=env_base,
        ))

        # 3. APM + observability (opt-in)
        if self.enable_apm:
            self.actions.append(PlanAction(
                kind="script",
                command="./deploy/oci/ensure_apm.sh --apply",
                description="Provision APM Domain + RUM Web Application",
                env={**env_base, "PLAN_ONLY": "false"},
                requires_confirmation=True,
            ))
        if self.enable_stack_monitoring:
            self.actions.append(PlanAction(
                kind="script",
                command="./deploy/oci/ensure_stack_monitoring.sh",
                description="Register ATP as Stack Monitoring resource",
                env={**env_base, "DRY_RUN": "false", "AUTONOMOUS_DATABASE_ID": self.existing_atp_id},
                requires_confirmation=True,
            ))

        # 4. Runtime
        if self.runtime in (RuntimeChoice.OKE_EXISTING, RuntimeChoice.OKE_NEW):
            self.actions.append(PlanAction(
                kind="script",
                command="./deploy/oke/deploy-oke.sh",
                description="Apply OKE Deployments + Services + HPA + NetworkPolicies",
                env=env_base,
                requires_confirmation=True,
            ))
        elif self.runtime in (RuntimeChoice.VM_EXISTING, RuntimeChoice.VM_NEW):
            self.actions.append(PlanAction(
                kind="script",
                command="./deploy/vm/install.sh",
                description="Provision docker-compose stack on target VM",
                env=env_base,
                requires_confirmation=True,
            ))

        return self.actions
