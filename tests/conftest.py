from typing import AsyncGenerator

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.main import app
from app.core.database import Base, get_db

import redis.asyncio as aioredis
from app.core.redis import get_redis



# DB 1, not DB 0 — same Redis server, separate logical database,
# same "two drawers, one cabinet" idea as distribution_api_test.
TEST_REDIS_URL = "redis://redis:6379/1"



# Note: "db" here (not "localhost") because tests run INSIDE the api container,
# same as your real DATABASE_URL — same reason Alembic needed "db" too.
# Separate database name so tests never touch your real dev data.
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/distribution_api_test"

# NullPool = open a fresh connection every time, never reuse one.
# Each test runs in its own event loop, and a reused connection from a
# previous test's loop crashes ("attached to a different loop").
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_sessionx() -> AsyncGenerator[AsyncSession, None]:
    """Fresh tables for every test, wiped clean after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as sessionx:
        yield sessionx

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def redis_clientx() -> AsyncGenerator[aioredis.Redis, None]:
    """Isolated Redis client for tests — DB 1, never touches your real DB 0 queues."""
    rclient = aioredis.from_url(TEST_REDIS_URL, encoding="utf-8", decode_responses=True)
    await rclient.flushdb()  # start clean in case a previous run left leftovers
    yield rclient
    await rclient.flushdb()  # clean up after
    await rclient.aclose()


@pytest_asyncio.fixture
async def client(db_sessionx: AsyncSession, redis_clientx: aioredis.Redis) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client that hits your FastAPI app directly — no real network, no real server."""

    async def override_get_db():
        yield db_sessionx

    async def override_get_redis():
    # No "yield" here — get_redis returns a value directly, doesn't generate one.
        return redis_clientx

    app.dependency_overrides[get_db] = override_get_db # because endpoints use get_db and we test endpoints
    app.dependency_overrides[get_redis] = override_get_redis


    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def workers_use_test_db(db_sessionx: AsyncSession, monkeypatch) -> AsyncSession:
    """Workers don't use FastAPI's get_db — they open sessions themselves via AsyncSessionLocal.
    So instead of a dependency override, we swap that name inside the worker modules
    for the test database's session maker. Depends on db_sessionx so the tables exist.
    """
    import app.workers.event_worker as event_worker
    import app.workers.delivery_worker as delivery_worker

    monkeypatch.setattr(event_worker, "AsyncSessionLocal", TestingSessionLocal)
    monkeypatch.setattr(delivery_worker, "AsyncSessionLocal", TestingSessionLocal)
    return db_sessionx











