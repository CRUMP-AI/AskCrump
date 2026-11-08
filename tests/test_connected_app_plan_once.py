from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from backend.connected_app_agent import ConnectedOperatorDisposition, ConnectedOperatorPlanner
from backend.connected_app_contracts import ConnectionAuthorizationState, ConnectorAccountKind
from backend.connected_app_plan_once import (
    ConnectedPlanBindingKey,
    ConnectedPlanInvocationClaim,
    ConnectedPlanOnceCommand,
    ConnectedPlanOnceCoordinator,
    ConnectedPlanOnceError,
    ConnectedPlanOperationRecord,
    ConnectedPlanOperationState,
)
from backend.connected_app_plan_vault import (
    ConnectedPlanCommitmentKey,
    ConnectedPlanEnvelopeVault,
    ConnectedPlanMasterKey,
    ConnectedPlanVaultError,
    EncryptedConnectedPlanEnvelope,
)
from backend.connected_app_policy import ConnectorActionKind, ConnectorProvider, ConnectorResource
from backend.connected_app_service import ConnectedConnectionView


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000002"
CHAT = "00000000-0000-4000-8000-000000000003"
MESSAGE = "00000000-0000-4000-8000-000000000004"
TURN = "00000000-0000-4000-8000-000000000005"
CLAIM = "00000000-0000-4000-8000-000000000006"
CONNECTION = "00000000-0000-4000-8000-000000000007"
SHA_A = "a" * 64
SHA_B = "b" * 64


def connection() -> ConnectedConnectionView:
    return ConnectedConnectionView(
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        granted_actions=(ConnectorActionKind.MAIL_SEARCH,),
        authorization_state=ConnectionAuthorizationState.ACTIVE,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA_A,
        expires_at=NOW + timedelta(days=30),
        updated_at=NOW,
    )


def proposal() -> dict[str, object]:
    return {
        "kind": "action",
        "connectionId": CONNECTION,
        "action": "mail.search",
        "parameters": {
            "query": "from:alex@example.com",
            "folderIds": ["inbox"],
            "after": None,
            "before": None,
            "limit": 10,
        },
        "schedule": None,
        "question": None,
    }


class Model:
    def __init__(self, value: object, gate: asyncio.Event | None = None) -> None:
        self.value = value
        self.gate = gate
        self.calls = 0
        self.call_arguments: list[dict[str, object]] = []

    async def complete(self, **kwargs) -> str:
        self.calls += 1
        self.call_arguments.append(kwargs)
        if self.gate is not None:
            await self.gate.wait()
        if isinstance(self.value, BaseException):
            raise self.value
        return json.dumps(self.value, separators=(",", ":"))


class MemoryEnvelopeStore:
    def __init__(self) -> None:
        self.records: dict[str, EncryptedConnectedPlanEnvelope] = {}
        self.tombstones: set[str] = set()

    async def put_once(self, record):
        payload_id = record.reference.payload_id
        if payload_id in self.tombstones:
            return None
        current = self.records.get(payload_id)
        if current is None:
            self.records[payload_id] = record
            return record
        return current

    async def read_exact(self, **bindings):
        record = self.records.get(bindings["payload_id"])
        if record is None:
            return None
        reference = record.reference
        if (
            reference.owner_id != bindings["owner_id"]
            or reference.turn_id != bindings["turn_id"]
            or reference.planning_id != bindings["planning_id"]
            or reference.planning_binding_sha256 != bindings["planning_binding_sha256"]
        ):
            return None
        return record

    async def delete_once(self, **bindings):
        self.records.pop(bindings["payload_id"], None)
        self.tombstones.add(bindings["payload_id"])
        return True


