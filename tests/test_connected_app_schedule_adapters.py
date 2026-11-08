from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.connected_app_agent import (
    ConnectedOperatorDisposition,
    ConnectedOperatorPlan,
    ConnectedOperatorSchedule,
)
from backend.connected_app_chat_operator import (
    ConnectedOperatorActionContext,
    ConnectedOperatorChatRequest,
)
from backend.connected_app_contracts import (
    ConnectionAuthorizationState,
    MailDraftSpec,
    MailQuery,
    MailSearchRequest,
    MailSendRequest,
)
from backend.connected_app_plan_once import (
    ConnectedPlanBindingKey,
    ConnectedPlanOnceCommand,
    ConnectedPlanOperationRecord,
    ConnectedPlanOperationState,
)
from backend.connected_app_policy import (
    ConnectedActionPolicy,
    ConnectedApprovalEvidence,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from backend.connected_app_schedule_adapters import (
    ConnectedChatScheduleRecord,
    ConnectedOperatorScheduleCoordinator,
    ConnectedScheduleAdapterError,
    ConnectedScheduleTemplateCommitmentKey,
    ConnectedScheduleTemplateKey,
    ConnectedScheduleTemplateResolver,
    ConnectedScheduleTemplateVault,
    EncryptedConnectedScheduleTemplate,
    SupabaseConnectedChatScheduleStage,
    SupabaseConnectedScheduleStore,
)
from backend.connected_app_scheduler import (
    ConnectedScheduleClaim,
    ConnectedScheduleFinish,
    ConnectedScheduleRunOutcome,
    ConnectedSchedulerError,
)
from backend.connected_app_service import ConnectedConnectionAuthorityView


NOW = datetime(2026, 11, 8, 6, 0, tzinfo=UTC)
OWNER = "86300000-0000-4000-8000-000000000001"
SESSION = "86300000-0000-4000-8000-000000000002"
CHAT = "86300000-0000-4000-8000-000000000003"
MESSAGE = "86300000-0000-4000-8000-000000000004"
TURN = "86300000-0000-4000-8000-000000000005"
TURN_CLAIM = "86300000-0000-4000-8000-000000000006"
CONNECTION = "86300000-0000-4000-8000-000000000007"
TASK = "86300000-0000-4000-8000-000000000008"
SCHEDULE = "86300000-0000-4000-8000-000000000009"
TEMPLATE = "86300000-0000-4000-8000-000000000010"
PLAN_PAYLOAD = "86300000-0000-4000-8000-000000000011"
CLAIM = "86300000-0000-4000-8000-000000000012"
COMPLETION = "86300000-0000-4000-8000-000000000013"
OPERATION = "86300000-0000-4000-8000-000000000014"
OCCURRENCE = "86300000-0000-4000-8000-000000000015"
OCCURRENCE_ACTION = "86300000-0000-4000-8000-000000000016"
OCCURRENCE_APPROVAL = "86300000-0000-4000-8000-000000000017"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def vault() -> ConnectedScheduleTemplateVault:
    return ConnectedScheduleTemplateVault(
        primary_key=ConnectedScheduleTemplateKey("schedule-key-1", b"k" * 32),
        commitment_key=ConnectedScheduleTemplateCommitmentKey(
            "schedule-commitment-1", b"c" * 32
        ),
    )


def sealed(
    *,
    action: ConnectorActionKind = ConnectorActionKind.MAIL_SEARCH,
    request=None,
) -> tuple[ConnectedScheduleTemplateVault, EncryptedConnectedScheduleTemplate]:
    subject = vault()
    if request is None:
        request = MailSearchRequest.build(MailQuery(query="from:client", limit=5))
    return subject, subject.prepare(
        template_id=TEMPLATE,
        schedule_id=SCHEDULE,
        owner_id=OWNER,
        turn_id=TURN,
        connection_id=CONNECTION,
        task_id=TASK,
        plan_payload_id=PLAN_PAYLOAD,
        plan_reference_binding_sha256=SHA_A,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=action,
        authorization_revision=3,
        authorization_snapshot_sha256=SHA_B,
        granted_actions_sha256=action_set_sha256({action}),
        granted_scopes_sha256=SHA_C,
        request=request,
        created_at=NOW,
    )


def claim(record: EncryptedConnectedScheduleTemplate) -> ConnectedScheduleClaim:
    reference = record.reference
    write = ConnectedActionPolicy.requirement(reference.action).mutates_external_state
    return ConnectedScheduleClaim(
        schedule_id=reference.schedule_id,
        owner_id=reference.owner_id,
        connection_id=reference.connection_id,
        task_id=reference.task_id,
        provider=reference.provider,
        resource=reference.resource,
        action=reference.action,
        action_template_ref=reference.template_id,
        parameters_sha256=reference.parameters_sha256,
        task_state_revision=1,
        time_zone="America/New_York",
        cadence_seconds=3600,
        quiet_start_minute=None,
        quiet_end_minute=None,
        requires_approval_every_run=write,
        scheduled_for=NOW - timedelta(minutes=1),
        claim_id=CLAIM,
        claimed_at=NOW,
        claim_expires_at=NOW + timedelta(minutes=2),
        turn_id=reference.turn_id,
        grant_id=CLAIM,
        plan_payload_id=reference.plan_payload_id,
        plan_reference_binding_sha256=reference.plan_reference_binding_sha256,
        authorization_revision=reference.authorization_revision,
        authorization_snapshot_sha256=reference.authorization_snapshot_sha256,
        granted_actions_sha256=reference.granted_actions_sha256,
        granted_scopes_sha256=reference.granted_scopes_sha256,
        template_reference_binding_sha256=reference.binding_sha256,
        resource_version_sha256=reference.resource_version_sha256,
        occurrence_id=OCCURRENCE if write else None,
        occurrence_action_id=OCCURRENCE_ACTION if write else None,
        occurrence_approval_id=OCCURRENCE_APPROVAL if write else None,
        occurrence_created_at=NOW if write else None,
    )


class TemplateReader:
    def __init__(self, record: EncryptedConnectedScheduleTemplate) -> None:
        self.record = record

    async def read_template(self, *, template_id: str):
        return self.record if template_id == self.record.reference.template_id else None


def test_schedule_template_round_trip_is_typed_bound_and_redacted():
    subject, record = sealed()
    opened = subject.open(record)
    assert type(opened.request) is MailSearchRequest
    assert opened.request.query.query == "from:client"
    assert record.reference.binding_sha256 not in repr(record)
    assert "from:client" not in repr(record)
    assert "from:client" not in repr(record.reference)


def test_schedule_template_rejects_ciphertext_or_owner_binding_tamper():
    subject, record = sealed()
    changed = ("A" if record.payload_ciphertext[0] != "A" else "B") + record.payload_ciphertext[1:]
    with pytest.raises(ConnectedScheduleAdapterError) as ciphertext_failure:
        replace(record, payload_ciphertext=changed)
    assert ciphertext_failure.value.code == "CONNECTED_SCHEDULE_CUSTODY_CORRUPT"

    rebound = replace(record.reference, owner_id="86300000-0000-4000-8000-000000000099")
    with pytest.raises(ConnectedScheduleAdapterError) as owner_failure:
        subject.open(replace(record, reference=rebound))
    assert owner_failure.value.code == "CONNECTED_SCHEDULE_CUSTODY_CORRUPT"


@pytest.mark.asyncio
async def test_resolver_reconstructs_read_only_from_encrypted_server_custody():
    subject, record = sealed()
    run = await ConnectedScheduleTemplateResolver(
        templates=TemplateReader(record), vault=subject
    ).prepare(claim(record))
    assert type(run.invocation.request) is MailSearchRequest
    assert run.invocation.request.query.query == "from:client"
    assert run.invocation.intent.parameters_sha256 == record.reference.parameters_sha256
    assert run.grant.actions == frozenset({ConnectorActionKind.MAIL_SEARCH})
    assert run.approval is None


@pytest.mark.asyncio
async def test_every_scheduled_write_requires_a_fresh_exact_approval():
    request = MailSendRequest.build(
        MailDraftSpec(
            to=("client@example.com",),
            subject="Private scheduled subject",
            body_text="Private scheduled body",
        )
    )
    subject, record = sealed(action=ConnectorActionKind.MAIL_SEND, request=request)
    schedule_claim = claim(record)
    resolver = ConnectedScheduleTemplateResolver(
        templates=TemplateReader(record), vault=subject
    )
    with pytest.raises(ConnectedSchedulerError) as failure:
        await resolver.prepare(schedule_claim)
    assert failure.value.code == "CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED"

    class Approvals:
        calls = 0

        async def fresh_approval(self, *, claim, intent, action_payload):
            self.calls += 1
            return ConnectedApprovalEvidence(
                approval_id=claim.occurrence_approval_id,
                action_id=intent.action_id,
                owner_id=claim.owner_id,
                task_id=claim.task_id,
                turn_id=claim.turn_id,
                connection_id=claim.connection_id,
                provider=claim.provider,
                resource=claim.resource,
                action=claim.action,
                authorization_revision=claim.authorization_revision,
                authorization_snapshot_sha256=claim.authorization_snapshot_sha256,
                approval_class=ConnectedActionPolicy.requirement(claim.action).approval_class,
                approval_binding_sha256=SHA_D,
                parameters_sha256=claim.parameters_sha256,
                resource_version_sha256=claim.resource_version_sha256,
                approved_at=NOW,
                expires_at=NOW + timedelta(minutes=5),
            )

    approvals = Approvals()
    approved = await ConnectedScheduleTemplateResolver(
        templates=TemplateReader(record), vault=subject, approvals=approvals
    ).prepare(schedule_claim)
    assert approvals.calls == 1
    assert approved.approval is not None
    assert approved.approval.action_id == approved.invocation.intent.action_id

    class WrongApprovals(Approvals):
        async def fresh_approval(self, *, claim, intent, action_payload):
            value = await super().fresh_approval(
                claim=claim, intent=intent, action_payload=action_payload
            )
            return replace(
                value, action_id="86300000-0000-4000-8000-000000000021"
            )

    with pytest.raises(ConnectedSchedulerError) as mismatch:
        await ConnectedScheduleTemplateResolver(
            templates=TemplateReader(record),
            vault=subject,
            approvals=WrongApprovals(),
        ).prepare(schedule_claim)
    assert mismatch.value.code == "CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED"


def context() -> ConnectedOperatorActionContext:
    return ConnectedOperatorActionContext(
        request=ConnectedOperatorChatRequest(
            owner_id=OWNER,
            session_id=SESSION,
            chat_id=CHAT,
            message_id=MESSAGE,
            message="Check for client email every hour",
            time_zone="America/New_York",
        ),
        turn_id=TURN,
        claim_token=TURN_CLAIM,
        origin_session_binding_sha256=SHA_C,
        request_binding_sha256=SHA_D,
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


@pytest.mark.asyncio
async def test_coordinator_creates_only_from_settled_plan_and_recovers_exact_replay():
    planning_key = ConnectedPlanBindingKey("plan-key-1", b"p" * 32)
    schedule_vault = vault()
    action = ConnectorActionKind.MAIL_SEARCH
    plan = ConnectedOperatorPlan(
        disposition=ConnectedOperatorDisposition.SCHEDULE,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=action,
        request=MailSearchRequest.build(MailQuery(query="newer_than:1d", limit=10)),
        schedule=ConnectedOperatorSchedule(
            cadence_seconds=3600,
            time_zone="America/New_York",
            quiet_start="22:00",
            quiet_end="07:00",
            requires_approval_every_run=False,
        ),
        requires_approval=False,
    )

    class Plans:
        calls = 0

        async def read(self, command):
            self.calls += 1
            return ConnectedPlanOperationRecord(
                state=ConnectedPlanOperationState.SETTLED,
                planning_id=command.planning_id,
                owner_id=command.owner_id,
                turn_id=command.turn_id,
                planning_binding_key_id=command.planning_binding_key_id,
                planning_binding_sha256=command.planning_binding_sha256,
                payload_id=command.payload_id,
                invocation_id=command.invocation_id,
                invocation_expires_at=NOW + timedelta(minutes=5),
                disposition=ConnectedOperatorDisposition.SCHEDULE,
                connection_id=CONNECTION,
                provider=ConnectorProvider.GOOGLE,
                resource=ConnectorResource.MAIL,
                action=action,
                payload_commitment_key_id="plan-commitment-1",
                payload_sha256=SHA_A,
                payload_reference_binding_sha256=SHA_B,
                error_code=None,
                requested_at=NOW,
                expires_at=NOW + timedelta(minutes=10),
                updated_at=NOW,
            )

    class Authorities:
        calls = 0

        async def get_connection_authority(self, **_):
            self.calls += 1
            return ConnectedConnectionAuthorityView(
                connection_id=CONNECTION,
                provider=ConnectorProvider.GOOGLE,
                resource=ConnectorResource.MAIL,
                authorization_state=ConnectionAuthorizationState.ACTIVE,
                authorization_revision=3,
                authorization_snapshot_sha256=SHA_B,
                granted_scopes_sha256=SHA_C,
                granted_actions=(action,),
                expires_at=NOW + timedelta(hours=1),
            )

    class Stage:
        stored = None
        encrypted = None
        calls = 0

        async def read(self, **_):
            return self.stored

        async def create(self, *, context, planning, request_id, task_id, record, **_):
            self.calls += 1
            self.encrypted = record
            reference = record.reference
            self.stored = ConnectedChatScheduleRecord(
                request_id=request_id,
                schedule_id=reference.schedule_id,
                template_id=reference.template_id,
                owner_id=context.request.owner_id,
                turn_id=context.turn_id,
                task_id=task_id,
                connection_id=reference.connection_id,
                plan_payload_id=planning.payload_id,
                plan_reference_binding_sha256=reference.plan_reference_binding_sha256,
                provider=reference.provider,
                resource=reference.resource,
                action=reference.action,
                parameters_sha256=reference.parameters_sha256,
                template_reference_binding_sha256=reference.binding_sha256,
                next_run_at=NOW + timedelta(minutes=1),
                created_at=NOW,
            )
            return self.stored

    plans, authorities, stage = Plans(), Authorities(), Stage()
    coordinator = ConnectedOperatorScheduleCoordinator(
        planning_key=planning_key,
        plans=plans,
        authorities=authorities,
        vault=schedule_vault,
        stage=stage,
        now=lambda: NOW,
    )
    first = await coordinator.create(context=context(), plan=plan)
    second = await coordinator.create(context=context(), plan=plan)
    assert first == second
    assert plans.calls == authorities.calls == stage.calls == 1
    assert type(schedule_vault.open(stage.encrypted).request) is MailSearchRequest


class Database:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        value = self.rows[name]
        if isinstance(value, Exception):
            raise value
        return value


def claim_row(value: ConnectedScheduleClaim) -> dict[str, object]:
    return {
        "schedule_id": value.schedule_id,
        "owner_id": value.owner_id,
        "connection_id": value.connection_id,
        "task_id": value.task_id,
        "provider": value.provider.value,
        "resource": value.resource.value,
        "action": value.action.value,
        "action_template_ref": value.action_template_ref,
        "parameters_sha256": value.parameters_sha256,
        "task_state_revision": value.task_state_revision,
        "time_zone": value.time_zone,
        "cadence_seconds": value.cadence_seconds,
        "quiet_start_minute": value.quiet_start_minute,
        "quiet_end_minute": value.quiet_end_minute,
        "requires_approval_every_run": value.requires_approval_every_run,
        "scheduled_for": value.scheduled_for.isoformat(),
        "claim_id": value.claim_id,
        "claimed_at": value.claimed_at.isoformat(),
        "claim_expires_at": value.claim_expires_at.isoformat(),
        "turn_id": value.turn_id,
        "grant_id": value.grant_id,
        "plan_payload_id": value.plan_payload_id,
        "plan_reference_binding_sha256": value.plan_reference_binding_sha256,
        "authorization_revision": value.authorization_revision,
        "authorization_snapshot_sha256": value.authorization_snapshot_sha256,
        "granted_actions_sha256": value.granted_actions_sha256,
        "granted_scopes_sha256": value.granted_scopes_sha256,
        "template_reference_binding_sha256": value.template_reference_binding_sha256,
        "resource_version_sha256": value.resource_version_sha256,
        "occurrence_id": value.occurrence_id,
        "occurrence_action_id": value.occurrence_action_id,
        "occurrence_approval_id": value.occurrence_approval_id,
        "occurrence_created_at": (
            None
            if value.occurrence_created_at is None
            else value.occurrence_created_at.isoformat()
        ),
    }


@pytest.mark.asyncio
async def test_concrete_store_uses_v3_claim_finish_and_exact_readback_rpcs():
    _, record = sealed()
    schedule_claim = claim(record)
    finish = ConnectedScheduleFinish(
        completion_id=COMPLETION,
        schedule_id=SCHEDULE,
        owner_id=OWNER,
        claim_id=CLAIM,
        task_state_revision=1,
        outcome=ConnectedScheduleRunOutcome.READ,
        operation_id=OPERATION,
        next_run_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )
    finish_row = {
        "completion_id": finish.completion_id,
        "schedule_id": finish.schedule_id,
        "owner_id": finish.owner_id,
        "claim_id": finish.claim_id,
        "task_state_revision": finish.task_state_revision,
        "outcome": finish.outcome.value,
        "operation_id": finish.operation_id,
        "next_run_at": finish.next_run_at.isoformat(),
        "finished_at": finish.finished_at.isoformat(),
        "recorded_at": (NOW + timedelta(seconds=1)).isoformat(),
        "occurrence_id": None,
    }
    database = Database(
        {
            "connected_app_claim_schedule_v3": [claim_row(schedule_claim)],
            "connected_app_read_schedule_claim_v3": claim_row(schedule_claim),
            "connected_app_finish_schedule_v3": finish_row,
            "connected_app_read_schedule_finish_v3": finish_row,
        }
    )
    store = SupabaseConnectedScheduleStore(database)
    assert await store.claim_once(claim_id=CLAIM, lease_seconds=120) == schedule_claim
    assert await store.readback_claim(claim_id=CLAIM) == schedule_claim
    assert (await store.finish_once(finish)).finish == finish
    assert (
        await store.readback_finish(
            schedule_id=SCHEDULE, claim_id=CLAIM, completion_id=COMPLETION
        )
    ).finish == finish
    assert [name for name, _, _ in database.calls] == [
        "connected_app_claim_schedule_v3",
        "connected_app_read_schedule_claim_v3",
        "connected_app_finish_schedule_v3",
        "connected_app_read_schedule_finish_v3",
    ]


@pytest.mark.asyncio
async def test_chat_stage_recovers_response_loss_only_by_exact_server_readback():
    _, record = sealed()
    action_context = context()
    planning = ConnectedPlanOnceCommand.build(
        binding_key=ConnectedPlanBindingKey("plan-key-1", b"p" * 32),
        owner_id=OWNER,
        session_id=SESSION,
        chat_id=CHAT,
        message_id=MESSAGE,
        turn_id=TURN,
        claim_token=TURN_CLAIM,
        origin_session_binding_sha256=SHA_C,
        request_binding_sha256=SHA_D,
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )

    class LostDatabase:
        def __init__(self):
            self.calls = 0

        async def rpc(self, name, payload, **_):
            if name == "connected_operator_create_chat_schedule_v2":
                self.calls += 1
                raise TimeoutError("response lost")
            reference = record.reference
            return {
                "request_id": payload["p_request_id"],
                "schedule_id": reference.schedule_id,
                "template_id": reference.template_id,
                "owner_id": OWNER,
                "turn_id": TURN,
                "task_id": TASK,
                "connection_id": CONNECTION,
                "plan_payload_id": PLAN_PAYLOAD,
                "plan_reference_binding_sha256": SHA_A,
                "provider": "google",
                "resource": "mail",
                "action": "mail.search",
                "parameters_sha256": reference.parameters_sha256,
                "template_reference_binding_sha256": reference.binding_sha256,
                "next_run_at": (NOW + timedelta(minutes=1)).isoformat(),
                "created_at": NOW.isoformat(),
            }

    database = LostDatabase()
    stage = SupabaseConnectedChatScheduleStage(database)
    recovered = await stage.create(
        context=action_context,
        planning=planning,
        request_id=CLAIM,
        task_id=TASK,
        record=record,
        cadence_seconds=3600,
        time_zone="America/New_York",
        quiet_start_minute=None,
        quiet_end_minute=None,
        requires_approval_every_run=False,
    )
    assert database.calls == 1
    assert recovered.template_id == TEMPLATE
