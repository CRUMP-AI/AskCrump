from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace

import pytest

from backend.connected_app_action_preparation import ConnectedActionPreparationStatus
from backend.connected_app_contracts import MailGetRequest
from backend.connected_app_execution_outbox import (
    ConnectedDispatchCoordinator,
    ConnectedDispatchError,
    ConnectedDispatchRecord,
    ConnectedDispatchStatus,
    SupabaseConnectedDispatchStore,
    _record,
)
from backend.connected_app_payload_resolution import ConnectedPayloadResolutionError
from backend.connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorApprovalClass,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from backend.connected_app_runtime import (
    ConnectedActionInvocation,
    ConnectedActionOutcome,
    ConnectedActionRuntimeResult,
    ConnectedReadTerminalRecord,
)


NOW = datetime(2026, 11, 8, 4, 30, tzinfo=timezone.utc)
OWNER = "10000000-0000-4000-8000-000000000001"
REQUEST = "10000000-0000-4000-8000-000000000002"
ACTION = "10000000-0000-4000-8000-000000000003"
GRANT = "10000000-0000-4000-8000-000000000004"
TASK = "10000000-0000-4000-8000-000000000005"
TURN = "10000000-0000-4000-8000-000000000006"
CONNECTION = "10000000-0000-4000-8000-000000000007"
PAYLOAD = "10000000-0000-4000-8000-000000000008"
APPROVAL = "10000000-0000-4000-8000-000000000009"
CLAIM = "10000000-0000-4000-8000-000000000010"
RESULT = "10000000-0000-4000-8000-000000000011"
SHA = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _value(
    *,
    write: bool = False,
    status: ConnectedDispatchStatus = ConnectedDispatchStatus.QUEUED,
) -> dict[str, object]:
    action = ConnectorActionKind.MAIL_SEND if write else ConnectorActionKind.MAIL_GET
    actions = [action]
    values: dict[str, object] = {
        "operation_id": ACTION,
        "request_id": REQUEST,
        "owner_id": OWNER,
        "grant_id": GRANT,
        "action_id": ACTION,
        "task_id": TASK,
        "turn_id": TURN,
        "connection_id": CONNECTION,
        "provider": ConnectorProvider.GOOGLE.value,
        "resource": ConnectorResource.MAIL.value,
        "action": action.value,
        "authorization_revision": 4,
        "authorization_snapshot_sha256": SHA,
        "granted_actions_sha256": SHA_B,
        "granted_scopes_sha256": SHA_C,
        "grant_actions": [item.value for item in actions],
        "grant_actions_sha256": action_set_sha256(actions),
        "task_state_revision": 2,
        "payload_id": PAYLOAD,
        "payload_reference_binding_sha256": SHA_B,
        "parameters_sha256": SHA_C,
        "resource_version_sha256": None,
        "policy_version": ConnectedActionPolicy.version,
        "mutates_external_state": write,
        "approval_class": (
            ConnectorApprovalClass.EXTERNAL_COMMUNICATION.value
            if write
            else ConnectorApprovalClass.NONE.value
        ),
        "preparation_status": (
            ConnectedActionPreparationStatus.PENDING_APPROVAL.value
            if write
            else ConnectedActionPreparationStatus.READY.value
        ),
        "requested_at": _iso(NOW),
        "preparation_expires_at": _iso(NOW + timedelta(minutes=10)),
        "grant_expires_at": _iso(NOW + timedelta(minutes=20)),
        "approval_id": APPROVAL if write else None,
        "approval_binding_sha256": SHA if write else None,
        "approval_approved_at": _iso(NOW + timedelta(seconds=1)) if write else None,
        "approval_expires_at": _iso(NOW + timedelta(minutes=5)) if write else None,
        "status": status.value,
        "next_attempt_at": _iso(NOW) if status is ConnectedDispatchStatus.QUEUED else None,
        "attempt_count": 0,
        "claim_id": None,
        "fencing_token": None,
        "lease_expires_at": None,
        "invocation_started_at": None,
        "terminal_outcome": None,
        "read_result_ref": None,
        "receipt_outcome": None,
        "provider_request_id_sha256": None,
        "provider_resource_id_sha256": None,
        "result_resource_version_sha256": None,
        "terminal_binding_sha256": None,
        "failure_code_sha256": None,
        "completed_at": None,
        "created_at": _iso(NOW),
        "updated_at": _iso(NOW),
    }
    return values


