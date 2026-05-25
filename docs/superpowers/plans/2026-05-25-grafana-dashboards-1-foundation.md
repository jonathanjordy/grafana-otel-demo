# Foundation + Home Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up Grafana dashboard provisioning, move the legacy dashboard into a subfolder, verify the metric label inventory, and ship the Home landing page.

**Architecture:** All dashboard JSON lives under `grafana/provisioning/dashboards/` (the path already mounted by docker-compose). Subfolder `legacy/` holds the old dashboard. `foldersFromFilesStructure: true` makes Grafana mirror the directory tree as folders. Home is set as the default landing page via the `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH` env var on the grafana service.

**Tech Stack:** Grafana 10.3.0, Prometheus 2.50, Loki, Tempo 2.4.0, docker-compose.

**Spec:** [`../specs/2026-05-25-grafana-dashboards-redesign-design.md`](../specs/2026-05-25-grafana-dashboards-redesign-design.md)

**Deviation from spec §5.1:** Dashboards live under `grafana/provisioning/dashboards/` instead of `grafana/dashboards/` because docker-compose already mounts the former. This avoids touching the volume mount.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `grafana/provisioning/dashboards/dashboards.yaml` | modify | Enable `foldersFromFilesStructure`, keep path |
| `grafana/provisioning/dashboards/legacy/otel-demo-legacy.json` | move + edit | Existing legacy dashboard, retitled |
| `grafana/otel-demo-dashboard-template.json` | delete (via git mv) | Old location |
| `docker-compose.yml` | modify | Add `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH` env var |
| `grafana/provisioning/dashboards/home.json` | create | Landing dashboard |
| `docs/superpowers/plans/verification-notes.md` | create | Records metric/label verification results |

---

## Task 1: Inspect running stack and verify metric labels

This task is the gating check from spec §9. If `service_name` or `traces_spanmetrics_*` labels aren't what we expect, every subsequent plan needs adjusted query templates. Do this FIRST.

**Files:**
- Create: `docs/superpowers/plans/verification-notes.md`

- [ ] **Step 1: Start the stack**

Run from repo root:
```bash
docker compose up --build -d
```

Wait 60 seconds for the load-generator to produce traffic and for Tempo's metrics_generator to start writing span metrics to Prometheus.

- [ ] **Step 2: Confirm services are healthy**

Run:
```bash
docker compose ps
```

Expected: `order-service`, `inventory-service`, `payment-service`, `otel-collector`, `prometheus`, `tempo`, `loki`, `grafana`, `node-exporter`, `redis`, `postgres`, `load-generator` all show `Up` or `Up (healthy)`.

- [ ] **Step 3: Verify business metrics exist with `demo_` prefix**

Run:
```bash
curl -s 'http://localhost:9090/api/v1/label/__name__/values' | python -c "import json,sys; d=json.load(sys.stdin)['data']; [print(m) for m in d if m.startswith('demo_')]"
```

Expected output includes at minimum:
```
demo_orders_total
demo_order_errors_total
demo_order_duration_seconds_bucket
demo_order_duration_seconds_count
demo_order_duration_seconds_sum
demo_payments_total
demo_payment_failures_total
demo_payment_duration_seconds_bucket
demo_payment_amount_dollars_bucket
demo_inventory_cache_hits_total
demo_inventory_cache_misses_total
demo_inventory_lookup_duration_seconds_bucket
demo_http_server_duration_milliseconds_bucket
demo_http_server_duration_milliseconds_count
demo_http_client_duration_milliseconds_bucket
```

If any custom-business metric is missing: stop, investigate. If `demo_http_server_*` is missing, check that the instrumentation export interval has had time to fire (wait another 30s) — auto-instrumentation metrics are batched.

- [ ] **Step 4: Verify Tempo span metrics exist**

Run:
```bash
curl -s 'http://localhost:9090/api/v1/label/__name__/values' | python -c "import json,sys; d=json.load(sys.stdin)['data']; [print(m) for m in d if m.startswith('traces_')]"
```

