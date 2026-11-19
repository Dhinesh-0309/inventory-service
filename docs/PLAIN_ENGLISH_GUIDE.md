# Explain the project in plain English

This version is for explaining the project to a friend, interviewer, or teammate who knows what a website is but has not studied observability.

## Start with the online shop

Imagine an online shop. When a customer places an order, one part of the software handles the order. Another part checks whether there is enough stock. In this project, these are two separate services:

- **Orders** is written in Java and uses Spring Boot. It receives the order.
- **Inventory** is written in Python and uses FastAPI. It checks the stock and estimates the risk of running out.

The services are like two teams working on the same shop. Orders asks Inventory a question over HTTP, which is the basic request-and-response method websites use to talk to each other.

## Why add observability?

If customers say, “The shop is slow,” or orders start failing, we need clues to find out what is wrong. Is the order service slow? Is inventory slow? Is the model taking too long? Is a service returning errors?

Observability gives us those clues. It does not predict exactly where a future error will happen. It helps us notice unusual behavior and investigate where a problem occurred.

Think of it like a car dashboard and a trip recorder:

- **Metrics** are dashboard readings over time: how many orders came in, how many succeeded, how long requests took, and how many failed.
- **A trace** is the trip recorder for one request. It shows that request travelling from Orders to Inventory and how long each step took.
- **Health checks** are simple “are you alive and ready?” questions for each service.
- **Logs** are written messages from the services. This demo keeps them in Docker’s output; it does not have a separate log-search system.

Together, these clues help answer “What is going wrong?” and “Where should I look next?”

## What happens when a customer places an order?

1. The customer’s request reaches the Java Orders service.
2. Orders checks that the request has a SKU and a valid quantity.
3. Orders asks the Python Inventory service whether the stock is available.
4. Inventory checks its sample stock list and runs its small stockout-risk model.
5. Inventory sends its answer back to Orders.
6. Orders returns a response, such as accepted or rejected.

While this happens, the project records information about the request. For example, it records how long the request took, whether it succeeded, and which services it visited.

## What does “instrument the application” mean?

Instrumenting an application means adding measuring tools to it. Like adding a timer and a counter to a process, we add code or an automatic agent that records useful information while the application runs.

This project collects two kinds of measurements:

**Automatic HTTP measurements** are created by OpenTelemetry instrumentation. They include things like the number of HTTP requests, their response codes, and how long they took. “HTTP telemetry” simply means information about HTTP requests and responses.

**Business measurements** are added in the application code because only the application knows what an “accepted order” or “stockout prediction” means. This project counts accepted and rejected orders and measures model predictions and inference time.

For example, a request can return HTTP 200 but contain a status of rejected because there is not enough stock. The HTTP request worked successfully; the business decision was to reject the order. Those are different things, so we track both.

## What does the stockout-risk model actually predict?

Imagine SKU-42 is a pencil. The Inventory service does two separate checks:

1. **Can this order be filled?** It looks up the demo stock for the SKU and compares it with the order quantity. In this demo, SKU-42 has 80 units. An order for 2 pencils is available; an order for more than 80 is rejected.
2. **How risky is it that this item could run out?** The model uses the daily demand, stock-on-hand value, supplier lead time, and demand variability sent with the request. In simple terms, high demand, little stock, a long wait for a supplier, and unpredictable demand point toward higher risk.

These checks are separate. The order quantity does **not** go into the model in this version. It is used only for the availability check. The SKU name also does not teach the model what a pencil is; the model receives the numeric demand and stock-related values.

The model is a Random Forest trained when the Python service starts using generated example data. During training, examples are marked as risky when a simple formula—daily demand × lead days × demand variability—is greater than stock on hand × 1.6. The trained model estimates a risk probability, then the service labels it low, medium, or high.

For example, imagine a pencil with high daily sales, only a few pencils left, and a long supplier wait. The model would be expected to return a higher risk than for a pencil with lots of stock and low, steady demand. It is a demonstration, not a reliable business forecast: the training data is synthetic, and the request's stock-on-hand value is supplied by the caller rather than read from the demo stock lookup.

