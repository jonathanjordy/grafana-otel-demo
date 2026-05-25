# Grafana dashboards

Seven dashboards built from code analysis of this repo's OTel demo. Designed to fix the duplicate-legend problem in `../otel-demo-dashboard-template.json` and split one cluttered dashboard into focused audience-specific views.

## What's here

| File | Audience | Answers |
|---|---|---|
| `home.json` | anyone | "What is this and where do I go?" |
| `ops-overview.json` | on-call, ops | "Is the system healthy right now?" |
| `dev-order.json` | order-service developer | "Why is my service slow / failing?" |
| `dev-inventory.json` | inventory-service developer | (same) |
| `dev-payment.json` | payment-service developer | (same) |
| `otel-correlation-demo.json` | OTel learners | "How do metrics, logs, traces link together?" |
| `business-view.json` | PM / business | "Throughput, conversion, top items, revenue" |

## Importing

**Option A — Grafana UI** (one at a time):
1. Sidebar → Dashboards → New → Import
2. Upload JSON file, or paste contents
3. Pick your datasources: `prometheus`, `loki`, `tempo` (must match the UIDs in your Grafana)
4. Repeat per file

**Option B — Provisioning** (bulk):
Drop all `.json` files into your Grafana provisioning dashboards folder (e.g. `/etc/grafana/provisioning/dashboards/`) and ensure the provider yaml has `foldersFromFilesStructure: true`. Restart Grafana.

## Datasource UID assumptions

The dashboards reference datasources by these UIDs (matching this repo's `grafana/provisioning/datasources/datasources.yaml`):
- `prometheus` — Prometheus
- `loki` — Loki
- `tempo` — Tempo

If your deployed Grafana uses different UIDs, do a find-replace in each file before importing, OR pick the right datasource during the import wizard.

## Label assumptions (verify against your stack)

Queries assume the following label conventions. If your collector / SDK versions produce different names, edit the affected queries.

| Assumption | Where used | If different |
|---|---|---|
| `service_name` label on `demo_*` and `demo_http_*` metrics | dev-order/inventory/payment endpoint breakdown panels | replace `service_name="X"` with `job=~"X.*"` |
| `service` label on `traces_spanmetrics_*` and `traces_service_graph_*` | dev dashboards' "Dependencies" row | replace with whatever Tempo emits (often `service_name`) |
| `severity` field after `\| json` in Loki | ops-overview & dev dashboards' log panels, correlation demo | replace `severity="ERROR"` with `severity_text="ERROR"` or `level="ERROR"` depending on your logs |
| `otelServiceName` field after `\| json` | dev dashboards' log panels | replace with `serviceName` or whatever your JSON-parsed log emits |
| Prometheus metric namespace prefix `demo_` | every business-metric query | This is set by `otel-collector/config.yaml` (`namespace: demo`). If your collector uses a different namespace or none at all, find-replace `demo_` → your prefix (or empty). |
| HTTP histogram name `demo_http_server_duration_milliseconds_*` | dev dashboards' endpoint breakdown | Newer FastAPIInstrumentor versions emit `http_server_request_duration_seconds_*` instead (and in **seconds**, not ms). If so, change both the name and the unit (`"ms"` → `"s"`). |

To check your stack quickly:
```
# What demo_ metrics exist?
curl -s 'http://<prometheus>/api/v1/label/__name__/values' | jq '.data[] | select(startswith("demo_"))'

# What labels does demo_orders_total have?
curl -s 'http://<prometheus>/api/v1/series?match[]=demo_orders_total' | jq

# What labels does traces_spanmetrics_calls_total have?
curl -s 'http://<prometheus>/api/v1/series?match[]=traces_spanmetrics_calls_total' | jq
```

## Key design choices

**Duplicate-legend fix.** The original dashboard's legends showed `p99 p99 p99 p99` etc. because PromQL queries lacked aggregation. Every query here wraps in `sum by (...)` or `sum(...)`, which collapses the `job`/`instance` dimensions that the same metric arrives with via two scrape paths (collector + direct).

**Visual conventions:**
- Service colors: order=purple, inventory=green, payment=red
- Status: success=green, warning=yellow, error=red, latency=blue
- Tooltip: `multi` mode everywhere
- Legend: short labels only, units on the axis (not in the legend)

**Cross-signal navigation** relies on the datasource configuration already shipped in this repo:
- Tempo → Loki via `tracesToLogsV2`
- Loki → Tempo via `derivedFields` regex on `"traceid":"(\w+)"`
- Prometheus → Tempo via `exemplarTraceIdDestinations`

The correlation demo's exemplar dots additionally need Prometheus running with `--enable-feature=exemplar-storage`. Without that flag, dots won't appear but everything else still works.

## Related docs

- Design spec: [`../../docs/superpowers/specs/2026-05-25-grafana-dashboards-redesign-design.md`](../../docs/superpowers/specs/2026-05-25-grafana-dashboards-redesign-design.md)
- Implementation plans (kept for reference, not required to use the dashboards): [`../../docs/superpowers/plans/`](../../docs/superpowers/plans/)
- Legacy dashboard (original single-page): [`../otel-demo-dashboard-template.json`](../otel-demo-dashboard-template.json)
