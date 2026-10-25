from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def runtime_source(source: str) -> str:
    start = source.index("  function manuscriptExportDeliveryRuntime()")
    end = source.index("\n  const manuscriptExportDelivery = manuscriptExportDeliveryRuntime();", start)
    return source[start:end]


def function_source(source: str, name: str) -> str:
    match = re.search(rf"^  (?:async )?function {re.escape(name)}\([^\n]*", source, re.MULTILINE)
    assert match, name
    next_match = re.search(r"^  (?:async )?function [A-Za-z0-9_]+\(", source[match.end():], re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(source)
    return source[match.start():end]


def test_project_and_library_share_one_content_free_delivery_runtime_contract():
    product = read("public/crump-product-5.3.js")
    library = read("public/crump-library-5.7.js")
    runtime = runtime_source(product)

    assert runtime == runtime_source(library)
    assert "const runKey = '__crumpManuscriptExportRun'" in runtime
    assert "const sequenceKey = '__crumpManuscriptExportRunSequence'" in runtime
    assert "const cleanupByRun = new WeakMap()" in runtime
    assert "token," in runtime
    assert "controller: new AbortController()" in runtime
    assert "userId: normalizedUserId" in runtime
    assert "surface: normalizedSurface" in runtime
    assert "attachCleanup(run, cleanup)" in runtime
    assert "if (complete) return" in runtime
    assert "run.controller.abort()" in runtime
    assert "cleanupByRun.get(run)?.()" in runtime

    # A canonical handoff gets only the private file identity. Web/PWA may
    # recover through the same-origin owner-checked endpoint; native fails shut.
    assert "const fileId = String(file?.id || '').trim()" in runtime
    assert "if (!fileId)" in runtime
    assert "const canonicalFile = {...file, id: fileId, url: ''}" in runtime
    assert "canonicalOpen(canonicalFile, true, {" in runtime
    assert "signal: run.controller.signal" in runtime
    assert "async deliver(file, run, shouldProceed = () => true)" in runtime
    assert "const canProceed = () => this.isCurrent(run, run?.userId) && shouldProceed() !== false" in runtime
    assert "shouldProceed: canProceed" in runtime
    assert "if (opened === true) return true" in runtime
    assert "`/api/files/${encodeURIComponent(fileId)}/content?download=1`" in runtime
    assert "if (window.CrumpAPI?.isNative)" in runtime
    assert "Retry from Files" in runtime
    assert "window.location.assign" not in runtime
    assert "window.open" not in runtime
    assert "file.url" not in runtime


def test_both_export_surfaces_use_shared_guard_auth_fences_and_exact_control_restore():
    for relative, surface, export_name, context_guard in (
        ("public/crump-product-5.3.js", "project", "exportManuscript", "projectOperationIsCurrent"),
        ("public/crump-library-5.7.js", "library", "exportCurrentManuscript", "libraryOperationIsCurrent"),
    ):
        source = read(relative)
        start = source.index("  const MANUSCRIPT_EXPORT_FORMATS")
        end = source.index("\n  function ", source.index(f"  async function {export_name}", start) + 20)
        export = source[start:end]

        assert "new Set(['docx', 'pdf', 'epub'])" in export
        assert "[data-crump53-export], [data-crump53-run-output], [data-crump57-export-format]" in export
        assert "label: button.innerHTML" in export
        assert "ariaBusy: button.getAttribute('aria-busy')" in export
        assert "button.innerHTML = label" in export
        assert "button.setAttribute('aria-busy', ariaBusy)" in export
        assert f"manuscriptExportDelivery.begin('{surface}', operation.userId)" in export
        assert "manuscriptExportDelivery.attachCleanup" in export
        assert "signal: run.controller.signal" in export
        assert "manuscriptExportDelivery.isCurrent(run, operation.userId)" in export
        assert context_guard in export
        assert "await manuscriptExportDelivery.deliver(data.file, run, resourceIsCurrent)" in export
        assert "resourceIsCurrent" in export
        assert "error?.name === 'AbortError'" in export
        assert "manuscriptExportDelivery.finish(run)" in export

    product = read("public/crump-product-5.3.js")
    library = read("public/crump-library-5.7.js")
    assert "manuscriptExportDelivery.abort()" in product[product.index("  function resetProjectAuthMemory"):]
    reset = library[library.index("  function resetLibraryAuthMemory"):]
    assert "libraryAuthSequence += 1" in reset
    assert "manuscriptExportDelivery.abort()" in reset
    assert "state.books = []" in reset
    assert "closeModal({restoreFocus: false, overlay: state.modal})" in reset
    assert "grid.replaceChildren()" in reset


def test_canonical_file_tool_handoff_carries_abort_and_owner_guard_to_the_final_click():
    composer = read("public/crump-5.0.js")

    assert "function fileDeliveryMayProceed({signal = null, shouldProceed = null} = {})" in composer
    assert "if (signal?.aborted) return false" in composer
    assert "return shouldProceed() === true" in composer
    assert "async function resolvedFileUrl(file, {download = false, signal = null, shouldProceed = null} = {})" in composer
    assert "signal: signal || undefined" in composer
    assert "if (!fileDeliveryMayProceed(deliveryOptions)) return ''" in composer
    assert "async function openFile(file, download = false, deliveryOptions = {})" in composer
    assert "if (!url || !fileDeliveryMayProceed(deliveryOptions)) return false" in composer
    assert "if (!fileDeliveryMayProceed(deliveryOptions)) {" in composer
    assert "link.click(); link.remove()" in composer
    assert "open: (file, download = false, options = {}) => openFile(file, download, options)" in composer


def test_real_dual_surface_fixture_covers_delivery_failures_races_and_account_switches():
    fixture = read("tests/fixtures/manuscript-export-delivery.html")
    verifier = read("scripts/verify-manuscript-export-delivery.cjs")
    package = read("package.json")

    assert "/public/crump-product-5.3.js?v=manuscript-export-delivery-fixture-2" in fixture
    assert "/public/crump-library-5.7.js?v=manuscript-export-delivery-fixture-2" in fixture
    for evidence in (
        "window.fixtureExportRequests",
        "window.fixtureFileHandoffs",
        "window.fixtureFallbackDownloads",
        "window.fixtureSwitchAccount",
        "window.fixtureResolveDeferredExport",
        "window.fixtureResolveDeferredCanonical",
        "window.fixtureSetManuscriptRunOutput",
    ):
        assert evidence in fixture

    for surface in ("project", "library"):
        for format_name in ("docx", "pdf", "epub"):
            assert format_name in verifier
    for marker in (
        "results.failures.push(`${surface}:url-only`)",
        "results.failures.push(`${surface}:native-fail-closed`)",
        "results.failures.push(`${surface}:${mode}`)",
    ):
        assert marker in verifier

    for marker in (
        "project:false",
        "library:absent",
        "project-to-library",
        "library-to-project",
        "project:late-api",
        "library:late-api",
        "project:late-canonical",
        "project:saved-output-id",
        "project:saved-output-url-only",
        "project:saved-output-native-fail-closed",
        "project:saved-output-late-canonical",
        "project:late-canonical",
        "library:closed-modal",
        "project:saved-output-late-canonical",
    ):
        assert marker in verifier
    assert "['controller', 'surface', 'token', 'userId']" in verifier
    assert "assert.deepEqual(restored.map" in verifier
    assert "assert.deepEqual(browserErrors, [])" in verifier
    assert "assert.deepEqual(popupUrls, [])" in verifier
    assert '"test:manuscript-export-delivery"' in package
    assert "npm run test:manuscript-export-delivery" in package


def test_saved_full_draft_output_is_id_only_and_uses_the_shared_delivery_guard():
    product = read("public/crump-product-5.3.js")
    render_start = product.index("  function renderManuscriptRun()")
    render_end = product.index("\n  function scheduleManuscriptPoll()", render_start)
    run_delivery = product[render_start:render_end]

    assert "const outputFileId = String(run.outputFile?.id || '').trim()" in run_delivery
    assert "data-crump53-run-output" in run_delivery
    assert "href=\"${escapeHtml(run.outputFile.url)}" not in run_delivery
    assert "outputFile?.url" not in run_delivery
    assert "Delivery could not be verified. Check Files before trying again." in run_delivery
    assert "manuscriptExportDelivery.begin('project-run-output', operation.userId)" in run_delivery
    assert "await manuscriptExportDelivery.deliver(file, run, resourceIsCurrent)" in run_delivery
    assert "manuscriptExportDelivery.isCurrent(run, operation.userId)" in run_delivery
    assert "projectOperationIsCurrent(operation)" in run_delivery
    assert "String(state.manuscriptRun?.outputFile?.id || '').trim()" in run_delivery
    assert "String(state.activeManuscript?.id || '').trim() === manuscriptId" in run_delivery


def test_all_private_manuscript_async_mutators_share_abortable_auth_and_identity_fences():
    product = read("public/crump-product-5.3.js")

    assert "manuscriptOperations: new Map()" in product
    assert "function beginManuscriptOperation(key" in product
    assert "controller: new AbortController()" in function_source(product, "beginManuscriptOperation")
    assert "projectOperationIsCurrent(context)" in function_source(product, "manuscriptOperationIsCurrent")
    assert "context.projectId === String(state.activeProject?.id || '').trim()" in function_source(product, "manuscriptOperationIsCurrent")
    assert "context.manuscriptId === String(state.activeManuscript?.id || '').trim()" in function_source(product, "manuscriptOperationIsCurrent")
    assert "context.sectionId === String(state.activeSection?.id || '').trim()" in function_source(product, "manuscriptOperationIsCurrent")
    assert "abortManuscriptOperations()" in function_source(product, "resetProjectAuthMemory")

    guarded = {
        "refreshManuscripts": "'list'",
        "createManuscript": "'create'",
        "loadManuscript": "'load'",
        "retryManuscriptOutputLookup": "'retry-output'",
        "pollManuscriptRun": "'poll'",
        "startFullManuscript": "'start-run'",
        "controlManuscriptRun": "'control-run'",
        "planManuscript": "'plan'",
        "addChapter": "'add-section'",
        "saveSection": "'save-section'",
        "draftSection": "'draft-section'",
        "draftNextSection": "'draft-next'",
    }
    for name, key in guarded.items():
        body = function_source(product, name)
        assert f"beginManuscriptOperation({key}" in body, name
        assert "signal: operation.controller.signal" in body, name
        assert "manuscriptOperationIsCurrent(operation" in body, name
        assert "finishManuscriptOperation(operation)" in body, name

    replace = function_source(product, "replaceSection")
    assert "operation && !manuscriptOperationIsCurrent(operation)" in replace
    workspace = function_source(product, "openManuscriptWorkspace")
    assert workspace.count("projectOperationIsCurrent(operation)") >= 3


def test_library_cover_signing_cannot_repopulate_account_a_cache_after_auth_switch():
    library = read("public/crump-library-5.7.js")
    cover = function_source(library, "coverUrl")
    reset = function_source(library, "resetLibraryAuthMemory")

    assert "coverSignControllers: new Map()" in library
    assert "const operation = libraryOperationContext()" in cover
    assert "const controller = new AbortController()" in cover
    assert "signedLibraryFile(file, {signal: controller.signal})" in cover
    assert "state.coverSignControllers.get(file.id) !== controller" in cover
    assert "!libraryOperationIsCurrent(operation)" in cover
    assert "state.coverUrls.set(file.id" in cover
    assert "state.coverSignControllers.forEach(controller => controller.abort())" in reset
    assert "state.coverSignControllers.clear()" in reset
    assert reset.index("state.coverSignControllers.clear()") < reset.index("state.coverUrls.clear()")

    verifier = read("scripts/verify-manuscript-export-delivery.cjs")
    for marker in (
        "project:late-list",
        "project:late-load",
        "project:late-poll",
        "project:late-draft",
        "library:late-cover-sign",
    ):
        assert marker in verifier


def test_manuscript_export_runtime_is_cache_busted_through_both_lazy_loaders():
    product_loader = read("public/crump-product-loader.js")
    library_loader = read("public/crump-library-loader.js")
    runtime = read("public/runtime-body-v1.js")
    native = read("scripts/build-native.mjs")
    worker = read("public/sw.js")

    assert "/crump-product-5.3.js?v=5.9.76-legacy-project-resume-truth-1" in product_loader
    assert "/crump-library-5.7.js?v=5.9.76-account-owner-boundary-1" in library_loader
    for shell in (runtime, native, worker):
        assert "/crump-product-loader.js?v=5.9.76-legacy-project-resume-truth-1" in shell
        assert "/crump-library-loader.js?v=5.9.76-account-owner-boundary-1" in shell
