package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Config struct {
	AppName                 string
	ServiceName             string
	Environment             string
	Port                    int
	OracleDSN               string
	OracleUser              string
	OraclePassword          string
	OracleWalletDir         string
	OracleWalletPassword    string
	EnterpriseCRMURL        string
	APMEndpoint             string
	APMPrivateDataKey       string
	LogLevel                string
	PollSeconds             int
	AllowedOrigins          []string
	WorkflowFaultyQuery     bool
	SelectAIProfileName     string
	SelectAITimeoutSeconds  int
}

func Load() (Config, error) {
	cfg := Config{
		AppName:                env("WORKFLOW_APP_NAME", "octo-workflow-gateway"),
		ServiceName:            env("WORKFLOW_SERVICE_NAME", "octo-workflow-gateway"),
		Environment:            env("ENVIRONMENT", "development"),
		Port:                   envInt("WORKFLOW_PORT", 8090),
		OracleDSN:              strings.TrimSpace(os.Getenv("ORACLE_DSN")),
		OracleUser:             env("ORACLE_USER", "ADMIN"),
		OraclePassword:         strings.TrimSpace(os.Getenv("ORACLE_PASSWORD")),
		OracleWalletDir:        env("ORACLE_WALLET_DIR", "/opt/oracle/wallet"),
		OracleWalletPassword:   strings.TrimSpace(os.Getenv("ORACLE_WALLET_PASSWORD")),
		EnterpriseCRMURL:       strings.TrimSpace(os.Getenv("ENTERPRISE_CRM_URL")),
		APMEndpoint:            strings.TrimSpace(os.Getenv("OCI_APM_ENDPOINT")),
		APMPrivateDataKey:      strings.TrimSpace(os.Getenv("OCI_APM_PRIVATE_DATAKEY")),
		LogLevel:               env("WORKFLOW_LOG_LEVEL", "info"),
		PollSeconds:            envInt("WORKFLOW_POLL_SECONDS", 90),
		AllowedOrigins:         csvEnv("WORKFLOW_ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"),
		WorkflowFaultyQuery:    envBool("WORKFLOW_FAULTY_QUERY_ENABLED", false),
		SelectAIProfileName:    strings.TrimSpace(os.Getenv("SELECTAI_PROFILE_NAME")),
		SelectAITimeoutSeconds: envInt("SELECTAI_TIMEOUT_SECONDS", 30),
	}
	if cfg.OracleDSN == "" {
		return Config{}, fmt.Errorf("ORACLE_DSN is required for workflow gateway")
	}
	if cfg.OraclePassword == "" {
		return Config{}, fmt.Errorf("ORACLE_PASSWORD is required for workflow gateway")
	}
	if cfg.PollSeconds < 30 {
		cfg.PollSeconds = 30
	}
	return cfg, nil
}

func env(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func envInt(key string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return value
}

func envBool(key string, fallback bool) bool {
	raw := strings.TrimSpace(strings.ToLower(os.Getenv(key)))
	if raw == "" {
		return fallback
	}
	switch raw {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}

func csvEnv(key, fallback string) []string {
	raw := env(key, fallback)
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}
