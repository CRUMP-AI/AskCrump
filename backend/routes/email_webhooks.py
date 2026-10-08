"""Signed, privacy-minimized transactional email delivery callbacks."""
from __future__ import annotations

import asyncio
import binascii
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from svix.webhooks import Webhook, WebhookVerificationError

from ..runtime import db, settings


logger = logging.getLogger('askcrump.email_webhooks')
router = APIRouter(prefix='/api/webhooks', tags=['webhooks'])

_MESSAGE_KINDS = frozenset({'verification', 'password_reset'})
_OUTCOMES = {
    'email.sent': 'accepted',
    'email.delivered': 'delivered',
    'email.delivery_delayed': 'transient',
    'email.failed': 'failed',
    'email.suppressed': 'suppressed',
    'email.complained': 'complaint',
}
_BOUNCE_OUTCOMES = {
    'Permanent': 'permanent',
    'Transient': 'transient',
    'Undetermined': 'failed',
}
_SUPPORTED_EVENTS = frozenset((*_OUTCOMES, 'email.bounced'))
_PERSISTENCE_DEADLINE_SECONDS = 4.0


class InvalidResendEvent(ValueError):
    """The signed callback is not a valid supported Resend delivery event."""


def _sha256_text(namespace: str, value: str) -> str:
    return hashlib.sha256(f'{namespace}:{value}'.encode('utf-8')).hexdigest()


def _occurred_at(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise InvalidResendEvent('Invalid event timestamp.')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise InvalidResendEvent('Invalid event timestamp.') from exc
    if parsed.tzinfo is None:
        raise InvalidResendEvent('Invalid event timestamp.')
    return parsed.astimezone(timezone.utc).isoformat()


def _message_kind(data: dict[str, Any]) -> str | None:
    tags = data.get('tags')
    if not isinstance(tags, dict):
        return None
    value = tags.get('message_kind')
    return value if value in _MESSAGE_KINDS else None


def _normalize_event(payload: Any, delivery_id: str, raw_body: bytes) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        raise InvalidResendEvent('Invalid webhook payload.')

    event_type = payload.get('type')
    if not isinstance(event_type, str):
        raise InvalidResendEvent('Invalid webhook payload.')
    if event_type not in _SUPPORTED_EVENTS:
        return None

    data = payload.get('data')
    if not isinstance(data, dict):
        raise InvalidResendEvent('Invalid webhook payload.')
    message_kind = _message_kind(data)
    if message_kind is None:
        # A signed event without Ask Crump's allowlisted tag may belong to a
        # different sender workflow. Acknowledge it without retaining it.
        return None

    provider_email_id = data.get('email_id')
    if (
        not isinstance(provider_email_id, str)
        or not provider_email_id
        or len(provider_email_id) > 256
    ):
        raise InvalidResendEvent('Invalid webhook payload.')

    if event_type == 'email.bounced':
        bounce = data.get('bounce')
        bounce_type = bounce.get('type') if isinstance(bounce, dict) else None
        outcome_class = _BOUNCE_OUTCOMES.get(bounce_type)
        if outcome_class is None:
            raise InvalidResendEvent('Invalid bounce classification.')
    else:
        outcome_class = _OUTCOMES[event_type]

    return {
        'p_provider_event_hash': _sha256_text('resend-event', delivery_id),
        'p_provider_email_hash': _sha256_text('resend-email', provider_email_id),
        'p_payload_fingerprint': hashlib.sha256(raw_body).hexdigest(),
        'p_environment': settings.environment,
        'p_message_kind': message_kind,
        'p_event_type': event_type,
        'p_outcome_class': outcome_class,
        'p_occurred_at': _occurred_at(payload.get('created_at')),
    }


@router.post('/resend', status_code=204)
async def resend_delivery_webhook(request: Request) -> Response:
    secret = settings.resend_webhook_secret
    if not secret:
        return JSONResponse(
            status_code=503,
            content={'success': False, 'error': 'Email delivery webhook is not configured.'},
        )

    raw_body = await request.body()
    signature_headers = {
        'svix-id': request.headers.get('svix-id', ''),
        'svix-timestamp': request.headers.get('svix-timestamp', ''),
        'svix-signature': request.headers.get('svix-signature', ''),
    }
    if not all(signature_headers.values()):
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Invalid webhook signature.'},
        )

    try:
        Webhook(secret).verify(raw_body, signature_headers)
    except (WebhookVerificationError, ValueError, binascii.Error, UnicodeDecodeError):
        logger.warning('Rejected Resend webhook with an invalid signature')
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Invalid webhook signature.'},
        )

    try:
        payload = json.loads(raw_body)
        record = _normalize_event(payload, signature_headers['svix-id'], raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError, InvalidResendEvent):
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Invalid webhook payload.'},
        )

    if record is None:
        return Response(status_code=204)

    try:
        # Resend owns delivery retries. Bound this idempotent write to one short
        # attempt so an unhealthy database produces a prompt retryable 503.
        async with asyncio.timeout(_PERSISTENCE_DEADLINE_SECONDS):
            await db.rpc('record_resend_delivery_event', record, timeout=3.0)
    except Exception:
        logger.exception(
            'Resend delivery event persistence failed event_type=%s message_kind=%s',
            record['p_event_type'],
            record['p_message_kind'],
        )
        return JSONResponse(
            status_code=503,
            content={'success': False, 'error': 'Webhook persistence unavailable.'},
        )

    return Response(status_code=204)
