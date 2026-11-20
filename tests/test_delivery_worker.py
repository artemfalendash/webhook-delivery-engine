"""
Tests for the delivery worker (app/workers/delivery_worker.py → process_delivery).

respx plays the CLIENT'S SERVER: we script how it answers (200, 500, network
failure) — no real internet, no real waiting for retry timers.
"""
import json

import httpx
import pytest
from sqlalchemy import select

import app.models as models
from app.workers.delivery_worker import MAX_RETRIES, process_delivery
from tests.test_signatures import client_verifies

TARGET_URL = "https://client.test/hook"
SECRET = "s3cret"


@pytest.fixture
def db(workers_use_test_db):
    return workers_use_test_db


async def make_delivery(db, payload=None, attempt_number=0):
    """One webhook + one event + one pending delivery, like the event worker would create."""
    webhook = models.Webhook(target_url=TARGET_URL, secret_key=SECRET, event_type="order.paid")
    event = models.Event(event_type="order.paid", payload=payload or {"amount": 10})
    db.add_all([webhook, event])
    await db.commit()

    delivery = models.Delivery(webhook_id=webhook.id, event_id=event.id, attempt_number=attempt_number)
    db.add(delivery)
    await db.commit()
    return delivery


async def reload(db, delivery_id):
    """Read the delivery fresh from the database (the worker changed it in its own session)."""
    query = select(models.Delivery).where(models.Delivery.id == delivery_id).execution_options(populate_existing=True)
    return (await db.execute(query)).scalar_one()


async def count_attempts(db, delivery_id):
    query = select(models.DeliveryAttempt).where(models.DeliveryAttempt.delivery_id == delivery_id)
    return len((await db.execute(query)).scalars().all())


async def scheduled_retries(redis):
    return [json.loads(job)["delivery_id"] for job in await redis.zrange("delayed_deliveries", 0, -1)]


# ---------- Success ----------

async def test_2xx_marks_delivery_as_success(db, redis_clientx, respx_mock):
    respx_mock.post(TARGET_URL).mock(return_value=httpx.Response(200, text="ok"))
    delivery = await make_delivery(db)

    await process_delivery(delivery.id, redis_clientx)

    delivery = await reload(db, delivery.id)
    assert delivery.status == "success"
    assert delivery.status_code == 200
    assert delivery.attempt_number == 1
    assert await count_attempts(db, delivery.id) == 1


async def test_client_can_verify_the_signature_of_what_actually_arrives(db, redis_clientx, respx_mock):
    """The other half of the Cyrillic fix: the REAL outgoing request verifies on the client's side."""
    route = respx_mock.post(TARGET_URL).mock(return_value=httpx.Response(200))
    delivery = await make_delivery(db, payload={"status": "Замовлення оплачено", "amount": 10})

    await process_delivery(delivery.id, redis_clientx)

    sent = route.calls.last.request
    assert client_verifies(SECRET, sent.headers["X-Signature-256"], sent.content)


# ---------- Temporary failures → retry ----------

async def test_5xx_schedules_a_retry_and_stays_pending(db, redis_clientx, respx_mock):
    respx_mock.post(TARGET_URL).mock(return_value=httpx.Response(500))
    delivery = await make_delivery(db)

    await process_delivery(delivery.id, redis_clientx)

    delivery = await reload(db, delivery.id)
    assert delivery.status == "pending"
    assert delivery.attempt_number == 1
    assert await scheduled_retries(redis_clientx) == [delivery.id]


async def test_network_error_schedules_a_retry(db, redis_clientx, respx_mock):
    respx_mock.post(TARGET_URL).mock(side_effect=httpx.ConnectError("client server is down"))
    delivery = await make_delivery(db)

    await process_delivery(delivery.id, redis_clientx)

    delivery = await reload(db, delivery.id)
    assert delivery.status == "pending"
    assert await scheduled_retries(redis_clientx) == [delivery.id]
    assert await count_attempts(db, delivery.id) == 1


# ---------- Giving up → dead letter ----------

