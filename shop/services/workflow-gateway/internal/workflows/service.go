package workflows

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"go.opentelemetry.io/otel/attribute"

	"octo-drone-shop/services/workflow-gateway/internal/config"
	"octo-drone-shop/services/workflow-gateway/internal/database"
	"octo-drone-shop/services/workflow-gateway/internal/telemetry"
)

type QuerySpec struct {
	Name            string `json:"name"`
	Label           string `json:"label"`
	ComponentName   string `json:"component_name"`
	ActionName      string `json:"action_name"`
	Description     string `json:"description"`
	SQL             string `json:"sql"`
	ExpectedFailure bool   `json:"expected_failure"`
}

type Service struct {
	cfg       config.Config
	store     *database.Store
	telemetry *telemetry.Telemetry
	catalog   map[string]QuerySpec

	mu        sync.RWMutex
	lastRun   time.Time
	lastError string
}

func New(cfg config.Config, store *database.Store, tel *telemetry.Telemetry) *Service {
	return &Service{
		cfg:       cfg,
		store:     store,
		telemetry: tel,
		catalog: map[string]QuerySpec{
			"orders_backlog": {
				Name:          "orders_backlog",
				Label:         "Orders Backlog",
				ComponentName: "drone-shop",
				ActionName:    "query",
				Description:   "Summarizes live order status and revenue distribution.",
				SQL: "SELECT status, COUNT(*) AS order_count, ROUND(COALESCE(SUM(total), 0), 2) AS total_value " +
					"FROM orders GROUP BY status ORDER BY total_value DESC",
			},
			"inventory_watch": {
				Name:          "inventory_watch",
				Label:         "Inventory Watch",
				ComponentName: "drone-shop",
				ActionName:    "query",
				Description:   "Lists active products that are near backorder so operations can react early.",
				SQL: "SELECT sku, name, stock, category FROM products " +
					"WHERE is_active = 1 AND stock <= 10 ORDER BY stock ASC, name ASC FETCH FIRST 25 ROWS ONLY",
			},
			"crm_customer_mix": {
				Name:          "crm_customer_mix",
				Label:         "CRM Customer Mix",
				ComponentName: "enterprise-crm-portal",
				ActionName:    "query",
				Description:   "Correlates CRM-linked customers with order volume in the shared ATP.",
				SQL: "SELECT c.company, c.email, COUNT(o.id) AS order_count, ROUND(COALESCE(SUM(o.total), 0), 2) AS spend " +
					"FROM customers c LEFT JOIN orders o ON o.customer_id = c.id " +
					"WHERE lower(COALESCE(DBMS_LOB.SUBSTR(c.notes, 4000, 1), '')) LIKE '%enterprise-crm-portal%' " +
					"GROUP BY c.company, c.email ORDER BY spend DESC FETCH FIRST 20 ROWS ONLY",
			},
			"component_topology": {
				Name:          "component_topology",
				Label:         "Component Topology",
				ComponentName: "oracle-atp",
				ActionName:    "query",
				Description:   "Builds a backend-centric component rollup across orders, customers, and query history.",
				SQL: "SELECT component_name, COUNT(*) AS observations, MAX(observed_at) AS latest_observation " +
					"FROM component_snapshots GROUP BY component_name ORDER BY latest_observation DESC FETCH FIRST 20 ROWS ONLY",
			},
			"broken_orders_probe": {
				Name:            "broken_orders_probe",
				Label:           "Broken Orders Probe",
				ComponentName:   "oracle-atp",
				ActionName:      "faulty_query",
				Description:     "Intentionally invalid query for DB Management and OPSI investigation.",
				SQL:             "SELECT non_existing_column FROM orders FETCH FIRST 5 ROWS ONLY",
				ExpectedFailure: true,
			},
			"missing_table_probe": {
				Name:            "missing_table_probe",
				Label:           "Missing Table Probe",
				ComponentName:   "oracle-atp",
				ActionName:      "faulty_query",
				Description:     "Intentionally references a missing relation to surface parse failures in ATP diagnostics.",
				SQL:             "SELECT * FROM order_debug_ghost FETCH FIRST 5 ROWS ONLY",
				ExpectedFailure: true,
			},
		},
	}
}

func (s *Service) Catalog() []QuerySpec {
	items := make([]QuerySpec, 0, len(s.catalog))
	for _, item := range s.catalog {
		items = append(items, item)
	}
	return items
}

func (s *Service) Store() *database.Store {
	return s.store
}

func (s *Service) Overview(ctx context.Context) (map[string]any, error) {
	payload, err := s.store.Overview(ctx)
	if err != nil {
		return nil, err
	}
	s.mu.RLock()
	lastRun := s.lastRun
	lastError := s.lastError
	s.mu.RUnlock()
	lastRunText := ""
	if !lastRun.IsZero() {
		lastRunText = lastRun.UTC().Format(time.RFC3339)
	}

	payload["scheduler"] = map[string]any{
		"poll_seconds": s.cfg.PollSeconds,
		"last_run_at":  lastRunText,
		"last_error":   lastError,
	}
	payload["gateway"] = map[string]any{
		"service_name":            s.cfg.ServiceName,
		"faulty_query_enabled":    s.cfg.WorkflowFaultyQuery,
		"selectai_configured":     s.cfg.SelectAIProfileName != "",
		"selectai_profile_name":   s.cfg.SelectAIProfileName,
		"crm_endpoint_configured": s.cfg.EnterpriseCRMURL != "",
	}
	return payload, nil
}

func (s *Service) QueryExecutions(ctx context.Context, limit int) ([]map[string]any, error) {
	return s.store.QueryExecutions(ctx, limit)
}

func (s *Service) ComponentSnapshots(ctx context.Context, limit int) ([]map[string]any, error) {
	return s.store.ComponentSnapshots(ctx, limit)
}

