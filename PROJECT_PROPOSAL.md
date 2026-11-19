# Observability Lab: Java and Python Microservices

## Project goal

Build a small, realistic service system that demonstrates how an engineer can detect, investigate, and explain production-style failures using metrics, traces, health checks, and dashboards.

**Working title:** Observable Order Platform

**Resume summary (draft):** Built a containerized Java and Python microservice application instrumented with OpenTelemetry, Prometheus, Grafana, and Jaeger; created service and system dashboards, health checks, and failure scenarios to investigate latency and errors across service boundaries.

## Proposed application

Use two independently running services in one application:

- **Java Spring Boot `orders` service:** accepts an order, validates it, and calls the Python service.
- **Python FastAPI `inventory` service:** checks/reserves stock and returns a result. It also hosts a small local stockout-risk model trained on synthetic data, so inference latency, prediction counts, and errors can be observed without a cloud account or paid API.

The Java and Python components are separate processes and containers, communicating over HTTP. This makes the cross-service trace propagation and service health meaningful while keeping the first version manageable. A small load generator can send normal and deliberately varied traffic.

## Observability architecture

```text
Load generator ──HTTP──> Java orders ──HTTP──> Python inventory
                            │                         │
                            └──────── OTLP ────────────┘
                                      │
                             OpenTelemetry Collector
                              ┌───────┴────────┐
                         traces             metrics
                            │                   │
                          Jaeger <── Grafana ── Prometheus

Host/container metrics: node-exporter and cAdvisor ──> Prometheus
```

Grafana can use Prometheus for metrics and Jaeger as a trace data source. The OpenTelemetry Collector receives OTLP telemetry from both services, exports traces to Jaeger, and exposes application metrics for Prometheus to scrape. Prometheus also scrapes its own, host, and container metrics.

## What to instrument

### Application metrics

- Request count, error count, and request duration by service, route, and status class.
- Orders accepted, rejected, and completed.
- Inventory checks and reservation outcomes.
- Outbound dependency request duration and failures.
- A small business metric such as available-stock checks or order value, with bounded labels.

Use histograms for latency and counters for event totals. For the optional stockout-risk inference, record prediction latency, prediction counts by bounded outcome, and model errors. Avoid labels with unbounded values such as customer IDs, order IDs, or raw URLs.

### Traces

- One trace should span the incoming order request, Java processing, the HTTP call, and Python inventory handling.
- Include useful span attributes and status/error details without recording secrets or personal data.
- Demonstrate context propagation across the Java-to-Python boundary.

### Health and system signals

- Java and Python liveness and readiness endpoints.
- Container CPU/memory and host CPU/memory/disk metrics.
- A dependency failure scenario that makes readiness or request health visibly change.

## Dashboards and demonstrations

Create a service overview dashboard with request rate, error rate, latency percentiles, and healthy instance count. Add a system dashboard for host/container resource use. Link an example slow or failed request from a metric panel to its Jaeger trace.

Include repeatable scenarios such as:

1. Normal traffic and a healthy baseline.
2. A deliberately slow inventory response, visible as elevated latency and a longer child span.
3. Inventory errors or unavailability, visible in error metrics, health status, and failed traces.
4. A short load burst that demonstrates resource and latency behavior.

## Suggested implementation phases

1. **Agree on scope and domain.** Confirm the order/inventory example and local Docker Compose target.
2. **Build the application.** Add the Spring Boot and FastAPI services, request flow, health endpoints, and deterministic failure/latency switches.
3. **Add telemetry.** Instrument both services with OpenTelemetry SDKs and configure trace context propagation and metric export.
4. **Run the stack.** Add the Collector, Prometheus, Grafana, Jaeger, node-exporter, and cAdvisor in Docker Compose.
5. **Make it usable.** Provision dashboards and data sources, add a load generator, and document startup and scenarios.
6. **Polish for a resume.** Capture dashboard/trace screenshots, explain design decisions, and add a concise architecture diagram and demo steps to the README.

## Proposed first-version boundaries

- Run locally with Docker Compose; no cloud account or Kubernetes required for the first milestone.
- Keep storage and business logic intentionally small; this is an observability project, not a full commerce platform.
- Start with metrics, traces, and health checks. Add centralized logs (for example, Loki) only after the core flow works.
- Keep the AI/ML feature small and local: it is a practical instrumentation target, while observability remains the project's main subject.
- Add alert rules for a small number of actionable conditions, such as sustained high error rate or latency, after dashboards are in place.

## Confirmed project choices

- **Domain:** orders + inventory.
- **Runtime:** local Docker Compose; no cloud account or Kubernetes dependency.
- **Frameworks:** Spring Boot + FastAPI.
- **AI/ML feature:** a small local scikit-learn stockout-risk model using synthetic data, included as a useful inference path to instrument. It does not require an external AI API and remains secondary to the observability work.

Implementation has started with service skeletons, a Collector pipeline, local telemetry backends, health checks, a provisioned Grafana dashboard, a traffic generator, and a learning guide. The next iteration can focus on running the stack and resolving any local Docker/runtime issues, then deepen the dashboards and incident exercises.
