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

    reset_start = auth.index("@router.post('/reset-password')")
    reset_end = auth.index("@router.post('/resend-verification')")
    reset_route = auth[reset_start:reset_end]

    assert "'is_verified': True" in reset_route
    assert "'verification_token_hash': None" in reset_route
    assert "'verification_token_expires': None" in reset_route
    assert "'password_reset_token_hash': None" in reset_route
    assert "'password_reset_expires': None" in reset_route
    assert "filters={'id': eq(user['id'])}" in reset_route


def test_forgot_password_keeps_account_enumeration_message_generic():
    auth = read("backend/routes/auth.py")

    forgot_start = auth.index("@router.post('/forgot-password')")
    forgot_end = auth.index("@router.post('/reset-password')")
    forgot_route = auth[forgot_start:forgot_end]

    assert "Always return the same result to prevent account enumeration." in forgot_route
    assert "If an account exists for that email, a reset link has been sent." in forgot_route
