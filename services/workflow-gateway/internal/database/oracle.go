package database

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	goora "github.com/sijms/go-ora/v2"

	"octo-drone-shop/services/workflow-gateway/internal/config"
	"octo-drone-shop/services/workflow-gateway/internal/telemetry"
)

type Store struct {
	db          *sql.DB
	serviceName string
}

type QueryResult struct {
	QueryName       string           `json:"query_name"`
	ComponentName   string           `json:"component_name"`
	ActionName      string           `json:"action_name"`
	Status          string           `json:"status"`
	QueryText       string           `json:"query_text"`
	PromptText      string           `json:"prompt_text,omitempty"`
	ExpectedFailure bool             `json:"expected_failure"`
	RowCount        int              `json:"row_count"`
	DurationMS      float64          `json:"duration_ms"`
	ErrorMessage    string           `json:"error_message,omitempty"`
	TraceID         string           `json:"trace_id,omitempty"`
	Rows            []map[string]any `json:"rows,omitempty"`
}

type WorkflowRun struct {
	WorkflowKey   string
	WorkflowLabel string
	ScheduleMode  string
	Status        string
	ResultSummary string
	TraceID       string
	DurationMS    float64
}

type ComponentSnapshot struct {
	ComponentName string
	ComponentType string
	Status        string
	LatencyMS     float64
	Details       string
	TraceID       string
}

func New(cfg config.Config) (*Store, error) {
	host, port, service, err := resolveWalletTarget(cfg.OracleWalletDir, cfg.OracleDSN)
	if err != nil {
		return nil, err
	}

	options := map[string]string{
		"AUTH TYPE": "TCPS",
		"SSL":       "true",
	}
	if cfg.OracleWalletDir != "" {
		options["WALLET"] = cfg.OracleWalletDir
	}
	if cfg.OracleWalletPassword != "" {
		options["WALLET PASSWORD"] = cfg.OracleWalletPassword
	}

	dsn := goora.BuildUrl(host, port, service, cfg.OracleUser, cfg.OraclePassword, options)
	db, err := sql.Open("oracle", dsn)
	if err != nil {
		return nil, fmt.Errorf("open oracle connection: %w", err)
	}
	db.SetConnMaxLifetime(30 * time.Minute)
	db.SetMaxIdleConns(4)
	db.SetMaxOpenConns(12)

	return &Store{db: db, serviceName: cfg.ServiceName}, nil
}

func (s *Store) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db.Close()
}

func (s *Store) Ping(ctx context.Context) error {
	return s.db.PingContext(ctx)
}

func (s *Store) RunQuery(ctx context.Context, queryName string, componentName string, actionName string, queryText string, scheduleMode string, expectedFailure bool, promptText string) QueryResult {
	result := QueryResult{
		QueryName:       queryName,
		ComponentName:   componentName,
		ActionName:      actionName,
		QueryText:       queryText,
		PromptText:      promptText,
		ExpectedFailure: expectedFailure,
		TraceID:         telemetry.TraceID(ctx),
	}
	started := time.Now()
	_ = s.setSessionContext(ctx, actionName+"."+queryName, result.TraceID)
	rows, err := queryRows(ctx, s.db, queryText)
	result.DurationMS = roundDurationMS(time.Since(started))

	if err != nil {
		result.Status = "error"
		result.ErrorMessage = err.Error()
	} else {
		result.Status = "success"
		result.RowCount = len(rows)
		result.Rows = rows
	}

	s.recordQueryExecution(ctx, result, scheduleMode)
	return result
}

func (s *Store) GenerateSelectAI(ctx context.Context, prompt string, action string, profileName string) QueryResult {
	const sqlText = "SELECT DBMS_CLOUD_AI.GENERATE(prompt => :1, profile_name => :2, action => :3) AS RESULT FROM dual"
	result := QueryResult{
		QueryName:     "select_ai_generate",
		ComponentName: "oracle-atp",
		ActionName:    action,
		QueryText:     sqlText,
		PromptText:    prompt,
		TraceID:       telemetry.TraceID(ctx),
	}
	started := time.Now()
	_ = s.setSessionContext(ctx, "selectai."+action, result.TraceID)

	var generated string
	err := s.db.QueryRowContext(ctx, sqlText, prompt, profileName, action).Scan(&generated)
	result.DurationMS = roundDurationMS(time.Since(started))
	if err != nil {
		result.Status = "error"
		result.ErrorMessage = err.Error()
	} else {
		result.Status = "success"
		result.RowCount = 1
		result.Rows = []map[string]any{{"generated": generated}}
	}
	s.recordQueryExecution(ctx, result, "manual")
	return result
}

