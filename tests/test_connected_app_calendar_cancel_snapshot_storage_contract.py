from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/20261108068000_connected_calendar_cancel_snapshot_authority.sql"
MODULE = ROOT / "backend/connected_app_calendar_cancel_snapshot.py"
SQL = MIGRATION.read_text(encoding="utf-8")
PYTHON = MODULE.read_text(encoding="utf-8")


def test_snapshot_migration_is_forward_exact_and_predecessor_pinned():
    assert "__PREDECESSOR_FINGERPRINT__" not in SQL
    assert "__TARGET_FINGERPRINT__" not in SQL
    assert "connected_loop_private.multi_step_target_fingerprint_v1()" in SQL
    assert "911134df6337047466b663f2859e247f" in SQL
    assert SQL.count("755dbb418bb4cef4d102f1587ee1c99a") == 2
    assert "using errcode='55000'" in SQL
    assert "begin;" in SQL
    assert SQL.rstrip().endswith("commit;")


def test_snapshot_authority_is_private_content_free_and_unpublished():
    assert "connected_cancel_private.snapshot_reads" in SQL
    assert "enable row level security" in SQL
    assert "force row level security" in SQL
    assert (
        "revoke all on schema connected_cancel_private\n"
        "  from public,anon,authenticated,service_role;"
    ) in SQL
    assert "publication exposure refused" in SQL
    assert "calendar_id" not in SQL
    assert "event_id" not in SQL
    assert "event_title" not in SQL
    assert "event_description" not in SQL
    assert "attendees" not in SQL


def test_both_sources_cross_prepare_and_just_in_time_fences():
    for name in (
        "connected_app_prepare_cancel_snapshot_chat_v1",
        "connected_app_prepare_cancel_snapshot_schedule_v1",
        "connected_app_begin_cancel_snapshot_chat_v1",
        "connected_app_begin_cancel_snapshot_schedule_v1",
    ):
        assert f"create or replace function public.{name}(" in SQL
        assert f'function="{name}"' in PYTHON
    assert "operation_row.action is distinct from 'calendar.cancel'" in SQL
    assert "p_action<>'calendar.get'" in SQL
    assert "occurrence_row.current_claim_id is distinct from p_claim_id" in SQL
    assert "schedule_row.claim_id is distinct from p_claim_id" in SQL
    assert "schedule_row.claim_expires_at is null" in SQL
    assert "schedule_row.claim_expires_at<=now_at" in SQL
    assert "snapshot_row.expires_at<=now_at" in SQL


def test_child_read_has_exact_authority_version_and_service_role_only_rpc():
    assert "not ('calendar.get'=any(connection_row.granted_actions))" in SQL
    assert "not ('calendar.cancel'=any(connection_row.granted_actions))" in SQL
    assert "p_resource_version_sha256!~'^[0-9a-f]{64}$'" in SQL
    assert "template_row.resource_version_sha256<>p_resource_version_sha256" in SQL
    assert "false,'none','ready'" in SQL
    assert "array['calendar.get']" in SQL
    assert SQL.count("grant execute on function public.connected_app_") == 4
    assert "from public,anon,authenticated;" in SQL
    assert "to service_role;" in SQL


def test_python_source_has_no_direct_credential_or_provider_dependency():
    assert "from .connected_app_credential" not in PYTHON
    assert "from .connected_app_google" not in PYTHON
    assert "from .connected_app_microsoft" not in PYTHON
    assert "browser" in PYTHON.lower()
    assert "ConnectedAppRuntime" in PYTHON
    assert "ConnectedActionPayloadResolver" in PYTHON
    assert "ConnectedPayloadVault" in PYTHON
    assert "_MAX_SNAPSHOT_AGE = timedelta(minutes=5)" in PYTHON
