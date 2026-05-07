package com.octo.apmdemo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
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
