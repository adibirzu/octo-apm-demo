"""Local payment gateway simulator for observability demos."""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

from .base import Intent, PaymentEventKind, WebhookEvent


@dataclass(frozen=True)
class SimulatedPaymentDecision:
    provider_reference: str
    status: str
    risk_score: int
    latency_ms: int
    amount_minor_units: int
    currency: str
    error_code: str = ""
    decision_source: str = "python-simulator"

    def observability_fields(self) -> dict[str, object]:
        return {
            "payment.provider": "simulated",
            "payment.provider_reference": self.provider_reference,
            "payment.status": self.status,
            "payment.risk_score": self.risk_score,
            "payment.latency_ms": self.latency_ms,
            "payment.error_code": self.error_code,
            "payment.decision_source": self.decision_source,
            "payment.amount_minor_units": self.amount_minor_units,
            "payment.currency": self.currency,
        }


class SimulatedPaymentProvider:
    name = "simulated"

    def __init__(self, *, mode: str | None = None, fixed_latency_ms: int | None = None) -> None:
        self.mode = (mode or os.getenv("PAYMENT_SIMULATION_MODE", "approve")).strip().lower()
        self.fixed_latency_ms = fixed_latency_ms

    def create_intent(
        self,
        *,
        amount_minor_units: int,
        currency: str,
        order_id: int,
        customer_email: str,
    ) -> Intent:
        return Intent(
            provider=self.name,
            provider_reference=self._provider_reference(order_id, amount_minor_units, customer_email),
            amount_minor_units=int(amount_minor_units),
            currency=(currency or "usd").lower(),
            client_secret=None,
            redirect_url=None,
        )

    def decide(
        self,
        *,
        amount_minor_units: int,
        currency: str,
        order_id: int,
        customer_email: str,
    ) -> SimulatedPaymentDecision:
        started = time.monotonic()
        reference = self._provider_reference(order_id, amount_minor_units, customer_email)
        risk_score = self._risk_score(amount_minor_units, customer_email, reference)
        if self.mode in {"decline", "deny"}:
            status = "declined"
            risk_score = max(risk_score, 85)
        elif self.mode == "timeout":
            status = "timeout"
        elif risk_score >= 85:
            status = "declined"
        else:
            status = "authorized"
        latency_ms = self.fixed_latency_ms
        if latency_ms is None:
            latency_ms = int((time.monotonic() - started) * 1000) + 25 + (risk_score % 40)
        error_code = "" if status == "authorized" else f"SIM_{status.upper()}"
        return SimulatedPaymentDecision(
            provider_reference=reference,
            status=status,
            risk_score=risk_score,
            latency_ms=latency_ms,
            amount_minor_units=int(amount_minor_units),
            currency=(currency or "usd").lower(),
            error_code=error_code,
        )

    def verify_webhook(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent:
        return WebhookEvent(
            provider=self.name,
            provider_event_id="simulated-local",
            kind=PaymentEventKind.SUCCEEDED,
            provider_reference="simulated-local",
            amount_minor_units=0,
            currency="usd",
            raw_payload={"simulated": True},
        )

    @staticmethod
    def _provider_reference(order_id: int, amount_minor_units: int, customer_email: str) -> str:
        digest = hashlib.sha256(
            f"{order_id}:{amount_minor_units}:{customer_email.lower()}".encode("utf-8")
        ).hexdigest()[:16]
        return f"sim_{order_id}_{digest}"

    @staticmethod
    def _risk_score(amount_minor_units: int, customer_email: str, reference: str) -> int:
        amount_score = min(int(amount_minor_units) // 100_000, 55)
        domain = customer_email.rsplit("@", 1)[-1].lower() if "@" in customer_email else "unknown"
        domain_score = 8 if domain not in {"example.invalid", "octo.local"} else 2
        entropy_score = int(reference[-2:], 16) % 30
        return max(0, min(99, amount_score + domain_score + entropy_score))
