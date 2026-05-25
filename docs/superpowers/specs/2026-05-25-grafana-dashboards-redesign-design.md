# Grafana Dashboards Redesign — Design Spec

**Date:** 2026-05-25
**Author:** brainstorming session (Claude + Rishad)
**Status:** Draft — pending review

## 1. Problem

The existing single dashboard `grafana/otel-demo-dashboard-template.json` has two classes of problems:

1. **Duplicate legends.** Every Prometheus query omits `sum by (...)` aggregation. Each metric is scraped from two paths (collector's prometheus exporter on `:8889` AND each service's own `/metrics`), and `histogram_quantile` is called without `sum by (le)`. The combined effect is that one logical series (e.g. "orders/min — confirmed", or "p99") shows up many times per panel, one per `(job, instance)` and per label set the panel didn't intend to split on.
2. **Unfocused.** One dashboard tries to be ops health, dev debugging, business KPI, and OTel teaching at once. Different audiences need different signals.

## 2. Goals

- Build dashboards that are **readable at a glance** for their intended audience.
- Fix the duplicate-legend problem at the root by writing aggregation-correct PromQL.
- Surface every signal the *existing* instrumentation supports (no service or collector changes).
- Keep the current dashboard as a referenceable "legacy" version.

## 3. Non-goals

- No changes to service code (`*-service/main.py`), collector config (`otel-collector/config.yaml`), or Tempo / Loki / Prometheus configs.
- No new metrics. If a panel idea requires data we don't already emit, it's noted as a follow-up rather than forced.
- No backend-specific Grafana plugin installs beyond what `docker-compose.yml` already provides.
- Not designing alerting rules — out of scope for this spec.

## 4. Audience and dashboards

Seven dashboards, each focused on one audience. All live in a single Grafana folder `OTel Demo`. The legacy dashboard moves to a subfolder `OTel Demo / Legacy`.

| # | Dashboard | Audience | Primary question |
|---|---|---|---|
| 1 | Home | Anyone landing in Grafana | "What is this and where do I go?" |
| 2 | Ops / SRE Overview | On-call, ops | "Is the system healthy right now?" |
| 3 | Dev — Order Service | Order-service developer | "Why is my service slow / failing?" |
| 4 | Dev — Inventory Service | Inventory-service developer | (same) |
| 5 | Dev — Payment Service | Payment-service developer | (same) |
| 6 | OTel Correlation Demo | Visitors learning OTel | "How do metrics, logs, traces link together?" |
| 7 | Business / Product | PM / business stakeholder | "What's our throughput, conversion, top items?" |

## 5. Shared conventions

These apply uniformly to all 7 dashboards. They are the single source of truth — any per-dashboard section that contradicts them is a bug.

### 5.1 File layout

```
grafana/
  dashboards/
    home.json
    ops-overview.json
    dev-order.json
    dev-inventory.json
    dev-payment.json
    otel-correlation-demo.json
    business-view.json
    legacy/
      otel-demo-legacy.json
  provisioning/
    dashboards/
      dashboards.yaml          # tells Grafana to load grafana/dashboards/**
    datasources/
      datasources.yaml         # unchanged
```

`grafana/otel-demo-dashboard-template.json` is moved to `grafana/dashboards/legacy/otel-demo-legacy.json` and its title is changed to `OTel Demo — Legacy` (no other internal edits). The provisioning yaml lists `grafana/dashboards` recursively so the `legacy/` subfolder appears as a Grafana subfolder.

The compose mount for Grafana already provides `./grafana:/etc/grafana/provisioning` (or similar). The provisioning yaml file path is the only piece that may need a small update; the plan will verify.

### 5.2 PromQL aggregation rules (the duplicate-legend fix)

Every non-Tempo query in every panel MUST follow these patterns. This is what eliminates the duplicate legends.

| Pattern | Template |
|---|---|
| Rate by a label | `sum by (<label>) (rate(<metric>[1m]))` |
| Total rate (no split) | `sum(rate(<metric>[1m]))` |
| Histogram quantile | `histogram_quantile(<q>, sum by (le) (rate(<metric>_bucket[5m])))` |
| Quantile split by label | `histogram_quantile(<q>, sum by (le, <label>) (rate(<metric>_bucket[5m])))` |
| Ratio (percent) | `100 * sum(rate(<num>[5m])) / (sum(rate(<denom_a>[5m])) + sum(rate(<denom_b>[5m])))` — never divide unaggregated metrics |

