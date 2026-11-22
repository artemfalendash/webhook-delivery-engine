import asyncio
import json
import time
import httpx
import redis.asyncio as aioredis
import app.models as models
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import generate_webhook_signature, serialize_payload
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.backoff import get_retry_delay
from app.core.redis import redis_client
from app.core.rate_limiter import extract_domain, is_rate_limited


MAX_RETRIES = 5


async def schedule_retry(redis_client, delivery_id: str, attempt_number: int):
    """Calculates backoff delay and pushes job into Redis ZSET."""
    delay = get_retry_delay(attempt_number)
    run_at_timestamp = time.time() + delay


    job_payload = json.dumps({"delivery_id": delivery_id})
    await redis_client.zadd("delayed_deliveries", {job_payload: run_at_timestamp})

    print(f"⏳ [RETRY SCHEDULED] Delivery {delivery_id} queued for attempt {attempt_number + 1} in {delay}s")


async def poll_delayed_queue(redis_client):
    """Background loop that moves matured retries from ZSET back to main queue."""
    while True:
        try:
            now = time.time()
            # Fetch jobs with score <= current timestamp
            ready_jobs = await redis_client.zrangebyscore(
                "delayed_deliveries", 0, now
            )

            for job in ready_jobs:
                # Use pipeline for atomic move
                pipe = redis_client.pipeline()
                pipe.zrem("delayed_deliveries", job)
                pipe.rpush("deliveries_queue", job)

                await pipe.execute()

                print(f"🔄 [RETRY MATURED] Delivery {job} moved back to {"deliveries_queue"}")

        except Exception as e:
            print(f"⚠️ Error in delayed queue poller: {e}")

        # Check every second
        await asyncio.sleep(1)


async def handle_delivery_failure(redis_client, sessionx, delivery: models.Delivery):
    """Handles failure state, increments attempts, and schedules retry or DLQ."""
    if delivery.attempt_number >= MAX_RETRIES:
        delivery.status = "dead_letter"
        await sessionx.commit()
        print(
            f"💀 [DEAD LETTER] Delivery {delivery.id} failed after {MAX_RETRIES} attempts."
        )
    else:
        await schedule_retry(redis_client, delivery.id, delivery.attempt_number)
        delivery.status = "pending"
        await sessionx.commit()


async def process_delivery(delivery_id: str, redis_client) -> None:
    async with AsyncSessionLocal() as sessionx:
        search_query = (
            select(models.Delivery)
            .where(models.Delivery.id == delivery_id)
            .options(
                selectinload(models.Delivery.webhook),
                selectinload(models.Delivery.event),
            )
        )
        result = await sessionx.execute(search_query)
        delivery = result.scalar_one_or_none()

        if not delivery:
            print(f"⚠️ Delivery record '{delivery_id}' not found.")
            return

        webhook = delivery.webhook
        event = delivery.event

        if not webhook or not event:
            print(f"⚠️ Webhook or Event relation missing for Delivery '{delivery_id}'.")
            return


        domain = extract_domain(webhook.target_url)

        if await is_rate_limited(redis_client, domain):
            print(f"⏳ [RATE LIMITED] {domain} reached limit. Postponing Delivery: {delivery_id}")

            now = int(time.time())

            job_payload = json.dumps({"delivery_id": delivery_id})
            await redis_client.zadd("delayed_deliveries", {job_payload: now + 2})
            
            return


        # Serialize once: these exact bytes are both signed and sent
        body = serialize_payload(event.payload)

        signature_header = generate_webhook_signature(
            secret_key=webhook.secret_key,
            body=body,
        )

        headers = {
            "Content-Type": "application/json",
            "X-Signature-256": signature_header,
            "User-Agent": "Webhook-Service/1.0",
        }

        delivery.attempt_number += 1

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook.target_url,
                    content=body,
                    headers=headers,
                )

            delivery.status_code = response.status_code
            delivery.response_body = response.text[:2000]  # Truncate large responses


            delivery_attempt = models.DeliveryAttempt(delivery_id=delivery.id, status_code=delivery.status_code, response_body=delivery.response_body, attempt_number=delivery.attempt_number)
            sessionx.add(delivery_attempt)


            if 200 <= response.status_code < 300:
                delivery.status = "success"
                print(f"✅ [SUCCESS] Delivery: {delivery_id} | Status: {response.status_code}")

            elif response.status_code >= 500 or response.status_code == 429:
                # Temporary problem (server error, or "too many requests, slow down") → retry later
                print(f"⚠️  [TEMPORARY ERROR {response.status_code}] Delivery: {delivery_id} -> Retrying")
                await handle_delivery_failure(redis_client, sessionx, delivery)

            else:
                # Permanent problem (e.g. 404 wrong URL) → retrying won't help, a human must look.
                # dead_letter so the admin replay button works after the client fixes it.
                delivery.status = "dead_letter"
                print(f"💀 [PERMANENT ERROR {response.status_code}] Delivery: {delivery_id} -> Dead letter")

        except httpx.RequestError as exc:
            delivery.status_code = None
            delivery.response_body = f"Network Exception: {str(exc)}"[:2000]

            delivery_attempt = models.DeliveryAttempt(delivery_id=delivery.id, status_code=delivery.status_code, response_body=delivery.response_body, attempt_number=delivery.attempt_number)
            sessionx.add(delivery_attempt)

            print(f"💥 [NETWORK ERROR] Delivery: {delivery_id} | Error: {exc}")

            await handle_delivery_failure(redis_client, sessionx, delivery)

        await sessionx.commit()


async def run_delivery_worker() -> None:
    print("🚀 Background Delivery Worker starting up...")


    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_timeout=None,  # Prevents TCP socket timeouts while waiting on BLPOP
    )

    asyncio.create_task(poll_delayed_queue(redis_client))

    print("🟢 Delivery Worker connected to Redis. Listening on 'deliveries_queue'...")

    try:
        while True:
            try:
                result = await redis_client.blpop("deliveries_queue", timeout=0)

                if result:
                    queue_name, raw_job_data = result
                    job_data = json.loads(raw_job_data)
                    delivery_id = job_data.get("delivery_id")

                    if delivery_id:
                        await process_delivery(delivery_id, redis_client)

            except aioredis.TimeoutError:
                continue

    except asyncio.CancelledError:
        print("🛑 Delivery Worker received shutdown signal.")
    finally:
        await redis_client.aclose()
        print("🔴 Delivery Worker connection closed.")

if __name__ == "__main__":
    asyncio.run(run_delivery_worker())
