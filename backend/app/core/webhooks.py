"""Outbound, HMAC-signed webhooks for ATS / integration partners (Phase 8).

Delivery is best-effort and retried through the background job queue, so a
partner outage never blocks a recruiter action. Every request is signed with
HMAC-SHA256 over ``"<timestamp>.<body>"`` using a per-job secret; partners must
verify the ``X-AIC-Signature: sha256=<hex>`` header against the raw body before
trusting the payload, and should reject stale timestamps.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

DELIVERY_TIMEOUT_SECONDS = 10.0
SIGNATURE_HEADER = "X-AIC-Signature"
TIMESTAMP_HEADER = "X-AIC-Timestamp"
EVENT_HEADER = "X-AIC-Event"
MAX_ATTEMPTS_HINT = 5
# Background-queue job type that delivers a queued ATS webhook.
ATS_WEBHOOK_JOB = "ats.webhook"


def sign(secret: str, body: bytes, timestamp: str) -> str:
    """Return the hex HMAC-SHA256 of ``"<timestamp>.<body>"``."""
    message = timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


@dataclass
class WebhookDelivery:
    url: str
    event: str
    payload: dict
    secret: str


class WebhookSender:
    """POSTs one delivery. Raises on a transport error or a non-2xx response.

    A fresh client per delivery keeps this dependency-free of the app's event
    loop lifecycle; deliveries are low-volume (one per recruiter decision).
    """

    async def send(self, delivery: WebhookDelivery) -> int:
        body = json.dumps(delivery.payload, separators=(",", ":"), default=str).encode()
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            EVENT_HEADER: delivery.event,
            TIMESTAMP_HEADER: timestamp,
            SIGNATURE_HEADER: f"sha256={sign(delivery.secret, body, timestamp)}",
        }
        async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
            response = await client.post(delivery.url, content=body, headers=headers)
        # Any non-2xx is a delivery failure the queue should retry.
        response.raise_for_status()
        return response.status_code


webhook_sender = WebhookSender()