def _queued(*, write: bool = False) -> ConnectedDispatchRecord:
    return _record(_value(write=write))


def _leased(record: ConnectedDispatchRecord) -> ConnectedDispatchRecord:
    return replace(
        record,
        status=ConnectedDispatchStatus.LEASED,
        next_attempt_at=None,
        attempt_count=record.attempt_count + 1,
        claim_id=CLAIM,
        fencing_token=1,
        lease_expires_at=NOW + timedelta(minutes=2),
        updated_at=NOW + timedelta(seconds=1),
    )


def _invoked(record: ConnectedDispatchRecord) -> ConnectedDispatchRecord:
    return replace(
        record,
        status=ConnectedDispatchStatus.INVOKED,
        invocation_started_at=NOW + timedelta(seconds=2),
        updated_at=NOW + timedelta(seconds=2),
    )


def _read_terminal(record: ConnectedDispatchRecord) -> ConnectedDispatchRecord:
    return replace(
        record,
        status=ConnectedDispatchStatus.READ_SUCCEEDED,
        terminal_outcome="read",
        read_result_ref=RESULT,
        terminal_binding_sha256=SHA,
        completed_at=NOW + timedelta(seconds=3),
        updated_at=NOW + timedelta(seconds=3),
    )


def test_dispatch_projection_is_exact_and_reconstructs_policy_authority() -> None:
    read = _queued()
    assert read.operation_id == read.action_id
    assert read.intent().action is ConnectorActionKind.MAIL_GET
    assert read.grant().actions == frozenset({ConnectorActionKind.MAIL_GET})
    assert read.approval() is None

    write = _queued(write=True)
    approval = write.approval()
    assert approval is not None
    assert approval.approval_id == APPROVAL
    assert approval.action is ConnectorActionKind.MAIL_SEND
    assert approval.parameters_sha256 == SHA_C
    assert approval.approval_class is ConnectorApprovalClass.EXTERNAL_COMMUNICATION


def test_dispatch_projection_rejects_extra_keys_and_result_shape_drift() -> None:
    extra = _value()
    extra["private_content"] = "must never cross the boundary"
    with pytest.raises(ConnectedDispatchError) as added:
        _record(extra)
    assert added.value.code == "CONNECTED_DISPATCH_RPC_SHAPE_INVALID"

    malformed = _value()
    malformed.update(
        status="read_succeeded",
        next_attempt_at=None,
        terminal_outcome="read",
        completed_at=_iso(NOW + timedelta(seconds=2)),
        terminal_binding_sha256=SHA,
    )
    with pytest.raises(ConnectedDispatchError) as missing_result:
        _record(malformed)
    assert missing_result.value.code == "CONNECTED_DISPATCH_RPC_SHAPE_INVALID"


class PayloadResolver:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, object]] = []

    async def resolve(self, *, payload_id, intent):
        self.calls.append((payload_id, intent))
        if self.error is not None:
            raise ConnectedPayloadResolutionError(self.error)
        request = MailGetRequest.build(message_id="message-0000000001")
        invocation = ConnectedActionInvocation(
            intent=intent,
            request=request,
            payload_sha256=intent.parameters_sha256,
            request_target_binding_sha256=request.target_binding_sha256,
        )
        return SimpleNamespace(invocation=invocation)


class Runtime:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    async def run(self, invocation, **kwargs):
        self.calls.append({"invocation": invocation, **kwargs})
        if self.fail:
            raise RuntimeError("content that must not be persisted")
        intent = invocation.intent
        terminal = ConnectedReadTerminalRecord(
            operation_id=intent.action_id,
            provider=intent.provider,
            resource=intent.resource,
            action=intent.action,
            binding_sha256=SHA,
            authority_sha256=SHA_B,
            idempotency_key_hash=hashlib.sha256(
                intent.idempotency_key.encode()
            ).hexdigest(),
            observed_at=NOW + timedelta(seconds=3),
        )
        return ConnectedActionRuntimeResult(
            operation_id=intent.action_id,
            outcome=ConnectedActionOutcome.READ,
            replayed=False,
            terminal=terminal,
        )


