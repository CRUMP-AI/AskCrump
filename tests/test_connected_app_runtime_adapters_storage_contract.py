from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261108058000_connected_runtime_ledger_binding.sql"
SOURCE = MIGRATION.read_text(encoding="utf-8")


def _body(name: str) -> str:
    match = re.search(
        rf"create or replace function public\.{name}\(.*?\)\s*returns jsonb.*?as \$fn\$(.*?)\$fn\$;",
        SOURCE,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None
    return match.group(1).lower()


def test_v2_claim_persists_and_compares_exact_invocation_binding() -> None:
    body = _body("connected_app_claim_action_v2")
    assert "p_invocation_binding_sha256" in body
    assert "invocation_binding_sha256" in body
    assert "action_row.invocation_binding_sha256 <> p_invocation_binding_sha256" in body
    assert "p_operation_id <> p_action_id" in body


def test_v2_settlement_binds_claim_fence_and_exact_terminal_replay() -> None:
    body = _body("connected_app_settle_action_v2")
    for contract in (
        "action_row.claim_id <> p_claim_id",
        "action_row.fencing_token <> p_fencing_token",
        "action_row.invocation_binding_sha256 <> p_invocation_binding_sha256",
        "terminal_resource_version_sha256",
        "provider_request_id_sha256",
        "provider_resource_id_sha256",
        "action_row.preobserve_use_nonce",
    ):
        assert contract in body
    assert "p_terminal_outcome not in ('read', 'succeeded', 'ambiguous')" in body


def test_v2_access_recovery_rebinds_fresh_authority_and_invocation() -> None:
    body = _body("connected_app_recover_access_v2")
    for contract in (
        "action_row.claim_id <> p_expired_claim_id",
        "action_row.invocation_binding_sha256 <> p_invocation_binding_sha256",
        "grant_id = p_grant_id",
        "authority_sha256 = p_authority_sha256",
        "execution_deadline = p_execution_deadline",
    ):
        assert contract in body


def test_legacy_claim_read_recover_settle_are_revoked_after_v2_composition() -> None:
    for name in (
        "connected_app_claim_action_v1",
        "connected_app_read_action_v1",
        "connected_app_recover_access_v1",
        "connected_app_settle_action_v1",
    ):
        assert re.search(
            rf"revoke all on function public\.{name}\(.*?\)\s*from service_role;",
            SOURCE,
            re.IGNORECASE | re.DOTALL,
        )
    for name in (
        "connected_app_claim_action_v2",
        "connected_app_read_action_v2",
        "connected_app_recover_access_v2",
        "connected_app_settle_action_v2",
    ):
        assert re.search(
            rf"grant execute on function public\.{name}\(.*?\)\s*to service_role;",
            SOURCE,
            re.IGNORECASE | re.DOTALL,
        )


def test_migration_refuses_backfill_and_has_exact_target_fingerprint() -> None:
    assert "cannot backfill invocation binding" in SOURCE
    assert "using errcode = '55000'" in SOURCE
    assert "192b3c7abb884d47736df936c1820bc9" in SOURCE
    assert "TARGET_FINGERPRINT" not in SOURCE
