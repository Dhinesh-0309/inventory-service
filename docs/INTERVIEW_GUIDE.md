# Observable Order Platform: interview guide

This document explains what this project actually does, how its telemetry flows, how to demo it, and how to discuss its limitations honestly. Use the **interview answer** sections as a starting point; put them in your own words rather than memorizing them.

## 1. The project in one sentence

This is a local, Docker Compose based microservice demo: a Java/Spring Boot order API calls a Python/FastAPI inventory API with a small scikit-learn stockout-risk model, while OpenTelemetry sends correlated traces and metrics to Jaeger and Prometheus/Grafana.

## 2. The architecture

```text
curl / traffic generator
          |
          | POST /orders
          v
  Java orders service  ---- HTTP + trace context ----> Python inventory service
    Spring Boot                                        FastAPI + sklearn model
          |                                                   |
          +---- OTLP traces and metrics ----------------------+
                                  |
                        OpenTelemetry Collector
                          /                 \
                  traces to Jaeger      Prometheus exporter
                                              ^
                                              | scrape every 10s
                           Prometheus <-------+
                              ^
                              | scrapes
                   node-exporter and cAdvisor
                              |
                           Grafana
                 dashboards / data sources
```

The Java and Python services are independent processes and containers, joined by the Compose network. Inside that network, Compose DNS resolves `inventory` to the Python container. The host ports are for local access: orders `8080`, inventory `8000`, Prometheus `9090`, Grafana `3000`, Jaeger UI `16686`, cAdvisor `8081`, and node-exporter `9100`.

### Walk one request through the system

1. A client sends `POST /orders` to Spring Boot.
2. The OpenTelemetry Java agent creates an HTTP server span and captures framework/runtime telemetry. It also instruments the outbound Java HTTP client.
3. `OrderController` validates the SKU and quantity, starts a custom `orders.submit` span, and adds order attributes.
4. Java calls `POST /inventory/check`, passing the inventory inputs and W3C trace context. The outbound HTTP span is a child of the order span.
5. FastAPI instrumentation extracts that context and starts the inventory server span. The handler checks the demo stock level and starts `inventory.stockout_risk.predict` around model inference.
6. The Python service returns availability plus risk probability and label. Java increments `orders.accepted` or `orders.rejected` and returns an order response.
7. Each SDK/agent exports telemetry over OTLP to the Collector. The Collector batches it, sends traces to Jaeger, and exposes metrics on port `9464` for Prometheus to scrape.
8. Prometheus also scrapes itself, node-exporter, and cAdvisor. Grafana queries Prometheus for metrics and Jaeger for traces.

The key point is correlation: the services propagate one trace ID across the HTTP boundary. A trace lets you inspect the individual request; metrics let you see aggregate behavior over many requests.

## 3. Telemetry: what each signal answers

### Metrics

Metrics are numeric time series aggregated over time. They answer questions like “Are errors increasing?”, “What is p95 latency?”, or “How many high-risk predictions occurred?”

**Automatic metrics:** the Java agent and FastAPI instrumentation produce HTTP server duration/count metrics and runtime/process metrics. The Collector translates OTLP metrics into Prometheus exposition format. Prometheus polls that endpoint every 10 seconds; it does not receive application metrics by scraping the application endpoint directly.

**Custom business metrics:**

- Java `orders.accepted` and `orders.rejected` counters count successful inventory decisions, split by availability outcome.
- Python `inventory.stockout_risk.predictions` counts completed inference attempts with a bounded `risk` attribute (`low`, `medium`, `high`, or `error`).
- Python `inventory.stockout_risk.errors` counts inference errors with a bounded reason.
- Python `inventory.stockout_risk.inference.duration` is a histogram of model inference time in milliseconds.

Prometheus normalizes names. For example, `orders.accepted` appears as `orders_accepted_total`; the Python histogram appears as `inventory_stockout_risk_inference_duration_milliseconds_*`.

### Histograms and percentiles

A histogram records observations into buckets plus count and sum. Prometheus can combine bucket counts across replicas and estimate a percentile with `histogram_quantile`. Do not average per-instance p95 values; aggregate the buckets first. A percentile needs enough samples and a time window containing traffic, which is why the demo sends a traffic burst and uses a five-minute rate window.

### Traces and spans

A trace is the end-to-end record for one request. A span is one timed operation within that trace. The server spans show the inbound request, the client span shows the dependency call, and the custom Python span isolates model inference. Trace attributes help explain one request; avoid using high-cardinality or sensitive values in metrics labels.

