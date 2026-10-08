from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "migrations"
    / "20261007233345_verification_email_transient_recovery.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8")
NORMALIZED = " ".join(SQL.lower().split())
WORKFLOW = (
    ROOT / ".github" / "workflows" / "postgres-migration-gate.yml"
).read_text(encoding="utf-8")
CONFIG = (ROOT / "backend" / "config.py").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")


def test_recovery_ledger_is_private_forced_rls_and_content_free():
    assert "create table if not exists private.verification_email_recovery_attempts" in NORMALIZED
    assert "enable row level security" in NORMALIZED
    assert "force row level security" in NORMALIZED
    assert (
        "revoke all on table private.verification_email_recovery_attempts "
        "from public, anon, authenticated, service_role"
    ) in NORMALIZED

    table = NORMALIZED.split(
        "create table if not exists private.verification_email_recovery_attempts (",
        1,
    )[1].split("create index if not exists verification_email_recovery_user_idx", 1)[0]
    assert "provider_email_hash text primary key" in table
    assert "user_id uuid not null" in table
    assert "message_kind text not null default 'verification'" in table
    assert "attempt_count smallint not null default 0" in table
    assert "token_expires_at timestamptz not null" in table
    assert "state text not null default 'sent'" in table
    for prohibited in (
        "email text",
        "email_address",
        "recipient ",
        "recipient_hash",
        "subject ",
        "body ",
        "html ",
        "url ",
        "token_hash ",
        "raw_payload",
        "provider_email_id",
        "provider_event_id",
        "jsonb",
    ):
        assert prohibited not in table


def test_recovery_is_exactly_one_attempt_and_only_signed_transient_is_eligible():
    assert "attempt_count in (0, 1)" in NORMALIZED
    assert "set state = 'sending', attempt_count = 1" in NORMALIZED
    assert "signed_event.outcome_class = 'transient'" in NORMALIZED
    assert "signed_event.provider_email_hash = attempt.provider_email_hash" in NORMALIZED
    assert "attempt.attempt_count = 0" in NORMALIZED
    assert "attempt.state = 'sent'" in NORMALIZED
    assert "signed_event.outcome_class = 'delivered'" in NORMALIZED
    assert "'permanent', 'failed', 'suppressed', 'complaint'" in NORMALIZED
    assert "for update of attempts skip locked" in NORMALIZED


def test_all_recovery_functions_are_service_role_only_and_search_path_pinned():
    signatures = (
        "public.register_verification_email_recovery_attempt( text, uuid, text, timestamptz )",
        "public.record_resend_delivery_event_and_recovery( text, text, text, text, text, text, text, timestamptz )",
        "public.claim_verification_email_recovery(uuid)",
        "public.prepare_verification_email_recovery( text, uuid, text, timestamptz, text, timestamptz )",
        "public.complete_verification_email_recovery( text, uuid, text, timestamptz )",
        "public.fail_verification_email_recovery( text, uuid, text, text, timestamptz )",
    )
    for signature in signatures:
        assert (
            f"revoke all on function {signature} "
            "from public, anon, authenticated, service_role"
        ) in NORMALIZED
        assert f"grant execute on function {signature} to service_role" in NORMALIZED

    assert NORMALIZED.count("security definer") == 6
    assert NORMALIZED.count("set search_path = ''") == 6


def test_migration_order_and_postgres_gate_are_explicit():
    assert MIGRATION.name > "20261001084000_project_artifact_continuity_aggregate.sql"
    assert MIGRATION.name > "20261007221534_resend_delivery_event_observability.sql"
    assert "verification-email-recovery:" in WORKFLOW
    assert "tests/postgres/verification_email_recovery_baseline.sql" in WORKFLOW
    assert "migrations/20261007221534_resend_delivery_event_observability.sql" in WORKFLOW
    assert "migrations/20261007233345_verification_email_transient_recovery.sql" in WORKFLOW
    assert "tests/postgres/test_verification_email_recovery_migration.sql" in WORKFLOW


def test_recovery_has_a_source_lock_and_an_off_environment_default():
    assert "VERIFICATION_EMAIL_RECOVERY_RELEASED = False" in CONFIG
    assert (
        "VERIFICATION_EMAIL_RECOVERY_RELEASED\n"
        "            and _bool(os.getenv('CRUMP_ENABLE_VERIFICATION_EMAIL_RECOVERY'), False)"
    ) in CONFIG
    assert "CRUMP_ENABLE_VERIFICATION_EMAIL_RECOVERY=false" in ENV_EXAMPLE
