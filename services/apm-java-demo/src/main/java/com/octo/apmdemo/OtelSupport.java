package com.octo.apmdemo;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import jakarta.servlet.http.HttpServletRequest;
import java.time.Duration;
import java.util.Collections;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class OtelSupport {
    private static final Logger LOG = LoggerFactory.getLogger(OtelSupport.class);
    private static final TextMapGetter<HttpServletRequest> REQUEST_GETTER = new TextMapGetter<>() {
        @Override
        public Iterable<String> keys(HttpServletRequest carrier) {
            if (carrier == null) {
                return Collections.emptyList();
            }
            return Collections.list(carrier.getHeaderNames());
        }

        @Override
        public String get(HttpServletRequest carrier, String key) {
            return carrier == null ? null : carrier.getHeader(key);
        }
    };

    private static volatile OpenTelemetry openTelemetry = OpenTelemetry.noop();
    private static volatile Tracer tracer = openTelemetry.getTracer("octo-apm-java-demo");

    private OtelSupport() {}

    static void initialize() {
        String endpoint = env("OCI_APM_ENDPOINT", "");
        String privateDataKey = env("OCI_APM_PRIVATE_DATAKEY", "");
        String serviceName = env("OCI_APM_SERVICE_NAME", "octo-java-app-server");
        if (endpoint.isBlank() || privateDataKey.isBlank()) {
            LOG.warn("OCI APM OTLP exporter disabled for {} because endpoint/data key is missing", serviceName);
            return;
        }

        String baseUrl = endpoint.replaceFirst("/+$", "").split("/20200101")[0];
        String tracesEndpoint = baseUrl + "/20200101/opentelemetry/private/v1/traces";
        OtlpHttpSpanExporter exporter = OtlpHttpSpanExporter.builder()
            .setEndpoint(tracesEndpoint)
            .addHeader("Authorization", "dataKey " + privateDataKey)
            .setTimeout(Duration.ofSeconds(10))
            .build();

        SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
            .setResource(Resource.getDefault().merge(Resource.create(resourceAttributes(serviceName))))
            .addSpanProcessor(BatchSpanProcessor.builder(exporter).build())
            .build();

        OpenTelemetrySdk sdk = OpenTelemetrySdk.builder()
            .setTracerProvider(tracerProvider)
            .setPropagators(ContextPropagators.create(W3CTraceContextPropagator.getInstance()))
            .build();

        try {
            GlobalOpenTelemetry.set(sdk);
        } catch (IllegalStateException alreadySet) {
            LOG.debug("GlobalOpenTelemetry was already initialized; using local SDK instance");
        }
        openTelemetry = sdk;
        tracer = sdk.getTracer("octo-apm-java-demo", "1.0.0");
        Runtime.getRuntime().addShutdownHook(new Thread(tracerProvider::close));
        LOG.info("OCI APM OTLP trace exporter configured for service={} endpoint={}", serviceName, tracesEndpoint);
    }

    static Tracer tracer() {
        return tracer;
    }

    static Context extract(HttpServletRequest request) {
        return openTelemetry.getPropagators()
            .getTextMapPropagator()
            .extract(Context.current(), request, REQUEST_GETTER);
    }

    private static Attributes resourceAttributes(String serviceName) {
        AttributesBuilder builder = Attributes.builder()
            .put("service.name", serviceName)
            .put("service.namespace", env("SERVICE_NAMESPACE", "octo"))
            .put("service.instance.id", env("SERVICE_INSTANCE_ID", env("HOSTNAME", "unknown")))
            .put("service.version", "1.0.0")
            .put("deployment.environment", env("DEPLOYMENT_ENVIRONMENT", "production"))
            .put("app.runtime", "oke")
            .put("app.module", "java-payment-gateway")
            .put("cloud.provider", "oci")
            .put("oci.demo.stack", env("DEMO_STACK_NAME", "octo-apm-demo"));

        String resourceAttributes = env("OTEL_RESOURCE_ATTRIBUTES", "");
        if (!resourceAttributes.isBlank()) {
            for (String pair : resourceAttributes.split(",")) {
                String[] parts = pair.split("=", 2);
                if (parts.length == 2 && !parts[0].isBlank() && !parts[1].isBlank()) {
                    builder.put(parts[0].trim(), parts[1].trim());
                }
            }
        }
        return builder.build();
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
