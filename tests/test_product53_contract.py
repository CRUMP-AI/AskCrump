from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_product53_runtime_is_registered_last_and_cached():
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")
    assert "/crump-product-5.3.css" in runtime
    assert "/crump-product-5.3.js" in runtime
    assert runtime.index("/crump-navigation-5.2.5.js") < runtime.index("/crump-product-5.3.js")
    assert "ask-crump-new-body-v1-r105" in worker
    assert "/crump-product-5.3.js" in worker
    assert "crump-product-5.3.js" in checker


def test_mobile_polish_matches_approved_scope():
    css = read("public/crump-product-5.3.css")
    assert "#scrollToEndBtn" in css
    assert "left: 50% !important" in css
    assert "right: auto !important" in css
    assert "translateX(-50%)" in css
    assert "padding-bottom: 0 !important" in css
    assert "env(safe-area-inset-bottom) - 24px" in css


def test_projects_media_manuscripts_and_cost_controls_are_registered():
    application = read("backend/application.py")
    runtime = read("backend/runtime.py")
    chat = read("backend/routes/chat.py")
    config = read("backend/config.py")
    for route in ("projects", "features", "media", "manuscripts"):
        assert f"application.include_router({route}.router)" in application
    assert "FeatureService" in runtime
    assert "ProjectService" in runtime
    assert "VideoService" in runtime
    assert "ManuscriptService" in runtime
    assert "consume_feature_for_request" in chat
    assert "apply_project_context" in chat
    assert "GEMINI_API_KEY" in read(".env.example")
    assert "video_generation_enabled" in config


def test_product_expansion_schema_is_private_and_complete():
    migration = read("migrations/009_product_expansion.sql")
    for table in (
        "projects",
        "project_chats",
        "project_files",
        "project_context",
        "manuscripts",
        "manuscript_sections",
        "media_jobs",
    ):
        assert f"public.{table}" in migration
        assert f"alter table public.{table} enable row level security" in migration
        assert f"revoke all on table public.{table} from anon, authenticated" in migration
    assert "generated_video" in migration
    assert "manuscript_export" in migration
    assert "application/epub+zip" in migration


def test_internal_entitlement_schema_is_billing_independent_and_generic():
    migration = read("migrations/012_internal_entitlements.sql")
    assert "internal_tier" in migration
    assert "professional" in migration and "enterprise" in migration
    assert "@" not in migration


def test_video_retry_does_not_bill_twice():
    route = read("backend/routes/media.py")
    existing_lookup = route.index('existing = await _existing_job(')
    consume = route.index("receipt = await features.consume(")
    assert existing_lookup < consume
    assert "idempotentReplay" in route
    video = read("backend/video_service.py")
    providers = read("backend/video_providers.py")
    assert "duration = 8" in video
    # Veo 3.1 Fast continuation is single-output by definition and rejects
    # numberOfVideos. Keep the provider-specific continuation contract explicit.
    assert 'if video_reference:' in providers
    assert 'instance["video"] = {"uri": video_reference}' in providers
    assert 'parameters["numberOfVideos"] = 1' not in providers
    assert 'parameters["resolution"] = "720p"' in providers
    assert 'parameters["durationSeconds"] = 8' in providers
    assert "async def _mark_failed" in video
    assert "could not save the file" in video


def test_private_account_library_surfaces_saved_creations():
    routes = read("backend/routes/files.py")
    service = read("backend/file_service.py")
    product = read("public/crump-product-5.3.js")
    styles = read("public/crump-product-5.3.css")
    assert "@router.get('')" in routes
    assert "'deleted_at': 'is.null'" in routes
    assert "order='created_at.desc'" in routes
    assert "'createdAt': row.get('created_at')" in service
    assert 'data-crump53-panel="library"' in product
    assert "api('/api/files?limit=200')" in product
    assert "Saved to Library" in product
    assert "openStudio('library')" in product
    assert ".crump53-library-grid" in styles
    assert "const opened = await loadManuscript(manuscriptId)" in product
    assert "target.scrollIntoView" in product
    assert "'Opened ' + (workspace?.title || 'manuscript') + '.'" in product


def test_library_is_one_dedicated_destination_instead_of_a_workspace_tab():
    product = read("public/crump-product-5.3.js")
    library = read("public/crump-library-5.7.js")
    navigation = read("public/crump-navigation-5.9.30.js")
    styles = read("public/crump-product-5.3.css")

    assert 'id="crump53Sheet"' in product
    assert 'id="crump53WorkspaceTabs"' not in product
    assert 'data-crump53-tab=' not in product
    assert "const STUDIO_SECTION_META = Object.freeze" in product
    assert "projects: {kicker: 'WORKSPACE', title: 'Projects', label: 'Ask Crump Projects'}" in product
    assert "library: {kicker: 'PRIVATE LIBRARY', title: 'Library', label: 'Ask Crump Library'}" in product
    assert "filesPill.addEventListener" not in product
    assert "file: {label: 'Files', description: 'Attach a reference file'}" in product
    assert "Open your private Library" not in product
    assert "openStudio('library')" in product
    assert "const libraryPanel = document.querySelector('[data-crump53-panel=\"library\"]')" in library
    assert "libraryPanel.insertBefore(card, libraryPanel.firstElementChild)" in library
    assert "manuscriptTab.textContent = 'Library'" not in library
    assert "section === 'library'" in navigation
    assert '.crump53-tabs' not in styles

    fixture = read("tests/fixtures/dedicated-library-destination.html")
    assert "/public/crump-product-5.3.js?fixture=dedicated-library" in fixture
    assert "/public/crump-library-5.7.js?fixture=dedicated-library" in fixture
    assert "/public/crump-navigation-5.9.30.js?fixture=dedicated-library" in fixture
    assert 'data-v1-command="file"' in fixture
    assert ".v1-rail { position: relative;" in fixture


