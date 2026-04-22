"""OCI tenancy discovery — all calls via the `oci` SDK.

Discovery is **read-only**. The wizard does not create resources here;
it assembles a picture of what's already in the tenancy so the
planning step (`plan.py`) can present real choices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OciResource:
    id: str
    name: str
    state: str = ""


@dataclass
class TenancyInventory:
    tenancy_ocid: str = ""
    tenancy_name: str = ""
    regions: list[str] = field(default_factory=list)
    selected_region: str = ""
    compartments: list[OciResource] = field(default_factory=list)
    oke_clusters: list[OciResource] = field(default_factory=list)
    atps: list[OciResource] = field(default_factory=list)
    vcns: list[OciResource] = field(default_factory=list)
    ocir_namespace: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "tenancy_name": self.tenancy_name,
            "selected_region": self.selected_region,
            "n_compartments": len(self.compartments),
            "n_oke_clusters": len(self.oke_clusters),
            "n_atps": len(self.atps),
            "n_vcns": len(self.vcns),
            "ocir_namespace": self.ocir_namespace,
        }


class Discovery:
    """Wraps the OCI SDK calls we need. Lazy-imports oci so the wizard
    module can be imported (and tested) without the SDK installed."""

    def __init__(self, *, profile: str = "DEFAULT", region: str = ""):
        self._profile = profile
        self._region_override = region
        self._config: dict[str, Any] | None = None

    def _oci(self):
        try:
            import oci  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "oci SDK not installed — pip install '.[oci]' to use discovery"
            ) from exc
        return oci

    def _get_config(self) -> dict[str, Any]:
        if self._config is None:
            oci = self._oci()
            cfg = oci.config.from_file(profile_name=self._profile)
            if self._region_override:
                cfg["region"] = self._region_override
            self._config = cfg
        return self._config

    def tenancy(self) -> tuple[str, str]:
        oci = self._oci()
        cfg = self._get_config()
        ic = oci.identity.IdentityClient(cfg)
        t = ic.get_tenancy(cfg["tenancy"]).data
        return t.id, getattr(t, "name", "")

    def regions(self) -> list[str]:
        oci = self._oci()
        cfg = self._get_config()
        ic = oci.identity.IdentityClient(cfg)
        return [r.region_name for r in ic.list_region_subscriptions(cfg["tenancy"]).data]

    def compartments(self) -> list[OciResource]:
        oci = self._oci()
        cfg = self._get_config()
        ic = oci.identity.IdentityClient(cfg)
        raw = ic.list_compartments(
            cfg["tenancy"],
            compartment_id_in_subtree=True,
            access_level="ACCESSIBLE",
            lifecycle_state="ACTIVE",
        ).data
        return [OciResource(id=c.id, name=c.name, state=c.lifecycle_state) for c in raw]

    def oke_clusters(self, compartment_id: str) -> list[OciResource]:
        oci = self._oci()
        cfg = self._get_config()
        ce = oci.container_engine.ContainerEngineClient(cfg)
        raw = ce.list_clusters(compartment_id=compartment_id).data
        return [OciResource(id=c.id, name=c.name, state=c.lifecycle_state) for c in raw]

    def atps(self, compartment_id: str) -> list[OciResource]:
        oci = self._oci()
        cfg = self._get_config()
        db = oci.database.DatabaseClient(cfg)
        raw = db.list_autonomous_databases(compartment_id=compartment_id).data
        return [OciResource(id=d.id, name=d.display_name, state=d.lifecycle_state) for d in raw]

    def vcns(self, compartment_id: str) -> list[OciResource]:
        oci = self._oci()
        cfg = self._get_config()
        vn = oci.core.VirtualNetworkClient(cfg)
        raw = vn.list_vcns(compartment_id=compartment_id).data
        return [OciResource(id=v.id, name=v.display_name, state=v.lifecycle_state) for v in raw]

    def ocir_namespace(self) -> str:
        oci = self._oci()
        cfg = self._get_config()
        os_client = oci.object_storage.ObjectStorageClient(cfg)
        return os_client.get_namespace().data

    def build_inventory(self, *, compartment_id: str) -> TenancyInventory:
        tid, tname = self.tenancy()
        inv = TenancyInventory(
            tenancy_ocid=tid,
            tenancy_name=tname,
            selected_region=self._get_config().get("region", ""),
        )
        inv.regions = self.regions()
        inv.compartments = self.compartments()
        inv.oke_clusters = self.oke_clusters(compartment_id)
        inv.atps = self.atps(compartment_id)
        inv.vcns = self.vcns(compartment_id)
        inv.ocir_namespace = self.ocir_namespace()
        return inv