class MemoryControlPlane:
    def __init__(self) -> None:
        self.record: ConnectedPlanOperationRecord | None = None
        self.lock = asyncio.Lock()
        self.settle_calls = 0

    @staticmethod
    def _base(command, **changes):
        values = dict(
            state=ConnectedPlanOperationState.RESERVED,
            planning_id=command.planning_id,
            owner_id=command.owner_id,
            turn_id=command.turn_id,
            planning_binding_key_id=command.planning_binding_key_id,
            planning_binding_sha256=command.planning_binding_sha256,
            payload_id=command.payload_id,
            invocation_id=None,
            invocation_expires_at=None,
            disposition=None,
            connection_id=None,
            provider=None,
            resource=None,
            action=None,
            payload_commitment_key_id=None,
            payload_sha256=None,
            payload_reference_binding_sha256=None,
            error_code=None,
            requested_at=command.requested_at,
            expires_at=command.expires_at,
            updated_at=NOW,
        )
        values.update(changes)
        return ConnectedPlanOperationRecord(**values)

    async def begin(self, command):
        async with self.lock:
            if self.record is None:
                self.record = self._base(command)
            return self.record

    async def mark_invoked(self, command):
        async with self.lock:
            assert self.record is not None
            permitted = self.record.state is ConnectedPlanOperationState.RESERVED
            if permitted:
                self.record = replace(
                    self.record,
                    state=ConnectedPlanOperationState.INVOKED,
                    invocation_id=command.invocation_id,
                    invocation_expires_at=NOW + timedelta(seconds=45),
                    updated_at=NOW,
                )
            return ConnectedPlanInvocationClaim(self.record, permitted)

    async def settle(self, command, *, reference, result):
        async with self.lock:
            self.settle_calls += 1
            assert self.record is not None
            if self.record.state is ConnectedPlanOperationState.SETTLED:
                return self.record
            assert self.record.state is ConnectedPlanOperationState.INVOKED
            plan = result.plan
            self.record = replace(
                self.record,
                state=ConnectedPlanOperationState.SETTLED,
                disposition=result.disposition,
                connection_id=None if plan is None else plan.connection_id,
                provider=None if plan is None else plan.provider,
                resource=None if plan is None else plan.resource,
                action=None if plan is None else plan.action,
                payload_commitment_key_id=reference.commitment_key_id,
                payload_sha256=reference.payload_sha256,
                payload_reference_binding_sha256=reference.binding_sha256,
                updated_at=NOW,
            )
            return self.record

    async def fail(self, command, *, error_code):
        assert self.record is not None
        self.record = replace(
            self.record,
            state=ConnectedPlanOperationState.FAILED,
            error_code=error_code,
        )
        return self.record

    async def mark_effect_unknown(self, command):
        assert self.record is not None
        self.record = replace(
            self.record,
            state=ConnectedPlanOperationState.EFFECT_UNKNOWN,
            error_code="MODEL_EFFECT_UNKNOWN",
        )
        return self.record

    async def read(self, command):
        return self.record


