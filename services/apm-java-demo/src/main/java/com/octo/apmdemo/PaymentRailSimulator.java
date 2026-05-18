package com.octo.apmdemo;

import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.api.trace.Span;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

final class PaymentRailSimulator {
    private PaymentRailSimulator() {}

    static Rail rail(App.PaymentAuthorizeRequest request) {
        String method = safePaymentValue(request.payment_method(), "credit_card");
        String cardBrand = safePaymentValue(request.card_brand(), "");
        String network = safeNetwork(request.payment_network(), cardBrand, method);
        String walletProvider = safePaymentValue(request.wallet_provider(), request.wallet_type());
        String tokenizationType = walletTokenizationType(method, request.wallet_tokenization_type());
        return new Rail(
            method,
            network,
            safePaymentValue(request.payment_gateway_request_id(), "pgw-" + request.order_id()),
            safePaymentValue(request.gateway_provider(), "cybersource-compatible-simulator"),
            safePaymentValue(request.wallet_type(), ""),
            walletProvider,
            tokenizationType,
            safePaymentValue(request.wallet_token_hash(), ""),
            cardBrand.isBlank() ? network : cardBrand,
            safePaymentValue(request.card_last4(), ""),
            safePaymentValue(request.card_fingerprint(), "")
        );
    }

    static Rail rail(App.PaymentVerifyRequest request) {
        String method = safePaymentValue(request.payment_method(), "credit_card");
        String cardBrand = safePaymentValue(request.card_brand(), "");
        String network = safeNetwork(request.payment_network(), cardBrand, method);
        String walletProvider = safePaymentValue(request.wallet_provider(), request.wallet_type());
        String tokenizationType = walletTokenizationType(method, request.wallet_tokenization_type());
        return new Rail(
            method,
            network,
            safePaymentValue(request.payment_gateway_request_id(), "pgw-" + request.order_id()),
            safePaymentValue(request.gateway_provider(), "cybersource-compatible-simulator"),
            safePaymentValue(request.wallet_type(), ""),
            walletProvider,
            tokenizationType,
            safePaymentValue(request.wallet_token_hash(), ""),
            cardBrand.isBlank() ? network : cardBrand,
            safePaymentValue(request.card_last4(), ""),
            safePaymentValue(request.card_fingerprint(), "")
        );
    }

    static Map<String, Object> walletFlow(App.PaymentAuthorizeRequest request, Rail rail) {
        return walletFlow(
            rail,
            request.order_id(),
            request.card_last4(),
            request.card_exp_month(),
            request.card_exp_year()
        );
    }

    static Map<String, Object> walletFlow(App.PaymentVerifyRequest request, Rail rail) {
        return walletFlow(
            rail,
            request.order_id(),
            request.card_last4(),
            request.card_exp_month(),
            request.card_exp_year()
        );
    }

    static Map<String, Object> cardFlow(
        App.PaymentAuthorizeRequest request,
        Rail rail,
        Map<String, Object> networkAuthorization
    ) {
        return cardFlow(
            rail,
            request.billing_postal_code(),
            request.card_cvv_present(),
            networkAuthorization
        );
    }

    static Map<String, Object> cardFlow(
        App.PaymentVerifyRequest request,
        Rail rail,
        Map<String, Object> networkAuthorization
    ) {
        return cardFlow(
            rail,
            request.billing_postal_code(),
            request.card_cvv_present(),
            networkAuthorization
        );
    }

    static Map<String, Object> networkAuthorization(
        App.PaymentAuthorizeRequest request,
        Rail rail,
        String decision,
        String authCode
    ) {
        String responseCode = switch (decision) {
            case "approved" -> "00";
            case "timeout" -> "91";
            default -> "05";
        };
        String gatewayCode = switch (decision) {
            case "approved" -> "APPROVED";
            case "timeout" -> "TIMED_OUT";
            default -> "DECLINED";
        };
        String seed = request.order_id() + ":" + rail.gatewayRequestId() + ":" + rail.network();
        Map<String, Object> flow = new HashMap<>();
        flow.put("network", rail.network());
        flow.put("gateway_code", gatewayCode);
        flow.put("response_code", responseCode);
        flow.put("authorization_code", authCode);
        flow.put("retrieval_reference_number", numericId(seed + ":rrn", 12));
        flow.put("system_trace_audit_number", numericId(seed + ":stan", 6));
        flow.put("network_transaction_id", syntheticId("ntx", request.order_id(), seed, 20));
        flow.put("avs_result", safePaymentValue(request.billing_postal_code(), "").isBlank() ? "U" : "Y");
        flow.put("cvv_result", request.card_cvv_present() ? "M" : "U");
        flow.put("three_ds", threeDsFlow(rail.network(), !rail.walletType().isBlank()));
        flow.put("acquirer", "octo-acquirer-simulator");
        flow.put("processor", "octo-java-app-server");
        return flow;
    }

