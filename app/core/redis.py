import redis.asyncio as aioredis
from app.core.config import settings

redis_client: aioredis.Redis | None = None


async def init_redis() -> None:
    """Initialize Redis connection pool on app startup."""
    global redis_client
    redis_client = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True,)


async def close_redis() -> None:
    """Close Redis connection pool on app shutdown."""
    global redis_client
    if redis_client: 
        await redis_client.aclose()


async def get_redis() -> aioredis.Redis:
    """Dependency / Helper to retrieve active Redis client."""
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized.")
    return redis_client
