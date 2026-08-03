from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "migrations" / "001_python_backend.sql").read_text()


def test_legacy_session_credentials_are_removed():
    normalized = MIGRATION.lower()
    assert "token_hash text not null" in normalized
    assert "drop column if exists session_token" in normalized
    assert "alter column token_hash set not null" in normalized


def test_legacy_conversation_failures_stop_the_migration():
    normalized = MIGRATION.lower()
    assert "raise exception 'legacy crump_chats migration failed:" in normalized
    assert "raise notice" not in normalized


def test_incomplete_accounts_are_rejected_before_constraints_are_applied():
    normalized = MIGRATION.lower()
    assert "missing email address" in normalized
    assert "missing password hash" in normalized
    assert "duplicate user emails exist after case normalization" in normalized
