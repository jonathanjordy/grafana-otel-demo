# Correlation Demo + Business View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the OTel Correlation Demo (storytelling dashboard showing metrics ↔ logs ↔ traces wiring) and the Business / Product view (outcome-focused KPIs).

**Architecture:** Two independent JSON dashboards. The correlation demo's headline feature — exemplar dots on the metric panel that jump to Tempo — depends on Prometheus accepting and storing exemplars; Task 1 decides whether to enable that flag.

**Tech Stack:** Grafana 10.3.0, Prometheus, Tempo, Loki, docker-compose.

**Spec:** [`../specs/2026-05-25-grafana-dashboards-redesign-design.md`](../specs/2026-05-25-grafana-dashboards-redesign-design.md) §6.6, §6.7, §9

**Prerequisites:** Plans 1, 2, 3 complete. `verification-notes.md` available.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `docker-compose.yml` | maybe modify | Add `--enable-feature=exemplar-storage` to prometheus |
| `grafana/provisioning/dashboards/otel-correlation-demo.json` | create | The storytelling dashboard |
| `grafana/provisioning/dashboards/business-view.json` | create | The KPI/outcomes dashboard |

---

## Task 1: Decide on Prometheus exemplar storage flag

Per spec §9, the correlation demo's "click exemplar dot → Tempo" navigation only works if Prometheus stores exemplars. Currently `docker-compose.yml` runs prometheus without `--enable-feature=exemplar-storage`.

- [ ] **Step 1: Check current prometheus command**

Read `docker-compose.yml` around line 145 (the prometheus service). Confirm the `command:` list contains:
```yaml
- "--config.file=/etc/prometheus/prometheus.yml"
- "--storage.tsdb.path=/prometheus"
- "--web.enable-remote-write-receiver"
```

And does NOT contain `--enable-feature=exemplar-storage`.

- [ ] **Step 2: Verify exemplars are actually being produced**

Run:
```bash
curl -s 'http://localhost:9090/api/v1/query_exemplars?query=demo_orders_total&start='$(date -u -d '5 minutes ago' '+%Y-%m-%dT%H:%M:%SZ')'&end='$(date -u '+%Y-%m-%dT%H:%M:%SZ')
```

Expected output one of:
- A JSON response with non-empty `data` array → exemplars ARE flowing → enabling storage gives full functionality. Choose **option A** below.
- A JSON response with empty `data` array → exemplars not stored yet → enabling the flag will start storing them on restart. Choose **option A** below.
- An error mentioning "exemplar storage" or feature disabled → flag definitively required for storage. Choose **option A** below.

If no exemplars are emitted by the SDK at all (the OTel-collector → Prometheus exporter pipeline may strip them), option A still won't show dots — but the cost of enabling the flag is one line. Choose **option A**.

- [ ] **Step 3: Pick a path**

**Option A (recommended):** Enable exemplar storage. Proceed to Step 4.
**Option B:** Skip exemplars. Skip to Task 2 and adjust the metric panel in Task 3 to remove `exemplar: true`.

- [ ] **Step 4: Add the flag (if Option A)**

Edit `docker-compose.yml`, find the prometheus service's `command:` block and add the flag:

```yaml
  prometheus:
    image: prom/prometheus:v2.50.0
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--web.enable-remote-write-receiver"
      - "--enable-feature=exemplar-storage"
```

- [ ] **Step 5: Restart prometheus only**

```bash
docker compose restart prometheus
sleep 10
```

Verify it came up cleanly:
```bash
docker compose logs prometheus --tail 30
```

Expected: no errors. The line `enable feature: exemplar-storage` should appear in startup logs.

- [ ] **Step 6: Re-verify exemplars are stored**

After 60s of load-generator traffic, repeat the query from Step 2. Expected: `data` array now contains exemplar objects with `seriesLabels` and a list of exemplar dots each having `labels.traceID`.

