from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "migrations"
    / "20261007233345_verification_email_transient_recovery.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8")
RACE_MIGRATION = (
    ROOT
    / "migrations"
    / "20261008000000_verification_email_recovery_race_safety.sql"
)
RACE_SQL = RACE_MIGRATION.read_text(encoding="utf-8")
NORMALIZED = " ".join((SQL + "\n" + RACE_SQL).lower().split())
RACE_NORMALIZED = " ".join(RACE_SQL.lower().split())
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
        "raw_payload",
        "provider_email_id",
        "provider_event_id",
        "jsonb",
    ):
        assert prohibited not in table
    assert "recovery_token_hash text" in RACE_NORMALIZED
    assert "raw ids" in RACE_NORMALIZED
    assert "and tokens are prohibited" in RACE_NORMALIZED


def test_recovery_is_exactly_one_attempt_and_only_signed_transient_is_eligible():
    assert "attempt_count in (0, 1)" in NORMALIZED
    assert "set state = 'prepared', attempt_count = 1" in RACE_NORMALIZED
    assert "authorize_verification_email_recovery_dispatch" in RACE_NORMALIZED
    assert "dispatch_authorized_at = pg_catalog.clock_timestamp()" in RACE_NORMALIZED
    assert "signed_event.outcome_class = 'transient'" in RACE_NORMALIZED
    assert "signed_event.provider_email_hash = attempt.provider_email_hash" in NORMALIZED
    assert "attempt.attempt_count = 0" in NORMALIZED
    assert "attempt.state = 'sent'" in NORMALIZED
    assert "signed_event.outcome_class = 'delivered'" in NORMALIZED
    assert "'permanent', 'failed', 'suppressed', 'complaint'" in NORMALIZED
    assert "for update of attempts skip locked" in RACE_NORMALIZED
    assert "events.payload_fingerprint = p_payload_fingerprint" in RACE_NORMALIZED
    assert "verification_recovery_outcome_rank" in RACE_NORMALIZED


def test_all_recovery_functions_are_service_role_only_and_search_path_pinned():
    signatures = (
        "public.register_verification_email_recovery_attempt( text, uuid, text, timestamptz )",
        "public.record_resend_delivery_event_and_recovery( text, text, text, text, text, text, text, timestamptz )",
        "public.claim_verification_email_recovery(uuid, text)",
        "public.prepare_verification_email_recovery( text, uuid, text, timestamptz, text, timestamptz, text )",
        "public.authorize_verification_email_recovery_dispatch( text, uuid, text, text, timestamptz, text )",
        "public.complete_verification_email_recovery( text, uuid, text, text, text, timestamptz )",
        "public.fail_verification_email_recovery( text, uuid, text, text )",
        "public.consume_verification_email_recovery_token( text, text )",
    )
    for signature in signatures:
        assert (
            f"revoke all on function {signature} "
            "from public, anon, authenticated, service_role"
        ) in RACE_NORMALIZED
        assert f"grant execute on function {signature} to service_role" in RACE_NORMALIZED

    assert RACE_NORMALIZED.count("security definer") == 8
    assert RACE_NORMALIZED.count("set search_path = ''") == 9


def test_migration_order_and_postgres_gate_are_explicit():
    assert MIGRATION.name > "20261001084000_project_artifact_continuity_aggregate.sql"
    assert MIGRATION.name > "20261007221534_resend_delivery_event_observability.sql"
    assert "verification-email-recovery:" in WORKFLOW
    assert "tests/postgres/verification_email_recovery_baseline.sql" in WORKFLOW
    assert "migrations/20261007221534_resend_delivery_event_observability.sql" in WORKFLOW
    assert "migrations/20261007233345_verification_email_transient_recovery.sql" in WORKFLOW
    assert "migrations/20261008000000_verification_email_recovery_race_safety.sql" in WORKFLOW
    assert "tests/postgres/test_verification_email_recovery_race_safety.sql" in WORKFLOW


def test_recovery_has_a_source_lock_and_an_off_environment_default():
    assert "VERIFICATION_EMAIL_RECOVERY_RELEASED = False" in CONFIG
    assert (
        "VERIFICATION_EMAIL_RECOVERY_RELEASED\n"
        "            and _bool(os.getenv('CRUMP_ENABLE_VERIFICATION_EMAIL_RECOVERY'), False)"
    ) in CONFIG
    assert "CRUMP_ENABLE_VERIFICATION_EMAIL_RECOVERY=false" in ENV_EXAMPLE
