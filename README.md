# Distributed FastAPI + Full OpenTelemetry Stack

A 3-service Python system instrumented end-to-end with OpenTelemetry traces, metrics, and structured logs — all backed by OpenSearch and observable in Jaeger + Prometheus.

## Architecture

```
                       ┌──────────────────┐
                       │     gateway      │ :8000  (public API)
                       └────────┬─────────┘
                                │ httpx (OTel-instrumented)
                ┌───────────────┴───────────────┐
                ▼                               ▼
        ┌──────────────┐                ┌──────────────┐
        │  items-svc   │ :8001          │  users-svc   │ :8002
        └──────┬───────┘                └──────┬───────┘
               │                                │
               └────────────────┬───────────────┘
                                ▼
                        ┌──────────────┐
                        │  OpenSearch  │ :9200
                        └──────────────┘

       traces/metrics                logs (with trace_id)
              │                              │
              ▼                              ▼
     ┌──────────────────┐              docker logs
     │ OTel Collector   │ :4317
     └──┬───────────┬───┘
        ▼           ▼
   ┌────────┐  ┌────────────┐
   │ Jaeger │  │ Prometheus │
   │ :16686 │  │  :9090     │
   └────────┘  └────────────┘
```

## Quick start

```bash
docker compose -f deploy/docker-compose.yml up --build -d
```

Wait ~30s for OpenSearch to become healthy, then:

```bash
# 1. Create a user
USER=$(curl -s -X POST localhost:8000/api/users \
  -H 'Content-Type: application/json' \
  -d '{"name":"alice","email":"alice@example.com"}' | jq -r .id)

# 2. Create an item owned by that user (gateway validates owner first)
curl -X POST localhost:8000/api/items \
  -H 'Content-Type: application/json' \
  -d "{\"title\":\"hello\",\"description\":\"world\",\"owner_id\":\"$USER\"}"

# 3. Search items (gateway hydrates owners in a batch call)
curl "localhost:8000/api/items?q=hello" | jq
```

## Where to see what

| What | Where |
|---|---|
| Traces (distributed across all 3 services) | http://localhost:16686 — pick service `gateway` |
| Metrics (RED + business counters) | http://localhost:9090 — try `rate(app_items_created_total[1m])` |
| Structured logs with `trace_id` | `docker compose -f deploy/docker-compose.yml logs -f gateway` |

## How observability works

- **Traces** — `FastAPIInstrumentor` creates a root span per request; `HTTPXClientInstrumentor` creates child spans for downstream HTTP calls and injects W3C `traceparent` headers so all 3 services share one trace. `RequestsInstrumentor` covers `opensearch-py`. Custom spans in `store.py` files add business attributes.
- **Metrics** — Both standard HTTP server metrics (auto) and custom counters/histograms in `common/metrics.py` are exported via OTLP to the Collector, which exposes them on `:8889` for Prometheus to scrape.
- **Logs** — `structlog` emits JSON; `LoggingInstrumentor` injects `trace_id`/`span_id` into every record. Grab a `trace_id` from a log line, paste into Jaeger search to jump to the full trace.
- **Baggage** — Gateway sets a `request.id` in OTel baggage; it propagates automatically to downstream service spans.
