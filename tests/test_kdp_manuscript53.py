from io import BytesIO
import zipfile

from backend.manuscript_service import (
    ManuscriptService,
    chapter_count_from_prompt,
    estimate_pages,
    kdp_inside_margin,
    kdp_profile,
    target_words_from_prompt,
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


def test_long_form_targets_are_read_from_natural_language_and_bounded():
    assert target_words_from_prompt('Write a 70,000 word novel.') == 70_000
    assert target_words_from_prompt('Build a 65k-word memoir.') == 65_000
    assert target_words_from_prompt('Write a 999,999 word book.') == 150_000
    assert chapter_count_from_prompt('Plan this as 34 chapters.') == 34
    assert chapter_count_from_prompt('Use 99 chapters.') == 80


def test_blueprint_json_and_continuity_summary_are_resilient():
    decoded = ManuscriptService._decode_blueprint(
        '```json\n{"title":"Northbound","chapters":[{"title":"Departure","purpose":"Leave home."}]}\n```'
    )
    assert decoded['title'] == 'Northbound'
    normalized = ManuscriptService._normalize_blueprint(
        decoded,
        brief='Write an original road novel.',
        preferred_title='',
        target_words=70_000,
        chapter_count=12,
    )
    assert normalized['title'] == 'Northbound'
    assert normalized['targetWords'] == 70_000
    assert len(normalized['chapters']) == 12

    summary = ManuscriptService._summary('opening ' + ('middle ' * 400) + 'final state')
    assert summary.startswith('opening')
    assert '[chapter ending]' in summary
    assert summary.endswith('final state')


def test_long_form_routes_and_platform_capabilities_are_explicit():
    root = __import__('pathlib').Path(__file__).resolve().parents[1]
    routes = (root / 'backend' / 'routes' / 'manuscripts.py').read_text(encoding='utf-8')
    chat = (root / 'backend' / 'routes' / 'chat.py').read_text(encoding='utf-8')
    prompt = (root / 'backend' / 'ai_service.py').read_text(encoding='utf-8')
    assert '/blueprint' in routes
    assert '/draft-next' in routes
    assert 'begin_long_form' in chat
    assert 'manuscriptWorkspace' in chat
    assert 'downloadable DOCX, PDF, PPTX, XLSX' in prompt


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
