# Observability Experiments: Find the Problem, Follow the Evidence

A step-by-step lab for the local Order and Inventory application. Each experiment changes one thing so you can see how symptoms appear in metrics and traces, then explain what you found.

## The project story

A customer places an order with the Java Orders service. Orders calls the Python Inventory service to check stock and calculate a stockout-risk estimate. If something goes wrong, we want to answer: Is the system unhealthy? Which service is affected? What happened to this particular request?

Prometheus stores measurements over time. Grafana displays them as graphs. Jaeger shows the steps and timing of an individual request. OpenTelemetry is the instrumentation and export standard used by the services and Collector. **Metrics show patterns across many requests; a trace helps us inspect one request.** Neither one alone automatically proves the root cause.

## 1. Start the lab and create a baseline

In Terminal:

~~~sh
cd /Users/dp/Documents/observability-project
docker compose up -d --build
docker compose ps
~~~

Wait for `orders` and `inventory` to show `healthy`. Check readiness:

~~~sh
curl -fsS http://localhost:8080/actuator/health/readiness
curl -fsS http://localhost:8000/health/ready
~~~

Open Grafana at http://localhost:3000 (login `admin` / `admin`), Prometheus at http://localhost:9090/graph, Prometheus targets at http://localhost:9090/targets, and Jaeger at http://localhost:16686. In Grafana open **Observable Order Platform** and set the time range to **Last 15 minutes**.

Create normal traffic:

~~~sh
bash scripts/generate-traffic.sh
~~~

It sends 60 orders. Wait about 15 seconds for requests, export, and scraping to finish. In Jaeger select service `orders`, search recent traces, open one trace, and expand its spans. Follow the request from Orders into the Inventory service and `inventory.stockout_risk.predict` model operation.

**Look for:** both services have traffic, errors are zero or close to zero, and traces contain spans from both services. Record the baseline request rate, latency, error rate, and longest span.

**Say:** “I established a healthy baseline first. Grafana shows the overall behavior over time, while Jaeger lets me follow one order across the two services.”

## 2. Read the key Prometheus queries

Paste these queries into Prometheus one at a time:

~~~promql
sum by (service_name) (rate(http_server_request_duration_seconds_count[1m]))
~~~

Requests per second, grouped by service. The underlying count is a counter; `rate` calculates its recent per-second increase.

~~~promql
histogram_quantile(0.95, sum by (service_name, le) (rate(http_server_request_duration_seconds_bucket[5m])))
~~~

Estimated HTTP p95 latency by service, in seconds. Roughly 95 of 100 requests were at or below this duration in the window. It needs enough requests to be useful; after a quiet period it can be empty or jumpy.

~~~promql
sum by (service_name) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m]))
~~~

Server errors per second. `5..` matches HTTP status 500–599. A business rejection may still use a successful HTTP response, so it is not automatically an HTTP error.

~~~promql
orders_accepted_total
orders_rejected_total
sum by (risk) (rate(inventory_stockout_risk_predictions_total[5m]))
~~~

These show accepted and rejected business outcomes and model predictions grouped by bounded risk label. Counters only increase; `rate(...)` shows how quickly they increase.

~~~promql
histogram_quantile(0.95, sum by (le) (rate(inventory_stockout_risk_inference_duration_milliseconds_bucket[5m])))
~~~

Estimated p95 time spent inside model inference, in milliseconds. It does not measure the entire Inventory request.

## 3. Experiment: business rejection is not a service outage

SKU-42 has 80 demo units. Request 81:

~~~sh
curl -i -sS http://localhost:8080/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-42","quantity":81,"dailyDemand":8,"onHand":40,"leadDays":4,"demandVolatility":2}'
~~~

**Look for:** response body status `rejected`; `orders_rejected_total` increases. This is an expected business decision, not a 5xx service failure. Find the trace in Jaeger; it can still be a successful request through both services.

**Say:** “A rejection does not necessarily mean the system is broken. Inventory made a valid business decision because there was not enough stock. I watch business outcome counters separately from HTTP error metrics.”

## 4. Experiment: make Inventory slow

Add a 900 millisecond demo delay and send 20 orders:

~~~sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":900,"fail":false}'
REQUESTS=20 bash scripts/generate-traffic.sh
~~~

Inspect HTTP p95 in Grafana and a slow Orders trace in Jaeger. **Look for:** the whole request is slower; the Inventory server span includes most of the added wait. The model inference timer may remain low because the demo waits before inference begins. So a slow Inventory request does not necessarily mean the model itself is slow.

