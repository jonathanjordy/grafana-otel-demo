import os
import json
import logging
import time
import random
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Float, text

# ─────────────────────────────────────────────────────────────
# OTEL SETUP — do this before anything else
# ─────────────────────────────────────────────────────────────
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from prometheus_client import make_asgi_app

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "order-service")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

# Resource — identifies this service in every span, metric, and log
resource = Resource.create({
    "service.name": SERVICE_NAME,
    "service.version": "1.0.0",
    "deployment.environment": "demo",
})

# Tracer provider — sends spans to OTel Collector via gRPC
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(SERVICE_NAME)

# Meter provider — sends metrics to OTel Collector AND exposes /metrics for Prometheus
prometheus_reader = PrometheusMetricReader()
otlp_metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True)
)
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[prometheus_reader, otlp_metric_reader]
)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(SERVICE_NAME)

# Custom business metrics
order_counter = meter.create_counter(
    "orders_total",
    description="Total number of orders placed",
)
order_errors_counter = meter.create_counter(
    "order_errors_total",
    description="Total number of failed orders",
)
order_duration = meter.create_histogram(
    "order_duration_seconds",
    description="Time taken to process an order",
    unit="s",
)

# Logger provider — ships logs to OTel Collector via gRPC
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)
set_logger_provider(logger_provider)

# ─────────────────────────────────────────────────────────────
# LOGGING — inject trace_id into every log line automatically
# ─────────────────────────────────────────────────────────────
LoggingInstrumentor().instrument(set_logging_format=True, logger_provider=logger_provider)

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "service": "' + SERVICE_NAME + '", '
           '"trace_id": "%(otelTraceID)s", "span_id": "%(otelSpanID)s", "message": "%(message)s"}',
)
logger = logging.getLogger(SERVICE_NAME)

# ─────────────────────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://demo:demo@postgres:5432/demo")
# sqlalchemy needs asyncpg driver
DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    id          = Column(Integer, primary_key=True, index=True)
    item_id     = Column(String, nullable=False)
    quantity    = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)
    status      = Column(String, default="confirmed")

# Auto-instrument SQLAlchemy — every query becomes a child span automatically
SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

# ─────────────────────────────────────────────────────────────
# SERVICE URLS
# ─────────────────────────────────────────────────────────────
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://inventory-service:8001")
PAYMENT_URL   = os.getenv("PAYMENT_URL",   "http://payment-service:8002")

# ─────────────────────────────────────────────────────────────
# APP LIFESPAN — create DB table on startup
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Order service started — DB tables ready")
    yield
    await engine.dispose()

app = FastAPI(title="Order Service", lifespan=lifespan)

# Auto-instrument FastAPI — every request gets a root span automatically
FastAPIInstrumentor.instrument_app(app)

# Auto-instrument httpx — every outgoing HTTP call gets a child span automatically
# and injects traceparent header so downstream services join the same trace
HTTPXClientInstrumentor().instrument()

# Mount Prometheus /metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ─────────────────────────────────────────────────────────────
# REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────────────────────
class OrderRequest(BaseModel):
    item_id:      str
    quantity:     int
    slow_query:   bool = False   # Demo scenario: triggers slow inventory lookup
    fail_payment: bool = False   # Demo scenario: triggers payment failure

class OrderResponse(BaseModel):
    order_id:    int
    status:      str
    total_price: float
    trace_id:    str             # Returned so you can paste it straight into Tempo