Critical: never use a raw metric in a panel target. Always wrap in `sum(...)` or `sum by (...)`. This collapses `job`/`instance` (which is what doubles every series today since the same metric arrives via the collector AND via direct scrape).

### 5.3 Visual conventions

- **Service colors** (consistent across all dashboards):
  - `order-service` = purple
  - `inventory-service` = green
  - `payment-service` = red
- **Status colors:**
  - success / healthy = green
  - warn = yellow
  - error / failed = red
  - latency series = blue
- **Legend format:** short label only, no units (units live on the axis). `legendFormat: "{{status}}"` not `"orders/min — {{status}}"`.
- **Tooltip mode:** `multi` on all timeseries.
- **Time defaults:** `now-30m` to `now`, refresh `10s` (Business view overrides to `now-24h`).
- **Variables present on every dashboard:**
  - `$service` — multi-select (single-select on per-service dev dashboards), default `All`. Query: `label_values(up, job)`.
  - `$item_id` — multi-select, default `All`. Query: `label_values(demo_orders_total, item_id)`.

### 5.4 Datasource UIDs

Already provisioned: `prometheus`, `tempo`, `loki`. All targets reference these UIDs explicitly.

### 5.5 Verified metric inventory

The design assumes only these metrics (and nothing else). If a panel idea isn't covered here, it gets cut, not invented.

**Custom business metrics (collector namespace `demo_`):**
- `demo_orders_total{item_id, status="confirmed"}` — only `confirmed` status is recorded; failed orders are in the errors counter
- `demo_order_errors_total{reason}` — reasons: `insufficient_stock`, `inventory_service_error`, `payment_failed`
- `demo_order_duration_seconds_{bucket,sum,count}{item_id, le}`
- `demo_payments_total{status, item_id}` — status: `success` | `failed`
- `demo_payment_failures_total{reason, item_id}` — reasons: `invalid_amount`, `forced_by_demo_flag`, `random_gateway_rejection`
- `demo_payment_duration_seconds_{bucket,sum,count}{status, le}`
- `demo_payment_amount_dollars_{bucket,sum,count}{item_id, le}`
- `demo_inventory_cache_hits_total{item_id}`
- `demo_inventory_cache_misses_total{item_id}`
- `demo_inventory_lookup_duration_seconds_{bucket,sum,count}{item_id, cache_hit, le}`

**HTTP server metrics (FastAPIInstrumentor 0.45b0, OTLP → collector → `demo_` prefix):**
- `demo_http_server_duration_milliseconds_{bucket,sum,count}{http_method, http_route, http_status_code, le, ...}`
- `demo_http_server_active_requests`
- `demo_http_server_request_size_bytes`, `demo_http_server_response_size_bytes`

**HTTP client metrics (HTTPXClientInstrumentor 0.45b0):**
- `demo_http_client_duration_milliseconds_{bucket,sum,count}{http_method, http_status_code, net_peer_name, le, ...}`

**Tempo span metrics (`metrics_generator` enabled, remote-write to Prometheus, no namespace prefix):**
- `traces_spanmetrics_calls_total{service, span_name, span_kind, status_code}`
- `traces_spanmetrics_latency_{bucket,sum,count}{service, span_name, le}`
- `traces_service_graph_request_total{client, server, connection_type}`
- `traces_service_graph_request_failed_total{client, server}`
- `traces_service_graph_request_server_seconds_bucket{client, server, le}`

