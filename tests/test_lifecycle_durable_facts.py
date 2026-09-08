from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260908131528_lifecycle_durable_product_facts.sql"


def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def function(source: str, name: str) -> str:
    start = source.index(f"create or replace function public.{name}")
    return source[start : source.index("$function$;", start)]


def test_migration_replaces_only_two_service_role_invoker_functions():
    source = sql()
    lowered = source.lower()

    assert "\nbegin;" in lowered
    assert lowered.rstrip().endswith("commit;")
    assert lowered.count("create or replace function public.") == 2
    assert lowered.count("security invoker") == 2
    assert lowered.count("set search_path = ''") == 2
    assert "security definer" not in lowered
    assert "create table" not in lowered
    assert "alter table" not in lowered
    assert not re.search(r"\b(?:insert into|update public\.|delete from|truncate)\b", lowered)

    for signature in (
        "public.lifecycle_prompt_facts(uuid, text)",
        "public.product_weekly_lifecycle_export(timestamptz, timestamptz, text)",
    ):
        assert f"revoke all on function {signature}\n  from public, anon, authenticated;" in lowered
        assert f"grant execute on function {signature}\n  to service_role;" in lowered


def test_account_eligibility_reads_only_required_fields_and_is_environment_bound():
    source = sql()
    lowered = source.lower()
    facts = function(lowered, "lifecycle_prompt_facts")

    assert "public.users%rowtype" not in facts
    assert "select *" not in facts
    assert (
        "u.is_verified,\n    u.deleted_at,\n    u.created_at,\n"
        "    u.registration_environment"
    ) in source
    assert "v_registration_environment = p_environment" in source
    assert "p_environment = 'production' and v_registration_environment is null" in source
    for prohibited in (
        "u.email",
        "u.name",
        "u.password_hash",
        "u.stripe_customer_id",
        "u.revenuecat_app_user_id",
    ):
        assert prohibited not in facts


def test_decision_facts_use_durable_work_without_treating_an_empty_project_as_aha():
    source = sql()
    facts = function(source, "lifecycle_prompt_facts")

    assert "from public.message_receipts r where r.user_id = p_user_id" in facts
    assert "from public.chat_jobs j where j.user_id = p_user_id" in facts
    assert "j.status = 'completed'" in facts
    assert "e.event_name = 'ActivationReached'" in facts
    assert "p.archived_at is null" in facts
    assert "from public.project_chats pc" in facts
    assert "from public.project_files pf" in facts
    assert "v_has_project_continuity or v_has_artifact" in facts
    assert "v_has_project or v_has_artifact" not in facts
    assert "f.deleted_at is null" in facts
    assert "f.status = 'ready'" in facts
    assert "f.size_bytes > 0" in facts
    assert "'generated_image', 'generated_document', 'generated_video', 'manuscript_export'" in facts
    assert "e.event_name in ('ArtifactPackaged', 'ArtifactDownloaded')" in facts


def test_weekly_export_uses_exact_durable_targets_and_windows():
    source = sql()
    export = function(source, "product_weekly_lifecycle_export")

    assert export.count("u.deleted_at is null") == 2
    assert export.count("coalesce(u.internal_tier, '') = ''") == 2
    assert export.count("u.registration_environment = p_environment") == 2
    assert export.count(
        "p_environment = 'production' and u.registration_environment is null"
    ) == 2
    assert "from public.chat_jobs j" in export
    assert "j.status = 'completed'" in export
    assert "j.updated_at >= q.eligible_at" in export
    assert "q.message_key = 'continuity-assist'" in export
    assert "p.event_key = 'first-durable-project'" in export
    assert "from public.project_chats pc" in export
    assert "join public.projects p" in export
    assert "p.archived_at is null" in export
    assert "from public.user_files f" in export
    assert "f.created_at >= q.eligible_at" in export
    assert export.count("< q.eligible_at + interval '24 hours'") >= 4
    assert "p.event_name = 'ResponseShared'" in export
    assert "p.event_name in ('WorkspaceOpened', 'RecentWorkResumed')" in export
    assert "q.eligible_at <= p_until - interval '7 days'" in export

    continuity = export[export.index("q.message_key = 'continuity-assist'") :]
    continuity = continuity[: continuity.index("q.message_key = 'artifact-assist'")]
    assert "from public.projects p\n" not in continuity


def test_return_contract_and_queries_remain_content_free():
    source = sql()
    lowered = source.lower()
    export = function(lowered, "product_weekly_lifecycle_export")
    return_contract = export.split("returns table (", 1)[1].split(")\nlanguage sql", 1)[0]

    assert "user_id" not in return_contract
    assert "decision_id" not in return_contract
    assert "prompt" not in return_contract
    for prohibited in (
        "storage_path",
        "filename",
        "file_name",
        "response_data",
        "request_payload",
        "message_content",
        "project_name",
        "u.email",
    ):
        assert prohibited not in lowered
