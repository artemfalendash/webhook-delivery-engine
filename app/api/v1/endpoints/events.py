from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
import app.models as models 
from app.schemas.event import EventCreate, EventResponse

import json
import redis.asyncio as aioredis
from app.core.redis import get_redis


router = APIRouter()

@router.post("", response_model=EventResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_event(event_in: EventCreate, sessionx: AsyncSession = Depends(get_db), redis: aioredis.Redis = Depends(get_redis)):

    new_event = models.Event(event_type=event_in.event_type, payload=event_in.payload)
    
    sessionx.add(new_event)
    await sessionx.commit()
    await sessionx.refresh(new_event)

    job_payload = json.dumps({"event_id": str(new_event.id)})
    await redis.rpush("events_queue", job_payload)
    
    return new_event
