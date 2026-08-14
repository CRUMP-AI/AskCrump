from io import BytesIO
import zipfile

from backend.manuscript_service import (
    ManuscriptService,
    estimate_pages,
    kdp_inside_margin,
    kdp_profile,
)


def test_kdp_gutter_tiers_and_bleed_page_math():
    assert kdp_inside_margin(150) == 0.375
    assert kdp_inside_margin(151) == 0.5
    assert kdp_inside_margin(301) == 0.625
    assert kdp_inside_margin(501) == 0.75
    assert kdp_inside_margin(701) == 0.875
    profile = kdp_profile(trim_code="6x9", page_count=320, bleed=True)
    assert profile["trimWidth"] == 6.0
    assert profile["trimHeight"] == 9.0
    assert profile["pageWidth"] == 6.125
    assert profile["pageHeight"] == 9.25
    assert profile["insideMargin"] == 0.625
    assert profile["outsideMargin"] >= 0.375
    oversized = kdp_profile(trim_code="8.5x11", page_count=591, bleed=False)
    assert oversized["blackInkWhitePaperMaxPages"] == 590
    assert oversized["warnings"]


def test_page_estimate_never_drops_below_kdp_minimum_print_length():
    assert estimate_pages(100) >= 24
    assert estimate_pages(100_000) > 300


def test_docx_pdf_and_epub_exports_have_valid_container_signatures():
    service = ManuscriptService(db=None, ai=None, projects=None)
    manuscript = {
        "id": "00000000-0000-0000-0000-000000000001",
        "title": "Test Novel",
        "subtitle": "",
        "author_name": "Test Author",
    }
    sections = [
        {"title": "Chapter One", "content": "The opening paragraph.\n\nA second paragraph.\n\n⸻\n\nAfter the break."}
    ]
    profile = kdp_profile(trim_code="6x9", page_count=180, bleed=False)

    docx = service._docx(manuscript, sections, profile)
    assert docx.startswith(b"PK")
    with zipfile.ZipFile(BytesIO(docx)) as archive:
        assert "word/document.xml" in archive.namelist()
        settings = archive.read("word/settings.xml")
        assert b"mirrorMargins" in settings

    pdf = service._pdf(manuscript, sections, profile)
    assert pdf.startswith(b"%PDF")

    epub = service._epub(manuscript, sections)
    with zipfile.ZipFile(BytesIO(epub)) as archive:
        assert archive.namelist()[0] == "mimetype"
        assert archive.read("mimetype") == b"application/epub+zip"
        assert "OEBPS/package.opf" in archive.namelist()
        assert "OEBPS/nav.xhtml" in archive.namelist()