func (s *Service) RunQuery(ctx context.Context, name string, scheduleMode string) (database.QueryResult, error) {
	spec, ok := s.catalog[name]
	if !ok {
		return database.QueryResult{}, fmt.Errorf("query %q is not defined", name)
	}

	ctx, span := s.telemetry.Tracer("workflow-gateway").Start(ctx, "workflow.query."+spec.Name)
	defer span.End()
	span.SetAttributes(
		attribute.String("app.module", "workflow-gateway"),
		attribute.String("workflow.query_name", spec.Name),
		attribute.String("workflow.component", spec.ComponentName),
		attribute.String("db.statement.preview", spec.SQL),
	)

	result := s.store.RunQuery(ctx, spec.Name, spec.ComponentName, spec.ActionName, spec.SQL, scheduleMode, spec.ExpectedFailure, "")
	span.SetAttributes(
		attribute.String("workflow.status", result.Status),
		attribute.Float64("db.client.execution_time_ms", result.DurationMS),
		attribute.Int("db.row_count", result.RowCount),
	)
	if result.Status == "error" && !spec.ExpectedFailure {
		return result, fmt.Errorf(result.ErrorMessage)
	}
	return result, nil
}

func (s *Service) RunSelectAI(ctx context.Context, prompt string, action string) (database.QueryResult, error) {
	if s.cfg.SelectAIProfileName == "" {
		return database.QueryResult{}, fmt.Errorf("SELECTAI_PROFILE_NAME is not configured")
	}
	ctx, span := s.telemetry.Tracer("workflow-gateway").Start(ctx, "workflow.selectai."+action)
	defer span.End()
	span.SetAttributes(
		attribute.String("selectai.action", action),
		attribute.String("selectai.profile", s.cfg.SelectAIProfileName),
	)
	result := s.store.GenerateSelectAI(ctx, prompt, action, s.cfg.SelectAIProfileName)
	span.SetAttributes(
		attribute.String("workflow.status", result.Status),
		attribute.Float64("db.client.execution_time_ms", result.DurationMS),
	)
	if result.Status == "error" {
		return result, fmt.Errorf(result.ErrorMessage)
	}
	return result, nil
}

func (s *Service) StartScheduler(ctx context.Context) {
	go func() {
		ticker := time.NewTicker(time.Duration(s.cfg.PollSeconds) * time.Second)
		defer ticker.Stop()

		s.runScheduledSweep(ctx)
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				s.runScheduledSweep(ctx)
			}
		}
	}()
}

func (s *Service) runScheduledSweep(parent context.Context) {
	ctx, span := s.telemetry.Tracer("workflow-gateway").Start(parent, "workflow.scheduler.sweep")
	defer span.End()

	started := time.Now()
	for _, key := range []string{"orders_backlog", "inventory_watch", "crm_customer_mix"} {
		if _, err := s.RunQuery(ctx, key, "scheduled"); err != nil {
			s.setLastError(err.Error())
			telemetry.Log(ctx, "ERROR", "scheduled workflow query failed", map[string]any{
				"workflow.query_name": key,
				"error.message":       err.Error(),
			})
		}
	}

	if s.cfg.WorkflowFaultyQuery {
		if _, err := s.RunQuery(ctx, "broken_orders_probe", "scheduled"); err != nil {
			telemetry.Log(ctx, "WARNING", "scheduled faulty probe executed", map[string]any{
				"workflow.query_name": "broken_orders_probe",
				"error.message":       err.Error(),
			})
		}
	}

	overview, err := s.store.Overview(ctx)
	if err == nil {
		s.recordSnapshots(ctx, overview)
	} else {
		s.setLastError(err.Error())
	}

	durationMS := float64(time.Since(started).Microseconds()) / 1000.0
	s.store.RecordWorkflowRun(ctx, database.WorkflowRun{
		WorkflowKey:   "scheduled_backend_sweep",
		WorkflowLabel: "Scheduled Backend Sweep",
		ScheduleMode:  "scheduled",
		Status:        "success",
		ResultSummary: "orders, crm, inventory, and component snapshots refreshed",
		TraceID:       telemetry.TraceID(ctx),
		DurationMS:    durationMS,
	})

	s.mu.Lock()
	s.lastRun = time.Now().UTC()
	s.lastError = ""
	s.mu.Unlock()
}

func (s *Service) recordSnapshots(ctx context.Context, overview map[string]any) {
	dbLatency := 0.0
	s.store.RecordComponentSnapshot(ctx, database.ComponentSnapshot{
		ComponentName: "oracle-atp",
		ComponentType: "database",
		Status:        "connected",
		LatencyMS:     dbLatency,
		Details:       "Shared ATP is reachable from workflow gateway",
		TraceID:       telemetry.TraceID(ctx),
	})

	if orders, ok := overview["orders"]; ok {
		details := marshalJSON(orders)
		s.store.RecordComponentSnapshot(ctx, database.ComponentSnapshot{
			ComponentName: "drone-shop",
			ComponentType: "application",
			Status:        "healthy",
			Details:       details,
			TraceID:       telemetry.TraceID(ctx),
		})
	}
	if crm, ok := overview["crm"]; ok {
		details := marshalJSON(crm)
		s.store.RecordComponentSnapshot(ctx, database.ComponentSnapshot{
			ComponentName: "enterprise-crm-portal",
			ComponentType: "integration",
			Status:        "healthy",
			Details:       details,
			TraceID:       telemetry.TraceID(ctx),
		})
	}
}

func (s *Service) setLastError(message string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.lastError = message
}

func marshalJSON(value any) string {
	payload, err := json.Marshal(value)
	if err != nil {
		return ""
	}
	return string(payload)
}
