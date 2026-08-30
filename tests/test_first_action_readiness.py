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
    assert runtime.index("['/crump-product-5.3.js?v=5.9.76-intelligence-architecture-1', 'crumpproduct53']") < runtime.index(
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
