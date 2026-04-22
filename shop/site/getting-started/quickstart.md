# Quick Start

## Local Development (Docker Compose)

```bash
# Clone
git clone https://github.com/adibirzu/octo-drone-shop.git
cd octo-drone-shop

# Start with PostgreSQL (no Oracle ATP needed)
docker compose up -d

# Verify
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

Open [http://localhost:8080/shop](http://localhost:8080/shop) for the storefront.

## Local Development (Python)

```bash
# Prerequisites: Python 3.12+, PostgreSQL
pip install -r requirements.txt

# Set PostgreSQL connection
export DATABASE_URL="postgresql://user:pass@localhost:5432/octodrone"

# Start
uvicorn server.main:app --host 0.0.0.0 --port 8080 --reload
```

## Verify Observability

```bash
# Health check
curl http://localhost:8080/health

# Readiness (includes DB, APM, RUM status)
curl http://localhost:8080/ready | python3 -m json.tool

# 360 Dashboard
curl http://localhost:8080/api/observability/360 | python3 -m json.tool

# Prometheus metrics
curl http://localhost:8080/metrics
```

## Run Tests

```bash
# E2E tests (237 Playwright tests)
npm install
npm run test:e2e

# Against live deployment
SHOP_URL=https://shop.<your-domain> npm run test:e2e
```
