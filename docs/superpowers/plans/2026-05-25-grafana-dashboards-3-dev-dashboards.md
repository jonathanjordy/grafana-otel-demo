# Dev Dashboards Implementation Plan (order / inventory / payment)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three per-service developer deep-dive dashboards. Each follows the same six-row skeleton: identity strip, endpoint breakdown, business panels, span-metric dependencies, logs, traces.

**Architecture:** Build `dev-order.json` first as the reference. Then derive `dev-inventory.json` and `dev-payment.json` by copying and substituting the business-panel and dependency rows. All three share UID prefix `otel-demo-dev-*` to match the Home dashboard's links.

**Tech Stack:** Grafana 10.3.0, Prometheus, Tempo (span metrics + traces), Loki.

**Spec:** [`../specs/2026-05-25-grafana-dashboards-redesign-design.md`](../specs/2026-05-25-grafana-dashboards-redesign-design.md) §6.3, §6.4, §6.5

**Prerequisites:**
- Plans 1 and 2 complete.
- `verification-notes.md` confirms `service_name` label exists. If verification said use `job=~"<svc>.*"` instead, substitute in every panel query.
- `verification-notes.md` confirms Tempo span metrics use the `service` label (not `service_name`). If it's different, substitute in span-metric panels.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `grafana/provisioning/dashboards/dev-order.json` | create | Order-service deep-dive |
| `grafana/provisioning/dashboards/dev-inventory.json` | create | Inventory-service deep-dive |
| `grafana/provisioning/dashboards/dev-payment.json` | create | Payment-service deep-dive |

---

## Task 1: Build `dev-order.json` — skeleton + Row 1 (identity strip)

**Files:**
- Create: `grafana/provisioning/dashboards/dev-order.json`

- [ ] **Step 1: Create the file with skeleton + Row 1**

```json
{
  "uid": "otel-demo-dev-order",
  "title": "Dev — Order Service",
  "tags": ["otel", "demo", "dev", "order-service"],
  "timezone": "browser",
  "schemaVersion": 38,
  "refresh": "10s",
  "time": { "from": "now-30m", "to": "now" },
  "templating": {
    "list": [
      {
        "name": "item_id",
        "type": "query",
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "query": "label_values(demo_orders_total, item_id)",
        "label": "Item",
        "current": { "text": "All", "value": "$__all" },
        "includeAll": true,
        "multi": true,
        "refresh": 2
      }
    ]
  },
  "panels": [
    {
      "id": 100, "type": "row", "title": "Identity",
      "gridPos": { "x": 0, "y": 0, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 101, "type": "stat", "title": "RPS",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": { "defaults": { "unit": "reqps", "decimals": 2, "color": { "mode": "fixed", "fixedColor": "purple" } } },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "area" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum(rate(demo_http_server_duration_milliseconds_count{service_name=\"order-service\"}[1m]))",
        "legendFormat": "rps", "refId": "A"
      }]
    },
    {
      "id": 102, "type": "stat", "title": "Error %",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 4, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": {
        "defaults": {
          "unit": "percent", "decimals": 2,
          "thresholds": { "mode": "absolute", "steps": [
            { "color": "green", "value": null },
            { "color": "yellow", "value": 1 },
            { "color": "red", "value": 5 }
          ] }
        }
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "100 * sum(rate(demo_order_errors_total[5m])) / (sum(rate(demo_orders_total[5m])) + sum(rate(demo_order_errors_total[5m])))",
        "legendFormat": "err %", "refId": "A"
      }]
    },
    {
      "id": 103, "type": "stat", "title": "p50 latency",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 8, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": { "defaults": { "unit": "s", "decimals": 3, "color": { "mode": "fixed", "fixedColor": "green" } } },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.50, sum by(le) (rate(demo_order_duration_seconds_bucket[5m])))",
        "legendFormat": "p50", "refId": "A"
      }]
    },
    {
      "id": 104, "type": "stat", "title": "p95 latency",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": {
        "defaults": {
          "unit": "s", "decimals": 3,
          "thresholds": { "mode": "absolute", "steps": [
            { "color": "green", "value": null },
            { "color": "yellow", "value": 0.5 },
            { "color": "red", "value": 2 }
          ] }
        }
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.95, sum by(le) (rate(demo_order_duration_seconds_bucket[5m])))",
        "legendFormat": "p95", "refId": "A"
      }]
    },
    {
      "id": 105, "type": "stat", "title": "p99 latency",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 16, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": { "defaults": { "unit": "s", "decimals": 3, "color": { "mode": "fixed", "fixedColor": "red" } } },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.99, sum by(le) (rate(demo_order_duration_seconds_bucket[5m])))",
        "legendFormat": "p99", "refId": "A"
      }]
    },
    {
      "id": 106, "type": "stat", "title": "Uptime",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 20, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": { "defaults": { "unit": "s", "color": { "mode": "fixed", "fixedColor": "blue" } } },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "time() - max(process_start_time_seconds{job=\"order-service\"})",
        "legendFormat": "uptime", "refId": "A"
      }]
    }
  ]
}
```

