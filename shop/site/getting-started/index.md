# Getting Started

Deploy the OCTO platform from the unified
[`octo-apm-demo`](https://github.com/adibirzu/octo-apm-demo) project.
This service repo remains useful for app-level development, but new OCI
tenancy deployments should use the unified deployment stack.

## Deployment Options

| Option | Time | Requirements |
|---|---|---|
| [Quick Start](quickstart.md) | 5 min | Docker, PostgreSQL (local dev) |
| [OKE Deployment](oke-deployment.md) | 30 min | OCI OKE cluster, Oracle ATP, OCI APM |
| [Private Compute Deployment](https://adibirzu.github.io/octo-apm-demo/getting-started/compute-deployment/) | 60-90 min | OCI tenancy, Resource Manager, private ATP, LB/WAF |

## Sections

- [Prerequisites](prerequisites.md) — What you need before deploying
- [Quick Start](quickstart.md) — Local development with Docker
- [OKE Deployment](oke-deployment.md) — Production deployment on Oracle Kubernetes Engine
- [Unified Deployment Options](https://adibirzu.github.io/octo-apm-demo/getting-started/deployment-options/) — Private Compute, OKE, Resource Manager, and single-VM paths
