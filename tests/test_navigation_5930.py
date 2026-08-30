from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_five_destination_navigation_is_final_runtime_layer_and_boot_critical():
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")

    for asset in ("/crump-navigation-5.9.30.css", "/crump-navigation-5.9.30.js"):
        assert asset in runtime
        assert worker.count(asset) >= 2
        assert f"url.pathname === '{asset}'" in worker
        assert asset.lstrip("/") in checker

    assert runtime.index("/crump-library-5.7.js") < runtime.index("/crump-navigation-5.9.30.js")
    assert "ask-crump-new-body-v1-r132" in worker


def test_navigation_exposes_exact_product_destinations_on_desktop_and_mobile():
    script = read("public/crump-navigation-5.9.30.js")
    styles = read("public/crump-navigation-5.9.30.css")

    for destination in ("ask", "projects", "create", "library", "you"):
        assert f"id: '{destination}'" in script

    assert "crump5930-rail-destinations" in script
    assert 'id = \'crump5930MobileNav\'' in script
    assert "grid-template-columns: repeat(5,minmax(0,1fr))" in styles
    assert "aria-current" in script


def test_destination_surfaces_leave_persistent_navigation_clickable():
    styles = read("public/crump-navigation-5.9.30.css")

    assert ".crump53-overlay," in styles
    assert ".crump5930-create-overlay," in styles
    assert "#settingsModal" in styles
    assert "left: var(--ac-rail);" in styles
    assert "bottom: calc(var(--crump5930-mobile-nav) + env(safe-area-inset-bottom));" in styles
    assert "100dvh - var(--crump5930-mobile-nav)" in styles


def test_navigation_reuses_existing_product_surfaces_without_data_migration():
    script = read("public/crump-navigation-5.9.30.js")
    body = read("public/crump-v1-body.js")
    documents = read("public/crump-5.0.js")

    assert "window.CrumpProduct53?.open?.('projects')" in script
    assert "window.CrumpProduct53?.open?.('library')" in script
    assert "window.CrumpProduct53?.open?.(action === 'manuscript' ? 'manuscripts' : 'video')" in script
    assert "window.CrumpDocumentStudio?.open?.()" in script
    assert "window.CrumpDocumentStudio?.select?.('pptx'" in script
    assert "window.CrumpImageStudio.open()" in script
    assert "window.CrumpBodyV1 = Object.freeze({" in body
    assert "syncConversationLibrary: syncLibraryControl" in body
    assert "toggleConversationLibrary: openLibrary" in body
    assert "window.CrumpImageStudio = Object.freeze" in documents
    assert "select: (format = 'docx'" in documents


def test_create_hub_is_non_generating_and_accessible_until_user_sends():
    script = read("public/crump-navigation-5.9.30.js")

    assert 'role="dialog" aria-modal="true"' in script
    assert "Nothing generates until you review the setup and send your request." in script
    assert "crump5930CreateClose" in script
    assert "event.key === 'Escape'" in script
    assert "fetch(" not in script


def test_navigation_has_a_bounded_local_rollback_switch():
    script = read("public/crump-navigation-5.9.30.js")

    assert "askcrump.navigation.mode" in script
    assert "=== 'legacy'" in script
    assert "dataset.crumpNavigation5930 = 'legacy'" in script


def test_chats_contains_history_while_account_actions_live_under_you():
    page = read("public/app.html")
    script = read("public/crump-navigation-5.9.30.js")
    styles = read("public/crump-navigation-5.9.30.css")

    assert 'data-v1-settings-tab="plan"' in page
    assert 'data-v1-settings-panel="plan"' in page
    assert 'id="v1OpenPlanBtn"' in page
    assert 'id="v1PlanCreditSummary"' in page
    assert "function consolidateAccountNavigation()" in script
    assert "footer.hidden = true;" in script
    assert "footer.setAttribute('aria-hidden', 'true');" in script
    assert "byId('upgradeBtnSidebar')?.click()" in script
    assert "new MutationObserver(syncPlanSummary)" in script
    assert '.v1-library-footer[hidden]' in styles
    assert "display: none !important" in styles


def test_settings_save_action_only_appears_on_editable_sections():
    body = read("public/crump-v1-body.js")

    assert "saveButton.hidden = !['profile', 'behavior'].includes(name);" in body


def test_navigation_consolidation_fixture_uses_the_production_layers():
    fixture = read("tests/fixtures/navigation-consolidation.html")

    assert '/public/crump-v1-body.js' in fixture
    assert '/public/crump-navigation-5.9.30.js' in fixture
    assert 'id="v1OpenPlanBtn"' in fixture
    assert 'id="billingProof"' in fixture
    assert 'billing51-sidebar-balance">649 C' in fixture
