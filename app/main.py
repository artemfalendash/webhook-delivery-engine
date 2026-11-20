from fastapi import FastAPI
from app.api.v1.router import api_router
from contextlib import asynccontextmanager
from app.core.redis import init_redis, close_redis




@asynccontextmanager
async def lifespan(_app: FastAPI): #explanation below
    await init_redis()
    try:
        yield
    finally:
        await close_redis()

"""
Why "_app: FastAPI" Is Required Even If Unused
You asked: If we don't use app inside lifespan, why the fuck is it even passed?

It comes down to the ASGI Specification (the low-level protocol FastAPI, Starlette, and Uvicorn use to communicate):
The protocol strictly mandates that every lifespan handler MUST accept app as its first positional argument.

Under the hood, Uvicorn/Starlette calls lifespan(app). Whether you use app inside your block or ignore it, Starlette passes it anyway.

VS Code dims app because static analysis sees an unused variable. 
If it annoys you, in Python convention you can name it _app — the underscore tells VS Code and other devs: 
"I am required by the framework to accept this argument, but I'm deliberately ignoring it.
"""


""" 
@asynccontextmanager & lifespan= kwarg explanation

Okay, so the final explanation is this: it is the case, where the kwarg takes the blueprint of the function without () 
so it doesn't run right away, therefore the kwarg and the decorator must work together so when server is started 
the kwarg does the work of running the function, then the yield pauses it, and then when the app shuts down
since the kwarg was the one to run the function, it gets back to the decorator and says "the server has shut down, Ima let you know that",
so then that decorator unpauses that yield, and the "finally" runs.
"""







app = FastAPI(title="Event Dispatch & Webhook Delivery Engine", lifespan=lifespan)
app.include_router(api_router, prefix="/api/v1")



"""
# Instrustion: 

#1 
python -m uvicorn app.main:app --reload

#2 
redis-server

#3 
python -m app.workers.event_worker

#4
python -m app.workers.delivery_worker

"""



# python -m uvicorn app.main:app --reload





# Alembic migrations:
# python -m alembic revision --autogenerate -m "..."
# python -m alembic upgrade head

"""
def upgrade() -> None:
    # Drop in order of dependencies (child table first, then parents)
    op.drop_table("deliveries")
    op.drop_table("events")
    op.drop_table("webhooks")

"""



# redis-server
# redis-cli ping
# redis-cli lrange events_queue 0 -1
# redis-cli --raw lrange events_queue 0 -1


# python -m app.workers.event_worker

# python -m app.workers.delivery_worker




# docker compose up -d --build
# docker compose exec api alembic upgrade head







# docker compose logs -f event_worker

# docker compose logs -f delivery_worker

# The -f flag means "follow" — same idea as tail -f if you've ever heard of it — it keeps streaming new lines live instead of dumping the log once and exiting.




