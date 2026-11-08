from __future__ import annotations

from datetime import UTC, datetime, timedelta
import inspect
from pathlib import Path

import pytest

from backend.connected_app_policy import (
    ConnectedApprovalEvidence,
    ConnectorActionKind,
    ConnectorApprovalClass,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_runtime import ConnectedActionEffectRequest
from backend.connected_app_runtime_adapters import SupabaseConnectedActionLedger


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "migrations"
    / "20261108069100_connected_approval_effect_transition.sql"
)
SOURCE = MIGRATION.read_text(encoding="utf-8")
HOST_SOURCE = (ROOT / "backend" / "connected_app_host_bootstrap.py").read_text(
    encoding="utf-8"
)
SHA = "a" * 64
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def test_runtime_calls_only_atomic_approval_effect_rpc() -> None:
    source = inspect.getsource(SupabaseConnectedActionLedger.begin_effect)
    assert "connected_app_consume_approval_and_begin_effect_v1" in source
    assert '"connected_app_begin_effect_v1"' not in source
    assert '"connected_app_consume_approval_v1"' not in source
    assert '"p_approval_binding_sha256"' in source
    assert "record.approval_binding_sha256" in source


def test_effect_request_and_approval_require_exact_binding() -> None:
    assert "approval_binding_sha256" in ConnectedActionEffectRequest.__dataclass_fields__
    with pytest.raises(ValueError, match="approval_binding_sha256"):
        ConnectedApprovalEvidence(
            approval_id="10000000-0000-4000-8000-000000000001",
            action_id="10000000-0000-4000-8000-000000000002",
            owner_id="10000000-0000-4000-8000-000000000003",
            task_id="10000000-0000-4000-8000-000000000004",
            turn_id="10000000-0000-4000-8000-000000000005",
            connection_id="10000000-0000-4000-8000-000000000006",
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.MAIL,
            action=ConnectorActionKind.MAIL_SEND,
            authorization_revision=1,
            authorization_snapshot_sha256=SHA,
            approval_class=ConnectorApprovalClass.EXTERNAL_COMMUNICATION,
            approval_binding_sha256="invalid",
            parameters_sha256=SHA,
            resource_version_sha256=None,
            approved_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )


def test_migration_composes_consume_and_effect_in_one_transaction() -> None:
    normalized = SOURCE.lower()
    assert "connected_app_consume_approval_and_begin_effect_v1" in normalized
    consume = normalized.index("perform public.connected_app_consume_approval_v1")
    begin = normalized.index("result:=public.connected_app_begin_effect_v1")
    assert consume < begin
    assert "p_approval_binding_sha256" in normalized
    assert "security definer" in normalized
    assert "set search_path=''" in normalized
    assert "to service_role" in normalized
    assert "from public,anon,authenticated,service_role" in normalized
    assert "00000000000000000000000000000000" not in normalized


def test_migration_has_explicit_response_loss_replay_and_closes_primitives() -> None:
    normalized = SOURCE.lower()
    assert "if action_row.status='effect_possible' then" in normalized
    assert "approval_row.approval_binding_sha256<>p_approval_binding_sha256" in normalized
    assert "action_row.effect_use_nonce is distinct from p_effect_use_nonce" in normalized
    assert "approval_row.consumed_by_operation_id is distinct from" in normalized
    for primitive in (
        "connected_app_create_approval_v1(",
        "connected_app_consume_approval_v1(",
        "connected_app_begin_effect_v1(",
    ):
        start = normalized.index(f"revoke all on function public.{primitive}")
        assert "from public,anon,authenticated,service_role" in normalized[start:]
    assert "not pg_catalog.has_function_privilege(" in normalized
    assert "'service_role',decide_approval_oid,'execute'" in normalized


def test_host_contract_requires_atomic_691_transition() -> None:
    assert '"20261108069100"' in HOST_SOURCE
    assert '"atomic_one_use_approval_consumption_and_effect_start"' in HOST_SOURCE


def test_fingerprint_helpers_are_source_attested_before_reapply_mutation() -> None:
    normalized = SOURCE.lower()
    preflight = normalized[: normalized.index("create or replace function public.")]
    assert "pg_catalog.pg_get_functiondef" in preflight
    for definition_md5 in (
        "ea00734dc01645ca3402fcca70840cf5",
        "81801876eb127d22939d77fb2e2fa0e0",
        "0c205a01197b172b8227a2b86a7cd34b",
    ):
        assert definition_md5 in preflight
        assert definition_md5 in normalized
    assert "observed_catalog is distinct from observed_target" in preflight
    assert "observed_catalog is distinct from observed_target" in normalized