If still empty after 2 minutes: the upstream SDK or collector isn't including exemplars on the OTLP push. This is acceptable — the correlation demo's metric panel will still render, just without dots. The log-based trace_id link still works.

- [ ] **Step 7: Commit (if Option A)**

```bash
git add docker-compose.yml
git commit -m "feat(prometheus): enable exemplar storage for trace correlation"
```

---

## Task 2: Create `otel-correlation-demo.json` — skeleton + intro

**Files:**
- Create: `grafana/provisioning/dashboards/otel-correlation-demo.json`

- [ ] **Step 1: Write skeleton + Row 1 (intro markdown)**

```json
{
  "uid": "otel-demo-correlation",
  "title": "OTel Correlation Demo",
  "tags": ["otel", "demo", "correlation", "teaching"],
  "timezone": "browser",
  "schemaVersion": 38,
  "refresh": "10s",
  "time": { "from": "now-15m", "to": "now" },
  "panels": [
    {
      "id": 100, "type": "text", "title": "",
      "gridPos": { "x": 0, "y": 0, "w": 24, "h": 4 },
      "options": {
        "mode": "markdown",
        "content": "# How OpenTelemetry connects metrics, logs, and traces\n\nEach panel below is one step in the story. Watch the live data from the load-generator, or trigger a specific request:\n\n- **Force a failure:** `curl -X POST localhost:8000/orders -H 'Content-Type: application/json' -d '{\"item_id\":\"sku-1\",\"quantity\":1,\"fail_payment\":true}'`\n- **Force a slow query:** same as above with `\"slow_query\":true`"
      }
    }
  ]
}
```

- [ ] **Step 2: Reload and verify**

```bash
docker compose restart grafana
sleep 10
```

Open `OTel Correlation Demo`. Expected: markdown intro renders cleanly.

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/otel-correlation-demo.json
git commit -m "feat(grafana): correlation demo skeleton + intro"
```

---

## Task 3: Correlation demo — the metric, the log, the trace, the service map, the call-to-action

**Files:**
- Modify: `grafana/provisioning/dashboards/otel-correlation-demo.json`

- [ ] **Step 1: Append all 5 remaining panels**

Inside `panels`, after panel 100, append (note the leading comma):

