import asyncio
import json
import redis.asyncio as aioredis
from app.core.config import settings

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
import app.models as models


async def process_event(event_id: str, redis_client) -> None:
    async with AsyncSessionLocal() as sessionx:

        search_query = select(models.Event).where(models.Event.id == event_id)
        result = await sessionx.execute(search_query)
        event = result.scalar_one_or_none()

        if not event:
            print(f"⚠️ Event {event_id} not found in database. Skipping.")
            return

        # Look up active Webhooks matching event.event_type
        search_query = select(models.Webhook).where(models.Webhook.event_type == event.event_type, models.Webhook.is_active == True)
        result = await sessionx.execute(search_query)
        matching_webhooks = result.scalars().all()

        if not matching_webhooks:
            print(f" No active webhooks found for event_type '{event.event_type}'.")
            return

        # Create initial Delivery records in Postgres with status="pending"
        deliveries = []
        for webhook in matching_webhooks:
            delivery = models.Delivery(event_id=event.id, webhook_id=webhook.id)
            deliveries.append(delivery)

        sessionx.add_all(deliveries)
        await sessionx.commit()

        for delivery in deliveries:
            job_paylaod = json.dumps({"delivery_id": str(delivery.id)})
            await redis_client.rpush("deliveries_queue", job_paylaod)

        print(f"✅ Created {len(deliveries)} pending delivery record(s) for Event {event.id}!")


async def run_worker() -> None:
    print("🚀 Background Event Worker starting up...")

    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_timeout=None
    )

    print("🟢 Worker connected to Redis. Listening on 'events_queue'...")

    try:
        while True:
            try: 
                result = await redis_client.blpop("events_queue", timeout=0)

                if result:
                    queue_name, raw_job_data = result
                    job_data = json.loads(raw_job_data)
                    event_id = job_data.get("event_id")

                    if event_id:
                        print(f"⚡ [WORKER PICKED UP JOB] Event ID: {event_id}")
                        await process_event(event_id, redis_client)
                        
            except aioredis.TimeoutError:
                # Silently catch idle socket timeouts and continue listening
                continue

    except asyncio.CancelledError:
        print("🛑 Worker received shutdown signal.")
    finally:
        await redis_client.aclose()
        print("🔴 Worker connection closed.")


if __name__ == "__main__":
    asyncio.run(run_worker())


"""
Explanations:


Why create a Redis client inside the worker instead of get_redis()?

FastAPI's get_redis() relies on FastAPI's app state/lifespan created when Uvicorn boots the web server. 
The worker process runs in a completely separate OS process (a different terminal, different PID) outside of Uvicorn. 
Uvicorn and FastAPI do not exist inside this terminal process, so FastAPI's dependency injection does not exist here. 
The worker must open its own dedicated TCP socket connection to Redis.


blpop Breakdown
BLPOP stands for Blocking Left Pop:
B (Blocking): If the queue is empty, it freezes the connection and waits instead of returning None immediately.
L (Left): It pops elements from the left (head) of the list. 
Because FastAPI adds items to the right via RPUSH, popping from the left establishes a standard FIFO (First-In, First-Out) queue.
POP: It removes and returns the item from Redis RAM.

What timeout=0 Does
The timeout parameter defines how long Redis should wait for an item to appear before giving up:
timeout=0: Tells Redis to wait infinitely. 
The network connection stays open, and the worker sleeps silently with zero CPU usage until a new payload hits the queue.

timeout=10: Redis would wait 10 seconds. If no item arrives within 10 seconds, blpop returns None and finishes, 
forcing your while True loop to start a new iteration.


Is result a key-value pair?

No. result is a native Python 2-element tuple returned by Redis BLPOP. It looks like this:
Python
("events_queue", '{"event_id": "44a4bb8a-a2cc-4fe3-a3f9-6bf9e4761579"}')

Element 0: The name of the Redis queue key where the item was found ("events_queue").

Element 1: The raw JSON string value popped off the queue ('{"event_id": "..."}').


Tuple Unpacking & The Unused Variable

How two variables get assigned at once: Python supports iterable unpacking. 
When an expression on the right is a 2-item tuple ((A, B)), 
Python assigns index 0 to the first variable name and index 1 to the second automatically:

queue_name, raw_job_data = result
# queue_name = "events_queue"
# raw_job_data = '{"event_id": "..."}'
Why Redis gives us queue_name: BLPOP allows you to listen to multiple queues at once 
(e.g., blpop(["high_priority", "low_priority"], timeout=0)). 
Redis includes the queue name in the output so the consumer knows which queue delivered the item.


Function: json.loads stands for "load string". It performs deserialization—the exact reverse of json.dumps.
Input: The serialized string '{"event_id": "44a4..."}' (<class 'str'>).
Output: A native Python dictionary {"event_id": "44a4..."} (<class 'dict'>).


Why if __name__ == "__main__":?

__name__ is a special built-in variable set by the Python interpreter when a file is executed:

When you execute the file directly (python -m app.workers.event_worker): Python sets __name__ = "__main__". 
The condition evaluates to True, executing asyncio.run(run_worker()), which initializes the async event loop and executes the worker function.

If another file imports this script (import app.workers.event_worker): Python sets __name__ = "app.workers.event_worker". 
The condition evaluates to False, so the worker loop does not run automatically upon import.


"""
