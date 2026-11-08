from pathlib import Path


SQL = Path("migrations/20261108052000_connected_chat_action_stage.sql").read_text(
    encoding="utf-8"
)
NORMALIZED = " ".join(SQL.casefold().split())


def test_plan_preparation_and_turn_stage_share_one_transaction() -> None:
    assert "create or replace function public.connected_operator_prepare_chat_action_v1" in NORMALIZED
    assert "operation_row.state<>'settled'" in NORMALIZED
    assert "operation_row.disposition<>'action'" in NORMALIZED
    assert "operation_row.payload_id is distinct from turn_row.plan_payload_id" in NORMALIZED
    assert "public.connected_app_operator_prepare_action_v1(" in NORMALIZED
    assert "set stage='prepared', preparation_request_id=p_request_id" in NORMALIZED
    assert NORMALIZED.index("begin;") < NORMALIZED.index(
        "create or replace function public.connected_operator_prepare_chat_action_v1"
    )
    assert NORMALIZED.rstrip().endswith("commit;")


def test_read_execution_is_a_separate_no_effect_stage_fence() -> None:
    assert "create or replace function public.connected_operator_begin_chat_read_v1" in NORMALIZED
    assert "preparation_row.status<>'ready' or preparation_row.mutates_external_state" in NORMALIZED
    assert "set stage='executing', execution_request_id=p_execution_request_id" in NORMALIZED
    assert "no_provider_effect" in NORMALIZED
    function = NORMALIZED.split(
        "create or replace function public.connected_operator_begin_chat_read_v1", 1
    )[1].split("comment on function", 1)[0]
    assert "execute_write" not in function
    assert "begin_effect" not in function


def test_owner_session_job_turn_and_plan_are_revalidated() -> None:
    assert NORMALIZED.count("perform connected_app_private.owner_lock_v1(p_owner_id)") >= 2
    assert NORMALIZED.count("from public.sessions as session") >= 2
    assert NORMALIZED.count("session_row.revoked_at is not null") >= 2
    assert NORMALIZED.count("job_row.claim_token<>p_claim_token") >= 2
    assert NORMALIZED.count("turn_row.origin_session_binding_sha256") >= 2
    assert "operation_row.session_id<>p_session_id" in NORMALIZED
    assert "p_expires_at>operation_row.expires_at" in NORMALIZED


def test_turn_bindings_are_content_free_and_single_purpose() -> None:
    assert "add column if not exists execution_request_id uuid" in NORMALIZED
    assert "add column if not exists schedule_request_id uuid" in NORMALIZED
    assert "add column if not exists schedule_id uuid" in NORMALIZED
    assert "connected_chat_turns_single_work_binding_check" in NORMALIZED
    assert "not (action_id is not null and schedule_id is not null)" in NORMALIZED
    assert "message_body" not in NORMALIZED
    assert "recipient" not in NORMALIZED
    assert "event_title" not in NORMALIZED


def test_exact_target_and_service_role_only_authority() -> None:
    assert "423a6b0bd7f659ba37c729170c424dfc" in NORMALIZED
    assert "connected chat action-stage target drifted" in NORMALIZED
    assert "connected chat action-stage predecessor catalog drifted" in NORMALIZED
    assert "using errcode = '55000'" in NORMALIZED
    assert NORMALIZED.count("security definer") >= 2
    assert NORMALIZED.count("set search_path = ''") >= 2
    assert "from public,anon,authenticated" in NORMALIZED
    assert "to service_role" in NORMALIZED
