# Distributed FastAPI — Learning Environment for OpenTelemetry

[![tests](https://github.com/kacper481/test/actions/workflows/test.yml/badge.svg)](https://github.com/kacper481/test/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

A self-contained, multi-service Python system designed for **learning the workflow of observability**: metrics → traces → logs, end-to-end. Every piece is real (no toy stubs), every part is instrumented with OpenTelemetry, and a built-in load generator + planted bugs let you practice debugging like in production.

> **📚 Start with [LEARN.md](./LEARN.md)** — 8 progressive exercises that teach the actual workflow. The rest of this file is a reference.

> ⚠️ **Defaults are for local learning, not production.** Out of the box the OpenSearch security plugin is disabled, RabbitMQ uses `guest`/`guest`, and Grafana allows anonymous admin — for a frictionless loop. The gateway ships with opt-in API-key auth and rate limiting (see [Security hardening](#security-hardening-opt-in)), but there's more to do before real traffic — see [What is and isn't production-ready](#what-is-and-isnt-production-ready). **Don't expose the default configuration publicly.**

## What you'll see

Once the stack is up and the load generator has run for ~30 seconds, you can drill from dashboards down into individual traces:

```
                       Grafana                                  Jaeger
                   ───────────────                          ───────────────
  Request rate by service          ┐       POST /api/items                       (gateway)
  p95 latency  ────────►  spike    │       ├── gateway.validate_owner
  ────────────────────────► click  └──►    │   └── HTTP GET /users/{id}          (gateway → users-svc)
                                           │       └── users.get
                                           │           └── HTTP GET .../users/_doc/...   (→ OpenSearch)
                                           ├── HTTP POST /items                  (gateway → items-svc)
                                           │   └── items.create
                                           │       └── HTTP PUT .../items/_doc/...
                                           └── publish items.created             (gateway → RabbitMQ)
                                               └── consume items.created         (notifications-svc)
                                                   └── send_email
```

One logical request → 4 services → traces, metrics, and structured logs all correlated by `trace_id`.

*(Screenshots of Jaeger & Grafana go in [`docs/screenshots/`](./docs/screenshots/) — see the README in that folder for capture instructions.)*

## Architecture

```
                       ┌────────────────────┐
   loadgen ─────────►  │      gateway       │ :8000  (public API)
                       └─────┬──────────┬───┘
                             │ httpx    │ aio-pika publish (items.created)
              ┌──────────────┘          ▼
              ▼                   ┌──────────────┐       ┌─────────────────────┐
       ┌──────────────┐           │   RabbitMQ   │ ◄──── │ notifications-svc   │
       │  items-svc   │ :8001     └──────────────┘       │ (async consumer)    │
       └──────┬───────┘                                  └─────────────────────┘
              │
       ┌──────────────┐
       │  users-svc   │ :8002
       └──────┬───────┘
              ▼
       ┌──────────────┐
       │  OpenSearch  │ :9200
       └──────────────┘

   traces ───────────────►  ┌──────────────────┐  ──── traces ──►  Jaeger :16686
   metrics ──────────────►  │  OTel Collector  │
   (all 4 services)         └──────────────────┘  ──── metrics ─►  Prometheus :9090
                                                                          │
                                                                          ▼
                                                                   Grafana :3001
                                                                   (pre-built dashboard)
```

## Quickstart

```bash
docker compose -f deploy/docker-compose.yml up --build -d
```

After ~45s everything is up and the load generator is sending traffic. Then open:

| Tool | URL | Notes |
|---|---|---|
| Grafana | http://localhost:3001 | Pre-built "Distributed FastAPI — Overview" dashboard |
| Jaeger | http://localhost:16686 | Select service `gateway`, click *Find Traces* |
| Prometheus | http://localhost:9090 | Raw metrics + PromQL |
| RabbitMQ | http://localhost:15672 | `guest` / `guest` — see queue depths |
| Gateway docs | http://localhost:8000/docs | Try requests manually |

Stop everything: `docker compose -f deploy/docker-compose.yml down`.

## What's in here

| Path | Purpose |
|---|---|
| `services/gateway/` | Public API, fans out to downstreams, publishes events |
| `services/items_svc/` | Items CRUD + search with aggregations |
| `services/users_svc/` | Users CRUD + batch mget |
| `services/notifications_svc/` | RabbitMQ consumer, demonstrates async trace propagation |
| `common/telemetry.py` | OTel SDK bootstrap (~50 lines, does traces + metrics + log correlation) |
| `common/logging.py` | structlog JSON, auto-injects `trace_id` / `span_id` |
| `common/chaos.py` | Env-var-toggled latency + error injection for exercises |
| `common/metrics.py` | Custom business counters / histograms |
| `tools/loadgen.py` | Continuous traffic generator (scenarios: steady / spike / read_heavy / write_heavy) |
| `deploy/` | docker-compose, Dockerfile, OTel collector config, Prometheus config, Grafana provisioning + dashboard |
| `tests/` | Pytest suite (18 tests, fully mocked, run with `pytest`) |
| `LEARN.md` | **The exercises — start here** |

## Manual interaction

```bash
# Health checks
curl localhost:8000/health

# Create a user, then an item
USER=$(curl -s -X POST localhost:8000/api/users \
  -H 'Content-Type: application/json' \
  -d '{"name":"alice","email":"a@x.com"}' | jq -r .id)

curl -X POST localhost:8000/api/items \
  -H 'Content-Type: application/json' \
  -d "{\"title\":\"hello\",\"description\":\"world\",\"owner_id\":\"$USER\"}"

# Search (with owner hydration)
curl "localhost:8000/api/items?q=hello" | jq

# Watch logs (JSON, includes trace_id for Jaeger correlation)
docker compose -f deploy/docker-compose.yml logs -f gateway
```

## Chaos / exercise toggles

Set these env vars in `deploy/docker-compose.yml` to enable planted bugs for the exercises:

| Variable | Effect | Used in exercise |
|---|---|---|
| `CHAOS_ITEMS_SEARCH_MS=300` | Adds 300ms latency to items search | Ex 3, 7 |
| `CHAOS_USERS_GET_ERROR_RATE=0.3` | 30% of users.get requests return 500 | Ex 4 |
| `CHAOS_GATEWAY_VALIDATE_MS=80` | Adds latency to owner-validation hop | Ex 7 |
| `CHAOS_OS_INDEX_SLOW_MS=150` | Slows down OpenSearch index ops | — |

Each toggle writes a `chaos.delay_ms` / `chaos.failure` attribute onto the affected span so you can spot it in Jaeger.

## Security hardening (opt-in)

The defaults are wide open for a frictionless learning loop. The gateway ships with two opt-in production controls — set the env var to turn each on:

| Variable | Effect |
|---|---|
| `GATEWAY_API_KEY=<secret>` | Require an `X-API-Key: <secret>` header on every `/api/*` request (returns 401 if missing, 403 if wrong). `/health` stays open for liveness probes. |
| `RATE_LIMIT_PER_MINUTE=<N>` | Per-client-IP rate limit; excess requests get HTTP 429. |
| `RABBITMQ_USER` / `RABBITMQ_PASS` | Override the broker's default `guest`/`guest` credentials. |
| `LOADGEN_API_KEY=<secret>` | Make the bundled load generator send the API key (match `GATEWAY_API_KEY`). |

Example — run the stack locked down:

```bash
GATEWAY_API_KEY=$(openssl rand -hex 16) \
RATE_LIMIT_PER_MINUTE=120 \
RABBITMQ_USER=app RABBITMQ_PASS=$(openssl rand -hex 16) \
docker compose -f deploy/docker-compose.yml up -d
```

These are real, tested controls (see `tests/test_security.py`) — but they are the **floor**, not a complete production posture. See the next section.

## What is and isn't production-ready

This project is built to *teach observability*, and it is genuinely solid in that role: real services, real instrumentation, a tested codebase, and opt-in auth/rate-limiting. But do **not** mistake "runs cleanly with `docker compose up`" for "ready to serve real traffic." Honest gaps before you'd put this in front of users:

**Secrets & config**
- Secrets live in env vars / `.env` files. Real deployments need a secret manager (Vault, AWS/GCP Secrets Manager, sealed secrets) — never secrets in compose or git.
- No secret rotation, no per-client API keys, no key revocation. The single shared API key is a demo-grade control; real systems want OAuth2/OIDC or JWTs.

**Transport & network**
- All traffic is plaintext HTTP. Production needs TLS everywhere (a reverse proxy / ingress terminating HTTPS, and ideally mTLS between services).
- OpenSearch runs with its security plugin **disabled** and Grafana allows **anonymous admin**. Both must be locked down with real auth before exposure.

**Resilience & scale**
- Single-node OpenSearch, single RabbitMQ, single replica per service — no high availability. Production wants clustering, replication, and multiple replicas behind a load balancer.
- The in-memory rate limiter is per-process; with multiple gateway replicas you'd need a shared backend (e.g. Redis via slowapi's `storage_uri`).
- No connection-retry/backoff if OpenSearch or RabbitMQ are slow to come up beyond compose healthchecks; no circuit breakers on downstream calls.

**Operations**
- No alerting or SLOs — you get dashboards, but nothing pages you. Add Alertmanager / Grafana alerts tied to the RED metrics.
- No persistent volumes configured for OpenSearch/Prometheus data; restarts lose data.
- Container images aren't pinned by digest, run as root, and aren't scanned. Production wants digest pins, a non-root user, and image scanning in CI.
- Intended for Docker Compose on one host. Real deployment targets (Kubernetes, ECS) need their own manifests, probes, autoscaling, and resource requests/limits.

Treat the checklist above as the roadmap from "great learning environment" to "production service."

## Running tests

```bash
pip install -r requirements.txt
pip install pytest
pytest -v
```

34 tests cover every route across the 3 HTTP services, cross-process trace propagation through RabbitMQ, the chaos toggles, and the opt-in auth + rate-limiting controls. All external dependencies (OpenSearch, RabbitMQ, downstream services) are mocked.
