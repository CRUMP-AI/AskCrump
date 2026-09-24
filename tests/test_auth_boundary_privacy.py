from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def between(source: str, start: str, end: str) -> str:
    return source[source.index(start):source.index(end, source.index(start))]


def test_private_ui_uses_one_idempotent_auth_boundary_for_logout_and_user_changes() -> None:
    app = read("public/app.js")
    composer = read("public/crump-5.0.js")
    product = read("public/crump-product-5.3.js")

    assert "window.CrumpAuthBoundary = Object.freeze" in app
    assert "window.addEventListener('crump:authentication-required', handleAuthenticationRequired)" in app
    assert "window.addEventListener('crump:authenticated-ready', handleAuthenticatedReady)" in app
    assert "Object.defineProperty(window, 'currentUser'" in app
    assert "set: assignCurrentUser" in app
    assert "if (event.key !== USER_CACHE_KEY) return" in app
    assert "window.location.reload()" in app
    assert "ownerUserId && ownerUserId !== nextUserId" in app
    assert "runScrubbers('authenticated-user-changed', nextUserId)" in app
    assert "window.CrumpAuthBoundary?.register?.('main-composer', scrubComposerAuthBoundary)" in composer
    assert "window.CrumpAuthBoundary.register('product-studio', clearProductAuthState)" in product


def test_project_target_state_and_storage_are_account_bound_at_auth_transitions() -> None:
    product = read("public/crump-product-5.3.js")
    scrub = between(
        product,
        "  function resetProjectAuthMemory()",
        "  function clearVideoReferenceAuthState()",
    )
    browser = read("scripts/verify-project-chat-context-boundary.cjs")
    fixture = read("tests/fixtures/project-chat-context-boundary.html")

    assert "ACTIVE_PROJECT_STORAGE_KEY = 'askcrump.activeProject53'" in product
    assert "function projectStorageKey(" in product
    assert "encodeURIComponent(normalized)" in product
    assert "function claimLegacyStoredProject()" in product
    assert "localStorage.removeItem(ACTIVE_PROJECT_STORAGE_KEY)" in product
    assert "const projectTarget = currentProjectTarget() || await restoreStoredProjectTarget();" in product
    assert "projectId: projectTarget?.id || null" in product
    for contract in (
        "projectAuthSequence += 1",
        "state.projects = []",
        "state.activeProject = null",
        "state.chatProject = null",
        "state.rememberedProjectTarget = null",
        "state.projectConversations = []",
        "state.libraryFiles = []",
        "conversationProjectCache.clear()",
        "conversationProjectRequests.clear()",
        "storedProjectTargetPromise = null",
        "storedProjectTargetId = ''",
        "renderVideoProjectDestination()",
    ):
        assert contract in scrub
    for contract in (
        "verifyAccountBoundary",
        "fixtureAuthenticationRequired",
        "unselectedRequest.projectId",
        "accountAStored",
        "accountBStored",
        "sameAccountReload",
    ):
        assert contract in browser
    assert "window.fixtureAuthenticationRequired" in fixture
    assert "window.fixtureLogin" in fixture
    assert "fixtureProjectB" in fixture


def test_composer_scrub_releases_private_drafts_masks_previews_and_inflight_uploads() -> None:
    composer = read("public/crump-5.0.js")
    scrub = between(composer, "  function scrubComposerAuthBoundary()", "  function renderToolChip()")
    add_files = between(composer, "  async function addFiles", "  async function uploadItem")
    upload = between(composer, "  async function uploadItem", "  function uploadSigned")

    for contract in (
        "composerAuthSequence += 1",
        "item?.authController?.abort?.()",
        "item?.controller?.abort?.()",
        "revokeAttachmentPreview(item)",
        "state.attachments = []",
        "state.precisionImageEdit = null",
        "state.imageRecovery = null",
        "input.value = ''",
        "fileInput.value = ''",
        "window.CrumpPrecisionImageEditor?.close?.()",
        "state.lightbox?.remove()",
    ):
        assert contract in scrub
    assert "const authSequence = composerAuthSequence" in add_files
    assert "if (authSequence !== composerAuthSequence) return" in add_files
    assert "signal: item.authController.signal" in upload
    assert "assertComposerUploadCurrent(item, authSequence)" in upload


