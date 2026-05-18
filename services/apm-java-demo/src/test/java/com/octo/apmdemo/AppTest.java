package com.octo.apmdemo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.junit.jupiter.api.extension.ExtendWith;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class AppTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void readyReportsJavaAppServerRole() throws Exception {
        mockMvc.perform(get("/ready"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.service").value("octo-java-app-server"))
            .andExpect(jsonPath("$.role").value("droneshop-app-server"));
    }

    @Test
    void paymentAuthorizeReturnsObservableDecision() throws Exception {
        mockMvc.perform(
                post("/api/java-apm/payment/authorize")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "order_id": 42,
                          "amount_minor_units": 12999,
                          "currency": "usd",
                          "customer_email_domain": "example.invalid",
                          "idempotency_key_hash": "abc123"
                        }
                        """)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.decision").value("approved"))
            .andExpect(jsonPath("$.payment_provider").value("simulated-java-gateway"))
            .andExpect(jsonPath("$.order_id").value(42));
    }

    @Test
    void paymentAuthorizeEmitsStructuredLogForLogAnalytics(CapturedOutput output) throws Exception {
        mockMvc.perform(
                post("/api/java-apm/payment/authorize")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("X-Request-Id", "req-java-43")
                    .header("X-Workflow-Id", "checkout")
                    .header("X-Workflow-Step", "payment-authorize")
                    .content("""
                        {
                          "order_id": 43,
                          "amount_minor_units": 12999,
                          "currency": "usd",
                          "customer_email_domain": "example.invalid",
                          "idempotency_key_hash": "structured-log-test",
                          "payment_method": "credit_card",
                          "payment_network": "mastercard",
                          "payment_gateway_request_id": "pgw-43-test"
                        }
                        """)
            )
            .andExpect(status().isOk());

        assertThat(output.getOut())
            .contains("\"message\":\"java_payment_authorize\"")
            .contains("\"service_name\":\"octo-java-app-server\"")
            .contains("\"service.name\":\"octo-java-app-server\"")
            .contains("\"service.namespace\":\"octo\"")
            .contains("\"request_id\":\"req-java-43\"")
            .contains("\"workflow_id\":\"checkout\"")
            .contains("\"workflow_step\":\"payment-authorize\"")
            .contains("\"service\":")
            .contains("\"name\":\"octo-java-app-server\"")
            .contains("\"namespace\":\"octo\"")
            .contains("\"trace_id\":")
            .contains("\"span_id\":")
            .contains("\"payment_gateway_request_id\":\"pgw-43-test\"")
            .contains("\"payment.gateway.request_id\":\"pgw-43-test\"")
            .contains("\"payment.token.safe\":true");
    }

    @Test
    void paymentAuthorizeReturnsCardNetworkAuthorizationDetails() throws Exception {
        mockMvc.perform(
                post("/api/java-apm/payment/authorize")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "order_id": 91,
                          "amount_minor_units": 12999,
                          "currency": "usd",
                          "customer_email_domain": "example.invalid",
                          "idempotency_key_hash": "abc123",
                          "payment_method": "credit_card",
                          "payment_network": "visa",
                          "payment_gateway_request_id": "pgw-91-test",
                          "gateway_provider": "cybersource-compatible-simulator",
                          "card_brand": "visa",
                          "card_last4": "1111",
                          "card_fingerprint": "fingerprint-safe",
                          "billing_postal_code": "10001",
                          "card_cvv_present": true,
                          "verification_decision": "approved"
                        }
                        """)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.decision").value("approved"))
            .andExpect(jsonPath("$.payment_gateway_request_id").value("pgw-91-test"))
            .andExpect(jsonPath("$.card_flow.network").value("visa"))
            .andExpect(jsonPath("$.card_flow.avs_result").value("Y"))
            .andExpect(jsonPath("$.card_flow.cvv_result").value("M"))
            .andExpect(jsonPath("$.card_flow.three_ds.program").value("Visa Secure"))
            .andExpect(jsonPath("$.network_authorization.network").value("visa"))
            .andExpect(jsonPath("$.network_authorization.response_code").value("00"))
            .andExpect(jsonPath("$.network_authorization.gateway_code").value("APPROVED"));
    }

    @Test
    void paymentVerifyReturnsGooglePayTokenizationDetails() throws Exception {
        mockMvc.perform(
                post("/api/java-apm/payment/verify")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "order_id": 92,
                          "amount_minor_units": 12999,
                          "currency": "usd",
                          "customer_email_domain": "example.invalid",
                          "idempotency_key_hash": "wallet123",
                          "payment_method": "google_pay",
                          "payment_network": "mastercard",
                          "context_risk_score": 12,
                          "risk_reasons": "",
                          "payment_gateway_request_id": "pgw-92-test",
                          "gateway_provider": "cybersource-compatible-simulator",
                          "wallet_type": "google_pay",
                          "wallet_provider": "google_pay",
                          "wallet_tokenization_type": "PAYMENT_GATEWAY",
                          "wallet_token_hash": "wallet-token-hash",
                          "card_brand": "mastercard",
                          "card_last4": "4444"
                        }
                        """)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.verification_provider").value("octo-antifraud-verification-app"))
            .andExpect(jsonPath("$.decision").value("approved"))
            .andExpect(jsonPath("$.payment_gateway_request_id").value("pgw-92-test"))
            .andExpect(jsonPath("$.wallet_flow.provider").value("google_pay"))
            .andExpect(jsonPath("$.wallet_flow.google_pay.api_version").value(2))
            .andExpect(jsonPath("$.wallet_flow.google_pay.payment_method_data_type").value("CARD"))
            .andExpect(jsonPath("$.wallet_flow.tokenization_type").value("PAYMENT_GATEWAY"))
            .andExpect(jsonPath("$.wallet_flow.token_hash").value("wallet-token-hash"));
    }

    @Test
    void sqlErrorSimulationRequiresConfiguredOracleConnection() throws Exception {
        mockMvc.perform(
                post("/api/java-apm/simulate/sql-error")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"error_code\":\"ora-00942\"}")
            )
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.status").value("error"))
            .andExpect(jsonPath("$.error_type").value("SQLException"))
            .andExpect(jsonPath("$['sql.vendor_code']").value(17002));
    }

    @Test
    void attackSimulationReturnsMitreAttributes() throws Exception {
        mockMvc.perform(
                post("/api/java-apm/simulate/attack")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "technique_id": "T1059",
                          "tactic": "execution",
                          "source_ip": "203.0.113.44"
                        }
                        """)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.type").value("attack_java_segment"))
            .andExpect(jsonPath("$['mitre.technique_id']").value("T1059"))
            .andExpect(jsonPath("$['attack.source_ip']").value("203.0.113.44"));
    }
}
