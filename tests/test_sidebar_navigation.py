from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def _button(html: str, element_id: str) -> str:
    match = re.search(
        rf'<button\s+id="{re.escape(element_id)}".*?</button>',
        html,
        flags=re.DOTALL,
    )
    assert match, f'Missing button #{element_id}'
    return match.group(0)


def test_settings_and_billing_have_one_explicit_sidebar_destination_each():
    html = (PUBLIC / 'app.html').read_text(encoding='utf-8')

    assert html.count('id="settingsBtn"') == 1
    assert html.count('id="upgradeBtnSidebar"') == 1
    assert 'data-v1-command="settings"' not in html
    assert 'data-v1-command="billing"' not in html
    assert 'v1-rail-spacer' not in html

    settings = _button(html, 'settingsBtn')
    billing = _button(html, 'upgradeBtnSidebar')
    assert '<svg' not in settings
    assert '<span>Settings</span>' in settings
    assert '<svg' not in billing
    assert '<span>Plan & credits</span>' in billing


def test_removed_rail_commands_have_no_stale_command_handlers():
    js = (PUBLIC / 'crump-v1-body.js').read_text(encoding='utf-8')
    assert "case 'settings':" not in js
    assert "case 'billing':" not in js
    assert 'v1-rail-spacer' not in (PUBLIC / 'crump-v1-body.css').read_text(encoding='utf-8')


def test_credit_badge_remains_attached_to_plan_row_and_mobile_drawer_closes():
    billing_js = (PUBLIC / 'crump-billing-5.1.js').read_text(encoding='utf-8')
    billing_css = (PUBLIC / 'crump-billing-5.1.css').read_text(encoding='utf-8')
    body_css = (PUBLIC / 'crump-v1-body.css').read_text(encoding='utf-8')
    app_js = (PUBLIC / 'app.js').read_text(encoding='utf-8')

    assert "const button = $('#upgradeBtnSidebar');" in billing_js
    assert 'button.appendChild(badge);' in billing_js
    assert "$('#sidebar')?.classList.remove('active');" in billing_js
    assert "document.getElementById('sidebar')?.classList.remove('active');" in app_js
    assert '#upgradeBtnSidebar .billing51-sidebar-balance' in billing_css
    assert 'SIDEBAR NAVIGATION HARDENING — 2026-08-11' in body_css
    assert 'display: flex !important;' in body_css
