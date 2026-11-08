from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4

import pytest

from backend.connected_app_contracts import MailDraftSpec, MailSendRequest
from backend.connected_app_payload_envelope import ConnectedActionPayloadEnvelope
from backend.connected_app_payload_resolution import (
    ConnectedActionPayloadResolver,
    ConnectedPayloadResolutionError,
)
from backend.connected_app_payload_vault import ConnectedPayloadRef
from backend.connected_app_policy import (
    ConnectedActionIntent,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = "00000000-0000-4000-8000-000000000001"
TASK = "00000000-0000-4000-8000-000000000002"
TURN = "00000000-0000-4000-8000-000000000003"
CONNECTION = "00000000-0000-4000-8000-000000000004"
ACTION = "00000000-0000-4000-8000-000000000005"
PAYLOAD = "00000000-0000-4000-8000-000000000006"
AUTH = "a" * 64
COMMITMENT = "b" * 64


def _request() -> MailSendRequest:
    return MailSendRequest.build(
        MailDraftSpec(
            ("recipient@example.com",),
            "Private subject",
            "Private body",
        )
    )


def _intent(*, parameters: str = COMMITMENT) -> ConnectedActionIntent:
    return ConnectedActionIntent.build(
        action_id=ACTION,
        owner_id=OWNER,
        task_id=TASK,
        turn_id=TURN,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        authorization_revision=1,
        authorization_snapshot_sha256=AUTH,
        action=ConnectorActionKind.MAIL_SEND,
        parameters_sha256=parameters,
        requested_at=NOW,
    )


def _reference(**changes) -> ConnectedPayloadRef:
    values = dict(
        payload_id=PAYLOAD,
        owner_id=OWNER,
        connection_id=CONNECTION,
        action_id=ACTION,
        provider=ConnectorProvider.GOOGLE,
        action=ConnectorActionKind.MAIL_SEND,
        commitment_key_id="commitment-key-1",
        payload_sha256=COMMITMENT,
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )
    values.update(changes)
    return ConnectedPayloadRef(**values)


class References:
    def __init__(self, reference: ConnectedPayloadRef | None) -> None:
        self.reference = reference
        self.calls = []

    async def resolve_reference(self, **values):
        self.calls.append(values)
        return self.reference


class Payloads:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls = []

    async def open_json(self, reference):
        self.calls.append(reference)
        return self.value


def _subject(reference=None, value=None):
    request = _request()
    references = References(reference if reference is not None else _reference())
    payloads = Payloads(
        value
        if value is not None
        else ConnectedActionPayloadEnvelope.build(
            action=ConnectorActionKind.MAIL_SEND,
            request=request,
        ).to_value()
    )
    return (
        ConnectedActionPayloadResolver(references=references, payloads=payloads),
        references,
        payloads,
    )


@pytest.mark.asyncio
async def test_resolver_recovers_owner_bound_reference_and_builds_private_invocation():
    subject, references, payloads = _subject()

    result = await subject.resolve(payload_id=PAYLOAD, intent=_intent())

    assert result.reference.payload_sha256 == COMMITMENT
    assert result.invocation.payload_sha256 == COMMITMENT
    assert result.invocation.request.target_binding_sha256 != COMMITMENT
    assert result.invocation.request_target_binding_sha256 == (
        result.invocation.request.target_binding_sha256
    )
    assert references.calls == [
        {
            "owner_id": OWNER,
            "payload_id": PAYLOAD,
            "connection_id": CONNECTION,
            "action_id": ACTION,
            "provider": ConnectorProvider.GOOGLE,
            "action": ConnectorActionKind.MAIL_SEND,
        }
    ]
    assert payloads.calls == [result.reference]
    assert "recipient@example.com" not in repr(result)
    assert "Private body" not in repr(subject)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reference",
    [
        _reference(owner_id="00000000-0000-4000-8000-000000000099"),
        _reference(connection_id="00000000-0000-4000-8000-000000000099"),
        _reference(action_id="00000000-0000-4000-8000-000000000099"),
        _reference(provider=ConnectorProvider.MICROSOFT),
        _reference(action=ConnectorActionKind.MAIL_CREATE_DRAFT),
        _reference(payload_sha256="c" * 64),
    ],
)
async def test_reference_identity_substitution_fails_before_decryption(reference):
    subject, _, payloads = _subject(reference=reference)

    with pytest.raises(ConnectedPayloadResolutionError) as raised:
        await subject.resolve(payload_id=PAYLOAD, intent=_intent())

    assert raised.value.code == "CONNECTED_PAYLOAD_BINDING_MISMATCH"
    assert payloads.calls == []


