from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from zoneinfo import ZoneInfo

import pytest

from backend.connected_app_contracts import (
    CalendarCancelRequest,
    EventSnapshot,
    MailDraftSpec,
    MailSendRequest,
)
from backend.connected_app_payload_envelope import ConnectedActionPayloadEnvelope
from backend.connected_app_payload_vault import ConnectedPayloadRef
from backend.connected_app_policy import ConnectorActionKind, ConnectorProvider
from backend.connected_app_review_resolution import (
    ConnectedApprovalPreviewVaultResolver,
    ConnectedApprovalReviewEnvelope,
    ConnectedReviewResolutionError,
)
from backend.connected_app_service import (
    ConnectedCalendarReviewPayload,
    ConnectedMailReviewPayload,
)


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = "00000000-0000-4000-8000-000000000001"
CONNECTION = "00000000-0000-4000-8000-000000000002"
ACTION = "00000000-0000-4000-8000-000000000003"
APPROVAL = "00000000-0000-4000-8000-000000000004"
PAYLOAD = "00000000-0000-4000-8000-000000000005"
PARAMETERS = "a" * 64
PREVIEW = "b" * 64
APPROVAL_BINDING = "c" * 64


class References:
    def __init__(self, reference):
        self.reference = reference

    async def resolve_reference(self, **_):
        return self.reference


class Payloads:
    def __init__(self, value):
        self.value = value

    async def open_json(self, _reference):
        return self.value


def _reference(action: ConnectorActionKind) -> ConnectedPayloadRef:
    return ConnectedPayloadRef(
        payload_id=PAYLOAD,
        owner_id=OWNER,
        connection_id=CONNECTION,
        action_id=ACTION,
        provider=ConnectorProvider.GOOGLE,
        action=action,
        commitment_key_id="preview-key-1",
        payload_sha256=PREVIEW,
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )


def _mail_envelope() -> ConnectedApprovalReviewEnvelope:
    request = MailSendRequest.build(
        MailDraftSpec(("recipient@example.com",), "Private subject", "Private body")
    )
    return ConnectedApprovalReviewEnvelope(
        approval_id=APPROVAL,
        action_id=ACTION,
        connection_id=CONNECTION,
        parameters_sha256=PARAMETERS,
        resource_version_sha256=None,
        action_payload=ConnectedActionPayloadEnvelope.build(
            action=ConnectorActionKind.MAIL_SEND,
            request=request,
        ),
        review_payload=ConnectedMailReviewPayload(
            account=CONNECTION,
            to=request.spec.to,
            cc=request.spec.cc,
            bcc=request.spec.bcc,
            subject=request.spec.subject,
            body_text=request.spec.body_text,
            reply_context=None,
        ),
    )


@pytest.mark.asyncio
async def test_mail_preview_round_trips_from_encrypted_owner_bound_record():
    envelope = _mail_envelope()
    subject = ConnectedApprovalPreviewVaultResolver(
        references=References(_reference(ConnectorActionKind.MAIL_SEND)),
        payloads=Payloads(envelope.to_value()),
    )

    preview = await subject.resolve(
        owner_id=OWNER,
        approval_id=APPROVAL,
        connection_id=CONNECTION,
        action_id=ACTION,
        provider=ConnectorProvider.GOOGLE,
        action=ConnectorActionKind.MAIL_SEND,
        approval_binding_sha256=APPROVAL_BINDING,
        parameters_sha256=PARAMETERS,
        resource_version_sha256=None,
        review_payload_ref=PAYLOAD,
        preview_sha256=PREVIEW,
    )

    assert preview.parameters_sha256 == PARAMETERS
    assert preview.preview_sha256 == PREVIEW
    assert preview.payload.body_text == "Private body"
    assert preview.request_target_binding_sha256 != PARAMETERS
    assert "recipient@example.com" not in repr(subject)
    assert "Private body" not in repr(envelope)


