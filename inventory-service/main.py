import os
import logging
import asyncio
import json
import random

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
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
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

SERVICE_NAME  = os.getenv("OTEL_SERVICE_NAME", "inventory-service")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

resource = Resource.create({
    "service.name":            SERVICE_NAME,
    "service.version":         "1.0.0",
    "deployment.environment":  "demo",
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
cache_hits   = meter.create_counter("inventory_cache_hits_total",   description="Redis cache hits")
cache_misses = meter.create_counter("inventory_cache_misses_total",  description="Redis cache misses")
lookup_duration = meter.create_histogram(
    "inventory_lookup_duration_seconds",
    description="Time taken for stock lookup (cache + db)",
    unit="s",
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
# REDIS
# ─────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Auto-instrument Redis — every Redis call becomes a child span
RedisInstrumentor().instrument()

# ─────────────────────────────────────────────────────────────
# SIMULATED STOCK DATABASE
# In a real service this would be a DB query. Here we keep it
# simple so the demo focuses on tracing, not data modelling.
# ─────────────────────────────────────────────────────────────
STOCK_DB = {
    "laptop":     {"quantity": 50,  "unit_price": 999.99},
    "headphones": {"quantity": 120, "unit_price":  79.99},
    "keyboard":   {"quantity": 30,  "unit_price":  49.99},
    "monitor":    {"quantity": 15,  "unit_price": 299.99},
    "mouse":      {"quantity": 200, "unit_price":  29.99},
}

# ─────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────
app = FastAPI(title="Inventory Service")
FastAPIInstrumentor.instrument_app(app)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

redis_client: aioredis.Redis = None

@app.on_event("startup")
async def startup():
    global redis_client
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Inventory service started — Redis connected")

@app.on_event("shutdown")
async def shutdown():
    await redis_client.aclose()


# ─────────────────────────────────────────────────────────────
# STOCK ENDPOINT
# ─────────────────────────────────────────────────────────────
@app.get("/stock/{item_id}")
async def get_stock(item_id: str, slow: bool = False):
    """
    Returns stock level for an item.

    slow=true  →  Demo scenario: simulates a slow DB query (2s delay).
                  In Tempo you will see this span take 2s while all
                  other spans are <100ms — the bottleneck is obvious.
    """
    import time
    start = time.time()

    current_span = trace.get_current_span()
    current_span.set_attribute("inventory.item_id",   item_id)
    current_span.set_attribute("inventory.slow_mode",  slow)

    logger.info(f"Stock lookup started — item_id={item_id} slow={slow}")

    # ── Step 1: Try Redis cache first ────────────────────────
    with tracer.start_as_current_span("redis-cache-lookup") as cache_span:
        cache_span.set_attribute("cache.key", f"stock:{item_id}")

        cached = await redis_client.get(f"stock:{item_id}")

        if cached:
            cache_hits.add(1, {"item_id": item_id})
            cache_span.set_attribute("cache.hit", True)
            logger.info(f"Cache HIT — item_id={item_id}")
            stock = json.loads(cached)

        else:
            cache_misses.add(1, {"item_id": item_id})
            cache_span.set_attribute("cache.hit", False)
            logger.info(f"Cache MISS — item_id={item_id} — falling back to DB lookup")

            # ── Step 2: Simulate DB lookup ───────────────────
            with tracer.start_as_current_span("db-stock-lookup") as db_span:
                db_span.set_attribute("db.table",   "inventory")
                db_span.set_attribute("db.item_id", item_id)
                db_span.set_attribute("db.slow_query_forced", slow)

                if slow:
                    # ── DEMO SCENARIO: slow query ─────────────
                    # This is the bottleneck detection scenario.
                    # The 2s sleep makes this span dominate the
                    # trace waterfall — instantly visible in Tempo.
                    db_span.add_event("slow_query_triggered", {
                        "reason": "demo scenario — simulating missing index",
                        "delay_ms": 2000,
                    })
                    logger.warning(f"SLOW QUERY triggered — item_id={item_id} — sleeping 2s")
                    await asyncio.sleep(2)
                else:
                    # Normal DB lookup latency (20–80ms)
                    await asyncio.sleep(random.uniform(0.02, 0.08))

                # Look up in our simulated stock DB
                if item_id not in STOCK_DB:
                    db_span.set_attribute("db.found", False)
                    db_span.set_status(trace.StatusCode.ERROR, f"Item not found: {item_id}")
                    logger.warning(f"Item not found — item_id={item_id}")
                    return JSONResponse(status_code=404, content={"detail": f"Item '{item_id}' not found"})

                stock = STOCK_DB[item_id]
                db_span.set_attribute("db.found",    True)
                db_span.set_attribute("db.quantity", stock["quantity"])

                # Cache the result for 60 seconds
                await redis_client.setex(
                    f"stock:{item_id}",
                    60,
                    json.dumps(stock)
                )
                logger.info(f"DB lookup complete — item_id={item_id} quantity={stock['quantity']} cached for 60s")

    # ── Record lookup duration metric ─────────────────────────
    duration = time.time() - start
    lookup_duration.record(duration, {"item_id": item_id, "cache_hit": str(cached is not None)})
    current_span.set_attribute("inventory.lookup_duration_s", round(duration, 3))

    logger.info(f"Stock lookup complete — item_id={item_id} quantity={stock['quantity']} duration={round(duration,3)}s")

    return {
        "item_id":    item_id,
        "quantity":   stock["quantity"],
        "unit_price": stock["unit_price"],
    }


# ─────────────────────────────────────────────────────────────
# ADMIN ENDPOINTS (useful during demo)
# ─────────────────────────────────────────────────────────────
@app.delete("/cache/{item_id}")
async def clear_cache(item_id: str):
    """Clear Redis cache for an item — forces a DB lookup on next request."""
    await redis_client.delete(f"stock:{item_id}")
    logger.info(f"Cache cleared for item_id={item_id}")
    return {"message": f"Cache cleared for {item_id}"}


@app.get("/stock")
async def list_stock():
    """List all available items — handy for demo setup."""
    return {"items": list(STOCK_DB.keys()), "tip": "Use any of these as item_id in POST /orders"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}