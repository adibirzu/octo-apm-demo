"""Behavioral tests for deploy/pre-flight-check.sh.

The pre-flight script validates that required env vars are present and that
reachable local tooling (kubectl, oci, envsubst) is on PATH before a new
tenancy deploy is attempted. Missing variables must produce non-zero exit
with a clear error message — never silently use defaults.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "deploy" / "pre-flight-check.sh"


def _run(env: dict[str, str]) -> subprocess.CompletedProcess:
    # Start from an empty environment so missing-var tests are deterministic,
    # then inject PATH so bash + coreutils can resolve.
    base: dict[str, str] = {"PATH": os.environ.get("PATH", "")}
    base.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=base,
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.mark.portability
def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.exists(), f"pre-flight script missing at {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), "pre-flight script must be chmod +x"


@pytest.mark.portability
def test_fails_when_dns_domain_missing() -> None:
    result = _run({"OCIR_REPO": "r.ocir.io/t/shop", "K8S_NAMESPACE": "ns"})
    assert result.returncode != 0
    assert "DNS_DOMAIN" in (result.stderr + result.stdout)


@pytest.mark.portability
def test_fails_when_ocir_repo_missing() -> None:
    result = _run(
        {"DNS_DOMAIN": "tenant-a.example.invalid", "K8S_NAMESPACE": "ns"}
    )
    assert result.returncode != 0
    assert "OCIR_REPO" in (result.stderr + result.stdout)


@pytest.mark.portability
def test_fails_when_namespace_missing() -> None:
    result = _run(
        {
            "DNS_DOMAIN": "tenant-a.example.invalid",
            "OCIR_REPO": "r.ocir.io/t/shop",
        }
    )
    assert result.returncode != 0
    assert "K8S_NAMESPACE" in (result.stderr + result.stdout)


@pytest.mark.portability
def test_fails_on_example_cloud_leak() -> None:
    """Catch the most common copy-paste mistake: keeping example.cloud."""
    result = _run(
        {
            "DNS_DOMAIN": "shop.example.cloud",
            "OCIR_REPO": "r.ocir.io/t/shop",
            "K8S_NAMESPACE": "ns",
        }
    )
    assert result.returncode != 0
    combined = result.stderr + result.stdout
    assert "example.cloud" in combined or "placeholder" in combined


@pytest.mark.portability
def test_reports_missing_tools_but_passes_env_check() -> None:
    """With all required env vars set and no fake tenancy leak, env validation
    should pass. (Tool availability is environment-dependent, so we accept
    either exit 0 or a non-zero that cites the missing tool, not env vars.)
    """
    result = _run(
        {
            "DNS_DOMAIN": "tenant-a.example.invalid",
            "OCIR_REPO": "r.ocir.io/t/shop",
            "K8S_NAMESPACE": "octo-drone-shop",
        }
    )
    combined = result.stderr + result.stdout
    # Must not complain about required env vars in this case.
    assert "DNS_DOMAIN is not set" not in combined
    assert "OCIR_REPO is not set" not in combined
    assert "K8S_NAMESPACE is not set" not in combined
