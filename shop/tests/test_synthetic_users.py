"""Synthetic corporate user generation coverage."""

from __future__ import annotations

import pytest

from server.modules.synthetic_users import (
    DEFAULT_SYNTHETIC_USER_EMAIL_DOMAIN,
    generate_synthetic_users,
    normalize_synthetic_domain,
)


def test_synthetic_user_defaults_use_reserved_demo_domain() -> None:
    users = generate_synthetic_users(count=6, domain="")

    assert DEFAULT_SYNTHETIC_USER_EMAIL_DOMAIN == "apex.example.test"
    assert len(users) == 6
    assert all(user.email.endswith("@apex.example.test") for user in users)
    assert all("." in user.username for user in users)
    assert "oracle.com" not in str([user.email for user in users])


def test_synthetic_user_generation_rotates_names_deterministically() -> None:
    first = generate_synthetic_users(count=3, domain="corp.example.test")
    second = generate_synthetic_users(count=3, domain="corp.example.test")

    assert [user.email for user in first] == [user.email for user in second]
    assert [user.display_name for user in first] == [user.display_name for user in second]


@pytest.mark.parametrize("domain", ["example", "@example.test", "bad domain.test", "example.test/secret"])
def test_synthetic_user_domain_validation_rejects_unsafe_values(domain: str) -> None:
    with pytest.raises(ValueError):
        normalize_synthetic_domain(domain)
