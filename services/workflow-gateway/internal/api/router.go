package api

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"octo-drone-shop/services/workflow-gateway/internal/config"
	"octo-drone-shop/services/workflow-gateway/internal/telemetry"
	"octo-drone-shop/services/workflow-gateway/internal/workflows"
)

type Router struct {
	cfg       config.Config
	service   *workflows.Service
	telemetry *telemetry.Telemetry

	requestsTotal    *prometheus.CounterVec
	requestDuration  *prometheus.HistogramVec
}

func New(cfg config.Config, service *workflows.Service, tel *telemetry.Telemetry) *Router {
	return &Router{
		cfg:       cfg,
		service:   service,
		telemetry: tel,
		requestsTotal: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "workflow_gateway_http_requests_total",
				Help: "Total HTTP requests handled by the workflow gateway.",
			},
			[]string{"route", "method", "status"},
		),
		requestDuration: promauto.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "workflow_gateway_http_request_duration_ms",
				Help:    "HTTP request duration for workflow gateway endpoints.",
				Buckets: []float64{25, 50, 100, 250, 500, 1000, 2000, 5000},
			},
			[]string{"route", "method"},
		),
	}
}

func (r *Router) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.Handle("/health", r.instrument("health", http.HandlerFunc(r.handleHealth)))
	mux.Handle("/api/workflows/catalog", r.instrument("catalog", http.HandlerFunc(r.handleCatalog)))
	mux.Handle("/api/workflows/overview", r.instrument("overview", http.HandlerFunc(r.handleOverview)))
	mux.Handle("/api/components/snapshots", r.instrument("components", http.HandlerFunc(r.handleComponents)))
	mux.Handle("/api/query-lab/executions", r.instrument("executions", http.HandlerFunc(r.handleExecutions)))
	mux.Handle("/api/query-lab/run", r.instrument("run_query", http.HandlerFunc(r.handleRunQuery)))
	mux.Handle("/api/selectai/generate", r.instrument("selectai", http.HandlerFunc(r.handleSelectAI)))
	return r.withCORS(mux)
}

func (r *Router) instrument(route string, next http.Handler) http.Handler {
	handler := http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		started := time.Now()
		recorder := &statusRecorder{ResponseWriter: w, statusCode: http.StatusOK}
		next.ServeHTTP(recorder, req)
		r.requestsTotal.WithLabelValues(route, req.Method, strconv.Itoa(recorder.statusCode)).Inc()
		r.requestDuration.WithLabelValues(route, req.Method).Observe(float64(time.Since(started).Microseconds()) / 1000.0)
	})
	return r.telemetry.HTTPMiddleware("workflow."+route, handler)
}

func (r *Router) withCORS(next http.Handler) http.Handler {
	allowed := make(map[string]struct{}, len(r.cfg.AllowedOrigins))
	for _, origin := range r.cfg.AllowedOrigins {
		allowed[origin] = struct{}{}
	}
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		origin := req.Header.Get("Origin")
		if origin != "" {
			if _, ok := allowed["*"]; ok {
				w.Header().Set("Access-Control-Allow-Origin", "*")
			} else if _, ok := allowed[origin]; ok {
				w.Header().Set("Access-Control-Allow-Origin", origin)
			}
			w.Header().Set("Vary", "Origin")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, Traceparent")
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		}
		if req.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, req)
	})
}

func (r *Router) handleHealth(w http.ResponseWriter, req *http.Request) {
	ctx, cancel := context.WithTimeout(req.Context(), 5*time.Second)
	defer cancel()
	err := r.service.Store().Ping(ctx)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"status": "error", "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"status":               "ok",
		"service":              r.cfg.ServiceName,
		"selectai_configured":  r.cfg.SelectAIProfileName != "",
		"faulty_query_enabled": r.cfg.WorkflowFaultyQuery,
	})
}

func (r *Router) handleCatalog(w http.ResponseWriter, req *http.Request) {
	if req.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"queries": r.service.Catalog()})
}

func (r *Router) handleOverview(w http.ResponseWriter, req *http.Request) {
	if req.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	payload, err := r.service.Overview(req.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (r *Router) handleComponents(w http.ResponseWriter, req *http.Request) {
	if req.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	limit := parseLimit(req.URL.Query().Get("limit"), 12)
	payload, err := r.service.ComponentSnapshots(req.Context(), limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": payload})
}

func (r *Router) handleExecutions(w http.ResponseWriter, req *http.Request) {
	if req.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	limit := parseLimit(req.URL.Query().Get("limit"), 15)
	payload, err := r.service.QueryExecutions(req.Context(), limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": payload})
}

func (r *Router) handleRunQuery(w http.ResponseWriter, req *http.Request) {
	if req.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	var payload struct {
		QueryName string `json:"query_name"`
	}
	if err := json.NewDecoder(req.Body).Decode(&payload); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "invalid payload"})
		return
	}
	payload.QueryName = strings.TrimSpace(payload.QueryName)
	if payload.QueryName == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "query_name is required"})
		return
	}
	result, err := r.service.RunQuery(req.Context(), payload.QueryName, "manual")
	if err != nil && result.ExpectedFailure {
		writeJSON(w, http.StatusOK, result)
		return
	}
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error(), "result": result})
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (r *Router) handleSelectAI(w http.ResponseWriter, req *http.Request) {
	if req.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	var payload struct {
		Prompt string `json:"prompt"`
		Action string `json:"action"`
	}
	if err := json.NewDecoder(req.Body).Decode(&payload); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "invalid payload"})
		return
	}
	payload.Prompt = strings.TrimSpace(payload.Prompt)
	payload.Action = strings.TrimSpace(payload.Action)
	if payload.Prompt == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "prompt is required"})
		return
	}
	if payload.Action == "" {
		payload.Action = "showsql"
	}
	result, err := r.service.RunSelectAI(req.Context(), payload.Prompt, payload.Action)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error(), "result": result})
		return
	}
	writeJSON(w, http.StatusOK, result)
}

type statusRecorder struct {
	http.ResponseWriter
	statusCode int
}

func (r *statusRecorder) WriteHeader(statusCode int) {
	r.statusCode = statusCode
	r.ResponseWriter.WriteHeader(statusCode)
}

func parseLimit(raw string, fallback int) int {
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	if value < 1 {
		return fallback
	}
	if value > 100 {
		return 100
	}
	return value
}

func writeJSON(w http.ResponseWriter, statusCode int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	_ = json.NewEncoder(w).Encode(payload)
}
