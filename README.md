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

## Project Structure

```
otel-demo/
├── docker-compose.yml
├── order-service/          # Entry point — POST /orders
├── inventory-service/      # Stock check with Redis cache
├── payment-service/        # Payment processing
├── otel-collector/         # Receives and routes all telemetry
└── grafana/
    ├── tempo/              # Trace storage config
    ├── prometheus/         # Metrics scrape config
    ├── loki/               # Log storage config
    └── provisioning/       # Auto-loads datasources + dashboard
```

## Services

| Service | Port | Role |
|---|---|---|
| order-service | 8000 | Entry point — POST /orders |
| inventory-service | 8001 | Stock check with Redis cache |
| payment-service | 8002 | Payment processing |
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

---

## Demo Scenarios

### 1. Normal trace waterfall
```bash
curl -s -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"item_id": "laptop", "quantity": 1}' | jq
```
Copy the `trace_id` from the response → open Grafana → Explore → Tempo → paste it.
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
The `payment-gateway-call` span will be red. Click it to see the full exception message and attributes.

---

### 4. Metrics → Logs → Traces correlation
Generate load with random failures:
```bash
for i in $(seq 1 40); do
  curl -s -X POST http://localhost:8000/orders \
    -H "Content-Type: application/json" \
    -d '{"item_id": "laptop", "quantity": 1}' > /dev/null
  sleep 0.5
done
```

Then in Grafana:
1. Open the **OTel Demo — Order System** dashboard
2. Watch **Payment Failure Rate (%)** climb (random ~10% failure rate)
3. Scroll to **Error Logs Only** panel — find a log line with `"level": "ERROR"`
4. Click the `trace_id` value → jumps directly to the trace in Tempo
5. See the exact red span, exception message, and all span attributes

---

## Telemetry Architecture

```
Your services (order / inventory / payment)
    → OTel SDK pushes spans + metrics + logs via OTLP gRPC :4317
        → OTel Collector receives everything
            ├── traces   → Grafana Tempo  (waterfall view)
            ├── metrics  → Prometheus     (dashboards + alerts)
            ├── logs     → Grafana Loki   (log explorer)
            └── all three → ClickHouse   (data warehouse)

Node Exporter (host metrics)
    → OTel Collector scrapes :9100
        ├── metrics → Prometheus
        └── metrics → ClickHouse
```

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

-- Payment failure rate
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

Every log line automatically contains `trace_id` and `span_id` via
`OTLPLoggingHandler` — this is what enables the Loki → Tempo jump link in Grafana
and ensures logs are correlated with traces in ClickHouse.

---

## Stopping the demo
```bash
docker compose down -v   # -v also removes volumes (wipes stored traces/metrics/logs)
```