Expected:
```
traces_service_graph_request_failed_total
traces_service_graph_request_server_seconds_bucket
traces_service_graph_request_total
traces_spanmetrics_calls_total
traces_spanmetrics_latency_bucket
traces_spanmetrics_latency_count
traces_spanmetrics_latency_sum
```

If none of these are present, Tempo's metrics_generator isn't writing to Prometheus. Check `grafana/tempo/config.yaml:26-39` and the Prometheus `--web.enable-remote-write-receiver` flag.

- [ ] **Step 5: Verify `service_name` label is attached to business metrics**

Run:
```bash
curl -s 'http://localhost:9090/api/v1/series?match[]=demo_orders_total' | python -m json.tool
```

Expected output shows each series with a `service_name` label set to `order-service`. Also note `job` (will be `otel-collector` and `order-service`, since the metric is scraped from two paths) and `instance`.

If `service_name` is absent: fall back is `job=~"order-service.*"`. Note this in the verification file for future plans.

- [ ] **Step 6: Verify Tempo span metric label is `service` (not `service_name`)**

Run:
```bash
curl -s 'http://localhost:9090/api/v1/series?match[]=traces_spanmetrics_calls_total' | python -m json.tool | head -40
```

Expected: each series has a `service` label (e.g. `"service": "order-service"`) and a `span_name` label. If it's actually `service_name` in your Tempo version, note it — the dev dashboards' span-metric panels need adjustment.

- [ ] **Step 7: Verify Loki has JSON-parseable logs with the expected fields**

Open http://localhost:3000 (Grafana, anonymous admin). Go to Explore → Loki datasource. Run query:
```
{exporter="OTLP"} | json
```

Expected: log lines with parsed fields including `severity`, `otelTraceID`, `otelSpanID`, `otelServiceName`, `body`. If `severity` is in a different case (e.g. `Severity` or `severityText`), note it — every Loki query in subsequent plans uses `severity="ERROR"`.

- [ ] **Step 8: Record verification results**

Create `docs/superpowers/plans/verification-notes.md` with the contents:

```markdown
# Dashboard verification notes — recorded YYYY-MM-DD

## Metric label verification (Plan 1, Task 1)

- Business metrics `demo_*` present: YES / NO (list missing if any)
- HTTP server metrics `demo_http_server_duration_milliseconds_*` present: YES / NO
- HTTP client metrics `demo_http_client_duration_milliseconds_*` present: YES / NO
- Tempo span metrics `traces_spanmetrics_*` present: YES / NO
- Tempo service graph metrics `traces_service_graph_*` present: YES / NO

## Label names

- `service_name` on business metrics: YES / NO (if NO, use `job=~"<service>.*"` instead)
- `service` on `traces_spanmetrics_*`: YES / NO (if NO, label is: ____)
- Loki `severity` field present after `| json`: YES / NO (if differently named: ____)

## Adjustments needed in later plans

(List any query template substitutions needed)
```

Fill in actual results from steps 3–7.

- [ ] **Step 9: Commit verification notes**

```bash
git add docs/superpowers/plans/verification-notes.md
git commit -m "chore: record metric/label verification results for dashboard redesign"
```

---

## Task 2: Move legacy dashboard into a subfolder

**Files:**
- Move: `grafana/otel-demo-dashboard-template.json` → `grafana/provisioning/dashboards/legacy/otel-demo-legacy.json`
- Edit: the moved file's `"title"` field

- [ ] **Step 1: Create the legacy subdirectory**

```bash
mkdir -p grafana/provisioning/dashboards/legacy
```

- [ ] **Step 2: Move the file using git mv to preserve history**

```bash
git mv grafana/otel-demo-dashboard-template.json grafana/provisioning/dashboards/legacy/otel-demo-legacy.json
```

- [ ] **Step 3: Update the dashboard title**

Edit `grafana/provisioning/dashboards/legacy/otel-demo-legacy.json` line 3:

Change:
```json
"title": "OTel Demo — Order System",
```

To:
```json
"title": "OTel Demo — Legacy",
```