func (s *Store) RecordWorkflowRun(ctx context.Context, payload WorkflowRun) {
	const stmt = "" +
		"INSERT INTO workflow_runs (workflow_key, workflow_label, source_service, schedule_mode, status, result_summary, trace_id, duration_ms, completed_at) " +
		"VALUES (:1, :2, :3, :4, :5, :6, :7, :8, CURRENT_TIMESTAMP)"
	_, _ = s.db.ExecContext(
		ctx,
		stmt,
		payload.WorkflowKey,
		payload.WorkflowLabel,
		s.serviceName,
		payload.ScheduleMode,
		payload.Status,
		payload.ResultSummary,
		payload.TraceID,
		payload.DurationMS,
	)
}

func (s *Store) RecordComponentSnapshot(ctx context.Context, payload ComponentSnapshot) {
	const stmt = "" +
		"INSERT INTO component_snapshots (component_name, component_type, status, source_service, latency_ms, details, trace_id) " +
		"VALUES (:1, :2, :3, :4, :5, :6, :7)"
	_, _ = s.db.ExecContext(
		ctx,
		stmt,
		payload.ComponentName,
		payload.ComponentType,
		payload.Status,
		s.serviceName,
		payload.LatencyMS,
		payload.Details,
		payload.TraceID,
	)
}

func (s *Store) Overview(ctx context.Context) (map[string]any, error) {
	queries := map[string]string{
		"orders": "SELECT COUNT(*) AS order_count, ROUND(COALESCE(SUM(total), 0), 2) AS revenue, " +
			"COUNT(CASE WHEN status = 'processing' THEN 1 END) AS processing_count FROM orders",
		"crm": "SELECT COUNT(*) AS customer_count, " +
			"COUNT(CASE WHEN lower(notes) LIKE '%enterprise-crm-portal%' THEN 1 END) AS crm_linked FROM customers",
		"inventory": "SELECT COUNT(*) AS low_stock_count FROM products WHERE is_active = 1 AND stock <= 10",
	}

	response := map[string]any{}
	for key, sqlText := range queries {
		rows, err := queryRows(ctx, s.db, sqlText)
		if err != nil {
			return nil, err
		}
		if len(rows) > 0 {
			response[key] = rows[0]
		}
	}

	recentQueries, err := queryRows(ctx, s.db,
		"SELECT id, query_name, component_name, action_name, status, expected_failure, row_count, duration_ms, "+
			"error_message, trace_id, created_at FROM query_executions ORDER BY created_at DESC FETCH FIRST 12 ROWS ONLY")
	if err != nil {
		return nil, err
	}
	recentRuns, err := queryRows(ctx, s.db,
		"SELECT id, workflow_key, workflow_label, schedule_mode, status, result_summary, trace_id, duration_ms, completed_at "+
			"FROM workflow_runs ORDER BY completed_at DESC FETCH FIRST 12 ROWS ONLY")
	if err != nil {
		return nil, err
	}
	components, err := queryRows(ctx, s.db,
		"SELECT component_name, component_type, status, latency_ms, details, trace_id, observed_at FROM component_snapshots "+
			"ORDER BY observed_at DESC FETCH FIRST 12 ROWS ONLY")
	if err != nil {
		return nil, err
	}
	response["recent_queries"] = recentQueries
	response["recent_workflows"] = recentRuns
	response["components"] = components
	return response, nil
}

func (s *Store) QueryExecutions(ctx context.Context, limit int) ([]map[string]any, error) {
	if limit < 1 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	sqlText := fmt.Sprintf(
		"SELECT id, query_name, component_name, source_service, schedule_mode, action_name, status, expected_failure, row_count, duration_ms, error_message, trace_id, created_at FROM query_executions ORDER BY created_at DESC FETCH FIRST %d ROWS ONLY",
		limit,
	)
	return queryRows(ctx, s.db, sqlText)
}

func (s *Store) ComponentSnapshots(ctx context.Context, limit int) ([]map[string]any, error) {
	if limit < 1 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	sqlText := fmt.Sprintf(
		"SELECT component_name, component_type, status, latency_ms, details, trace_id, observed_at FROM component_snapshots ORDER BY observed_at DESC FETCH FIRST %d ROWS ONLY",
		limit,
	)
	return queryRows(ctx, s.db, sqlText)
}

