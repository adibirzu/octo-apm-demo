"""MuShop Cloud Native Portal — Configuration.

Loads settings from environment variables with sensible defaults.
Supports both PostgreSQL (dev/Docker) and Oracle ATP (production/OKE).
"""

import os


class Config:
    app_name = os.getenv("APP_NAME", "mushop-cloudnative")
    app_runtime = os.getenv("APP_RUNTIME", "docker")  # docker, oke, vm
    port = int(os.getenv("PORT", "8080"))
    environment = os.getenv("ENVIRONMENT", "development")

    # ── Database ──
    # Oracle ATP (production)
    oracle_dsn = os.getenv("ORACLE_DSN", "")  # e.g. "(description=...)" or TNS alias
    oracle_user = os.getenv("ORACLE_USER", "mushop")
    oracle_password = os.getenv("ORACLE_PASSWORD", "")
    oracle_wallet_dir = os.getenv("ORACLE_WALLET_DIR", "")
    oracle_wallet_password = os.getenv("ORACLE_WALLET_PASSWORD", "")

    # PostgreSQL fallback (dev/Docker Compose)
    pg_url = os.getenv("DATABASE_URL", "")
    database_sync_url = os.getenv("DATABASE_SYNC_URL", "")

    # ── MuShop backend (original oci-cloudnative) ──
    mushop_backend_url = os.getenv("MUSHOP_BACKEND_URL", "")  # e.g. http://mushop-api:8080

    # ── OCI APM ──
    oci_apm_endpoint = os.getenv("OCI_APM_ENDPOINT", "")
    oci_apm_private_datakey = os.getenv("OCI_APM_PRIVATE_DATAKEY", "")
    oci_apm_public_datakey = os.getenv("OCI_APM_PUBLIC_DATAKEY", "")
    oci_apm_rum_endpoint = os.getenv("OCI_APM_RUM_ENDPOINT", "")

    # ── OCI Logging SDK ──
    oci_log_id = os.getenv("OCI_LOG_ID", "")
    oci_log_group_id = os.getenv("OCI_LOG_GROUP_ID", "")

    # ── Splunk HEC ──
    splunk_hec_url = os.getenv("SPLUNK_HEC_URL", "")
    splunk_hec_token = os.getenv("SPLUNK_HEC_TOKEN", "")

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
    def use_oracle(self) -> bool:
        return bool(self.oracle_dsn or self.oracle_wallet_dir)

    @property
    def database_url(self) -> str:
        """Return async database URL for SQLAlchemy."""
        if self.use_oracle:
            # oracle+oracledb_async for async Oracle connections
            return f"oracle+oracledb_async://{self.oracle_user}:{self.oracle_password}@"
        return self.pg_url or "postgresql+asyncpg://mushop:mushop@localhost:5432/mushop"


cfg = Config()
