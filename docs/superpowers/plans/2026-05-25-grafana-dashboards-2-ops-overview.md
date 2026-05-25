# Ops / SRE Overview Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Ops/SRE overview dashboard — a glanceable health page that answers "is something broken?" in under 5 seconds.

**Architecture:** Single JSON dashboard `ops-overview.json`. Six rows: health strip (6 stat tiles), rate (3 timeseries), latency (3 timeseries), saturation (2 host metrics), service map (Tempo nodeGraph), errors (log rate + log panel). All Prometheus queries use `sum by (...)` aggregation to eliminate the duplicate-legend problem inherited from the legacy dashboard.

**Tech Stack:** Grafana 10.3.0, Prometheus, Tempo, Loki.

**Spec:** [`../specs/2026-05-25-grafana-dashboards-redesign-design.md`](../specs/2026-05-25-grafana-dashboards-redesign-design.md) §6.2

**Prerequisites:** Plan 1 complete. `verification-notes.md` confirms `service_name` label and Tempo span metrics. If verification noted any substitutions, apply them as you go.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `grafana/provisioning/dashboards/ops-overview.json` | create | The Ops/SRE dashboard |

---

## Task 1: Create skeleton + variables + Row 1 (Health strip)

The skeleton sets the dashboard UID (referenced by Home), variables (`$service`, `$item_id`), and the 6 stat tiles in row 1.

**Files:**
- Create: `grafana/provisioning/dashboards/ops-overview.json`

- [ ] **Step 1: Write the dashboard skeleton with Row 1**

Create `grafana/provisioning/dashboards/ops-overview.json`:

```json
{
  "uid": "otel-demo-ops",
  "title": "Ops Overview",
  "tags": ["otel", "demo", "ops"],
  "timezone": "browser",
  "schemaVersion": 38,
  "refresh": "10s",
  "time": { "from": "now-30m", "to": "now" },
  "templating": {
    "list": [
      {
        "name": "service",
        "type": "query",
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "query": "label_values(up, job)",
        "label": "Service",
        "current": { "text": "All", "value": "$__all" },
        "includeAll": true,
        "multi": true,
        "refresh": 2
      },
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
      "id": 100, "type": "row", "title": "Health at a glance",
      "gridPos": { "x": 0, "y": 0, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 101, "type": "stat", "title": "Order Error %",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 1, "w": 4, "h": 4 },
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
        "legendFormat": "error %", "refId": "A"
      }]
    },
    {
      "id": 102, "type": "stat", "title": "Payment Fail %",
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
      "description": "Baseline is ~10% due to built-in random failure (payment-service/main.py:188). Yellow = normal, Red = something extra is wrong."
    },
    {
      "id": 103, "type": "stat", "title": "p95 Order Duration",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 8, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": {
        "defaults": {
          "unit": "s", "decimals": 2,
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
      "id": 104, "type": "stat", "title": "p95 Inventory Duration",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": {
        "defaults": {
          "unit": "s", "decimals": 2,
          "thresholds": { "mode": "absolute", "steps": [
            { "color": "green", "value": null },
            { "color": "yellow", "value": 0.2 },
            { "color": "red", "value": 1 }
          ] }
        }
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "histogram_quantile(0.95, sum by(le) (rate(demo_inventory_lookup_duration_seconds_bucket[5m])))",
        "legendFormat": "p95", "refId": "A"
      }]
    },
    {
      "id": 105, "type": "stat", "title": "Cache Hit %",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 16, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": {
        "defaults": {
          "unit": "percent", "decimals": 1,
          "thresholds": { "mode": "absolute", "steps": [
            { "color": "red", "value": null },
            { "color": "yellow", "value": 50 },
            { "color": "green", "value": 80 }
          ] }
        }
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "100 * sum(rate(demo_inventory_cache_hits_total[5m])) / sum(rate(demo_inventory_cache_hits_total[5m]) + rate(demo_inventory_cache_misses_total[5m]))",
        "legendFormat": "hit %", "refId": "A"
      }]
    },
    {
      "id": 106, "type": "stat", "title": "Orders/min now",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 20, "y": 1, "w": 4, "h": 4 },
      "fieldConfig": {
        "defaults": {
          "unit": "reqpm", "decimals": 1,
          "color": { "mode": "fixed", "fixedColor": "purple" }
        }
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "area" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum(rate(demo_orders_total[1m])) * 60",
        "legendFormat": "orders/min", "refId": "A"
      }]
    }
  ]
}
```

