from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261108050000_connected_oauth_runtime_authority.sql"
ADAPTER = ROOT / "backend" / "connected_app_oauth_supabase.py"


def test_runtime_authority_migration_is_forward_attested_and_private():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "b370daab7379a1e09a620719948d6699" in sql
    assert "cfd262b61a4f8c408b74b2ca18d97d8d" in sql
    assert "raise exception 'connected OAuth runtime authority target drifted'" in sql
    assert "set search_path = ''" in sql
    assert "set_config('search_path', 'pg_catalog,public', true)" in sql
    assert "oauth_permit_capability_custody" in sql
    assert "force row level security" in sql
    assert (
        "revoke all on table connected_app_private.oauth_permit_capability_custody\n"
        "  from public, anon, authenticated, service_role"
    ) in sql
    assert "connected_app_oauth_finalize_v2" in sql
    assert "p_authorization_issued_at timestamptz" in sql
    assert "p_authorization_snapshot_sha256 text" in sql
    assert "p_completion_binding_sha256 text" in sql
    assert "authorization_snapshot_sha256 = p_authorization_snapshot_sha256" in sql
    assert "set completion_binding_sha256 = p_completion_binding_sha256" not in sql
    assert "connected_app_oauth_consume_permit_v2" in sql
    assert "'claimed', true" in sql
    assert "'claimed', false" in sql
    assert "delete from connected_app_private.oauth_permit_capability_custody" in sql
    assert "revoke all on function public.connected_app_oauth_finalize_v1" in sql
    assert "revoke all on function public.connected_app_oauth_issue_permit_v1" in sql


def test_concrete_supabase_adapters_reconstruct_and_verify_restart_authority():
    source = ADAPTER.read_text(encoding="utf-8")

    assert "class SupabaseOAuthFlowRepository" in source
    assert "class SupabaseOAuthCompletionRepository" in source
    assert "class SupabaseConnectedAccountRegistry" in source
    assert "class SupabaseOAuthRepositoryCoordinator" in source
    assert "SupabaseOAuthSecretStore(database)" in source
    assert '"connected_app_oauth_finalize_v2"' in source
    assert '"connected_app_get_binding_v2"' in source
    assert '"connected_app_oauth_put_permit_capability_v2"' in source
    assert '"connected_app_oauth_consume_permit_v2"' in source
    assert "authorization.snapshot_sha256" in source
    assert "delegated_scope_plan" in source
    assert "authorization.granted_scopes_sha256" in source
    assert "_digest(broker_ref)" in source
    assert "capability='<redacted>'" not in source
    assert "secret='<redacted>'" in source
    assert "ProviderOAuth" not in source
