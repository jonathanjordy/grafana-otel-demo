# OTel Demo — Distributed Tracing with Grafana Tempo

A portfolio demo of the **three pillars of observability** — metrics, logs, and traces —
using a realistic e-commerce microservices setup.

## Stack

| Layer | Tool |
|---|---|
| Services | Python FastAPI (3 microservices) |
| Instrumentation | OpenTelemetry SDK + auto-instrumentation |
| Trace storage | Grafana Tempo |
| Metrics storage | Prometheus |
| Log storage | Grafana Loki |
| Visualisation | Grafana |
| Databases | PostgreSQL + Redis |

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
In Tempo the `payment-gateway-call` span is red. Click it to see the full
exception message and attributes attached to the failing span.

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
`LoggingInstrumentor` — this is what enables the Loki → Tempo jump link in Grafana.

---

## Stopping the demo
```bash
docker compose down -v   # -v also removes volumes (wipes stored traces/metrics/logs)
```