class Store:
    def __init__(
        self,
        *,
        response_loss: frozenset[str] = frozenset(),
        terminal_after_runtime_error: ConnectedDispatchStatus = (
            ConnectedDispatchStatus.EFFECT_UNKNOWN
        ),
    ) -> None:
        self.record = _queued()
        self.response_loss = set(response_loss)
        self.terminal_after_runtime_error = terminal_after_runtime_error
        self.calls: list[str] = []

    def _lose(self, name: str) -> None:
        if name in self.response_loss:
            self.response_loss.remove(name)
            raise RuntimeError("lost response")

    async def ensure(self, *, owner_id, request_id):
        self.calls.append("ensure")
        assert owner_id == OWNER and request_id == REQUEST
        self._lose("ensure")
        return self.record

    async def scan_owners(self, *, limit):
        self.calls.append("scan_owners")
        return (OWNER,)

    async def reconcile_owner(self, *, owner_id, limit):
        self.calls.append("reconcile_owner")
        if self.record.status is ConnectedDispatchStatus.QUEUED:
            return (self.record,)
        return ()

    async def claim(self, *, owner_id, action_id, claim_id, lease_seconds):
        self.calls.append("claim")
        assert owner_id == OWNER and action_id == ACTION and claim_id == CLAIM
        self.record = _leased(self.record)
        self._lose("claim")
        return self.record

    async def mark_invoked(self, **values):
        self.calls.append("mark_invoked")
        self.record = _invoked(self.record)
        self._lose("mark_invoked")
        return self.record

    async def preflight_failure(self, *, retryable, failure_code_sha256, **values):
        self.calls.append("preflight_failure")
        if retryable:
            self.record = replace(
                self.record,
                status=ConnectedDispatchStatus.QUEUED,
                next_attempt_at=NOW + timedelta(seconds=2),
                claim_id=None,
                fencing_token=None,
                lease_expires_at=None,
                updated_at=NOW + timedelta(seconds=2),
            )
        else:
            self.record = replace(
                self.record,
                status=ConnectedDispatchStatus.FAILED,
                next_attempt_at=None,
                terminal_outcome="failed",
                failure_code_sha256=failure_code_sha256,
                completed_at=NOW + timedelta(seconds=2),
                updated_at=NOW + timedelta(seconds=2),
            )
        return self.record

    async def settle(self, **values):
        self.calls.append("settle")
        self.record = _read_terminal(self.record)
        self._lose("settle")
        return self.record

    async def runtime_exit(self, **values):
        self.calls.append("runtime_exit")
        if self.terminal_after_runtime_error is ConnectedDispatchStatus.EFFECT_UNKNOWN:
            self.record = replace(
                self.record,
                status=ConnectedDispatchStatus.EFFECT_UNKNOWN,
                terminal_outcome="ambiguous",
                completed_at=NOW + timedelta(seconds=3),
                updated_at=NOW + timedelta(seconds=3),
            )
        return self.record

    async def read(self, *, owner_id, action_id):
        self.calls.append("read")
        return self.record


def _coordinator(
    store,
    payloads,
    runtime,
    *,
    require_ready=lambda: None,
) -> ConnectedDispatchCoordinator:
    return ConnectedDispatchCoordinator(
        store=store,
        payloads=payloads,
        runtime=runtime,
        require_ready=require_ready,
        new_uuid=lambda: CLAIM,
        lease_seconds=60,
    )


