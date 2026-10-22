import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_library_lifecycle_runtime_fences_account_modal_and_resource_effects():
    library = read("public/crump-library-5.7.js")

    for contract in (
        "const libraryOperations = new Set();",
        "const libraryOverlayOperations = new WeakMap();",
        "const libraryModalIdentity = new WeakMap();",
        "const libraryRefreshes = new Map();",
        "function beginLibraryOperation(surface, {",
        "function activeLibraryOperation(operation)",
        "function assertLibraryOperationCurrent(operation)",
        "function finishLibraryOperation(operation)",
        "function abortLibraryOverlayOperations(overlay)",
        "function abortAllLibraryOperations()",
        "function beginLibraryRefresh(key, parentOperation = null)",
        "function libraryRefreshIsCurrent(refresh)",
        "function finishLibraryRefresh(refresh)",
        "function abortAllLibraryRefreshes()",
    ):
        assert contract in library

    assert "abortLibraryOverlayOperations(overlay);" in library
    assert "abortAllLibraryOperations();" in library
    assert "abortAllLibraryRefreshes();" in library
    assert "operation.controller.signal" in library
    assert "refresh.controller.signal" in library
    assert "state.modal !== operation.overlay" in library
    assert "libraryModalIdentity.get(operation.overlay) !== operation.modalIdentity" in library
    assert "libraryModalSequence !== closedSequence || state.modal" in library
    assert "state.modal !== overlay" in library
    assert "[data-crump57-object-url]" in library
    assert "URL.revokeObjectURL(previousUrl)" in library


def test_library_async_flows_use_scoped_nodes_signals_and_currentness_checks():
    library = read("public/crump-library-5.7.js")

    for surface in ("reader", "preview", "import", "editor-save", "trash", "restore", "permanent-delete"):
        assert f"beginLibraryOperation('{surface}'" in library

    for refresh in ("books", "deleted-books", "projects"):
        assert f"beginLibraryRefresh('{refresh}'" in library

    assert "async function uploadLibraryFile(file, operation)" in library
    assert "signal: operation.controller.signal" in library
    assert "shouldProceed: () => activeLibraryOperation(operation)" in library
    assert "overlay.querySelector('#crump57ReaderLoading')" in library
    assert "overlay.querySelector('#crump57PreviewOpen')" in library
    assert "overlay.querySelector('#crump57ImportForm')" in library
    assert "overlay.querySelector('#crump57BookForm')" in library
    assert "closeModal({overlay})" in library
    assert "if (error?.name === 'AbortError' || !activeLibraryOperation(operation)) return;" in library


def test_composer_upload_honors_library_caller_abort_and_guard_without_breaking_default_callers():
    composer = read("public/crump-5.0.js")

    assert "upload: async (file, options = {}) =>" in composer
    assert "const callerSignal = options?.signal || null;" in composer
    assert "const callerShouldProceed = typeof options?.shouldProceed === 'function'" in composer
    assert "callerSignal?.addEventListener?.('abort'" in composer
    assert "callerSignal?.removeEventListener?.('abort'" in composer
    assert "item.callerShouldProceed = callerMayProceed;" in composer
    assert "if (!callerMayProceed()) throw composerBoundaryAbortError();" in composer
    assert "upload: async file =>" not in composer


def test_crud_privacy_browser_fixture_is_non_vacuous_and_registered():
    fixture = read("tests/fixtures/library-crud-privacy.html")
    upload_fixture = read("tests/fixtures/image-upload-preview-stability.html")
    verifier = read("scripts/verify-library-crud-privacy.cjs")
    matrix = read("scripts/verify-browser-control-matrix.mjs")
    package = json.loads(read("package.json"))

    for marker in (
        "fixturePlan",
        "fixturePlanUpload",
        "fixtureResolveUpload",
        "fixtureSwitchAccount",
        "fixtureRequestEvidence",
        "fixtureUploadEvidence",
        "overlayRemovals",
        "<script src=\"/public/crump-library-5.7.js",
    ):
        assert marker in fixture

    for assertion in (
        "mutated a post-switch overlay",
        "stale Preview A mutated Preview B",
        "A-initiated import modal mounted after A→B",
        "Import A posted hybrid metadata from Import B",
        "Editor A PATCHed after its upload outlived the modal",
        "superseded books request was not aborted",
        "superseded deleted-books request was not aborted",
        "superseded Project request was not aborted",
        "same-account delete error did not permit retry",
    ):
        assert assertion in verifier

    for key in (
        "reader:book-a",
        "signed:front-cover-book-a",
        "projects",
        "import",
        "edit:book-a",
        "trash:book-a",
        "restore:deleted-a",
        "delete:deleted-a",
        "books",
        "deleted",
    ):
        assert key in verifier

    assert "assertFencedRequest" in verifier
    assert "hasSignal: true" in verifier
    assert "aborted: true" in verifier
    assert "mayProceed: false" in verifier
    for marker in (
        "fixtureResetDirectUploadEvidence",
        "fixtureDirectUploadEvidence",
        "__directUploadRequests",
        "__directUploadRevocations",
        "__xhrSends",
    ):
        assert marker in upload_fixture
    for assertion in (
        "pre-aborted real upload unexpectedly resolved",
        "guard-false real upload unexpectedly resolved",
        "caller abort did not reach the real upload XHR",
        "cancelled real upload did not revoke its preview blob",
        "successful real upload did not revoke its preview blob",
    ):
        assert assertion in verifier
    assert "image-upload-preview-stability.html" in verifier
    assert "window.CrumpFileTools.upload" in verifier
    assert "directUploadWrapper" in verifier
    assert "'verify-library-crud-privacy.cjs'" in matrix
    assert package["scripts"]["test:library-crud-privacy"] == "node scripts/verify-library-crud-privacy.cjs"
    assert "npm run test:library-crud-privacy" in package["scripts"]["test"]