def test_projects_manuscripts_and_video_are_isolated_destinations():
    product = read("public/crump-product-5.3.js")
    navigation = read("public/crump-navigation-5.9.30.js")
    polish = read("public/crump-polish-5.6.js")

    assert "manuscripts: {kicker: 'LONG-FORM', title: 'Manuscripts', label: 'Ask Crump Manuscripts'}" in product
    assert "video: {kicker: 'MOTION', title: 'Video Studio', label: 'Ask Crump Video Studio'}" in product
    assert "selectStudioPanel(section)" in product
    assert 'id="crump53OpenProjectsFromManuscript"' in product
    assert "openStudio('projects')" in product
    assert "openStudio('video')" in product
    assert "section === 'projects'" in navigation
    assert "section === 'manuscripts' || section === 'video'" in navigation
    assert "panel.setAttribute('role', 'region')" in polish
    assert "panel.setAttribute('aria-hidden', panel.hidden ? 'true' : 'false')" in polish
    assert "role', 'tab'" not in polish


def test_private_video_library_uses_owner_checked_inline_playback():
    routes = read("backend/routes/files.py")
    product = read("public/crump-product-5.3.js")
    styles = read("public/crump-product-5.3.css")
    assert "@router.get('/{file_id}/playback')" in routes
    assert "'Cache-Control': 'private, no-store'" in routes
    assert "api(`/api/files/${encodeURIComponent(fileId)}/playback`)" in product
    assert "IntersectionObserver" in product
    assert ".crump53-playback-state" in styles


def test_compact_creation_menu_preserves_every_tool():
    product = read("public/crump-product-5.3.js")
    styles = read("public/crump-product-5.3.css")
    for tool in ("focus", "research", "image", "document", "manuscript", "video", "file"):
        assert f"{tool}: {{label:" in product
    assert "enhanceToolMenu(strip)" in product
    assert ".crump53-tool-menu" in styles


def test_feature_policy_has_explicit_expensive_tool_gates():
    policy = read("backend/feature_service.py")
    assert '"image"' in policy and '"professional"' in policy
    assert '"video"' in policy and '60' in policy
    assert '"video_hd"' in policy and '90' in policy
    assert '"manuscript_draft"' in policy and '8' in policy
    assert '"manuscript_blueprint"' in policy and '4' in policy
    assert '"kdp_export"' in policy and '{"free": -1' in policy
    assert 'PROJECT_LIMITS = {"free": 2, "professional": 25, "enterprise": 200}' in policy


def test_projects_ui_exposes_isolated_canon_and_video_copy_matches_cost_policy():
    js = read("public/crump-product-5.3.js")
    assert "Canon & project notes" in js
    assert "/context`" in js
    assert "720p · 60 credits" in js
    assert "every generation spends crump credits" in js.lower()
    assert "Planning costs 4 credits and drafting costs 8 on Free" in js
    assert "Enterprise includes one" not in js


def test_native_bundle_loads_the_same_product_layers_as_the_web_runtime():
    native = read("scripts/build-native.mjs")
    for asset in (
        "/crump-v1-stability.css",
        "/crump-v1-stability.js",
        "/crump-navigation-5.2.5.css",
        "/crump-navigation-5.2.5.js",
        "/crump-product-5.3.css",
        "/crump-product-5.3.js",
        "/crump-product-5.3.1.css",
        "/crump-product-5.3.1.js",
        "/crump-subscriptions-5.3.2.js",
        "/crump-polish-5.6.css",
        "/crump-polish-5.6.js",
        "/crump-navigation-5.9.30.css",
        "/crump-navigation-5.9.30.js",
    ):
        assert asset in native
    assert native.index("/crump-navigation-5.2.5.js") < native.index("/crump-product-5.3.js")
    assert native.index("/crump-library-5.7.js") < native.index("/crump-navigation-5.9.30.js")


def test_manuscript_ui_exposes_planning_progress_and_chat_handoff():
    js = read("public/crump-product-5.3.js")
    assert "Create & plan" in js
    assert "Draft next chapter" in js
    assert 'id="crump53ManuscriptWorkspace"' in js
    assert "manuscriptWorkspace" in js
    assert "crump53DocumentMode" in js
