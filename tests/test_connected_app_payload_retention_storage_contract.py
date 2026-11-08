from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "20261108068600_connected_ciphertext_retention.sql"
).read_text(encoding="utf-8")


def test_retention_is_bounded_physical_erasure_for_both_ciphertext_vaults():
    assert "connected_app_purge_expired_ciphertext_v1" in SQL
    assert "p_payload_maximum not between 1 and 100" in SQL
    assert "p_plan_maximum not between 1 and 100" in SQL
    assert "p_loop_maximum not between 1 and 100" in SQL
    assert "delete from connected_app_private.payload_envelopes" in SQL
    assert "record_state='deleted'" in SQL
    assert "payload_ciphertext=null" in SQL
    assert "wrapped_key_ciphertext=null" in SQL
    assert "delete from connected_loop_private.envelopes" in SQL
    assert "'loop_envelopes_purged',loop_envelopes_purged" in SQL
    assert "where envelope.record_state='live' and envelope.expires_at<=now_at" in SQL


def test_retention_uses_owner_before_payload_and_plan_row_locks():
    put = SQL.index("create or replace function public.connected_app_payload_put_v1")
    purge = SQL.index(
        "create or replace function public.connected_app_purge_expired_ciphertext_v1"
    )
    assert SQL.index("owner_lock_v1(p_owner_id)", put, purge) < SQL.index(
        "'connected-payload:' || p_payload_id::text", put, purge
    )
    purge_sql = SQL[purge:]
    assert purge_sql.index("owner_lock_v1(candidate.owner_id)") < purge_sql.index(
        "'connected-payload:' || candidate.payload_id::text"
    )
    plan_loop = purge_sql.index("from connected_plan_private.envelopes")
    assert purge_sql.index("owner_lock_v1(candidate.owner_id)", plan_loop) < purge_sql.index(
        "from connected_plan_private.operations", plan_loop
    ) < purge_sql.index("from connected_plan_private.envelopes", plan_loop + 1)
    loop_envelopes = purge_sql.index("from connected_loop_private.envelopes")
    assert purge_sql.index(
        "owner_lock_v1(candidate.owner_id)", loop_envelopes
    ) < purge_sql.index("from connected_loop_private.loops", loop_envelopes) < purge_sql.index(
        "from connected_loop_private.steps", loop_envelopes
    ) < purge_sql.index("from connected_loop_private.envelopes", loop_envelopes + 1)


def test_payload_reads_share_the_purge_advisory_fence():
    read = SQL.index("create or replace function public.connected_app_payload_read_v1")
    purge = SQL.index(
        "create or replace function public.connected_app_purge_expired_ciphertext_v1"
    )
    read_sql = SQL[read:purge]
    assert "'connected-payload:' || p_payload_id::text" in read_sql
    assert read_sql.index("pg_advisory_xact_lock") < read_sql.index(
        "from connected_app_private.payload_tombstones"
    )


def test_retention_private_boundary_is_service_role_only_and_publication_safe():
    assert "revoke all on schema connected_retention_private" in SQL
    assert "from public,anon,authenticated,service_role" in SQL
    assert (
        "grant execute on function public.connected_app_purge_expired_ciphertext_v1(\n"
        "  integer,integer,integer\n)\n"
        "  to service_role"
    ) in SQL
    assert "publication exposure refused" in SQL
    assert "has_schema_privilege(\n       'service_role','connected_retention_private','usage')" in SQL


def test_retention_migration_is_not_left_with_unfrozen_placeholders():
    # This assertion intentionally remains red until the exact PG17 target is
    # computed and pinned after migration 68500 is frozen.
    assert "__PREDECESSOR_FINGERPRINT__" not in SQL
    assert "__TARGET_FINGERPRINT__" not in SQL
