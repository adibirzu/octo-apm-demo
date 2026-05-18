"""Checkout payment normalization, antifraud, and safe persistence.

This module intentionally accepts raw card data only at the simulator boundary.
It returns and stores PCI-safe metadata: network, last4, expiry, token hashes,
risk decisions, and gateway status. Full PAN and CVV values must not be logged
or persisted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import text


_CARD_METHODS = {"credit_card", "card"}
_WALLET_METHODS = {"apple_pay", "google_pay"}
_SAFE_METHODS = _CARD_METHODS | _WALLET_METHODS | {"bank_transfer", "crypto", "wire"}


@dataclass(frozen=True)
class PaymentContext:
    method: str
    provider: str
    card_brand: str = ""
    card_last4: str = ""
    card_exp_month: int | None = None
    card_exp_year: int | None = None
    card_fingerprint: str = ""
    card_cvv_present: bool = False
    wallet_type: str = ""
    wallet_token_hash: str = ""
    billing_postal_code: str = ""
    risk_score: int = 0
    risk_reasons: tuple[str, ...] = ()

    @property
    def should_decline(self) -> bool:
        blocking = {
            "invalid_luhn",
            "expired_card",
            "invalid_cvv",
            "missing_wallet_token",
            "unsupported_card_network",
            "issuer_decline_test_card",
        }
        return self.risk_score >= 85 or bool(blocking.intersection(self.risk_reasons))

    def safe_fields(self) -> dict[str, Any]:
        return {
            "payment.method": self.method,
            "payment.provider": self.provider,
            "payment.card_brand": self.card_brand,
            "payment.card_last4": self.card_last4,
            "payment.card_exp_month": self.card_exp_month or "",
            "payment.card_exp_year": self.card_exp_year or "",
            "payment.wallet_type": self.wallet_type,
            "payment.wallet_token_hash": self.wallet_token_hash,
            "payment.card_cvv_present": self.card_cvv_present,
            "payment.billing_postal_code": self.billing_postal_code,
            "payment.antifraud_score": self.risk_score,
            "payment.antifraud_reasons": ",".join(self.risk_reasons),
        }


def build_payment_context(
    *,
    payment_method: str,
    payment_details: dict[str, Any] | None,
    amount_minor_units: int,
    customer_email: str,
) -> PaymentContext:
    method = _normalize_method(payment_method)
    details = payment_details if isinstance(payment_details, dict) else {}

    if method in _CARD_METHODS:
        return _card_context(details, amount_minor_units=amount_minor_units, customer_email=customer_email)
    if method in _WALLET_METHODS:
        return _wallet_context(method, details, amount_minor_units=amount_minor_units, customer_email=customer_email)

    return PaymentContext(
        method=method,
        provider=f"simulated-{method}",
        risk_score=_base_risk(amount_minor_units, customer_email),
        risk_reasons=(),
    )


async def persist_payment_transaction(
    db,
    *,
    order_id: int,
    amount_minor_units: int,
    currency: str,
    context: PaymentContext,
    status: str,
    provider_reference: str,
    gateway_latency_ms: int,
    decision_source: str,
    error_code: str,
    trace_id: str,
) -> None:
    if db is None:
        return

    await db.execute(
        text(
            """
            INSERT INTO payment_transactions (
                order_id, provider, provider_reference, payment_method, wallet_type,
                status, amount_minor_units, currency, card_brand, card_last4,
                card_exp_month, card_exp_year, card_fingerprint, wallet_token_hash,
                billing_postal_code, antifraud_score, antifraud_reasons,
                gateway_latency_ms, decision_source, error_code, trace_id
            ) VALUES (
                :order_id, :provider, :provider_reference, :payment_method, :wallet_type,
                :status, :amount_minor_units, :currency, :card_brand, :card_last4,
                :card_exp_month, :card_exp_year, :card_fingerprint, :wallet_token_hash,
                :billing_postal_code, :antifraud_score, :antifraud_reasons,
                :gateway_latency_ms, :decision_source, :error_code, :trace_id
            )
            """
        ),
        {
            "order_id": int(order_id),
            "provider": context.provider,
            "provider_reference": provider_reference[:128],
            "payment_method": context.method,
            "wallet_type": context.wallet_type,
            "status": status,
            "amount_minor_units": int(amount_minor_units),
            "currency": (currency or "usd").lower()[:10],
            "card_brand": context.card_brand,
            "card_last4": context.card_last4,
            "card_exp_month": context.card_exp_month,
            "card_exp_year": context.card_exp_year,
            "card_fingerprint": context.card_fingerprint,
            "wallet_token_hash": context.wallet_token_hash,
            "billing_postal_code": context.billing_postal_code,
            "antifraud_score": int(context.risk_score),
            "antifraud_reasons": ",".join(context.risk_reasons),
            "gateway_latency_ms": int(gateway_latency_ms or 0),
            "decision_source": decision_source,
            "error_code": error_code,
            "trace_id": trace_id,
        },
    )


def _normalize_method(payment_method: str) -> str:
    method = re.sub(r"[^a-z0-9_]+", "_", str(payment_method or "credit_card").strip().lower())
    if method == "googlepay":
        method = "google_pay"
    if method == "applepay":
        method = "apple_pay"
    return method if method in _SAFE_METHODS else "credit_card"


def _card_context(details: dict[str, Any], *, amount_minor_units: int, customer_email: str) -> PaymentContext:
    card = details.get("card") if isinstance(details.get("card"), dict) else details
    number = _digits(card.get("number") or card.get("card_number"))
    cvv = _digits(card.get("cvv") or card.get("card_cvv"))
    expiry_month, expiry_year = _parse_expiry(card.get("expiry") or card.get("card_expiry"), card)
    brand = _detect_card_brand(number)
    last4 = number[-4:] if len(number) >= 4 else ""
    reasons: list[str] = []

    if number:
        if not _luhn_valid(number):
            reasons.append("invalid_luhn")
        if brand not in {"visa", "mastercard"}:
            reasons.append("unsupported_card_network")
        if number in {"4000000000000002", "5105105105105100"}:
            reasons.append("issuer_decline_test_card")
    else:
        reasons.append("legacy_no_card_details")

    if number and (expiry_month is None or expiry_year is None):
        reasons.append("missing_expiry")
    elif number and _expired(expiry_month, expiry_year):
        reasons.append("expired_card")

    if number and not (3 <= len(cvv) <= 4):
        reasons.append("invalid_cvv")

    postal_code = _safe_text(card.get("billing_postal_code") or card.get("postal_code"), 24)
    risk_score = _score_risk(
        amount_minor_units=amount_minor_units,
        customer_email=customer_email,
        reasons=reasons,
        postal_code=postal_code,
    )
    fingerprint = ""
    if number:
        fingerprint = sha256(f"{brand}:{number[:6]}:{last4}:{expiry_month}:{expiry_year}".encode("utf-8")).hexdigest()[:24]

    return PaymentContext(
        method="credit_card",
        provider=f"simulated-{brand}" if brand in {"visa", "mastercard"} else "simulated-card",
        card_brand=brand,
        card_last4=last4,
        card_exp_month=expiry_month,
        card_exp_year=expiry_year,
        card_fingerprint=fingerprint,
        card_cvv_present=bool(cvv),
        billing_postal_code=postal_code,
        risk_score=risk_score,
        risk_reasons=tuple(reasons),
    )


def _wallet_context(method: str, details: dict[str, Any], *, amount_minor_units: int, customer_email: str) -> PaymentContext:
    wallet = details.get("wallet") if isinstance(details.get("wallet"), dict) else details
    token = str(wallet.get("token") or wallet.get("payment_token") or "")
    network = _safe_text(wallet.get("network") or wallet.get("card_network") or "", 32).lower()
    brand = "mastercard" if network in {"mastercard", "mc"} else ("visa" if network == "visa" else network)
    reasons: list[str] = []
    if not token:
        reasons.append("missing_wallet_token")
    if brand and brand not in {"visa", "mastercard"}:
        reasons.append("unsupported_wallet_network")
    risk_score = _score_risk(
        amount_minor_units=amount_minor_units,
        customer_email=customer_email,
        reasons=reasons,
        postal_code="",
    )
    token_payload = token or json.dumps(wallet, sort_keys=True, default=str)
    return PaymentContext(
        method=method,
        provider=f"simulated-{method.replace('_', '-')}",
        card_brand=brand if brand in {"visa", "mastercard"} else "",
        wallet_type=method,
        wallet_token_hash=sha256(token_payload.encode("utf-8")).hexdigest()[:24] if token_payload else "",
        risk_score=risk_score,
        risk_reasons=tuple(reasons),
    )


def _score_risk(*, amount_minor_units: int, customer_email: str, reasons: list[str], postal_code: str) -> int:
    score = _base_risk(amount_minor_units, customer_email)
    reason_weights = {
        "invalid_luhn": 80,
        "expired_card": 70,
        "invalid_cvv": 45,
        "missing_wallet_token": 80,
        "unsupported_card_network": 35,
        "unsupported_wallet_network": 20,
        "missing_expiry": 20,
        "legacy_no_card_details": 0,
        "issuer_decline_test_card": 90,
    }
    score += sum(reason_weights.get(reason, 5) for reason in reasons)
    if postal_code and not re.fullmatch(r"[a-zA-Z0-9 -]{3,12}", postal_code):
        score += 15
        reasons.append("billing_postal_code_format")
    return max(0, min(99, score))


def _base_risk(amount_minor_units: int, customer_email: str) -> int:
    amount_score = min(max(int(amount_minor_units), 0) // 200_000, 45)
    domain = customer_email.rsplit("@", 1)[-1].lower() if "@" in customer_email else "unknown"
    domain_score = 2 if domain in {"example.invalid", "example.test", "apex.example.test", "octo.local"} else 8
    return min(99, amount_score + domain_score)


def _safe_text(value: object, limit: int) -> str:
    return re.sub(r"[^a-zA-Z0-9 ._@+-]+", "", str(value or "")).strip()[:limit]


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _detect_card_brand(number: str) -> str:
    if number.startswith("4"):
        return "visa"
    if len(number) >= 4:
        prefix2 = int(number[:2])
        prefix4 = int(number[:4])
        if 51 <= prefix2 <= 55 or 2221 <= prefix4 <= 2720:
            return "mastercard"
    return "unknown" if number else ""


def _luhn_valid(number: str) -> bool:
    if len(number) < 12:
        return False
    total = 0
    parity = len(number) % 2
    for index, char in enumerate(number):
        digit = int(char)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _parse_expiry(value: object, card: dict[str, Any]) -> tuple[int | None, int | None]:
    month_raw = card.get("exp_month") or card.get("expiry_month")
    year_raw = card.get("exp_year") or card.get("expiry_year")
    if month_raw and year_raw:
        return _coerce_month_year(month_raw, year_raw)
    match = re.match(r"^\s*(\d{1,2})\s*/\s*(\d{2}|\d{4})\s*$", str(value or ""))
    if not match:
        return None, None
    return _coerce_month_year(match.group(1), match.group(2))


def _coerce_month_year(month_raw: object, year_raw: object) -> tuple[int | None, int | None]:
    try:
        month = int(month_raw)
        year = int(year_raw)
    except (TypeError, ValueError):
        return None, None
    if year < 100:
        year += 2000
    if month < 1 or month > 12:
        return None, year
    return month, year


def _expired(month: int | None, year: int | None) -> bool:
    if month is None or year is None:
        return False
    now = datetime.utcnow()
    return (int(year), int(month)) < (now.year, now.month)
