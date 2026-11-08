from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "20261108068700_connected_oauth_callback_owner_binding.sql"
).read_text(encoding="utf-8")


def test_callback_v2_requires_current_owner_and_session_before_and_after_lock():
    assert "connected_app_operator_prepare_oauth_callback_v2" in SQL
    assert "flow_row.owner_id<>p_owner_id" in SQL
    assert "flow_row.session_binding_sha256<>p_session_binding_sha256" in SQL
    first_check = SQL.index("flow_row.owner_id<>p_owner_id")
    owner_lock = SQL.index("owner_lock_v1(p_owner_id)", first_check)
    second_check = SQL.index("flow_row.owner_id<>p_owner_id", owner_lock)
    callback_lock = SQL.index("oauth_callback_requests", second_check)
    assert first_check < owner_lock < second_check < callback_lock


def test_legacy_unbound_callback_is_not_service_role_callable():
    expected = (
        "revoke all on function public.connected_app_operator_prepare_oauth_callback_v1(\n"
        "  text,text,text,timestamptz\n"
        ") from public,anon,authenticated,service_role"
    )
    assert expected in SQL
    assert (
        "grant execute on function public.connected_app_operator_prepare_oauth_callback_v2"
        in SQL
    )
    assert "connected_app_operator_deny_oauth_callback_v1" in SQL
    assert "p_error<>'access_denied'" in SQL
    assert "connected_oauth_binding_private.denial_receipts" in SQL


def test_duplicate_loser_has_canonical_replayable_inactive_receipt():
    assert "connected_oauth_binding_private.inactive_completions" in SQL
    assert "connected_app_oauth_read_completion_v3" in SQL
    assert "inactive OAuth completion replay drifted" in SQL
    assert "from public,anon,authenticated,service_role" in SQL
    assert "grant execute on function public.connected_app_oauth_read_completion_v3" in SQL


def test_exactly_one_active_connection_per_provider_resource_is_enforced():
    assert "duplicate active connected account requires operator resolution" in SQL
    assert "connected_app_connections_one_active_resource_idx" in SQL
    assert "on connected_app_private.connections(owner_id,provider,resource)" in SQL
    assert "where authorization_state='active'" in SQL


def test_oauth_binding_migration_is_not_left_with_unfrozen_placeholders():
    assert "__PREDECESSOR_FINGERPRINT__" not in SQL
    assert "__TARGET_FINGERPRINT__" not in SQL
