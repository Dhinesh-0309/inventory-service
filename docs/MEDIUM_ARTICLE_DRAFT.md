# Observability Is a Team Sport: What My Java and Python Lab Taught Me

*Building a two-service order flow helped me understand that useful telemetry starts with a conversation about what the business needs to know—not with choosing a dashboard.*

When an order fails or becomes slow, one question comes up quickly: **who is responsible for the telemetry?** Is it the application developer, the DevOps or platform engineer, or the SRE?

I used to think of observability mostly as a set of tools to install. While building my local e-commerce observability lab, I learned that the tools are only one part of the work. Teams also need to agree on what to measure, who understands each measurement, and how that information will help during an incident.

The project gave me a small place to explore that idea. It has a Java Spring Boot Orders service and a Python FastAPI Inventory service. Orders calls Inventory to check stock and calculate a stockout-risk estimate. I added OpenTelemetry instrumentation and connected the services to Prometheus, Grafana, and Jaeger using Docker Compose.

> **[Add screenshot: the project architecture showing Orders, Inventory, the OpenTelemetry Collector, Prometheus, Grafana, and Jaeger.]**
>
> *Caption: One order crosses two services. Telemetry follows the same path to the tools used to inspect it.*

## The ownership question has a team answer

There is no single role that can decide every useful metric.

An application developer knows where important business events happen. In this project, the Orders service knows when an order is accepted or rejected. The Inventory service knows whether a stock check succeeded and how long model inference took. That domain knowledge matters because an infrastructure dashboard cannot tell us what “a good order” means to the business.

A platform or DevOps engineer can make instrumentation easier to use consistently. They might provide OpenTelemetry libraries or agents, configure the Collector, attach service metadata, manage the telemetry pipeline, and publish shared dashboard templates.

An SRE can help connect those measurements to reliability goals. They can ask what customers experience when the service is slow, which errors matter, what should trigger an alert, and what evidence an on-call engineer needs during an incident.

These are useful areas of focus, not isolated job boundaries. The team needs to agree on the meaning of each signal. Otherwise, two services may measure similar things differently, or a dashboard may show numbers that nobody knows how to act on.

## Start with questions, then choose measurements

Before adding a metric, I find it useful to ask:

- What customer or business problem are we trying to notice?
- Which service knows when that event happens?
- What should count as success, failure, or an expected business outcome?
- What dimensions would help us investigate without creating an unmanageable number of time series?
- Who will use this signal, and what action could they take from it?

For example, “order rejected because stock is insufficient” and “Inventory service is unavailable” are different outcomes. In the project, an order can be rejected while the HTTP request itself succeeds. If I only count HTTP errors, I miss an important business result. If I count every rejected order as a system outage, I create a misleading alert.

That distinction is small in code, but meaningful for the person trying to understand what customers experienced.

## A small request, three useful views

The request path is:

**Customer → Java Orders service → Python Inventory service → Orders response**

OpenTelemetry provides APIs and instrumentation that create telemetry and send it through the Collector. Prometheus stores and queries metrics. Grafana visualizes those metrics. Jaeger helps inspect traces across the services.

I use the three views to answer different questions:

- **Metrics:** Is request latency or the error rate changing across many requests?
- **Traces:** What happened to one particular order, and where did it spend time?
- **Health checks:** Are the services ready to handle work?

A graph can reveal that latency increased, but it does not automatically say why. A trace can show that an individual request spent most of its time waiting for Inventory. Together, those signals narrow the investigation.

> **[Add screenshot: Grafana showing request latency and error metrics after a traffic burst.]**
>
> *Caption: Metrics show the pattern across requests. The dashboard is useful because the team agreed what those measurements mean.*

> **[Add screenshot: a Jaeger trace showing the Orders request and its Inventory child span.]**
>
> *Caption: A trace follows one request across the service boundary and shows where its time was spent.*

## The experiments that made the concepts click

I added several scenarios to make the behavior visible.

### A business rejection is not automatically an outage

SKU-42 has 80 demo units. Requesting more than that produces a rejected order. This is an expected business result: the application is responding, and stock is insufficient. That should be measured separately from a 5xx response caused by a service problem.

### A slow service does not always mean slow model inference

The Inventory demo can pause before it runs the model. The complete request becomes slower, but the model inference timer can remain short. This showed me why a single “service latency” number cannot explain every kind of delay. I need measurements around the relevant operations, plus a trace to see how they fit together.

### A dependency failure can appear at more than one layer

When Inventory is put into demo failure mode, Orders cannot complete its downstream call and returns an error to its caller. Metrics show whether server errors are appearing. A trace helps connect the failed order to the Inventory call that failed.

### Model metrics need context too

The Inventory service records prediction outcomes and inference duration. I can change demand, stock, lead time, and volatility to compare the model output. The model uses synthetic training data, so it is a learning example—not a production forecasting claim.

> **[Add screenshot: the browser Experiment Playground with a scenario selected and its result displayed.]**
>
> *Caption: The Playground lets a reader change inputs and run normal, rejected, slow, failure, and model-risk scenarios.*

## Agree on the telemetry contract

The practical lesson I’m taking away is that teams should discuss instrumentation together before every service invents its own conventions.

For each important signal, agree on its name, unit, meaning, and useful attributes. Decide which service should emit it. Use consistent service names and trace context so related work can be connected. Be careful with labels that can have unlimited values, such as order IDs or customer IDs; those can create too many time series and may expose sensitive information.

This is how I think about “instrument once, use it across the team.” It does not mean one person writes every metric or that a metric is magically reused everywhere. It means people share a clear contract and common patterns, so the telemetry is understandable across services and teams.

## What I learned

My main takeaway is that observability is not finished when the Collector is running or a dashboard has been created. It is useful when the people responsible for the application, platform, and reliability agree on what the signals mean and how they will respond to them.

Developers bring the business context. Platform engineers make telemetry collection and conventions repeatable. SREs connect the signals to service reliability and incident response. The work overlaps, and that overlap is where a shared understanding is built.

This local project helped me practice those ideas with two languages and a request that crosses a service boundary. It also reminded me that telemetry helps people investigate; it does not automatically find the root cause or make the system reliable on its own.

## Try the project

The repository includes a browser Experiment Playground. Clone the repository, start the services, and open the Playground locally:

```sh
git clone [your public repository URL]
cd [project folder]
docker compose up --build
```

Then visit **http://localhost:8088**. Choose a scenario, run an order, and follow the clues to Prometheus, Grafana, or Jaeger.

The services and demo controls are intended for local learning. The model is synthetic, and the project does not include a production database, alerting system, centralized log platform, or Kubernetes deployment.

**Project repository:** [Add your public GitHub link]

**Next for me:** I want to keep improving the experiment flow and use it to practice turning a customer-facing symptom into a clear investigation and recovery story.
