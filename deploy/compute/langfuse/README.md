# Langfuse on OCTO Compute

This is the sidecar comparison stack for `${LANGFUSE_PUBLIC_URL}`. It is intentionally separate from the Drone Shop and CRM containers so the demo apps keep their current ports, images, wallets, and APM wiring.

## What Runs

- `langfuse-web` on `127.0.0.1:${LANGFUSE_WEB_PORT:-33000}`
- `langfuse-worker`
- Postgres for Langfuse metadata
- ClickHouse for trace/event analytics
- Redis for queues/cache
- MinIO for Langfuse object storage buckets

## Install On An Existing Compute VM

1. Copy these files with the repo deployment.
2. Create `/opt/octo/langfuse.env` from `langfuse.env.template`.
3. Fill every blank secret with generated values:

```bash
openssl rand -base64 32  # NEXTAUTH_SECRET, SALT
openssl rand -hex 32     # ENCRYPTION_KEY
openssl rand -base64 32  # POSTGRES_PASSWORD, CLICKHOUSE_PASSWORD, REDIS_AUTH, MINIO_ROOT_PASSWORD, LANGFUSE_S3_UPLOAD_SECRET_ACCESS_KEY
```

4. Install the unit:

```bash
sudo cp /opt/octo/repo/deploy/compute/systemd/octo-langfuse.service /etc/systemd/system/octo-langfuse.service
sudo systemctl daemon-reload
sudo systemctl enable --now octo-langfuse.service
```

5. Expose the hostname later by routing `${LANGFUSE_PUBLIC_URL}` through the OCI Load Balancer/WAF to the selected VM private IP on `LANGFUSE_WEB_PORT`.

Until the LB listener/rule is added, verify from the VM:

```bash
curl -fsS http://127.0.0.1:${LANGFUSE_WEB_PORT:-33000}/api/public/health
```

## Notes

- The compose setup is intended for demo comparison, not HA production.
- Use `LANGFUSE_COMPOSE_BIN="docker compose"` or `LANGFUSE_COMPOSE_BIN="podman compose"` depending on the VM runtime.
- Keep the Langfuse platform secrets in `/opt/octo/langfuse.env`; do not add them to the app `runtime.env`.
- After creating a Langfuse project, copy only the project ingestion keys into the Shop app runtime using variables or secret files:

```bash
LANGFUSE_ENABLED=true
LANGFUSE_HOST=${LANGFUSE_PUBLIC_URL}
LANGFUSE_PROJECT_NAME=drones.octodemo.cloud
LANGFUSE_PUBLIC_KEY=<project-public-key>
LANGFUSE_SECRET_KEY_FILE=/opt/octo/secrets/langfuse-secret-key
LANGFUSE_OTEL_EXPORT_ENABLED=true
```

The Drone Shop exports the same assistant spans to OCI APM and, when these
values are present, to Langfuse's OTLP endpoint. The span payload contains
session IDs, token counts, guardrail outcomes, and prompt/response hashes;
raw prompts and responses stay disabled unless `LLMETRY_CAPTURE_CONTENT=true`
is explicitly set for a controlled demo.
- The public hostname deliberately does not reuse the shop/admin app service. Public routing should be added as a separate LB backend path/hostname so `${SHOP_PUBLIC_URL}` and `${CRM_PUBLIC_URL}` continue unchanged.
