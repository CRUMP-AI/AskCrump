"""Gmail write adapter for the agent executor.

This module is the execution adapter behind the ``gmail.draft`` and
``gmail.send`` registry capabilities. It is deliberately not wired to
an HTTP route: the run service owns the approval lifecycle, freezes
the exact payload on the approval card, and the executor dispatches
approved runs to ``execute`` here.

Contract:

- The payload is validated against the registry entry's required
  fields. The field lists live in ``agent_registry`` only; this
  module reads them from the capability instead of duplicating them.
- Execution binds to ONE of the user's Google connections (see
  ``google_connector`` for the binding rule: a connection named in
  the payload binds, otherwise the default connection). A missing
  connection raises ``CONNECTION_REQUIRED``. The granted scopes of
  the BOUND connection alone are checked — never a union across
  connections — and when that record's grant lacks the capability's
  scope, ``execute`` raises ``INSUFFICIENT_SCOPE`` before any
  provider call. The provider call then runs with the bound
  connection's own token, resolved in the same step. When the record
  carries no scope information, the provider call runs and a Gmail
  403 ``insufficientPermissions`` response is mapped to the same code
  by the connector.
- The result is a redacted summary: the recipient domain, the
  subject length, and the provider draft/message ids. The body and
  the full recipient address never appear in a result.
"""
from __future__ import annotations

from typing import Any

from . import agent_registry
from .google_connector import (
    GoogleConnector,
    GoogleConnectorError,
    binding_selectors,
)

SUPPORTED_CAPABILITY_IDS = frozenset({'gmail.draft', 'gmail.send'})

__all__ = [
    'SUPPORTED_CAPABILITY_IDS',
    'GmailWriteAdapter',
    'execute',
]


def _default_connector() -> GoogleConnector:
    # Built lazily so importing this module never requires runtime
    # configuration; tests and the executor inject their own connector.
    from .google_vault import GoogleVault
    from .runtime import db, settings

    return GoogleConnector(settings=settings, db=db, vault=GoogleVault())


def _validate_payload(
    capability: agent_registry.Capability, payload: Any
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GoogleConnectorError(
            'Run input must be an object.', 'INVALID_PAYLOAD', 400
        )
    required = capability.input_schema.get('required') or []
    missing = [name for name in required if payload.get(name) in (None, '')]
    if missing:
        raise GoogleConnectorError(
            f"Missing required input: {', '.join(missing)}.",
            'INVALID_PAYLOAD',
            400,
        )
    return payload


def _recipient_domain(address: str) -> str:
    text = str(address or '').strip()
    if '@' not in text:
        return ''
    return text.rsplit('@', 1)[-1].strip().lower().rstrip('>')


async def _bound_access_token(
    connector: GoogleConnector,
    user_id: str,
    capability: agent_registry.Capability,
    payload: dict[str, Any],
) -> str | None:
    """Resolve the run's bound connection and return its token.

    The connector checks the capability's scopes against the bound
    connection's grant alone and raises ``CONNECTION_REQUIRED`` /
    ``INSUFFICIENT_SCOPE`` before any provider call. Returns None for
    connectors without bound access (test doubles), where the caller
    falls back to the plain user-scoped dispatch and the provider's
    own 403 mapping remains the scope gate.
    """
    bound_access = getattr(connector, 'bound_access_token', None)
    if bound_access is None:
        return None
    selectors = binding_selectors(payload)
    _connection, token = await bound_access(
        user_id,
        connection_id=selectors['connection_id'],
        account_email=selectors['account_email'],
        required_scopes=capability.required_scopes,
    )
    return str(token)


async def execute(
    capability_id: str,
    user_id: str,
    payload: Any,
    *,
    connector: GoogleConnector | None = None,
) -> dict[str, Any]:
    """Execute one approved ``gmail.draft`` or ``gmail.send`` run."""
    capability = agent_registry.get_capability(capability_id)
    if capability is None:
        raise GoogleConnectorError(
            'That capability is not available.', 'CAPABILITY_NOT_FOUND', 404
        )
    if capability.id not in SUPPORTED_CAPABILITY_IDS:
        raise GoogleConnectorError(
            f'This adapter does not execute {capability.id}.',
            'UNSUPPORTED_CAPABILITY',
            400,
        )
    data = _validate_payload(capability, payload)
    to = str(data.get('to') or '').strip()
    subject = str(data.get('subject') or '')
    body = str(data.get('body') or '')

    client = connector if connector is not None else _default_connector()
    access_token = await _bound_access_token(client, user_id, capability, data)

    if capability.id == 'gmail.draft':
        if access_token is not None:
            created = await client.create_draft_with_token(
                access_token, to=to, subject=subject, body=body
            )
        else:
            created = await client.create_draft(
                user_id, to=to, subject=subject, body=body
            )
        return {
            'capabilityId': capability.id,
            'status': 'draft_created',
            'draftId': created.get('id', ''),
            'messageId': created.get('messageId', ''),
            'threadId': created.get('threadId', ''),
            'recipientDomain': _recipient_domain(to),
            'subjectLength': len(subject),
        }
    if access_token is not None:
        sent = await client.send_message_with_token(
            access_token, to=to, subject=subject, body=body
        )
    else:
        sent = await client.send_message(user_id, to=to, subject=subject, body=body)
    return {
        'capabilityId': capability.id,
        'status': 'sent',
        'messageId': sent.get('id', ''),
        'threadId': sent.get('threadId', ''),
        'recipientDomain': _recipient_domain(to),
        'subjectLength': len(subject),
    }


class GmailWriteAdapter:
    """Class form of ``execute`` for executors that hold adapters."""

    def __init__(self, connector: GoogleConnector | None = None) -> None:
        self._connector = connector

    async def execute(
        self, capability_id: str, user_id: str, payload: Any
    ) -> dict[str, Any]:
        return await execute(
            capability_id, user_id, payload, connector=self._connector
        )
