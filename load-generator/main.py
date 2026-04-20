import asyncio
import random
import logging
import httpx
import os
from datetime import datetime

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8001")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [load-generator] %(levelname)s — %(message)s"
)
logger = logging.getLogger("load-generator")

# ─────────────────────────────────────────────────────────────
# AVAILABLE ITEMS
# ─────────────────────────────────────────────────────────────
ITEMS = ["laptop", "headphones", "keyboard", "monitor", "mouse"]

# ─────────────────────────────────────────────────────────────
# TRAFFIC PATTERNS
# Each pattern runs for a random duration then switches.
# This creates the kind of organic spikes you'd see in Grafana.
# ─────────────────────────────────────────────────────────────
PATTERNS = [
    {
        "name":        "normal",
        "description": "steady low traffic",
        "min_delay":   2.0,
        "max_delay":   5.0,
        "slow_query_chance":   0.05,   # 5%  chance of slow query
        "fail_payment_chance": 0.05,   # 5%  chance of forced payment fail
        "burst_chance":        0.0,    # no bursts
    },
    {
        "name":        "busy",
        "description": "high traffic — like a flash sale",
        "min_delay":   0.2,
        "max_delay":   1.0,
        "slow_query_chance":   0.10,
        "fail_payment_chance": 0.10,
        "burst_chance":        0.2,    # 20% chance of a burst of 5 requests
    },
    {
        "name":        "degraded",
        "description": "slow DB — bottleneck scenario",
        "min_delay":   1.0,
        "max_delay":   3.0,
        "slow_query_chance":   0.80,   # mostly slow queries
        "fail_payment_chance": 0.05,
        "burst_chance":        0.0,
    },
    {
        "name":        "payment_issues",
        "description": "payment gateway having problems",
        "min_delay":   1.0,
        "max_delay":   3.0,
        "slow_query_chance":   0.05,
        "fail_payment_chance": 0.70,   # mostly failing payments
        "burst_chance":        0.0,
    },
    {
        "name":        "quiet",
        "description": "off-hours — very low traffic",
        "min_delay":   5.0,
        "max_delay":   15.0,
        "slow_query_chance":   0.02,
        "fail_payment_chance": 0.02,
        "burst_chance":        0.0,
    },
]

# ─────────────────────────────────────────────────────────────
# HOW LONG EACH PATTERN RUNS (seconds)
# ─────────────────────────────────────────────────────────────
PATTERN_DURATION_MIN = 60    # at least 1 minute per pattern
PATTERN_DURATION_MAX = 300   # at most 5 minutes per pattern


async def send_order(client: httpx.AsyncClient, pattern: dict) -> None:
    item_id      = random.choice(ITEMS)
    quantity     = random.randint(1, 3)
    slow_query   = random.random() < pattern["slow_query_chance"]
    fail_payment = random.random() < pattern["fail_payment_chance"]

    try:
        response = await client.post(
            f"{ORDER_SERVICE_URL}/orders",
            json={
                "item_id":      item_id,
                "quantity":     quantity,
                "slow_query":   slow_query,
                "fail_payment": fail_payment,
            },
            timeout=15.0,
        )

        status = response.status_code
        body   = response.json()

        if status == 200:
            logger.info(
                f"OK     order_id={body.get('order_id')} "
                f"item={item_id} qty={quantity} "
                f"total={body.get('total_price')} "
                f"trace_id={body.get('trace_id', '')[:16]}..."
            )
        elif status == 402:
            logger.warning(
                f"FAIL   payment failed "
                f"item={item_id} qty={quantity} "
                f"trace_id={body.get('trace_id', '')[:16]}..."
            )
        elif status == 409:
            logger.warning(f"STOCK  insufficient stock item={item_id}")
        else:
            logger.warning(f"WARN   status={status} item={item_id}")

    except httpx.TimeoutException:
        logger.error(f"TIMEOUT  item={item_id} slow_query={slow_query}")
    except Exception as e:
        logger.error(f"ERROR  {e}")


async def run_burst(client: httpx.AsyncClient, pattern: dict) -> None:
    """Send 3-8 requests in quick succession to simulate a traffic spike."""
    burst_size = random.randint(3, 8)
    logger.info(f"BURST  sending {burst_size} rapid requests")
    tasks = [send_order(client, pattern) for _ in range(burst_size)]
    await asyncio.gather(*tasks)


async def clear_random_cache(client: httpx.AsyncClient) -> None:
    """Occasionally clear a cache entry to force DB path on next request."""
    item = random.choice(ITEMS)
    try:
        await client.delete(
            f"{INVENTORY_SERVICE_URL}/cache/{item}",
            timeout=5.0
        )
        logger.info(f"CACHE  cleared cache for {item}")
    except Exception:
        pass


async def main() -> None:
    logger.info("Load generator starting...")
    logger.info(f"Target: {ORDER_SERVICE_URL}")

    # Wait for order-service to be ready
    logger.info("Waiting 15s for services to be ready...")
    await asyncio.sleep(15)

    async with httpx.AsyncClient() as client:

        # Verify order service is up
        for attempt in range(10):
            try:
                resp = await client.get(f"{ORDER_SERVICE_URL}/health", timeout=5.0)
                if resp.status_code == 200:
                    logger.info("Order service is healthy — starting load generation")
                    break
            except Exception:
                logger.info(f"Waiting for order-service... attempt {attempt + 1}/10")
                await asyncio.sleep(5)

        request_count  = 0
        pattern_index  = 0

        while True:
            # Pick a pattern — mostly random but weighted toward normal
            pattern = random.choices(
                PATTERNS,
                weights=[40, 20, 15, 15, 10],  # normal, busy, degraded, payment_issues, quiet
                k=1
            )[0]

            duration = random.uniform(PATTERN_DURATION_MIN, PATTERN_DURATION_MAX)
            pattern_index += 1

            logger.info(
                f"━━━ Pattern #{pattern_index}: '{pattern['name']}' "
                f"({pattern['description']}) "
                f"for {int(duration)}s ━━━"
            )

            end_time = asyncio.get_event_loop().time() + duration

            while asyncio.get_event_loop().time() < end_time:
                # Send a burst occasionally
                if random.random() < pattern["burst_chance"]:
                    await run_burst(client, pattern)
                else:
                    await send_order(client, pattern)

                # Occasionally clear cache to make inventory take the slow path
                if random.random() < 0.05:
                    await clear_random_cache(client)

                request_count += 1

                # Random delay between requests
                delay = random.uniform(pattern["min_delay"], pattern["max_delay"])
                await asyncio.sleep(delay)

            logger.info(
                f"━━━ Pattern complete. Total requests sent: {request_count} ━━━"
            )

            # Short pause between patterns (2-10 seconds)
            gap = random.uniform(2, 10)
            logger.info(f"Pausing {int(gap)}s before next pattern...")
            await asyncio.sleep(gap)


if __name__ == "__main__":
    asyncio.run(main())