- [ ] **Step 2: Reload Grafana and verify**

```bash
docker compose restart grafana
sleep 10
```

Expected: dashboard appears at `Dev — Order Service`. Six identity tiles render with live numbers. Home page's "Dev — Order" tile link now resolves.

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/dev-order.json
git commit -m "feat(grafana): dev-order skeleton + identity strip"
```

---

## Task 2: `dev-order.json` Row 2 — Endpoint breakdown

**Files:**
- Modify: `grafana/provisioning/dashboards/dev-order.json` — append to `panels` array

- [ ] **Step 1: Append Row 2**

Inside the `panels` array (before the closing `]`), append:

```json
,
    {
      "id": 200, "type": "row", "title": "Endpoint breakdown (HTTP)",
      "gridPos": { "x": 0, "y": 5, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 201, "type": "timeseries", "title": "RPS by route",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 6, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 10 }, "unit": "reqps", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (http_route) (rate(demo_http_server_duration_milliseconds_count{service_name=\"order-service\"}[1m]))",
        "legendFormat": "{{http_route}}", "refId": "A"
      }]
    },
    {
      "id": 202, "type": "timeseries", "title": "p95 latency by route",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 6, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 5 }, "unit": "ms", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.95, sum by (http_route, le) (rate(demo_http_server_duration_milliseconds_bucket{service_name=\"order-service\"}[5m])))",
        "legendFormat": "{{http_route}}", "refId": "A"
      }],
      "description": "Note: unit is milliseconds because the auto-instrumentation histogram is named *_milliseconds_bucket."
    },
    {
      "id": 203, "type": "timeseries", "title": "Status code mix",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 14, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 1, "fillOpacity": 70, "stacking": { "mode": "normal" } }, "unit": "reqps", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (http_status_code) (rate(demo_http_server_duration_milliseconds_count{service_name=\"order-service\"}[1m]))",
        "legendFormat": "{{http_status_code}}", "refId": "A"
      }]
    },
    {
      "id": 204, "type": "heatmap", "title": "Latency heatmap",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 14, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "scaleDistribution": { "type": "linear" } } } },
      "options": { "calculate": false, "cellGap": 1, "yAxis": { "axisLabel": "ms" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (le) (rate(demo_http_server_duration_milliseconds_bucket{service_name=\"order-service\"}[2m]))",
        "legendFormat": "{{le}}", "refId": "A", "format": "heatmap"
      }]
    }
```

- [ ] **Step 2: Verify**

Wait 30s for provisioner pickup, refresh. Expected:
- RPS by route shows at least one series per FastAPI route, e.g. `POST /orders`, `GET /metrics`
- p95 by route — similar
- Status code mix dominated by `200`s, with occasional non-2xx if any errors
- Heatmap shows latency distribution as colored cells; brighter cells = more requests in that latency bucket

If RPS panel is empty: HTTP server metrics may have a different name in your version. Run `curl 'http://localhost:9090/api/v1/label/__name__/values' | grep http_server` and substitute. Note in `verification-notes.md`.

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/dev-order.json
git commit -m "feat(grafana): dev-order row 2 — endpoint breakdown"
```

---

## Task 3: `dev-order.json` Row 3 — Business panels (order-specific)

**Files:**
- Modify: `grafana/provisioning/dashboards/dev-order.json`

- [ ] **Step 1: Append Row 3**

```json
,
    {
      "id": 300, "type": "row", "title": "Business — orders",
      "gridPos": { "x": 0, "y": 22, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 301, "type": "timeseries", "title": "Orders/min by status",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 23, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 10 }, "unit": "reqpm", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (status) (rate(demo_orders_total[1m])) * 60",
        "legendFormat": "{{status}}", "refId": "A"
      }]
    },
    {
      "id": 302, "type": "timeseries", "title": "Errors/min by reason",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 23, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 15, "stacking": { "mode": "normal" } }, "unit": "reqpm", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (reason) (rate(demo_order_errors_total[1m])) * 60",
        "legendFormat": "{{reason}}", "refId": "A"
      }]
    },
    {
      "id": 303, "type": "barchart", "title": "Error reason mix (range total)",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 31, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "short", "color": { "mode": "palette-classic" } } },
      "options": { "orientation": "horizontal", "showValue": "always", "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (reason) (increase(demo_order_errors_total[$__range]))",
        "legendFormat": "{{reason}}", "refId": "A", "format": "table", "instant": true
      }]
    },
    {
      "id": 304, "type": "table", "title": "Top items by orders (range)",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 31, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "align": "right" } } },
      "options": { "showHeader": true, "sortBy": [{ "displayName": "Value", "desc": true }] },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "topk(10, sum by (item_id) (increase(demo_orders_total[$__range])))",
        "legendFormat": "{{item_id}}", "refId": "A", "format": "table", "instant": true
      }],
      "transformations": [{ "id": "organize", "options": { "excludeByName": { "Time": true }, "indexByName": {}, "renameByName": {} } }]
    }
```

- [ ] **Step 2: Verify**

Refresh. Expected:
- `Orders/min by status` shows the `confirmed` series (only status emitted by the code; spec §5.5)
- `Errors/min by reason` shows up to 3 series matching `payment-service/main.py` and `order-service/main.py` failure reasons
- `Error reason mix` bar chart shows horizontal bars per reason
- `Top items by orders` table shows item IDs and order counts, sorted descending

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/dev-order.json
git commit -m "feat(grafana): dev-order row 3 — business panels"
```

---

## Task 4: `dev-order.json` Row 4 — Span-metric dependencies

This row is the "where is my latency going?" view. It uses Tempo's auto-generated span metrics to show child-span RED metrics (the order service's calls to inventory, payment, DB, etc.) without needing direct DB/HTTP-client metrics.

**Files:**
- Modify: `grafana/provisioning/dashboards/dev-order.json`

- [ ] **Step 1: Append Row 4**

```json
,
    {
      "id": 400, "type": "row", "title": "Dependencies (via span metrics)",
      "gridPos": { "x": 0, "y": 39, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 401, "type": "timeseries", "title": "Child span call rate (per span_name)",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 40, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 10 }, "unit": "reqps", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (span_name) (rate(traces_spanmetrics_calls_total{service=\"order-service\", span_name!~\"POST /orders|GET /metrics|GET /\"}[1m]))",
        "legendFormat": "{{span_name}}", "refId": "A"
      }],
      "description": "Manual child spans only (check-inventory, payment-gateway-call, save-order-db, record-transaction). Server-entry spans excluded via regex."
    },
    {
      "id": 402, "type": "timeseries", "title": "Child span p95 latency",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 40, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 5 }, "unit": "ms", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.95, sum by (span_name, le) (rate(traces_spanmetrics_latency_bucket{service=\"order-service\", span_name!~\"POST /orders|GET /metrics|GET /\"}[5m])))",
        "legendFormat": "{{span_name}}", "refId": "A"
      }],
      "description": "Tempo's spanmetrics histogram is in milliseconds by default."
    }
```

- [ ] **Step 2: Verify**

Refresh. Expected:
- Call rate panel shows series for `check-inventory`, `payment-gateway-call`, `save-order-db`, `record-transaction` (per CLAUDE.md's "Span hierarchy convention")
- p95 panel shows latencies for the same spans
- The slowest span is typically `payment-gateway-call` (~100ms) or `save-order-db`

If panels are empty: confirm `service` is the correct label name (vs `service_name`). Substitute per `verification-notes.md` if needed. If span names are different (e.g. `db-stock-lookup` vs `db_stock_lookup`), the regex filter still works since it's a negated match.

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/dev-order.json
git commit -m "feat(grafana): dev-order row 4 — span-metric dependencies"
```

---

## Task 5: `dev-order.json` Rows 5 & 6 — Logs + Traces

**Files:**
- Modify: `grafana/provisioning/dashboards/dev-order.json`

- [ ] **Step 1: Append Rows 5 + 6**

```json
,
    {
      "id": 500, "type": "row", "title": "Logs (this service)",
      "gridPos": { "x": 0, "y": 48, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 501, "type": "logs", "title": "Order-service logs (click trace_id → Tempo)",
      "datasource": { "type": "loki", "uid": "loki" },
      "gridPos": { "x": 0, "y": 49, "w": 24, "h": 10 },
      "options": {
        "dedupStrategy": "none", "enableLogDetails": true, "prettifyLogMessage": true,
        "showLabels": false, "showTime": true, "sortOrder": "Descending", "wrapLogMessage": true
      },
      "targets": [{
        "datasource": { "type": "loki", "uid": "loki" },
        "expr": "{exporter=\"OTLP\"} | json | otelServiceName=\"order-service\"",
        "refId": "A", "editorMode": "code", "queryType": "range", "maxLines": 200
      }]
    },
    {
      "id": 600, "type": "row", "title": "Traces (slowest recent)",
      "gridPos": { "x": 0, "y": 59, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 601, "type": "table", "title": "Recent traces sorted by duration",
      "datasource": { "type": "tempo", "uid": "tempo" },
      "gridPos": { "x": 0, "y": 60, "w": 24, "h": 10 },
      "fieldConfig": { "defaults": { "custom": { "filterable": true } } },
      "options": { "footer": { "enablePagination": true } },
      "targets": [{
        "datasource": { "type": "tempo", "uid": "tempo" },
        "queryType": "traceql",
        "query": "{ .service.name = \"order-service\" } | select(traceDuration)",
        "limit": 20, "refId": "A"
      }]
    }
  ]
}
```

The closing `]` and `}` are the panel-array and root close — this is the LAST task that appends panels to dev-order.

- [ ] **Step 2: Verify**

Refresh. Expected:
- Logs panel shows order-service log lines, JSON-formatted, sorted desc
- Each line is expandable; expand reveals `traceid` as a clickable derived field → Tempo opens
- Traces table shows recent traces, sortable by duration

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/dev-order.json
git commit -m "feat(grafana): dev-order rows 5 + 6 — logs and traces"
```

---

## Task 6: Build `dev-inventory.json` by copying dev-order and substituting

**Files:**
- Create: `grafana/provisioning/dashboards/dev-inventory.json`

- [ ] **Step 1: Copy dev-order.json**

```bash
cp grafana/provisioning/dashboards/dev-order.json grafana/provisioning/dashboards/dev-inventory.json
```

- [ ] **Step 2: Update dashboard metadata**

Edit `grafana/provisioning/dashboards/dev-inventory.json`:
- Change `"uid": "otel-demo-dev-order"` → `"uid": "otel-demo-dev-inventory"`
- Change `"title": "Dev — Order Service"` → `"title": "Dev — Inventory Service"`
- Change tag `"order-service"` → `"inventory-service"`

- [ ] **Step 3: Update the `item_id` template variable**

Change the query in the templating section from:
```json
"query": "label_values(demo_orders_total, item_id)"
```
to:
```json
"query": "label_values(demo_inventory_cache_hits_total, item_id)"
```

- [ ] **Step 4: Update Row 1 (identity strip) — replace all `order-service` filters and panel queries**

Replace panel 101 (RPS) target expr:
```
sum(rate(demo_http_server_duration_milliseconds_count{service_name="inventory-service"}[1m]))
```

Replace panel 102 (Error %). Inventory has no business-error counter, so substitute "cache miss %" — this is the inventory equivalent of an error rate for ops thinking:
```json
{
  "id": 102, "type": "stat", "title": "Cache miss %",
  "datasource": { "type": "prometheus", "uid": "prometheus" },
  "gridPos": { "x": 4, "y": 1, "w": 4, "h": 4 },
  "fieldConfig": {
    "defaults": {
      "unit": "percent", "decimals": 1,
      "thresholds": { "mode": "absolute", "steps": [
        { "color": "green", "value": null },
        { "color": "yellow", "value": 20 },
        { "color": "red", "value": 50 }
      ] }
    }
  },
  "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
  "targets": [{
    "datasource": { "type": "prometheus", "uid": "prometheus" },
    "expr": "100 * sum(rate(demo_inventory_cache_misses_total[5m])) / sum(rate(demo_inventory_cache_hits_total[5m]) + rate(demo_inventory_cache_misses_total[5m]))",
    "legendFormat": "miss %", "refId": "A"
  }]
}
```

Replace panels 103/104/105 (p50/p95/p99) target `expr` — substitute `demo_order_duration_seconds_bucket` → `demo_inventory_lookup_duration_seconds_bucket` in all three.

Replace panel 106 (Uptime) target `expr`:
```
time() - max(process_start_time_seconds{job="inventory-service"})
```

- [ ] **Step 5: Update Row 2 (endpoint breakdown) — replace `service_name`**

In panels 201, 202, 203, 204: substitute every occurrence of `service_name="order-service"` → `service_name="inventory-service"`. No other changes in this row.

- [ ] **Step 6: Replace Row 3 (business) entirely with inventory-specific panels**

Find Row 3 (panel id 300 row + panels 301, 302, 303, 304) and replace those 5 panels with:

```json
,
    {
      "id": 300, "type": "row", "title": "Business — cache",
      "gridPos": { "x": 0, "y": 22, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 301, "type": "timeseries", "title": "Cache hits vs misses (per minute)",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 23, "w": 12, "h": 8 },
      "fieldConfig": {
        "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 10 }, "unit": "short" },
        "overrides": [
          { "matcher": { "id": "byName", "options": "hits" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "green" } }] },
          { "matcher": { "id": "byName", "options": "misses" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "orange" } }] }
        ]
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "sum(rate(demo_inventory_cache_hits_total[1m])) * 60", "legendFormat": "hits", "refId": "A" },
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "sum(rate(demo_inventory_cache_misses_total[1m])) * 60", "legendFormat": "misses", "refId": "B" }
      ]
    },
    {
      "id": 302, "type": "timeseries", "title": "Cache hit % over time",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 23, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 5 }, "unit": "percent", "min": 0, "max": 100, "color": { "mode": "fixed", "fixedColor": "green" } } },
      "options": { "tooltip": { "mode": "single" }, "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "100 * sum(rate(demo_inventory_cache_hits_total[1m])) / sum(rate(demo_inventory_cache_hits_total[1m]) + rate(demo_inventory_cache_misses_total[1m]))",
        "legendFormat": "hit %", "refId": "A"
      }]
    },
    {
      "id": 303, "type": "timeseries", "title": "Lookup p95 split by cache_hit",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 31, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 5 }, "unit": "s", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.95, sum by (cache_hit, le) (rate(demo_inventory_lookup_duration_seconds_bucket[5m])))",
        "legendFormat": "cache_hit={{cache_hit}}", "refId": "A"
      }],
      "description": "Headline insight: cache_hit=true is fast (~5ms), cache_hit=false slow. slow_query=true bumps cache_hit=false toward 2s."
    },
    {
      "id": 304, "type": "table", "title": "Top items by miss count (range)",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 31, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "align": "right" } } },
      "options": { "showHeader": true, "sortBy": [{ "displayName": "Value", "desc": true }] },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "topk(10, sum by (item_id) (increase(demo_inventory_cache_misses_total[$__range])))",
        "legendFormat": "{{item_id}}", "refId": "A", "format": "table", "instant": true
      }],
      "transformations": [{ "id": "organize", "options": { "excludeByName": { "Time": true }, "indexByName": {}, "renameByName": {} } }]
    }
