from datetime import datetime
from typing import Any
from pydantic import BaseModel

class EventCreate(BaseModel):
    event_type: str
    payload: dict[str, Any]

class EventResponse(BaseModel):
    id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}  # Modern Pydantic v2 syntax

