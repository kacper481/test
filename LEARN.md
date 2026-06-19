# Learning Path: Observability with OpenTelemetry

A progressive set of exercises that teach the **workflow** of debugging a distributed system using OpenTelemetry traces, metrics, and structured logs. Configuration of the SDK is the easy part — these exercises focus on the skill that actually matters: looking at telemetry and figuring out what's wrong.

## Setup

```bash
docker compose -f deploy/docker-compose.yml up --build -d
```

Wait ~45 seconds for everything to come up, then check:

| Tool | URL | What you'll see |
|---|---|---|
| Jaeger | http://localhost:16686 | Distributed traces |
| Prometheus | http://localhost:9090 | Raw metrics + PromQL |
| Grafana | http://localhost:3001 | Pre-built "Distributed FastAPI — Overview" dashboard |
| RabbitMQ | http://localhost:15672 | Queue depths (guest / guest) |
| Gateway docs | http://localhost:8000/docs | Try requests manually |

The `loadgen` service is already hammering the gateway at ~3 req/s, so dashboards have data within ~30s.

To stop everything: `docker compose -f deploy/docker-compose.yml down`.

---

## Exercise 1 — Your first trace

**Goal:** find a single request in Jaeger and read its trace tree.

```bash
curl localhost:8000/api/users -X POST -H 'Content-Type: application/json' \
  -d '{"name":"alice","email":"a@x.com"}'
```

