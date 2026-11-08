from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib

import pytest

from backend.connected_app_contracts import (
    EventSnapshot,
    FreeBusyWindow,
    MessageSnapshot,
    MessageSummary,
)
from backend.connected_app_policy import ConnectorActionKind, ConnectorProvider, ConnectorResource
from backend.connected_app_read_results import ConnectedReadResultCoordinator
from backend.connected_app_read_surface import (
    ConnectedOwnerReadResultError,
    ConnectedOwnerReadResultIndex,
    ConnectedOwnerReadResultService,
    SupabaseConnectedOwnerReadResultIndex,
)
from backend.connected_app_runtime import (
    ConnectedDurableReadResult,
    ConnectedReadObservation,
)


NOW = datetime(2026, 11, 8, 6, 20, tzinfo=UTC)
OWNER = "10000000-0000-4000-8000-000000000001"
TASK = "10000000-0000-4000-8000-000000000002"
TURN = "10000000-0000-4000-8000-000000000003"
CONNECTION = "10000000-0000-4000-8000-000000000004"
ACTION = "10000000-0000-4000-8000-000000000005"
RESULT = ConnectedReadResultCoordinator.payload_id(ACTION)
INVOCATION = "a" * 64
IDEMPOTENCY = "b" * 64
AUTHORITY = "c" * 64
MANIFEST = "f" * 64


def index() -> ConnectedOwnerReadResultIndex:
    return ConnectedOwnerReadResultIndex(
        operation_id=ACTION,
        owner_id=OWNER,
        task_id=TASK,
        turn_id=TURN,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_GET,
        parameters_sha256="d" * 64,
        request_resource_version_sha256=None,
        terminal_resource_version_sha256=None,
        invocation_binding_sha256=INVOCATION,
        idempotency_key_sha256=IDEMPOTENCY,
        terminal_binding_sha256=INVOCATION,
        authority_sha256=AUTHORITY,
        observed_at=NOW,
        result_payload_id=RESULT,
        expires_at=NOW + timedelta(days=6),
    )


def durable() -> ConnectedDurableReadResult:
    terminal = index().terminal()
    observation = ConnectedReadObservation(
        operation_id=ACTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        value=MessageSnapshot(
            message_id="message-1",
            resource_version="etag-1",
            received_at=NOW,
            subject="<img src=x onerror=alert(1)>",
            sender="sender@example.com",
            recipients=("owner@example.com",),
            body_text="<script>alert(1)</script>" + ("x" * 90_000),
            attachment_count=1,
        ),
        observed_at=NOW,
        resource_version=None,
    )
    return ConnectedDurableReadResult(terminal=terminal, observation=observation)


class Index:
    def __init__(self, value=index()):
        self.value = value
        self.calls = []

    async def get(self, **kwargs):
        self.calls.append(kwargs)
        return self.value


class Results:
    def __init__(self, value=None):
        self.calls = []
        self.value = value

    async def replay(self, **kwargs):
        self.calls.append(kwargs)
        return self.value or durable()


