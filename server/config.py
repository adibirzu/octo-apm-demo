"""OCTO Drone Shop configuration.

Supports direct environment variables plus ``*_FILE`` variants for secrets so
deployments can source credentials from mounted secret files without copying
them into tracked env files.
"""

import os
from urllib.parse import urlparse


def _read_secret_file(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip()


def _env_value(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_secret(name: str, default: str = "") -> str:
    explicit = os.getenv(name)
    if explicit is not None and explicit != "":
        return explicit
    file_path = (os.getenv(f"{name}_FILE", "") or "").strip()
    if file_path:
        return _read_secret_file(file_path)
    return default


class Config:
    app_name = _env_value("APP_NAME", _env_value("OBSERVABILITY_APP_NAME", "octo-drone-shop"))
    brand_name = _env_value("BRAND_NAME", "OCTO Drone Shop")
    app_version = _env_value("APP_VERSION", "1.2.0")
    app_runtime = _env_value("APP_RUNTIME", "oke")
    app_env = _env_value("APP_ENV", _env_value("ENVIRONMENT", "production"))
    dns_domain = _env_value("DNS_DOMAIN", "")
    service_namespace = _env_value("SERVICE_NAMESPACE", "octo")
    service_instance_id = _env_value("SERVICE_INSTANCE_ID", _env_value("HOSTNAME", "local-dev"))
    demo_stack_name = _env_value("DEMO_STACK_NAME", "platform-stack")
    otel_service_name = os.getenv(
        "OTEL_SERVICE_NAME",
        _env_value("OBSERVABILITY_SERVICE_NAME", "octo-drone-shop"),
    )
    oci_auth_mode = _env_value("OCI_AUTH_MODE", "auto")
    port = int(_env_value("PORT", "8080"))
    environment = _env_value("ENVIRONMENT", "production")
    auth_token_secret = _env_secret("AUTH_TOKEN_SECRET", "")

    # ── Database ──
    # PostgreSQL (preferred for non-ATP deployments)
    _pg_url = _env_secret("DATABASE_URL", "")
    _pg_sync_url = _env_secret("DATABASE_SYNC_URL", "")
    # Oracle ATP
    oracle_dsn = _env_value("ORACLE_DSN", "")
    oracle_user = _env_value("ORACLE_USER", "ADMIN")
    oracle_password = _env_secret("ORACLE_PASSWORD", "")
    oracle_wallet_dir = _env_value("ORACLE_WALLET_DIR", "")
    oracle_wallet_password = _env_secret("ORACLE_WALLET_PASSWORD", "")

    # ── Cross-service integration ──
    # SERVICE_CRM_URL is the canonical env var (matches SERVICE_SHOP_URL
    # on the CRM side). ENTERPRISE_CRM_URL is kept as a legacy alias so
    # existing tenants continue to work — prefer SERVICE_CRM_URL in new
    # deployments.
    enterprise_crm_url = _env_value(
        "SERVICE_CRM_URL", _env_value("ENTERPRISE_CRM_URL", "")
    )
    _using_legacy_crm_url_alias = bool(
        os.getenv("ENTERPRISE_CRM_URL") and not os.getenv("SERVICE_CRM_URL")
    )
    _crm_public_url = _env_value("CRM_PUBLIC_URL", "").rstrip("/")
    workflow_api_base_url = _env_value("WORKFLOW_API_BASE_URL", "").rstrip("/")
    _workflow_public_api_base_url = _env_value("WORKFLOW_PUBLIC_API_BASE_URL", "").rstrip("/")
    workflow_service_name = _env_value("WORKFLOW_SERVICE_NAME", "octo-workflow-gateway")
    workflow_poll_seconds = int(_env_value("WORKFLOW_POLL_SECONDS", "90"))
    workflow_faulty_query_enabled = _env_value("WORKFLOW_FAULTY_QUERY_ENABLED", "false").lower() in ("1", "true", "yes")

    # ── OCI APM ──
    oci_apm_endpoint = _env_value("OCI_APM_ENDPOINT", "")
    oci_apm_private_datakey = _env_secret("OCI_APM_PRIVATE_DATAKEY", "")
    oci_apm_public_datakey = _env_value("OCI_APM_PUBLIC_DATAKEY", "")
    oci_apm_rum_endpoint = _env_value("OCI_APM_RUM_ENDPOINT", "")
    oci_apm_web_application = _env_value("OCI_APM_WEB_APPLICATION", "octo-drone-shop")

    # ── OCI Logging SDK ──
    oci_log_id = _env_value("OCI_LOG_ID", "")
    oci_log_group_id = _env_value("OCI_LOG_GROUP_ID", "")

    # ── OCI Generative AI ──
    oci_compartment_id = _env_value("OCI_COMPARTMENT_ID", "")
    oci_genai_endpoint = _env_value("OCI_GENAI_ENDPOINT", "")
    oci_genai_model_id = _env_value("OCI_GENAI_MODEL_ID", "")
    selectai_profile_name = _env_value("SELECTAI_PROFILE_NAME", "")

    # ── OCI Console Drilldown URLs ──
    apm_console_url = _env_value("APM_CONSOLE_URL", "")
    opsi_console_url = _env_value("OPSI_CONSOLE_URL", "")
    db_management_console_url = _env_value("DB_MANAGEMENT_CONSOLE_URL", "")
    log_analytics_console_url = _env_value("LOG_ANALYTICS_CONSOLE_URL", "")

    # ── Internal service-to-service authentication ──
    # Shared key between CRM and Drone Shop so the CRM backend can proxy
    # simulation/demo requests without an SSO token. Empty = disabled.
    internal_service_key = _env_secret("INTERNAL_SERVICE_KEY", "")

    # ── IDCS / OCI IAM Identity Domain (OIDC SSO) ──
    idcs_domain_url = _env_value("IDCS_DOMAIN_URL", "").rstrip("/")
    idcs_client_id = _env_value("IDCS_CLIENT_ID", "")
    idcs_client_secret = _env_secret("IDCS_CLIENT_SECRET", "")
    _idcs_redirect_uri = _env_value("IDCS_REDIRECT_URI", "")
    idcs_scope = _env_value("IDCS_SCOPE", "openid profile email")
    _idcs_post_logout_redirect = _env_value("IDCS_POST_LOGOUT_REDIRECT", "")
    # JWKS verification can be disabled in air-gapped dev only.
    idcs_verify_jwt = _env_value("IDCS_VERIFY_JWT", "true").lower() in ("1", "true", "yes")

    # ── Splunk HEC ──
    splunk_hec_url = _env_value("SPLUNK_HEC_URL", "")
    splunk_hec_token = _env_secret("SPLUNK_HEC_TOKEN", "")
    # OCI APM does not support OTLP log ingestion — logs go via OCI Logging SDK.
    # Set to "true" only if a third-party OTLP log collector is configured.
    otlp_log_export_enabled = _env_value("OTLP_LOG_EXPORT_ENABLED", "false").lower() in ("1", "true", "yes")

    @property
    def shop_public_url(self) -> str:
        """Derive the shop's public URL from DNS_DOMAIN if set."""
        if self.dns_domain:
            return f"https://shop.{self.dns_domain}"
        return ""

    @property
    def crm_public_url(self) -> str:
        """Derive the CRM's public URL from DNS_DOMAIN if set."""
        if self._crm_public_url:
            return self._crm_public_url
        if self.dns_domain:
            return f"https://crm.{self.dns_domain}"
        return ""

    @staticmethod
    def _hostname_from_url(url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return (parsed.hostname or "").strip()

    @classmethod
    def _is_private_service_hostname(cls, hostname: str) -> bool:
        normalized = (hostname or "").strip().lower()
        return normalized.endswith(".svc.cluster.local") or normalized.endswith(".cluster.local")

    @classmethod
    def _public_url_or_empty(cls, url: str) -> str:
        hostname = cls._hostname_from_url(url)
        if not hostname or cls._is_private_service_hostname(hostname):
            return ""
        return url

    @property
    def crm_public_hostname(self) -> str:
        return self._hostname_from_url(self.crm_public_url)

    @property
    def workflow_public_api_base_url(self) -> str:
        if self._workflow_public_api_base_url:
            return self._workflow_public_api_base_url
        return self._public_url_or_empty(self.workflow_api_base_url)

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
        return self._hostname_from_url(self.enterprise_crm_url)

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
        # No localhost fallback: a missing redirect must surface as an
        # IDCS misconfiguration in validate(), not silently break SSO.
        if self._idcs_redirect_uri:
            return self._idcs_redirect_uri
        if self.dns_domain:
            return f"https://shop.{self.dns_domain}/api/auth/sso/callback"
        return ""

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
            "crm_host": self.crm_public_hostname or None,
            "crm_public_url": self.crm_public_url or None,
            "workflow_gateway_configured": self.workflow_gateway_configured,
            "workflow_api_base_url": self.workflow_public_api_base_url or None,
        }

    def warn_deprecations(self) -> list[str]:
        """Return a list of deprecation warnings the caller should log.

        Kept as a data-returning function instead of calling ``logging``
        directly so tests can assert the warning set without capturing
        log output.
        """
        warnings: list[str] = []
        if self._using_legacy_crm_url_alias:
            warnings.append(
                "ENTERPRISE_CRM_URL is deprecated; set SERVICE_CRM_URL instead. "
                "The legacy name will be removed in a future release."
            )
        return warnings

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
            # Common cause: IDCS_REDIRECT_URI is neither set explicitly nor
            # derivable (DNS_DOMAIN empty). Name it in the error to save
            # operator time.
            needs_dns = bool(self.idcs_domain_url and not self.dns_domain and not self._idcs_redirect_uri)
            hint = " Missing DNS_DOMAIN prevents IDCS_REDIRECT_URI derivation." if needs_dns else ""
            raise RuntimeError(
                "IDCS SSO is partially configured. Set IDCS_DOMAIN_URL, "
                "IDCS_CLIENT_ID, IDCS_CLIENT_SECRET, IDCS_REDIRECT_URI."
                + hint
            )


cfg = Config()
