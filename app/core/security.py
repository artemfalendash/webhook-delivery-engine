import hashlib
import hmac
import json
import time
from typing import Any, Dict


def serialize_payload(payload: Dict[str, Any]) -> bytes:
    """Turns the payload into the exact bytes we will send over the wire.

    Done ONCE per delivery: the same bytes get signed and sent, so the
    signature can never drift from the body (e.g. Cyrillic, emoji).
    """
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def generate_webhook_signature(secret_key: str, body: bytes) -> str:
    """Generates an HMAC SHA-256 signature header for the exact request body.

    Header format: t=<unix_timestamp>,v1=<hex_digest>
    """
    timestamp = int(time.time())

    # Combine timestamp and body to prevent replay attacks
    signed_payload = f"{timestamp}.".encode("utf-8") + body

    # Compute HMAC SHA-256 hex digest
    signature = hmac.new(
        key=secret_key.encode("utf-8"),
        msg=signed_payload,
        digestmod=hashlib.sha256
    ).hexdigest()

    return f"t={timestamp},v1={signature}"
