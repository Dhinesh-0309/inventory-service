import asyncio
import os
import time
from typing import Annotated

import numpy as np
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestClassifier


service_name = os.getenv("OTEL_SERVICE_NAME", "inventory")
resource = Resource.create({"service.name": service_name})
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(tracer_provider)

metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=10_000)
metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))
meter = metrics.get_meter("inventory.business")
prediction_counter = meter.create_counter(
    "inventory.stockout_risk.predictions", description="Completed local stockout-risk predictions"
)
prediction_errors = meter.create_counter(
    "inventory.stockout_risk.errors", description="Failed stockout-risk predictions"
)
inference_duration = meter.create_histogram(
    "inventory.stockout_risk.inference.duration", unit="ms", description="Local model inference duration"
)
tracer = trace.get_tracer("inventory.business")


def train_model() -> RandomForestClassifier:
    """Train a deterministic demo classifier from generated inventory examples."""
    rng = np.random.default_rng(42)
    rows = 2_000
    daily_demand = rng.uniform(1, 40, rows)
    on_hand = rng.uniform(0, 500, rows)
    lead_days = rng.uniform(1, 30, rows)
    volatility = rng.uniform(0.5, 4, rows)
    risk_score = daily_demand * lead_days * volatility
    labels = (risk_score > on_hand * 1.6).astype(int)
    model = RandomForestClassifier(n_estimators=40, max_depth=8, random_state=42, n_jobs=1)
    model.fit(np.column_stack([daily_demand, on_hand, lead_days, volatility]), labels)
    return model


model = train_model()
inventory_levels = {"SKU-42": 80, "SKU-7": 24, "SKU-100": 150}
behavior = {"delay_ms": 0, "fail": False}


class CheckRequest(BaseModel):
    sku: Annotated[str, Field(min_length=1, max_length=64)]
    quantity: Annotated[int, Field(gt=0, le=10_000)]
    dailyDemand: Annotated[float, Field(ge=0, le=10_000)] = 8
    onHand: Annotated[float, Field(ge=0, le=100_000)] = 40
    leadDays: Annotated[float, Field(ge=0, le=365)] = 4
    demandVolatility: Annotated[float, Field(ge=0.1, le=10)] = 2


class DemoBehavior(BaseModel):
    delayMs: Annotated[int, Field(ge=0, le=10_000)] = 0
    fail: bool = False


class DemoBehaviorResponse(BaseModel):
    delayMs: int
    fail: bool


app = FastAPI(title="Inventory Service", version="0.1.0")
FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, meter_provider=metrics.get_meter_provider())


@app.get("/health/live")
async def liveness():
    return {"status": "UP", "service": service_name}


@app.get("/health/ready")
async def readiness():
    if model is None:
        raise HTTPException(status_code=503, detail="model is not loaded")
    return {"status": "UP", "model": "stockout-risk-demo"}


@app.post("/inventory/check")
async def check_inventory(request: CheckRequest):
    if behavior["delay_ms"]:
        await asyncio.sleep(behavior["delay_ms"] / 1000)
    if behavior["fail"]:
        raise HTTPException(status_code=503, detail="inventory dependency is in demo failure mode")

    available = inventory_levels.get(request.sku, 0) >= request.quantity
    started = time.perf_counter()
    outcome = "error"
    with tracer.start_as_current_span("inventory.stockout_risk.predict") as span:
        span.set_attribute("inventory.sku", request.sku)
        span.set_attribute("inventory.quantity", request.quantity)
        try:
            features = np.array([[
                request.dailyDemand,
                request.onHand,
                request.leadDays,
                request.demandVolatility,
            ]])
            probability = float(model.predict_proba(features)[0][1])
            label = "high" if probability >= 0.65 else "medium" if probability >= 0.35 else "low"
            span.set_attribute("ml.model.name", "stockout-risk-demo")
            span.set_attribute("ml.model.version", "synthetic-v1")
            span.set_attribute("ml.prediction.risk", label)
            span.set_attribute("ml.prediction.probability", probability)
            outcome = label
            return {
                "available": available,
                "stockoutRisk": round(probability, 4),
                "riskLabel": label,
            }
        except Exception as error:
            prediction_errors.add(1, {"reason": "inference_error"})
            span.record_exception(error)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(error)))
            raise HTTPException(status_code=500, detail="risk inference failed") from error
        finally:
            inference_duration.record((time.perf_counter() - started) * 1000)
            prediction_counter.add(1, {"risk": outcome})


@app.post("/demo/behavior", response_model=DemoBehaviorResponse)
async def set_demo_behavior(request: DemoBehavior):
    behavior["delay_ms"] = request.delayMs
    behavior["fail"] = request.fail
    return {"delayMs": behavior["delay_ms"], "fail": behavior["fail"]}
