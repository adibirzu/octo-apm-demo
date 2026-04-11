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
    dns_domain = os.getenv("DNS_DOMAIN", "")
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
    workflow_api_base_url = os.getenv("WORKFLOW_API_BASE_URL", "").rstrip("/")
    workflow_service_name = os.getenv("WORKFLOW_SERVICE_NAME", "octo-workflow-gateway")
    workflow_poll_seconds = int(os.getenv("WORKFLOW_POLL_SECONDS", "90"))
    workflow_faulty_query_enabled = os.getenv("WORKFLOW_FAULTY_QUERY_ENABLED", "false").lower() in ("1", "true", "yes")

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
    selectai_profile_name = os.getenv("SELECTAI_PROFILE_NAME", "")

    # ── OCI Console Drilldown URLs ──
    apm_console_url = os.getenv("APM_CONSOLE_URL", "")
    opsi_console_url = os.getenv("OPSI_CONSOLE_URL", "")
    db_management_console_url = os.getenv("DB_MANAGEMENT_CONSOLE_URL", "")
    log_analytics_console_url = os.getenv("LOG_ANALYTICS_CONSOLE_URL", "")

    # ── Internal service-to-service authentication ──
    # Shared key between CRM and Drone Shop so the CRM backend can proxy
    # simulation/demo requests without an SSO token. Empty = disabled.
    internal_service_key = os.getenv("INTERNAL_SERVICE_KEY", "")

    # ── IDCS / OCI IAM Identity Domain (OIDC SSO) ──
    idcs_domain_url = os.getenv("IDCS_DOMAIN_URL", "").rstrip("/")
    idcs_client_id = os.getenv("IDCS_CLIENT_ID", "")
    idcs_client_secret = os.getenv("IDCS_CLIENT_SECRET", "")
    _idcs_redirect_uri = os.getenv("IDCS_REDIRECT_URI", "")
    idcs_scope = os.getenv("IDCS_SCOPE", "openid profile email")
    _idcs_post_logout_redirect = os.getenv("IDCS_POST_LOGOUT_REDIRECT", "")
    # JWKS verification can be disabled in air-gapped dev only.
    idcs_verify_jwt = os.getenv("IDCS_VERIFY_JWT", "true").lower() in ("1", "true", "yes")

    # ── Splunk HEC ──
    splunk_hec_url = os.getenv("SPLUNK_HEC_URL", "")
    splunk_hec_token = os.getenv("SPLUNK_HEC_TOKEN", "")
    # OCI APM does not support OTLP log ingestion — logs go via OCI Logging SDK.
    # Set to "true" only if a third-party OTLP log collector is configured.
    otlp_log_export_enabled = os.getenv("OTLP_LOG_EXPORT_ENABLED", "false").lower() in ("1", "true", "yes")

    @property
    def shop_public_url(self) -> str:
        """Derive the shop's public URL from DNS_DOMAIN if set."""
        if self.dns_domain:
            return f"https://shop.{self.dns_domain}"
        return ""

    @property
    def crm_public_url(self) -> str:
        """Derive the CRM's public URL from DNS_DOMAIN if set."""
        if self.dns_domain:
            return f"https://crm.{self.dns_domain}"
        return ""

    @property
    def cors_origins_default(self) -> str:
        """Build default CORS origins from DNS_DOMAIN or fall back to empty."""
        if self.dns_domain:
            return f"https://shop.{self.dns_domain},https://crm.{self.dns_domain}"
        return ""

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
    def workflow_gateway_configured(self) -> bool:
        return bool(self.workflow_api_base_url)

    @property
    def selectai_configured(self) -> bool:
        return bool(self.selectai_profile_name)

    @property
    def idcs_redirect_uri(self) -> str:
        if self._idcs_redirect_uri:
            return self._idcs_redirect_uri
        if self.dns_domain:
            return f"https://shop.{self.dns_domain}/api/auth/sso/callback"
        return "http://localhost:8080/api/auth/sso/callback"

    @property
    def idcs_post_logout_redirect(self) -> str:
        if self._idcs_post_logout_redirect:
            return self._idcs_post_logout_redirect
        if self.dns_domain:
            return f"https://shop.{self.dns_domain}/login"
        return "/login"

    @property
    def idcs_configured(self) -> bool:
        return bool(
            self.idcs_domain_url
            and self.idcs_client_id
            and self.idcs_client_secret
            and self.idcs_redirect_uri
        )

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
            "selectai_configured": self.selectai_configured,
            "crm_configured": bool(self.enterprise_crm_url),
            "crm_host": self.crm_hostname or None,
            "workflow_gateway_configured": self.workflow_gateway_configured,
            "workflow_api_base_url": self.workflow_api_base_url or None,
        }

    def validate(self) -> None:
        # ATP credentials are optional — app falls back to PostgreSQL if not set
        if self.oracle_dsn and not self.oracle_password:
            raise RuntimeError("ORACLE_DSN is set but ORACLE_PASSWORD is missing")

        # In production, the bearer-token signing secret MUST be supplied.
        # Outside production, server.auth_security generates a per-process
        # random secret with a warning log.
        if self.is_production and not self.auth_token_secret:
            raise RuntimeError(
                "AUTH_TOKEN_SECRET is required when ENVIRONMENT=production. "
                "Provide it via secret/env so bearer tokens can be signed."
            )

        # In production with SSO partially configured (some fields set,
        # others missing), refuse to start so the misconfiguration is loud.
        # Use raw env vars (not properties with fallbacks) to detect
        # partial SSO config. idcs_redirect_uri has a DNS_DOMAIN fallback
        # that would make this always True.
        partial = any([
            self.idcs_domain_url, self.idcs_client_id,
            self.idcs_client_secret, self._idcs_redirect_uri,
        ])
        if partial and not self.idcs_configured and self.is_production:
            raise RuntimeError(
                "IDCS SSO is partially configured. Set IDCS_DOMAIN_URL, "
                "IDCS_CLIENT_ID, IDCS_CLIENT_SECRET, IDCS_REDIRECT_URI."
            )


cfg = Config()
