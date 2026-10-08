from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "migrations"
    / "20261007221534_resend_delivery_event_observability.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8")
NORMALIZED = " ".join(SQL.lower().split())
WORKFLOW = (
    ROOT / ".github" / "workflows" / "postgres-migration-gate.yml"
).read_text(encoding="utf-8")


def test_resend_receipts_live_in_a_private_content_free_table():
    assert "create schema if not exists private" in NORMALIZED
    assert (
        "revoke all on schema private "
        "from public, anon, authenticated, service_role"
    ) in NORMALIZED
    assert "create table if not exists private.resend_delivery_events" in NORMALIZED
    assert "alter table private.resend_delivery_events enable row level security" in NORMALIZED
    assert "alter table private.resend_delivery_events force row level security" in NORMALIZED
    assert (
        "revoke all on table private.resend_delivery_events "
        "from public, anon, authenticated, service_role"
    ) in NORMALIZED
    assert "grant " not in NORMALIZED.split(
        "on table private.resend_delivery_events", 1
    )[1].split("create or replace function", 1)[0]

    table_definition = NORMALIZED.split(
        "create table if not exists private.resend_delivery_events (", 1
    )[1].split(
        "create index if not exists resend_delivery_events_window_idx", 1
    )[0]
    for prohibited in (
        "user_id ",
        "recipient ",
        "recipient_hash ",
        "email_address ",
        "subject ",
        "body ",
        "html ",
        "url ",
        "token ",
        "headers ",
        "raw_payload ",
        "jsonb",
        "provider_event_id ",
        "provider_email_id ",
    ):
        assert prohibited not in table_definition


def test_all_external_identifiers_are_lowercase_sha256_only():
    for column in (
        "provider_event_hash",
        "provider_email_hash",
        "payload_fingerprint",
    ):
        assert f"{column} ~ '^[0-9a-f]{{64}}$'" in NORMALIZED
        assert f"coalesce(p_{column}, '') !~ '^[0-9a-f]{{64}}$'" in NORMALIZED

    assert "payload_fingerprint text not null unique" in NORMALIZED
    assert "provider_event_hash text primary key" in NORMALIZED


def test_event_and_outcome_vocabularies_are_exact_and_content_free():
    exact_pairs = (
        ("email.sent", "accepted"),
        ("email.delivered", "delivered"),
        ("email.delivery_delayed", "transient"),
        ("email.failed", "failed"),
        ("email.suppressed", "suppressed"),
        ("email.complained", "complaint"),
    )
    for event_type, outcome in exact_pairs:
        assert (
            f"p_event_type = '{event_type}' and p_outcome_class = '{outcome}'"
            in NORMALIZED
        )

    assert (
        "p_event_type = 'email.bounced' and p_outcome_class in "
        "('permanent', 'transient', 'failed')"
    ) in NORMALIZED

    for excluded_event in ("email.opened", "email.clicked", "email.received"):
        assert excluded_event not in NORMALIZED

    assert "message_kind in ('verification', 'password_reset')" in NORMALIZED


def test_recording_and_aggregate_rpcs_are_service_role_only_and_pinned():
    assert (
        "create or replace function public.record_resend_delivery_event( "
        "p_provider_event_hash text, p_provider_email_hash text, "
        "p_payload_fingerprint text, p_environment text, p_message_kind text, "
        "p_event_type text, p_outcome_class text, p_occurred_at timestamptz ) "
        "returns boolean"
    ) in NORMALIZED

    record_signature = (
        "public.record_resend_delivery_event( "
        "text, text, text, text, text, text, text, timestamptz )"
    )
    aggregate_signature = (
        "public.resend_delivery_event_aggregate( "
        "timestamptz, timestamptz, text )"
    )
    for signature in (record_signature, aggregate_signature):
        assert (
            f"revoke all on function {signature} "
            "from public, anon, authenticated, service_role"
        ) in NORMALIZED
        assert f"grant execute on function {signature} to service_role" in NORMALIZED

    assert NORMALIZED.count("security definer") == 2
    assert NORMALIZED.count("set search_path = ''") == 2
    assert "on conflict do nothing" in NORMALIZED
    assert "resend event replay mismatch" in NORMALIZED


def test_aggregate_is_half_open_counts_only_and_returns_no_identifiers():
    start = NORMALIZED.index(
        "create or replace function public.resend_delivery_event_aggregate("
    )
    aggregate = NORMALIZED[start:]
    returns = aggregate.split("returns table (", 1)[1].split(") language", 1)[0]

    assert "events.occurred_at >= p_since" in aggregate
    assert "events.occurred_at < p_until" in aggregate
    assert "count(distinct scoped.provider_email_hash)" in aggregate
    assert "provider_event_hash" not in returns
    assert "provider_email_hash" not in returns
    assert "payload_fingerprint" not in returns
    assert "user_id" not in returns
    assert "email" not in returns
    assert "recipient" not in returns
    assert "url" not in returns
    assert "text" in returns  # only the fixed message-kind dimension


def test_postgres_ci_executes_the_resend_migration_gate():
    assert "resend-delivery-observability:" in WORKFLOW
    assert "tests/postgres/resend_delivery_event_baseline.sql" in WORKFLOW
    assert "migrations/20261007221534_resend_delivery_event_observability.sql" in WORKFLOW
    assert "tests/postgres/test_resend_delivery_event_migration.sql" in WORKFLOW