async def test_last_allowed_failure_moves_delivery_to_dead_letter(db, redis_clientx, respx_mock):
    respx_mock.post(TARGET_URL).mock(return_value=httpx.Response(500))
    delivery = await make_delivery(db, attempt_number=MAX_RETRIES - 1)  # 4 failures already

    await process_delivery(delivery.id, redis_clientx)

    delivery = await reload(db, delivery.id)
    assert delivery.status == "dead_letter"
    assert delivery.attempt_number == MAX_RETRIES
    assert await scheduled_retries(redis_clientx) == []  # no more retries


# ---------- Permanent client errors (4xx) ----------

async def test_4xx_goes_straight_to_dead_letter_without_retrying(db, redis_clientx, respx_mock):
    """404 = wrong URL. Waiting won't fix it, only a human will → dead letter, so it can be replayed later."""
    respx_mock.post(TARGET_URL).mock(return_value=httpx.Response(404))
    delivery = await make_delivery(db)

    await process_delivery(delivery.id, redis_clientx)

    delivery = await reload(db, delivery.id)
    assert delivery.status == "dead_letter"
    assert await scheduled_retries(redis_clientx) == []


async def test_429_too_many_requests_is_retried_later(db, redis_clientx, respx_mock):
    """429 = 'slow down, try later'. That's temporary, so it must be retried like a 5xx."""
    respx_mock.post(TARGET_URL).mock(return_value=httpx.Response(429))
    delivery = await make_delivery(db)

    await process_delivery(delivery.id, redis_clientx)

    delivery = await reload(db, delivery.id)
    assert delivery.status == "pending"
    assert await scheduled_retries(redis_clientx) == [delivery.id]


# ---------- Outbound rate limiting ----------

async def test_rate_limited_delivery_is_postponed_without_sending_or_counting_an_attempt(
    db, redis_clientx, respx_mock, monkeypatch
):
    import app.workers.delivery_worker as delivery_worker

    async def always_limited(*args, **kwargs):
        return True

    monkeypatch.setattr(delivery_worker, "is_rate_limited", always_limited)
    route = respx_mock.post(TARGET_URL).mock(return_value=httpx.Response(200))
    delivery = await make_delivery(db)

    await process_delivery(delivery.id, redis_clientx)

    delivery = await reload(db, delivery.id)
    assert not route.called                      # nothing was sent
    assert delivery.attempt_number == 0          # not counted as a failure
    assert await scheduled_retries(redis_clientx) == [delivery.id]  # will try again shortly


async def test_rate_limiter_allows_10_per_second_per_domain_then_blocks(redis_clientx, monkeypatch):
    from app.core import rate_limiter

    monkeypatch.setattr(rate_limiter.time, "time", lambda: 1_700_000_000)  # freeze the clock in one second

    results = [await rate_limiter.is_rate_limited(redis_clientx, "client.test") for _ in range(11)]
    assert results == [False] * 10 + [True]

    # A different domain has its own separate limit
    assert await rate_limiter.is_rate_limited(redis_clientx, "other.test") is False


# ---------- Admin replay ----------

async def test_replay_puts_a_dead_letter_delivery_back_in_the_queue(client, db_sessionx, redis_clientx):
    delivery = await make_delivery(db_sessionx, attempt_number=MAX_RETRIES)
    delivery.status = "dead_letter"
    await db_sessionx.commit()

    response = await client.post(f"/api/v1/deliveries/{delivery.id}/replay")

    assert response.status_code == 200
    delivery = await reload(db_sessionx, delivery.id)
    assert delivery.status == "pending"
    assert delivery.attempt_number == 0
    jobs = await redis_clientx.lrange("deliveries_queue", 0, -1)
    assert jobs == [json.dumps({"delivery_id": delivery.id})]


async def test_replay_refuses_deliveries_that_are_not_dead_letter(client, db_sessionx):
    delivery = await make_delivery(db_sessionx)  # still pending

    response = await client.post(f"/api/v1/deliveries/{delivery.id}/replay")

    assert response.status_code == 400
