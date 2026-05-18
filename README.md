# Distributed FastAPI — Learning Environment for OpenTelemetry

A self-contained, multi-service Python system designed for **learning the workflow of observability**: metrics → traces → logs, end-to-end. Every piece is real (no toy stubs), every part is instrumented with OpenTelemetry, and a built-in load generator + planted bugs let you practice debugging like in production.

> **📚 Start with [LEARN.md](./LEARN.md)** — 8 progressive exercises that teach the actual workflow. The rest of this file is a reference.

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

## Running tests

```bash
pip install -r requirements.txt
pip install pytest
pytest -v
```

18 tests cover every route across all 3 HTTP services. All external dependencies (OpenSearch, downstream services) are mocked.
