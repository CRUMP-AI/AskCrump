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

    asset = "/runtime-body-v1.js?v=5.9.76-local-photo-studio-loader-1"
    assert asset in shell
    assert asset in worker
    assert "ask-crump-new-body-v1-r211" in worker
    assert "ask-crump-new-body-v1-r211" in checker


def test_runtime_fetch_fixture_is_credential_free_and_measures_the_full_plan():
    fixture = read("tests/fixtures/workspace-runtime-fetch-plan.html")

    assert "/public/runtime-body-v1.js?v=workspace-fetch-plan-fixture-2" in fixture
    assert 'aria-label="Maximum concurrent styles"' in fixture
    assert 'aria-label="Scripts preloaded before execution"' in fixture
    assert 'aria-label="First executed script"' in fixture
    assert 'aria-label="Last executed script"' in fixture
    assert 'aria-label="Simulated runtime milliseconds"' in fixture
    assert 'aria-label="Browser errors"' in fixture
    assert "simulatedFetchMs = 120" in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture.lower()
