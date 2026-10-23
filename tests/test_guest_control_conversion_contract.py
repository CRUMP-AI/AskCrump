from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
AUTH_SERVICE = (ROOT / "backend" / "auth_service.py").read_text(encoding="utf-8")
AUTH_ROUTE = (ROOT / "backend" / "routes" / "auth.py").read_text(encoding="utf-8")
CONTROL_SQL = (
    ROOT / "migrations" / "20261021040000_guest_mode_control.sql"
).read_text(encoding="utf-8")


def test_registration_has_a_narrow_control_independent_guest_identity_resolver():
    resolver = AUTH_SERVICE.split(
        "async def authenticate_guest_for_registration(", 1
    )[1].split("async def create_session(", 1)[0]

    assert "session_tokens_from_request(request, settings)" in resolver
    assert "'expires_at': gt(now)" in resolver
    assert "_registration_guest_session_is_eligible(session)" in resolver
    assert "not is_guest_user(user)" in resolver
    assert "guest_mode_enabled" not in resolver
    assert "get_guest_mode_control_v1" not in resolver

    registration = AUTH_ROUTE.split("async def register(", 1)[1].split(
        "@router.post('/guest')", 1
    )[0]
    assert "authenticate_guest_for_registration(request, db, settings)" in registration
    assert "filters={'id': eq(guest_user['id'])}" in registration
    assert "'guest_message_count'" not in registration
    assert "'usage_events'" not in registration


def test_only_database_control_revocations_are_eligible_for_conversion():
    eligibility = AUTH_SERVICE.split(
        "def _registration_guest_session_is_eligible(", 1
    )[1].split("async def authenticate_guest_for_registration(", 1)[0]

    assert "if revoked_at is None" in eligibility
    assert "device_info.get('guestControlRevokedAt')" in eligibility
    assert "revoked_timestamp == marked_timestamp" in eligibility
    assert "'guestControlRevokedAt', v_updated_at" in CONTROL_SQL
    assert "set revoked_at = v_updated_at" in CONTROL_SQL


def test_ordinary_guest_authentication_remains_fail_closed():
    ordinary = AUTH_SERVICE.split("async def authenticate_request(", 1)[1].split(
        "async def revoke_current_session(", 1
    )[0]
    assert "if is_guest_user(user) and not await guest_mode_enabled(db):" in ordinary
    assert "status_code=503" in ordinary
