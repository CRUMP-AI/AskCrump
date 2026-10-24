from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_production_transactional_email_cannot_use_resend_test_sender():
    config = read("backend/config.py")

    assert "def _transactional_from_email(environment: str, configured: str | None) -> str:" in config
    assert "Ask Crump <noreply@askcrump.com>" in config
    assert "environment == 'production'" in config
    assert "'@resend.dev' in value.lower()" in config
    assert "from_email=_transactional_from_email(environment, os.getenv('FROM_EMAIL'))" in config


def test_password_reset_finishes_verification_for_inbox_owner():
    auth = read("backend/routes/auth.py")
    migration = read("migrations/20261024051228_atomic_password_reset.sql")

    reset_start = auth.index("@router.post('/reset-password')")
    reset_end = auth.index("@router.post('/resend-verification')")
    reset_route = auth[reset_start:reset_end]

    assert "'consume_password_reset_v1'" in reset_route
    assert "'p_token_hash': token_hash(payload.token)" in reset_route
    assert "'p_password_hash': hash_password(payload.newPassword)" in reset_route
    assert "db.select_one" not in reset_route
    assert "db.update" not in reset_route

    assert "set password_hash = p_password_hash" in migration
    assert "is_verified = true" in migration
    assert "is_guest = false" in migration
    assert "verification_token_hash = null" in migration
    assert "password_reset_token_hash = null" in migration
    assert "update public.sessions" in migration


def test_forgot_password_keeps_account_enumeration_message_generic():
    auth = read("backend/routes/auth.py")

    forgot_start = auth.index("@router.post('/forgot-password')")
    forgot_end = auth.index("@router.post('/reset-password')")
    forgot_route = auth[forgot_start:forgot_end]

    assert "Always return the same result to prevent account enumeration." in forgot_route
    assert "If an account exists for that email, a reset link has been sent." in forgot_route


def test_login_finalization_and_password_upgrade_share_one_database_cas():
    auth = read("backend/routes/auth.py")
    service = read("backend/auth_service.py")
    migration = read("migrations/20261024051228_atomic_password_reset.sql")

    login_start = auth.index("@router.post('/login')")
    login_end = auth.index("@router.api_route('/check-session'")
    login_route = auth[login_start:login_end]

    assert "finalize_login_session(" in login_route
    assert "expected_password_hash=expected_password_hash" in login_route
    assert "upgraded_password_hash=upgraded_password_hash" in login_route
    assert "create_session(" not in login_route
    assert "db.update" not in login_route
    assert login_route.index("if finalized is None:") < login_route.index(
        "set_session_cookie(response, raw_token, request)"
    )

    helper = service.split("async def finalize_login_session(", 1)[1].split(
        "\n\nasync def create_session(", 1
    )[0]
    assert "'finalize_password_login_v1'" in helper
    assert "'p_expected_password_hash': expected_password_hash" in helper
    assert "'p_upgraded_password_hash': upgraded_password_hash" in helper
    assert "db.insert" not in helper
    assert "db.upsert" not in helper
    assert "db.update" not in helper

    function = migration.split(
        "create or replace function public.finalize_password_login_v1(", 1
    )[1].split("revoke all on function public.consume_password_reset_v1", 1)[0]
    assert function.index("from public.users as account") < function.index("for update;")
    assert function.index("for update;") < function.index(
        "v_user.password_hash is distinct from p_expected_password_hash"
    )
    assert function.index("set password_hash = coalesce(") < function.index(
        "insert into public.sessions as persisted"
    )
    assert "set search_path = ''" in function


def test_registered_verification_and_session_mint_share_reset_serialization():
    auth = read("backend/routes/auth.py")
    service = read("backend/auth_service.py")
    migration = read("migrations/20261024051228_atomic_password_reset.sql")

    verify_start = auth.index("@router.get('/verify-email')")
    verify_route = auth[verify_start:]
    assert "verify_registered_and_create_session(" in verify_route
    assert "verification_token_hash=verification_token_hash" in verify_route
    assert "db.update(" not in verify_route
    assert "raw_token, _ = await create_session(" not in verify_route
    assert verify_route.index("if atomic_result:") < verify_route.index(
        "set_session_cookie(response, raw_token, request)"
    )

    helper = service.split(
        "async def verify_registered_and_create_session(", 1
    )[1].split("\n\nasync def finalize_login_session(", 1)[0]
    assert "'verify_registered_and_create_session_v1'" in helper
    assert "'p_verification_token_hash': verification_token_hash" in helper
    assert "db.insert" not in helper
    assert "db.upsert" not in helper
    assert "db.update" not in helper

    function = migration.split(
        "create or replace function public.verify_registered_and_create_session_v1(",
        1,
    )[1].split("revoke all on function public.consume_password_reset_v1", 1)[0]
    assert function.index("from public.users as account") < function.index("for update;")
    assert function.index("for update;") < function.index(
        "v_user.verification_token_hash is distinct from p_verification_token_hash"
    )
    assert function.index("set is_verified = true") < function.index(
        "insert into public.sessions as persisted"
    )
    assert "set search_path = ''" in function


def test_postgres_gate_exercises_reset_login_verification_races_and_acl_refusals():
    workflow = read(".github/workflows/postgres-migration-gate.yml")
    job = workflow.split("registration-growth-cohorts:", 1)[1].split(
        "\n  chat-claim-and-artifact-versioning:", 1
    )[0]

    ordered = [
        "tests/postgres/atomic_password_reset_duplicate_fixture.sql",
        "migrations/20261024051228_atomic_password_reset.sql",
        "tests/postgres/test_atomic_password_reset_migration.sql",
        "tests/postgres/test_atomic_password_login_migration.sql",
        "tests/postgres/test_atomic_registered_verification_migration.sql",
        "tests/postgres/test_atomic_password_reset_concurrency.sh",
        "tests/postgres/atomic_password_reset_acl_drift_fixture.sql",
        "tests/postgres/atomic_password_login_acl_drift_fixture.sql",
        "tests/postgres/atomic_registered_verification_acl_drift_fixture.sql",
    ]
    positions = [job.index(path) for path in ordered]
    assert positions == sorted(positions)
    assert "--single-transaction" in job
    assert "Unexpected consume_password_reset_v1 owner or ACL" in job
    assert "Unexpected finalize_password_login_v1 owner or ACL" in job
    assert "Unexpected verify_registered_and_create_session_v1 owner or ACL" in job
