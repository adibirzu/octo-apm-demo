package telemetry

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
)

type Config struct {
	ServiceName       string
	AppName           string
	Environment       string
	APMEndpoint       string
	APMPrivateDataKey string
}

type Telemetry struct {
	tracerProvider *sdktrace.TracerProvider
	serviceName    string
	appName        string
	environment    string
}

func New(ctx context.Context, cfg Config) (*Telemetry, error) {
	res, err := resource.Merge(
		resource.Default(),
		resource.NewSchemaless(
			attribute.String("service.name", cfg.ServiceName),
			attribute.String("app.name", cfg.AppName),
			attribute.String("deployment.environment", cfg.Environment),
			attribute.String("cloud.provider", "oci"),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("create resource: %w", err)
	}

	provider := sdktrace.NewTracerProvider(
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
	)

	if cfg.APMEndpoint != "" && cfg.APMPrivateDataKey != "" {
		endpoint := fmt.Sprintf("%s/20200101/opentelemetry/private/v1/traces", trimAPMBase(cfg.APMEndpoint))
		exporter, exportErr := otlptracehttp.New(
			ctx,
			otlptracehttp.WithEndpointURL(endpoint),
			otlptracehttp.WithHeaders(map[string]string{"Authorization": "dataKey " + cfg.APMPrivateDataKey}),
		)
		if exportErr != nil {
			return nil, fmt.Errorf("create otlp exporter: %w", exportErr)
		}
		provider.RegisterSpanProcessor(sdktrace.NewBatchSpanProcessor(exporter))
	}

	otel.SetTracerProvider(provider)
	otel.SetTextMapPropagator(propagation.TraceContext{})

	return &Telemetry{
		tracerProvider: provider,
		serviceName:    cfg.ServiceName,
		appName:        cfg.AppName,
		environment:    cfg.Environment,
	}, nil
}

func (t *Telemetry) Shutdown(ctx context.Context) error {
	if t == nil || t.tracerProvider == nil {
		return nil
	}
	return t.tracerProvider.Shutdown(ctx)
}

func (t *Telemetry) Tracer(name string) trace.Tracer {
	return otel.Tracer(name)
}

func (t *Telemetry) HTTPMiddleware(name string, next http.Handler) http.Handler {
	return otelhttp.NewHandler(next, name)
}

func Log(ctx context.Context, level string, message string, extra map[string]any) {
	entry := map[string]any{
		"timestamp":              time.Now().UTC().Format(time.RFC3339Nano),
		"level":                  level,
		"message":                message,
		"oracleApmTraceId":       TraceID(ctx),
		"trace_id":               TraceID(ctx),
		"service.name":           os.Getenv("WORKFLOW_SERVICE_NAME"),
		"deployment.environment": os.Getenv("ENVIRONMENT"),
	}
	for key, value := range extra {
		entry[key] = value
	}
	payload, err := json.Marshal(entry)
	if err != nil {
		slog.Error("marshal log entry", "error", err)
		log.Printf(`{"level":"ERROR","message":"marshal log entry","error":"%v"}`, err)
		return
	}
	log.Println(string(payload))
}

func TraceID(ctx context.Context) string {
	spanCtx := trace.SpanContextFromContext(ctx)
	if !spanCtx.IsValid() {
		return ""
	}
	return spanCtx.TraceID().String()
}

func trimAPMBase(endpoint string) string {
	value := endpoint
	if idx := len(value); idx > 0 {
		value = strings.TrimRight(value, "/")
	}
	if cut := strings.Index(value, "/20200101"); cut >= 0 {
		return value[:cut]
	}
	return value
}