@pytest.mark.asyncio
async def test_exact_post_route_resume_survives_ensure_and_execution_response_loss() -> None:
    store = Store(
        response_loss=frozenset({"ensure", "claim", "mark_invoked", "settle"})
    )
    payloads = PayloadResolver()
    runtime = Runtime()

    result = await _coordinator(store, payloads, runtime).resume_prepared(
        owner_id=OWNER, request_id=REQUEST
    )

    assert result.invoked is True
    assert result.record is not None
    assert result.record.status is ConnectedDispatchStatus.READ_SUCCEEDED
    assert result.record.read_result_ref == RESULT
    assert len(runtime.calls) == 1
    assert store.calls.count("ensure") == 2
    assert store.calls.count("read") == 3


@pytest.mark.asyncio
async def test_payload_preflight_failure_never_invokes_runtime() -> None:
    store = Store()
    payloads = PayloadResolver("CONNECTED_PAYLOAD_NOT_FOUND")
    runtime = Runtime()

    result = await _coordinator(store, payloads, runtime).resume_prepared(
        owner_id=OWNER, request_id=REQUEST
    )

    assert result.invoked is False
    assert result.record is not None
    assert result.record.status is ConnectedDispatchStatus.FAILED
    assert runtime.calls == []
    assert store.calls.count("preflight_failure") == 1


@pytest.mark.asyncio
async def test_runtime_error_reconciles_effect_unknown_without_blind_retry() -> None:
    store = Store()
    runtime = Runtime(fail=True)
    subject = _coordinator(store, PayloadResolver(), runtime)

    first = await subject.resume_prepared(owner_id=OWNER, request_id=REQUEST)
    second = await subject.run_bounded()

    assert first.invoked is True
    assert first.record is not None
    assert first.record.status is ConnectedDispatchStatus.EFFECT_UNKNOWN
    assert second.actions_invoked == 0
    assert len(runtime.calls) == 1
    assert store.calls.count("runtime_exit") == 1


@pytest.mark.asyncio
async def test_readiness_is_fenced_for_claim_phase_and_provider_invocation() -> None:
    store = Store()
    runtime = Runtime()
    checks = 0

    def require_ready() -> None:
        nonlocal checks
        checks += 1

    result = await _coordinator(
        store,
        PayloadResolver(),
        runtime,
        require_ready=require_ready,
    ).resume_prepared(owner_id=OWNER, request_id=REQUEST)

    assert result.invoked is True
    assert checks == 3
    assert len(runtime.calls) == 1


@pytest.mark.asyncio
async def test_readiness_lapse_after_invoked_transition_never_calls_provider() -> None:
    store = Store()
    runtime = Runtime()
    checks = 0

    def require_ready() -> None:
        nonlocal checks
        checks += 1
        if checks == 3:
            raise RuntimeError("expired")

    with pytest.raises(ConnectedDispatchError) as raised:
        await _coordinator(
            store,
            PayloadResolver(),
            runtime,
            require_ready=require_ready,
        ).resume_prepared(owner_id=OWNER, request_id=REQUEST)

    assert raised.value.code == "CONNECTED_DISPATCH_NOT_READY"
    assert raised.value.retryable is True
    assert runtime.calls == []
    assert store.calls.count("runtime_exit") == 1
    assert store.record.status is ConnectedDispatchStatus.EFFECT_UNKNOWN


@pytest.mark.asyncio
async def test_startup_reconciler_is_bounded_and_discovery_only() -> None:
    store = Store()
    subject = _coordinator(store, PayloadResolver(), Runtime())

    ready = await subject.reconcile_startup(owner_limit=1, per_owner_limit=1)

    assert ready == (store.record,)
    assert store.calls == ["scan_owners", "reconcile_owner"]


class Database:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], bool]] = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        return _value()


@pytest.mark.asyncio
async def test_supabase_adapter_uses_exact_service_rpc_without_transport_retry() -> None:
    database = Database()
    store = SupabaseConnectedDispatchStore(database=database)

    record = await store.ensure(owner_id=OWNER, request_id=REQUEST)

    assert record is not None and record.request_id == REQUEST
    assert database.calls == [
        (
            "connected_dispatch_ensure_v1",
            {"p_owner_id": OWNER, "p_request_id": REQUEST},
            False,
        )
    ]