@pytest.mark.asyncio
async def test_missing_or_failed_reference_lookup_is_content_free():
    subject, _, _ = _subject(reference=None)
    subject._references.reference = None
    with pytest.raises(ConnectedPayloadResolutionError) as missing:
        await subject.resolve(payload_id=PAYLOAD, intent=_intent())
    assert missing.value.code == "CONNECTED_PAYLOAD_NOT_FOUND"

    class FailedReferences:
        async def resolve_reference(self, **_):
            raise RuntimeError("database detail with private content")

    subject = ConnectedActionPayloadResolver(
        references=FailedReferences(),
        payloads=Payloads({}),
    )
    with pytest.raises(ConnectedPayloadResolutionError) as failed:
        await subject.resolve(payload_id=PAYLOAD, intent=_intent())
    assert failed.value.code == "CONNECTED_PAYLOAD_UNAVAILABLE"
    assert "private" not in str(failed.value)


@pytest.mark.asyncio
async def test_envelope_target_or_action_tamper_is_rejected():
    request = _request()
    target_tamper = ConnectedActionPayloadEnvelope.build(
        action=ConnectorActionKind.MAIL_SEND,
        request=request,
    ).to_value()
    target_tamper["requestTargetBindingSha256"] = hashlib.sha256(b"sibling").hexdigest()
    subject, _, _ = _subject(value=target_tamper)
    with pytest.raises(ConnectedPayloadResolutionError) as target_error:
        await subject.resolve(payload_id=PAYLOAD, intent=_intent())
    assert target_error.value.code == "CONNECTED_PAYLOAD_BINDING_MISMATCH"

    action_tamper = ConnectedActionPayloadEnvelope.build(
        action=ConnectorActionKind.MAIL_SEND,
        request=request,
    ).to_value()
    action_tamper["action"] = ConnectorActionKind.MAIL_CREATE_DRAFT.value
    subject, _, _ = _subject(value=action_tamper)
    with pytest.raises(ConnectedPayloadResolutionError) as action_error:
        await subject.resolve(payload_id=PAYLOAD, intent=_intent())
    assert action_error.value.code == "CONNECTED_PAYLOAD_BINDING_MISMATCH"


@pytest.mark.asyncio
async def test_intent_commitment_substitution_fails_without_opening_payload():
    subject, _, payloads = _subject()
    with pytest.raises(ConnectedPayloadResolutionError) as raised:
        await subject.resolve(
            payload_id=PAYLOAD,
            intent=_intent(parameters="d" * 64),
        )
    assert raised.value.code == "CONNECTED_PAYLOAD_BINDING_MISMATCH"
    assert payloads.calls == []


def test_resolver_rejects_noncanonical_payload_id_and_bad_dependencies():
    with pytest.raises(TypeError):
        ConnectedActionPayloadResolver(references=object(), payloads=Payloads({}))
    subject, _, _ = _subject()
    with pytest.raises(ConnectedPayloadResolutionError) as raised:
        import asyncio

        asyncio.run(subject.resolve(payload_id=str(uuid4()).upper(), intent=_intent()))
    assert raised.value.code == "CONNECTED_PAYLOAD_INVALID"
