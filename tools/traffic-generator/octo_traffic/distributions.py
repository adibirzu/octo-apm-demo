"""Realistic probability distributions — kept in one place so unit tests
can assert shapes independent of the transport.

Every function returns a stdlib-compatible value. ``numpy`` is used for
the stock distributions because SciPy's API is overkill and ``random``
lacks log-normal + Pareto in the standard library.
"""

from __future__ import annotations

import numpy as np

_rng: np.random.Generator | None = None


def set_seed(seed: int) -> None:
    """Pin the RNG so a run is reproducible when seed != 0.

    Thread-safety: numpy's default_rng is per-thread by convention;
    the generator runs most of its hot loop in asyncio, so all draws
    execute in one event loop thread — safe.
    """
    global _rng
    _rng = np.random.default_rng(seed or None)


def _rng_() -> np.random.Generator:
    global _rng
    if _rng is None:
        _rng = np.random.default_rng()
    return _rng


def session_duration_seconds(*, mu: float, sigma: float) -> float:
    """Log-normal — classic model for web session duration.

    Returns seconds with a long right tail (a few users stay very long).
    """
    return float(_rng_().lognormal(mean=mu, sigma=sigma))


def pageviews_per_session(*, alpha: float, cap: int) -> int:
    """Pareto — few users browse deeply, most bounce on 1–3 pages.

    Clamped to ``cap`` so a single session cannot starve the RPS budget.
    """
    raw = _rng_().pareto(alpha) + 1.0
    return int(min(cap, max(1, round(raw))))


def bernoulli(p: float) -> bool:
    return bool(_rng_().random() < p)


def poisson_arrival_inter_seconds(rps: float) -> float:
    """Gap between two new session arrivals at ``rps`` rate, seconds."""
    if rps <= 0:
        return float("inf")
    return float(_rng_().exponential(scale=1.0 / rps))


def choice(items):
    """Uniform-random choice driven by the pinned RNG."""
    return _rng_().choice(items)
