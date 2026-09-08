from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "migrations"
    / "20260908131539_lifecycle_prompt_delivery_kill_switch.sql"
)


def function_body(source: str) -> str:
    start = source.index(
        "create or replace function public.record_lifecycle_prompt_action"
    )
    return source[start : source.index("$function$;", start)]


def test_stale_decision_rechecks_message_kill_switch_before_show():
    source = MIGRATION.read_text(encoding="utf-8")
    body = function_body(source)
    shown = body[body.index("if p_action = 'shown' then") :]
    shown = shown[: shown.index("if p_action in ('dismissed', 'acted')")]

    control_lookup = shown.index("from public.lifecycle_prompt_controls c")
    disabled_reason = shown.index("v_reason := 'channel-disabled'")
    facts_recheck = shown.index("v_facts := public.lifecycle_prompt_facts")
    suppression_insert = shown.index("insert into public.lifecycle_prompt_events")

    assert control_lookup < disabled_reason < facts_recheck < suppression_insert
    assert "where c.message_key = v_state.message_key" in shown
    assert "if not coalesce(v_control_enabled, false) then" in shown
    assert "'recorded', false, 'suppressionReason', v_reason" in shown


def test_function_replacement_preserves_fail_closed_security_boundary():
    source = MIGRATION.read_text(encoding="utf-8")
    body = function_body(source)

    assert source.lower().count("create or replace function public.") == 1
    assert "security invoker" in body
    assert "set search_path = ''" in body
    assert "from public, anon, authenticated" in source
    assert "to service_role" in source
    assert "create table" not in source.lower()
    assert "alter table" not in source.lower()
    assert "security definer" not in source.lower()


def test_function_replacement_keeps_existing_delivery_rechecks_and_caps():
    source = MIGRATION.read_text(encoding="utf-8")
    body = function_body(source)

    for marker in (
        "v_state.active_decision_expires_at <= now()",
        "v_facts := public.lifecycle_prompt_facts",
        "coalesce(p_recovery_surface, false)",
        "coalesce(p_active_work, false)",
        "v_reason := 'target-completed'",
        "v_reason := 'session-collision'",
        "v_reason := 'frequency-cap'",
        "e.created_at >= now() - interval '7 days'",
        "on conflict (decision_id, event_type) do nothing",
    ):
        assert marker in body


def test_migration_contains_no_content_or_outbound_channel_fields():
    source = MIGRATION.read_text(encoding="utf-8").lower()

    for prohibited in (
        "prompt_text",
        "response_text",
        "message_content",
        "project_name",
        "file_name",
        "storage_path",
        "email_address",
        "notification_body",
        "send_email",
        "send_push",
    ):
        assert prohibited not in source