```

- [ ] **Step 7: Replace Row 4 (dependencies) entirely with inventory-specific span panels**

Find Row 4 (panel id 400 row + panels 401, 402) and replace with 3 panels:

```json
,
    {
      "id": 400, "type": "row", "title": "Dependencies (via span metrics)",
      "gridPos": { "x": 0, "y": 39, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 401, "type": "timeseries", "title": "Redis vs DB call rate",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 40, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 10 }, "unit": "reqps", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (span_name) (rate(traces_spanmetrics_calls_total{service=\"inventory-service\", span_name=~\"redis-cache-lookup|db-stock-lookup\"}[1m]))",
        "legendFormat": "{{span_name}}", "refId": "A"
      }]
    },
    {
      "id": 402, "type": "timeseries", "title": "Redis lookup p95",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 40, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 5 }, "unit": "ms", "color": { "mode": "fixed", "fixedColor": "blue" } } },
      "options": { "tooltip": { "mode": "single" }, "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.95, sum by (le) (rate(traces_spanmetrics_latency_bucket{service=\"inventory-service\", span_name=\"redis-cache-lookup\"}[5m])))",
        "legendFormat": "redis p95", "refId": "A"
      }]
    },
    {
      "id": 403, "type": "timeseries", "title": "DB fallback p95",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 48, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 5 }, "unit": "ms", "color": { "mode": "fixed", "fixedColor": "orange" } } },
      "options": { "tooltip": { "mode": "single" }, "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.95, sum by (le) (rate(traces_spanmetrics_latency_bucket{service=\"inventory-service\", span_name=\"db-stock-lookup\"}[5m])))",
        "legendFormat": "db p95", "refId": "A"
      }]
    }
