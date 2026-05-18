# Screenshots

This folder is where you capture screenshots after your first successful boot. The README references these paths, so committing them gives anyone browsing the repo a preview of what they'll get.

## Suggested set

| Filename | What to capture |
|---|---|
| `jaeger-trace-tree.png` | A `POST /api/items` trace expanded in Jaeger, showing all 4 services (gateway, users-svc, items-svc, notifications-svc) |
| `jaeger-span-tags.png` | Detail view of a span with `chaos.delay_ms` or `item.id` attributes visible |
| `grafana-overview.png` | The full "Distributed FastAPI — Overview" dashboard with steady traffic from the load generator |
| `grafana-error-spike.png` | The error-rate panel during Exercise 4 (chaos errors enabled) |
| `prometheus-query.png` | A PromQL query result, e.g. `histogram_quantile(0.95, ...)` |

## How to capture

```bash
docker compose -f deploy/docker-compose.yml up --build -d
# Wait ~45s, let the loadgen run for at least 30s
# Then visit the URLs below and capture:
#   http://localhost:16686  — Jaeger
#   http://localhost:3001   — Grafana ("Distributed FastAPI — Overview")
#   http://localhost:9090   — Prometheus
```

PNG screenshots ≤ ~500 KB per file is courteous to people on slow connections.
