/*
 * octo-apm-java-demo — a tiny Spring Boot service whose sole purpose is
 * to populate the OCI APM "App Servers" dashboard. The OCI APM Java
 * agent (attached via `-javaagent:` in the Dockerfile) reports:
 *
 *   - Apdex (threshold driven by spring-boot-actuator health)
 *   - Active Servers (one per running JVM)
 *   - Server restarts
 *   - Resource consumption per request thread
 *   - Server request rate
 *   - App server CPU load
 *   - JVM info: Name, version, Young/Old GC time
 *
 * None of the Python services (shop, crm) can populate these metrics
 * because the OCI APM Python SDK does not emit server-info. Hence this
 * service exists — it is NOT part of any business flow.
 */
package com.octo.apmdemo;

import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class App {

    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }

    @GetMapping("/")
    public Map<String, Object> root() {
        return Map.of(
            "service", "octo-apm-java-demo",
            "purpose", "populate OCI APM App Servers view",
            "jvm.version", System.getProperty("java.version"),
            "jvm.name", System.getProperty("java.vm.name"),
            "endpoints", java.util.List.of("/", "/healthz", "/slow", "/allocate", "/error")
        );
    }

    @GetMapping("/healthz")
    public Map<String, String> healthz() {
        return Map.of("status", "up");
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
        byte[][] buffers = new byte[megabytes][];
        for (int i = 0; i < megabytes; i++) {
            buffers[i] = new byte[1024 * 1024];  // 1 MiB blocks
            buffers[i][0] = (byte) i;            // touch the page
        }
        long total = 0L;
        for (byte[] b : buffers) {
            total += b.length;
        }
        return Map.of("allocated_bytes", total);
    }

    // Controlled error path — counts toward Apdex "frustrated" + server errors.
    @GetMapping("/error")
    public Map<String, String> error() {
        throw new IllegalStateException("intentional demo error");
    }
}