```

This adds a 3rd panel (`403`). Bump the subsequent row's `gridPos.y` accordingly: Row 5 row header moves from y=48 to y=56, panel 501 (logs) from y=49 to y=57, Row 6 row header from y=59 to y=67, panel 601 (traces) from y=60 to y=68. (Grafana auto-corrects overlap, but explicit coords are cleaner.)

- [ ] **Step 8: Update Rows 5 & 6 — filter logs and traces to inventory**

Panel 501 (logs): change `otelServiceName="order-service"` → `otelServiceName="inventory-service"`. Update panel title from "Order-service logs..." → "Inventory-service logs...".

Panel 601 (traces): change TraceQL query from `.service.name = "order-service"` → `.service.name = "inventory-service"`.

- [ ] **Step 9: Verify**

Wait 30s, refresh. Open `Dev — Inventory Service`. Expected:
- Identity strip shows inventory metrics; cache miss % is the second tile
- Endpoint breakdown shows inventory-service routes (`GET /stock/{id}`, `GET /metrics`)
- Business row: cache hits vs misses, hit % over time, p95 split by cache_hit (headline insight), top items by misses
- Dependencies: Redis vs DB rates, Redis p95, DB p95
- Logs and traces filtered to inventory

Trigger a slow query to validate the cache_hit panel:
```bash
for i in $(seq 1 10); do curl -s -X POST http://localhost:8000/orders -H "Content-Type: application/json" -d '{"item_id":"sku-1","quantity":1,"slow_query":true}' > /dev/null & done
wait
```

After 30s, the `cache_hit=false` line on panel 303 should climb to ~2s. `cache_hit=true` stays flat near 0.

- [ ] **Step 10: Commit**

```bash
git add grafana/provisioning/dashboards/dev-inventory.json
git commit -m "feat(grafana): add dev-inventory dashboard"
```

---

## Task 7: Build `dev-payment.json` by copying dev-order and substituting

**Files:**
- Create: `grafana/provisioning/dashboards/dev-payment.json`

- [ ] **Step 1: Copy and rename metadata**

```bash
cp grafana/provisioning/dashboards/dev-order.json grafana/provisioning/dashboards/dev-payment.json
```

Edit `dev-payment.json`:
- `"uid"`: `"otel-demo-dev-payment"`
- `"title"`: `"Dev — Payment Service"`
- Tag: `"order-service"` → `"payment-service"`
- Templating query: `"label_values(demo_payments_total, item_id)"`

- [ ] **Step 2: Update Row 1 (identity strip)**

Panel 101 (RPS) expr: `sum(rate(demo_http_server_duration_milliseconds_count{service_name="payment-service"}[1m]))`

Panel 102 (Error %) — replace with "Failure %" using payment-fail thresholds:
```json
{
  "id": 102, "type": "stat", "title": "Failure %",
  "datasource": { "type": "prometheus", "uid": "prometheus" },
  "gridPos": { "x": 4, "y": 1, "w": 4, "h": 4 },
  "fieldConfig": {
    "defaults": {
      "unit": "percent", "decimals": 2,
      "thresholds": { "mode": "absolute", "steps": [
        { "color": "green", "value": null },
        { "color": "yellow", "value": 5 },
        { "color": "red", "value": 15 }
      ] }
    }
  },
  "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
  "targets": [{
    "datasource": { "type": "prometheus", "uid": "prometheus" },
    "expr": "100 * sum(rate(demo_payment_failures_total[5m])) / (sum(rate(demo_payments_total[5m])) + sum(rate(demo_payment_failures_total[5m])))",
    "legendFormat": "fail %", "refId": "A"
  }],
  "description": "Baseline ~10% due to built-in random failure. Yellow = normal, Red = anomaly."
}
```

Panels 103/104/105 (p50/p95/p99): substitute `demo_order_duration_seconds_bucket` → `demo_payment_duration_seconds_bucket` in all three.

Panel 106 (Uptime): `process_start_time_seconds{job="payment-service"}`.

- [ ] **Step 3: Update Row 2 (endpoint breakdown)**

Substitute all `service_name="order-service"` → `service_name="payment-service"` in panels 201, 202, 203, 204.

- [ ] **Step 4: Replace Row 3 (business) with payment-specific panels**

```json
,
    {
      "id": 300, "type": "row", "title": "Business — payments",
      "gridPos": { "x": 0, "y": 22, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 301, "type": "timeseries", "title": "Payments/min by status",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 23, "w": 12, "h": 8 },
      "fieldConfig": {
        "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 10 }, "unit": "reqpm" },
        "overrides": [
          { "matcher": { "id": "byName", "options": "success" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "green" } }] },
          { "matcher": { "id": "byName", "options": "failed" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "red" } }] }
        ]
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (status) (rate(demo_payments_total[1m])) * 60",
        "legendFormat": "{{status}}", "refId": "A"
      }]
    },
    {
      "id": 302, "type": "timeseries", "title": "Failures/min by reason",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 23, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 15, "stacking": { "mode": "normal" } }, "unit": "reqpm", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (reason) (rate(demo_payment_failures_total[1m])) * 60",
        "legendFormat": "{{reason}}", "refId": "A"
      }]
    },
    {
      "id": 303, "type": "timeseries", "title": "p95 latency by status (success vs failed)",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 31, "w": 12, "h": 8 },
      "fieldConfig": {
        "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 5 }, "unit": "s" },
        "overrides": [
          { "matcher": { "id": "byName", "options": "success" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "green" } }] },
          { "matcher": { "id": "byName", "options": "failed" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "red" } }] }
        ]
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.95, sum by (status, le) (rate(demo_payment_duration_seconds_bucket[5m])))",
        "legendFormat": "{{status}}", "refId": "A"
      }],
      "description": "Useful to see whether failed paths are faster or slower than successful ones."
    },
    {
      "id": 304, "type": "histogram", "title": "Payment amount distribution",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 31, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "currencyUSD", "color": { "mode": "fixed", "fixedColor": "purple" } } },
      "options": { "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (le) (rate(demo_payment_amount_dollars_bucket[5m]))",
        "legendFormat": "{{le}}", "refId": "A", "format": "heatmap"
      }]
    }