W3C Trace Context carries `traceparent` across the service boundary. This is why Jaeger can show the Java and Python operations in one trace instead of as unrelated requests.

### Logs

There is no centralized log backend in this version. Spring logs and Uvicorn logs go to container stdout/stderr and can be inspected with `docker compose logs orders inventory`. The Collector's `debug` exporter logs telemetry summaries for learning. It is not an application log database.

### Health checks

- Liveness asks whether a process is alive and should keep running.
- Readiness asks whether a service is ready to handle requests. Python readiness checks that the local model exists; Java uses Spring Boot Actuator readiness.
- Compose health status is separate from Prometheus metrics. The configured `depends_on` entries order container starts; they do not express a full readiness dependency condition.
- Inventory becoming unavailable makes an order fail, but it does not make the order service's own process liveness fail. This separation is intentional: a dependency problem is not necessarily a reason to restart the caller.

## 4. How to run the demo

From Terminal:

```sh
cd /Users/dp/Documents/observability-project
docker compose up -d --build
docker compose ps
```

Wait for `orders` and `inventory` to show healthy. Send one request:

```sh
curl -sS http://localhost:8080/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-42","quantity":2,"dailyDemand":8,"onHand":40,"leadDays":4,"demandVolatility":2}'
```

Then generate a baseline:

```sh
bash scripts/generate-traffic.sh
```

In Grafana, open **Observable Order Platform**. In Jaeger, search for service `orders` and open a recent trace. In Prometheus, start with these queries:

```promql
sum by (service_name) (rate(http_server_request_duration_seconds_count[1m]))
```

```promql
histogram_quantile(0.95, sum by (service_name, le) (rate(http_server_request_duration_seconds_bucket[5m])))
```

```promql
sum by (service_name) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m]))
```

```promql
sum by (risk) (inventory_stockout_risk_predictions_total)
```

```promql
container_memory_working_set_bytes{id=~"/docker/.*"}
```

After a request, wait 10–15 seconds for metric export and scrape. If a graph is empty, widen the time range, send more traffic, and check Prometheus **Status → Targets**.

## 5. Repeatable experiments and what you should see

### Baseline traffic

Run `bash scripts/generate-traffic.sh`. Request rate and counters rise; a representative sample of traces appears in Jaeger. This is the control condition for comparisons.

### Model input changes

Submit one order with low demand, high on-hand stock, and short lead time; then submit another with high demand, low stock, long lead time, and high volatility. Compare `stockoutRisk` and `riskLabel` in the response, the `ml.*` attributes on the inference span, and the Prometheus prediction count grouped by `risk`.

The classifier is trained deterministically from synthetic data when the inventory service starts. It demonstrates how to observe inference; it is not a validated demand forecasting model.

### Business rejection

Request more than the demo stock level for `SKU-42` (80 units), while staying below the input limit of 10,000. The order API returns an order with status `rejected`; this is a business outcome, not an HTTP 5xx. `orders.rejected` should increase.

### Slow dependency

Set inventory delay to 900 ms:

```sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":900,"fail":false}'
```

Send orders again. The request and Python server span should get longer. The delay is deliberately before the model inference span, so the inference histogram should not include that artificial wait. Reset it afterward with `{"delayMs":0,"fail":false}`.

### Dependency failure

Set failure mode:

```sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":0,"fail":true}'
```

Orders should receive an HTTP `502` because inventory returned an error. Look for a rise in 5xx request rate and an error trace in Jaeger. Since inventory fails before inference, no model prediction is produced for that request. Reset immediately with `{"delayMs":0,"fail":false}`.

### Resource pressure

Use the traffic generator and inspect `container_memory_working_set_bytes` or `node_cpu_seconds_total`. cAdvisor and node-exporter describe Docker Desktop's Linux VM/container environment; they are not direct measurements of macOS hardware.

## 6. Interview-ready explanations

### “Tell me about this project.” (about 30 seconds)

> I built a local microservice observability lab with a Spring Boot order API calling a FastAPI inventory service. The Python service runs a small local stockout-risk model. I instrumented automatic HTTP/runtime telemetry and custom business/model metrics with OpenTelemetry, used a Collector to route traces to Jaeger and expose metrics for Prometheus, and built a Grafana dashboard. I can generate normal traffic and inject inventory latency or errors, then correlate aggregate metrics with a request trace to see where the time or failure occurred.

### “Why a Collector?”

