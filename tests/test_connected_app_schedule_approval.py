from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.connected_app_contracts import MailDraftSpec, MailSendRequest
from backend.connected_app_payload_envelope import ConnectedActionPayloadEnvelope
from backend.connected_app_payload_vault import ConnectedPayloadRef
from backend.connected_app_policy import (
    ConnectedActionIntent,
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_schedule_approval import (
    ConnectedScheduleApprovalCoordinator,
    ConnectedScheduleApprovalRecord,
    ConnectedScheduleApprovalStatus,
    SupabaseConnectedScheduleApprovalStore,
)
from backend.connected_app_scheduler import ConnectedScheduleClaim, ConnectedSchedulerError


NOW = datetime(2026, 11, 8, 8, 0, tzinfo=UTC)
OWNER = "96600000-0000-4000-8000-000000000001"
SCHEDULE = "96600000-0000-4000-8000-000000000002"
CONNECTION = "96600000-0000-4000-8000-000000000003"
TASK = "96600000-0000-4000-8000-000000000004"
TURN = "96600000-0000-4000-8000-000000000005"
TEMPLATE = "96600000-0000-4000-8000-000000000006"
CLAIM = "96600000-0000-4000-8000-000000000007"
OCCURRENCE = "96600000-0000-4000-8000-000000000008"
ACTION = "96600000-0000-4000-8000-000000000009"
APPROVAL = "96600000-0000-4000-8000-000000000010"
PREVIEW = "96600000-0000-4000-8000-000000000011"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def payload() -> ConnectedActionPayloadEnvelope:
    return ConnectedActionPayloadEnvelope.build(
        action=ConnectorActionKind.MAIL_SEND,
        request=MailSendRequest.build(
            MailDraftSpec(
                to=("client@example.test",),
                subject="Scheduled update",
                body_text="Private scheduled body",
            )
        ),
    )


def claim() -> ConnectedScheduleClaim:
    return ConnectedScheduleClaim(
        schedule_id=SCHEDULE,
        owner_id=OWNER,
        connection_id=CONNECTION,
        task_id=TASK,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEND,
        action_template_ref=TEMPLATE,
        parameters_sha256=SHA_A,
        task_state_revision=3,
        time_zone="UTC",
        cadence_seconds=3600,
        quiet_start_minute=None,
        quiet_end_minute=None,
        requires_approval_every_run=True,
        scheduled_for=NOW - timedelta(minutes=1),
        claim_id=CLAIM,
        claimed_at=NOW,
        claim_expires_at=NOW + timedelta(minutes=2),
        turn_id=TURN,
        grant_id=CLAIM,
        plan_payload_id="96600000-0000-4000-8000-000000000012",
        plan_reference_binding_sha256=SHA_B,
        authorization_revision=4,
        authorization_snapshot_sha256=SHA_C,
        granted_actions_sha256=SHA_D,
        granted_scopes_sha256=SHA_B,
        template_reference_binding_sha256=SHA_C,
        resource_version_sha256=None,
        occurrence_id=OCCURRENCE,
        occurrence_action_id=ACTION,
        occurrence_approval_id=APPROVAL,
        occurrence_created_at=NOW - timedelta(seconds=10),
    )


def intent(value: ConnectedScheduleClaim | None = None) -> ConnectedActionIntent:
    value = value or claim()
    return ConnectedActionIntent.build(
        action_id=ACTION,
        owner_id=OWNER,
        task_id=TASK,
        turn_id=TURN,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        authorization_revision=4,
        authorization_snapshot_sha256=SHA_C,
        action=ConnectorActionKind.MAIL_SEND,
        parameters_sha256=SHA_A,
        requested_at=value.occurrence_created_at,
    )


def record(
    *,
    status: ConnectedScheduleApprovalStatus,
    binding: str = SHA_D,
) -> ConnectedScheduleApprovalRecord:
    decided = NOW if status in {
        ConnectedScheduleApprovalStatus.APPROVED,
        ConnectedScheduleApprovalStatus.DENIED,
    } else None
    return ConnectedScheduleApprovalRecord(
        occurrence_id=OCCURRENCE,
        schedule_id=SCHEDULE,
        owner_id=OWNER,
        approval_id=APPROVAL,
        action_id=ACTION,
        task_id=TASK,
        turn_id=TURN,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEND,
        authorization_revision=4,
        authorization_snapshot_sha256=SHA_C,
        granted_scopes_sha256=SHA_B,
        policy_version=ConnectedActionPolicy.version,
        action_revision=3,
        approval_class=ConnectedActionPolicy.requirement(
            ConnectorActionKind.MAIL_SEND
        ).approval_class,
        approval_binding_sha256=binding,
        parameters_sha256=SHA_A,
        resource_version_sha256=None,
        preview_sha256=SHA_C,
        review_payload_ref=PREVIEW,
        status=status,
        occurrence_created_at=NOW - timedelta(seconds=10),
        expires_at=NOW + timedelta(minutes=14, seconds=50),
        decided_at=decided,
        approved_at=(NOW if status is ConnectedScheduleApprovalStatus.APPROVED else None),
        consumed_at=None,
    )


class Vault:
    def __init__(self) -> None:
        self.values: list[object] = []

    async def seal_json(self, **kwargs):
        self.values.append(kwargs["value"])
        return ConnectedPayloadRef(
            payload_id=PREVIEW,
            owner_id=kwargs["owner_id"],
            connection_id=kwargs["connection_id"],
            action_id=kwargs["action_id"],
            provider=kwargs["provider"],
            action=kwargs["action"],
            commitment_key_id="preview-commitment",
            payload_sha256=SHA_C,
            created_at=kwargs["created_at"],
            expires_at=kwargs["expires_at"],
        )


class Store:
    def __init__(self, current=None, *, lose_response=False) -> None:
        self.current = current
        self.puts = 0
        self.lose_response = lose_response

    async def read(self, *, owner_id, occurrence_id):
        assert owner_id == OWNER
        assert occurrence_id == OCCURRENCE
        return self.current

    async def put_pending(self, **kwargs):
        self.puts += 1
        self.current = record(
            status=ConnectedScheduleApprovalStatus.PENDING,
            binding=kwargs["approval_binding_sha256"],
        )
        if self.lose_response:
            raise TimeoutError("stored but response lost")
        return self.current


@pytest.mark.asyncio
async def test_first_poll_creates_one_encrypted_pending_preview_and_no_authority():
    store, vault = Store(), Vault()
    coordinator = ConnectedScheduleApprovalCoordinator(
        store=store, payload_vault=vault, now=lambda: NOW
    )

    result = await coordinator.fresh_approval(
        claim=claim(), intent=intent(), action_payload=payload()
    )

    assert result is None
    assert store.puts == 1
    assert len(vault.values) == 1
    assert "Private scheduled body" not in repr(store.current)
    assert "Private scheduled body" in str(vault.values[0])

    second = await coordinator.fresh_approval(
        claim=claim(), intent=intent(), action_payload=payload()
    )
    assert second is None
    assert store.puts == 1
    assert len(vault.values) == 1


@pytest.mark.asyncio
async def test_put_response_loss_recovers_exact_pending_record_without_second_write():
    store, vault = Store(lose_response=True), Vault()
    coordinator = ConnectedScheduleApprovalCoordinator(
        store=store, payload_vault=vault, now=lambda: NOW
    )

    assert await coordinator.fresh_approval(
        claim=claim(), intent=intent(), action_payload=payload()
    ) is None
    assert store.puts == 1


@pytest.mark.asyncio
async def test_approved_occurrence_from_between_worker_claims_is_current_and_one_use():
    approved = record(status=ConnectedScheduleApprovalStatus.APPROVED)
    coordinator = ConnectedScheduleApprovalCoordinator(
        store=Store(approved), payload_vault=Vault(), now=lambda: NOW + timedelta(seconds=1)
    )

    evidence = await coordinator.fresh_approval(
        claim=replace(
            claim(),
            claimed_at=NOW + timedelta(seconds=1),
            claim_expires_at=NOW + timedelta(minutes=2, seconds=1),
        ),
        intent=intent(),
        action_payload=payload(),
    )

    assert evidence is not None
    assert evidence.approval_id == APPROVAL
    assert evidence.action_id == ACTION

    consumed = replace(approved, consumed_at=NOW + timedelta(seconds=1))
    consumed_coordinator = ConnectedScheduleApprovalCoordinator(
        store=Store(consumed), payload_vault=Vault(), now=lambda: NOW + timedelta(seconds=2)
    )
    assert await consumed_coordinator.fresh_approval(
        claim=claim(), intent=intent(), action_payload=payload()
    ) is None


@pytest.mark.asyncio
async def test_cross_owner_or_action_record_fails_closed():
    changed = replace(record(status=ConnectedScheduleApprovalStatus.APPROVED), owner_id=(
        "96600000-0000-4000-8000-000000000099"
    ))
    coordinator = ConnectedScheduleApprovalCoordinator(
        store=Store(changed), payload_vault=Vault(), now=lambda: NOW
    )
    with pytest.raises(ConnectedSchedulerError, match="FRESH_APPROVAL_REQUIRED"):
        await coordinator.fresh_approval(
            claim=claim(), intent=intent(), action_payload=payload()
        )


def test_terminal_approved_occurrence_is_ui_readable_but_never_reusable():
    executed = replace(
        record(status=ConnectedScheduleApprovalStatus.APPROVED),
        status=ConnectedScheduleApprovalStatus.EXECUTED,
        consumed_at=NOW + timedelta(seconds=1),
    )
    cancelled = replace(
        record(status=ConnectedScheduleApprovalStatus.APPROVED),
        status=ConnectedScheduleApprovalStatus.CANCELLED,
    )

    assert executed.evidence() is None
    assert cancelled.evidence() is None


class Database:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def rpc(self, function, params, *, retry_transient=False):
        self.calls.append((function, params, retry_transient))
        return self.rows[function]


def row(value: ConnectedScheduleApprovalRecord) -> dict[str, object]:
    return {
        "occurrence_id": value.occurrence_id,
        "schedule_id": value.schedule_id,
        "owner_id": value.owner_id,
        "approval_id": value.approval_id,
        "action_id": value.action_id,
        "task_id": value.task_id,
        "turn_id": value.turn_id,
        "connection_id": value.connection_id,
        "provider": value.provider.value,
        "resource": value.resource.value,
        "action": value.action.value,
        "authorization_revision": value.authorization_revision,
        "authorization_snapshot_sha256": value.authorization_snapshot_sha256,
        "granted_scopes_sha256": value.granted_scopes_sha256,
        "policy_version": value.policy_version,
        "action_revision": value.action_revision,
        "approval_class": value.approval_class.value,
        "approval_binding_sha256": value.approval_binding_sha256,
        "parameters_sha256": value.parameters_sha256,
        "resource_version_sha256": value.resource_version_sha256,
        "preview_sha256": value.preview_sha256,
        "review_payload_ref": value.review_payload_ref,
        "status": value.status.value,
        "occurrence_created_at": value.occurrence_created_at.isoformat(),
        "expires_at": value.expires_at.isoformat(),
        "decided_at": None if value.decided_at is None else value.decided_at.isoformat(),
        "approved_at": None if value.approved_at is None else value.approved_at.isoformat(),
        "consumed_at": None if value.consumed_at is None else value.consumed_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_supabase_store_uses_exact_service_role_schedule_approval_rpcs():
    pending = record(status=ConnectedScheduleApprovalStatus.PENDING)
    database = Database(
        {
            "connected_app_read_schedule_approval_v1": row(pending),
            "connected_app_put_schedule_approval_v1": [row(pending)],
        }
    )
    store = SupabaseConnectedScheduleApprovalStore(database)
    assert await store.read(owner_id=OWNER, occurrence_id=OCCURRENCE) == pending
    result = await store.put_pending(
        claim=claim(),
        intent=intent(),
        approval_binding_sha256=SHA_D,
        preview_payload_ref=PREVIEW,
        preview_reference_binding_sha256=SHA_A,
        preview_sha256=SHA_C,
        created_at=NOW - timedelta(seconds=10),
        expires_at=NOW + timedelta(minutes=14, seconds=50),
    )
    assert result == pending
    assert [call[0] for call in database.calls] == [
        "connected_app_read_schedule_approval_v1",
        "connected_app_put_schedule_approval_v1",
    ]
    assert database.calls[0][2] is True
    assert database.calls[1][2] is False