def test_video_job_and_request_storage_is_owner_scoped_and_content_free() -> None:
    product = read("public/crump-product-5.3.js")
    loader = read("public/crump-product-loader.js")
    request_store = between(product, "  function storeVideoRequest", "  function videoReferenceDraftStorage")
    request_read = between(product, "  function readStoredVideoRequest", "  function storeVideoRequest")
    job_store = between(product, "  function storeVideoJob", "  function readStoredVideoRequest")

    assert "`${baseKey}:${encodeURIComponent(normalized)}`" in product
    assert "String(value?.userId || '') !== normalizedUserId" in product
    assert "String(legacyValue?.userId || '') === normalizedUserId" in product
    assert "version: VIDEO_STORAGE_VERSION" in job_store
    assert "userId: normalizedUserId" in job_store
    assert "requestDigest" in request_store and "requestDigest" in request_read
    assert "prompt" not in request_store
    assert "referenceFileIds" not in request_store
    assert "referencePlan" not in request_store
    assert "fingerprint" not in product
    assert "crypto.subtle.digest('SHA-256', bytes)" in product
    assert "hasStoredVideoRecord(VIDEO_JOB_KEY, 'job')" in loader
    assert "hasStoredVideoRecord(VIDEO_REQUEST_KEY, 'request')" in loader
    assert "String(value?.userId || '') !== userId" in loader
    assert "localStorage.setItem(accountKey, JSON.stringify(sanitized))" in loader


def test_video_async_work_and_resume_remain_bound_to_the_starting_owner() -> None:
    product = read("public/crump-product-5.3.js")
    start = between(product, "  async function startVideo", "  async function retryVideoProjectAttachment")
    poll = between(product, "  function pollVideo", "  function resumePendingVideoJob")
    scrub = between(product, "  function resetVideoReferenceMemory", "  function clearVideoReferenceAuthState")

    assert "const ownerUserId = currentVideoReferenceUserId()" in start
    assert "const authSequence = videoReferenceAuthSequence" in start
    assert "signal: startController.signal" in start
    assert "storeVideoRequest(null, ownerUserId)" in start
    assert "storeVideoJob(data.job.id, ownerUserId)" in start
    assert "currentVideoReferenceUserId() !== ownerUserId" in start
    assert "currentVideoReferenceUserId() !== normalizedOwnerUserId" in poll
    assert "storeVideoJob('', normalizedOwnerUserId)" in poll
    assert "ignoreLegacyVideoJob(jobId, normalizedOwnerUserId)" in poll
    assert "VIDEO_REQUEST_RECOVERY_GRACE_MS = 5 * 60 * 1000" in product
    assert "same request key" in product
    assert "state.videoStartAbortController?.abort?.()" in scrub
    assert "state.videoContinuationAbortController?.abort?.()" in scrub
    assert "prompt.value = ''" in scrub
    assert "referenceInput.value = ''" in scrub
    assert "byId('crump53VideoResult')?.replaceChildren()" in scrub


def test_lazy_project_reference_queue_and_file_list_are_account_fenced() -> None:
    detail = read("public/crump-product-5.3.1.js")
    loader = read("public/crump-product-loader.js")
    attach = between(detail, "  async function attachQueuedAfterSave", "  function projectFileGroup")
    refresh = between(detail, "  async function refreshProjectFiles", "  function hideProjectFiles")
    scrub = between(detail, "  function scrubProductDetailAuthBoundary", "  function handleProductDetailAuthenticated")

    assert "window.CrumpAuthBoundary.register('product-studio-detail', scrubProductDetailAuthBoundary)" in detail
    assert "productDetailOperationIsCurrent(operation)" in attach
    assert "state.queue.some(item => item.ownerUserId !== operation.userId)" in attach
    assert "state.projectReferenceAbortController" in attach
    assert "signal: controller.signal" in refresh
    assert "productDetailOperationIsCurrent(operation)" in refresh
    for contract in (
        "productDetailAuthSequence += 1",
        "state.projectReferenceAbortController?.abort?.()",
        "state.projectFilesAbortController?.abort?.()",
        "state.queue = []",
        "input.value = ''",
        "hideProjectFiles()",
        "state.renameSheet?.remove()",
    ):
        assert contract in scrub
    assert "`${ACTIVE_PROJECT_KEY}:${encodeURIComponent(userId)}`" in loader
    cached = between(loader, "  function cachedProjectTarget()", "  facade = Object.freeze")
    assert "stored(ACTIVE_PROJECT_KEY)" not in cached


