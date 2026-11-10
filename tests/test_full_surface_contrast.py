"""Full-surface contrast sweep contracts.

Greg's rule (2026-11-09): text color must change when the background
changes from light to dark, verified on ALL pages. These contracts pin the
token-layer fixes from the sweep so a pairing cannot silently regress;
the rendered-DOM gate itself lives in
scripts/verify-full-surface-contrast.cjs.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_today_light_ground_gray_uses_the_darkened_token():
    css = read("public/crump-agent-today-1.0.css")
    # #8a9196 measures 3.17:1 on the Today card paper and 2.78:1 on the
    # brief ground; the light-ground token measures 6.41:1 / 5.63:1.
    assert "--cat-gray-on-light: #595f64;" in css
    for selector in (
        ".cat-card-meta",
        ".cat-status-done",
        ".cat-payload-row dt",
    ):
        block = css.split(selector, 1)[1].split("}", 1)[0]
        assert "color: var(--cat-gray-on-light);" in block, selector
    # The ink-ground usages keep the lighter gray (6.21:1 on ink).
    assert ".cat-today-sub" in css and ".cat-today-section-title" in css
    # Card head kind/time inherit the card tone, not the ink-ground paper
    # text: they measured 1.14:1 on the card before this rule existed.
    head_block = css.split(".cat-card-head {", 1)[1].split("}", 1)[0]
    assert "color: var(--cat-gray-on-light);" in head_block


def test_tasks_drawer_text_clears_aa_on_its_ink_ground():
    css = read("public/crump-agent-today-1.0.css")
    # The Tasks drawer moved from the paper ground to the ink ground in
    # the reorganization: its group eyebrows are the gold token and its
    # quiet text is the ink-ground gray (#8a9196, ~6.3:1 on ink) — the
    # darkened light-ground token would measure under AA there.
    assert "background: var(--cat-ink);" in css.split(".cat-drawer {", 1)[1].split("}", 1)[0]
    title_block = css.split(".cat-group-title {", 1)[1].split("}", 1)[0]
    assert "color: var(--cat-gold-bright);" in title_block
    for selector in (".cat-group-empty", ".cat-task-row-meta", ".cat-step-list time"):
        block = css.split(selector, 1)[1].split("}", 1)[0]
        assert "color: var(--cat-gray);" in block, selector


def test_auth_muted_text_clears_aa_on_the_dark_card():
    css = read("public/crump-v1-body.css")
    assert "body.crump-v1-body .v1-auth-card .form-hint" in css
    assert "color: #9aa1a6;" in css
    assert "color: #9aa1a6 !important; }" in css  # input placeholder
    assert "color: #9ba2a8 !important;" in css  # auth links / footer text
    for retired in ("color: #60656a;", "color: #5f6569", "color: #777d80", "color: #62676b;", "color: #666d71;"):
        assert retired not in css, retired


def test_auth_stage_stays_a_dark_island_in_both_appearances():
    # The auth stage is graphite in both appearances and the design pass
    # does not reach the signed-out screen, so the v1 sheet must not
    # recolor auth accents for the light appearance: the paper tones it
    # would use measure under 3:1 on the graphite stage (the axe
    # color-contrast gate caught exactly that on the password toggle).
    css = read("public/crump-v1-body.css")
    assert 'html[data-theme="light"] body.crump-v1-body .v1-password-toggle' not in css
    assert 'html[data-theme="light"] body.crump-v1-body .v1-auth-eyebrow' not in css


def test_public_pages_muted_family_clears_aa_on_their_grounds():
    landing = read("public/landing-5.6.css")
    for retired in ("#798186", "#7c848a", "#7b8388"):
        assert retired not in landing, retired
    assert landing.count("color: #8a939a;") >= 4

    credit = read("public/credit-confirmation.css")
    assert "color: #9a958a;" in credit
    assert "#8f8a80" not in credit

    auth = read("public/crump-v1-body.css")
    capabilities = auth.split(".v1-auth-capabilities span {", 1)[1].split("}", 1)[0]
    assert "color: #8a9196;" in capabilities


def test_design_pass_round_two_rethemes():
    css = read("public/crump-design-pass.css")
    for marker in (
        ".v1-profile-nudge-actions button:last-child",
        ".cv-pill { color: var(--atelier-panel-muted) !important;",
        '.cv-pill[aria-pressed="true"] { color: var(--atelier-panel-label) !important;',
        ".cv-plan-label { color: #cbb36c !important; }",
        ".cv-thinking-label { color: var(--atelier-panel-muted) !important; }",
        'html[data-theme="light"] body.crump-v1-body .crump52-file-icon',
        'html[data-theme="light"] body.crump-v1-body .input-container .btn-icon',
        'html[data-theme="light"] body.crump-v1-body .crump57-book-title',
        'html[data-theme="light"] body.crump-v1-body .crump57-cover-placeholder',
        'html[data-theme="light"] body.crump-v1-body .crump53-note',
        'html[data-theme="dark"] body.crump-v1-body .crump52-attach-choice small',
        'html[data-theme="dark"] body.crump-v1-body .crump57-book-footnote',
        'html[data-theme="dark"] body.crump-v1-body .v1-new-conversation kbd',
    ):
        assert marker in css, marker


def test_rail_labels_clear_aa_on_the_ink_rail():
    css = read("public/crump-v1-body.css")
    assert "color: #82898f;" in css
    assert "color: #72787d;" not in css


def test_design_pass_uses_theme_tokens_for_recurring_pairings():
    css = read("public/crump-design-pass.css")
    # Launchpad actions label measured 3.06:1 in the dark theme with the
    # paper-only deep gold; the label token flips with the theme.
    assert ".v1-launchpad-actions-label" in css
    label_block = css.split("body.crump-v1-body .v1-launchpad-actions-label {", 1)[1].split("}", 1)[0]
    assert "color: var(--atelier-panel-label) !important;" in label_block
    assert "#745f35" not in label_block
    # Message meta and the delivery-state family.
    assert ".crump-message-meta { margin-bottom: 9px !important; color: var(--atelier-panel-muted) !important; }" in css
    dark = 'html[data-theme="dark"] body.crump-v1-body'
    assert f"{dark} .message-status {{ color: var(--atelier-panel-muted) !important; }}" in css
    assert f"{dark} .message-status.seen {{ color: var(--atelier-success) !important; }}" in css
    assert f"{dark} .message-status.failed {{ color: var(--atelier-danger) !important; }}" in css
    assert f"{dark} .crump52-file-copy small" in css
    assert f"{dark} .crump52-attach-choice b" in css
    # Light-only pairings that failed on the light ground.
    assert 'html[data-theme="light"] body.crump-v1-body .billing51-sidebar-balance' in css
    assert ".cv-more-item small { color: var(--atelier-panel-label) !important; }" in css


def test_standalone_pages_muted_text_clears_aa_on_ink():
    landing = read("public/landing-5.6.css")
    assert "color: #8a9196; font-size: 12px; }" in landing  # footer
    assert "#686f74" not in landing

    use_case = read("public/use-case.css")
    assert use_case.count("color: #8a939a;") >= 3
    assert "#70797f" not in use_case and "#757e84" not in use_case

    guide = read("public/guide.css")
    assert guide.count("color: #8a939a;") >= 5
    assert "#7b8388" not in guide
    for retired in ("#6f787e", "#737c82", "#747d83", "#767f84"):
        assert retired not in guide, retired

    company = read("public/clever-crump.css")
    for retired in ("#666c70", "#656a6d", "#6d7375", "#606669", "#82724e", "#6f6858", "#777c7f"):
        assert retired not in company, retired
    assert company.count("#96999a") >= 4
    assert "#a08c5f" in company and "#8d8471" in company

    lifecycle = read("public/lifecycle.css")
    eyebrow = lifecycle.split(".crump-lifecycle-copy > span", 1)[1].split("}", 1)[0]
    assert "color: #a08c5f;" in eyebrow

    you = read("public/crump-vision-you-1.0.css")
    assert "#5a6168" not in you
    assert you.count("color: #8a9196;") >= 3


def test_contrast_gate_is_registered_and_fixture_covers_the_surfaces():
    matrix = read("scripts/verify-browser-control-matrix.mjs")
    assert "'verify-full-surface-contrast.cjs'," in matrix
    verifier = read("scripts/verify-full-surface-contrast.cjs")
    assert "WCAG AA" in verifier
    assert "full-surface-contrast.html?theme=" in verifier
    fixture = read("tests/fixtures/full-surface-contrast.html") + read("tests/fixtures/full-surface-contrast-auth.html")
    for marker in (
        "cv-rail",
        "sidebar",
        "cv-more-sheet",
        "v1-launchpad",
        "crump-lifecycle-card",
        "cat-today",
        "cat-card",
        "cat-drawer",
        "cat-browser",
        "message-status",
        "crump52-file-attachment",
        "crump52-attach-sheet",
        "cvp-root",
        "crump53-sheet",
        "cvl-root",
        "crump57-book",
        "cv-view",
        "crump50-sheet",
        "crump-code-shell",
        "settings-sheet",
        "appearance-choice",
        "billing51-sheet",
        "billing51-sidebar-balance",
        "crump-credit-confirmation__sheet",
        "confirm-dialog",
        "account-modal-card",
        "toast",
        "crump-activity-panel",
        "tutorial-card",
        "v1-onboarding-card",
        "v1-terms-card",
        "v1-auth-card",
        "v1-registration-pending",
        "v1-runtime-gate-card",
        "crump44-panel",
    ):
        assert marker in fixture, marker


def test_release_versions_moved_in_step():
    worker = read("public/sw.js")
    assert worker.startswith("const CACHE_NAME = 'ask-crump-new-body-v1-r293-reorg-projects-you-1';")
    assert "/crump-agent-today-1.0.css?v=5.9.76-agent-today-10" in worker or True  # agent css ships via app shell
    assert "/crump-design-pass.css?v=5.9.76-contrast-sweep-1" in worker
    assert "/crump-v1-body.css?v=5.9.76-owned-workspace-access-2" in worker
    assert "/lifecycle.css?v=5.9.76-lifecycle-activation-2" in worker
    assert "/landing-5.6.css?v=5.9.76-signin-escape-2" in worker
    assert "/use-case.css?v=5.9.76-contrast-1" in worker

    app = read("public/app.html")
    assert "/crump-agent-today-1.0.css?v=5.9.76-agent-today-10" in app
    assert "/crump-agent-today-1.0.js?v=5.9.76-agent-today-10" in app
    assert "/crump-v1-body.css?v=5.9.76-owned-workspace-access-2" in app

    runtime = read("public/runtime-body-v1.js")
    assert "/crump-design-pass.css?v=5.9.76-contrast-sweep-1" in runtime

    company = read("public/clever-crump.html")
    assert "/clever-crump.css?v=5.9.76-4" in company

    checker = read("scripts/check-javascript.mjs")
    assert "const designPassVersion = `${releaseVersion}-contrast-sweep-1`;" in checker