    static void enrichPaymentSpan(
        String operation,
        App.PaymentAuthorizeRequest request,
        Rail rail,
        String decision,
        int riskScore
    ) {
        enrichPaymentSpan(
            operation,
            request.order_id(),
            request.amount_minor_units(),
            request.currency(),
            request.customer_email_domain(),
            request.idempotency_key_hash(),
            rail,
            decision,
            riskScore
        );
    }

    static void enrichPaymentSpan(
        String operation,
        App.PaymentVerifyRequest request,
        Rail rail,
        String decision,
        int riskScore
    ) {
        enrichPaymentSpan(
            operation,
            request.order_id(),
            request.amount_minor_units(),
            request.currency(),
            request.customer_email_domain(),
            request.idempotency_key_hash(),
            rail,
            decision,
            riskScore
        );
    }

    static void emitPaymentFlowEvents(
        App.PaymentAuthorizeRequest request,
        Rail rail,
        String decision,
        int riskScore,
        Map<String, Object> networkAuthorization,
        boolean verificationOnly
    ) {
        emitPaymentFlowEvents(
            request.order_id(),
            request.amount_minor_units(),
            request.currency(),
            rail,
            decision,
            riskScore,
            networkAuthorization,
            verificationOnly
        );
    }

    static void emitPaymentFlowEvents(
        App.PaymentVerifyRequest request,
        Rail rail,
        String decision,
        int riskScore,
        Map<String, Object> networkAuthorization,
        boolean verificationOnly
    ) {
        emitPaymentFlowEvents(
            request.order_id(),
            request.amount_minor_units(),
            request.currency(),
            rail,
            decision,
            riskScore,
            networkAuthorization,
            verificationOnly
        );
    }

    private static Map<String, Object> walletFlow(
        Rail rail,
        long orderId,
        String cardLast4,
        int cardExpMonth,
        int cardExpYear
    ) {
        Map<String, Object> flow = new HashMap<>();
        flow.put("provider", rail.walletProvider());
        flow.put("wallet_type", rail.walletType());
        flow.put("tokenization_type", rail.walletTokenizationType());
        flow.put("token_hash", rail.walletTokenHash());
        flow.put("network", rail.network());
        flow.put("card_last4", safePaymentValue(cardLast4, rail.cardLast4()));
        flow.put("token_safe", true);
        if (rail.method().equals("google_pay")) {
            flow.put("google_pay", Map.of(
                "api_version", 2,
                "api_version_minor", 0,
                "payment_method_data_type", "CARD",
                "tokenization_type", rail.walletTokenizationType().isBlank() ? "PAYMENT_GATEWAY" : rail.walletTokenizationType(),
                "gateway", "cybersource",
                "card_network", networkLabel(rail.network())
            ));
        } else if (rail.method().equals("apple_pay")) {
            flow.put("apple_pay", Map.of(
                "merchant_validation", "completed",
                "payment_data_version", "EC_v1",
                "transaction_id_hash", syntheticId("apple-pay", orderId, rail.gatewayRequestId(), 24),
                "payment_method_network", networkLabel(rail.network()),
                "header_present", true
            ));
        }
        if (cardExpMonth > 0) {
            flow.put("card_exp_month", cardExpMonth);
        }
        if (cardExpYear > 0) {
            flow.put("card_exp_year", cardExpYear);
        }
        return flow;
    }

    private static Map<String, Object> cardFlow(
        Rail rail,
        String billingPostalCode,
        boolean cardCvvPresent,
        Map<String, Object> networkAuthorization
    ) {
        String safePostalCode = nullToEmpty(billingPostalCode);
        Map<String, Object> flow = new HashMap<>();
        flow.put("brand", rail.cardBrand());
        flow.put("network", rail.network());
        flow.put("last4", rail.cardLast4());
        flow.put("fingerprint", rail.cardFingerprint());
        flow.put("entry_mode", "ecommerce");
        flow.put("tokenized", !rail.cardFingerprint().isBlank() || !rail.walletTokenHash().isBlank());
        flow.put(
            "avs_result",
            safePaymentValue((String) networkAuthorization.get("avs_result"), safePostalCode.isBlank() ? "U" : "Y")
                .toUpperCase(Locale.ROOT)
        );
        flow.put(
            "cvv_result",
            safePaymentValue((String) networkAuthorization.get("cvv_result"), cardCvvPresent ? "M" : "U")
                .toUpperCase(Locale.ROOT)
        );
        flow.put("three_ds", threeDsFlow(rail.network(), !rail.walletType().isBlank()));
        return flow;
    }