def test_retry_paths_and_continuations_cannot_cross_the_auth_boundary() -> None:
    composer = read("public/crump-5.0.js")
    product = read("public/crump-product-5.3.js")
    retry_message = between(composer, "  async function retryMessage", "  function reviseImageMessage")
    project_retry = between(
        product,
        "  async function retryVideoProjectAttachment",
        "  function renderReadyVideo",
    )
    continuation = between(product, "  async function continueVideoScene", "  function pollVideo")
    scrub = between(product, "  function resetVideoReferenceMemory", "  function clearVideoReferenceAuthState")

    assert "const authSequence = composerAuthSequence" in retry_message
    assert "if (!retryIsCurrent()) return" in retry_message
    assert "chat = retryChat()" in retry_message
    assert "const ownerUserId = currentVideoReferenceUserId()" in project_retry
    assert "signal: retryController.signal" in project_retry
    assert "currentVideoReferenceUserId() !== ownerUserId" in project_retry
    assert "state.videoProjectRetryAbortController?.abort?.()" in scrub
    assert "operationType: 'extend'" in continuation
    assert "const requestDigest = await videoRequestDigest(continuationRequest)" in continuation
    assert "storeVideoRequest({idempotencyKey, requestDigest" in continuation
    assert "storeVideoRequest(null, ownerUserId)" in continuation


def test_executable_browser_specs_cover_account_boundaries_and_owner_resume() -> None:
    video = read("scripts/verify-video-reference-browser.cjs")
    composer = read("scripts/verify-visual-media-browser.cjs")
    product_detail = read("scripts/verify-product-studio-detail-auth-boundary.cjs")
    browser_matrix = read("scripts/verify-browser-control-matrix.mjs")
    video_fixture = read("tests/fixtures/video-reference-upload.html")
    composer_fixture = read("tests/fixtures/image-upload-preview-stability.html")
    product_detail_fixture = read(
        "tests/fixtures/product-studio-detail-auth-boundary.html"
    )

    for contract in (
        "pendingRequestBeforeReload",
        "sameAccountJobResume",
        "crossAccountJobIsolation",
        "accountBJobResume",
        "inFlightAccountSwitch",
        "requestDigest",
        "recoveryLookups",
        "delayedRecovery",
        "legacyWrongAccountResume",
        "wrongAccountCanCreate",
        "rightfulAccountRecovered",
    ):
        assert contract in video
    for contract in (
        "sameAccountReady",
        "logoutToDifferentAccount",
        "directUserChange",
        "uploadAborts",
        "revokedBlobs",
        "crossTabIdentityChange",
    ):
        assert contract in composer
    for contract in (
        "queuedBeforeBoundary",
        "switchedToB",
        "lateAccountACompletion",
        "accountBRendered",
        "fixtureResolveProjectFiles",
        "fixtureResolveUpload",
        "signalAborted",
        "attachRequests",
    ):
        assert contract in product_detail
    assert "/public/app.js?v=auth-boundary-fixture-1" in video_fixture
    assert "/public/app.js?v=auth-boundary-fixture-1" in composer_fixture
    assert "/public/crump-product-5.3.1.js" in product_detail_fixture
    assert "window.CrumpAuthBoundary" in product_detail_fixture
    assert "window.fixtureProjectFileRequests" in product_detail_fixture
    assert "window.fixtureUploads" in product_detail_fixture
    assert "verify-product-studio-detail-auth-boundary.cjs" in browser_matrix
