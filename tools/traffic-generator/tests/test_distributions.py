"""Unit tests for the probability distributions.

No network, no OTel — just the math. Keeps the fast feedback loop
independent of a reachable shop URL.
"""

from __future__ import annotations

import statistics

import pytest

from octo_traffic import distributions as dist


def test_set_seed_is_reproducible() -> None:
    dist.set_seed(42)
    first = [
        dist.session_duration_seconds(mu=5.0, sigma=0.8),
        dist.pageviews_per_session(alpha=1.7, cap=30),
        dist.bernoulli(0.5),
    ]
    dist.set_seed(42)
    second = [
        dist.session_duration_seconds(mu=5.0, sigma=0.8),
        dist.pageviews_per_session(alpha=1.7, cap=30),
        dist.bernoulli(0.5),
    ]
    assert first == second


def test_pageviews_stays_in_bounds() -> None:
    dist.set_seed(1)
    caps = [dist.pageviews_per_session(alpha=1.5, cap=10) for _ in range(1000)]
    assert min(caps) >= 1
    assert max(caps) <= 10


def test_bernoulli_distribution_shape() -> None:
    dist.set_seed(7)
    trials = 5000
    true_fraction = sum(dist.bernoulli(0.3) for _ in range(trials)) / trials
    # Allow 2-sigma envelope
    assert abs(true_fraction - 0.3) < 0.03


def test_session_duration_heavy_tail() -> None:
    """Log-normal has a heavier right tail than a normal with same mean."""
    dist.set_seed(11)
    samples = [
        dist.session_duration_seconds(mu=5.0, sigma=0.8) for _ in range(2000)
    ]
    median = statistics.median(samples)
    # ~5% of samples should be >= 3× the median for these params (standard
    # property of log-normal)
    tail = [s for s in samples if s >= 3 * median]
    assert len(tail) >= 50


def test_poisson_arrival_rps() -> None:
    dist.set_seed(13)
    total = sum(dist.poisson_arrival_inter_seconds(rps=10.0) for _ in range(2000))
    expected_mean_gap = 1.0 / 10.0
    actual_mean_gap = total / 2000
    # Allow 10% envelope — n=2000 is enough to be tight.
    assert abs(actual_mean_gap - expected_mean_gap) / expected_mean_gap < 0.1


def test_poisson_arrival_rejects_nonpositive_rps() -> None:
    assert dist.poisson_arrival_inter_seconds(0.0) == float("inf")