```json
,
    {
      "id": 200, "type": "timeseries", "title": "Step 1 — The metric (orders/min). Click an exemplar dot to jump to Tempo.",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 4, "w": 24, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "custom": { "lineWidth": 2, "fillOpacity": 10 },
          "unit": "reqpm",
          "color": { "mode": "palette-classic" }
        }
      },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (status) (rate(demo_orders_total[1m])) * 60",
        "legendFormat": "{{status}}", "refId": "A",
        "exemplar": true
      }],
      "description": "If exemplar storage is enabled, small dots appear on the line — each is a real trace_id. Click → Tempo opens that trace. If you don't see dots, see Task 1."
    },
    {
      "id": 300, "type": "logs", "title": "Step 2 — The log. Each line carries the trace_id. Click the trace_id → Tempo.",
      "datasource": { "type": "loki", "uid": "loki" },
      "gridPos": { "x": 0, "y": 12, "w": 24, "h": 10 },
      "options": {
        "dedupStrategy": "none", "enableLogDetails": true, "prettifyLogMessage": true,
        "showLabels": false, "showTime": true, "sortOrder": "Descending", "wrapLogMessage": true
      },
      "targets": [{
        "datasource": { "type": "loki", "uid": "loki" },
        "expr": "{exporter=\"OTLP\"} | json",
        "refId": "A", "editorMode": "code", "queryType": "range", "maxLines": 100
      }],
      "description": "Expand any line to see structured fields including otelTraceID and otelSpanID. The trace_id is a clickable derived field (configured in datasources.yaml) that opens the trace in Tempo."
    },
    {
      "id": 400, "type": "table", "title": "Step 3 — The trace. Latest 20 traces across all three services.",
      "datasource": { "type": "tempo", "uid": "tempo" },
      "gridPos": { "x": 0, "y": 22, "w": 24, "h": 10 },
      "fieldConfig": { "defaults": { "custom": { "filterable": true } } },
      "options": { "footer": { "enablePagination": true } },
      "targets": [{
        "datasource": { "type": "tempo", "uid": "tempo" },
        "queryType": "traceql",
        "query": "{ .service.name =~ \"order-service|inventory-service|payment-service\" }",
        "limit": 20, "refId": "A"
      }],
      "description": "Click a trace ID → full waterfall opens. Each span's logs are accessible via the tracesToLogsV2 link (configured in datasources.yaml)."
    },
    {
      "id": 500, "type": "nodeGraph", "title": "Step 4 — The service map. Built automatically by Tempo from trace data.",
      "datasource": { "type": "tempo", "uid": "tempo" },
      "gridPos": { "x": 0, "y": 32, "w": 24, "h": 10 },
      "targets": [{
        "datasource": { "type": "tempo", "uid": "tempo" },
        "queryType": "serviceMap", "refId": "A"
      }],
      "description": "Nodes are services, edges show requests-per-second and average latency. No configuration needed — Tempo's metrics_generator discovers the topology from traces."
    },
    {
      "id": 600, "type": "text", "title": "",
      "gridPos": { "x": 0, "y": 42, "w": 24, "h": 4 },
      "options": {
        "mode": "markdown",
        "content": "## Try this\n\n1. Trigger a failure: `curl -X POST localhost:8000/orders -H 'Content-Type: application/json' -d '{\"item_id\":\"sku-1\",\"quantity\":1,\"fail_payment\":true}'`\n2. Wait ~5s for it to appear above.\n3. Scroll to **Step 2** (log panel) — find the ERROR log line, click its `traceid` field.\n4. You're now in Tempo viewing the full trace: order → inventory → payment, with the payment-gateway-call span marked failed.\n5. From any span, click its log icon to jump back to **Step 2** scoped to that span's logs.\n\nThat's the loop: metric → log → trace → back to metric. One trace_id stitches them together."
      }
    }
  ]
}
```

The closing `]` and `}` are root close — this is the last task on this dashboard.

- [ ] **Step 2: Verify**

Wait 30s, refresh. Expected:
- Intro markdown at top
- Metric panel (Step 1) with orders/min line. If exemplar storage is enabled and exemplars are flowing, you'll see tiny dots on the line. Hover one → tooltip shows trace_id.
- Logs panel (Step 2) populated with JSON-parsed log lines. Expanding any line reveals fields.
- Traces table (Step 3) showing recent traces.
- Service map (Step 4) showing nodes and edges.
- Try-this markdown at the bottom.

- [ ] **Step 3: Walk the correlation loop**

Trigger an error:
```bash
curl -X POST localhost:8000/orders -H "Content-Type: application/json" -d '{"item_id":"sku-1","quantity":1,"fail_payment":true}'
```

Wait 5s, refresh. Then:
1. In Step 2 (logs), find the latest ERROR line (from order-service or payment-service).
2. Expand it, locate the `traceid` field, click it.
3. Tempo should open in a side panel or new view showing the full trace waterfall.
4. From the trace view, click the "View logs for this span" icon (looks like a document icon) → Loki opens scoped to that span.

If any step fails: the `derivedFields` regex in `datasources.yaml` may need adjustment. Per CLAUDE.md it's set to `"traceid":"(\w+)"`. If your log JSON field is `otelTraceID` instead of `traceid`, that's the friction point — but `derivedFields` runs the regex against the raw log body, not the JSON-parsed fields, so the surface key in the JSON dump matters.

- [ ] **Step 4: Commit**

```bash
git add grafana/provisioning/dashboards/otel-correlation-demo.json
git commit -m "feat(grafana): complete OTel correlation demo dashboard"
```

---

## Task 4: Create `business-view.json` — skeleton + Row 1 (headline stats)

