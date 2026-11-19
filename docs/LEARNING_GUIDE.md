# Observability learning guide

This guide follows one request from the order API through inventory and explains which component owns each signal.

## 1. Generate one request

The Java agent instruments Spring MVC and its HTTP client automatically. It starts a server span for `POST /orders`, injects W3C trace context into the outbound HTTP request, and exports telemetry using OTLP. The order handler also creates the `orders.submit` span and increments `orders.accepted`.

FastAPI instrumentation extracts that trace context and starts the Python server span. The handler creates `inventory.stockout_risk.predict`, adds model metadata, and records inference duration and outcome. The result is returned to Java, so these spans should share a trace ID.

## 2. Follow the trace

Both services send OTLP to the Collector on port 4317. The Collector batches telemetry and forwards spans to Jaeger. In Jaeger, select `orders` or `inventory`, open a recent trace, and inspect parent/child timing. A slow inventory request should show the added time inside the Python server span; a failed request should carry an error status.

## 3. Follow the metrics

The Collector converts received OpenTelemetry metrics into a Prometheus scrape endpoint on port 9464. Prometheus scrapes that endpoint every 10 seconds. It separately scrapes node-exporter and cAdvisor for system metrics. Grafana has provisioned data sources for Prometheus and Jaeger.

Example PromQL queries:

```promql
sum by (service_name) (http_server_request_duration_seconds_count)
```

```promql
sum by (service_name) (http_server_request_duration_seconds_count{http_response_status_code=~"5.."})
```

```promql
histogram_quantile(0.95, sum by (le) (rate(inventory_stockout_risk_inference_duration_milliseconds_bucket[5m])))
```

Open Prometheus' **Status → Targets** page first if panels are empty. App metric names can be normalized by the Collector/Prometheus translation layer; use the metrics browser to inspect the exact exported name and labels for the installed versions.

## 4. Distinguish application and system health

- Liveness answers whether the process should be restarted if it stops responding.
- Readiness answers whether the inventory model is available to serve requests.
- Application metrics describe request and business behavior.
- node-exporter/cAdvisor metrics describe the Linux environment that runs Docker. On macOS, Docker Desktop runs containers in a Linux VM, so these are VM signals rather than direct macOS hardware telemetry. cAdvisor has access to Docker Desktop's daemon socket for per-container resource metrics; depending on Docker Desktop's runtime, dashboard labels may use container IDs.

## 5. Talk through an incident

1. Notice the elevated p95 latency or 5xx rate in Grafana/Prometheus.
2. Narrow the issue to `inventory` using service/route labels.
3. Open a corresponding trace in Jaeger and compare Java and Python span durations.
4. Check whether inference time or the simulated wait dominates the trace.
5. Use container metrics to see whether resource pressure coincides with the slowdown.

This sequence demonstrates the practical value of correlated metrics and traces. It also makes clear that an observed correlation is a clue to investigate, not proof of cause.
