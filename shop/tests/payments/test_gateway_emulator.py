"""Payment gateway emulator workflow definitions."""

from __future__ import annotations

from server.modules.payments.checkout_workflow import build_payment_context
from server.modules.payments.gateway_emulator import build_gateway_steps, payment_gateway_capabilities


def _step_names(method: str, details: dict) -> list[str]:
    context = build_payment_context(
        payment_method=method,
        payment_details=details,
        amount_minor_units=129900,
        customer_email="buyer@example.invalid",
    )
    return [step.name for step in build_gateway_steps(context)]


def test_google_pay_gateway_steps_include_token_decryption_and_network_cryptogram() -> None:
    steps = _step_names(
        "google_pay",
        {
            "wallet": {
                "provider": "google_pay",
                "token": "raw-token-never-logged",
                "network": "MASTERCARD",
            }
        },
    )

    assert steps == [
        "gateway_payment_received",
        "wallet_token_received",
        "gateway_token_decryption",
        "network_token_cryptogram_validation",
        "internal_antifraud_screening",
    ]


def test_apple_pay_gateway_steps_include_merchant_validation() -> None:
    steps = _step_names(
        "apple_pay",
        {
            "wallet": {
                "provider": "apple_pay",
                "token": "apple-payment-token",
                "network": "VISA",
            }
        },
    )

    assert "apple_pay_merchant_validation" in steps
    assert "gateway_token_decryption" in steps
    assert "network_token_cryptogram_validation" in steps


def test_card_gateway_steps_include_tokenization_and_network_routing() -> None:
    steps = _step_names(
        "credit_card",
        {
            "card": {
                "number": "4111111111111111",
                "expiry": "12/30",
                "cvv": "123",
            }
        },
    )

    assert "gateway_card_tokenization" in steps
    assert "card_network_routing" in steps


def test_payment_gateway_capabilities_are_token_safe() -> None:
    capabilities = payment_gateway_capabilities()

    assert capabilities["gateway"] == "octo-payment-gateway-emulator"
    assert capabilities["safe_storage"] == "tokenized_metadata_only"
    assert "payment_gateway_events" in capabilities["stores"]
    assert "google_pay" in capabilities["steps_by_method"]
    assert "verification_antifraud_request" in capabilities["steps_by_method"]["google_pay"]
    assert "verification_antifraud_response" in capabilities["steps_by_method"]["apple_pay"]
    assert "processor_authorization_request" in capabilities["steps_by_method"]["credit_card"]
