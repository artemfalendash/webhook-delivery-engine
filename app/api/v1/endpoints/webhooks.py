from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
import app.models as models
from app.schemas.webhook import WebhookCreate, WebhookResponse


router = APIRouter()


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(payload: WebhookCreate, sessionx: AsyncSession = Depends(get_db)):
    new_webhook = models.Webhook(
        target_url=payload.target_url,
        secret_key=payload.secret_key,
        event_type=payload.event_type,
    )
    sessionx.add(new_webhook)
    await sessionx.commit()
    await sessionx.refresh(new_webhook)

    return new_webhook
