"""Plan composition tests — pure, no OCI calls."""

from __future__ import annotations

from octo_wizard.plan import DBChoice, DeploymentPlan, RuntimeChoice


def _plan(**overrides) -> DeploymentPlan:
    defaults = dict(
        runtime=RuntimeChoice.OKE_EXISTING,
        db=DBChoice.ATP_EXISTING,
        compartment_id="ocid1.compartment.oc1..x",
        compartment_name="octo",
        region="eu-frankfurt-1",
        dns_domain="octodemo.cloud",
        ocir_namespace="acmecorp",
        existing_cluster_id="ocid1.cluster..y",
        existing_atp_id="ocid1.autonomousdatabase..z",
    )
    defaults.update(overrides)
    p = DeploymentPlan(**defaults)
    p.compose()
    return p


def test_plan_includes_preflight_and_init() -> None:
    plan = _plan()
    cmds = [a.command for a in plan.actions]
    assert any("pre-flight-check.sh" in c for c in cmds)
    assert any("init-tenancy.sh" in c for c in cmds)


def test_oke_runtime_adds_deploy_oke() -> None:
    plan = _plan(runtime=RuntimeChoice.OKE_EXISTING)
    assert any("deploy-oke.sh" in a.command for a in plan.actions)


def test_vm_runtime_adds_vm_install() -> None:
    plan = _plan(runtime=RuntimeChoice.VM_EXISTING)
    assert any("vm/install.sh" in a.command for a in plan.actions)


def test_opt_out_apm_removes_ensure_apm() -> None:
    plan = _plan(enable_apm=False)
    assert not any("ensure_apm" in a.command for a in plan.actions)


def test_stack_monitoring_atp_ocid_is_passed() -> None:
    plan = _plan(existing_atp_id="ocid1.atp..777")
    apm_action = next(a for a in plan.actions if "ensure_stack_monitoring" in a.command)
    assert apm_action.env["AUTONOMOUS_DATABASE_ID"] == "ocid1.atp..777"


def test_apm_action_requires_confirmation() -> None:
    plan = _plan()
    apm_action = next(a for a in plan.actions if "ensure_apm.sh" in a.command)
    assert apm_action.requires_confirmation


def test_runtime_action_carries_dns_env() -> None:
    plan = _plan(dns_domain="tenant-a.example.invalid")
    rt = next(a for a in plan.actions if "deploy-oke.sh" in a.command or "vm/install.sh" in a.command)
    assert rt.env["DNS_DOMAIN"] == "tenant-a.example.invalid"
