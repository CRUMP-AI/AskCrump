from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_web_and_native_runtime_fetch_assets_in_parallel_without_reordering_execution():
    web = read("public/runtime-body-v1.js")
    native = read("scripts/build-native.mjs")

    for source in (web, native):
        assert "const enhancementStyles = Object.freeze([" in source
        assert "const finalScripts = Object.freeze([" in source
        assert "const scriptPlan = Object.freeze([" in source
        assert "function primeScript(url, key)" in source
        assert "function primeScripts(entries)" in source
        assert "primeScripts(scriptPlan);" in source
        assert "const stylesReady = Promise.all(" in source
        assert "[...workspaceStyles, ...enhancementStyles].map" in source
        assert "async function loadStyle(url, key)" in source
        assert "async function loadScript(url, key)" in source
        assert "await loadStyleOnce(url" in source
        assert "await loadScriptOnce(url" in source
        assert "Workspace style unavailable." in source
        assert "Workspace script unavailable." in source
        assert "node.remove();" in source
        assert "const node = existing.cloneNode();" in source
        assert "document.head.appendChild(existing)" not in source
        assert "document.documentElement.dataset.crumpBodyRuntime = 'failed';" in source
        assert "Your sign-in is safe" in source
        assert "for (const [url, key] of scriptPlan)" in source or "for (const [url,key] of scriptPlan)" in source

        styles_start = source.index("const stylesReady = Promise.all(")
        prime_start = source.index("primeScripts(scriptPlan);", styles_start)
        await_start = source.index("await stylesReady;", prime_start)
        execute_start = source.index("for (const [url", await_start)
        assert styles_start < prime_start < await_start < execute_start

    assert "node.rel = 'preload';" in web
    assert "node.as = 'script';" in web
    assert 'node.dataset.crumpScriptPreload = key;' in web


def test_parallel_runtime_asset_is_versioned_for_web_pwa_and_native():
    shell = read("public/app.html")
    worker = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")

    asset = "/runtime-body-v1.js?v=5.9.76-document-delivery-focused-1"
    assert asset in shell
    assert asset in worker
    assert "ask-crump-new-body-v1-r251" in worker
    assert "ask-crump-new-body-v1-r251" in checker


def test_runtime_fetch_fixture_is_credential_free_and_measures_the_full_plan():
    fixture = read("tests/fixtures/workspace-runtime-fetch-plan.html")
    verifier = read("scripts/verify-workspace-runtime-fetch-plan.cjs")
    matrix = read("scripts/verify-browser-control-matrix.mjs")

    assert "/public/runtime-body-v1.js?v=workspace-fetch-plan-fixture-3" in fixture
    assert 'aria-label="Maximum concurrent styles"' in fixture
    assert 'aria-label="Scripts preloaded before execution"' in fixture
    assert 'aria-label="First executed script"' in fixture
    assert 'aria-label="Last executed script"' in fixture
    assert 'aria-label="Simulated runtime milliseconds"' in fixture
    assert 'aria-label="Browser errors"' in fixture
    assert 'aria-label="First style attempts"' in fixture
    assert 'aria-label="First script attempts"' in fixture
    assert 'aria-label="Runtime ready events"' in fixture
    assert 'aria-label="Runtime failure message"' in fixture
    assert "simulatedFetchMs = 120" in fixture
    assert "style-retry" in fixture
    assert "script-retry" in fixture
    assert "style-fail" in fixture
    assert "__fixtureAllowAssetSuccess" in fixture
    assert '<link rel="icon" href="data:,">' in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture.lower()
    assert "verify-workspace-runtime-fetch-plan.cjs" in matrix
    assert "evidence.maxStyles, 17" in verifier
    assert "evidence.preloadCount, 34" in verifier
    assert "mode === 'style-retry' ? 18 : 17" in verifier
    assert "mode === 'script-retry' ? 35 : 34" in verifier
    assert "evidence.styleAttempts, mode === 'style-retry' ? 2 : 1" in verifier
    assert "evidence.scriptAttempts, mode === 'script-retry' ? 2 : 1" in verifier
    assert "failureMessage: 'Ask Crump could not finish loading your workspace." in verifier
    assert "results['style-fail-recovery']" in verifier
    assert "evidence.runtimeMs > 0 && evidence.runtimeMs < 1_000" in verifier
    assert "password" not in verifier.lower()
    assert "askcrump.com" not in verifier.lower()


def test_returning_workspace_uses_precache_without_staling_the_shell():
    worker = read("public/sw.js")
    verifier = read("scripts/verify-service-worker-returning-load.cjs")
    matrix = read("scripts/verify-browser-control-matrix.mjs")

    assert "function mustRevalidate(request, url)" in worker
    assert "request.mode === 'navigate'" in worker
    assert "url.pathname === '/app.html'" in worker
    assert "url.pathname === '/app.js'" in worker
    assert "async function cacheFirst(request)" in worker
    assert "bootCritical(request, url)\n      ? cacheFirst(request)" in worker
    assert "originAssetRequests" in verifier
    assert "assert.equal(counts.get(fixturePath), 1" in verifier
    assert "verify-service-worker-returning-load.cjs" in matrix
    assert "verify-document-delivery-cache-upgrade.cjs" in matrix
    assert "askcrump.com" not in verifier.lower()
    assert "password" not in verifier.lower()
