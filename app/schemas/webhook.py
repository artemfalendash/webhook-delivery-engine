from datetime import datetime

from pydantic import BaseModel

class WebhookCreate(BaseModel):
    target_url: str
    secret_key: str
    event_type: str


class WebhookResponse(BaseModel):
    """What we send back after registering. No secret_key: secrets are never echoed back."""
    id: str
    target_url: str
    event_type: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