Reset the delay:

~~~sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":0,"fail":false}'
~~~

Send normal traffic again and confirm latency moves toward baseline.

**Say:** “The latency metric showed a slowdown. The trace localized most added time to Inventory. Model inference duration did not rise in the same way, so the artificial delay was outside the measured model operation.”

## 5. Experiment: make Inventory fail

Turn failure mode on:

~~~sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":0,"fail":true}'
~~~

Submit an order:

~~~sh
curl -i -sS http://localhost:8080/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-42","quantity":2,"dailyDemand":8,"onHand":40,"leadDays":4,"demandVolatility":2}'
~~~

**Look for:** Orders returns HTTP 502 after Inventory fails. The 5xx query increases. In Jaeger find the matching trace; inspect the failing downstream span and error status. No model prediction is expected because failure happens before inference.

Reset failure mode right away:

~~~sh
curl -sS -X POST http://localhost:8000/demo/behavior \
  -H 'Content-Type: application/json' \
  -d '{"delayMs":0,"fail":false}'
~~~

Generate normal traffic and confirm errors fall and successful traces return.

**Say:** “The 5xx rate showed a customer-facing failure. The trace showed the failed downstream Inventory call. I reset the injected failure and verified recovery with the same metric and a fresh request.”

## 6. Experiment: change model inputs

Send low-risk-looking inputs:

~~~sh
curl -sS http://localhost:8080/orders -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-42","quantity":2,"dailyDemand":1,"onHand":400,"leadDays":1,"demandVolatility":0.5}'
~~~

Then high-risk-looking inputs:

~~~sh
curl -sS http://localhost:8080/orders -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-42","quantity":2,"dailyDemand":35,"onHand":10,"leadDays":18,"demandVolatility":4}'
~~~

**Look for:** compare `riskLabel` and `stockoutRisk` in the responses. In Prometheus group predictions by risk; in Jaeger inspect model span attributes like `ml.model.name`, `ml.prediction.risk`, and `ml.prediction.probability`. Demand, stock on hand, lead time, and volatility are model inputs. Order quantity is used for the separate stock check, not the model input.

**Say:** “I recorded prediction counts, inference duration, and trace attributes to understand model behavior. This is a synthetic demo model, so it demonstrates observability rather than a production-quality forecast.”

## 7. A repeatable incident investigation

1. **Confirm the symptom** in Grafana: when did latency, errors, traffic, or resource use change? Compare with baseline.
2. **Find the scope** in Prometheus: group by `service_name`. Is Orders affected, Inventory, or both? Check `/targets` so you do not confuse broken telemetry collection with a healthy application.
3. **Follow one request** in Jaeger: select `orders`, choose a time range covering the issue, open a trace, and find the slow or failed span. See whether the downstream call or model span is involved.
4. **Check context** using service health and recent logs:

~~~sh
docker compose ps
docker compose logs --since=5m orders inventory otel-collector
~~~

5. **Change one thing** based on the evidence. In this lab, reset injected delay or failure.
6. **Verify recovery** by repeating the query and sending fresh traffic.

A short interview answer: “I noticed **[symptom]** in **[metric/dashboard]**. I narrowed it to **[service]**, then opened a matching Jaeger trace. The trace showed **[slow/error span]**. I checked service health and logs, took **[action]**, and verified recovery using the same metric and a fresh request.”

## If metrics or traces are missing

- Run `docker compose ps` and make sure the services are running.
- Check Prometheus `/targets`; Collector, node-exporter, and cAdvisor should be up.
- Wait at least one scrape interval (about 10 seconds) after generating traffic.
- Set Grafana and Jaeger to a time range that includes the experiment.
- Check logs with the command above. In Jaeger choose `orders` and search after traffic completes.

## System metrics and project limits

Container memory query:

~~~promql
container_memory_working_set_bytes{id=~"/docker/.*"}
~~~

Docker VM CPU query:

~~~promql
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)
~~~

Docker Desktop runs containers inside a Linux VM; node-exporter reports VM metrics, not Mac hardware. cAdvisor may label containers by ID rather than a friendly name.

This project demonstrates Java and Python services, OpenTelemetry, the Collector, Prometheus, PromQL, Grafana, Jaeger, health checks, business/model metrics, and local container/system metrics. The model uses synthetic demo data. There is no production database, alerting setup, log aggregation system, or Kubernetes deployment. Be clear about these limits in an interview.

## Stop the stack

~~~sh
docker compose down
~~~
