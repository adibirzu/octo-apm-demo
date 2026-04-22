"""Application configuration loaded from environment variables."""

import logging
import os
import secrets as _secrets
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_first(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and value != "":
            return value
    return default


def _read_secret_file(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip()


def _env_secret(key: str, default: str = "") -> str:
    explicit = os.getenv(key)
    if explicit is not None and explicit != "":
        return explicit
    file_path = (os.getenv(f"{key}_FILE", "") or "").strip()
    if file_path:
        return _read_secret_file(file_path)
    return default


def _env_bool(key: str, default: bool = False) -> bool:
    return _env(key, str(default)).lower() in ("true", "1", "yes")


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _auto_redirect_uri() -> str:
    """Derive SSO callback URI from DNS_DOMAIN or CRM_BASE_URL.

    Returns empty string if neither is set — this makes `idcs_configured`
    evaluate to False, which disables the SSO button in the login page.
    We intentionally do NOT fall back to localhost because a misconfigured
    redirect URI would cause SSO to silently fail after IDCS auth (the
    callback would redirect to the wrong origin).
    """
    base = os.getenv("CRM_BASE_URL", "")
    if base:
        return f"{base.rstrip('/')}/api/auth/sso/callback"
    dns = os.getenv("DNS_DOMAIN", "")
    if dns:
        return f"https://crm.{dns}/api/auth/sso/callback"
    return ""


def _default_app_secret_key() -> str:
    explicit = _env_secret("APP_SECRET_KEY")
    if explicit:
        return explicit
    if _env("APP_ENV", "production").lower() == "production":
        return ""
    ephemeral = _secrets.token_urlsafe(32)
    logger.warning(
        "APP_SECRET_KEY not set — generated an ephemeral signing key for this "
        "process. Sessions will be invalidated on restart. Set APP_SECRET_KEY "
        "or APP_SECRET_KEY_FILE in shared environments."
    )
    return ephemeral


@dataclass(frozen=True)
class Config:
    # Application
    app_name: str = field(default_factory=lambda: _env("APP_NAME", "enterprise-crm-portal"))
    brand_name: str = field(default_factory=lambda: _env("BRAND_NAME", "OCTO CRM APM"))
    app_version: str = field(default_factory=lambda: _env("APP_VERSION", "1.1.0"))
    app_port: int = field(default_factory=lambda: _env_int("APP_PORT", 8080))
    app_env: str = field(default_factory=lambda: _env("APP_ENV", "production"))
    app_secret_key: str = field(default_factory=_default_app_secret_key)
    app_runtime: str = field(default_factory=lambda: _env("APP_RUNTIME", "docker"))
    service_namespace: str = field(default_factory=lambda: _env("SERVICE_NAMESPACE", "octo"))
    service_instance_id: str = field(default_factory=lambda: _env("SERVICE_INSTANCE_ID", _env("HOSTNAME", "local-dev")))
    demo_stack_name: str = field(default_factory=lambda: _env("DEMO_STACK_NAME", "platform-stack"))
    dns_domain: str = field(default_factory=lambda: _env("DNS_DOMAIN"))
    crm_base_url: str = field(default_factory=lambda: _env("CRM_BASE_URL"))
    cors_allowed_origins_raw: str = field(default_factory=lambda: _env("CORS_ALLOWED_ORIGINS"))

    # Database — Oracle ATP
    db_pool_size: int = field(default_factory=lambda: _env_int("DB_POOL_SIZE", 10))
    db_max_overflow: int = field(default_factory=lambda: _env_int("DB_MAX_OVERFLOW", 20))
    db_pool_timeout: int = field(default_factory=lambda: _env_int("DB_POOL_TIMEOUT", 30))
    # Auth-path sync engine — intentionally separate from the main pool so it
    # can be tuned (and observed) independently. Small defaults keep the
    # per-replica Oracle ATP session footprint bounded; see KB-435.
    db_auth_pool_size: int = field(default_factory=lambda: _env_int("DB_AUTH_POOL_SIZE", 5))
    db_auth_max_overflow: int = field(default_factory=lambda: _env_int("DB_AUTH_MAX_OVERFLOW", 10))
    db_auth_pool_timeout: int = field(default_factory=lambda: _env_int("DB_AUTH_POOL_TIMEOUT", 5))
    # Dedicated executor for auth lookups so cache-miss bursts cannot queue
    # behind unrelated `asyncio.to_thread` calls. Sized to match the auth pool
    # + overflow so the executor is never the bottleneck before the DB is.
    auth_executor_max_workers: int = field(default_factory=lambda: _env_int("AUTH_EXECUTOR_MAX_WORKERS", 15))
    _database_url: str = field(default_factory=lambda: _env_secret("DATABASE_URL"))
    _database_sync_url: str = field(default_factory=lambda: _env_secret("DATABASE_SYNC_URL"))
    # Oracle ATP
    oracle_dsn: str = field(default_factory=lambda: _env("ORACLE_DSN"))
    oracle_user: str = field(default_factory=lambda: _env("ORACLE_USER", "ADMIN"))
    oracle_password: str = field(default_factory=lambda: _env_secret("ORACLE_PASSWORD"))
    oracle_wallet_dir: str = field(default_factory=lambda: _env("ORACLE_WALLET_DIR"))
    oracle_wallet_password: str = field(default_factory=lambda: _env_secret("ORACLE_WALLET_PASSWORD"))
    atp_ocid: str = field(default_factory=lambda: _env("ATP_OCID"))
    database_observability_enabled: bool = field(default_factory=lambda: _env_bool("DATABASE_OBSERVABILITY_ENABLED", True))

    # OCI APM
    oci_apm_endpoint: str = field(default_factory=lambda: _env("OCI_APM_ENDPOINT"))
    oci_apm_private_datakey: str = field(default_factory=lambda: _env_secret("OCI_APM_PRIVATE_DATAKEY"))
    oci_apm_public_datakey: str = field(default_factory=lambda: _env("OCI_APM_PUBLIC_DATAKEY"))
    otel_service_name: str = field(default_factory=lambda: _env("OTEL_SERVICE_NAME", "enterprise-crm-portal"))
    # OCI APM does not support OTLP log ingestion — logs go via OCI Logging SDK.
    otlp_log_export_enabled: bool = field(default_factory=lambda: _env_bool("OTLP_LOG_EXPORT_ENABLED", False))

    # OCI APM RUM
    oci_apm_rum_endpoint: str = field(default_factory=lambda: _env("OCI_APM_RUM_ENDPOINT"))
    oci_apm_rum_public_datakey: str = field(default_factory=lambda: _env("OCI_APM_RUM_PUBLIC_DATAKEY"))

    # OCI Logging
    oci_log_id: str = field(default_factory=lambda: _env("OCI_LOG_ID"))
    oci_log_group_id: str = field(default_factory=lambda: _env("OCI_LOG_GROUP_ID"))
    oci_auth_mode: str = field(default_factory=lambda: _env("OCI_AUTH_MODE", "instance_principal"))

    # Splunk
    splunk_hec_url: str = field(default_factory=lambda: _env("SPLUNK_HEC_URL"))
    splunk_hec_token: str = field(default_factory=lambda: _env_secret("SPLUNK_HEC_TOKEN"))

    # Cross-service integration
    # Deployment automation can inject these generic endpoint URLs directly.
    # Older platform-specific variable names remain as compatibility fallbacks
    # so existing environments do not break while tracked files stay portable.
    mushop_cloudnative_url: str = field(default_factory=lambda: _env("MUSHOP_CLOUDNATIVE_URL"))
    octo_apm_cloudnative_url: str = field(default_factory=lambda: _env("OCTO_APM_CLOUDNATIVE_URL"))
    # SERVICE_SHOP_URL is the canonical name (matches SERVICE_CRM_URL on the
    # shop side). OCTO_DRONE_SHOP_URL and MUSHOP_CLOUDNATIVE_URL remain as
    # deprecated aliases so existing tenancies keep working — a startup
    # warning surfaces when only a legacy name is set.
    octo_drone_shop_url: str = field(
        default_factory=lambda: _env_first(
            "SERVICE_SHOP_URL",
            "OCTO_DRONE_SHOP_URL",
            "MUSHOP_CLOUDNATIVE_URL",
        )
    )
    control_plane_url: str = field(
        default_factory=lambda: _env_first(
            "CONTROL_PLANE_URL",
            "_".join(("OCI", "DEMO", "CONTROL", "PLANE", "URL")),
        )
    )
    platform_backend_url: str = field(
        default_factory=lambda: _env_first(
            "PLATFORM_BACKEND_URL",
            "_".join(("OCI", "DEMO", "BACKEND", "URL")),
        )
    )
    opsi_console_url: str = field(default_factory=lambda: _env("OPSI_CONSOLE_URL"))
    db_management_console_url: str = field(default_factory=lambda: _env("DB_MANAGEMENT_CONSOLE_URL"))
    log_analytics_console_url: str = field(default_factory=lambda: _env("LOG_ANALYTICS_CONSOLE_URL"))
    apm_console_url: str = field(default_factory=lambda: _env("APM_CONSOLE_URL"))
    c22_skp_url: str = field(default_factory=lambda: _env("C22_SKP_URL"))
    external_orders_url: str = field(
        default_factory=lambda: _env_first(
            "EXTERNAL_ORDERS_URL",
            "SERVICE_SHOP_URL",
            "OCTO_DRONE_SHOP_URL",
            "MUSHOP_CLOUDNATIVE_URL",
        )
    )
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
    bootstrap_admin_password: str = field(default_factory=lambda: _env_secret("BOOTSTRAP_ADMIN_PASSWORD"))

    # Cross-service simulation proxy — shared key so the CRM backend can
    # proxy simulation/demo requests to the drone shop without SSO.
    drone_shop_internal_key: str = field(
        default_factory=lambda: _env_secret("DRONE_SHOP_INTERNAL_KEY") or _env_secret("INTERNAL_SERVICE_KEY")
    )

    # IDCS / OCI Identity Domain SSO
    idcs_domain_url: str = field(default_factory=lambda: _env("IDCS_DOMAIN_URL"))
    idcs_client_id: str = field(default_factory=lambda: _env("IDCS_CLIENT_ID"))
    idcs_client_secret: str = field(default_factory=lambda: _env_secret("IDCS_CLIENT_SECRET"))
    idcs_redirect_uri: str = field(default_factory=lambda: _env("IDCS_REDIRECT_URI") or _auto_redirect_uri())

    # Chaos / Issue simulation
    simulate_db_latency: bool = field(default_factory=lambda: _env_bool("SIMULATE_DB_LATENCY"))
    simulate_db_disconnect: bool = field(default_factory=lambda: _env_bool("SIMULATE_DB_DISCONNECT"))
    simulate_memory_leak: bool = field(default_factory=lambda: _env_bool("SIMULATE_MEMORY_LEAK"))
    simulate_cpu_spike: bool = field(default_factory=lambda: _env_bool("SIMULATE_CPU_SPIKE"))
    simulate_slow_queries: bool = field(default_factory=lambda: _env_bool("SIMULATE_SLOW_QUERIES"))

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def warn_deprecations(self) -> list[str]:
        """Return deprecation warnings for legacy env var names.

        Kept as a pure function returning the list so tests can assert
        the warning set without log-capture gymnastics.
        """
        warnings: list[str] = []
        if (
            not os.getenv("SERVICE_SHOP_URL")
            and (os.getenv("OCTO_DRONE_SHOP_URL") or os.getenv("MUSHOP_CLOUDNATIVE_URL"))
        ):
            warnings.append(
                "OCTO_DRONE_SHOP_URL / MUSHOP_CLOUDNATIVE_URL are deprecated; "
                "set SERVICE_SHOP_URL instead. Legacy names will be removed "
                "in a future release."
            )
        if (
            not os.getenv("INTERNAL_SERVICE_KEY")
            and not os.getenv("INTERNAL_SERVICE_KEY_FILE")
            and (os.getenv("DRONE_SHOP_INTERNAL_KEY") or os.getenv("DRONE_SHOP_INTERNAL_KEY_FILE"))
        ):
            warnings.append(
                "DRONE_SHOP_INTERNAL_KEY is deprecated; set INTERNAL_SERVICE_KEY "
                "instead (matches the shop side)."
            )
        return warnings

    @property
    def use_postgres(self) -> bool:
        return bool(self._database_url) and not bool(self.oracle_dsn)

    @property
    def database_url(self) -> str:
        """Async database URL for SQLAlchemy."""
        if self.use_postgres:
            if self._database_url.startswith("postgresql://"):
                return self._database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return self._database_url
        return f"oracle+oracledb_async://{self.oracle_user}:{self.oracle_password}@"

    @property
    def database_sync_url(self) -> str:
        """Synchronous database URL for OTel and bootstrap."""
        if self.use_postgres:
            if self._database_sync_url:
                return self._database_sync_url
            if self._database_url.startswith("postgresql+asyncpg://"):
                return self._database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
            return self._database_url
        return f"oracle+oracledb://{self.oracle_user}:{self.oracle_password}@"

    @property
    def idcs_configured(self) -> bool:
        return bool(self.idcs_domain_url and self.idcs_client_id and self.idcs_client_secret and self.idcs_redirect_uri)

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
        return "postgresql" if self.use_postgres else "oracle-atp"

    @property
    def cors_allowed_origins(self) -> list[str]:
        configured = [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins_raw.split(",")
            if origin.strip() and origin.strip() != "*"
        ]
        if configured:
            return list(dict.fromkeys(configured))

        derived: list[str] = []
        if self.crm_base_url:
            derived.append(self.crm_base_url.rstrip("/"))
        if self.dns_domain:
            derived.extend(
                [
                    f"https://crm.{self.dns_domain}",
                    f"https://shop.{self.dns_domain}",
                    f"https://ops.{self.dns_domain}",
                ]
            )
        return list(dict.fromkeys(origin for origin in derived if origin))

    def masked_database_url(self) -> str:
        url = self.database_url
        if "@" not in url or "://" not in url:
            return url
        prefix, suffix = url.split("@", 1)
        if ":" not in prefix:
            return url
        head, _secret = prefix.rsplit(":", 1)
        return f"{head}:***@{suffix}"

    def safe_runtime_summary(self) -> dict:
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "database_backend": self.database_target_label,
            "database_configured": bool(self._database_url) if self.use_postgres else bool(self.oracle_dsn and self.oracle_password),
            "apm_configured": self.apm_configured,
            "rum_configured": self.rum_configured,
            "logging_configured": self.logging_configured,
            "splunk_configured": bool(self.splunk_hec_url and self.splunk_hec_token),
            "idcs_configured": self.idcs_configured,
            "orders_sync_enabled": self.orders_sync_enabled,
            "cors_origins": self.cors_allowed_origins,
            "control_plane_configured": bool(self.control_plane_url),
        }

    def validate(self) -> None:
        if self.use_postgres and not self.database_url:
            raise RuntimeError("DATABASE_URL is set but could not be resolved")
        if self.oracle_dsn and not self.oracle_password:
            raise RuntimeError("ORACLE_DSN is set but ORACLE_PASSWORD is missing")
        if self.is_production and not self.app_secret_key:
            raise RuntimeError(
                "APP_SECRET_KEY is required when APP_ENV=production. "
                "Provide APP_SECRET_KEY or APP_SECRET_KEY_FILE."
            )
        if self.is_production and not self.bootstrap_admin_password:
            raise RuntimeError(
                "BOOTSTRAP_ADMIN_PASSWORD is required when APP_ENV=production. "
                "Provide BOOTSTRAP_ADMIN_PASSWORD or BOOTSTRAP_ADMIN_PASSWORD_FILE."
            )

        partial_sso = any([self.idcs_domain_url, self.idcs_client_id, self.idcs_client_secret, os.getenv("IDCS_REDIRECT_URI", "")])
        if partial_sso and not self.idcs_configured and self.is_production:
            raise RuntimeError(
                "IDCS SSO is partially configured. Set IDCS_DOMAIN_URL, "
                "IDCS_CLIENT_ID, IDCS_CLIENT_SECRET, and IDCS_REDIRECT_URI."
            )


cfg = Config()