This is the dashboard with row 1 complete. Subsequent tasks append panels to the `panels` array.

- [ ] **Step 2: Reload Grafana and verify Row 1**

```bash
docker compose restart grafana
sleep 10
```

Open http://localhost:3000 → Dashboards → `Ops Overview`. Expected:
- 6 stat tiles in a single row across the top
- Each tile shows a live number (not "N/A")
- Colors reflect thresholds (e.g. "Order Error %" green if <1, "Cache Hit %" green if >80)
- Two variables (`Service`, `Item`) at the top, both defaulting to "All"

The Home dashboard's "Ops Overview" tile link should now resolve (no 404).

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/ops-overview.json
git commit -m "feat(grafana): add Ops Overview dashboard skeleton + health strip"
```

---

## Task 2: Row 2 — Rate (3 timeseries)

**Files:**
- Modify: `grafana/provisioning/dashboards/ops-overview.json` — append 4 panels to the `panels` array (1 row + 3 timeseries)

- [ ] **Step 1: Append Row 2 panels**

Inside the `panels` array, after panel id 106 and before the closing `]`, append (note the leading comma):

```json
,
    {
      "id": 200, "type": "row", "title": "Rate",
      "gridPos": { "x": 0, "y": 5, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 201, "type": "timeseries", "title": "Orders/min by status",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 6, "w": 8, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 10, "stacking": { "mode": "none" } },
          "unit": "reqpm",
          "color": { "mode": "palette-classic" }
        }
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (status) (rate(demo_orders_total[1m])) * 60",
        "legendFormat": "{{status}}", "refId": "A"
      }]
    },
    {
      "id": 202, "type": "timeseries", "title": "Order errors/min by reason",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 8, "y": 6, "w": 8, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 15, "stacking": { "mode": "normal" } },
          "unit": "reqpm",
          "color": { "mode": "palette-classic" }
        }
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (reason) (rate(demo_order_errors_total[1m])) * 60",
        "legendFormat": "{{reason}}", "refId": "A"
      }]
    },
    {
      "id": 203, "type": "timeseries", "title": "Payment failures/min by reason",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 16, "y": 6, "w": 8, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 15, "stacking": { "mode": "normal" } },
          "unit": "reqpm",
          "color": { "mode": "palette-classic" }
        }
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (reason) (rate(demo_payment_failures_total[1m])) * 60",
        "legendFormat": "{{reason}}", "refId": "A"
      }]
    }
```

- [ ] **Step 2: Verify**

The provisioner picks up changes every 30 seconds (per `updateIntervalSeconds: 30` in `dashboards.yaml`). Refresh the Ops Overview page after 30s. Expected:
- 3 timeseries panels appear under a "Rate" row header
- Each panel's legend shows ONLY meaningful labels (e.g. `confirmed` not `orders/min — confirmed` with 4 duplicate copies)
- Error reason panel shows up to 3 series: `insufficient_stock`, `inventory_service_error`, `payment_failed`
- Payment failure reason panel shows up to 3 series: `invalid_amount`, `forced_by_demo_flag`, `random_gateway_rejection`

If legends still look duplicated: that means `sum by (...)` didn't fully collapse extra dimensions. Run the query in Grafana's Explore view and inspect the labels — if there are extra labels like `__name__`, that's normal; the legend format `{{reason}}` already picks only `reason`. If you see the same `reason` value twice with different `job` labels, the `sum by` is somehow being bypassed (likely a typo).

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/ops-overview.json
git commit -m "feat(grafana): ops dashboard row 2 — rate panels"
```

---

## Task 3: Row 3 — Latency (3 timeseries, p50/p95/p99)

**Files:**
- Modify: `grafana/provisioning/dashboards/ops-overview.json`

- [ ] **Step 1: Append Row 3 panels**

Append to the `panels` array (leading comma):