1. Open Jaeger (http://localhost:16686).
2. In the **Service** dropdown, pick `gateway`. Click **Find Traces**.
3. Click the most recent `POST /api/users` trace.

**Check yourself:**
- How many services participated in this trace? *(answer: 2 — gateway and users-svc)*
- How long did the whole request take? Where was time spent — gateway, users-svc, or OpenSearch?
- Click any span and look at its **Tags**. Find the `http.status_code`, `http.method`, and `http.route`.

---

## Exercise 2 — Anatomy of a fan-out trace

**Goal:** understand how one HTTP request can produce many spans across multiple services.

```bash
# First create a user, then create an item owned by them
USER=$(curl -s -X POST localhost:8000/api/users \
  -H 'Content-Type: application/json' \
  -d '{"name":"bob"}' | jq -r .id)

curl -X POST localhost:8000/api/items \
  -H 'Content-Type: application/json' \
  -d "{\"title\":\"my widget\",\"description\":\"awesome\",\"owner_id\":\"$USER\"}"
```

Find the `POST /api/items` trace in Jaeger.

**Check yourself:**
- Find these spans, in order: `POST /api/items` → `gateway.validate_owner` → `GET /users/{user_id}` (in **users-svc**) → `users.get` → an OpenSearch HTTP call → then `POST /items` (in **items-svc**) → `items.create` → another OpenSearch call.
- Now find the `publish items.created` span and the `consume items.created` span — the second is in **notifications-svc**, in a *different process*. The trace continued across a message queue. How did that work? *(answer: the gateway injects W3C `traceparent` into the message headers; the worker extracts it)*

---

## Exercise 3 — Find the slow one (planted bug #1)

**Goal:** use Jaeger to localize unexplained slowness to a single span.

Turn on a planted latency bug:

```bash
# In deploy/docker-compose.yml, uncomment this line in items-svc:
#     CHAOS_ITEMS_SEARCH_MS: "300"
# Then:
docker compose -f deploy/docker-compose.yml up -d items-svc
```

Now hammer the search endpoint a few times:

```bash
for i in 1 2 3 4 5; do curl -s "localhost:8000/api/items?q=red" > /dev/null; done
```

In Jaeger, find a slow `GET /api/items` trace.

**Check yourself:**
- Which span is suspicious? *(answer: `items.search` in items-svc takes ~300ms more than before)*
- Click that span. In its Tags, find `chaos.delay_ms` and `chaos.source`. The chaos module wrote a breadcrumb directly onto the span explaining itself.
- Now turn it off (comment the env var, `docker compose up -d items-svc`) and confirm traces speed back up.

**Lesson:** when one slow span dominates a trace, your bug is in that service's code path — not the network, not upstream, not downstream.

---

## Exercise 4 — Find the error (planted bug #2)

**Goal:** correlate a 5xx spike in metrics with a specific failing span and log line.

Turn on intermittent failures in users-svc:

```bash
# Uncomment in deploy/docker-compose.yml, users-svc section:
#     CHAOS_USERS_GET_ERROR_RATE: "0.3"   # 30% failure rate
docker compose -f deploy/docker-compose.yml up -d users-svc
```

Wait ~30 seconds, then open **Grafana → Distributed FastAPI — Overview**. The "Error rate (5xx) by service" panel should light up.

1. **From metrics → traces:** in Jaeger, filter by `Tags: error=true` (or just look for red traces) and find one. Notice the failing span is `users.get`.
2. **From traces → logs:** click the failing span, copy its `trace_id` from the Span tags. Now:
   ```bash
   docker compose -f deploy/docker-compose.yml logs users-svc | grep <trace_id>
   ```
   You should see the structured JSON log line for that exact request, including `span_id`. **This is the key skill:** traces tell you *where*, logs tell you *what*.

**Check yourself:**
- What fraction of requests fail? Does the error rate panel agree with `CHAOS_USERS_GET_ERROR_RATE`?
- Find the failing span's `chaos.failure: true` attribute.

Turn it off when done.

---

## Exercise 5 — Sequential vs parallel fan-out

**Goal:** see the difference between sequential and concurrent downstream calls in trace timelines.

```bash
# A "get item" request fetches the item AND its owner.
curl localhost:8000/api/items/<some-item-id>
```

In Jaeger, find that trace.

**Check yourself:**
- Look at `_fetch_item` and `_fetch_owner` in the span timeline. Are they sequential or parallel?  
  *(answer in `services/gateway/routes.py:get_item`: they're sequential — `await _fetch_item()` then `await _fetch_owner(...)`. The owner_id isn't known until the item arrives.)*
- Now look at a `GET /health` trace — the gateway pings items-svc and users-svc with `asyncio.gather`. You should see the two child spans starting at the same time and overlapping.

**Lesson:** trace timelines show you sequential bottlenecks instantly. Two child spans that *could* run in parallel but are drawn end-to-end mean you're leaving latency on the table.

---

## Exercise 6 — Cross-process tracing through a queue

**Goal:** prove that the trace continues from gateway → RabbitMQ → notifications-svc, even though they don't share an HTTP call.

```bash
curl -X POST localhost:8000/api/items \
  -H 'Content-Type: application/json' \
  -d "{\"title\":\"queue test\",\"owner_id\":\"$USER\"}"
```

Find the trace. Look at all the services involved.

**Check yourself:**
- Which 4 services appear in this single trace? *(answer: gateway, users-svc, items-svc, notifications-svc)*
- Find the `publish items.created` and `consume items.created` spans. The consume span happens *after* the response was returned to the client — yet it's part of the same trace.
- Read `services/gateway/events.py` and `services/notifications_svc/worker.py` and find the two lines that make this work: `propagate.inject(headers)` and `propagate.extract(headers)`. Everything else is plumbing — those two calls are the whole mechanism.

---

## Exercise 7 — Metrics-first debugging

**Goal:** practice the production workflow: spot an anomaly in metrics, then drill into a specific trace.

In Grafana, open the "p95 latency" panel. With the load generator running steady, you should see steady lines.

Now turn on **two** chaos toggles at once:

```bash
# In compose: enable BOTH CHAOS_ITEMS_SEARCH_MS=300 AND CHAOS_GATEWAY_VALIDATE_MS=80
docker compose -f deploy/docker-compose.yml up -d items-svc gateway
```

Watch the dashboard for ~1 minute.

**Check yourself:**
- Which service has elevated p95 latency? *(both items-svc and gateway)*
- Which route on each service? In Prometheus, run:
  ```
  histogram_quantile(0.95, sum by (service_name, http_route, le) (rate(app_http_server_duration_milliseconds_bucket[2m])))
  ```
- Now grab a trace from one of the slow endpoints and verify the slowness is in the spans you expect.

**Lesson:** metrics tell you *something* is wrong; traces tell you *what*. You don't read every trace — you read the trace for the request that looked weird in a metric.

---

## Exercise 8 — Write your own span

**Goal:** add a custom span with a meaningful business attribute — from scratch.

Open `services/gateway/routes.py` and find the `search_items` handler. Inside the `if owner_ids:` block you'll see a raw `http.post(...)` call that batch-fetches owners. Wrap it in a custom span so the owner-hydration step is visible as its own node in Jaeger:

```python
with _tracer.start_as_current_span("gateway.hydrate_owners") as span:
    span.set_attribute("hydrate.owner_count", len(owner_ids))
    mget_resp = await http.post(
        f"{request.app.state.users_url}/users/_mget",
        json={"ids": owner_ids},
    )
    mget_resp.raise_for_status()
    owners_by_id = {u["id"]: u for u in mget_resp.json()["users"]}
```

`_tracer` is already imported at the top of the file — no extra import needed.

Then rebuild and search:
```bash
docker compose -f deploy/docker-compose.yml up -d --build gateway
curl "localhost:8000/api/items?q=red"
```

Find the trace in Jaeger. You should now see `gateway.hydrate_owners` as a child span of the search request, with `hydrate.owner_count` in its tags.

**Bonus:** record the `owner_count` in a histogram metric (`common/metrics.py`) and query it in Prometheus.

---

## Recap: the workflow you've just learned

1. **A user reports something is wrong** → start in Grafana (dashboards).
2. **You see an anomaly** (latency, error rate, throughput) → identify which service + route.
3. **You jump to Jaeger** for that service/route → find a representative slow/failing trace.
4. **You read the trace** → find the suspicious span (slowest, errored, unexpected).
5. **You grab the `trace_id`** → grep the relevant service's logs → see the application-level context (what data, what code path).
6. **You fix the bug** → re-deploy → confirm the metric returns to normal.

That's it. That loop — metrics → traces → logs — is what observability tooling exists for. Setting up the SDK is just the price of admission.

---

## What to read in the codebase

| File | Why |
|---|---|
| `common/telemetry.py` | The complete OTel bootstrap. ~50 lines does it all. |
| `common/logging.py` | How `trace_id`/`span_id` get injected into every log line. |
| `services/gateway/events.py` | Manual trace context injection into RabbitMQ messages. |
| `services/notifications_svc/worker.py` | Manual extraction on the consumer side. |
| `services/items_svc/store.py` | Custom spans with business attributes (`item.id`, `search.query`). |
| `common/chaos.py` | How the planted bugs work — entirely opt-in via env vars. |
| `deploy/otel-collector-config.yaml` | Splits one OTLP stream into Jaeger (traces) + Prometheus (metrics). |
