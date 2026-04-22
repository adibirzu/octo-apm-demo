"""Circuit breaker for external service calls (CRM, workflow gateway).

Prevents cascading failures when an integration target is down.
State transitions: CLOSED → OPEN → HALF_OPEN → CLOSED.

Publishes breaker state to OCI Monitoring via the existing metrics pipeline.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — reject fast
    HALF_OPEN = "half_open" # Probing — allow one request


class CircuitBreaker:
    """Per-service circuit breaker with configurable thresholds."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("Circuit breaker '%s': OPEN → HALF_OPEN", self.name)
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def allow_request(self) -> bool:
        """Check if a request should proceed."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max:
                    self._half_open_calls += 1
                    return True
            return False
        return False  # OPEN

    def record_success(self) -> None:
        """Record a successful call — reset breaker if half-open."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("Circuit breaker '%s': HALF_OPEN → CLOSED (recovered)", self.name)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call — trip breaker if threshold reached."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s': HALF_OPEN → OPEN (probe failed)", self.name
                )
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s': CLOSED → OPEN (%d consecutive failures)",
                    self.name, self._failure_count,
                )

    def status(self) -> dict[str, Any]:
        """Return breaker state for observability endpoints."""
        current = self.state
        with self._lock:
            return {
                "name": self.name,
                "state": current.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_s": self.recovery_timeout,
                "last_failure_age_s": round(
                    time.time() - self._last_failure_time, 1
                ) if self._last_failure_time > 0 else None,
            }


# ── Global breaker instances ────────────────────────────────────
crm_breaker = CircuitBreaker("crm", failure_threshold=5, recovery_timeout=60.0)
workflow_breaker = CircuitBreaker("workflow_gateway", failure_threshold=3, recovery_timeout=30.0)
