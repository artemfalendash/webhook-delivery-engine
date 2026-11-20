"""
Tests for the event worker (app/workers/event_worker.py → process_event).

Job of the worker: take 1 event, find who's subscribed, create one pending
Delivery per subscriber, and put each delivery's job into deliveries_queue.
We call process_event directly — no infinite loop, no blpop.
"""
import json

from sqlalchemy import select

import app.models as models
from app.workers.event_worker import process_event


async def add_webhook(session, event_type="order.paid", is_active=True):
    webhook = models.Webhook(
        target_url="https://client.test/hook",
        secret_key="s3cret",
        event_type=event_type,
        is_active=is_active,
    )
    session.add(webhook)
    await session.commit()
    return webhook


async def add_event(session, event_type="order.paid"):
    event = models.Event(event_type=event_type, payload={"amount": 10})
    session.add(event)
    await session.commit()
    return event


async def get_deliveries(session):
    return (await session.execute(select(models.Delivery))).scalars().all()


async def test_one_event_creates_one_pending_delivery_per_subscriber(workers_use_test_db, redis_clientx):
    db = workers_use_test_db
    await add_webhook(db)
    await add_webhook(db)
    event = await add_event(db)

    await process_event(event.id, redis_clientx)

    deliveries = await get_deliveries(db)
    assert len(deliveries) == 2
    assert all(d.status == "pending" and d.event_id == event.id for d in deliveries)


async def test_each_delivery_gets_a_job_in_deliveries_queue(workers_use_test_db, redis_clientx):
    db = workers_use_test_db
    await add_webhook(db)
    await add_webhook(db)
    event = await add_event(db)

    await process_event(event.id, redis_clientx)

    jobs = await redis_clientx.lrange("deliveries_queue", 0, -1)
    queued_ids = {json.loads(job)["delivery_id"] for job in jobs}
    assert queued_ids == {d.id for d in await get_deliveries(db)}


async def test_only_active_webhooks_of_the_same_event_type_get_a_delivery(workers_use_test_db, redis_clientx):
    db = workers_use_test_db
    match = await add_webhook(db, event_type="order.paid", is_active=True)
    await add_webhook(db, event_type="order.paid", is_active=False)      # turned off
    await add_webhook(db, event_type="user.created", is_active=True)     # different event type
    event = await add_event(db, event_type="order.paid")

    await process_event(event.id, redis_clientx)

    deliveries = await get_deliveries(db)
    assert [d.webhook_id for d in deliveries] == [match.id]


async def test_event_with_no_subscribers_creates_nothing(workers_use_test_db, redis_clientx):
    db = workers_use_test_db
    event = await add_event(db, event_type="nobody.cares")

    await process_event(event.id, redis_clientx)

    assert await get_deliveries(db) == []
    assert await redis_clientx.llen("deliveries_queue") == 0


async def test_unknown_event_id_is_skipped_without_crashing(workers_use_test_db, redis_clientx):
    await process_event("does-not-exist", redis_clientx)

    assert await get_deliveries(workers_use_test_db) == []