func (s *Store) setSessionContext(ctx context.Context, action string, traceID string) error {
	_, err := s.db.ExecContext(
		ctx,
		"BEGIN DBMS_APPLICATION_INFO.SET_MODULE(:1, :2); DBMS_SESSION.SET_IDENTIFIER(:3); END;",
		truncate(s.serviceName, 48),
		truncate(action, 64),
		truncate(traceID, 64),
	)
	return err
}

func (s *Store) recordQueryExecution(ctx context.Context, result QueryResult, scheduleMode string) {
	const stmt = "" +
		"INSERT INTO query_executions (query_name, component_name, source_service, schedule_mode, action_name, status, expected_failure, query_text, prompt_text, row_count, duration_ms, error_message, trace_id) " +
		"VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, :13)"
	_, _ = s.db.ExecContext(
		ctx,
		stmt,
		result.QueryName,
		result.ComponentName,
		s.serviceName,
		scheduleMode,
		result.ActionName,
		result.Status,
		boolToInt(result.ExpectedFailure),
		result.QueryText,
		result.PromptText,
		result.RowCount,
		result.DurationMS,
		result.ErrorMessage,
		result.TraceID,
	)
}

func queryRows(ctx context.Context, db *sql.DB, query string, args ...any) ([]map[string]any, error) {
	rows, err := db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	columns, err := rows.Columns()
	if err != nil {
		return nil, err
	}

	out := make([]map[string]any, 0)
	for rows.Next() {
		values := make([]any, len(columns))
		scanTargets := make([]any, len(columns))
		for i := range values {
			scanTargets[i] = &values[i]
		}
		if err := rows.Scan(scanTargets...); err != nil {
			return nil, err
		}
		row := make(map[string]any, len(columns))
		for i, column := range columns {
			row[strings.ToLower(column)] = normalizeValue(values[i])
		}
		out = append(out, row)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

func normalizeValue(value any) any {
	switch typed := value.(type) {
	case []byte:
		return string(typed)
	case time.Time:
		return typed.UTC().Format(time.RFC3339)
	default:
		return typed
	}
}

func resolveWalletTarget(walletDir string, alias string) (string, int, string, error) {
	filePath := filepath.Join(walletDir, "tnsnames.ora")
	content, err := os.ReadFile(filePath)
	if err != nil {
		return "", 0, "", fmt.Errorf("read %s: %w", filePath, err)
	}
	block, err := findAliasBlock(string(content), alias)
	if err != nil {
		return "", 0, "", err
	}
	host, err := extractRegex(block, `(?i)host\s*=\s*([^)\s]+)`)
	if err != nil {
		return "", 0, "", err
	}
	portText, err := extractRegex(block, `(?i)port\s*=\s*(\d+)`)
	if err != nil {
		return "", 0, "", err
	}
	service, err := extractRegex(block, `(?i)service_name\s*=\s*([^)\s]+)`)
	if err != nil {
		return "", 0, "", err
	}
	port, err := strconv.Atoi(portText)
	if err != nil {
		return "", 0, "", fmt.Errorf("parse wallet port %q: %w", portText, err)
	}
	return host, port, service, nil
}

func findAliasBlock(content string, alias string) (string, error) {
	pattern := regexp.MustCompile(`(?im)^` + regexp.QuoteMeta(alias) + `\s*=`)
	indexes := pattern.FindStringIndex(content)
	if indexes == nil {
		return "", fmt.Errorf("tns alias %q not found in wallet", alias)
	}
	block := content[indexes[0]:]
	next := regexp.MustCompile(`(?im)\n[A-Za-z0-9_.-]+\s*=`).FindStringIndex(block)
	if next == nil {
		return block, nil
	}
	return strings.TrimSpace(block[:next[0]+1]), nil
}

func extractRegex(content string, expression string) (string, error) {
	match := regexp.MustCompile(expression).FindStringSubmatch(content)
	if len(match) < 2 {
		return "", fmt.Errorf("pattern %q not found", expression)
	}
	return strings.TrimSpace(match[1]), nil
}

func boolToInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

func truncate(value string, size int) string {
	if len(value) <= size {
		return value
	}
	return value[:size]
}

func roundDurationMS(duration time.Duration) float64 {
	return float64(duration.Microseconds()) / 1000.0
}
