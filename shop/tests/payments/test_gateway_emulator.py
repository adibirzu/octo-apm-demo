"""Payment gateway emulator workflow definitions."""

from __future__ import annotations

from server.modules.payments.checkout_workflow import build_payment_context
from server.modules.payments.gateway_emulator import (
    build_gateway_steps,
    payment_gateway_capabilities,
    workflow_detail_fields,
    _base_attributes,
    _component_attributes,
    _processor_service_name,
    _step_attributes,
)


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
    assert capabilities["processor_contract"] == "cybersource-compatible-authorization"
    assert "payment_gateway_events" in capabilities["stores"]
    assert "google_pay" in capabilities["steps_by_method"]
    assert "verification_antifraud_request" in capabilities["steps_by_method"]["google_pay"]
    assert "verification_antifraud_response" in capabilities["steps_by_method"]["apple_pay"]
    assert "processor_authorization_request" in capabilities["steps_by_method"]["credit_card"]


def test_google_pay_step_attributes_follow_token_safe_payment_data_shape() -> None:
    context = build_payment_context(
        payment_method="google_pay",
        payment_details={
            "wallet": {
                "provider": "google_pay",
                "token": "raw-google-token-never-logged",
                "network": "MASTERCARD",
            }
        },
        amount_minor_units=129900,
        customer_email="buyer@example.invalid",
    )
    step = build_gateway_steps(context)[1]
    attrs = _step_attributes(step, context=context, network="mastercard")

    assert attrs["payment.wallet.provider"] == "google_pay"
    assert attrs["payment.google_pay.api_version"] == 2
    assert attrs["payment.google_pay.payment_method_data.type"] == "CARD"
    assert attrs["payment.google_pay.card_network"] == "MASTERCARD"
    assert attrs["payment.wallet.tokenization_type"] == "PAYMENT_GATEWAY"
    assert attrs["payment.wallet.gateway"] == "cybersource"
    assert attrs["payment.wallet.token_hash"] == context.wallet_token_hash
    assert "raw-google-token-never-logged" not in str(attrs)


def test_apple_pay_step_attributes_include_merchant_session_and_payment_token_shape() -> None:
    context = build_payment_context(
        payment_method="apple_pay",
        payment_details={
            "wallet": {
                "provider": "apple_pay",
                "token": "raw-apple-token-never-logged",
                "network": "VISA",
            }
        },
        amount_minor_units=129900,
        customer_email="buyer@example.invalid",
    )
    merchant_attrs = _step_attributes(build_gateway_steps(context)[1], context=context, network="visa")
    token_attrs = _step_attributes(build_gateway_steps(context)[2], context=context, network="visa")

    assert merchant_attrs["payment.apple_pay.merchant_validation.status"] == "completed"
    assert merchant_attrs["payment.apple_pay.validation_url"] == "apple-pay-gateway.apple.com"
    assert token_attrs["payment.apple_pay.payment_data.version"] == "EC_v1"
    assert token_attrs["payment.apple_pay.payment_method.network"] == "VISA"
    assert token_attrs["payment.apple_pay.header.transaction_id_hash"]
    assert token_attrs["payment.wallet.token_hash"] == context.wallet_token_hash
    assert "raw-apple-token-never-logged" not in str(token_attrs)


def test_card_step_attributes_include_visa_mastercard_authorization_controls() -> None:
    context = build_payment_context(
        payment_method="credit_card",
        payment_details={
            "card": {
                "number": "5555555555554444",
                "expiry": "12/30",
                "cvv": "321",
                "billing_postal_code": "10001",
            }
        },
        amount_minor_units=129900,
        customer_email="buyer@example.invalid",
    )
    token_attrs = _step_attributes(build_gateway_steps(context)[2], context=context, network="mastercard")
    network_attrs = _step_attributes(build_gateway_steps(context)[4], context=context, network="mastercard")

    assert token_attrs["payment.card.brand"] == "mastercard"
    assert token_attrs["payment.card.tokenized"] is True
    assert token_attrs["payment.card.cvv.result"] == "M"
    assert network_attrs["payment.network.route"] == "mastercard-authorization"
    assert network_attrs["payment.3ds.program"] == "Mastercard Identity Check"
    assert network_attrs["payment.3ds.eci"] == "02"


