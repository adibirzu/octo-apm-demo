/*
 * octo-apm-java-demo — a small Spring Boot service that participates in
 * Drone Shop checkout and simulation flows while populating the OCI APM
 * "App Servers" dashboard. The OCI APM Java agent attached with
 * `-javaagent:` reports:
 *
 *   - Apdex (threshold driven by spring-boot-actuator health)
 *   - Active Servers (one per running JVM)
 *   - Server restarts
 *   - Resource consumption per request thread
 *   - Server request rate
 *   - App server CPU load
 *   - JVM info: Name, version, Young/Old GC time
 *
 * Python services (shop, crm) do not populate this app-server metric
 * surface by themselves, so checkout and admin simulations route through
 * this JVM to create a real downstream app-server segment.
 */
package com.octo.apmdemo;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
@RestController
public class App {
    private static final Logger LOG = LoggerFactory.getLogger(App.class);
    private static final String SERVICE_NAME = "octo-java-app-server";
    private static final String ROLE = "droneshop-app-server";
    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }

    @Bean
    public FilterRegistrationBean<OncePerRequestFilter> traceMdcFilter() {
        FilterRegistrationBean<OncePerRequestFilter> registration = new FilterRegistrationBean<>();
        registration.setFilter(new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain filterChain
            ) throws ServletException, IOException {
                String traceparent = request.getHeader("traceparent");
                if (traceparent != null) {
                    String[] parts = traceparent.split("-");
                    if (parts.length >= 4) {
                        MDC.put("trace_id", parts[1]);
                        MDC.put("span_id", parts[2]);
                    }
                }
                String correlationId = request.getHeader("X-Correlation-Id");
                if (correlationId != null && !correlationId.isBlank()) {
                    MDC.put("correlation_id", correlationId);
                }
                try {
                    filterChain.doFilter(request, response);
                } finally {
                    MDC.remove("trace_id");
                    MDC.remove("span_id");
                    MDC.remove("correlation_id");
                }
            }
        });
        registration.setOrder(1);
        return registration;
    }

    @GetMapping("/")
    public Map<String, Object> root() {
        return Map.of(
            "service", SERVICE_NAME,
            "role", ROLE,
            "purpose", "populate OCI APM App Servers view and link Drone Shop checkout calls",
            "jvm.version", System.getProperty("java.version"),
            "jvm.name", System.getProperty("java.vm.name"),
            "endpoints", List.of(
                "/", "/ready", "/healthz",
                "/api/java-apm/quote",
                "/api/java-apm/payment/verify",
                "/api/java-apm/payment/authorize",
                "/api/java-apm/simulate/slow",
                "/api/java-apm/simulate/gc",
                "/api/java-apm/simulate/cpu",
                "/api/java-apm/simulate/error",
                "/api/java-apm/simulate/external-error",
                "/api/java-apm/simulate/sql-error",
                "/api/java-apm/simulate/attack",
                "/slow", "/allocate", "/error"
            )
        );
    }

    @GetMapping("/ready")
    public Map<String, Object> ready() {
        return Map.of(
            "ready", true,
            "service", SERVICE_NAME,
            "role", ROLE,
            "runtime", "java",
            "app_server", "spring-boot-embedded-tomcat",
            "jvm.version", System.getProperty("java.version"),
            "jvm.name", System.getProperty("java.vm.name")
        );
    }

    @GetMapping("/healthz")
    public Map<String, String> healthz() {
        return Map.of("status", "up");
    }

    @GetMapping("/api/java-apm/health")
    public Map<String, Object> apiHealth() {
        return ready();
    }

    @PostMapping("/api/java-apm/quote")
    public Map<String, Object> quote(@RequestBody QuoteRequest request) throws InterruptedException {
        int quantity = Math.max(request.quantity(), 1);
        long base = Math.max(request.base_price_minor_units(), 0L) * quantity;
        long tax = Math.round(base * 0.07);
        long shipping = base >= 500_000 ? 0L : 14_900L;
        long total = base + tax + shipping;
        long latency = simulateLatency(30, 120);
        LOG.info(
            "quote_calculated product_id={} quantity={} base_minor={} total_minor={} latency_ms={}",
            request.product_id(), quantity, base, total, latency
        );
        return Map.of(
            "service", SERVICE_NAME,
            "quote_id", "quote-" + request.product_id() + "-" + Instant.now().toEpochMilli(),
            "product_id", request.product_id(),
            "quantity", quantity,
            "subtotal_minor_units", base,
            "tax_minor_units", tax,
            "shipping_minor_units", shipping,
            "total_minor_units", total,
            "latency_ms", latency
        );
    }

    @PostMapping("/api/java-apm/payment/authorize")
    public Map<String, Object> authorizePayment(@RequestBody PaymentAuthorizeRequest request)
        throws InterruptedException {
        long latency = simulateLatency(40, 250);
        int riskScore = riskScore(request);
        String mode = request.simulation_mode() == null || request.simulation_mode().isBlank()
            ? env("PAYMENT_SIMULATION_MODE", "approve").toLowerCase()
            : request.simulation_mode().toLowerCase();
        String decision = switch (mode) {
            case "decline", "deny" -> "declined";
            case "timeout" -> {
                Thread.sleep(1_500L);
                yield "timeout";
            }
            default -> riskScore >= 85 ? "declined" : "approved";
        };
        String errorCode = "approved".equals(decision) ? "" : "SIM_" + decision.toUpperCase();
        String authCode = "approved".equals(decision)
            ? "AUTH-" + request.order_id() + "-" + Integer.toHexString(riskScore * 997)
            : "";
        LOG.info(
            "payment_authorize order_id={} amount_minor={} currency={} decision={} risk_score={} latency_ms={} email_domain={}",
            request.order_id(), request.amount_minor_units(), request.currency(), decision,
            riskScore, latency, safeDomain(request.customer_email_domain())
        );
        Map<String, Object> payload = new HashMap<>();
        payload.put("payment_provider", "simulated-java-gateway");
        payload.put("order_id", request.order_id());
        payload.put("decision", decision);
        payload.put("authorization_code", authCode);
        payload.put("risk_score", riskScore);
        payload.put("latency_ms", latency);
        payload.put("currency", request.currency());
        payload.put("amount_minor_units", request.amount_minor_units());
        payload.put("error_code", errorCode);
        payload.put("customer_email_domain", safeDomain(request.customer_email_domain()));
        payload.put("idempotency_key_hash", nullToEmpty(request.idempotency_key_hash()));
        payload.put("simulation_mode", mode);
        return payload;
    }

    @PostMapping("/api/java-apm/payment/verify")
    public Map<String, Object> verifyPayment(@RequestBody PaymentVerifyRequest request)
        throws InterruptedException {
        long latency = simulateLatency(35, 180);
        int riskScore = verificationRiskScore(request);
        String mode = request.simulation_mode() == null || request.simulation_mode().isBlank()
            ? env("PAYMENT_SIMULATION_MODE", "approve").toLowerCase()
            : request.simulation_mode().toLowerCase();
        String reasons = nullToEmpty(request.risk_reasons()).toLowerCase();
        boolean forcedDecline = mode.equals("decline")
            || mode.equals("deny")
            || reasons.contains("issuer_decline_test_card")
            || reasons.contains("missing_wallet_token")
            || reasons.contains("invalid_luhn")
            || reasons.contains("expired_card");
        boolean periodicReview = deterministicIssue(request.idempotency_key_hash(), request.order_id(), 17);
        String decision;
        if (forcedDecline || riskScore >= 90) {
            decision = "declined";
        } else if (periodicReview || riskScore >= 70) {
            decision = "review";
        } else {
            decision = "approved";
        }
        String errorCode = switch (decision) {
            case "declined" -> forcedDecline ? "ANTIFRAUD_DECLINED" : "ANTIFRAUD_HIGH_RISK";
            case "review" -> "ANTIFRAUD_REVIEW";
            default -> "";
        };
        LOG.info(
            "payment_verify order_id={} amount_minor={} currency={} method={} network={} decision={} risk_score={} latency_ms={} email_domain={} periodic_review={}",
            request.order_id(), request.amount_minor_units(), request.currency(), nullToEmpty(request.payment_method()),
            nullToEmpty(request.payment_network()), decision, riskScore, latency,
            safeDomain(request.customer_email_domain()), periodicReview
        );
        Map<String, Object> payload = new HashMap<>();
        payload.put("verification_provider", "octo-antifraud-verification-app");
        payload.put("order_id", request.order_id());
        payload.put("decision", decision);
        payload.put("risk_score", riskScore);
        payload.put("risk_reasons", nullToEmpty(request.risk_reasons()));
        payload.put("periodic_review", periodicReview);
        payload.put("latency_ms", latency);
        payload.put("currency", request.currency());
        payload.put("amount_minor_units", request.amount_minor_units());
        payload.put("payment_method", nullToEmpty(request.payment_method()));
        payload.put("payment_network", nullToEmpty(request.payment_network()));
        payload.put("error_code", errorCode);
        payload.put("customer_email_domain", safeDomain(request.customer_email_domain()));
        payload.put("idempotency_key_hash", nullToEmpty(request.idempotency_key_hash()));
        payload.put("simulation_mode", mode);
        return payload;
    }

    @PostMapping("/api/java-apm/simulate/slow")
    public Map<String, Object> simulateSlow(@RequestBody(required = false) SimulationRequest request)
        throws InterruptedException {
        long requested = request == null ? 750L : request.duration_ms();
        long duration = Math.max(100L, Math.min(requested, 10_000L));
        Thread.sleep(duration);
        LOG.warn("simulation_slow duration_ms={}", duration);
        return Map.of("status", "completed", "type", "java_slow", "duration_ms", duration);
    }

    @PostMapping("/api/java-apm/simulate/gc")
    public Map<String, Object> simulateGc(@RequestBody(required = false) SimulationRequest request) {
        int requested = request == null ? 48 : request.megabytes();
        int megabytes = Math.max(8, Math.min(requested, 256));
        long allocated = allocateMegabytes(megabytes);
        LOG.warn("simulation_gc allocated_bytes={}", allocated);
        return Map.of("status", "completed", "type", "java_gc", "allocated_bytes", allocated);
    }

    @PostMapping("/api/java-apm/simulate/cpu")
    public Map<String, Object> simulateCpu(@RequestBody(required = false) SimulationRequest request) {
        long requested = request == null ? 500L : request.duration_ms();
        long duration = Math.max(100L, Math.min(requested, 5_000L));
        long deadline = System.nanoTime() + duration * 1_000_000L;
        long iterations = 0L;
        double value = 1.0d;
        while (System.nanoTime() < deadline) {
            value = Math.sqrt(value + ThreadLocalRandom.current().nextDouble(0.01d, 3.0d));
            iterations++;
        }
        LOG.warn("simulation_cpu duration_ms={} iterations={}", duration, iterations);
        return Map.of(
            "status", "completed",
            "type", "java_cpu",
            "duration_ms", duration,
            "iterations", iterations
        );
    }

    @PostMapping("/api/java-apm/simulate/error")
    public Map<String, Object> simulateError() {
        throw new IllegalStateException("intentional Java app-server simulation error");
    }

    @PostMapping("/api/java-apm/simulate/external-error")
    public Map<String, Object> simulateExternalError(
        @RequestBody(required = false) ExternalErrorRequest request
    ) throws IOException, InterruptedException {
        int statusCode = request == null ? 503 : request.status_code();
        statusCode = Math.max(400, Math.min(statusCode, 599));
        String targetUrl = request == null ? "" : nullToEmpty(request.target_url());
        if (targetUrl.isBlank()) {
            targetUrl = "https://httpstat.us/" + statusCode;
        }

        HttpRequest httpRequest = HttpRequest.newBuilder()
            .uri(URI.create(targetUrl))
            .timeout(Duration.ofSeconds(8))
            .header("User-Agent", "octo-demo-java-apm/1.0")
            .GET()
            .build();
        HttpResponse<String> response = HTTP_CLIENT.send(httpRequest, HttpResponse.BodyHandlers.ofString());
        LOG.warn(
            "external_error_simulated target_url={} status_code={} scenario={} attack_id={} run_id={} request_id={} api_gateway_request_id={} api_gateway_route={} api_gateway_action={}",
            targetUrl,
            response.statusCode(),
            request == null ? "default" : nullToEmpty(request.scenario()),
            request == null ? "" : nullToEmpty(request.attack_id()),
            request == null ? "" : nullToEmpty(request.run_id()),
            request == null ? "" : nullToEmpty(request.request_id()),
            request == null ? "" : nullToEmpty(request.api_gateway_request_id()),
            request == null ? "" : nullToEmpty(request.api_gateway_route()),
            request == null ? "" : nullToEmpty(request.api_gateway_action())
        );
        if (response.statusCode() >= 400) {
            throw new ExternalCallSimulationException(
                "intentional external call error status code " + response.statusCode(),
                targetUrl,
                response.statusCode()
            );
        }
        return Map.of(
            "status", "completed",
            "type", "external_error",
            "target_url", targetUrl,
            "status_code", response.statusCode()
        );
    }

    @PostMapping("/api/java-apm/simulate/sql-error")
    public Map<String, Object> simulateSqlError(@RequestBody(required = false) SqlErrorRequest request)
        throws SQLException {
        String code = request == null ? "ora-00942" : nullToEmpty(request.error_code()).toLowerCase();
        String statement = switch (code) {
            case "ora-01722", "invalid-number" -> "SELECT TO_NUMBER('OCTO_DEMO') FROM dual";
            case "ora-01476", "divide-by-zero" -> "SELECT 1 / 0 FROM dual";
            case "ora-00904", "invalid-identifier" -> "SELECT missing_column FROM dual";
            default -> "SELECT * FROM octo_apm_missing_table";
        };
        LOG.warn(
            "sql_error_simulation_requested error_code={} statement={} scenario={} attack_id={} run_id={} request_id={} api_gateway_request_id={} api_gateway_route={} api_gateway_action={}",
            code,
            statement,
            request == null ? "default" : nullToEmpty(request.scenario()),
            request == null ? "" : nullToEmpty(request.attack_id()),
            request == null ? "" : nullToEmpty(request.run_id()),
            request == null ? "" : nullToEmpty(request.request_id()),
            request == null ? "" : nullToEmpty(request.api_gateway_request_id()),
            request == null ? "" : nullToEmpty(request.api_gateway_route()),
            request == null ? "" : nullToEmpty(request.api_gateway_action())
        );
        try (Connection connection = oracleConnection();
             Statement jdbcStatement = connection.createStatement();
             ResultSet ignored = jdbcStatement.executeQuery(statement)) {
            return Map.of("status", "unexpected_success", "type", "sql_error", "statement", statement);
        } catch (SQLException exception) {
            LOG.error(
                "sql_error_simulated vendor_code={} sql_state={} message={}",
                exception.getErrorCode(), exception.getSQLState(), exception.getMessage(), exception
            );
            throw exception;
        }
    }

    @PostMapping("/api/java-apm/simulate/attack")
    public Map<String, Object> simulateAttack(@RequestBody(required = false) AttackRequest request)
        throws InterruptedException {
        String technique = request == null || nullToEmpty(request.technique_id()).isBlank()
            ? "T1059"
            : request.technique_id();
        String sourceIp = request == null || nullToEmpty(request.source_ip()).isBlank()
            ? "203.0.113." + ThreadLocalRandom.current().nextInt(10, 250)
            : request.source_ip();
        long latency = simulateLatency(60, 220);
        LOG.warn(
            "attack_path_java_segment technique_id={} tactic={} source_ip={} latency_ms={} attack_id={} run_id={} request_id={} api_gateway_request_id={} api_gateway_route={} api_gateway_action={}",
            technique,
            request == null ? "execution" : nullToEmpty(request.tactic()),
            sourceIp,
            latency,
            request == null ? "" : nullToEmpty(request.attack_id()),
            request == null ? "" : nullToEmpty(request.run_id()),
            request == null ? "" : nullToEmpty(request.request_id()),
            request == null ? "" : nullToEmpty(request.api_gateway_request_id()),
            request == null ? "" : nullToEmpty(request.api_gateway_route()),
            request == null ? "" : nullToEmpty(request.api_gateway_action())
        );
        return Map.of(
            "status", "completed",
            "type", "attack_java_segment",
            "mitre.technique_id", technique,
            "mitre.tactic", request == null ? "execution" : nullToEmpty(request.tactic()),
            "attack.source_ip", sourceIp,
            "latency_ms", latency
        );
    }

    // Sleep path — thread stays busy; shows as request-thread resource consumption.
    @GetMapping("/slow")
    public Map<String, Object> slow() throws InterruptedException {
        long ms = 200L + ThreadLocalRandom.current().nextLong(800);
        Thread.sleep(ms);
        return Map.of("slept_ms", ms);
    }

    // Allocation path — creates garbage to exercise Young GC.
    @GetMapping("/allocate")
    public Map<String, Object> allocate() {
        int megabytes = 16 + ThreadLocalRandom.current().nextInt(48);
        return Map.of("allocated_bytes", allocateMegabytes(megabytes));
    }

    private long allocateMegabytes(int megabytes) {
        byte[][] buffers = new byte[megabytes][];
        for (int i = 0; i < megabytes; i++) {
            buffers[i] = new byte[1024 * 1024];  // 1 MiB blocks
            buffers[i][0] = (byte) i;            // touch the page
        }
        long total = 0L;
        for (byte[] b : buffers) {
            total += b.length;
        }
        return total;
    }

    // Controlled error path — counts toward Apdex "frustrated" + server errors.
    @GetMapping("/error")
    public Map<String, String> error() {
        throw new IllegalStateException("intentional demo error");
    }

    @ExceptionHandler(IllegalStateException.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Map<String, Object> handleIllegalState(IllegalStateException exception) {
        LOG.error("controlled_java_error message={}", exception.getMessage(), exception);
        return Map.of(
            "status", "error",
            "error_type", exception.getClass().getSimpleName(),
            "message", exception.getMessage()
        );
    }

    @ExceptionHandler(ExternalCallSimulationException.class)
    @ResponseStatus(HttpStatus.BAD_GATEWAY)
    public Map<String, Object> handleExternalCallSimulation(ExternalCallSimulationException exception) {
        LOG.error(
            "controlled_external_error target_url={} status_code={}",
            exception.targetUrl(), exception.statusCode(), exception
        );
        return Map.of(
            "status", "error",
            "error_type", exception.getClass().getSimpleName(),
            "message", exception.getMessage(),
            "external.target_url", exception.targetUrl(),
            "external.status_code", exception.statusCode()
        );
    }

    @ExceptionHandler(SQLException.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Map<String, Object> handleSqlException(SQLException exception) {
        return Map.of(
            "status", "error",
            "error_type", exception.getClass().getSimpleName(),
            "sql.vendor_code", exception.getErrorCode(),
            "sql.state", nullToEmpty(exception.getSQLState()),
            "message", exception.getMessage()
        );
    }

    private Connection oracleConnection() throws SQLException {
        String dsn = env("ORACLE_DSN", "");
        String user = env("ORACLE_USER", "ADMIN");
        String password = env("ORACLE_PASSWORD", "");
        String walletDir = env("ORACLE_WALLET_DIR", "/opt/oracle/wallet");
        if (dsn.isBlank() || password.isBlank()) {
            throw new SQLException("ORACLE_DSN and ORACLE_PASSWORD are required for SQL error simulation", "08001", 17002);
        }
        System.setProperty("oracle.net.tns_admin", walletDir);
        String url = "jdbc:oracle:thin:@" + dsn + "?TNS_ADMIN=" + walletDir;
        return DriverManager.getConnection(url, user, password);
    }

    private long simulateLatency(int minMs, int maxMs) throws InterruptedException {
        long ms = ThreadLocalRandom.current().nextLong(minMs, maxMs + 1L);
        Thread.sleep(ms);
        return ms;
    }

    private int riskScore(PaymentAuthorizeRequest request) {
        int amountScore = (int) Math.min(55L, request.amount_minor_units() / 100_000L);
        int idempotencyScore = Math.abs(nullToEmpty(request.idempotency_key_hash()).hashCode() % 20);
        int domainScore = safeDomain(request.customer_email_domain()).endsWith(".invalid") ? 2 : 8;
        return Math.max(0, Math.min(99, amountScore + idempotencyScore + domainScore));
    }

    private int verificationRiskScore(PaymentVerifyRequest request) {
        int amountScore = (int) Math.min(45L, request.amount_minor_units() / 150_000L);
        int contextScore = Math.max(0, Math.min(99, request.context_risk_score()));
        int reasonScore = 0;
        String reasons = nullToEmpty(request.risk_reasons()).toLowerCase();
        if (reasons.contains("issuer_decline_test_card")) reasonScore += 90;
        if (reasons.contains("invalid_luhn")) reasonScore += 80;
        if (reasons.contains("expired_card")) reasonScore += 70;
        if (reasons.contains("missing_wallet_token")) reasonScore += 80;
        if (reasons.contains("invalid_cvv")) reasonScore += 35;
        if (reasons.contains("unsupported")) reasonScore += 30;
        int idempotencyScore = Math.abs(nullToEmpty(request.idempotency_key_hash()).hashCode() % 15);
        int domainScore = safeDomain(request.customer_email_domain()).endsWith(".invalid") ? 2 : 8;
        return Math.max(0, Math.min(99, Math.max(contextScore, amountScore + reasonScore + idempotencyScore + domainScore)));
    }

    private boolean deterministicIssue(String idempotencyHash, long orderId, int modulus) {
        String seed = nullToEmpty(idempotencyHash) + ":" + orderId;
        if (seed.isBlank() || modulus <= 0) {
            return false;
        }
        return Math.floorMod(seed.hashCode(), modulus) == 0;
    }

    private String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static String safeDomain(String value) {
        String domain = nullToEmpty(value).toLowerCase().replaceAll("[^a-z0-9._-]", "");
        return domain.isBlank() ? "unknown" : domain;
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    public record QuoteRequest(
        long product_id,
        int quantity,
        long base_price_minor_units
    ) {}

    public record PaymentAuthorizeRequest(
        long order_id,
        long amount_minor_units,
        String currency,
        String customer_email_domain,
        String idempotency_key_hash,
        String simulation_mode
    ) {}

    public record PaymentVerifyRequest(
        long order_id,
        long amount_minor_units,
        String currency,
        String customer_email_domain,
        String idempotency_key_hash,
        String payment_method,
        String payment_network,
        int context_risk_score,
        String risk_reasons,
        String simulation_mode
    ) {}

    public record SimulationRequest(
        long duration_ms,
        int megabytes
    ) {}

    public record ExternalErrorRequest(
        int status_code,
        String target_url,
        String scenario,
        String attack_id,
        String run_id,
        String request_id,
        String api_gateway_request_id,
        String api_gateway_route,
        String api_gateway_action
    ) {}

    public record SqlErrorRequest(
        String error_code,
        String scenario,
        String attack_id,
        String run_id,
        String request_id,
        String api_gateway_request_id,
        String api_gateway_route,
        String api_gateway_action
    ) {}

    public record AttackRequest(
        String technique_id,
        String tactic,
        String source_ip,
        String attack_id,
        String run_id,
        String request_id,
        String api_gateway_request_id,
        String api_gateway_route,
        String api_gateway_action
    ) {}

    public static final class ExternalCallSimulationException extends RuntimeException {
        private final String targetUrl;
        private final int statusCode;

        ExternalCallSimulationException(String message, String targetUrl, int statusCode) {
            super(message);
            this.targetUrl = targetUrl;
            this.statusCode = statusCode;
        }

        String targetUrl() {
            return targetUrl;
        }

        int statusCode() {
            return statusCode;
        }
    }
}