def _calendar_cancel_envelope() -> ConnectedApprovalReviewEnvelope:
    zone = ZoneInfo("America/New_York")
    starts = datetime(2026, 11, 9, 14, 0, tzinfo=zone)
    ends = starts + timedelta(minutes=30)
    request = CalendarCancelRequest.build(
        calendar_id="primary",
        event_id="event-1",
        expected_resource_version="etag-1",
    )
    event = EventSnapshot(
        event_id="event-1",
        calendar_id="primary",
        resource_version="etag-1",
        starts_at=starts,
        ends_at=ends,
        time_zone="America/New_York",
        title="Planning",
        attendees=("recipient@example.com",),
    )
    return ConnectedApprovalReviewEnvelope(
        approval_id=APPROVAL,
        action_id=ACTION,
        connection_id=CONNECTION,
        parameters_sha256=PARAMETERS,
        resource_version_sha256=hashlib.sha256(b"etag-1").hexdigest(),
        action_payload=ConnectedActionPayloadEnvelope.build(
            action=ConnectorActionKind.CALENDAR_CANCEL,
            request=request,
        ),
        review_payload=ConnectedCalendarReviewPayload(
            calendar="primary",
            event_context="event-1",
            title="Planning",
            start=starts.isoformat(),
            end=ends.isoformat(),
            time_zone="America/New_York",
            attendees=("recipient@example.com",),
            location="",
            description="",
        ),
        authoritative_event=event,
    )


@pytest.mark.asyncio
async def test_calendar_cancel_requires_authoritative_snapshot_inside_ciphertext():
    envelope = _calendar_cancel_envelope()
    restored = ConnectedApprovalReviewEnvelope.from_value(envelope.to_value())
    subject = ConnectedApprovalPreviewVaultResolver(
        references=References(_reference(ConnectorActionKind.CALENDAR_CANCEL)),
        payloads=Payloads(restored.to_value()),
    )

    preview = await subject.resolve(
        owner_id=OWNER,
        approval_id=APPROVAL,
        connection_id=CONNECTION,
        action_id=ACTION,
        provider=ConnectorProvider.GOOGLE,
        action=ConnectorActionKind.CALENDAR_CANCEL,
        approval_binding_sha256=APPROVAL_BINDING,
        parameters_sha256=PARAMETERS,
        resource_version_sha256=hashlib.sha256(b"etag-1").hexdigest(),
        review_payload_ref=PAYLOAD,
        preview_sha256=PREVIEW,
    )

    assert preview.payload.event_context == "event-1"
    assert restored.authoritative_event.resource_version == "etag-1"


@pytest.mark.asyncio
async def test_reference_commitment_owner_and_approval_substitution_fail_closed():
    envelope = _mail_envelope()
    subject = ConnectedApprovalPreviewVaultResolver(
        references=References(_reference(ConnectorActionKind.MAIL_SEND)),
        payloads=Payloads(envelope.to_value()),
    )
    with pytest.raises(ConnectedReviewResolutionError) as wrong_commitment:
        await subject.resolve(
            owner_id=OWNER,
            approval_id=APPROVAL,
            connection_id=CONNECTION,
            action_id=ACTION,
            provider=ConnectorProvider.GOOGLE,
            action=ConnectorActionKind.MAIL_SEND,
            approval_binding_sha256=APPROVAL_BINDING,
            parameters_sha256=PARAMETERS,
            resource_version_sha256=None,
            review_payload_ref=PAYLOAD,
            preview_sha256="d" * 64,
        )
    assert wrong_commitment.value.code == "CONNECTED_PREVIEW_BINDING_MISMATCH"

    with pytest.raises(ConnectedReviewResolutionError) as wrong_approval:
        await subject.resolve(
            owner_id=OWNER,
            approval_id="00000000-0000-4000-8000-000000000099",
            connection_id=CONNECTION,
            action_id=ACTION,
            provider=ConnectorProvider.GOOGLE,
            action=ConnectorActionKind.MAIL_SEND,
            approval_binding_sha256=APPROVAL_BINDING,
            parameters_sha256=PARAMETERS,
            resource_version_sha256=None,
            review_payload_ref=PAYLOAD,
            preview_sha256=PREVIEW,
        )
    assert wrong_approval.value.code == "CONNECTED_PREVIEW_BINDING_MISMATCH"


def test_plaintext_review_substitution_is_rejected_before_envelope_creation():
    envelope = _mail_envelope()
    with pytest.raises(ValueError, match="derived from the provider request"):
        ConnectedApprovalReviewEnvelope(
            approval_id=envelope.approval_id,
            action_id=envelope.action_id,
            connection_id=envelope.connection_id,
            parameters_sha256=envelope.parameters_sha256,
            resource_version_sha256=None,
            action_payload=envelope.action_payload,
            review_payload=ConnectedMailReviewPayload(
                account=CONNECTION,
                to=("attacker@example.com",),
                cc=(),
                bcc=(),
                subject="Private subject",
                body_text="Private body",
                reply_context=None,
            ),
        )