```

- [ ] **Step 5: Replace Row 4 (dependencies) with payment-specific spans**

```json
,
    {
      "id": 400, "type": "row", "title": "Dependencies (via span metrics)",
      "gridPos": { "x": 0, "y": 39, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 401, "type": "timeseries", "title": "payment-gateway-call rate",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 40, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 10 }, "unit": "reqpm", "color": { "mode": "fixed", "fixedColor": "purple" } } },
      "options": { "tooltip": { "mode": "single" }, "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum(rate(traces_spanmetrics_calls_total{service=\"payment-service\", span_name=\"payment-gateway-call\"}[1m])) * 60",
        "legendFormat": "calls/min", "refId": "A"
      }]
    },
    {
      "id": 402, "type": "timeseries", "title": "payment-gateway-call p95",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 40, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 5 }, "unit": "ms", "color": { "mode": "fixed", "fixedColor": "blue" } } },
      "options": { "tooltip": { "mode": "single" }, "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.95, sum by (le) (rate(traces_spanmetrics_latency_bucket{service=\"payment-service\", span_name=\"payment-gateway-call\"}[5m])))",
        "legendFormat": "p95", "refId": "A"
      }]
    }
```

This has the same panel count as dev-order Row 4 (2 panels), so Rows 5 & 6 grid positions stay unchanged.

- [ ] **Step 6: Update Rows 5 & 6**

Panel 501 (logs): `otelServiceName="payment-service"`, update title.
Panel 601 (traces): `.service.name = "payment-service"`.

- [ ] **Step 7: Verify**

Refresh. Open `Dev — Payment Service`. Trigger failures to confirm:
```bash
for i in $(seq 1 10); do curl -s -X POST http://localhost:8000/orders -H "Content-Type: application/json" -d "{\"item_id\":\"sku-$i\",\"quantity\":1,\"fail_payment\":true}" > /dev/null & done
wait
sleep 30
```

Expected:
- `Failure %` tile bumps red
- `Failures/min by reason` shows `forced_by_demo_flag` series spiking
- `p95 latency by status` may show `failed` paths being slightly faster (no gateway sleep on forced failures — check `payment-service/main.py` if curious)
- `Payment amount distribution` populated with bars

- [ ] **Step 8: Commit**

```bash
git add grafana/provisioning/dashboards/dev-payment.json
git commit -m "feat(grafana): add dev-payment dashboard"
```

---

## Task 8: Final cross-dashboard smoke test

- [ ] **Step 1: Open all three dev dashboards in tabs**

From Home, click each of the three "Dev — ..." tiles. Each should load without 404. Each should show 6 rows: identity, endpoints, business, deps, logs, traces.

- [ ] **Step 2: Verify no panel has duplicate legends**

Walk each dashboard top to bottom. Any timeseries panel with `p99 p99 p99 p99` style legends → re-paste the relevant `sum by (le)` query.

- [ ] **Step 3: Verify the `service_name` filter is actually filtering**

On `Dev — Order Service`, the RPS panel should show order-service rate only. If you see inventory or payment rates mixed in, the `service_name` label isn't applied to HTTP server metrics. Fall back: substitute `service_name="X"` → `job=~"X.*"` per `verification-notes.md`.

- [ ] **Step 4: No commit for smoke test**

If everything passes, Plan 3 is complete.

---

## Spec coverage (self-review)

- §5.2 PromQL aggregation: every business + HTTP query uses `sum by (...)` ✓
- §5.3 service colors: dev-order uses purple stat color, dev-inventory green theme via cache colors, dev-payment red/green status overrides ✓
- §6.3 Dev — Order Service: 6 rows ✓
- §6.4 Dev — Inventory Service: 6 rows with cache_hit split panel (headline insight) ✓
- §6.5 Dev — Payment Service: 6 rows with status latency split + amount distribution ✓
- §5.5 metric inventory: every query uses an already-verified metric ✓
- §9 risks: span-metric label name handled with verification fallback ✓
