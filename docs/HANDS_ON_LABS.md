# Hands-on observability labs

Run these labs from Terminal on your Mac. They use the running Docker Compose project and are designed to be repeated: generate a baseline, change one behavior, then compare metrics and traces.

## 1. Start the stack

```sh
cd /Users/dp/Documents/observability-project
docker compose up -d --build
docker compose ps
```

Wait until `orders` and `inventory` show `healthy`. Then check readiness:

```sh
curl -fsS http://localhost:8080/actuator/health/readiness
curl -fsS http://localhost:8000/health/ready
```

Open these pages:

- Grafana: <http://localhost:3000> — sign in with `admin` / `admin`, then open the **Observable Order Platform** dashboard.
- Prometheus: <http://localhost:9090/graph> — enter PromQL in the query box. Check <http://localhost:9090/targets> for scrape health.
- Jaeger: <http://localhost:16686> — search for recent `orders` and `inventory` traces.

## 2. Make a baseline and follow one request

Submit one order:

```sh
curl -sS http://localhost:8080/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-42","quantity":2,"dailyDemand":8,"onHand":40,"leadDays":4,"demandVolatility":2}'
```

You should get an accepted order response. In Jaeger, search service `orders`, open a recent trace, and follow it into `inventory`. Look at the server request span and `inventory.stockout_risk.predict` span; check their durations and attributes such as `ml.model.name`, `ml.prediction.risk`, and `ml.prediction.probability`.

Generate enough requests to make rates and percentiles easier to see:

```sh
bash scripts/generate-traffic.sh
```

The script sends 60 varied orders. Allow around 15 seconds for metric export and scraping, then inspect the Grafana dashboard or try these Prometheus queries:

```promql
sum by (service_name) (rate(http_server_request_duration_seconds_count[1m]))
```

```promql
histogram_quantile(0.95, sum by (service_name, le) (rate(http_server_request_duration_seconds_bucket[5m])))
```

```promql
orders_accepted_total
```

```promql
inventory_stockout_risk_predictions_total
```

The exact counter values grow as you run more requests. Metric names are the Prometheus-normalized forms of the OpenTelemetry instruments.

## 3. Change the model's input and compare business metrics

Send a low-risk-looking input:

```sh
curl -sS http://localhost:8080/orders -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-42","quantity":2,"dailyDemand":1,"onHand":400,"leadDays":1,"demandVolatility":0.5}'
```

Then send a high-risk-looking input:

```sh
curl -sS http://localhost:8080/orders -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-42","quantity":2,"dailyDemand":35,"onHand":10,"leadDays":18,"demandVolatility":4}'
```

Compare `riskLabel` and `stockoutRisk` in the responses. In Prometheus, group prediction counts by risk:

```promql
sum by (risk) (inventory_stockout_risk_predictions_total)
```

The classifier is a local demo trained on synthetic data, so treat it as an instrumented model operation rather than a real inventory forecast.

## 4. Simulate a slow dependency

Make inventory wait 900 ms before responding:

```sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":900,"fail":false}'
```

Send an order or a short traffic burst, then compare the latency dashboard and Jaeger trace with the baseline. The Python inventory span should account for most of the added time. Reset the behavior after the experiment:

```sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":0,"fail":false}'
```

## 5. Simulate an inventory outage

Turn on failure mode:

```sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":0,"fail":true}'
```

Submit an order and notice that the order API returns `502` after inventory returns an error. In Prometheus, graph the 5xx rate:

```promql
sum by (service_name) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m]))
```

Open the corresponding trace in Jaeger and inspect the error status and spans. Reset failure mode right away:

```sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":0,"fail":false}'
```

## 6. Explore system and container metrics

In Prometheus, inspect Docker container working set memory by container ID:

```promql
container_memory_working_set_bytes{id=~"/docker/.*"}
```

Inspect Linux VM CPU utilization:

```promql
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)
```

Docker Desktop runs containers inside a Linux VM, so node-exporter reports VM metrics, not macOS hardware metrics. cAdvisor can expose container IDs instead of friendly names.

## A useful incident-investigation routine

1. Start from a change in request rate, latency, error rate, or resource use in Grafana.
2. Narrow it down by service and route in Prometheus.
3. Find a matching recent trace in Jaeger.
4. Compare time spent in orders, inventory, and model inference spans.
5. Check container metrics for resource pressure around the same time.
6. Reset the simulated behavior and repeat the baseline to confirm the signal returns.

When finished, stop the services while retaining downloaded images:

```sh
docker compose down
```