Also update the `"uid"` from `"otel-demo-dashboard"` to `"otel-demo-legacy"` (line 2) so it doesn't collide with anything new.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: move legacy dashboard into provisioning/dashboards/legacy/"
```

---

## Task 3: Enable subfolder provisioning

**Files:**
- Modify: `grafana/provisioning/dashboards/dashboards.yaml`

- [ ] **Step 1: Edit the provisioning config**

Replace the entire contents of `grafana/provisioning/dashboards/dashboards.yaml` with:

```yaml
apiVersion: 1

providers:
  - name: "demo-dashboards"
    orgId: 1
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
      foldersFromFilesStructure: true
```

The only change is `foldersFromFilesStructure: false` → `true`. This makes Grafana mirror the on-disk directory structure as Grafana folders, so `legacy/otel-demo-legacy.json` shows up under a "legacy" folder in the Grafana UI.

- [ ] **Step 2: Reload Grafana and verify**

```bash
docker compose restart grafana
sleep 10
```

Open http://localhost:3000 → Dashboards. Expected: a folder named `legacy` containing `OTel Demo — Legacy`. No dashboards at top level yet.

- [ ] **Step 3: Commit**

```bash
git add grafana/provisioning/dashboards/dashboards.yaml
git commit -m "feat(grafana): enable subfolder provisioning for dashboards"
```

---

## Task 4: Set Home as the default landing page

**Files:**
- Modify: `docker-compose.yml` (grafana service, `environment:` block, around lines 169–172)

- [ ] **Step 1: Add the env var**

In `docker-compose.yml`, find the `grafana:` service block (around line 165) and add one line to the `environment:` list. After this edit the block looks like:

```yaml
  grafana:
    image: grafana/grafana:10.3.0
    ports:
      - "3000:3000"   # Open http://localhost:3000  (admin / admin)
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
      - GF_AUTH_DISABLE_LOGIN_FORM=false
      - GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/etc/grafana/provisioning/dashboards/home.json
```

The path uses the in-container mount point.

- [ ] **Step 2: Don't restart yet**

Home.json doesn't exist yet. Restarting now would log an error. Task 5 creates it; restart happens at the end of that task.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(grafana): set Home as default landing dashboard"
```

---

## Task 5: Create the Home dashboard

**Files:**
- Create: `grafana/provisioning/dashboards/home.json`

- [ ] **Step 1: Write the dashboard JSON**

Create `grafana/provisioning/dashboards/home.json` with:

