# OTel Demo — Distributed Tracing with Grafana Tempo

A portfolio demo of the **three pillars of observability** — metrics, logs, and traces —
using a realistic e-commerce microservices setup with a ClickHouse data warehouse.

## Stack

| Layer | Tool |
|---|---|
| Services | Python FastAPI (3 microservices) |
| Instrumentation | OpenTelemetry SDK + auto-instrumentation |
| Telemetry collector | OpenTelemetry Collector |
| Trace storage | Grafana Tempo |
| Metrics storage | Prometheus |
| Log storage | Grafana Loki |
| Visualisation | Grafana |
| Data warehouse | ClickHouse |
| App databases | PostgreSQL + Redis |
| Host metrics | Node Exporter |
| Load simulation | Load Generator |

## Project Structure

```
otel-demo/
├── docker-compose.yml
├── README.md
├── order-service/          # Entry point — POST /orders
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── inventory-service/      # Stock check with Redis cache
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── payment-service/        # Payment processing
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── load-generator/         # Sends randomized traffic indefinitely
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── otel-collector/
│   └── config.yaml
└── grafana/
    ├── tempo/
    │   └── config.yaml
    ├── prometheus/
    │   └── prometheus.yml
    ├── loki/
    │   └── config.yaml
    └── provisioning/
        ├── datasources/
        │   └── datasources.yaml
        └── dashboards/
            ├── dashboards.yaml
            └── otel-demo.json
```

## Services

| Service | Port | Role |
|---|---|---|
| order-service | 8000 | Entry point — POST /orders |
| inventory-service | 8001 | Stock check with Redis cache |
| payment-service | 8002 | Payment processing |
| load-generator | — | Sends randomized traffic indefinitely |
| otel-collector | 4317 / 4318 | Receives and routes all telemetry |
| prometheus | 9090 | Metrics storage |
| loki | 3100 | Log storage |
| tempo | 3200 | Trace storage |
| grafana | 3000 | Visualisation UI |
| postgres | 5432 | Orders database |
| redis | 6379 | Stock cache |
| node-exporter | 9100 | Host metrics (internal only) |

## Quickstart

```bash
git clone <your-repo>
cd otel-demo
docker compose up --build
```

Wait about 30 seconds for all services to be healthy, then open:

| URL | What |
|---|---|
| http://localhost:3000 | Grafana (user: admin / pass: admin) |
| http://localhost:8000/docs | Order Service Swagger UI |
| http://localhost:8000/demo/scenarios | All demo curl commands |
| http://localhost:8001/stock | Available item IDs |
| http://localhost:9090 | Prometheus (raw metrics) |

The load generator starts automatically and sends traffic indefinitely — your
Grafana dashboard will have live data immediately without any manual requests.

---

## Load Generator

The load generator runs inside Docker and cycles through 5 traffic patterns
automatically, each lasting 1-5 minutes before switching to the next:

| Pattern | Weight | Behavior |
|---|---|---|
| `normal` | 40% | Steady low traffic, 2-5s between requests |
| `busy` | 20% | Flash sale simulation, 0.2-1s delay, occasional bursts |
| `degraded` | 15% | 80% slow queries — triggers bottleneck scenario |
| `payment_issues` | 15% | 70% payment failures — spikes error rate |
| `quiet` | 10% | Off-hours, 5-15s between requests |

Watch it run:
```bash
docker compose logs load-generator -f
```

To stop the load generator without stopping everything else:
```bash
docker compose stop load-generator
```

To restart it:
```bash
docker compose start load-generator
```

---

## Demo Scenarios

### 1. Normal trace waterfall
```bash
curl -s -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"item_id": "laptop", "quantity": 1}' | jq
```
Copy the `trace_id` from the response → Grafana → Explore → Tempo → paste it.
You will see the full waterfall across all 3 services.

---

### 2. Slow query — bottleneck detection
```bash
# Clear Redis cache first to force the DB path
curl -X DELETE http://localhost:8001/cache/keyboard

curl -s -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"item_id": "keyboard", "quantity": 1, "slow_query": true}' | jq
```
In Tempo the `db-stock-lookup` span on inventory-service balloons to ~2s.
All other spans are under 150ms — the bottleneck is immediately obvious.

---

### 3. Error trace — find which service failed
```bash
curl -s -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"item_id": "laptop", "quantity": 1, "fail_payment": true}' | jq
```
The response body includes a `trace_id` even on failure:
```json
{ "detail": "Payment failed", "trace_id": "a3f9c12d..." }
```
Copy that `trace_id` → Grafana → Explore → Tempo → paste it.
The `payment-gateway-call` span will be red. Click it to see the full exception.

---

### 4. Metrics → Logs → Traces correlation

The load generator already produces this automatically. Just open Grafana and:

1. Open the **OTel Demo — Order System** dashboard
2. Watch **Payment Failure Rate (%)** — it climbs naturally from random 10% failures
3. Scroll to **Error Logs Only** panel — find a log line with `level=ERROR`
4. Expand the log line → click **"View trace in Tempo"** next to the `traceid` field
5. See the exact red span, exception message, and all span attributes

---

## Understanding the Dashboard

### p50 / p95 / p99 — what do they mean?