    private static Map<String, Object> threeDsFlow(String network, boolean wallet) {
        String normalized = safePaymentValue(network, "card");
        String program;
        String eci;
        if (normalized.equals("mastercard")) {
            program = "Mastercard Identity Check";
            eci = "02";
        } else if (normalized.equals("visa")) {
            program = "Visa Secure";
            eci = "05";
        } else {
            program = wallet ? "network-token-authentication" : "cardholder-authentication";
            eci = wallet ? "05" : "07";
        }
        return Map.of(
            "program", program,
            "eci", eci,
            "authentication_value_present", true,
            "flow", wallet ? "wallet_cryptogram" : "frictionless"
        );
    }

    private static void enrichPaymentSpan(
        String operation,
        long orderId,
        long amountMinorUnits,
        String currency,
        String customerEmailDomain,
        String idempotencyKeyHash,
        Rail rail,
        String decision,
        int riskScore
    ) {
        Span span = Span.current();
        setAttribute(span, "app.module", "java-payment-gateway");
        setAttribute(span, "app.logical_endpoint", operation);
        setAttribute(span, "payment.gateway.emulated", true);
        setAttribute(span, "payment.token.safe", true);
        setAttribute(span, "payment.gateway.request_id", rail.gatewayRequestId());
        setAttribute(span, "payment.gateway.provider", rail.gatewayProvider());
        setAttribute(span, "payment.method", rail.method());
        setAttribute(span, "payment.network", rail.network());
        setAttribute(span, "payment.wallet.provider", rail.walletProvider());
        setAttribute(span, "payment.wallet.type", rail.walletType());
        setAttribute(span, "payment.wallet.tokenization_type", rail.walletTokenizationType());
        setAttribute(span, "payment.wallet.token_hash", rail.walletTokenHash());
        setAttribute(span, "payment.card_brand", rail.cardBrand());
        setAttribute(span, "payment.card_last4", rail.cardLast4());
        setAttribute(span, "payment.card.fingerprint", rail.cardFingerprint());
        setAttribute(span, "payment.processor.decision", decision);
        setAttribute(span, "payment.risk_score", riskScore);
        setAttribute(span, "payment.amount_minor_units", amountMinorUnits);
        setAttribute(span, "payment.currency", safePaymentValue(currency, "usd"));
        setAttribute(span, "customer.email_domain", safeDomain(customerEmailDomain));
        setAttribute(span, "payment.idempotency_key_hash", safePaymentValue(idempotencyKeyHash, ""));
        setAttribute(span, "orders.order_id", orderId);
    }

    private static void emitPaymentFlowEvents(
        long orderId,
        long amountMinorUnits,
        String currency,
        Rail rail,
        String decision,
        int riskScore,
        Map<String, Object> networkAuthorization,
        boolean verificationOnly
    ) {
        addSpanEvent(
            verificationOnly ? "java.payment.antifraud.verify" : "java.payment.gateway.request.accepted",
            Map.of(
                "payment.gateway.request_id", rail.gatewayRequestId(),
                "payment.method", rail.method(),
                "payment.network", rail.network(),
                "payment.processor.decision", decision,
                "payment.risk_score", riskScore,
                "orders.order_id", orderId,
                "payment.amount_minor_units", amountMinorUnits,
                "payment.currency", safePaymentValue(currency, "usd")
            )
        );
        if (rail.method().equals("google_pay")) {
            addSpanEvent(
                "java.payment.wallet.google.payment_data.validated",
                Map.of(
                    "payment.google_pay.api_version", 2,
                    "payment.google_pay.api_version_minor", 0,
                    "payment.google_pay.payment_method_data.type", "CARD",
                    "payment.wallet.tokenization_type", rail.walletTokenizationType(),
                    "payment.wallet.gateway", "cybersource",
                    "payment.wallet.token_hash", rail.walletTokenHash()
                )
            );
        } else if (rail.method().equals("apple_pay")) {
            addSpanEvent(
                "java.payment.wallet.apple.payment_token.validated",
                Map.of(
                    "payment.apple_pay.merchant_validation.status", "completed",
                    "payment.apple_pay.payment_data.version", "EC_v1",
                    "payment.apple_pay.payment_method.network", networkLabel(rail.network()),
                    "payment.wallet.token_hash", rail.walletTokenHash()
                )
            );
        }
        if (!verificationOnly) {
            addSpanEvent(
                "java.payment.processor.authorization_request",
                Map.of(
                    "payment.gateway.request_id", rail.gatewayRequestId(),
                    "payment.processor.name", "octo-java-app-server",
                    "payment.network", rail.network(),
                    "payment.processor.decision", decision
                )
            );
            addSpanEvent(
                "java.payment.network." + rail.network() + ".authorize",
                Map.of(
                    "payment.network", rail.network(),
                    "payment.network.response_code", String.valueOf(networkAuthorization.getOrDefault("response_code", "")),
                    "payment.network.gateway_code", String.valueOf(networkAuthorization.getOrDefault("gateway_code", "")),
                    "payment.network.transaction_id", String.valueOf(networkAuthorization.getOrDefault("network_transaction_id", ""))
                )
            );
        }
    }

