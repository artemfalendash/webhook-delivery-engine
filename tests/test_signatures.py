"""
Tests for HMAC signing (app/core/security.py).

These play the role of the CLIENT: they take the signature header we produce
and verify it the way a real receiving server would, against the body bytes.
"""
import hashlib
import hmac

from app.core.security import generate_webhook_signature, serialize_payload

SECRET = "super-secret-key"


def client_verifies(secret: str, signature_header: str, body: bytes) -> bool:
    """What the client's server does: recompute the fingerprint and compare."""
    parts = dict(item.split("=", 1) for item in signature_header.split(","))
    timestamp, received_sig = parts["t"], parts["v1"]

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, received_sig)


def test_header_format():
    header = generate_webhook_signature(SECRET, serialize_payload({"amount": 10}))

    assert header.startswith("t=")
    assert ",v1=" in header
    assert len(header.split("v1=")[1]) == 64  # SHA-256 hex digest is 64 chars


def test_client_accepts_genuine_webhook():
    body = serialize_payload({"event": "order.paid", "amount": 10})
    header = generate_webhook_signature(SECRET, body)

    assert client_verifies(SECRET, header, body)


def test_client_rejects_tampered_payload():
    header = generate_webhook_signature(SECRET, serialize_payload({"amount": 10}))
    tampered_body = serialize_payload({"amount": 1000})  # attacker edits it in transit

    assert not client_verifies(SECRET, header, tampered_body)


def test_client_rejects_wrong_secret():
    body = serialize_payload({"amount": 10})
    header = generate_webhook_signature("attacker-guess", body)

    assert not client_verifies(SECRET, header, body)


def test_client_accepts_non_ascii_payload():
    """Real businesses send Cyrillic, accents, emoji. Signature must still verify."""
    body = serialize_payload({"status": "Замовлення оплачено", "amount": 10})
    header = generate_webhook_signature(SECRET, body)

    # Real UTF-8 letters on the wire, not З-style escapes
    assert "Замовлення".encode("utf-8") in body
    assert client_verifies(SECRET, header, body)