These are **percentiles** of request duration. They answer the question:
"What percentage of requests complete within this time?"

- **p50** — 50% of requests finish within this duration. This is the median — what a
  typical user experiences.
- **p95** — 95% of requests finish within this duration. The slowest 5% take longer.
  This is what your worst-case regular users experience.
- **p99** — 99% of requests finish within this duration. Only the slowest 1% take
  longer. This catches extreme outliers.

Example: if p50=120ms, p95=450ms, p99=2100ms it means most users are fine but a
small number are hitting something very slow — likely the slow query scenario.
Averages would hide this completely. Percentiles reveal it.

### Why are there multiple boxes in Total Orders / Total Payment Failures?

Each stat panel shows **one box per label combination** because the metrics are tagged.

For example `orders_total` is recorded with tags:
```
orders_total{item_id="laptop",  status="confirmed"} 42
orders_total{item_id="keyboard", status="confirmed"} 17
orders_total{item_id="monitor",  status="confirmed"} 8
```

So Grafana renders one box per unique `item_id` + `status` combination. This is
actually useful — you can see at a glance which items are selling most. The same
applies to payment failures, which are tagged by `reason` (random_gateway_rejection,
forced_by_demo_flag, etc.) so you can see the breakdown of why payments are failing.

If you want a single total number, the PromQL query needs a `sum()` wrapper:
```promql
sum(increase(demo_orders_total[24h]))
```

---

## Telemetry Architecture

```
Your services (order / inventory / payment)
    → OTel SDK pushes spans + metrics + logs via OTLP gRPC :4317
        → OTel Collector receives everything
            ├── traces   → Grafana Tempo    (waterfall view)
            ├── metrics  → Prometheus       (dashboards + alerts)
            ├── logs     → Grafana Loki     (log explorer)
            └── all three → ClickHouse     (data warehouse / analytics)

Node Exporter (host metrics: CPU, memory, disk, network)
    → OTel Collector scrapes :9100
        ├── metrics → Prometheus
        └── metrics → ClickHouse

Load Generator
    → sends randomized HTTP requests to order-service
        → triggers real traces, metrics, and logs automatically
```

---

## Loki Log Queries

| What you want | Query |
|---|---|
| All logs | `{job=~".+"}` |
| Errors only | `{level="ERROR"}` |
| order-service logs | `{job=~".+"} \| json \| attributes_otelServiceName = "order-service"` |
| By trace ID | `{job=~".+"} \| json \| traceid = "your-trace-id"` |
| Keyword search | `{job=~".+"} \|= "Payment failed"` |
| Slow query logs | `{job=~".+"} \|= "SLOW QUERY"` |

---

## What's in ClickHouse

All telemetry is stored in the `otel` database:

| Table | Contents |
|---|---|
| `otel.otel_traces` | All spans from all 3 services |
| `otel.otel_logs` | All log lines from all 3 services |
| `otel.otel_metrics_sum` | Counters (orders_total, payment_failures_total, etc.) |
| `otel.otel_metrics_gauge` | Gauges (node CPU, memory, disk, network) |
| `otel.otel_metrics_histogram` | Histograms (order_duration_seconds, etc.) |

Sample ClickHouse queries:
```sql
-- Count orders in last hour
SELECT count() FROM otel.otel_traces
WHERE ServiceName = 'order-service'
AND Timestamp >= now() - INTERVAL 1 HOUR;

-- Find all error logs
SELECT Timestamp, Body FROM otel.otel_logs
WHERE SeverityText = 'ERROR'
ORDER BY Timestamp DESC LIMIT 20;

-- Payment failure rate per minute
SELECT
  toStartOfMinute(TimeUnix) as minute,
  sum(Value) as failures
FROM otel.otel_metrics_sum
WHERE MetricName = 'demo_payment_failures_total'
GROUP BY minute ORDER BY minute DESC LIMIT 30;

-- Node CPU usage
SELECT MetricName, Value FROM otel.otel_metrics_gauge
WHERE MetricName LIKE '%node_cpu%'
LIMIT 10;
```

---

## How instrumentation works

Each service uses **OTel auto-instrumentation** for the boilerplate (incoming HTTP,
outgoing HTTP, Redis, SQLAlchemy) and **manual spans** for business logic steps.

```
Request arrives at order-service
  └── [auto] POST /orders                         ← FastAPIInstrumentor
        ├── [manual] check-inventory
        │     └── [auto] GET /stock/{id}          ← HTTPXClientInstrumentor
        │           ├── [manual] redis-cache-lookup  ← RedisInstrumentor
        │           └── [manual] db-stock-lookup
        ├── [manual] process-payment
        │     └── [auto] POST /charge             ← HTTPXClientInstrumentor
        │           ├── [manual] validate-charge
        │           ├── [manual] payment-gateway-call
        │           └── [manual] record-transaction
        └── [manual] save-order-db                ← SQLAlchemyInstrumentor
```

Every log line automatically contains `traceid` and `spanid` via `OTLPLoggingHandler`
— this is what enables the **"View trace in Tempo"** link in Grafana's log explorer
and ensures logs are correlated with traces in ClickHouse.

---

## Stopping the demo
```bash
docker compose down -v   # -v also removes volumes (wipes stored traces/metrics/logs)
```