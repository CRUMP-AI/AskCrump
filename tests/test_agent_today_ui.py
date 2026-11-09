"""Contract for the additive Agent Today layer on the app shell.

The layer is two new static files loaded last in app.html. It renders the
Today surface (approvals, live work, brief connection card), the Tasks
drawer, and the browser panel shell from the agent endpoints, and it must
stay honest while those endpoints are still landing: no staged data, and
the browser panel states plainly that live sessions are not available yet.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def test_app_html_loads_agent_today_layer_last_with_versioned_assets():
    app = read('public/app.html')
    css = '/crump-agent-today-1.0.css?v=5.9.76-agent-today-1'
    js = '/crump-agent-today-1.0.js?v=5.9.76-agent-today-1'
    assert css in app
    assert js in app
    assert (PUBLIC / 'crump-agent-today-1.0.css').exists()
    assert (PUBLIC / 'crump-agent-today-1.0.js').exists()
    # Loaded last: after the vision shell and the auth controller, so the
    # layer can sit on top of the shell it extends.
    assert app.index(js) > app.index('/crump-vision-shell-1.0.js')
    assert app.index(js) > app.index('/auth-controller.js')
    assert app.index(css) > app.index('/crump-vision-shell-1.0.css')


def test_today_layer_reads_the_agent_contracts_with_the_owner_header():
    js = read('public/crump-agent-today-1.0.js')
    assert "'/api/agent/capabilities'" in js
    assert "'/api/agent/approvals'" in js
    assert "'/api/agent/runs'" in js
    assert '/decision' in js
    assert "decision: decision" in js
    assert "'X-Ask-Crump-Expected-Owner'" in js
    assert "credentials: 'include'" in js


def test_today_layer_renders_approvals_live_work_and_the_brief_card():
    js = read('public/crump-agent-today-1.0.js')
    for needle in (
        'Waiting on you',
        'Live work',
        'Connect Google',
        'Built in Savannah',
        'browser.act',
        'Open browser',
        'Nothing needs you right now',
    ):
        assert needle in js, needle


def test_browser_panel_is_honest_about_execution_not_being_live():
    js = read('public/crump-agent-today-1.0.js')
    assert 'Per-user browser sessions are not live yet' in js
    assert 'pauseBtn.disabled = true' in js
    assert 'takeOverBtn.disabled = true' in js
    # No embedded browsing surface may be faked.
    assert 'iframe' not in js.lower()


def test_today_layer_declutters_without_removing_features():
    css = read('public/crump-agent-today-1.0.css')
    assert '[data-starter-prompt]' in css
    assert '.crump50-tool-chip' in css
    assert '#tutorialOverlay' in css


def test_today_layer_uses_the_house_palette_and_type():
    css = read('public/crump-agent-today-1.0.css')
    for needle in ('#070a0e', '#d5b971', '#b69855', '#f1efe9', '#8a9196', 'Georgia'):
        assert needle in css, needle
    assert 'min-height: 44px' in css


def test_nav_relabels_home_and_adds_tasks_without_touching_the_shell():
    js = read('public/crump-agent-today-1.0.js')
    assert 'data-cv-destination' in js
    assert 'data-cat-tasks' in js
    assert "'Today'" in js or '"Today"' in js or "'Today'" in js
    shell = read('public/crump-vision-shell-1.0.js')
    assert 'crump-agent-today' not in shell