**Process / Python (each service's own `/metrics`, no namespace):**
- `process_start_time_seconds{job}`
- `process_cpu_seconds_total{job}`
- `process_resident_memory_bytes{job}`
- `python_gc_collections_total{job, generation}`

**Node exporter:**
- All standard `node_*` metrics

### 5.6 Logs

Loki labels available: `job`, `exporter`. The log JSON body contains `severity`, `otelTraceID`, `otelSpanID`, `otelServiceName`, `body`. Filtering by severity uses LogQL JSON parsing: `{exporter="OTLP"} | json | severity="ERROR"`. The `derivedFields` regex on `"traceid":"(\w+)"` in datasources.yaml already produces clickable trace_id → Tempo links.

Filtering by service uses the parsed field too: `{exporter="OTLP"} | json | otelServiceName="order-service"`.

### 5.7 Navigation

A separate provisioning step sets the Home dashboard as the default. Either:
- `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/etc/grafana/provisioning/dashboards/home.json` env var in docker-compose, OR
- `grafana.ini` override mounted into the container.

Plan will pick whichever has fewer moving parts.

---

## 6. Per-dashboard sections

Each section: purpose, layout summary, panels with their queries (or query template), notes. Coordinates are 24-col Grafana grid; `w=` width, `h=` height. Rows are spacers (`type: row`).

### 6.1 Home

**Purpose:** Landing page. Navigates to the other 6 dashboards, with a live status teaser per tile.

**Layout:**
```
+----------------------------------------------------------------+
| Title text panel: "OTel Demo — Order System"  (h=4)            |
+----------------------------------------------------------------+
| Ops Overview  | Dev Order  | Dev Inventory | Dev Payment       |  (h=6)
+----------------------------------------------------------------+
| Correlation Demo  |  Business View  |  Legacy (subfolder link) |  (h=6)
+----------------------------------------------------------------+
```

**Panels:**

| Panel | Type | Live query | Link target |
|---|---|---|---|
| Title | text (markdown) | n/a | n/a |
| Ops Overview tile | stat | `100 * sum(rate(demo_order_errors_total[5m])) / (sum(rate(demo_orders_total[5m])) + sum(rate(demo_order_errors_total[5m])))` — "Error % now" | `ops-overview` dashboard |
| Dev Order tile | stat | `histogram_quantile(0.95, sum by(le)(rate(demo_order_duration_seconds_bucket{}[5m])))` — "p95 latency" | `dev-order` |
| Dev Inventory tile | stat | `100 * sum(rate(demo_inventory_cache_hits_total[5m])) / sum(rate(demo_inventory_cache_hits_total[5m]) + rate(demo_inventory_cache_misses_total[5m]))` — "Cache hit %" | `dev-inventory` |
| Dev Payment tile | stat | `100 * sum(rate(demo_payment_failures_total[5m])) / (sum(rate(demo_payments_total[5m])) + sum(rate(demo_payment_failures_total[5m])))` — "Failure %" | `dev-payment` |
| Correlation Demo tile | stat | `sum(rate(traces_spanmetrics_calls_total[5m])) * 60` — "spans/min" | `otel-correlation-demo` |
| Business tile | stat | `sum(rate(demo_orders_total[1m])) * 60` — "orders/min" | `business-view` |
| Legacy tile | text (markdown) | n/a — static link | `legacy/otel-demo-legacy` |

Panel links use Grafana's `links` array on each panel, set to dashboard UID. Tile stat panels use `colorMode: background` with thresholds matching the destination dashboard's conventions (red>5% on the ops tile, green>80% on the cache tile, etc.).

### 6.2 Ops / SRE Overview

**Purpose:** Glanceable health. Designed so on-call can answer "is something broken?" in <5 seconds.

**Variables:** `$service` (multi, default All), `$item_id` (multi, default All).

**Layout summary:** 6 rows, ~12 panels total.

**Row 1 — Health strip (h=4):** 6 stat tiles spanning full width

| Tile | Query | Unit | Thresholds (green / yellow / red) |
|---|---|---|---|
| Order error % | `100 * sum(rate(demo_order_errors_total[5m])) / (sum(rate(demo_orders_total[5m])) + sum(rate(demo_order_errors_total[5m])))` | percent | <1 / 1–5 / >5 |
| Payment fail % | `100 * sum(rate(demo_payment_failures_total[5m])) / (sum(rate(demo_payments_total[5m])) + sum(rate(demo_payment_failures_total[5m])))` | percent | <5 / 5–15 / >15 |
| p95 order dur | `histogram_quantile(0.95, sum by(le)(rate(demo_order_duration_seconds_bucket[5m])))` | s | <0.5 / 0.5–2 / >2 |
| p95 inventory dur | `histogram_quantile(0.95, sum by(le)(rate(demo_inventory_lookup_duration_seconds_bucket[5m])))` | s | <0.2 / 0.2–1 / >1 |
| Cache hit % | `100 * sum(rate(demo_inventory_cache_hits_total[5m])) / sum(rate(demo_inventory_cache_hits_total[5m]) + rate(demo_inventory_cache_misses_total[5m]))` | percent | reversed: >80 / 50–80 / <50 |
| Orders/min now | `sum(rate(demo_orders_total[1m])) * 60` | reqpm | neutral (no thresholds) |

Note on payment fail threshold: the service has a built-in 10% random failure rate (`payment-service/main.py:188`), so 5–15% is "normal", >15% means something extra is wrong. This is intentional and documented in CLAUDE.md as "do not fix".

**Row 2 — Rate (h=8):** 3 timeseries

| Panel | Query | Legend |
|---|---|---|
| Orders/min by status | `sum by (status) (rate(demo_orders_total[1m])) * 60` | `{{status}}` |
| Order errors/min by reason | `sum by (reason) (rate(demo_order_errors_total[1m])) * 60` | `{{reason}}` |
| Payment failures/min by reason | `sum by (reason) (rate(demo_payment_failures_total[1m])) * 60` | `{{reason}}` |

**Row 3 — Latency (h=8):** 3 timeseries, one per service, each with p50/p95/p99

Per-service template (3 targets per panel):
```promql
histogram_quantile(0.50, sum by (le) (rate(<metric>_bucket[5m])))    # legend: p50
histogram_quantile(0.95, sum by (le) (rate(<metric>_bucket[5m])))    # legend: p95
histogram_quantile(0.99, sum by (le) (rate(<metric>_bucket[5m])))    # legend: p99
```
With `<metric>` = `demo_order_duration_seconds`, `demo_inventory_lookup_duration_seconds`, `demo_payment_duration_seconds`.

**Row 4 — Host saturation (h=6):** 2 timeseries (node-exporter)

| Panel | Query |
|---|---|
| CPU % busy | `100 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100` |
| Memory used % | `100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)` |

**Row 5 — Service map (h=10):** Tempo nodeGraph, queryType `serviceMap`. Same as the existing dashboard, but full-width.

**Row 6 — Errors (h=10):** side-by-side

| Panel | Datasource | Query |
|---|---|---|
| Error log rate by service | Prometheus + Loki via `sum by (otelServiceName) (count_over_time({exporter="OTLP"} \| json \| severity="ERROR" [1m]))` — single timeseries | Loki |
| Recent error logs | logs | `{exporter="OTLP"} \| json \| severity="ERROR"` sorted desc, derivedFields trace_id link active | Loki |

Note: Loki's `count_over_time` returns per-instance counts; the `sum by (otelServiceName)` collapses them.

### 6.3 Dev — Order Service

**Purpose:** Debug one service. Covers RED, endpoint breakdown, business signals specific to order-service, dependency latencies (using span metrics), logs, and traces.

**Variables:** `$item_id` (multi, default All). `$service` is fixed to `order-service` (no variable needed — it's a per-service dashboard).

**Row 1 — Identity strip (h=4):** 6 stat tiles

| Tile | Query | Unit |
|---|---|---|
| RPS | `sum(rate(demo_http_server_duration_milliseconds_count{service_name="order-service"}[1m]))` | reqps |
| Error % | `100 * sum(rate(demo_order_errors_total[5m])) / (sum(rate(demo_orders_total[5m])) + sum(rate(demo_order_errors_total[5m])))` | percent |
| p50 latency | `histogram_quantile(0.50, sum by(le)(rate(demo_order_duration_seconds_bucket[5m])))` | s |
| p95 latency | `histogram_quantile(0.95, sum by(le)(rate(demo_order_duration_seconds_bucket[5m])))` | s |
| p99 latency | `histogram_quantile(0.99, sum by(le)(rate(demo_order_duration_seconds_bucket[5m])))` | s |
| Uptime | `time() - max(process_start_time_seconds{job="order-service"})` | s |

**Row 2 — Endpoint breakdown (h=8):** 4 panels (from FastAPI HTTP metrics)

| Panel | Type | Query |
|---|---|---|
| RPS by route | timeseries | `sum by (http_route) (rate(demo_http_server_duration_milliseconds_count{service_name="order-service"}[1m]))` |
| p95 by route | timeseries | `histogram_quantile(0.95, sum by (http_route, le) (rate(demo_http_server_duration_milliseconds_bucket{service_name="order-service"}[5m])))` |
| Status code mix | timeseries (stacked) | `sum by (http_status_code) (rate(demo_http_server_duration_milliseconds_count{service_name="order-service"}[1m]))` |
| Latency heatmap | heatmap | `sum by (le) (rate(demo_http_server_duration_milliseconds_bucket{service_name="order-service"}[2m]))` |

**Row 3 — Business panels (h=8):** 4 panels

| Panel | Type | Query |
|---|---|---|
| Orders/min by status | timeseries | `sum by (status) (rate(demo_orders_total[1m])) * 60` |
| Errors/min by reason | timeseries | `sum by (reason) (rate(demo_order_errors_total[1m])) * 60` |
| Error reason mix | barchart | `sum by (reason) (increase(demo_order_errors_total[$__range]))` |
| Top items by orders | table | `topk(10, sum by (item_id) (increase(demo_orders_total[$__range])))` |

**Row 4 — Dependencies via span metrics (h=8):** 2 panels

| Panel | Type | Query |
|---|---|---|
| Child span RPS | timeseries | `sum by (span_name) (rate(traces_spanmetrics_calls_total{service="order-service", span_name!="POST /orders"}[1m]))` — covers `check-inventory`, `payment-gateway-call`, `save-order-db`, `record-transaction` |
| Child span p95 | timeseries | `histogram_quantile(0.95, sum by (span_name, le) (rate(traces_spanmetrics_latency_bucket{service="order-service", span_name!="POST /orders"}[5m])))` |

This row is the "where is my latency going?" view. It uses Tempo's span-metrics generator to give the equivalent of DB / HTTP-client RED without needing SQLAlchemy/HTTPX metrics directly.

**Row 5 — Logs (h=8):** 1 wide panel

| Panel | Datasource | Query |
|---|---|---|
| Order-service logs | Loki (logs) | `{exporter="OTLP"} \| json \| otelServiceName="order-service"`, sorted desc, derivedFields active |

**Row 6 — Traces (h=8):** 1 wide panel

| Panel | Datasource | Query |
|---|---|---|
| Slowest recent traces | Tempo (table) | TraceQL: `{ .service.name = "order-service" }`, limit 20, sorted by `traceDuration` desc |

### 6.4 Dev — Inventory Service

Identical skeleton to Dev — Order Service, with business-panel substitutions:

**Row 1 identity strip:** RPS, p50/p95/p99 of `demo_inventory_lookup_duration_seconds`, cache hit %, uptime.

**Row 2 endpoint breakdown:** same template, `service_name="inventory-service"`.

**Row 3 business panels:**
| Panel | Query |
|---|---|
| Cache hits vs misses/min | `sum(rate(demo_inventory_cache_hits_total[1m])) * 60` (legend `hits`), `sum(rate(demo_inventory_cache_misses_total[1m])) * 60` (legend `misses`) |
| Cache hit % over time | `100 * sum(rate(demo_inventory_cache_hits_total[1m])) / sum(rate(demo_inventory_cache_hits_total[1m]) + rate(demo_inventory_cache_misses_total[1m]))` |
| Lookup p95 by cache_hit | `histogram_quantile(0.95, sum by (cache_hit, le) (rate(demo_inventory_lookup_duration_seconds_bucket[5m])))` — legend `cache_hit={{cache_hit}}` |
| Top items by miss rate | `topk(10, sum by (item_id) (rate(demo_inventory_cache_misses_total[$__range])))` |

The "Lookup p95 by cache_hit" panel is the headline insight: cache=true is fast, cache=false slow — and slow_query=true requests sit at ~2s.

**Row 4 dependencies via span metrics:**
| Panel | Query |
|---|---|
| Redis lookup p95 | `histogram_quantile(0.95, sum by (le) (rate(traces_spanmetrics_latency_bucket{service="inventory-service", span_name="redis-cache-lookup"}[5m])))` |
| DB fallback p95 | `histogram_quantile(0.95, sum by (le) (rate(traces_spanmetrics_latency_bucket{service="inventory-service", span_name="db-stock-lookup"}[5m])))` |
| Redis vs DB call rate | `sum by (span_name) (rate(traces_spanmetrics_calls_total{service="inventory-service", span_name=~"redis-cache-lookup|db-stock-lookup"}[1m]))` |

**Rows 5 & 6:** logs and traces filtered to `inventory-service`.

### 6.5 Dev — Payment Service

Same skeleton, payment-specific substitutions:

**Row 1 identity strip:** RPS, p50/p95/p99 of `demo_payment_duration_seconds`, failure %, uptime.

**Row 3 business panels:**
| Panel | Query |
|---|---|
| Payments/min by status | `sum by (status) (rate(demo_payments_total[1m])) * 60` |
| Failures/min by reason | `sum by (reason) (rate(demo_payment_failures_total[1m])) * 60` |
| Latency split by status | `histogram_quantile(0.95, sum by (status, le) (rate(demo_payment_duration_seconds_bucket[5m])))` — shows whether failed paths are faster/slower |
| Payment amount histogram | histogram panel: `sum by (le) (rate(demo_payment_amount_dollars_bucket[5m]))` |

**Row 4 dependencies via span metrics:**
| Panel | Query |
|---|---|
| `payment-gateway-call` p95 | `histogram_quantile(0.95, sum by (le) (rate(traces_spanmetrics_latency_bucket{service="payment-service", span_name="payment-gateway-call"}[5m])))` |
| Gateway call rate | `sum(rate(traces_spanmetrics_calls_total{service="payment-service", span_name="payment-gateway-call"}[1m])) * 60` |

**Rows 5 & 6:** logs and traces filtered to `payment-service`.

### 6.6 OTel Correlation Demo

**Purpose:** Show how a single request produces a metric, a log, and a trace, and how Grafana lets you jump between them.

**Variables:** none (kept simple for visitors).

**Row 1 — Intro (h=4):** text/markdown panel
> "This dashboard shows how OpenTelemetry connects metrics, logs, and traces. Each panel below is a step in the story. Use the load-generator's traffic to see live data, or trigger a failure with: `curl -X POST localhost:8000/orders -H 'Content-Type: application/json' -d '{"item_id":"sku-1","quantity":1,"fail_payment":true}'`."

**Row 2 — The metric (h=8):** 1 timeseries
- Query: `sum(rate(demo_orders_total[1m])) * 60`
- Critical config: `exemplars: true` — the timeseries shows trace_ids as exemplar dots. Datasource already has `exemplarTraceIdDestinations` pointing at Tempo (`datasources.yaml`).

**Row 3 — The log (h=8):** 1 logs panel
- Loki query: `{exporter="OTLP"} | json` with `otelTraceID` field visible. Derived fields turn trace_ids into Tempo links.

**Row 4 — The trace (h=10):** Tempo TraceQL table
- Query: `{ .service.name =~ "order-service|inventory-service|payment-service" }`, sorted by `startTime` desc, limit 20.

**Row 5 — The service map (h=10):** Tempo nodeGraph, `queryType: serviceMap`. Built from `traces_service_graph_*` metrics.

**Row 6 — Try this (h=4):** text/markdown
> "Want to see something break? Set `fail_payment=true` for guaranteed payment errors, or `slow_query=true` for a 2s inventory delay. Watch the metric exemplars appear, click one to see the full trace, scroll to its logs."

### 6.7 Business / Product View

**Purpose:** Outcomes, not infra. PM-friendly. Default time range `now-24h`.

**Variables:** `$item_id` (multi, default All).

**Row 1 — Headline stats (h=4):** 4 stat tiles

| Tile | Query | Unit |
|---|---|---|
| Total orders (range) | `sum(increase(demo_orders_total[$__range]))` | short |
| Total revenue (range) | `sum(increase(demo_payment_amount_dollars_sum[$__range]))` | currencyUSD |
| Average order value | `sum(increase(demo_payment_amount_dollars_sum[$__range])) / sum(increase(demo_payments_total{status="success"}[$__range]))` | currencyUSD |
| Conversion % | `100 * sum(rate(demo_orders_total[$__range])) / (sum(rate(demo_orders_total[$__range])) + sum(rate(demo_order_errors_total[$__range])))` | percent |

**Row 2 — Trends (h=8):** 3 timeseries

| Panel | Query |
|---|---|
| Orders/hr | `sum(rate(demo_orders_total[1h])) * 3600` |
| Revenue/hr | `sum(rate(demo_payment_amount_dollars_sum[1h])) * 3600` |
| Failure reason mix (stacked) | `sum by (reason) (rate(demo_payment_failures_total[5m])) * 60` |

**Row 3 — Per-item breakdown (h=10):** 3 tables

| Panel | Query |
|---|---|
| Top items by orders | `topk(10, sum by (item_id) (increase(demo_orders_total[$__range])))` |
| Top items by revenue | `topk(10, sum by (item_id) (increase(demo_payment_amount_dollars_sum[$__range])))` |
| Top items by payment failure | `topk(10, sum by (item_id) (increase(demo_payment_failures_total[$__range])))` |

**Row 4 — Distribution (h=8):** 2 panels

| Panel | Query |
|---|---|
| Payment amount histogram | histogram: `sum by (le) (rate(demo_payment_amount_dollars_bucket[5m]))` |
| Payment amount heatmap (over time) | heatmap: `sum by (le) (rate(demo_payment_amount_dollars_bucket[2m]))` |

## 7. Provisioning changes

1. Move `grafana/otel-demo-dashboard-template.json` → `grafana/dashboards/legacy/otel-demo-legacy.json`, update its title to `OTel Demo — Legacy`.
2. Create `grafana/dashboards/` folder with the 7 new JSON files.
3. Update `grafana/provisioning/dashboards/*.yaml` (whichever file controls dashboard provisioning) to point at `grafana/dashboards` with `foldersFromFilesStructure: true` so the `legacy/` subfolder is honored.
4. Set Home as default landing page via `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH` in `docker-compose.yml` for the grafana service (env var is simpler than mounting a custom `grafana.ini`).

## 8. Testing approach

There's no test suite for dashboards. Validation is manual but well-defined:

1. **Local stack up:** `docker compose up --build`. Wait ~30s for load-generator to produce traffic.
2. **Each dashboard:** open in Grafana, confirm:
   - No panel shows duplicate legend entries.
   - No panel shows "No data" if the corresponding metric is being emitted (use `curl localhost:9090/api/v1/label/__name__/values` to confirm metric existence if a panel is blank).
   - Thresholds color correctly under both normal and failure-injection load (e.g. `curl -X POST localhost:8000/orders -d '{"item_id":"sku-1","quantity":1,"fail_payment":true}'`).
3. **Cross-signal navigation:**
   - From an exemplar dot on the correlation demo metric panel → Tempo trace opens.
   - From a log line's trace_id → Tempo trace opens.
   - From Tempo trace span → Loki logs for that span open via the `tracesToLogsV2` datasource link.
4. **Provisioning:** `docker compose down -v && docker compose up` and confirm Grafana boots with Home as the landing page and all 7 dashboards visible in the `OTel Demo` folder.

## 9. Risks and open questions

- **`service_name` label.** OTel SDKs emit `service.name` as a resource attribute. The collector's prometheus exporter converts dots → underscores, so it becomes `service_name` on metrics. Dev dashboards rely on `service_name="order-service"` filters. If the exporter is configured to drop resource attributes, those filters break. Mitigation: the plan's first task is to spin up the stack and curl `otel-collector:8889/metrics` to verify the label is present; if not, fall back to `job=~"order-service.*"` (Prometheus job label).
- **Span metric label name.** Tempo's metrics_generator labels traces with `service` (not `service_name`). Confirmed by Tempo docs but verify in the same first task above.
- **HTTP server metric exact name.** Could be `http_server_duration_milliseconds` OR `http_server_request_duration_seconds` depending on semconv stabilization. Listed version (0.45b0) emits the former. The plan's verification step adjusts if reality differs.
- **`$__range` in stat queries** behaves as the panel's selected time range. Confirmed Grafana 10+ supports it on Prometheus targets.
- **Legacy dashboard provisioning.** Need to verify the existing provisioning yaml supports `foldersFromFilesStructure`; older provisioning configs require explicit `folder:` per file.
- **Prometheus exemplar storage is OFF.** `docker-compose.yml` runs Prometheus without `--enable-feature=exemplar-storage`. Without it, exemplars are dropped on ingest, so the OTel Correlation Demo's "click an exemplar dot to jump to Tempo" feature is dead. Mitigation options for the plan to choose between:
  1. **Add the flag** to the prometheus service's `command:` list. This is a one-line change to `docker-compose.yml` — technically outside "grafana/-only" scope, but trivial and non-disruptive. Recommended.
  2. **Drop the exemplar story from the correlation demo** and rely solely on the log-trace-id → Tempo link via `derivedFields`, plus the trace-search panel. The narrative still holds.
  
  If option 1 is rejected during plan execution, the metric panel in §6.6 becomes a plain timeseries (no exemplars) and the markdown intro is reworded.
