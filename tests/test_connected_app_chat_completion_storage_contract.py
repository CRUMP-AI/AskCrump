from pathlib import Path


SQL = Path("migrations/20261108040000_connected_operator_chat_completion.sql").read_text(
    encoding="utf-8"
)
NORMALIZED = " ".join(SQL.casefold().split())


def test_receipt_is_private_content_free_and_owner_deleted() -> None:
    assert (
        "create schema if not exists connected_chat_completion_private authorization postgres"
        in NORMALIZED
    )
    assert "enable row level security" in NORMALIZED
    assert "force row level security" in NORMALIZED
    assert "references public.users(id) on delete cascade" in NORMALIZED
    assert "references connected_chat_private.turns(turn_id) on delete cascade" in NORMALIZED
    table = NORMALIZED.split(
        "create table if not exists connected_chat_completion_private.completions (", 1
    )[1].split(");", 1)[0]
    assert "response_data" not in table
    assert "user_message" not in table
    assert "assistant_message jsonb" not in table
    assert "title" not in table
    assert "response_binding_sha256" in table


def test_completion_revalidates_live_session_request_job_and_turn() -> None:
    assert "perform connected_app_private.owner_lock_v1(p_owner_id)" in NORMALIZED
    assert "session_row.id = p_session_id" in NORMALIZED
    assert "session_row.revoked_at is null" in NORMALIZED
    assert "session_row.expires_at > now_at" in NORMALIZED
    assert "current_job.claim_token <> p_claim_token" in NORMALIZED
    assert (
        "current_turn.origin_session_binding_sha256 <> p_origin_session_binding_sha256"
        in NORMALIZED
    )
    assert "current_turn.request_binding_sha256 <> p_request_binding_sha256" in NORMALIZED


def test_reply_job_turn_and_receipt_share_one_transaction() -> None:
    assert "from public.persist_chat_reply(" in NORMALIZED
    assert "insert into connected_chat_completion_private.completions" in NORMALIZED
    assert "set status = 'completed', response_data = p_response_data" in NORMALIZED
    assert "set stage = 'terminal', updated_at = now_at" in NORMALIZED
    assert NORMALIZED.index("begin;") < NORMALIZED.index(
        "create schema if not exists connected_chat_completion_private"
    )
    assert NORMALIZED.rstrip().endswith("commit;")


def test_exact_replay_returns_receipt_without_second_reply_write() -> None:
    existing = NORMALIZED.index("if found then", NORMALIZED.index("where completion.turn_id"))
    writer = NORMALIZED.index("from public.persist_chat_reply(")
    assert existing < writer
    assert "connected chat completion replay drifted" in NORMALIZED
    assert "connected chat completion identity collided" in NORMALIZED


def test_rpc_is_service_role_only_with_empty_search_path() -> None:
    assert "security definer set search_path = ''" in NORMALIZED
    assert "revoke all on function public.connected_operator_complete_chat_v1" in NORMALIZED
    assert "grant execute on function public.connected_operator_complete_chat_v1" in NORMALIZED
    assert "to service_role" in NORMALIZED
    assert "e7ce957dd69f6fa93a02039348bc4e91" in NORMALIZED
    assert "connected chat reply writer drifted" in NORMALIZED


def test_reapply_requires_exact_target_and_refuses_partial_repair() -> None:
    assert "c7598d67398c07b8c0ed053571bbc1fe" in NORMALIZED
    assert "c4dacc64c97eb09bc98040ecba5e69a7" in NORMALIZED
    assert "partial connected chat completion target; refusing repair" in NORMALIZED
    assert "connected chat completion target drifted; refusing repair" in NORMALIZED
    assert "using errcode = '55000'" in NORMALIZED
