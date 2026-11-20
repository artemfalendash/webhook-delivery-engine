"""
Tests for the front door: POST /api/v1/events and POST /api/v1/webhooks.

Uses the fixtures from conftest.py: a test client that calls the API directly,
an isolated test database, and an isolated Redis (DB 1).
"""
import json

from sqlalchemy import select

import app.models as models

EVENTS_URL = "/api/v1/events"
WEBHOOKS_URL = "/api/v1/webhooks"


async def test_post_event_returns_202_accepted(client):
    response = await client.post(EVENTS_URL, json={"event_type": "order.paid", "payload": {"amount": 10}})

    assert response.status_code == 202
    body = response.json()
    assert body["event_type"] == "order.paid"
    assert body["payload"] == {"amount": 10}
    assert body["id"]


async def test_post_event_saves_it_to_the_database(client, db_sessionx):
    response = await client.post(EVENTS_URL, json={"event_type": "order.paid", "payload": {"amount": 10}})
    event_id = response.json()["id"]

    event = (await db_sessionx.execute(select(models.Event).where(models.Event.id == event_id))).scalar_one()
    assert event.event_type == "order.paid"


async def test_post_event_puts_a_job_in_the_events_queue(client, redis_clientx):
    response = await client.post(EVENTS_URL, json={"event_type": "order.paid", "payload": {"amount": 10}})
    event_id = response.json()["id"]

    jobs = await redis_clientx.lrange("events_queue", 0, -1)
    assert jobs == [json.dumps({"event_id": event_id})]


async def test_invalid_event_is_rejected_and_nothing_is_queued(client, redis_clientx):
    response = await client.post(EVENTS_URL, json={"payload": {"amount": 10}})  # no event_type

    assert response.status_code == 422
    assert await redis_clientx.llen("events_queue") == 0


async def test_register_webhook_returns_its_id(client):
    response = await client.post(
        WEBHOOKS_URL,
        json={"target_url": "https://client.test/hook", "secret_key": "s3cret", "event_type": "order.paid"},
    )

    assert response.status_code == 201
    assert response.json() is not None and response.json().get("id")


async def test_register_webhook_never_sends_the_secret_back(client):
    response = await client.post(
        WEBHOOKS_URL,
        json={"target_url": "https://client.test/hook", "secret_key": "s3cret", "event_type": "order.paid"},
    )

    assert "secret_key" not in response.json()
    assert "s3cret" not in response.text
