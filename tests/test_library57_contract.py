from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_library57_frontend_and_runtime_contract():
    library_js = read("public/crump-library-5.7.js")
    library_css = read("public/crump-library-5.7.css")
    runtime = read("public/runtime-body-v1.js")
    build_native = read("scripts/build-native.mjs")
    native_entry = read("public/native-entry.js")

    assert "/api/library/books/import" in library_js
    assert "Import a manuscript" in library_js
    assert "Front cover" in library_js
    assert "Back cover" in library_js
    assert "saveMedia" in library_js
    assert ".crump57-bookshelf" in library_css
    assert "/crump-library-5.7.js" in runtime
    assert "/crump-library-5.7.css" in runtime
    assert "/crump-library-5.7.js" in build_native
    assert "@capacitor-community/media" in native_entry


def test_library571_mobile_layout_and_book_views_are_intentional():
    library_js = read("public/crump-library-5.7.js")
    library_css = read("public/crump-library-5.7.css")

    for layout in ("grid", "list", "book"):
        assert f"'{layout}'" in library_js
    assert "askcrump.library57.preferences" in library_js
    assert "Recently Deleted" in library_js
    assert "Preview book" in library_js
    assert "Front + back covers" in library_js
    assert "crump57-library-shell" in library_js
    assert "button.textContent = 'Opening…'" in library_js
    assert "async function openBookReader(book)" in library_js
    assert "readerParagraphs(section.content)" in library_js
    assert "data-crump57-workspace" in library_js
    assert ">Edit manuscript</button>" in library_js
    assert "async function openBookWorkspace(book)" in library_js
    assert "crump57-reader-sheet" in library_css
    assert "crump57-reader-mobile-nav" in library_css
    assert ".crump57-bookshelf.is-layout-book" in library_css
    assert "grid-template-columns: 112px minmax(0, 1fr)" in library_css
    assert ".crump57-bookshelf.is-layout-grid" in library_css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in library_css
    assert "Mobile Grid stays a true visual grid" in library_css
    assert "top: 0 !important" in library_css
    assert "Book-inspired, not book-themed" in library_css


def test_library571_delete_restore_is_owner_checked_and_recoverable():
    routes = read("backend/routes/library.py")
    service = read("backend/library_service.py")
    files = read("backend/file_service.py")

    assert '@router.get("/books/deleted")' in routes
    assert '@router.post("/books/{manuscript_id}/trash")' in routes
    assert '@router.post("/books/{manuscript_id}/restore")' in routes
    assert '@router.delete("/books/{manuscript_id}")' in routes
    assert "deleteSource" in routes

    assert "async def trash_book" in service
    assert "async def restore_book" in service
    assert "async def delete_book_permanently" in service
    assert '"archived_at": trashed_at' in service
    assert '"archived_at": None' in service
    assert "MANUSCRIPT_RUN_ACTIVE" in service
    assert "_source_is_referenced_elsewhere" in service
    assert "libraryTrash" in service

    assert "async def restore_soft_deleted" in files
    assert "async def hard_delete" in files
    assert "payload={'prefixes': [storage_path]}" in files
    assert "await self.db.delete(" in files
