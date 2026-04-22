"""Remediator metrics (KG-039).

In-process counters + timers exposed at /metrics for Prometheus scrape.
OTel SDK could publish these too; plain text format is simpler here
since the remediator only runs a couple of replicas.

Metrics published:
    remediator_runs_total{state="...", tier="..."}   Counter
    remediator_run_time_to_propose_seconds           Histogram
    remediator_run_time_to_approve_seconds           Histogram
    remediator_run_time_to_execute_seconds           Histogram
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any


class _Counter:
    def __init__(self) -> None:
        self._value = 0

    def inc(self, amount: int = 1) -> None:
        self._value += amount

    @property
    def value(self) -> int:
        return self._value


class _Histogram:
    """Simple histogram — N buckets, counts + sum."""

    _BOUNDS = (0.1, 0.5, 1.0, 5.0, 30.0, 120.0, 600.0)

    def __init__(self) -> None:
        self._buckets = [0] * (len(self._BOUNDS) + 1)
        self._sum = 0.0
        self._count = 0

    def observe(self, seconds: float) -> None:
        self._sum += seconds
        self._count += 1
        for i, b in enumerate(self._BOUNDS):
            if seconds <= b:
                self._buckets[i] += 1
                return
        self._buckets[-1] += 1


class Metrics:
    """Thread-safe singleton-like container — tests can instantiate
    new instances to assert in isolation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, ...], _Counter] = defaultdict(_Counter)
        self._histograms: dict[str, _Histogram] = defaultdict(_Histogram)

    def inc_run(self, *, state: str, tier: str) -> None:
        with self._lock:
            self._counters[("remediator_runs_total", state, tier)].inc()

    def observe_time_to_propose(self, seconds: float) -> None:
        with self._lock:
            self._histograms["remediator_run_time_to_propose_seconds"].observe(seconds)

    def observe_time_to_approve(self, seconds: float) -> None:
        with self._lock:
            self._histograms["remediator_run_time_to_approve_seconds"].observe(seconds)

    def observe_time_to_execute(self, seconds: float) -> None:
        with self._lock:
            self._histograms["remediator_run_time_to_execute_seconds"].observe(seconds)

    def render_prometheus(self) -> str:
        with self._lock:
            lines: list[str] = []
            lines.append("# HELP remediator_runs_total Runs by state + tier")
            lines.append("# TYPE remediator_runs_total counter")
            for key, counter in self._counters.items():
                if key[0] != "remediator_runs_total":
                    continue
                state, tier = key[1], key[2]
                lines.append(f'remediator_runs_total{{state="{state}",tier="{tier}"}} {counter.value}')

            for name, hist in self._histograms.items():
                lines.append(f"# HELP {name} remediator timing")
                lines.append(f"# TYPE {name} histogram")
                cumulative = 0
                for bound, count in zip(hist._BOUNDS, hist._buckets[:-1]):
                    cumulative += count
                    lines.append(f'{name}_bucket{{le="{bound}"}} {cumulative}')
                lines.append(f'{name}_bucket{{le="+Inf"}} {hist._count}')
                lines.append(f"{name}_sum {hist._sum}")
                lines.append(f"{name}_count {hist._count}")
            return "\n".join(lines) + "\n"


_default = Metrics()


def default_metrics() -> Metrics:
    return _default
