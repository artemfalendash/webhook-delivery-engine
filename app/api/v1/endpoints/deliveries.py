import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
import app.models as models 
import redis.asyncio as aioredis
from app.core.redis import get_redis

router = APIRouter()

@router.post("/{delivery_id}/replay")
async def replay_dead_letter_delivery(delivery_id: str, sessionx: AsyncSession = Depends(get_db), redis_client: aioredis.Redis = Depends(get_redis)):
    
    result = await sessionx.execute(select(models.Delivery).where(models.Delivery.id == delivery_id))
    delivery = result.scalar_one_or_none()

    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    if delivery.status != "dead_letter":
        raise HTTPException(
            status_code=400, 
            detail=f"Only 'dead_letter' deliveries can be replayed. Current status: '{delivery.status}'"
        )

    # Reset exact schema columns
    delivery.status = "pending"
    delivery.attempt_number = 0

    payload = json.dumps({"delivery_id": str(delivery.id)})
    await redis_client.rpush("deliveries_queue", payload)

    await sessionx.commit()

    return {
        "status": "success",
        "message": f"Delivery {delivery_id} reset and re-queued into Redis.",
    }