**Files:**
- Create: `grafana/provisioning/dashboards/business-view.json`

- [ ] **Step 1: Write skeleton + Row 1**

```json
{
  "uid": "otel-demo-business",
  "title": "Business / Product View",
  "tags": ["otel", "demo", "business"],
  "timezone": "browser",
  "schemaVersion": 38,
  "refresh": "30s",
  "time": { "from": "now-24h", "to": "now" },
  "templating": {
    "list": [{
      "name": "item_id", "type": "query",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "query": "label_values(demo_orders_total, item_id)",
      "label": "Item",
      "current": { "text": "All", "value": "$__all" },
      "includeAll": true, "multi": true, "refresh": 2
    }]
  },
  "panels": [
    {
      "id": 100, "type": "row", "title": "Headlines",
      "gridPos": { "x": 0, "y": 0, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 101, "type": "stat", "title": "Total orders",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 1, "w": 6, "h": 5 },
      "fieldConfig": { "defaults": { "unit": "short", "decimals": 0, "color": { "mode": "fixed", "fixedColor": "purple" } } },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "area" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum(increase(demo_orders_total[$__range]))",
        "legendFormat": "orders", "refId": "A", "instant": true
      }]
    },
    {
      "id": 102, "type": "stat", "title": "Total revenue",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 6, "y": 1, "w": 6, "h": 5 },
      "fieldConfig": { "defaults": { "unit": "currencyUSD", "decimals": 2, "color": { "mode": "fixed", "fixedColor": "green" } } },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "area" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum(increase(demo_payment_amount_dollars_sum[$__range]))",
        "legendFormat": "revenue", "refId": "A", "instant": true
      }]
    },
    {
      "id": 103, "type": "stat", "title": "Avg order value",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 1, "w": 6, "h": 5 },
      "fieldConfig": { "defaults": { "unit": "currencyUSD", "decimals": 2, "color": { "mode": "fixed", "fixedColor": "blue" } } },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum(increase(demo_payment_amount_dollars_sum[$__range])) / sum(increase(demo_payments_total{status=\"success\"}[$__range]))",
        "legendFormat": "AOV", "refId": "A", "instant": true
      }]
    },
    {
      "id": 104, "type": "stat", "title": "Conversion %",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 18, "y": 1, "w": 6, "h": 5 },
      "fieldConfig": {
        "defaults": {
          "unit": "percent", "decimals": 1,
          "thresholds": { "mode": "absolute", "steps": [
            { "color": "red", "value": null },
            { "color": "yellow", "value": 80 },
            { "color": "green", "value": 95 }
          ] }
        }
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "colorMode": "background", "graphMode": "none" },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "100 * sum(rate(demo_orders_total[$__range])) / (sum(rate(demo_orders_total[$__range])) + sum(rate(demo_order_errors_total[$__range])))",
        "legendFormat": "conv %", "refId": "A", "instant": true
      }]
    }
  ]
}
```

- [ ] **Step 2: Verify**