> It gives the application services a stable OTLP destination and separates instrumentation from backend-specific delivery. The Collector receives telemetry, batches it, sends traces to Jaeger, and exposes metrics in Prometheus format. In a larger deployment, I could change routing, filtering, or backends centrally without rewriting each service's instrumentation.

### “Why both metrics and traces?”

> Metrics are efficient for trends and alert conditions across many requests, but they do not retain every request's path. Traces show the sequence and timing for one request, but are more expensive and are not the best way to calculate fleet-wide rates. I use a metric to detect a latency or error change and a trace to investigate an example.

### “Why use a histogram?”

> Request and inference times are distributions. Histograms let Prometheus aggregate bucket counts across instances and estimate p95/p99. A mean can hide a slow tail, and averaging separate percentiles is mathematically misleading.

### “How do you keep metrics cardinality controlled?”

> I use bounded dimensions such as service, route, status, and the three risk labels. I avoid order IDs, arbitrary SKUs, customer IDs, and raw URLs as metric labels. High-cardinality details belong in trace attributes only when appropriate, because they still affect trace storage and privacy.

### “How did you simulate an incident?”

> The inventory service has a local behavior control for a delay or a 503. With delay enabled, the order request rate can stay similar while latency rises; I compare the Python server span and overall p95. With failure enabled, the order API maps the downstream failure to 502, so I look for a 5xx increase and inspect the failed trace. Then I reset the behavior and compare against baseline.

### “What are the limitations?”

> This is a learning demo, not a production commerce system. It has no database, durable order state, authentication, retries, circuit breaker, or alert manager. The model uses synthetic data and is not production forecasting. Telemetry storage is local and ephemeral. The Java-to-Python JSON handling is intentionally small and hand-coded; in production I would use a standard typed serializer, explicit connection/read timeouts, and contract tests. Docker Desktop metrics describe its Linux VM, not macOS hardware.

## 7. What is implemented versus what could be next

**Implemented:** the two HTTP services; synthetic model; readiness/liveness endpoints; automatic HTTP/runtime instrumentation; custom counters and histogram; trace propagation; Collector pipelines; Prometheus scraping; provisioned Grafana data sources/dashboard; Jaeger UI; load generator; delay/failure controls; node-exporter and cAdvisor metrics.

**Not implemented yet:** persistent orders/inventory, authentication, centralized application logs, alert rules/Alertmanager, service-level objectives, retries/timeouts/circuit breaker, trace-to-metric exemplar links, deployment to Kubernetes/cloud, and model evaluation on real labeled data. Treat these as future work rather than claiming they already exist.

## 8. Source-code map

- `compose.yaml` — services, networks, ports, health checks, volumes, and Docker socket access for cAdvisor.
- `services/orders-java/src/main/java/dev/observabilitylab/orders/OrderController.java` — validation, outbound inventory call, custom spans, business counters, response mapping, and error handling.
- `services/orders-java/src/main/resources/application.properties` — Spring app name, Actuator probes, and inventory URL.
- `services/orders-java/Dockerfile` — Maven build and Java agent runtime image.
- `services/inventory-python/app.py` — OTel SDK setup, FastAPI instrumentation, model training/inference, metrics, spans, health endpoints, and demo behavior control.
- `observability/otel-collector.yaml` — OTLP receiver, memory limiter, batch processor, trace exporter, and Prometheus exporter.
- `observability/prometheus.yml` — scrape interval and targets.
- `observability/grafana/` — provisioned Prometheus/Jaeger data sources and dashboard.
- `scripts/generate-traffic.sh` — repeatable varied order traffic.
- `docs/HANDS_ON_LABS.md` — copy/paste experimentation sequence.

## 9. Practical design caveats to mention if asked

- `depends_on` in this Compose file establishes startup order, while container health checks report readiness; it does not make every service wait for dependency health.
- Java's demo outbound HTTP code does not set connect/read timeouts. A production caller should always bound how long it can wait for a dependency.
- The Java response JSON parser is intentionally narrow for this fixed demo response shape. A real service should use Jackson or another standard JSON library and test the API contract.
- There is no explicit retry. Retries can help transient errors but can also amplify load; they need limits, backoff, and idempotency.
- The cAdvisor socket gives that service Docker daemon access. It is enabled because the local demo needs container metrics; do not expose this setup as an Internet-facing production deployment.
- Prometheus and Jaeger use local, ephemeral storage in the current Compose setup. Recreating containers can lose historical telemetry.