    private static void addSpanEvent(String name, Map<String, Object> attributes) {
        AttributesBuilder builder = Attributes.builder();
        for (Map.Entry<String, Object> entry : attributes.entrySet()) {
            Object value = entry.getValue();
            if (value instanceof String stringValue && !stringValue.isBlank()) {
                builder.put(entry.getKey(), stringValue);
            } else if (value instanceof Integer integerValue) {
                builder.put(entry.getKey(), integerValue.longValue());
            } else if (value instanceof Long longValue) {
                builder.put(entry.getKey(), longValue);
            } else if (value instanceof Boolean booleanValue) {
                builder.put(entry.getKey(), booleanValue);
            }
        }
        Span.current().addEvent(name, builder.build());
    }

    private static void setAttribute(Span span, String key, String value) {
        if (value != null && !value.isBlank()) {
            span.setAttribute(key, value);
        }
    }

    private static void setAttribute(Span span, String key, long value) {
        span.setAttribute(key, value);
    }

    private static void setAttribute(Span span, String key, boolean value) {
        span.setAttribute(key, value);
    }

    private static String walletTokenizationType(String method, String requested) {
        String tokenizationType = safePaymentValue(requested, "").toUpperCase(Locale.ROOT);
        if (method.equals("google_pay") && tokenizationType.isBlank()) {
            return "PAYMENT_GATEWAY";
        }
        if (method.equals("apple_pay") && tokenizationType.isBlank()) {
            return "APPLE_PAY";
        }
        return tokenizationType;
    }

    private static String safeNetwork(String requested, String cardBrand, String method) {
        String network = safePaymentValue(requested, "");
        if (network.isBlank() || network.equals("network-token")) {
            network = safePaymentValue(cardBrand, "");
        }
        if (network.equals("mc")) {
            return "mastercard";
        }
        if (network.equals("mastercard") || network.equals("visa")) {
            return network;
        }
        if (safePaymentValue(method, "").endsWith("_pay")) {
            return "network-token";
        }
        return network.isBlank() ? "card" : network;
    }

    private static String safePaymentValue(String value, String fallback) {
        String raw = value == null || value.isBlank() ? nullToEmpty(fallback) : value;
        String safe = raw.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9._:@+,-]", "");
        return safe.length() > 160 ? safe.substring(0, 160) : safe;
    }

    private static String networkLabel(String network) {
        return switch (safePaymentValue(network, "")) {
            case "mastercard" -> "MASTERCARD";
            case "visa" -> "VISA";
            case "network-token" -> "NETWORK_TOKEN";
            default -> safePaymentValue(network, "UNKNOWN").toUpperCase(Locale.ROOT);
        };
    }

    private static String syntheticId(String prefix, long orderId, String seed, int length) {
        String hex = Integer.toHexString((orderId + ":" + seed).hashCode()).replace("-", "0");
        String padded = (hex + "00000000000000000000000000000000")
            .substring(0, Math.max(1, Math.min(length, 32)));
        return prefix + "-" + padded;
    }

    private static String numericId(String seed, int digits) {
        long modulus = 1L;
        for (int index = 0; index < digits; index++) {
            modulus *= 10L;
        }
        long value = Math.floorMod((long) seed.hashCode(), modulus);
        return String.format("%0" + digits + "d", value);
    }

    private static String safeDomain(String value) {
        String domain = nullToEmpty(value).toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9._-]", "");
        return domain.isBlank() ? "unknown" : domain;
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    record Rail(
        String method,
        String network,
        String gatewayRequestId,
        String gatewayProvider,
        String walletType,
        String walletProvider,
        String walletTokenizationType,
        String walletTokenHash,
        String cardBrand,
        String cardLast4,
        String cardFingerprint
    ) {}
}
