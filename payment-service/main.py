import os
import logging
import asyncio
import random
import uuid
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from prometheus_client import make_asgi_app

# ─────────────────────────────────────────────────────────────
# OTEL SETUP
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
from opentelemetry.instrumentation.logging import LoggingInstrumentor

SERVICE_NAME  = os.getenv("OTEL_SERVICE_NAME", "payment-service")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

resource = Resource.create({
    "service.name":           SERVICE_NAME,
    "service.version":        "1.0.0",
    "deployment.environment": "demo",
})

tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(SERVICE_NAME)

prometheus_reader  = PrometheusMetricReader()
otlp_metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True)
)
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[prometheus_reader, otlp_metric_reader]
)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(SERVICE_NAME)

# Custom metrics
payment_counter = meter.create_counter(
    "payments_total",
    description="Total payment attempts",
)
payment_failures = meter.create_counter(
    "payment_failures_total",
    description="Total payment failures",
)
payment_duration = meter.create_histogram(
    "payment_duration_seconds",
    description="Time taken to process a payment",
    unit="s",
)
payment_amount = meter.create_histogram(
    "payment_amount_dollars",
    description="Distribution of payment amounts",
    unit="$",
)

# Logger provider — ships logs to OTel Collector via gRPC
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)
set_logger_provider(logger_provider)

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
LoggingInstrumentor().instrument(set_logging_format=True, logger_provider=logger_provider)

# Attach OTLPHandler so Python log records are forwarded to the collector
from opentelemetry.sdk._logs import LoggingHandler as OTLPLoggingHandler
otlp_handler = OTLPLoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)
logging.getLogger().addHandler(otlp_handler)

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "service": "' + SERVICE_NAME + '", '
           '"trace_id": "%(otelTraceID)s", "span_id": "%(otelSpanID)s", "message": "%(message)s"}',
)
logger = logging.getLogger(SERVICE_NAME)

# ─────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────
app = FastAPI(title="Payment Service")
FastAPIInstrumentor.instrument_app(app)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# ─────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────
class ChargeRequest(BaseModel):
    amount:       float
    item_id:      str
    fail_payment: bool = False   # Demo scenario flag


class ChargeResponse(BaseModel):
    transaction_id: str
    status:         str
    amount:         float


