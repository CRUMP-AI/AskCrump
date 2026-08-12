from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def test_same_page_login_is_serialized_and_confirmed():
    source = (PUBLIC / 'device-auth.js').read_text(encoding='utf-8')
    assert 'this.loginPromise = null' in source
    assert 'if (this.loginPromise) return this.loginPromise' in source
    assert 'confirmIssuedSession()' in source
    assert "fetch('/api/auth/check-session'" in source
    assert 'for (let attempt = 0; attempt < 2; attempt += 1)' in source
    assert "code: 'SESSION_ESTABLISHMENT_FAILED'" in source


def test_transient_session_check_does_not_clear_persisted_identity():
    source = (PUBLIC / 'device-auth.js').read_text(encoding='utf-8')
    assert 'if (!response.ok)' in source
    assert 'return this.sessionUnavailable' in source
    assert 'A definitive successful response saying "not authenticated" is the only' in source
    assert 'this.clearLocalState();' in source


def test_bootstrap_surfaces_unavailable_without_claiming_logout():
    source = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    assert 'if (session.unavailable)' in source
    assert 'Your saved sign-in was preserved' in source


def test_explicit_logout_still_clears_native_and_local_state():
    source = (PUBLIC / 'device-auth.js').read_text(encoding='utf-8')
    assert 'await window.CrumpAPI?.clearSessionToken?.();' in source
    assert 'this.clearLocalState();' in source
