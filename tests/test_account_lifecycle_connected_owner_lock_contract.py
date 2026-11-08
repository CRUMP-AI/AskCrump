from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "migrations" / "20261108054000_account_lifecycle_connected_owner_lock.sql"
).read_text()
DATABASE = (ROOT / "backend" / "db.py").read_text()
CONNECTED_COMPLETION = (
    ROOT / "migrations" / "20261108040000_connected_operator_chat_completion.sql"
).read_text()


def _body(name: str, occurrence: int = 0) -> str:
    matches = list(
        re.finditer(
            rf"create or replace function public\.{re.escape(name)}\s*\(",
            MIGRATION,
            re.IGNORECASE,
        )
    )
    start = matches[occurrence].start()
    tail = MIGRATION[start:]
    marker = re.search(r"\bas\s+(\$[A-Za-z_0-9]*\$)", tail, re.IGNORECASE)
    assert marker is not None
    tag = marker.group(1)
    body_start = marker.end()
    body_end = tail.index(tag, body_start)
    return tail[body_start:body_end].lower()


def test_uses_one_connected_owner_lock_before_every_row_lock():
    functions = (
        "consume_password_reset_v1",
        "verify_registered_and_create_session_v1",
        "verify_guest_and_create_session_v1",
        "finalize_password_login_v1",
        "complete_initial_password_setup_v1",
        "delete_user_account",
    )
    for name in functions:
        body = _body(name)
        owner = body.index("connected_app_private.owner_lock_v1(")
        first_row_lock = body.find("for update")
        if first_row_lock < 0:
            first_row_lock = body.find("delete from")
        assert first_row_lock > owner

    for name in ("apply_guest_chat_sync_v2", "persist_guest_chat_reply_v1"):
        body = _body(name)
        control = body.index("lock_guest_mode_control_v1()")
        owner = body.index("connected_app_private.owner_lock_v1(p_user_id)")
        chat = body.index("from public.user_chats as target_chat")
        chat_row = body.index("for update", chat)
        user = body.index("from public.users as candidate")
        user_row = body.index("for update", user)
        assert control < owner < chat < chat_row < user < user_row

    deletion = _body("delete_user_account")
    owner = deletion.index("connected_app_private.owner_lock_v1(p_user_id)")
    chats = deletion.index("delete from public.user_chats")
    sessions = deletion.index("delete from public.sessions")
    user = deletion.index("delete from public.users")
    assert owner < chats < sessions < user

    assert "4716231172214320496" not in MIGRATION


def test_exact_current_or_target_attestation_and_connected_completion_pin():
    assert MIGRATION.count("Account lifecycle predecessor manifest drifted.") == 1
    assert "Account lifecycle exact target postflight failed." in MIGRATION
    assert MIGRATION.count("ab70e27e21f3e90e3cf6185638485d75") == 2
    assert "c7598d67398c07b8c0ed053571bbc1fe" in MIGRATION
    for target_hash in (
        "d47a6a36d9f1dc2302df928390041235",
        "59a70b8a8e24189f07c6c41c7ea44bb9",
        "7cb4d1914711769c33fd94ec24d6b0d0",
        "722dbbe9c5ad5b2f35b06141f3cfdb4b",
        "21e2ef4db85b329592dd3789fa68d04b",
        "3f4663e4db141a8513aba73f33d0abec",
        "45a30b4b172cf850db21fd4283a42fc9",
        "7512a874aa85ffd7770d44a2e3b530d7",
    ):
        assert MIGRATION.count(target_hash) == 2
    assert re.search(
        r"has_function_privilege\(\s*'authenticated'",
        MIGRATION,
    )
    assert "array['search_path=\"\"']::text[]" in MIGRATION


def test_connected_completion_keeps_owner_before_session_row_lock():
    start = CONNECTED_COMPLETION.index(
        "create or replace function public.connected_operator_complete_chat_v1("
    )
    body = CONNECTED_COMPLETION[start:]
    owner = body.index("connected_app_private.owner_lock_v1(p_owner_id)")
    session = body.index("from public.sessions as session_row")
    session_lock = body.index("for update", session)
    assert owner < session < session_lock


def test_measurement_contracts_are_not_added_or_rewritten():
    lowered = MIGRATION.lower()
    for forbidden in (
        "first_successful_answer",
        "activationreached",
        "product_first_successful",
        "registration_environment =",
        "email_verified_at =",
    ):
        assert forbidden not in lowered


def test_deadlock_is_metadata_only_for_non_idempotent_requests():
    assert '_POSTGRES_DEADLOCK_CODE = "40P01"' in DATABASE
    assert "deadlock_detected" in DATABASE
    assert "retryable_error" in DATABASE
    retry_loop = DATABASE.index("for attempt in range")
    error_metadata = DATABASE.index("deadlock_detected")
    assert retry_loop < error_metadata
    # The retry branch remains guarded by retryable_request; a normal POST RPC
    # reaches the one-attempt error metadata path instead of being replayed.
    assert "retryable_request\n                    and transient_status" in DATABASE