```json
{
  "uid": "otel-demo-home",
  "title": "OTel Demo — Home",
  "tags": ["otel", "demo", "home"],
  "timezone": "browser",
  "schemaVersion": 38,
  "refresh": "30s",
  "time": { "from": "now-15m", "to": "now" },
  "panels": [
    {
      "id": 1,
      "type": "text",
      "title": "",
      "gridPos": { "x": 0, "y": 0, "w": 24, "h": 4 },
      "options": {
        "mode": "markdown",
        "content": "# OTel Demo — Order System\n\nThree Python/FastAPI microservices instrumented with OpenTelemetry. Pick a dashboard below based on what you need to see.\n\n*Default refresh: 30s. Each tile shows one live number teaser.*"
      }
    },
    {
      "id": 2,
      "type": "stat",
      "title": "Ops Overview",
      "description": "Health-first, RED + saturation. Designed for on-call.",
      "gridPos": { "x": 0, "y": 4, "w": 6, "h": 6 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "decimals": 1,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 1 },
              { "color": "red", "value": 5 }
            ]
          }
        }
      },
      "options": {
        "reduceOptions": { "calcs": ["lastNotNull"] },
        "colorMode": "background",
        "textMode": "value_and_name",
        "graphMode": "none"
      },
      "links": [
        {
          "title": "Open Ops Overview",
          "url": "/d/otel-demo-ops/ops-overview",
          "targetBlank": false
        }
      ],
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "100 * sum(rate(demo_order_errors_total[5m])) / (sum(rate(demo_orders_total[5m])) + sum(rate(demo_order_errors_total[5m])))",
          "legendFormat": "error %",
          "refId": "A"
        }
      ]
    },
    {
      "id": 3,
      "type": "stat",
      "title": "Dev — Order",
      "description": "Debug order-service: RED, endpoints, deps, logs, traces.",
      "gridPos": { "x": 6, "y": 4, "w": 6, "h": 6 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "decimals": 2,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 0.5 },
              { "color": "red", "value": 2 }
            ]
          }
        }
      },
      "options": {
        "reduceOptions": { "calcs": ["lastNotNull"] },
        "colorMode": "background",
        "textMode": "value_and_name",
        "graphMode": "none"
      },
      "links": [
        { "title": "Open Dev — Order", "url": "/d/otel-demo-dev-order/dev-order-service", "targetBlank": false }
      ],
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "histogram_quantile(0.95, sum by(le) (rate(demo_order_duration_seconds_bucket[5m])))",
          "legendFormat": "p95 latency",
          "refId": "A"
        }
      ]
    },
    {
      "id": 4,
      "type": "stat",
      "title": "Dev — Inventory",
      "description": "Debug inventory-service: cache, lookup, deps, logs, traces.",
      "gridPos": { "x": 12, "y": 4, "w": 6, "h": 6 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "decimals": 1,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "red", "value": null },
              { "color": "yellow", "value": 50 },
              { "color": "green", "value": 80 }
            ]
          }
        }
      },
      "options": {
        "reduceOptions": { "calcs": ["lastNotNull"] },
        "colorMode": "background",
        "textMode": "value_and_name",
        "graphMode": "none"
      },
      "links": [
        { "title": "Open Dev — Inventory", "url": "/d/otel-demo-dev-inventory/dev-inventory-service", "targetBlank": false }
      ],
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "100 * sum(rate(demo_inventory_cache_hits_total[5m])) / sum(rate(demo_inventory_cache_hits_total[5m]) + rate(demo_inventory_cache_misses_total[5m]))",
          "legendFormat": "cache hit %",
          "refId": "A"
        }
      ]
    },
    {
      "id": 5,
      "type": "stat",
      "title": "Dev — Payment",
      "description": "Debug payment-service: failures, amounts, deps, logs, traces.",
      "gridPos": { "x": 18, "y": 4, "w": 6, "h": 6 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "decimals": 1,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 5 },
              { "color": "red", "value": 15 }
            ]
          }
        }
      },
      "options": {
        "reduceOptions": { "calcs": ["lastNotNull"] },
        "colorMode": "background",
        "textMode": "value_and_name",
        "graphMode": "none"
      },
      "links": [
        { "title": "Open Dev — Payment", "url": "/d/otel-demo-dev-payment/dev-payment-service", "targetBlank": false }
      ],
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "100 * sum(rate(demo_payment_failures_total[5m])) / (sum(rate(demo_payments_total[5m])) + sum(rate(demo_payment_failures_total[5m])))",
          "legendFormat": "failure %",
          "refId": "A"
        }
      ]
    },
    {
      "id": 6,
      "type": "stat",
      "title": "OTel Correlation Demo",
      "description": "How metrics ↔ logs ↔ traces link together.",
      "gridPos": { "x": 0, "y": 10, "w": 8, "h": 6 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "decimals": 0,
          "color": { "mode": "fixed", "fixedColor": "blue" }
        }
      },
      "options": {
        "reduceOptions": { "calcs": ["lastNotNull"] },
        "colorMode": "background",
        "textMode": "value_and_name",
        "graphMode": "none"
      },
      "links": [
        { "title": "Open Correlation Demo", "url": "/d/otel-demo-correlation/otel-correlation-demo", "targetBlank": false }
      ],
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "sum(rate(traces_spanmetrics_calls_total[5m])) * 60",
          "legendFormat": "spans/min",
          "refId": "A"
        }
      ]
    },
    {
      "id": 7,
      "type": "stat",
      "title": "Business / Product",
      "description": "Orders, revenue, conversion, top items.",
      "gridPos": { "x": 8, "y": 10, "w": 8, "h": 6 },
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "reqpm",
          "decimals": 0,
          "color": { "mode": "fixed", "fixedColor": "purple" }
        }
      },
      "options": {
        "reduceOptions": { "calcs": ["lastNotNull"] },
        "colorMode": "background",
        "textMode": "value_and_name",
        "graphMode": "none"
      },
      "links": [
        { "title": "Open Business View", "url": "/d/otel-demo-business/business-view", "targetBlank": false }
      ],
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "sum(rate(demo_orders_total[1m])) * 60",
          "legendFormat": "orders/min",
          "refId": "A"
        }
      ]
    },
    {
      "id": 8,
      "type": "text",
      "title": "Legacy",
      "gridPos": { "x": 16, "y": 10, "w": 8, "h": 6 },
      "options": {
        "mode": "markdown",
        "content": "### Legacy dashboard\n\nThe original single-page dashboard is preserved for reference.\n\n[Open OTel Demo — Legacy](/d/otel-demo-legacy/otel-demo-legacy)"
      }
    }
  ]
}
```