@pytest.mark.asyncio
async def test_owner_surface_replays_exact_result_and_projects_untrusted_text():
    source = Index()
    results = Results()
    service = ConnectedOwnerReadResultService(
        index=source,
        results=results,
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    record = await service.get(owner_id=OWNER, result_reference_id=RESULT)
    assert source.calls == [{"owner_id": OWNER, "result_payload_id": RESULT}]
    assert results.calls[0]["lookup"] == index().lookup()
    assert results.calls[0]["terminal"] == index().terminal()
    assert record["resultReferenceId"] == RESULT
    assert record["actionId"] == ACTION
    assert record["itemCount"] == 1
    assert record["itemsTruncated"] is False
    item = record["items"][0]
    assert item["subject"] == "<img src=x onerror=alert(1)>"
    assert item["bodyText"].startswith("<script>alert(1)</script>")
    assert item["bodyTruncated"] is True
    assert len(item["bodyText"].encode("utf-8")) <= 80_000
    assert item["trustBoundary"] == "untrusted_external_data"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "resource", "value", "kind"),
    [
        (
            ConnectorActionKind.MAIL_SEARCH,
            ConnectorResource.MAIL,
            (
                MessageSummary(
                    message_id="message-1",
                    resource_version="etag-1",
                    received_at=NOW,
                    subject="Status",
                    sender="sender@example.com",
                    recipients=("owner@example.com",),
                    labels=("inbox",),
                ),
            ),
            "mail_summary",
        ),
        (
            ConnectorActionKind.CALENDAR_LIST,
            ConnectorResource.CALENDAR,
            (
                EventSnapshot(
                    event_id="event-1",
                    calendar_id="calendar-1",
                    resource_version="etag-1",
                    starts_at=NOW,
                    ends_at=NOW + timedelta(hours=1),
                    time_zone="UTC",
                    title="Review",
                ),
            ),
            "calendar_event",
        ),
        (
            ConnectorActionKind.CALENDAR_GET,
            ConnectorResource.CALENDAR,
            EventSnapshot(
                event_id="event-2",
                calendar_id="calendar-1",
                resource_version="etag-2",
                starts_at=NOW,
                ends_at=NOW + timedelta(hours=1),
                time_zone="UTC",
                title="One event",
            ),
            "calendar_event",
        ),
        (
            ConnectorActionKind.CALENDAR_FREE_BUSY,
            ConnectorResource.CALENDAR,
            (
                FreeBusyWindow(
                    calendar_id="calendar-1",
                    starts_at=NOW,
                    ends_at=NOW + timedelta(minutes=30),
                ),
            ),
            "calendar_busy_window",
        ),
    ],
)
async def test_owner_surface_projects_every_read_kind_as_bounded_data(
    action, resource, value, kind
):
    record = index()
    source_record = ConnectedOwnerReadResultIndex(
        **{
            name: getattr(record, name)
            for name in ConnectedOwnerReadResultIndex.__dataclass_fields__
            if name not in {"action", "resource"}
        },
        action=action,
        resource=resource,
    )
    source = Index(source_record)
    durable_result = ConnectedDurableReadResult(
        terminal=source_record.terminal(),
        observation=ConnectedReadObservation(
            operation_id=ACTION,
            provider=ConnectorProvider.GOOGLE,
            resource=resource,
            value=value,
            observed_at=NOW,
            resource_version=None,
        ),
    )
    service = ConnectedOwnerReadResultService(
        index=source,
        results=Results(durable_result),
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    result = await service.get(owner_id=OWNER, result_reference_id=RESULT)
    assert result["items"][0]["kind"] == kind
    assert result["items"][0]["trustBoundary"] == "untrusted_external_data"


@pytest.mark.asyncio
async def test_owner_surface_bounds_large_lists_and_marks_truncation():
    record = index()
    source_record = ConnectedOwnerReadResultIndex(
        **{
            name: getattr(record, name)
            for name in ConnectedOwnerReadResultIndex.__dataclass_fields__
            if name != "action"
        },
        action=ConnectorActionKind.MAIL_SEARCH,
    )
    values = tuple(
        MessageSummary(
            message_id=f"message-{number}",
            resource_version=f"etag-{number}",
            received_at=NOW,
            subject="Status",
            sender="sender@example.com",
        )
        for number in range(101)
    )
    durable_result = ConnectedDurableReadResult(
        terminal=source_record.terminal(),
        observation=ConnectedReadObservation(
            operation_id=ACTION,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.MAIL,
            value=values,
            observed_at=NOW,
            resource_version=None,
        ),
    )
    service = ConnectedOwnerReadResultService(
        index=Index(source_record),
        results=Results(durable_result),
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    result = await service.get(owner_id=OWNER, result_reference_id=RESULT)
    assert result["itemCount"] == 100
    assert result["itemsTruncated"] is True


@pytest.mark.asyncio
async def test_owner_surface_refuses_cross_owner_and_expired_results():
    service = ConnectedOwnerReadResultService(
        index=Index(),
        results=Results(),
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    with pytest.raises(ConnectedOwnerReadResultError) as mismatch:
        await service.get(
            owner_id="10000000-0000-4000-8000-000000000099",
            result_reference_id=RESULT,
        )
    assert mismatch.value.code == "CONNECTED_READ_RESULT_NOT_FOUND"

    expired = ConnectedOwnerReadResultIndex(
        **{
            name: getattr(index(), name)
            for name in ConnectedOwnerReadResultIndex.__dataclass_fields__
            if name not in {"observed_at", "expires_at"}
        },
        observed_at=NOW - timedelta(days=1),
        expires_at=NOW,
    )
    service = ConnectedOwnerReadResultService(
        index=Index(expired),
        results=Results(),
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    with pytest.raises(ConnectedOwnerReadResultError) as expiry:
        await service.get(owner_id=OWNER, result_reference_id=RESULT)
    assert expiry.value.code == "CONNECTED_READ_RESULT_EXPIRED"


@pytest.mark.asyncio
async def test_supabase_owner_index_uses_service_role_rpc_and_exact_shape():
    class Database:
        def __init__(self):
            self.calls = []

        async def rpc(self, name, payload, **kwargs):
            self.calls.append((name, payload, kwargs))
            value = index()
            return {
                "operation_id": value.operation_id,
                "owner_id": value.owner_id,
                "task_id": value.task_id,
                "turn_id": value.turn_id,
                "connection_id": value.connection_id,
                "provider": value.provider.value,
                "resource": value.resource.value,
                "action": value.action.value,
                "parameters_sha256": value.parameters_sha256,
                "request_resource_version_sha256": (
                    value.request_resource_version_sha256
                ),
                "terminal_resource_version_sha256": (
                    value.terminal_resource_version_sha256
                ),
                "invocation_binding_sha256": value.invocation_binding_sha256,
                "idempotency_key_sha256": value.idempotency_key_sha256,
                "terminal_binding_sha256": value.terminal_binding_sha256,
                "authority_sha256": value.authority_sha256,
                "observed_at": value.observed_at.isoformat(),
                "result_payload_id": value.result_payload_id,
                "expires_at": value.expires_at.isoformat(),
            }

    database = Database()
    subject = SupabaseConnectedOwnerReadResultIndex(database)
    assert await subject.get(owner_id=OWNER, result_payload_id=RESULT) == index()
    assert database.calls == [
        (
            "connected_app_open_read_result_v1",
            {"p_owner_id": OWNER, "p_result_payload_id": RESULT},
            {"retry_transient": True},
        )
    ]


def test_index_rejects_non_deterministic_reference_and_terminal_drift():
    base = index()
    values = {
        name: getattr(base, name) for name in ConnectedOwnerReadResultIndex.__dataclass_fields__
    }
    values["result_payload_id"] = "10000000-0000-4000-8000-000000000099"
    with pytest.raises(ConnectedOwnerReadResultError):
        ConnectedOwnerReadResultIndex(**values)
    values = {
        name: getattr(base, name) for name in ConnectedOwnerReadResultIndex.__dataclass_fields__
    }
    values["terminal_binding_sha256"] = hashlib.sha256(b"drift").hexdigest()
    with pytest.raises(ConnectedOwnerReadResultError):
        ConnectedOwnerReadResultIndex(**values)
