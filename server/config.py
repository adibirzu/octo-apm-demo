"""OCTO-CRM-APM — Configuration.

ATP-only runtime configuration for OKE and OCI deployments.
"""

import os


class Config:
    app_name = os.getenv("APP_NAME", os.getenv("OBSERVABILITY_APP_NAME", "octo-drone-shop"))
    brand_name = os.getenv("BRAND_NAME", "OCTO Drone Shop")
    app_version = os.getenv("APP_VERSION", "1.2.0")
    app_runtime = os.getenv("APP_RUNTIME", "oke")
    app_env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production"))
    service_namespace = os.getenv("SERVICE_NAMESPACE", "octo")
    service_instance_id = os.getenv("SERVICE_INSTANCE_ID", os.getenv("HOSTNAME", "local-dev"))
    demo_stack_name = os.getenv("DEMO_STACK_NAME", "octo-demo")
    otel_service_name = os.getenv(
        "OTEL_SERVICE_NAME",
        os.getenv("OBSERVABILITY_SERVICE_NAME", "octo-drone-shop-oke"),
    )
    oci_auth_mode = os.getenv("OCI_AUTH_MODE", "auto")
    port = int(os.getenv("PORT", "8080"))
    environment = os.getenv("ENVIRONMENT", "production")
    auth_token_secret = os.getenv("AUTH_TOKEN_SECRET", "")

    # ── Database ──
    # PostgreSQL (preferred for non-ATP deployments)
    _pg_url = os.getenv("DATABASE_URL", "")
    _pg_sync_url = os.getenv("DATABASE_SYNC_URL", "")
    # Oracle ATP
    oracle_dsn = os.getenv("ORACLE_DSN", "")
    oracle_user = os.getenv("ORACLE_USER", "ADMIN")
    oracle_password = os.getenv("ORACLE_PASSWORD", "")
    oracle_wallet_dir = os.getenv("ORACLE_WALLET_DIR", "")
    oracle_wallet_password = os.getenv("ORACLE_WALLET_PASSWORD", "")

    # ── Cross-service integration ──
    enterprise_crm_url = os.getenv("ENTERPRISE_CRM_URL", "")

    # ── OCI APM ──
    oci_apm_endpoint = os.getenv("OCI_APM_ENDPOINT", "")
    oci_apm_private_datakey = os.getenv("OCI_APM_PRIVATE_DATAKEY", "")
    oci_apm_public_datakey = os.getenv("OCI_APM_PUBLIC_DATAKEY", "")
    oci_apm_rum_endpoint = os.getenv("OCI_APM_RUM_ENDPOINT", "")
    oci_apm_web_application = os.getenv("OCI_APM_WEB_APPLICATION", "octo-drone-shop")

    # ── OCI Logging SDK ──
    oci_log_id = os.getenv("OCI_LOG_ID", "")
    oci_log_group_id = os.getenv("OCI_LOG_GROUP_ID", "")

    # ── OCI Generative AI ──
    oci_compartment_id = os.getenv("OCI_COMPARTMENT_ID", "")
    oci_genai_endpoint = os.getenv("OCI_GENAI_ENDPOINT", "")
    oci_genai_model_id = os.getenv("OCI_GENAI_MODEL_ID", "")

    # ── OCI Console Drilldown URLs ──
    apm_console_url = os.getenv("APM_CONSOLE_URL", "")
    opsi_console_url = os.getenv("OPSI_CONSOLE_URL", "")
    db_management_console_url = os.getenv("DB_MANAGEMENT_CONSOLE_URL", "")
    log_analytics_console_url = os.getenv("LOG_ANALYTICS_CONSOLE_URL", "")

    # ── Splunk HEC ──
    splunk_hec_url = os.getenv("SPLUNK_HEC_URL", "")
    splunk_hec_token = os.getenv("SPLUNK_HEC_TOKEN", "")
    # OCI APM does not support OTLP log ingestion — logs go via OCI Logging SDK.
    # Set to "true" only if a third-party OTLP log collector is configured.
    otlp_log_export_enabled = os.getenv("OTLP_LOG_EXPORT_ENABLED", "false").lower() in ("1", "true", "yes")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def crm_hostname(self) -> str:
        if not self.enterprise_crm_url:
            return ""
        return self.enterprise_crm_url.split("://", 1)[-1].split("/", 1)[0]

    @property
    def apm_configured(self) -> bool:
        return bool(self.oci_apm_endpoint and self.oci_apm_private_datakey)

    @property
    def rum_configured(self) -> bool:
        return bool(self.oci_apm_rum_endpoint and self.oci_apm_public_datakey)

    @property
    def logging_configured(self) -> bool:
        return bool(self.oci_log_id)

    @property
    def database_target_label(self) -> str:
        return "postgresql" if self.use_postgres else "oracle_atp"

    @property
    def use_postgres(self) -> bool:
        return bool(self._pg_url) and not bool(self.oracle_dsn)

    @property
    def database_url(self) -> str:
        if self.use_postgres:
            # Convert postgresql:// to postgresql+asyncpg:// for async
            url = self._pg_url
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return f"oracle+oracledb_async://{self.oracle_user}:{self.oracle_password}@"

    @property
    def sync_database_url(self) -> str:
        if self.use_postgres:
            return self._pg_sync_url or self._pg_url
        return f"oracle+oracledb://{self.oracle_user}:{self.oracle_password}@"

    def masked_database_url(self) -> str:
        if self.use_postgres:
            return self._pg_url.split("@")[0].rsplit(":", 1)[0] + ":***@" + self._pg_url.split("@", 1)[-1] if "@" in self._pg_url else self._pg_url
        return f"oracle+oracledb_async://{self.oracle_user}:***@"

    def safe_runtime_summary(self) -> dict:
        return {
            "app_name": self.app_name,
            "environment": self.app_env,
            "app_runtime": self.app_runtime,
            "database_backend": self.database_target_label,
            "database_configured": bool(self._pg_url) if self.use_postgres else bool(self.oracle_dsn and self.oracle_password),
            "apm_configured": self.apm_configured,
            "rum_configured": self.rum_configured,
            "logging_configured": self.logging_configured,
            "splunk_configured": bool(self.splunk_hec_url and self.splunk_hec_token),
            "genai_configured": bool(self.oci_compartment_id and self.oci_genai_endpoint and self.oci_genai_model_id),
            "crm_configured": bool(self.enterprise_crm_url),
            "crm_host": self.crm_hostname or None,
        }

    def validate(self) -> None:
        # ATP credentials are optional — app falls back to PostgreSQL if not set
        if self.oracle_dsn and not self.oracle_password:
            raise RuntimeError("ORACLE_DSN is set but ORACLE_PASSWORD is missing")


cfg = Config()
