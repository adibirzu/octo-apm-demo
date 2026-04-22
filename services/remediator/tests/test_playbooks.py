"""Playbook registry + matching tests (unit-level, no k8s/redis)."""

from __future__ import annotations

import pytest

from octo_remediator.playbooks import CATALOG
from octo_remediator.playbooks.base import (
    ExecutionContext,
    Playbook,
    RemediationRun,
    RemediationTier,
)


def test_catalog_has_at_least_one_of_each_tier() -> None:
    tiers = {p.tier for p in CATALOG}
    assert RemediationTier.LOW in tiers
    assert RemediationTier.MEDIUM in tiers
    assert RemediationTier.HIGH in tiers


def test_cache_flush_matches_cache_alarms() -> None:
    from octo_remediator.playbooks.cache_flush import CacheFlushPlaybook

    p = CacheFlushPlaybook()
    assert p.matches({"body": "cache hit ratio stale"})
    assert p.matches({"metric_name": "cache.hit_ratio", "body": "low"})
    assert not p.matches({"body": "cpu hot"})


def test_scale_hpa_matches_cpu_alarms() -> None:
    from octo_remediator.playbooks.scale_hpa import ScaleHPAPlaybook

    p = ScaleHPAPlaybook()
    assert p.matches({"body": "CPU pressure sustained"})
    assert p.matches({"metric_name": "container_cpu_utilisation"})
    assert not p.matches({"body": "cache stale"})


def test_restart_deployment_matches_unhealthy() -> None:
    from octo_remediator.playbooks.restart_deployment import RestartDeploymentPlaybook

    p = RestartDeploymentPlaybook()
    assert p.matches({"body": "Deployment unhealthy for 10m"})
    assert p.matches({"body": "pod crashloop backoff"})
    assert not p.matches({"body": "cache miss"})


def test_restart_deployment_is_tier_high() -> None:
    from octo_remediator.playbooks.restart_deployment import RestartDeploymentPlaybook

    assert RestartDeploymentPlaybook().tier == RemediationTier.HIGH


def test_extract_params_honors_annotations() -> None:
    from octo_remediator.playbooks.scale_hpa import ScaleHPAPlaybook

    p = ScaleHPAPlaybook()
    params = p.extract_params({
        "body": "cpu",
        "annotations": {
            "target_namespace": "my-ns",
            "target_deployment": "my-dep",
            "min_replicas_increment": "3",
        },
    })
    assert params == {
        "namespace": "my-ns",
        "deployment": "my-dep",
        "min_replicas_increment": 3,
    }


async def test_cache_flush_dry_run_returns_action() -> None:
    from octo_remediator.playbooks.cache_flush import CacheFlushPlaybook

    p = CacheFlushPlaybook()
    run = RemediationRun.propose(
        playbook=p,
        alarm_id="alarm-1",
        alarm_summary="cache stale",
        params={"namespace": "shop:catalog"},
    )
    ctx = ExecutionContext(run=run, alarm={}, dry_run=True)
    actions = await p.execute(ctx)
    assert len(actions) == 1
    assert actions[0]["kind"] == "cache_flush_dryrun"
    assert actions[0]["target"] == "shop:catalog"
