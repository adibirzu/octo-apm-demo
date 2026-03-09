"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(override=True)


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    return _env(key, str(default)).lower() in ("true", "1", "yes")


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    # Application
    app_name: str = field(default_factory=lambda: _env("APP_NAME", "enterprise-crm-portal"))
    brand_name: str = field(default_factory=lambda: _env("BRAND_NAME", "OCTO CRM APM"))
    app_version: str = field(default_factory=lambda: _env("APP_VERSION", "1.1.0"))
    app_port: int = field(default_factory=lambda: _env_int("APP_PORT", 8080))
    app_env: str = field(default_factory=lambda: _env("APP_ENV", "production"))
    app_secret_key: str = field(default_factory=lambda: _env("APP_SECRET_KEY", "dev-secret-key"))
    app_runtime: str = field(default_factory=lambda: _env("APP_RUNTIME", "docker"))
    service_namespace: str = field(default_factory=lambda: _env("SERVICE_NAMESPACE", "octo"))
    service_instance_id: str = field(default_factory=lambda: _env("SERVICE_INSTANCE_ID", _env("HOSTNAME", "local-dev")))
    demo_stack_name: str = field(default_factory=lambda: _env("DEMO_STACK_NAME", "octo-apm"))

    # Database — PostgreSQL (default for local dev) or Oracle ATP (OKE production)
    _pg_url: str = field(default_factory=lambda: _env("DATABASE_URL", ""))
    _pg_sync_url: str = field(default_factory=lambda: _env("DATABASE_SYNC_URL", ""))
    db_pool_size: int = field(default_factory=lambda: _env_int("DB_POOL_SIZE", 10))
    db_max_overflow: int = field(default_factory=lambda: _env_int("DB_MAX_OVERFLOW", 20))
    db_pool_timeout: int = field(default_factory=lambda: _env_int("DB_POOL_TIMEOUT", 30))
    # Oracle ATP
    oracle_dsn: str = field(default_factory=lambda: _env("ORACLE_DSN"))
    oracle_user: str = field(default_factory=lambda: _env("ORACLE_USER", "ADMIN"))
    oracle_password: str = field(default_factory=lambda: _env("ORACLE_PASSWORD"))
    oracle_wallet_dir: str = field(default_factory=lambda: _env("ORACLE_WALLET_DIR"))
    oracle_wallet_password: str = field(default_factory=lambda: _env("ORACLE_WALLET_PASSWORD"))
    atp_ocid: str = field(default_factory=lambda: _env("ATP_OCID", _env("C28_ATP_OCID")))
    database_observability_enabled: bool = field(default_factory=lambda: _env_bool("DATABASE_OBSERVABILITY_ENABLED", True))

    # OCI APM
    oci_apm_endpoint: str = field(default_factory=lambda: _env("OCI_APM_ENDPOINT"))
    oci_apm_private_datakey: str = field(default_factory=lambda: _env("OCI_APM_PRIVATE_DATAKEY"))
    oci_apm_public_datakey: str = field(default_factory=lambda: _env("OCI_APM_PUBLIC_DATAKEY"))
    otel_service_name: str = field(default_factory=lambda: _env("OTEL_SERVICE_NAME", "enterprise-crm-portal"))
    otlp_log_export_enabled: bool = field(default_factory=lambda: _env_bool("OTLP_LOG_EXPORT_ENABLED", True))

    # OCI APM RUM
    oci_apm_rum_endpoint: str = field(default_factory=lambda: _env("OCI_APM_RUM_ENDPOINT"))
    oci_apm_rum_public_datakey: str = field(default_factory=lambda: _env("OCI_APM_RUM_PUBLIC_DATAKEY"))

    # OCI Logging
    oci_log_id: str = field(default_factory=lambda: _env("OCI_LOG_ID"))
    oci_log_group_id: str = field(default_factory=lambda: _env("OCI_LOG_GROUP_ID"))
    oci_auth_mode: str = field(default_factory=lambda: _env("OCI_AUTH_MODE", "instance_principal"))

    # Splunk
    splunk_hec_url: str = field(default_factory=lambda: _env("SPLUNK_HEC_URL"))
    splunk_hec_token: str = field(default_factory=lambda: _env("SPLUNK_HEC_TOKEN"))

    # Cross-service integration
    mushop_cloudnative_url: str = field(default_factory=lambda: _env("MUSHOP_CLOUDNATIVE_URL", _env("C28_MUSHOP_URL")))
    octo_apm_cloudnative_url: str = field(default_factory=lambda: _env("OCTO_APM_CLOUDNATIVE_URL", _env("C28_MUSHOP_URL")))
    octo_drone_shop_url: str = field(default_factory=lambda: _env("OCTO_DRONE_SHOP_URL", _env("MUSHOP_CLOUDNATIVE_URL", _env("C28_MUSHOP_URL"))))
    oci_demo_control_plane_url: str = field(default_factory=lambda: _env("OCI_DEMO_CONTROL_PLANE_URL"))
    oci_demo_backend_url: str = field(default_factory=lambda: _env("OCI_DEMO_BACKEND_URL"))
    opsi_console_url: str = field(default_factory=lambda: _env("OPSI_CONSOLE_URL"))
    db_management_console_url: str = field(default_factory=lambda: _env("DB_MANAGEMENT_CONSOLE_URL"))
    log_analytics_console_url: str = field(default_factory=lambda: _env("LOG_ANALYTICS_CONSOLE_URL"))
    apm_console_url: str = field(default_factory=lambda: _env("APM_CONSOLE_URL"))
    external_orders_url: str = field(default_factory=lambda: _env("EXTERNAL_ORDERS_URL", _env("OCTO_DRONE_SHOP_URL", _env("MUSHOP_CLOUDNATIVE_URL", _env("C28_MUSHOP_URL")))))
    external_orders_path: str = field(default_factory=lambda: _env("EXTERNAL_ORDERS_PATH", "/api/orders"))
    orders_sync_enabled: bool = field(default_factory=lambda: _env_bool("ORDERS_SYNC_ENABLED", True))
    orders_sync_interval_seconds: int = field(default_factory=lambda: _env_int("ORDERS_SYNC_INTERVAL_SECONDS", 300))
    orders_sync_source_name: str = field(default_factory=lambda: _env("ORDERS_SYNC_SOURCE_NAME", "octo-drone-shop"))
    suspicious_order_total_threshold: int = field(default_factory=lambda: _env_int("SUSPICIOUS_ORDER_TOTAL_THRESHOLD", 50000))
    backlog_order_age_minutes: int = field(default_factory=lambda: _env_int("BACKLOG_ORDER_AGE_MINUTES", 30))

    # Security
    security_log_enabled: bool = field(default_factory=lambda: _env_bool("SECURITY_LOG_ENABLED", True))
    session_timeout_seconds: int = field(default_factory=lambda: _env_int("SESSION_TIMEOUT_SECONDS", 3600))
    max_login_attempts: int = field(default_factory=lambda: _env_int("MAX_LOGIN_ATTEMPTS", 5))

    # Chaos / Issue simulation
    simulate_db_latency: bool = field(default_factory=lambda: _env_bool("SIMULATE_DB_LATENCY"))
    simulate_db_disconnect: bool = field(default_factory=lambda: _env_bool("SIMULATE_DB_DISCONNECT"))
    simulate_memory_leak: bool = field(default_factory=lambda: _env_bool("SIMULATE_MEMORY_LEAK"))
    simulate_cpu_spike: bool = field(default_factory=lambda: _env_bool("SIMULATE_CPU_SPIKE"))
    simulate_slow_queries: bool = field(default_factory=lambda: _env_bool("SIMULATE_SLOW_QUERIES"))

    @property
    def use_postgres(self) -> bool:
        """True when PostgreSQL is the backend (default for local dev)."""
        if self.oracle_dsn:
            return False
        return bool(self._pg_url)

    @property
    def database_url(self) -> str:
        """Async database URL for SQLAlchemy."""
        if self.use_postgres:
            url = self._pg_url
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        if self.oracle_dsn:
            return f"oracle+oracledb_async://{self.oracle_user}:{self.oracle_password}@"
        # Fallback: local dev PostgreSQL
        return "postgresql+asyncpg://crm_user:crm_password@localhost:5432/crm_db"

    @property
    def database_sync_url(self) -> str:
        """Synchronous database URL for OTel and bootstrap."""
        if self.use_postgres:
            return self._pg_sync_url or self._pg_url
        if self.oracle_dsn:
            return f"oracle+oracledb://{self.oracle_user}:{self.oracle_password}@"
        return "postgresql://crm_user:crm_password@localhost:5432/crm_db"

    @property
    def apm_configured(self) -> bool:
        return bool(self.oci_apm_endpoint and self.oci_apm_private_datakey)

    @property
    def rum_configured(self) -> bool:
        return bool(self.oci_apm_rum_endpoint and self.oci_apm_rum_public_datakey)

    @property
    def logging_configured(self) -> bool:
        return bool(self.oci_log_id)

    @property
    def atp_connection_name(self) -> str:
        """ATP connection/DSN name (e.g. 'ocidemoatp_low')."""
        return self.oracle_dsn or ""

    @property
    def database_target_label(self) -> str:
        if self.oracle_dsn or self.atp_ocid:
            return "oracle-atp"
        if self.use_postgres:
            return "postgresql"
        return "custom"


cfg = Config()
