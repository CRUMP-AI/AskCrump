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
    assert "ask-crump-new-body-v1-r81" in worker


def test_navigation_exposes_exact_product_destinations_on_desktop_and_mobile():
    script = read("public/crump-navigation-5.9.30.js")
    styles = read("public/crump-navigation-5.9.30.css")

    for destination in ("ask", "projects", "create", "library", "you"):
        assert f"id: '{destination}'" in script

    assert "crump5930-rail-destinations" in script
    assert 'id = \'crump5930MobileNav\'' in script
    assert "grid-template-columns: repeat(5,minmax(0,1fr))" in styles
    assert "aria-current" in script


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
    assert "window.CrumpBodyV1 = Object.freeze({command})" in body
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
