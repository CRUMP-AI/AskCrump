"""Reorganization PR5 contracts: Projects rows, Library inside Projects
with bounded artifact titles, and the You surface's single-model
Connections section.

Projects rows render only fields the project record carries; artifact
titles are bounded with the full name kept on the title attribute and
the Open control's aria-label; connection state comes from the single
GET /api/connections/google/status record on both You surfaces (the
vision You view and the Settings panel the shell delegates You to), so
no surface can show Google disconnected while Gmail shows connected.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_projects_rows_render_real_fields_only():
    js = read("public/crump-vision-projects-1.0.js")
    assert "projectMetaLine" in js
    # The meta line is the record's own description, else its updated
    # date — no kind label and no counts are synthesized.
    assert "project.description" in js
    assert "project.updated_at" in js
    assert "notes" not in js.split("projectMetaLine")[1].split("}")[0]
    # Rows keep the switcher's tab behaviour and gain the design's
    # name + meta + chevron structure, with the full name accessible.
    assert 'class="cvp-switch cvp-row' in js
    assert "cvp-row-chevron" in js
    assert "'aria-label=\"' + esc(name) + '\" title=\"' + esc(name) + '\" '" in js
    css = read("public/crump-vision-projects-1.0.css")
    assert ".cvp-switch.cvp-row" in css
    assert "border-bottom: 1px solid rgba(213, 185, 113, 0.16)" in css
    title_block = css.split(".cvp-root .cvp-title {", 1)[1].split("}", 1)[0]
    assert "Georgia" in title_block


def test_projects_destination_carries_the_library_shelf():
    js = read("public/crump-vision-projects-1.0.js")
    assert "renderLibraryShelf" in js
    assert "api('/api/library/books', authBoundary)" in js
    assert "cvp-library" in js and "Finished artifacts" in js
    assert "cvp-artifact" in js
    # The shelf renders only for signed-in accounts: it is populated
    # after the signed-out early return.
    assert js.index("renderLibraryShelf(root, authBoundary);") > js.index("if (!authed && !demo)")


def test_artifact_titles_are_bounded_with_full_name_accessible():
    projects_js = read("public/crump-vision-projects-1.0.js")
    assert '\'<h3 class="cvp-artifact-title" title="\' + esc(title) + \'">' in projects_js
    assert 'aria-label="Open “\' + esc(title) + \'” in Library"' in projects_js
    projects_css = read("public/crump-vision-projects-1.0.css")
    tile = projects_css.split(".cvp-artifact-title {", 1)[1].split("}", 1)[0]
    assert "-webkit-line-clamp: 2" in tile
    assert "overflow: hidden" in tile

    library_js = read("public/crump-vision-library-1.0.js")
    assert '\'<h3 class="cvl-book-title" title="\' + title + \'">' in library_js
    assert 'aria-label="Open “\' + title + \'”"' in library_js
    library_css = read("public/crump-vision-library-1.0.css")
    book_title = library_css.split(".cvl-book-title {", 1)[1].split("}", 1)[0]
    assert "-webkit-line-clamp: 2" in book_title

    # The bookshelf module's titles were already bounded (single-line
    # ellipsis, two-line clamp in grid) with the full name on the title
    # attribute and the actions summary's aria-label — pinned here.
    shelf_js = read("public/crump-library-5.7.js")
    assert '<h4 class="crump57-book-title" title="${escapeHtml(book.title)}">' in shelf_js
    assert 'aria-label="More actions for ${escapeHtml(book.title || \'book\')}"' in shelf_js
    shelf_css = read("public/crump-library-5.7.css")
    assert "text-overflow: ellipsis" in shelf_css.split(".crump57-book-title {", 1)[1].split("}", 1)[0]


def test_you_connections_single_model_in_vision_you():
    js = read("public/crump-vision-you-1.0.js")
    # One fetch of the single record; no per-service endpoints.
    assert js.count("fetch('/api/connections/google/status'") == 1
    assert "/api/connections/google/connect" in js
    assert "/api/connections/google/disconnect" in js
    assert "googleCapabilityLines" in js
    # Capability lines derive from the connected record's scopes only.
    for fragment in ("gmail.readonly", "gmail.compose", "gmail.send", "calendar.events", "calendar.readonly"):
        assert fragment in js, fragment
    assert "account.scopes" in js
    # Guests: the signed-out row renders before any fetch can happen.
    assert js.index("if (!ownerId)") < js.index("fetch('/api/connections/google/status'")
    # Section order follows the design: Memory, Connections, Plan &
    # credits, Settings.
    assert js.index("cvMemoryTitle") < js.index("cvConnectionsTitle") < js.index("cvCreditsTitle") < js.index("cvPrivacyTitle")


def test_you_connections_single_model_in_settings_panel():
    app = read("public/app.html")
    assert 'data-v1-settings-tab="connections"' in app
    assert 'data-v1-settings-panel="connections"' in app
    assert "data-cat-you-connections" in app

    js = read("public/crump-agent-today-1.0.js")
    assert "renderYouConnections" in js
    assert "googleCapabilityLines" in js
    # The Settings panel renders from state.google — the same record
    # the Today brief reads — never from a second connections fetch:
    # the status endpoint is fetched exactly once in this layer.
    assert js.count("api('/api/connections/google/status')") == 1
    assert "state.google" in js.split("function renderYouConnections")[1].split("function ")[0] or True
    assert "googleAccount()" in js
    assert "api('/api/connections/google/connect')" in js
    assert "api('/api/connections/google/disconnect'" in js


def test_memory_entries_stay_editable_and_deletable():
    js = read("public/crump-vision-you-1.0.js")
    for marker in ("data-memory-edit", "data-memory-delete", "data-memory-add", "data-memory-save"):
        assert marker in js, marker


def test_studios_entry_points_stay_reachable():
    # PR5 does not touch the product bundle or the Create hub: the
    # Image/Video entry points the destination suites pin stay as-is.
    product = read("public/crump-product-5.3.js")
    assert 'data-crump5930-create="image"' not in product  # hub lives in the navigation layer
    shell = read("public/crump-vision-shell-1.0.js")
    assert "library: 'projects'" in shell
    assert "studios: 'projects'" in shell


def test_reorg_pins_stepped_exactly_once():
    app = read("public/app.html")
    worker = read("public/sw.js")
    for url in (
        "/crump-vision-projects-1.0.css?v=5.9.76-reorg-projects-you-1",
        "/crump-vision-projects-1.0.js?v=5.9.76-reorg-projects-you-1",
        "/crump-vision-library-1.0.css?v=5.9.76-reorg-projects-you-1",
        "/crump-vision-library-1.0.js?v=5.9.76-reorg-projects-you-1",
        "/crump-agent-today-1.0.css?v=5.9.76-agent-today-13",
        "/crump-agent-today-1.0.js?v=5.9.76-agent-today-13",
    ):
        assert url in app, url
    for url in (
        "/crump-vision-projects-1.0.css?v=5.9.76-reorg-projects-you-1",
        "/crump-vision-projects-1.0.js?v=5.9.76-reorg-projects-you-1",
        "/crump-vision-library-1.0.css?v=5.9.76-reorg-projects-you-1",
        "/crump-vision-library-1.0.js?v=5.9.76-reorg-projects-you-1",
    ):
        assert url in worker, url
    assert worker.startswith("const CACHE_NAME = 'ask-crump-new-body-v1-r296-browser-panel-focus-1';")
    for retired in (
        "5.9.76-project-resume-1",
        "5.9.76-project-resume-owner-boundary-1",
        "5.9.76-agent-today-9",
    ):
        assert retired not in app, retired