```json
,
    {
      "id": 300, "type": "row", "title": "Latency (p50 / p95 / p99)",
      "gridPos": { "x": 0, "y": 14, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 301, "type": "timeseries", "title": "Order duration",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 15, "w": 8, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 5 },
          "unit": "s"
        },
        "overrides": [
          { "matcher": { "id": "byName", "options": "p50" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "green" } }] },
          { "matcher": { "id": "byName", "options": "p95" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "yellow" } }] },
          { "matcher": { "id": "byName", "options": "p99" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "red" } }] }
        ]
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "histogram_quantile(0.50, sum by (le) (rate(demo_order_duration_seconds_bucket[5m])))", "legendFormat": "p50", "refId": "A" },
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "histogram_quantile(0.95, sum by (le) (rate(demo_order_duration_seconds_bucket[5m])))", "legendFormat": "p95", "refId": "B" },
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "histogram_quantile(0.99, sum by (le) (rate(demo_order_duration_seconds_bucket[5m])))", "legendFormat": "p99", "refId": "C" }
      ]
    },
    {
      "id": 302, "type": "timeseries", "title": "Inventory lookup duration",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 8, "y": 15, "w": 8, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 5 },
          "unit": "s"
        },
        "overrides": [
          { "matcher": { "id": "byName", "options": "p50" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "green" } }] },
          { "matcher": { "id": "byName", "options": "p95" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "yellow" } }] },
          { "matcher": { "id": "byName", "options": "p99" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "red" } }] }
        ]
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "histogram_quantile(0.50, sum by (le) (rate(demo_inventory_lookup_duration_seconds_bucket[5m])))", "legendFormat": "p50", "refId": "A" },
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "histogram_quantile(0.95, sum by (le) (rate(demo_inventory_lookup_duration_seconds_bucket[5m])))", "legendFormat": "p95", "refId": "B" },
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "histogram_quantile(0.99, sum by (le) (rate(demo_inventory_lookup_duration_seconds_bucket[5m])))", "legendFormat": "p99", "refId": "C" }
      ]
    },
    {
      "id": 303, "type": "timeseries", "title": "Payment duration",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 16, "y": 15, "w": 8, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 5 },
          "unit": "s"
        },
        "overrides": [
          { "matcher": { "id": "byName", "options": "p50" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "green" } }] },
          { "matcher": { "id": "byName", "options": "p95" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "yellow" } }] },
          { "matcher": { "id": "byName", "options": "p99" }, "properties": [{ "id": "color", "value": { "mode": "fixed", "fixedColor": "red" } }] }
        ]
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "histogram_quantile(0.50, sum by (le) (rate(demo_payment_duration_seconds_bucket[5m])))", "legendFormat": "p50", "refId": "A" },
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "histogram_quantile(0.95, sum by (le) (rate(demo_payment_duration_seconds_bucket[5m])))", "legendFormat": "p95", "refId": "B" },
        { "datasource": { "type": "prometheus", "uid": "prometheus" }, "expr": "histogram_quantile(0.99, sum by (le) (rate(demo_payment_duration_seconds_bucket[5m])))", "legendFormat": "p99", "refId": "C" }
      ]
    }
```

- [ ] **Step 2: Verify**

Refresh dashboard. Expected:
- Each latency panel shows exactly 3 lines (p50/p95/p99), not 9 or 12
- p50 is green, p95 yellow, p99 red
- p99 > p95 > p50 in steady state

This is the headline fix for the original duplicate-legend bug. If you still see "p99 p99 p99 p99…", the `sum by (le)` was lost — re-paste from this plan.

- [ ] **Step 3: Trigger a slow query and confirm Inventory p95 spikes**

In another terminal:
```bash
for i in $(seq 1 10); do curl -s -X POST http://localhost:8000/orders -H "Content-Type: application/json" -d '{"item_id":"sku-1","quantity":1,"slow_query":true}' > /dev/null; sleep 1; done
```

Inventory p95 should climb visibly within 30s. After the loop ends, it decays back. This confirms the panel is wired correctly.

- [ ] **Step 4: Commit**

```bash
git add grafana/provisioning/dashboards/ops-overview.json
git commit -m "feat(grafana): ops dashboard row 3 — latency p50/p95/p99 per service"
```

---

## Task 4: Row 4 — Host saturation (2 timeseries)

**Files:**
- Modify: `grafana/provisioning/dashboards/ops-overview.json`

- [ ] **Step 1: Append Row 4**

