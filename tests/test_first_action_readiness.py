from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_product_starter_waits_for_the_real_runtime_instead_of_a_timer_guess():
    body = read("crump-v1-body.js")
    runtime = read("runtime-body-v1.js")

    assert "let pendingProductTab = '';" in body
    assert "window.addEventListener('crump:body-runtime-ready', flushPendingProduct);" in body
    assert "document.documentElement.dataset.crumpBodyRuntime === 'ready'" in body
    assert "window.setTimeout(() => window.CrumpProduct53?.open?.(tab), 120)" not in body
    assert runtime.index("['/crump-product-5.3.js?v=5.9.76-project-limit-plan-dormant-1', 'crumpproduct53']") < runtime.index(
        "window.dispatchEvent(new CustomEvent('crump:body-runtime-ready'))"
    )
    assert "for (const [url, key] of scriptPlan)" in runtime


def test_queued_product_starter_has_visible_progress_and_an_explicit_failure_path():
    body = read("crump-v1-body.js")

    assert "setProductLaunchBusy(tab, true);" in body
    assert "button.setAttribute('aria-busy', 'true')" in body
    assert "marker.textContent = busy ? '…' : marker.dataset.v1ReadyMarker" in body
    assert "setProductLaunchBusy(tab, false);" in body
    assert "did not finish loading. Refresh Ask Crump and try again." in body


def test_latest_product_choice_wins_without_changing_starter_measurement_semantics():
    body = read("crump-v1-body.js")

    assert "if (pendingProductTab && pendingProductTab !== tab)" in body
    assert "setProductLaunchBusy(pendingProductTab, false);" in body
    assert "pendingProductTab = tab;" in body
    assert "eventKey: 'first-starter-intent'" in body
    assert "source: command" in body


def test_browser_fixture_exercises_projects_and_video_without_credentials_or_network_writes():
    fixture = (ROOT / "tests" / "fixtures" / "launchpad-runtime-race.html").read_text(
        encoding="utf-8"
    )

    assert 'data-v1-command="projects"' in fixture
    assert 'data-v1-command="video"' in fixture
    assert "window.makeProductRuntimeReady" in fixture
    assert "window.__openedProductTabs.push(tab)" in fixture
    assert "fetch(" not in fixture
    assert "password" not in fixture.lower()


def test_launchpad_actions_have_clean_names_and_described_purpose():
    shell = read("app.html")

    actions = (
        ("Focus", "Think with Crump"),
        ("Research", "Research something"),
        ("File", "Analyze a file"),
        ("Image", "Create an image"),
        ("Projects", "Start or open a Project"),
        ("Video", "Create a video"),
    )
    for suffix, label in actions:
        assert f'aria-labelledby="v1Launch{suffix}Title"' in shell
        assert f'aria-describedby="v1Launch{suffix}Description"' in shell
        assert f'id="v1Launch{suffix}Title">{label}</strong>' in shell

    launchpad = shell[shell.index('<div class="v1-launchpad-grid">'):shell.index('<div class="v1-launchpad-foot"')]
    assert launchpad.count('<b aria-hidden="true">↗</b>') == 6
    assert '<span class="v1-launch-icon">✦</span>' not in launchpad


def test_first_action_browser_proof_is_credential_free_and_covers_all_six_choices():
    verifier = (ROOT / "scripts" / "verify-first-action-browser.cjs").read_text(encoding="utf-8")

    for label in (
        "Think with Crump",
        "Research something",
        "Analyze a file",
        "Create an image",
        "Start or open a Project",
        "Create a video",
    ):
        assert label in verifier
    assert "first-starter-intent" in verifier
    assert "password" not in verifier.lower()
    assert "fetch(" not in verifier