Note: tile UIDs in the `links` array (`otel-demo-ops`, `otel-demo-dev-order`, etc.) must match the UIDs you'll set in plans 2–4. They're listed in spec §6 panel headers. If a target dashboard doesn't exist yet, the link 404s — that's fine until the other plans land.

- [ ] **Step 2: Restart Grafana and verify**

```bash
docker compose restart grafana
sleep 10
```

Open http://localhost:3000. Expected: you land directly on the Home dashboard (because the env var is set). You should see:
- The markdown title at top
- Four tiles in row 1 (Ops, Dev-Order, Dev-Inventory, Dev-Payment), each showing a live number
- Three tiles in row 2 (Correlation, Business, Legacy)
- Tiles 2–7 should be colored according to their thresholds (e.g. Cache Hit % green if >80%, error % green if <1%)
- Clicking each tile attempts to navigate to its target dashboard (only Legacy works currently)

If you land on a different page: check `docker compose logs grafana | grep -i "home"` for path errors. The path MUST be the in-container path `/etc/grafana/provisioning/dashboards/home.json`, not a host path.

- [ ] **Step 3: Confirm no duplicate-legend issue on Home tiles**

Each stat panel displays a single number, so there's no legend to duplicate — but verify the query result isn't "N/A". If "N/A", the metric isn't producing data yet (load-generator needs more runtime) or the query is wrong.

- [ ] **Step 4: Commit**

```bash
git add grafana/provisioning/dashboards/home.json
git commit -m "feat(grafana): add Home landing dashboard"
```

---

## Task 6: Final smoke test

- [ ] **Step 1: Full restart from a clean slate**

```bash
docker compose down
docker compose up -d
sleep 60
```

The `-v` flag is intentionally NOT used here — we want to preserve Prometheus/Tempo/Loki data for confidence, since the verification notes file is per-environment.

- [ ] **Step 2: Open http://localhost:3000**

Expected:
- Lands on Home dashboard
- Home shows live numbers on all 6 stat tiles
- Sidebar → Dashboards shows `OTel Demo — Home` at top, and a `legacy` folder containing `OTel Demo — Legacy`
- Other dashboard links from Home 404 (expected; they're built in plans 2–4)

- [ ] **Step 3: Mark Plan 1 complete**

If everything looks right, no commit needed — this task is verification only.

---

## Spec coverage (self-review)

- Spec §4 (audience list): tile per dashboard ✓
- Spec §5.1 (file layout): adjusted to `grafana/provisioning/dashboards/` — noted in plan header ✓
- Spec §5.4 (datasource UIDs): home.json uses `prometheus` UID ✓
- Spec §5.7 (default home): env var added ✓
- Spec §6.1 (Home dashboard): all 8 panels present, queries match ✓
- Spec §9 risk: `service_name` label, span-metric label name, Loki severity — all checked in Task 1 ✓
