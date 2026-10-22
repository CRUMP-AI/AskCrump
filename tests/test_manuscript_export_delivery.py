from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_project_manuscript_export_uses_one_guarded_canonical_private_file_handoff():
    product = read("public/crump-product-5.3.js")
    start = product.index("const MANUSCRIPT_EXPORT_FORMATS")
    end = product.index("\n  function libraryCategory", start)
    export = product[start:end]

    assert "new Set(['docx', 'pdf', 'epub'])" in export
    assert "state.manuscriptExportInFlight" in export
    assert "if (state.manuscriptExportInFlight) return false" in export
    assert "window.CrumpFileTools.open(file, true)" in export
    assert "await Promise.resolve" in export
    assert "if (!file || (!fileId && !fileUrl))" in export
    assert "`/api/files/${encodeURIComponent(fileId)}/content?download=1`" in export
    assert "window.location.assign" in export
    assert "window.open" not in export
    assert "_blank" not in export
    assert "file.url}?download=1" not in export
    assert "button.disabled = true" in export
    assert "button.setAttribute('aria-busy', 'true')" in export
    assert "state.manuscriptExportInFlight = false" in export
    assert "button.disabled = disabled" in export
    assert "button.textContent = label" in export
    assert "button.removeAttribute('aria-busy')" in export


def test_project_manuscript_export_real_script_fixture_covers_delivery_and_failures():
    fixture = read("tests/fixtures/manuscript-export-delivery.html")
    verifier = read("scripts/verify-manuscript-export-delivery.cjs")
    package = read("package.json")

    assert "/public/crump-product-5.3.js?v=manuscript-export-delivery-fixture-1" in fixture
    assert "window.fixtureExportRequests" in fixture
    assert "window.fixtureFileHandoffs" in fixture
    assert "window.fixtureWindowOpenCalls" in fixture
    assert "https://fixture.supabase.co/storage/v1/object/sign/private/" in fixture
    for format_name in ("docx", "pdf", "epub"):
        assert format_name in verifier
    assert "result.requests.length, 1" in verifier
    assert "result.handoffs.length, 1" in verifier
    assert "rapidPending.requests.length, 1" in verifier
    assert "missing-file" in verifier
    assert "Fixture export request failed." in verifier
    assert "popupUrls" in verifier
    assert '"test:manuscript-export-delivery"' in package
    assert "npm run test:manuscript-export-delivery" in package


def test_project_manuscript_export_runtime_is_cache_busted():
    loader = read("public/crump-product-loader.js")

    assert "/crump-product-5.3.js?v=5.9.76-manuscript-export-delivery-1" in loader
    assert "/crump-product-5.3.js?v=5.9.76-response-continuity-cleanup-1" not in loader
