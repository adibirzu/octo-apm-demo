"""Profile registry tests — the 12 named profiles must all be present
and well-formed."""

from __future__ import annotations

import pytest

from octo_load_control.profiles import (
    PROFILES,
    ExecutorKind,
    Profile,
    ProfileName,
    get_profile,
    list_profiles,
)


def test_every_enumerated_name_has_a_profile() -> None:
    for name in ProfileName:
        assert name in PROFILES, f"ProfileName.{name.name} is enumerated but not in PROFILES"


def test_exactly_twelve_profiles() -> None:
    # OCI 360 §Load Profile Catalog mandates 12 — any change here
    # requires updating the OCI 360 doc first.
    assert len(PROFILES) == 12


@pytest.mark.parametrize("name", [p for p in ProfileName])
def test_profile_is_well_formed(name: ProfileName) -> None:
    p = PROFILES[name]
    assert isinstance(p, Profile)
    assert p.description, f"{name} has empty description"
    assert p.target_type, f"{name} has empty target_type"
    assert p.target_name, f"{name} has empty target_name"
    assert isinstance(p.executor, ExecutorKind)
    assert p.default_duration_seconds > 0


def test_get_profile_by_string_name() -> None:
    p = get_profile("db-read-burst")
    assert p.name == ProfileName.DB_READ_BURST


def test_get_profile_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="unknown profile"):
        get_profile("not-real")


def test_list_profiles_returns_stable_set() -> None:
    first = {p.name for p in list_profiles()}
    second = {p.name for p in list_profiles()}
    assert first == second == set(ProfileName)


def test_expected_signals_populated_for_visible_profiles() -> None:
    # Every profile that uses TRAFFIC_GENERATOR must document what
    # operators should see — otherwise the workshop can't verify.
    for p in list_profiles():
        if p.executor == ExecutorKind.TRAFFIC_GENERATOR:
            assert p.expected_signals, f"{p.name} is missing expected_signals"