# ─────────────────────────────────────────────────────────────
# CHARGE ENDPOINT
# ─────────────────────────────────────────────────────────────
@app.post("/charge", response_model=ChargeResponse)
async def charge(request: ChargeRequest):
    """
    Processes a payment charge.

    fail_payment=true  →  Demo scenario: simulates a payment gateway
                          rejection. The span is marked ERROR with a
                          full exception recorded — visible as a red
                          span in Tempo with the exception stacktrace.

    Random 10% failure →  Even without the flag, 1 in 10 requests
                          randomly fails to simulate real-world noise.
                          Run 20+ requests and watch the error rate
                          metric climb in the Grafana dashboard.
    """
    start = time.time()

    current_span = trace.get_current_span()
    current_span.set_attribute("payment.amount",       request.amount)
    current_span.set_attribute("payment.item_id",      request.item_id)
    current_span.set_attribute("payment.fail_forced",  request.fail_payment)

    logger.info(f"Payment charge started — amount={request.amount} item_id={request.item_id} fail_forced={request.fail_payment}")

    # ── Step 1: Validate the charge ──────────────────────────
    with tracer.start_as_current_span("validate-charge") as val_span:
        val_span.set_attribute("payment.amount",  request.amount)
        val_span.set_attribute("payment.item_id", request.item_id)

        if request.amount <= 0:
            val_span.set_status(trace.StatusCode.ERROR, "Invalid amount")
            val_span.record_exception(ValueError(f"Invalid amount: {request.amount}"))
            logger.error(f"Validation failed — invalid amount={request.amount}")
            payment_failures.add(1, {"reason": "invalid_amount"})
            return JSONResponse(status_code=400, content={"detail": "Amount must be greater than 0"})

        # Simulate brief validation time
        await asyncio.sleep(random.uniform(0.01, 0.03))
        val_span.set_attribute("validation.passed", True)
        logger.info(f"Validation passed — amount={request.amount}")

    # ── Step 2: Call simulated payment gateway ────────────────
    with tracer.start_as_current_span("payment-gateway-call") as gw_span:
        gw_span.set_attribute("gateway.provider",     "demo-stripe")
        gw_span.set_attribute("gateway.amount",       request.amount)
        gw_span.set_attribute("gateway.fail_forced",  request.fail_payment)

        # Simulate gateway network latency (50–150ms)
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # ── DEMO SCENARIO: forced failure ────────────────────
        # fail_payment=true always fails.
        # Additionally, 10% of requests fail randomly —
        # this creates organic error rate noise in Prometheus.
        should_fail = request.fail_payment or (random.random() < 0.10)

        if should_fail:
            failure_reason = "forced_by_demo_flag" if request.fail_payment else "random_gateway_rejection"

            # Record the exception ON the span — this is what creates
            # the red error span with stacktrace visible in Tempo
            error = Exception(
                f"Payment gateway rejected charge: amount={request.amount} "
                f"reason={failure_reason} item_id={request.item_id}"
            )
            gw_span.record_exception(error)
            gw_span.set_status(trace.StatusCode.ERROR, f"Gateway rejection: {failure_reason}")
            gw_span.set_attribute("gateway.failure_reason", failure_reason)
            gw_span.set_attribute("gateway.http_status",    402)

            payment_failures.add(1, {"reason": failure_reason, "item_id": request.item_id})
            payment_counter.add(1,  {"status": "failed", "item_id": request.item_id})

            duration = time.time() - start
            payment_duration.record(duration, {"status": "failed"})

            logger.error(
                f"Payment gateway REJECTED — amount={request.amount} "
                f"item_id={request.item_id} reason={failure_reason}"
            )

            return JSONResponse(
                status_code=402,
                content={
                    "detail":         "Payment declined by gateway",
                    "failure_reason": failure_reason,
                    "amount":         request.amount,
                }
            )

        # ── Happy path ───────────────────────────────────────
        transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
        gw_span.set_attribute("gateway.transaction_id", transaction_id)
        gw_span.set_attribute("gateway.http_status",    200)
        logger.info(f"Gateway approved — transaction_id={transaction_id} amount={request.amount}")

    # ── Step 3: Record the transaction ───────────────────────
    with tracer.start_as_current_span("record-transaction") as rec_span:
        rec_span.set_attribute("transaction.id",     transaction_id)
        rec_span.set_attribute("transaction.amount", request.amount)

        # Simulate brief write to payment ledger
        await asyncio.sleep(random.uniform(0.01, 0.04))
        rec_span.set_attribute("transaction.recorded", True)
        logger.info(f"Transaction recorded — transaction_id={transaction_id}")

    # ── Metrics ──────────────────────────────────────────────
    duration = time.time() - start
    payment_counter.add(1,    {"status": "success", "item_id": request.item_id})
    payment_duration.record(duration, {"status": "success"})
    payment_amount.record(request.amount, {"item_id": request.item_id})

    current_span.set_attribute("payment.transaction_id", transaction_id)
    current_span.set_attribute("payment.duration_s",     round(duration, 3))

    logger.info(
        f"Payment complete — transaction_id={transaction_id} "
        f"amount={request.amount} duration={round(duration, 3)}s"
    )

    return ChargeResponse(
        transaction_id=transaction_id,
        status="success",
        amount=request.amount,
    )


# ─────────────────────────────────────────────────────────────
# HEALTH + STATS ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/demo/failure-rate")
async def failure_rate_info():
    """Explains the random failure behaviour — useful during a demo."""
    return {
        "random_failure_rate": "10% of all requests fail randomly",
        "forced_failure":      "Set fail_payment=true in POST /orders to always fail",
        "tip": (
            "Send 20+ normal orders to generate organic error rate noise. "
            "Then open the Grafana dashboard and watch payment_failures_total climb. "
            "Click any spike → find the log → click trace_id → see the red span in Tempo."
        ),
    }