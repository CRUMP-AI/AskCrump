from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261108063000_connected_schedule_template_completion.sql"
CLEANUP_MIGRATION = (
    ROOT / "migrations" / "20261108061000_connected_grant_cleanup_refresh_fence.sql"
)


def _fingerprint_body(sql: str) -> str:
    matched = re.search(
        r"returns text language sql stable set search_path\s*=\s*''\s+as "
        r"\$fingerprint\$(.*?)\$fingerprint\$;",
        sql,
        flags=re.DOTALL,
    )
    assert matched is not None
    return "".join(matched.group(1).split())


def test_schedule_completion_migration_pins_exact_predecessor_and_target():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "e90e794c75b45084d89d6b1247d3287e" in sql
    assert "f03f8f3204e5623fd950ad1ffb9fd430" in sql
    assert "ASK_CRUMP_CONNECTED_OPEN_READ_RESULT_V1_OWNER_BOUND_CONTENT_FREE_INDEX" in sql
    assert sql.count("4b004a4a403058b443be9dac3c331950") == 2
    assert "connected schedule-template target drifted" in sql
    assert "connected schedule-template postflight fingerprint" in sql
    assert "raise exception 'connected schedule-template state is partial or mixed'" in sql


def test_schedule_successor_carries_exact_cleanup_predecessor_manifest():
    schedule_sql = MIGRATION.read_text(encoding="utf-8")
    cleanup_sql = CLEANUP_MIGRATION.read_text(encoding="utf-8")
    assert _fingerprint_body(schedule_sql) == _fingerprint_body(cleanup_sql)


def test_schedule_custody_and_completion_ledger_are_private_fail_closed():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "create schema if not exists connected_schedule_private" in sql
    assert "create table if not exists connected_schedule_private.templates" in sql
    assert "create table if not exists connected_schedule_private.run_completions" in sql
    assert sql.count("enable row level security") >= 2
    assert sql.count("force row level security") >= 2
    assert "ASK_CRUMP_AES_GCM_TYPED_CONNECTED_ACTION_PAYLOAD_ENVELOPE_SERVER_CUSTODY" in sql
    assert "ASK_CRUMP_CONNECTED_SCHEDULE_FINISH_V2_DURABLE_EXACT_COMPLETION_LEDGER" in sql
    assert "ASK_CRUMP_CONNECTED_SCHEDULE_CLAIM_V2_TEMPLATE_AUTHORITY_AND_GRANT_ATOMIC" in sql


def test_legacy_schedule_writers_are_revoked_and_v2_is_service_role_only():
    sql = MIGRATION.read_text(encoding="utf-8")
    compact = "".join(sql.split())
    for signature in (
        "public.connected_app_operator_create_schedule_v1(",
        "public.connected_app_put_schedule_v1(",
        "public.connected_app_claim_schedule_v1(uuid,integer)",
        "public.connected_app_finish_schedule_v1(uuid,uuid,uuid,timestamptz,bigint)",
    ):
        assert "".join(f"revoke all on function {signature}".split()) in compact
    for signature in (
        "public.connected_operator_create_chat_schedule_v2(",
        "public.connected_app_claim_schedule_v2(uuid,integer)",
        "public.connected_app_finish_schedule_v2(",
    ):
        assert signature in sql
    assert "execute 'grant execute on function '||signature||' to service_role'" in sql


def test_public_http_cannot_author_template_or_payload_references():
    route = (ROOT / "backend" / "routes" / "connected_apps.py").read_text(
        encoding="utf-8"
    )
    assert '@router.post("/schedules")' not in route
    assert "actionTemplateRef" not in route
    assert "payloadReference" not in route


def test_schedule_create_accepts_only_server_typed_runtime_actions():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "or p_action not in (" in sql
    for action in (
        "mail.search",
        "mail.get",
        "mail.create_draft",
        "mail.send",
        "mail.reply",
        "calendar.list",
        "calendar.get",
        "calendar.free_busy",
        "calendar.create",
        "calendar.update",
        "calendar.cancel",
    ):
        assert f"'{action}'" in sql
