from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.redis import close_redis, init_redis


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Open the Redis connection when the app starts, close it when the app stops."""
    await init_redis()
    try:
        yield
    finally:
        await close_redis()


app = FastAPI(title="Event Dispatch & Webhook Delivery Engine", lifespan=lifespan)
app.include_router(api_router, prefix="/api/v1")
