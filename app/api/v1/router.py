from fastapi import APIRouter
from app.api.v1.endpoints import events, webhooks, deliveries

api_router = APIRouter()
api_router.include_router(events.router, prefix="/events", tags=["Events"]) # tags= is for swagger UI
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"]) # tags= is for swagger UI
api_router.include_router(deliveries.router, prefix="/deliveries", tags=["Deliveries"]) # tags= is for swagger UI
