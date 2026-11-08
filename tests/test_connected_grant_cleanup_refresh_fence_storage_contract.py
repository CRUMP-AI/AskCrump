from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261108061000_connected_grant_cleanup_refresh_fence.sql"
CLEANUP = ROOT / "backend" / "connected_app_grant_cleanup.py"
OAUTH = ROOT / "backend" / "connected_app_durable_oauth.py"
STORES = ROOT / "backend" / "connected_app_durable_stores.py"
RACES = ROOT / "scripts" / "verify-connected-grant-cleanup-refresh-races-pg17.sql"
BEHAVIOR = ROOT / "tests" / "postgres" / "test_connected_grant_cleanup_refresh_fence.sql"


def test_migration_is_exact_private_forward_only_and_has_no_v1_refresh_fallback() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "e90e794c75b45084d89d6b1247d3287e" in sql
    assert "__TARGET_FINGERPRINT__" not in sql
    assert "connected cleanup/refresh target fingerprint drifted" in sql
    assert "connected cleanup/refresh postflight fingerprint drifted" in sql
    assert "set_config('search_path', 'pg_catalog,public', true)" in sql
    assert "set search_path = ''" in sql
    assert "provider_grant_cleanup_jobs" in sql
    assert "provider_grant_cleanup_claim_history" in sql
    assert "credential_refresh_lease_history" in sql
    assert "force row level security" in sql
    assert "connected_cleanup_owner_before_delete" in sql
    assert "connected_cleanup_credential_before_delete" in sql
    assert "connected_cleanup_provisional_before_delete" in sql
    assert "connected_app_provider_cleanup_release_recover_v1" in sql
    assert "oauth_provisional_tombstones" in sql
    assert "connected cleanup/refresh publication exposure refused" in sql
    credential_trigger = sql[
        sql.index("create or replace function connected_app_private.queue_credential_cleanup_v1") :
        sql.index("create or replace function connected_app_private.queue_provisional_cleanup_v1")
    ]
    provisional_trigger = sql[
        sql.index("create or replace function connected_app_private.queue_provisional_cleanup_v1") :
        sql.index("create or replace function connected_app_private.flag_owner_cleanup_v1")
    ]
    for trigger in (credential_trigger, provisional_trigger):
        assert trigger.index("for update") < trigger.index(
            "insert into connected_app_private.provider_grant_cleanup_claim_history"
        )
        assert trigger.index(
            "insert into connected_app_private.provider_grant_cleanup_claim_history"
        ) < trigger.index("insert into connected_app_private.provider_grant_cleanup_jobs")
    assert "credential_handle_sha256 = job.encrypted_record->>'credential_handle_sha256'" in sql
    assert "insert into connected_app_private.credential_refresh_lease_history" in sql
    assert "where lease_id = p_lease_id" in sql
    assert "revoke all on function public.connected_app_credential_claim_refresh_v1" in sql
    assert "revoke all on function public.connected_app_credential_finish_refresh_v1" in sql
    assert "revoke all on function public.connected_app_credential_quarantine_refresh_v1" in sql
    assert "grant execute on function public.connected_app_credential_claim_refresh_v1" not in sql
    assert "return public.connected_app_credential_claim_refresh_v1" not in sql
    assert "perform public.connected_app_credential_claim_refresh_v1" not in sql
    for table in (
        "credential_refresh_lease_history",
        "provider_grant_cleanup_jobs",
        "provider_grant_cleanup_claim_history",
    ):
        assert (
            f"revoke all on table connected_app_private.{table}\n"
            "  from public, anon, authenticated, service_role"
        ) in sql
    assert BEHAVIOR.exists()
    assert RACES.exists()


def test_cleanup_adapter_has_bounded_provider_specific_and_honest_outcomes() -> None:
    source = CLEANUP.read_text(encoding="utf-8")

    assert '"https://oauth2.googleapis.com/revoke"' in source
    assert "follow_redirects=False" in source
    assert "trust_env=False" in source
    assert '"Accept-Encoding": "identity"' in source
    assert "ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED" in source
    assert "class MicrosoftOAuthGrantRevoker" in source
    microsoft = source[source.index("class MicrosoftOAuthGrantRevoker") : source.index(
        "class ConnectedGrantCleanupWorker"
    )]
    assert "httpx" not in microsoft
    assert "USER_ACTION_REQUIRED" in microsoft
    assert '"connected_app_provider_cleanup_release_recover_v1"' in source
    assert '"connected_app_provider_cleanup_recover_v1"' in source
    assert "<redacted>" in source


def test_oauth_and_refresh_paths_use_durable_recovery_without_legacy_writers() -> None:
    oauth = OAUTH.read_text(encoding="utf-8")
    stores = STORES.read_text(encoding="utf-8")

    assert oauth.index("await self._grant_cleanup_store.begin(") < oauth.index(
        "await client.exchange_code("
    )
    assert "await self._grant_cleanup_store.attach(" in oauth
    assert "await self._grant_cleanup_store.release_recover(" in oauth
    assert "await self._store.erase_provisional_once(" in oauth
    assert oauth.index("await self._store.erase_provisional_once(") < oauth.index(
        "await self._grant_cleanup_store.release("
    )
    assert '"connected_app_credential_claim_refresh_v2"' in stores
    assert '"connected_app_credential_commit_refresh_v2"' in stores
    assert '"connected_app_credential_quarantine_refresh_v2"' in stores
    assert '"connected_app_credential_claim_refresh_v1"' not in stores
    assert '"connected_app_credential_finish_refresh_v1"' not in stores
