# Unified VM deployment

Single-VM alternative to the OKE path. Drone Shop + Enterprise CRM
Portal run as two containers behind nginx on one OCI Compute instance,
pointing at an existing OCI Autonomous Database (ATP).

Use this when:

- You want a demo/workshop environment that stands up in under 10
  minutes and has no Kubernetes moving parts.
- You need an air-gapped or region-restricted install where OKE is
  unavailable.
- You are reproducing an incident on an isolated copy of the stack.

Use OKE instead when: multi-replica, autoscaling, zero-downtime
rollouts, or WAF-as-code matter.

## Topology

```
                      ┌─────────────────────────────────────┐
                      │  OCI Compute VM (e.g. VM.Standard.  │
                      │  E5.Flex  2 OCPU / 16 GB)           │
                      │                                     │
    https://shop. ───►│  nginx  ──► shop  (uvicorn :8080)   │
          DOMAIN      │        └──► crm   (uvicorn :8080)   │
    https://crm.  ───►│                                     │
          DOMAIN      │  bridge network: octo               │
                      │  wallet mount: /opt/oracle/wallet   │
                      └────────────┬────────────────────────┘
                                   │ SQL*Net (mTLS over wallet)
                                   ▼
                            ┌─────────────────┐
                            │  OCI Autonomous │
                            │  Database (ATP) │
                            └─────────────────┘
```

Cross-service calls stay on the container network:
`SERVICE_CRM_URL=http://crm:8080`, `SERVICE_SHOP_URL=http://shop:8080`.
`INTERNAL_SERVICE_KEY` is the same shared secret used by the OKE deploy.

## Quick start

```bash
# 1. Pre-reqs on the VM
sudo dnf install -y git curl unzip                 # or apt-get install ...

# 2. Clone
git clone https://github.com/adibirzu/octo-apm-demo.git /opt/octo
cd /opt/octo/deploy/vm

# 3. Env
cp .env.template .env
${EDITOR:-vi} .env

# 4. Wallet (from OCI Console → ATP → DB Connection → Download Wallet)
unzip /path/to/Wallet_<DB>.zip -d wallet
# directory must contain cwallet.sso, ewallet.p12, tnsnames.ora, ...

# 5. TLS (one-shot via certbot)
sudo certbot certonly --standalone \
    -d shop.${DNS_DOMAIN} -d crm.${DNS_DOMAIN}
sudo cp /etc/letsencrypt/live/shop.${DNS_DOMAIN}/*.pem nginx/tls/shop/
sudo cp /etc/letsencrypt/live/crm.${DNS_DOMAIN}/*.pem  nginx/tls/crm/

# 6. Launch
sudo ./install.sh
```

## Validate

```bash
curl -s https://shop.${DNS_DOMAIN}/ready | jq
curl -s https://crm.${DNS_DOMAIN}/ready  | jq
curl -s https://shop.${DNS_DOMAIN}/api/integrations/schema | jq .info.title
curl -s https://crm.${DNS_DOMAIN}/api/integrations/schema  | jq .info.title
```

A healthy install returns the OpenAPI contract on both sides and both
`/ready` probes respond with `database.reachable = true`.

## cloud-init (one-shot bootstrap)

[`cloud-init.yaml`](cloud-init.yaml) is a cloud-init script you can
paste straight into the Oracle Cloud Compute create form. Replace the
`TODO` markers with your tenancy values; set `WALLET_PAR_URL` to a
pre-authenticated request URL for the wallet zip.

## Upgrades

```bash
cd /opt/octo/deploy/vm
sudo docker compose -f docker-compose-unified.yml --env-file .env pull
sudo systemctl restart octo.service
```

The `octo.service` systemd unit makes the stack survive reboots and
guarantees `docker compose up -d` runs with the right working
directory + env file on every boot.

## Observability on VM

APM + RUM + Log Analytics all work identically to the OKE deploy:
populate the same `OCI_APM_*` and `OCI_LOG_*` variables in `.env`. The
VM's instance principal must have policies granting `USE` on APM
domains and `use` on the target log group — otherwise the app runs
fine but OTLP/SDK pushes silently no-op.

## Multi-VM

This deploy is designed for a single VM. For HA, run two VMs behind an
OCI Load Balancer with Oracle Data Guard on the ATP side — or use the
OKE path, which is already multi-replica by default.
