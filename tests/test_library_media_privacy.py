from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_media_delivery_is_single_owner_fenced_and_abortable():
    media = read("public/crump-media-save.js")

    assert "const activeOperations = new Set();" in media
    assert "function beginOperation(file, {signal = null, shouldProceed = null} = {})" in media
    assert "if (!String(file?.id || '').trim()) return false;" in media
    assert "activeOperations.add(operation);" in media
    assert "finishOperation(operation);" in media
    assert "operation.userId !== currentAuthenticatedUserId()" in media
    assert "operation.fileId !== String(operation.file?.id || '').trim()" in media
    assert "signal: operation.controller.signal" in media
    assert "credentials: 'omit'" in media
    assert "if (!deliveryMayProceed(operation)) throw abortError();" in media
    assert "if (deliveryOptions.fallback === true) return fallbackDownload(operation);" in media
    assert "operation.controller.abort();\n      finishOperation(operation);" in media
    assert "shouldProceed: () => link.isConnected && mediaFileFromHref(link.href)?.id === file.id" in media
    assert "window.location.assign" not in media
    assert "register?.('media-save', abort)" in media
    assert "Object.freeze({saveMedia, relabelMediaActions, abort})" in media


def test_library_delegates_media_and_fences_original_source_delivery():
    library = read("public/crump-library-5.7.js")

    assert "function saveNativeMedia" not in library
    assert "function shareMediaFile" not in library
    assert "function androidAlbum" not in library
    assert "const deliver = window.CrumpMediaSave?.saveMedia;" in library
    assert "return deliver(file, deliveryOptions);" in library
    assert "const libraryFileDeliveryControllers = new Set();" in library
    assert "function openOriginalSource(book)" in library
    assert "{...book.sourceFile, id: sourceFileId, url: ''}" in library
    assert "{signal: controller.signal, shouldProceed}" in library
    assert "window.CrumpMediaSave?.abort?.();" in library
    assert "libraryFileDeliveryControllers.forEach(controller => controller.abort());" in library


def test_composer_preserves_guards_and_never_falls_through_after_auth_abort():
    composer = read("public/crump-5.0.js")

    assert "window.CrumpMediaSave?.abort?.();" in composer
    assert "window.CrumpMediaSave.saveMedia(file, deliveryOptions)" in composer
    assert "if (error?.name === 'AbortError' || !fileDeliveryMayProceed(deliveryOptions)) return false;" in composer
    assert "using the canonical file delivery fallback" in composer
    assert "open: (file, download = false, options = {}) => openFile(file, download, options)" in composer
    assert composer.index("if (handled) return true;") < composer.index("url = await resolvedFileUrl(file, {download: true, ...deliveryOptions});")


def test_privacy_browser_fixture_is_non_vacuous_and_registered():
    fixture = read("tests/fixtures/library-media-privacy.html")
    verifier = read("scripts/verify-library-media-privacy.cjs")
    matrix = read("scripts/verify-browser-control-matrix.mjs")
    package = read("package.json")

    for marker in (
        "fixtureDeferredSigns",
        "fixtureDeferredBlobs",
        "fixtureDeferredNativeSaves",
        "fixtureDeferredSources",
        "fixtureSwitchAccount",
        "fixtureResolveSign",
        "fixtureResolveBlob",
    ):
        assert marker in fixture
    for assertion in (
        "account A signed URL reached the Photos plugin after A→B",
        "same-account native image save did not reach Photos",
        "account A blob reached navigator.share after A→B",
        "direct video navigation fell back after A→B",
        "detached direct-video action triggered a stale fallback",
        "ordinary Files delivery must keep canonical fallback ownership",
        "URL-only media must not enter ID-based signing",
        "account A original source opened after A→B",
        "account A original-source delivery emitted a stale status after A→B",
    ):
        assert assertion in verifier
    assert "assert.equal(result.blobRequests[0].credentials, 'omit')" in verifier
    assert "url: handoff.file.url" in verifier
    assert "'verify-library-media-privacy.cjs'" in matrix
    assert '"test:library-media-privacy": "node scripts/verify-library-media-privacy.cjs"' in package


def test_changed_assets_are_versioned_across_web_pwa_and_native():
    token = "5.9.76-library-media-privacy-1"
    cache_name = "ask-crump-new-body-v1-r266-library-media-privacy-1"
    shell = read("public/app.html")
    runtime = read("public/runtime-body-v1.js")
    runtime_config = read("public/runtime-config.js")
    runtime_config_v1 = read("public/runtime-config-v1.js")
    worker = read("public/sw.js")
    native = read("scripts/build-native.mjs")
    checker = read("scripts/check-javascript.mjs")
    library_loader = read("public/crump-library-loader.js")

    assert f"/runtime-body-v1.js?v={token}" in shell
    for source in (runtime, worker, native):
        assert f"/crump-5.0.js?v={token}" in source
        assert f"/crump-media-save.js?v={token}" in source
        assert f"/crump-library-loader.js?v={token}" in source
    for source in (runtime_config, runtime_config_v1):
        assert f"/crump-5.0.js?v={token}" in source
    assert f"/crump-library-5.7.js?v={token}" in library_loader
    assert f"/runtime-body-v1.js?v={token}" in worker
    assert cache_name in worker
    assert cache_name in checker