# ─────────────────────────────────────────────────────────────
# MAIN ENDPOINT
# ─────────────────────────────────────────────────────────────
@app.post("/orders", response_model=OrderResponse)
async def create_order(order: OrderRequest):
    start_time = time.time()

    # Get the current trace ID so we can return it and embed it in logs
    current_span = trace.get_current_span()
    ctx           = current_span.get_span_context()
    trace_id_hex  = format(ctx.trace_id, "032x") if ctx.trace_id else "none"

    logger.info(f"Received order request — item_id={order.item_id} quantity={order.quantity} "
                f"slow_query={order.slow_query} fail_payment={order.fail_payment}")

    # Add useful attributes to the root span — visible in Tempo
    current_span.set_attribute("order.item_id",      order.item_id)
    current_span.set_attribute("order.quantity",     order.quantity)
    current_span.set_attribute("order.slow_query",   order.slow_query)
    current_span.set_attribute("order.fail_payment", order.fail_payment)

    async with httpx.AsyncClient() as client:

        # ── STEP 1: Check inventory ──────────────────────────
        with tracer.start_as_current_span("check-inventory") as inv_span:
            inv_span.set_attribute("inventory.item_id", order.item_id)
            inv_span.set_attribute("inventory.slow_query", order.slow_query)

            try:
                inv_response = await client.get(
                    f"{INVENTORY_URL}/stock/{order.item_id}",
                    params={"slow": order.slow_query},
                    timeout=10.0
                )
                inv_response.raise_for_status()
                stock = inv_response.json()

                inv_span.set_attribute("inventory.stock_available", stock["quantity"])
                logger.info(f"Inventory check OK — stock={stock['quantity']}")

                if stock["quantity"] < order.quantity:
                    inv_span.set_attribute("inventory.insufficient", True)
                    order_errors_counter.add(1, {"reason": "insufficient_stock"})
                    raise HTTPException(status_code=409, detail="Insufficient stock")

            except httpx.HTTPStatusError as e:
                inv_span.record_exception(e)
                inv_span.set_status(trace.StatusCode.ERROR, str(e))
                order_errors_counter.add(1, {"reason": "inventory_service_error"})
                logger.error(f"Inventory service error: {e}")
                raise HTTPException(status_code=502, detail="Inventory service error")

        # ── STEP 2: Process payment ──────────────────────────
        total_price = round(stock["unit_price"] * order.quantity, 2)

        with tracer.start_as_current_span("process-payment") as pay_span:
            pay_span.set_attribute("payment.amount",      total_price)
            pay_span.set_attribute("payment.item_id",     order.item_id)
            pay_span.set_attribute("payment.fail_forced", order.fail_payment)

            try:
                pay_response = await client.post(
                    f"{PAYMENT_URL}/charge",
                    json={
                        "amount":       total_price,
                        "item_id":      order.item_id,
                        "fail_payment": order.fail_payment,
                    },
                    timeout=10.0
                )
                pay_response.raise_for_status()
                payment = pay_response.json()

                pay_span.set_attribute("payment.transaction_id", payment["transaction_id"])
                logger.info(f"Payment OK — transaction_id={payment['transaction_id']} amount={total_price}")

            except httpx.HTTPStatusError as e:
                pay_span.record_exception(e)
                pay_span.set_status(trace.StatusCode.ERROR, str(e))
                order_errors_counter.add(1, {"reason": "payment_failed"})
                logger.error(f"Payment failed — amount={total_price} error={e}")
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail":   "Payment failed",
                        "trace_id": trace_id_hex,
                    }
                )

        # ── STEP 3: Save order to database ───────────────────
        with tracer.start_as_current_span("save-order-db") as db_span:
            async with AsyncSessionLocal() as session:
                new_order = Order(
                    item_id=order.item_id,
                    quantity=order.quantity,
                    total_price=total_price,
                    status="confirmed",
                )
                session.add(new_order)
                await session.commit()
                await session.refresh(new_order)

                db_span.set_attribute("db.order_id", new_order.id)
                logger.info(f"Order saved to DB — order_id={new_order.id}")

    # ── Record metrics ────────────────────────────────────────
    duration = time.time() - start_time
    order_counter.add(1, {"item_id": order.item_id, "status": "confirmed"})
    order_duration.record(duration, {"item_id": order.item_id})

    current_span.set_attribute("order.id",          new_order.id)
    current_span.set_attribute("order.total_price",  total_price)
    current_span.set_attribute("order.duration_s",   round(duration, 3))

    logger.info(f"Order completed — order_id={new_order.id} total={total_price} duration={round(duration,3)}s")

    return OrderResponse(
        order_id=new_order.id,
        status="confirmed",
        total_price=total_price,
        trace_id=trace_id_hex,   # paste this into Tempo's search box
    )


# ─────────────────────────────────────────────────────────────
# HEALTH + DEBUG ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/demo/scenarios")
async def demo_scenarios():
    """Quick reference — call this to remind yourself of all demo scenarios."""
    return {
        "normal_order": {
            "method": "POST",
            "url": "/orders",
            "body": {"item_id": "laptop", "quantity": 1},
            "shows": "Clean trace waterfall across all 3 services",
        },
        "slow_query": {
            "method": "POST",
            "url": "/orders",
            "body": {"item_id": "laptop", "quantity": 1, "slow_query": True},
            "shows": "Inventory span balloons — bottleneck clearly visible in Tempo",
        },
        "payment_failure": {
            "method": "POST",
            "url": "/orders",
            "body": {"item_id": "laptop", "quantity": 1, "fail_payment": True},
            "shows": "Red error span on payment-service, status=ERROR in trace",
        },
        "random_errors": {
            "method": "POST",
            "url": "/orders",
            "body": {"item_id": "laptop", "quantity": 1},
            "shows": "Run many requests — watch error rate rise in Grafana dashboard",
            "tip": "Use: for i in $(seq 50); do curl -s -X POST localhost:8000/orders -H 'Content-Type: application/json' -d '{\"item_id\":\"laptop\",\"quantity\":1}'; done",
        },
    }