def command(*, session_id=SESSION, claim_token=CLAIM) -> ConnectedPlanOnceCommand:
    return ConnectedPlanOnceCommand.build(
        binding_key=ConnectedPlanBindingKey("plan-bind-1", b"b" * 32),
        owner_id=OWNER,
        session_id=session_id,
        chat_id=CHAT,
        message_id=MESSAGE,
        turn_id=TURN,
        claim_token=claim_token,
        origin_session_binding_sha256=SHA_A,
        request_binding_sha256=SHA_B,
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def vault(store: MemoryEnvelopeStore) -> ConnectedPlanEnvelopeVault:
    return ConnectedPlanEnvelopeVault(
        store=store,
        master_keys={"plan-kek-1": ConnectedPlanMasterKey("plan-kek-1", b"k" * 32)},
        active_master_key_id="plan-kek-1",
        commitment_keys={"plan-hmac-1": ConnectedPlanCommitmentKey("plan-hmac-1", b"h" * 32)},
        active_commitment_key_id="plan-hmac-1",
    )


def coordinator(model, control, store):
    return ConnectedPlanOnceCoordinator(
        planner=ConnectedOperatorPlanner(model, now=lambda: NOW),
        control_plane=control,
        vault=vault(store),
        now=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_plan_output_is_encrypted_and_exact_replay_never_calls_model_twice():
    model = Model(proposal())
    control = MemoryControlPlane()
    store = MemoryEnvelopeStore()
    service = coordinator(model, control, store)
    first = await service.plan_once(
        command(),
        message="Check my email from Alex.",
        connections=(connection(),),
        user_time_zone="America/New_York",
    )
    replay = await service.plan_once(
        command(),
        message="Check my email from Alex.",
        connections=(connection(),),
        user_time_zone="America/New_York",
    )
    assert first.disposition is ConnectedOperatorDisposition.ACTION
    assert replay.plan == first.plan
    assert model.calls == 1
    assert model.call_arguments[0]["owner_id"] == OWNER
    encrypted = next(iter(store.records.values()))
    assert "alex@example.com" not in repr(encrypted)
    assert "alex@example.com" not in json.dumps(
        encrypted.__dict__ if hasattr(encrypted, "__dict__") else {}
    )


@pytest.mark.asyncio
async def test_crash_after_encrypted_write_recovers_without_second_model_call():
    model = Model(proposal())
    control = MemoryControlPlane()
    store = MemoryEnvelopeStore()
    service = coordinator(model, control, store)
    cmd = command()
    await control.begin(cmd)
    claim = await control.mark_invoked(cmd)
    assert claim.invoke_permitted is True
    prepared = service._planner.prepare(
        owner_id=cmd.owner_id,
        message="Check my email from Alex.",
        connections=(connection(),),
        user_time_zone="America/New_York",
    )
    raw = await service._planner.complete(prepared)
    await service._vault.seal_json(
        payload_id=cmd.payload_id,
        owner_id=cmd.owner_id,
        turn_id=cmd.turn_id,
        planning_id=cmd.planning_id,
        planning_binding_sha256=cmd.planning_binding_sha256,
        value={"version": "connected-plan-output-v1", "raw": raw},
        created_at=cmd.requested_at,
        expires_at=cmd.expires_at,
    )
    result = await service.plan_once(
        cmd,
        message="Check my email from Alex.",
        connections=(connection(),),
        user_time_zone="America/New_York",
    )
    assert result.disposition is ConnectedOperatorDisposition.ACTION
    assert model.calls == 1
    assert control.record.state is ConnectedPlanOperationState.SETTLED


@pytest.mark.asyncio
async def test_invoked_without_output_is_busy_then_effect_unknown_never_reinvokes():
    model = Model(proposal())
    control = MemoryControlPlane()
    store = MemoryEnvelopeStore()
    service = coordinator(model, control, store)
    cmd = command()
    await control.begin(cmd)
    await control.mark_invoked(cmd)
    with pytest.raises(ConnectedPlanOnceError) as busy:
        await service.plan_once(
            cmd,
            message="Check my email from Alex.",
            connections=(connection(),),
            user_time_zone="America/New_York",
        )
    assert busy.value.code == "CONNECTED_PLAN_ONCE_BUSY"
    control.record = replace(
        control.record,
        invocation_expires_at=NOW - timedelta(seconds=1),
    )
    with pytest.raises(ConnectedPlanOnceError) as unknown:
        await service.plan_once(
            cmd,
            message="Check my email from Alex.",
            connections=(connection(),),
            user_time_zone="America/New_York",
        )
    assert unknown.value.code == "CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN"
    assert model.calls == 0
    assert control.record.state is ConnectedPlanOperationState.EFFECT_UNKNOWN


@pytest.mark.asyncio
async def test_concurrent_same_operation_has_one_model_call_owner():
    gate = asyncio.Event()
    model = Model(proposal(), gate)
    control = MemoryControlPlane()
    store = MemoryEnvelopeStore()
    service = coordinator(model, control, store)
    cmd = command()
    first = asyncio.create_task(
        service.plan_once(
            cmd,
            message="Check my email from Alex.",
            connections=(connection(),),
            user_time_zone="America/New_York",
        )
    )
    while model.calls == 0:
        await asyncio.sleep(0)
    with pytest.raises(ConnectedPlanOnceError) as second:
        await service.plan_once(
            cmd,
            message="Check my email from Alex.",
            connections=(connection(),),
            user_time_zone="America/New_York",
        )
    assert second.value.code == "CONNECTED_PLAN_ONCE_BUSY"
    gate.set()
    assert (await first).disposition is ConnectedOperatorDisposition.ACTION
    assert model.calls == 1


@pytest.mark.asyncio
async def test_model_response_loss_is_effect_unknown_and_never_reinvoked():
    model = Model(RuntimeError("response lost"))
    control = MemoryControlPlane()
    store = MemoryEnvelopeStore()
    service = coordinator(model, control, store)
    with pytest.raises(ConnectedPlanOnceError) as lost:
        await service.plan_once(
            command(),
            message="Check my email from Alex.",
            connections=(connection(),),
            user_time_zone="America/New_York",
        )
    assert lost.value.code == "CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN"
    assert model.calls == 1
    assert store.records == {}
    assert control.record.state is ConnectedPlanOperationState.EFFECT_UNKNOWN
    with pytest.raises(ConnectedPlanOnceError) as replay:
        await service.plan_once(
            command(),
            message="Check my email from Alex.",
            connections=(connection(),),
            user_time_zone="America/New_York",
        )
    assert replay.value.code == "CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN"
    assert model.calls == 1


@pytest.mark.asyncio
async def test_settle_response_loss_reads_committed_result_without_retrying_settle():
    class CommittedLostResponseControl(MemoryControlPlane):
        async def settle(self, command_value, *, reference, result):
            await super().settle(command_value, reference=reference, result=result)
            raise RuntimeError("response lost")

    model = Model(proposal())
    control = CommittedLostResponseControl()
    store = MemoryEnvelopeStore()
    result = await coordinator(model, control, store).plan_once(
        command(),
        message="Check my email from Alex.",
        connections=(connection(),),
        user_time_zone="America/New_York",
    )
    assert result.disposition is ConnectedOperatorDisposition.ACTION
    assert model.calls == 1
    assert control.settle_calls == 1


@pytest.mark.asyncio
async def test_uncommitted_settle_loss_is_not_retried_in_same_attempt():
    class UncommittedLostResponseControl(MemoryControlPlane):
        async def settle(self, command_value, *, reference, result):
            self.settle_calls += 1
            raise RuntimeError("response lost before commit")

    model = Model(proposal())
    control = UncommittedLostResponseControl()
    store = MemoryEnvelopeStore()
    with pytest.raises(ConnectedPlanOnceError) as lost:
        await coordinator(model, control, store).plan_once(
            command(),
            message="Check my email from Alex.",
            connections=(connection(),),
            user_time_zone="America/New_York",
        )
    assert lost.value.code == "CONNECTED_PLAN_ONCE_EFFECT_UNKNOWN"
    assert model.calls == 1
    assert control.settle_calls == 1
    assert control.record.state is ConnectedPlanOperationState.INVOKED


def test_session_and_current_claim_are_part_of_stable_operation_binding():
    first = command()
    another_session = command(session_id="00000000-0000-4000-8000-000000000008")
    another_claim = command(claim_token="00000000-0000-4000-8000-000000000009")
    assert first.planning_id == another_session.planning_id == another_claim.planning_id
    assert first.payload_id == another_session.payload_id == another_claim.payload_id
    assert first.planning_binding_sha256 != another_session.planning_binding_sha256
    assert first.planning_binding_sha256 != another_claim.planning_binding_sha256


@pytest.mark.asyncio
async def test_tombstone_permanently_prevents_encrypted_payload_resurrection():
    store = MemoryEnvelopeStore()
    encrypted_vault = vault(store)
    cmd = command()
    reference = await encrypted_vault.seal_json(
        payload_id=cmd.payload_id,
        owner_id=cmd.owner_id,
        turn_id=cmd.turn_id,
        planning_id=cmd.planning_id,
        planning_binding_sha256=cmd.planning_binding_sha256,
        value={"version": "connected-plan-output-v1", "raw": "secret"},
        created_at=cmd.requested_at,
        expires_at=cmd.expires_at,
    )
    assert await encrypted_vault.erase(
        owner_id=cmd.owner_id,
        turn_id=cmd.turn_id,
        planning_id=cmd.planning_id,
        planning_binding_sha256=cmd.planning_binding_sha256,
        payload_id=reference.payload_id,
    )
    with pytest.raises(ConnectedPlanVaultError) as erased:
        await encrypted_vault.seal_json(
            payload_id=cmd.payload_id,
            owner_id=cmd.owner_id,
            turn_id=cmd.turn_id,
            planning_id=cmd.planning_id,
            planning_binding_sha256=cmd.planning_binding_sha256,
            value={"version": "connected-plan-output-v1", "raw": "secret"},
            created_at=cmd.requested_at,
            expires_at=cmd.expires_at,
        )
    assert erased.value.code == "CONNECTED_PLAN_VAULT_ERASED"


@pytest.mark.asyncio
async def test_replay_revalidates_current_connection_authority_without_model_call():
    model = Model(proposal())
    control = MemoryControlPlane()
    store = MemoryEnvelopeStore()
    service = coordinator(model, control, store)
    cmd = command()
    await service.plan_once(
        cmd,
        message="Check my email from Alex.",
        connections=(connection(),),
        user_time_zone="America/New_York",
    )
    revoked = replace(
        connection(),
        authorization_state=ConnectionAuthorizationState.REVOKED,
    )
    replay = await service.plan_once(
        cmd,
        message="Check my email from Alex.",
        connections=(revoked,),
        user_time_zone="America/New_York",
    )
    assert replay.disposition is ConnectedOperatorDisposition.CLARIFY
    assert model.calls == 1


def test_secret_keys_and_customer_content_are_redacted():
    key = ConnectedPlanBindingKey("binding-1", b"x" * 32)
    assert "x" * 16 not in repr(key)
    assert "alex@example.com" not in repr(command())
    with pytest.raises(TypeError):
        key.__reduce_ex__(4)