def test_gateway_step_components_identify_wallet_processor_and_card_rails() -> None:
    google_context = build_payment_context(
        payment_method="google_pay",
        payment_details={"wallet": {"provider": "google_pay", "token": "safe-token", "network": "MASTERCARD"}},
        amount_minor_units=129900,
        customer_email="buyer@example.invalid",
    )
    apple_context = build_payment_context(
        payment_method="apple_pay",
        payment_details={"wallet": {"provider": "apple_pay", "token": "safe-token", "network": "VISA"}},
        amount_minor_units=129900,
        customer_email="buyer@example.invalid",
    )
    card_context = build_payment_context(
        payment_method="credit_card",
        payment_details={"card": {"number": "5555555555554444", "expiry": "12/30", "cvv": "321"}},
        amount_minor_units=129900,
        customer_email="buyer@example.invalid",
    )

    google_attrs = _component_attributes(build_gateway_steps(google_context)[1], context=google_context, network="network-token")
    apple_attrs = _component_attributes(build_gateway_steps(apple_context)[1], context=apple_context, network="network-token")
    card_attrs = _component_attributes(build_gateway_steps(card_context)[4], context=card_context, network="mastercard")

    assert google_attrs["component"] == "google-pay-gateway"
    assert google_attrs["payment.component"] == "Google Pay Gateway"
    assert apple_attrs["component"] == "apple-pay-gateway"
    assert apple_attrs["payment.component"] == "Apple Pay Gateway"
    assert card_attrs["component"] == "mastercard-payment-network"
    assert card_attrs["payment.component"] == "Mastercard Payment Network"


def test_gateway_step_response_fields_expose_safe_component_labels() -> None:
    context = build_payment_context(
        payment_method="google_pay",
        payment_details={"wallet": {"provider": "google_pay", "token": "safe-token", "network": "MASTERCARD"}},
        amount_minor_units=129900,
        customer_email="buyer@example.invalid",
    )
    attrs = _component_attributes(build_gateway_steps(context)[1], context=context, network="mastercard")
    response = build_gateway_steps(context)[1].__class__(
        name="wallet_token_received",
        phase="wallet_token",
        message="Payment gateway received Google Pay encrypted payment data",
        attributes=attrs,
    ).response_fields()

    assert response["component"] == "google-pay-gateway"
    assert response["component_label"] == "Google Pay Gateway"
    assert response["peer_service"] == "google-pay-gateway"


def test_processor_service_name_uses_runtime_java_component() -> None:
    class JavaClient:
        service_name = "octo-java-app-server-oke"

    assert _processor_service_name(JavaClient()) == "octo-java-app-server-oke"


def test_workflow_detail_fields_only_exposes_safe_gateway_summary() -> None:
    details = workflow_detail_fields(
        {
            "payment.wallet.token_hash": "hash-ok",
            "payment.processor.authorization_code": "AUTH-SHOULD-NOT-LEAK",
            "payment.processor.response_code": "00",
            "payment.card.cvv.result": "M",
            "payment.card.pan": "4111111111111111",
            "payment.wallet.token.raw": "secret",
        }
    )

    assert details == {
        "payment.wallet.token_hash": "hash-ok",
        "payment.processor.response_code": "00",
        "payment.card.cvv.result": "M",
    }


def test_gateway_base_attributes_include_purchase_journey_context() -> None:
    context = build_payment_context(
        payment_method="google_pay",
        payment_details={"wallet": {"provider": "google_pay", "token": "safe-token", "network": "MASTERCARD"}},
        amount_minor_units=129900,
        customer_email="buyer@example.invalid",
    )

    attrs = _base_attributes(
        order_id=42,
        amount_minor_units=129900,
        currency="usd",
        context=context,
        gateway_request_id="pgw-42-test",
        network="network-token",
        observability_context={
            "shop.journey_id": "journey-42",
            "enduser.action": "shop.checkout.submit",
            "checkout.step": "payment",
        },
    )

    assert attrs["shop.journey_id"] == "journey-42"
    assert attrs["enduser.action"] == "shop.checkout.submit"
    assert attrs["checkout.step"] == "payment"
    assert attrs["payment.gateway.request_id"] == "pgw-42-test"