## Where does the information go?

The services send their OpenTelemetry measurements to the **OpenTelemetry Collector**. Think of the Collector as a mailroom: it receives information from both services and sends it to the right place.

- The Collector sends **traces** to **Jaeger**, where you can open one request and follow its steps.
- The Collector exposes application **metrics** at an HTTP address. **Prometheus** checks that address regularly and saves the metric values over time. This regular check is called scraping.
- **node-exporter** and **cAdvisor** provide system and container measurements that Prometheus also scrapes.
- **Grafana** draws charts using the data stored by Prometheus. Grafana can also connect to Jaeger to help inspect traces.

In this project, the Collector’s Prometheus metrics endpoint is http://localhost:9464/metrics. Prometheus reads it every 10 seconds. This is separate from the shop’s application endpoints: Orders listens on port 8080, and Inventory listens on port 8000.

## How do we investigate a problem?

Suppose customers report that placing orders has become slow:

1. Open Grafana and look at request rate, errors, and latency. This tells us whether the problem is happening broadly and when it started.
2. If the charts show that requests are slow, open Jaeger and find a slow order request.
3. Follow the request’s trace. It shows how much time was spent in Orders and how much was spent waiting for Inventory.
4. If Inventory took most of the time, investigate that service. If the model step took most of Inventory’s time, investigate the model work.

The metric points us toward a problem. The trace helps us inspect one example and see where its time went.

## A simple demonstration you can give

First start the services and open Grafana and Jaeger. Generate ordinary orders and look at a normal request. Then tell Inventory to wait 900 milliseconds before replying. Generate another order.

You should see the request take longer in Grafana. In Jaeger, the trace shows that more time was spent in the Inventory part of the trip. Reset the delay and the request should become faster again.

You can also tell Inventory to return an error. The order request then fails, and the error appears in the metrics and trace. Reset the error mode after the demonstration.

## A presentation version

Here is a simple version you can say out loud:

> “Imagine an online shop where one service receives orders and another checks stock. In my project, the order service uses Java and Spring Boot, and the inventory service uses Python and FastAPI. If a customer’s order is slow or fails, it can be hard to tell which service caused the problem. So I added observability, which gives us clues about how the system is behaving. We count requests and accepted or rejected orders, measure how long requests take, and create a trace that follows one order from the Java service into the Python service. OpenTelemetry collects this information. Prometheus stores and lets us query the metrics, Grafana shows the charts, and Jaeger lets us inspect the request trace. I can make Inventory slow or make it fail, then use the charts and trace to show where the problem happened.”

## A few terms in everyday words

| Term | Plain meaning |
|---|---|
| Service | One part of the application that does a particular job |
| Microservice | A service that runs separately and talks to other services over a network |
| Endpoint | A URL where a service accepts a particular request, such as /orders |
| HTTP status | A number that summarizes how an HTTP request went, such as 200 for success or 502 for a failed dependency call |
| Instrumentation | Measuring code or an agent that records information while the app runs |
| Metric | A number recorded over time, such as orders per minute or request duration |
| Trace | A record showing the path and timing of one request across services |
| Span | One timed step inside a trace |
| Collector | A service that receives telemetry and forwards it to the monitoring tools |
| Scrape | Prometheus regularly reading a metrics endpoint over HTTP |
| Dashboard | Charts that help a person see changes and patterns |
| Readiness | Whether a service is ready to handle requests |

## Keep the claims accurate

- This demo helps us **detect and investigate** issues; it does not predict every failure in advance.
- HTTP measurements tell us about requests. Business metrics tell us what the application considered an accepted or rejected order.
- Inventory uses a small model trained on generated example data. It is there to provide an inference step to measure, not to make real stock decisions.
- Docker Desktop runs the containers in a Linux virtual machine. Its system metrics are not direct readings from macOS hardware.
- This is an observability learning project, not a complete production e-commerce system.
