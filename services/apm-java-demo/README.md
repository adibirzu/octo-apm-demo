# octo-apm-java-demo

Minimal Spring Boot 3 service that exists purely to populate the OCI
APM **App Servers** dashboard (Apdex, Active Servers, Young/Old GC time,
Process CPU load, request-thread resource consumption, VM name +
version).

The Python services (`shop`, `crm`) can't populate App Servers because
the OCI APM Python SDK does not emit server-info. The OCI APM Java
agent does — this service attaches the agent via `-javaagent:` and
reports to the same APM domain.

## Endpoints

| Path | Purpose |
|---|---|
| `GET /` | Service metadata + JVM version |
| `GET /healthz` | Trivial 200 |
| `GET /slow` | Random 200–1000 ms sleep (thread-resource consumption) |
| `GET /allocate` | Allocates 16–64 MiB (drives Young GC) |
| `GET /error` | Controlled 500 (Apdex "frustrated" + server errors) |
| `GET /actuator/health/{liveness,readiness}` | K8s probes |

## Build + deploy

```bash
export OCIR_REGION=eu-frankfurt-1
export OCIR_TENANCY=<ns>
export OCIR_REPO=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-apm-java-demo
export REMOTE_HOST=control-plane-oci

./deploy/deploy-apm-java-demo.sh
```

Traffic generator is a CronJob in `deploy/k8s/oke/apm-java-demo/deployment.yaml`
that fires `/`, `/slow`, `/allocate`, `/error` every 5 min.

## Verify in the Console

1. OCI Console → Observability & Management → APM → Service Monitoring → **App servers**.
2. Compartment: `demo-applications`. APM domain: `oci-octo-demo-apm`.
3. Filter Service = `octo-apm-java-demo`.
4. Within 2–5 min you should see:
   - Apdex gauge (0.8–1.0 in normal operation, dips when `/error` hits)
   - Active Servers = 1
   - Resource consumption (request threads) chart
   - Server request rate (ops/min)
   - **App server CPU** table row with APM agent version, VM name
     (HotSpot / J9), VM version, Process CPU load %, Young GC time,
     Old GC time.

## How the agent gets wired

`Dockerfile` downloads the OCI APM Java agent zip at build time from
the public object-storage URL documented by Oracle. `entrypoint.sh`
attaches it via `-javaagent:<path>` and passes the three required
system properties:

```
-Dcom.oracle.apm.agent.data.upload.endpoint=${OCI_APM_ENDPOINT}
-Dcom.oracle.apm.agent.private.data.key=${OCI_APM_PRIVATE_DATAKEY}
-Dcom.oracle.apm.agent.service.name=octo-apm-java-demo
```

Both env vars come from the existing `octo-apm` K8s secret
(populated by `deploy/init-tenancy.sh`). No new secrets, no new IAM.

## If the agent zip download fails

Some tenancies restrict egress to Object Storage. The Dockerfile
degrades gracefully — `entrypoint.sh` detects a missing
`/opt/apm-agent/bootstrap/apm-java-agent.jar` and boots the app
*without* the agent. The app is still reachable, just absent from
the App Servers view.

To side-load the agent:
```bash
kubectl cp /local/apm-agent.zip \
  -n octo-drone-shop octo-apm-java-demo-<pod>:/tmp/
kubectl exec -n octo-drone-shop octo-apm-java-demo-<pod> -- sh -c \
  'cd /opt/apm-agent && unzip -o /tmp/apm-agent.zip && exit'
kubectl rollout restart deployment/octo-apm-java-demo -n octo-drone-shop
```