Wait 30s, refresh. Expected: 4 headline stat tiles with live numbers over the last 24h. AOV ~$50-$300 depending on which payment amounts the load-generator has produced.

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/business-view.json
git commit -m "feat(grafana): business view skeleton + headlines"
```

---

## Task 5: Business view Row 2 — Trends (3 timeseries)

**Files:**
- Modify: `grafana/provisioning/dashboards/business-view.json`

- [ ] **Step 1: Append Row 2**

```json
,
    {
      "id": 200, "type": "row", "title": "Trends",
      "gridPos": { "x": 0, "y": 6, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 201, "type": "timeseries", "title": "Orders per hour",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 7, "w": 8, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 10 }, "unit": "short", "color": { "mode": "fixed", "fixedColor": "purple" } } },
      "options": { "tooltip": { "mode": "single" }, "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum(rate(demo_orders_total[5m])) * 3600",
        "legendFormat": "orders/hr", "refId": "A"
      }]
    },
    {
      "id": 202, "type": "timeseries", "title": "Revenue per hour",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 8, "y": 7, "w": 8, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 2, "fillOpacity": 10 }, "unit": "currencyUSD", "color": { "mode": "fixed", "fixedColor": "green" } } },
      "options": { "tooltip": { "mode": "single" }, "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum(rate(demo_payment_amount_dollars_sum[5m])) * 3600",
        "legendFormat": "$/hr", "refId": "A"
      }]
    },
    {
      "id": 203, "type": "timeseries", "title": "Failure reasons (stacked)",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 16, "y": 7, "w": 8, "h": 8 },
      "fieldConfig": { "defaults": { "custom": { "lineWidth": 1, "fillOpacity": 70, "stacking": { "mode": "normal" } }, "unit": "reqpm", "color": { "mode": "palette-classic" } } },
      "options": { "tooltip": { "mode": "multi" }, "legend": { "displayMode": "list", "placement": "bottom" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (reason) (rate(demo_payment_failures_total[5m])) * 60",
        "legendFormat": "{{reason}}", "refId": "A"
      }]
    }
```

- [ ] **Step 2: Verify**

Refresh. Expected: 3 trend lines for orders/hr, revenue/hr, and stacked failure reasons.

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/business-view.json
git commit -m "feat(grafana): business view row 2 — trends"
```

---

## Task 6: Business view Row 3 — Per-item tables (3 tables)

**Files:**
- Modify: `grafana/provisioning/dashboards/business-view.json`

- [ ] **Step 1: Append Row 3**

```json
,
    {
      "id": 300, "type": "row", "title": "Per-item",
      "gridPos": { "x": 0, "y": 15, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 301, "type": "table", "title": "Top items by orders",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 16, "w": 8, "h": 10 },
      "fieldConfig": { "defaults": { "custom": { "align": "right" } } },
      "options": { "showHeader": true, "sortBy": [{ "displayName": "Value", "desc": true }] },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "topk(10, sum by (item_id) (increase(demo_orders_total[$__range])))",
        "legendFormat": "{{item_id}}", "refId": "A", "format": "table", "instant": true
      }],
      "transformations": [{ "id": "organize", "options": { "excludeByName": { "Time": true } } }]
    },
    {
      "id": 302, "type": "table", "title": "Top items by revenue",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 8, "y": 16, "w": 8, "h": 10 },
      "fieldConfig": { "defaults": { "unit": "currencyUSD", "custom": { "align": "right" } } },
      "options": { "showHeader": true, "sortBy": [{ "displayName": "Value", "desc": true }] },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "topk(10, sum by (item_id) (increase(demo_payment_amount_dollars_sum[$__range])))",
        "legendFormat": "{{item_id}}", "refId": "A", "format": "table", "instant": true
      }],
      "transformations": [{ "id": "organize", "options": { "excludeByName": { "Time": true } } }]
    },
    {
      "id": 303, "type": "table", "title": "Top items by payment failure",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 16, "y": 16, "w": 8, "h": 10 },
      "fieldConfig": { "defaults": { "custom": { "align": "right" } } },
      "options": { "showHeader": true, "sortBy": [{ "displayName": "Value", "desc": true }] },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "topk(10, sum by (item_id) (increase(demo_payment_failures_total[$__range])))",
        "legendFormat": "{{item_id}}", "refId": "A", "format": "table", "instant": true
      }],
      "transformations": [{ "id": "organize", "options": { "excludeByName": { "Time": true } } }]
    }
```

- [ ] **Step 2: Verify**

