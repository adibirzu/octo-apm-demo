ARG OTEL_COLLECTOR_VERSION=0.110.0
FROM otel/opentelemetry-collector-contrib:${OTEL_COLLECTOR_VERSION}

# Config is mounted at /etc/otelcol-contrib/config.yaml in OKE/compose,
# but bake a sensible default for one-off runs.
COPY config/otel-collector.yaml /etc/otelcol-contrib/config.yaml

# OTLP gRPC + OTLP HTTP + health + pprof + zpages + collector self-metrics
EXPOSE 4317 4318 13133 1777 55679 8888

# Default cmd from the upstream image already references /etc/otelcol-
# contrib/config.yaml — no override needed.
