from pathlib import Path


SQL = Path("migrations/20261108020000_connected_chat_turn_binding.sql").read_text(encoding="utf-8")
NORMALIZED = " ".join(SQL.casefold().split())


def test_chat_turn_storage_is_private_content_free_and_owner_deleted() -> None:
    assert "create schema if not exists connected_chat_private authorization postgres" in NORMALIZED
    assert "enable row level security" in NORMALIZED
    assert "force row level security" in NORMALIZED
    assert "references public.users(id) on delete cascade" in NORMALIZED
    assert "references public.chat_jobs(id) on delete cascade" in NORMALIZED
    assert "message text" not in NORMALIZED
    assert "body text" not in NORMALIZED
    assert "attachment_ids" not in NORMALIZED
    assert "request_binding_sha256" in NORMALIZED
    assert "origin_session_binding_sha256" in NORMALIZED


def test_claim_never_rewrites_chat_or_clears_a_durable_response() -> None:
    assert "set status = 'processing', error_code = null," in NORMALIZED
    assert "set status = 'processing', chat_id" not in NORMALIZED
    assert "response_data = null" not in NORMALIZED
    assert "current_job.chat_id <> p_chat_id" in NORMALIZED
    assert "connected chat turn replay drifted" in NORMALIZED


def test_claim_is_service_role_only_and_uses_owner_lock_first() -> None:
    assert "perform connected_app_private.owner_lock_v1(p_owner_id)" in NORMALIZED
    assert "revoke all on function public.connected_chat_claim_turn_v1" in NORMALIZED
    assert "grant execute on function public.connected_chat_claim_turn_v1" in NORMALIZED
    assert "to service_role" in NORMALIZED
    assert "set search_path = ''" in NORMALIZED


def test_effect_unknown_and_exact_terminal_paths_fail_closed() -> None:
    assert "current_turn.stage = 'effect_unknown'" in NORMALIZED
    assert "connected chat effect is unknown" in NORMALIZED
    assert "current_turn.stage <> 'terminal'" in NORMALIZED
    assert "current_job.response_data is null" in NORMALIZED


def test_migration_reapplies_only_after_exact_catalog_fingerprint() -> None:
    assert "4887a4c14128fb5a05d667cdfec50669" in NORMALIZED
    assert "connected chat turn target drifted; refusing repair" in NORMALIZED
    assert "create schema if not exists connected_chat_private" in NORMALIZED
    assert "create or replace function public.connected_chat_claim_turn_v1" in NORMALIZED
    assert "using errcode = '55000'" in NORMALIZED
    assert "connected chat turn postflight failed" in NORMALIZED