```json
,
    {
      "id": 400, "type": "row", "title": "Host saturation",
      "gridPos": { "x": 0, "y": 23, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 401, "type": "timeseries", "title": "CPU % busy",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 24, "w": 12, "h": 6 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 10 },
          "unit": "percent", "min": 0, "max": 100,
          "color": { "mode": "fixed", "fixedColor": "blue" }
        }
      },
      "options": { "tooltip": { "mode": "single" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "100 - (avg(rate(node_cpu_seconds_total{mode=\"idle\"}[1m])) * 100)",
        "legendFormat": "cpu busy", "refId": "A"
      }]
    },
    {
      "id": 402, "type": "timeseries", "title": "Memory used %",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 24, "w": 12, "h": 6 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 10 },
          "unit": "percent", "min": 0, "max": 100,
          "color": { "mode": "fixed", "fixedColor": "orange" }
        }
      },
      "options": { "tooltip": { "mode": "single" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))",
        "legendFormat": "mem used", "refId": "A"
      }]
    }
```

- [ ] **Step 2: Verify**

Refresh. Expected: 2 panels showing CPU and memory %, smooth lines. In a docker-compose demo on a real laptop, both should be modest.

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/ops-overview.json
git commit -m "feat(grafana): ops dashboard row 4 — host saturation"
```

---

## Task 5: Row 5 — Service map (Tempo nodeGraph)

**Files:**
- Modify: `grafana/provisioning/dashboards/ops-overview.json`

- [ ] **Step 1: Append Row 5**

```json
,
    {
      "id": 500, "type": "row", "title": "Service map",
      "gridPos": { "x": 0, "y": 30, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 501, "type": "nodeGraph", "title": "Service dependency graph",
      "datasource": { "type": "tempo", "uid": "tempo" },
      "gridPos": { "x": 0, "y": 31, "w": 24, "h": 10 },
      "targets": [{
        "datasource": { "type": "tempo", "uid": "tempo" },
        "queryType": "serviceMap", "refId": "A"
      }],
      "description": "Built from Tempo traces_service_graph_* metrics. Each edge shows RPS and avg latency. Click a node to drill into traces."
    }
```

- [ ] **Step 2: Verify**

Refresh. Expected: a node graph showing 4 nodes (`user`, `order-service`, `inventory-service`, `payment-service`) with edges between them. Edge labels show request rate and latency.

If the graph is empty: Tempo's metrics_generator needs traces flowing. Wait 60s after starting the stack. If still empty, confirm `traces_service_graph_request_total` exists in Prometheus (`curl 'http://localhost:9090/api/v1/query?query=traces_service_graph_request_total'`).

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/ops-overview.json
git commit -m "feat(grafana): ops dashboard row 5 — Tempo service map"
```

---

## Task 6: Row 6 — Errors (log rate + recent error logs)

**Files:**
- Modify: `grafana/provisioning/dashboards/ops-overview.json`

- [ ] **Step 1: Append Row 6**

```json
,
    {
      "id": 600, "type": "row", "title": "Errors",
      "gridPos": { "x": 0, "y": 41, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 601, "type": "timeseries", "title": "Error log rate by service",
      "datasource": { "type": "loki", "uid": "loki" },
      "gridPos": { "x": 0, "y": 42, "w": 8, "h": 10 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 15, "drawStyle": "bars" },
          "unit": "short",
          "color": { "mode": "palette-classic" }
        }
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "loki", "uid": "loki" },
        "expr": "sum by (otelServiceName) (count_over_time({exporter=\"OTLP\"} | json | severity=\"ERROR\" [1m]))",
        "legendFormat": "{{otelServiceName}}", "refId": "A"
      }],
      "description": "Counts ERROR-level log lines per service per minute. Spikes here precede or accompany metric-level errors."
    },
    {
      "id": 602, "type": "logs", "title": "Recent error logs (click trace_id → Tempo)",
      "datasource": { "type": "loki", "uid": "loki" },
      "gridPos": { "x": 8, "y": 42, "w": 16, "h": 10 },
      "options": {
        "dedupStrategy": "none", "enableLogDetails": true, "prettifyLogMessage": true,
        "showLabels": false, "showTime": true, "sortOrder": "Descending", "wrapLogMessage": true
      },
      "targets": [{
        "datasource": { "type": "loki", "uid": "loki" },
        "expr": "{exporter=\"OTLP\"} | json | severity=\"ERROR\"",
        "refId": "A", "editorMode": "code", "queryType": "range", "maxLines": 100
      }]
    }
  ]
}
```

The closing `]` and `}` are the dashboard's panels-array close and root-object close — this is the LAST task that appends panels.

- [ ] **Step 2: Verify**

Refresh. Expected:
- Bar chart on the left showing error log rate per service. Most bars will be for `payment-service` (the 10% random failure floor).
- Logs panel on the right with recent error log lines. Each line is expandable; expanding shows the JSON body with `traceid` as a clickable derived field. Click it → Tempo opens that trace.

If the bar chart is empty: the JSON parser may not produce `severity` as that key. Run the Loki query in Explore view, add `| json`, and inspect the parsed fields. If the field is `severity_text` or `level`, update the query.

If the derived-field link is missing on log lines: check `grafana/provisioning/datasources/datasources.yaml` has the `derivedFields` block on the Loki datasource (per CLAUDE.md it's there).

- [ ] **Step 3: Trigger errors to confirm**

```bash
for i in $(seq 1 5); do curl -s -X POST http://localhost:8000/orders -H "Content-Type: application/json" -d '{"item_id":"sku-1","quantity":1,"fail_payment":true}' > /dev/null; done
```

Within 30s, both panels should show fresh entries. Click a trace_id in the log panel → Tempo opens with the full trace highlighting the payment failure span.

- [ ] **Step 4: Commit**

```bash
git add grafana/provisioning/dashboards/ops-overview.json
git commit -m "feat(grafana): ops dashboard row 6 — error log rate + recent error logs"
```

---

## Task 7: Final smoke test

- [ ] **Step 1: Full dashboard pass**

Open `Ops Overview`. Walk through every panel top to bottom and confirm:
- No panel says "No data" (unless intentional — e.g. service map empty for the first minute)
- No legend has duplicate entries
- Thresholds color correctly under normal load (most things green)
- The 6 rows correspond to the 6 sections of spec §6.2

- [ ] **Step 2: Failure injection pass**

```bash
# Force errors
for i in $(seq 1 20); do curl -s -X POST http://localhost:8000/orders -H "Content-Type: application/json" -d '{"item_id":"sku-1","quantity":1,"fail_payment":true}' > /dev/null & done
wait
sleep 30
```

Expected after 30s:
- `Order Error %` tile turns yellow then red
- `Order errors/min by reason` shows `payment_failed` series spiking
- `Recent error logs` populated with new entries
- `Order duration p95/p99` may bump slightly

After 2 minutes of idle, all tiles should return to green.

- [ ] **Step 3: Slow-query injection pass**

```bash
for i in $(seq 1 10); do curl -s -X POST http://localhost:8000/orders -H "Content-Type: application/json" -d '{"item_id":"sku-1","quantity":1,"slow_query":true}' > /dev/null & done
wait
sleep 30
```

Expected:
- `p95 Inventory Duration` tile yellow/red
- `Inventory lookup duration` p95 spikes visibly toward 2s
- `Order duration` p95 also bumps (the order request waits on inventory)

- [ ] **Step 4: No commit needed for smoke test**

If any panel fails verification, go back to the relevant task and fix. Otherwise, Plan 2 is complete.

---

## Spec coverage (self-review)

- §5.2 PromQL aggregation rules: every query uses `sum by (...)` or `sum(...)` ✓
- §5.3 visual conventions: timeseries use multi-mode tooltip, list legend, legendFormat is short ✓
- §6.2 Row 1 health strip: 6 stat tiles with thresholds ✓
- §6.2 Row 2 rate: 3 timeseries with correct queries ✓
- §6.2 Row 3 latency: 3 timeseries × 3 quantiles, no duplicate legends ✓
- §6.2 Row 4 saturation: 2 node-exporter timeseries ✓
- §6.2 Row 5 service map: Tempo nodeGraph ✓
- §6.2 Row 6 errors: log rate timeseries + log panel with derived fields ✓
- §5.4 datasource UIDs explicit: yes (`prometheus`, `tempo`, `loki`) ✓
- §9 Loki severity field name: verified in Plan 1 Task 1 Step 7; if different, adjust queries in Task 6 Step 1 ✓