Refresh. Expected: 3 tables side-by-side, each with `item_id` and a numeric Value column. Tables sorted descending. The `$__range` evaluates to the dashboard's time range (24h by default).

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/business-view.json
git commit -m "feat(grafana): business view row 3 — per-item top-10 tables"
```

---

## Task 7: Business view Row 4 — Distribution (histogram + heatmap)

**Files:**
- Modify: `grafana/provisioning/dashboards/business-view.json`

- [ ] **Step 1: Append Row 4**

```json
,
    {
      "id": 400, "type": "row", "title": "Payment amount distribution",
      "gridPos": { "x": 0, "y": 26, "w": 24, "h": 1 }, "collapsed": false
    },
    {
      "id": 401, "type": "histogram", "title": "Distribution (last 5m)",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 0, "y": 27, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "currencyUSD", "color": { "mode": "fixed", "fixedColor": "purple" } } },
      "options": { "legend": { "displayMode": "hidden" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (le) (rate(demo_payment_amount_dollars_bucket[5m]))",
        "legendFormat": "{{le}}", "refId": "A", "format": "heatmap"
      }]
    },
    {
      "id": 402, "type": "heatmap", "title": "Amount distribution over time",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "x": 12, "y": 27, "w": 12, "h": 8 },
      "options": { "calculate": false, "cellGap": 1, "yAxis": { "axisLabel": "$" } },
      "targets": [{
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (le) (rate(demo_payment_amount_dollars_bucket[2m]))",
        "legendFormat": "{{le}}", "refId": "A", "format": "heatmap"
      }]
    }
  ]
}
```

The closing `]` and `}` are the dashboard's panels-array and root close — this is the LAST task.

- [ ] **Step 2: Verify**

Refresh. Expected:
- Histogram on left: bars showing how payment amounts cluster (mostly small amounts, some large)
- Heatmap on right: amount-vs-time view; horizontal bands light up depending on time of day

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/business-view.json
git commit -m "feat(grafana): business view row 4 — payment amount distribution"
```

---

## Task 8: Final cross-dashboard smoke test

- [ ] **Step 1: Walk Home → all 7 dashboards**

From Home, click every tile. Each should load:
- Ops Overview ✓
- Dev — Order ✓
- Dev — Inventory ✓
- Dev — Payment ✓
- OTel Correlation Demo ✓
- Business / Product View ✓
- Legacy (in subfolder) ✓

- [ ] **Step 2: Run the correlation loop end-to-end**

Trigger one of each scenario:
```bash
curl -X POST localhost:8000/orders -H "Content-Type: application/json" -d '{"item_id":"sku-1","quantity":1}'   # normal
curl -X POST localhost:8000/orders -H "Content-Type: application/json" -d '{"item_id":"sku-1","quantity":1,"fail_payment":true}'   # error
curl -X POST localhost:8000/orders -H "Content-Type: application/json" -d '{"item_id":"sku-1","quantity":1,"slow_query":true}'   # slow
```

On the Correlation Demo dashboard:
- All three requests appear in Step 2 logs
- Click the trace_id of the error → Tempo opens
- In Tempo, click a span's "go to logs" icon → Loki opens

On Business view:
- The total orders count went up by 3 (assuming `$__range` covers right now)

- [ ] **Step 3: Restart from scratch and confirm everything provisions clean**

```bash
docker compose down
docker compose up --build -d
sleep 90
```

Open http://localhost:3000. Expected:
- Lands on Home (env var still wired)
- All 7 dashboards present (6 in `OTel Demo` folder + 1 in `legacy/`)
- No "this dashboard is broken" errors in the Grafana sidebar

- [ ] **Step 4: No commit needed**

Plan 4 complete. The full dashboard redesign is shipped.

---

## Spec coverage (self-review)

- §6.6 OTel Correlation Demo: 6 panels (intro, metric w/ exemplars, log, trace, service map, call-to-action) ✓
- §6.7 Business view: 4 rows (headlines, trends, per-item, distribution) ✓
- §9 Prometheus exemplar storage: explicit decision task with both paths ✓
- §5.2 PromQL aggregation: every query uses `sum by (...)` ✓
- §5.4 datasource UIDs: prometheus / tempo / loki used explicitly ✓
- §5.5 metric inventory: all queries use verified metrics ✓
- §5.7 navigation: Home → all 7 reachable, verified in Task 8 ✓
