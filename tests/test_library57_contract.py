from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_library57_frontend_and_runtime_contract():
    library_js = (ROOT / "public" / "crump-library-5.7.js").read_text(encoding="utf-8")
    library_css = (ROOT / "public" / "crump-library-5.7.css").read_text(encoding="utf-8")
    runtime = (ROOT / "public" / "runtime-body-v1.js").read_text(encoding="utf-8")
    build_native = (ROOT / "scripts" / "build-native.mjs").read_text(encoding="utf-8")
    native_entry = (ROOT / "public" / "native-entry.js").read_text(encoding="utf-8")

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
