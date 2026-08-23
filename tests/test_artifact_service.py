from io import BytesIO
import zipfile

from docx import Document
from openpyxl import load_workbook
from pptx import Presentation
from pypdf import PdfReader

from backend.artifact_service import ArtifactService


class DummyFiles:
    pass


def service():
    return ArtifactService(DummyFiles())


SAMPLE = """# Product Brief

## Purpose
A concise, polished artifact.

- First point
- Second point

| Item | Value |
| --- | --- |
| Quality | High |
| Readiness | 95% |
| Budget | $12,500 |
| Launch | 2026-09-15 |
"""


def test_binary_artifacts_are_valid_containers():
    generator = service()
    docx = generator.docx(SAMPLE)
    pptx = generator.pptx(SAMPLE)
    xlsx = generator.xlsx(SAMPLE)
    pdf = generator.pdf(SAMPLE)
    assert zipfile.is_zipfile(BytesIO(docx))
    assert zipfile.is_zipfile(BytesIO(pptx))
    assert zipfile.is_zipfile(BytesIO(xlsx))
    assert pdf.startswith(b'%PDF')


def test_supported_format_aliases():
    assert ArtifactService.normalize_format('Word') == 'docx'
    assert ArtifactService.normalize_format('.PDF') == 'pdf'
    assert ArtifactService.normalize_format('powerpoint') == 'pptx'
    assert ArtifactService.normalize_format('excel') == 'xlsx'


def test_natural_language_document_requests_are_detected():
    assert ArtifactService.detect_request(
        'Write the full manuscript and send it as a Word documented file.'
    ) == 'docx'
    assert ArtifactService.detect_request('Please compose the proposal and deliver a PDF.') == 'pdf'
    assert ArtifactService.detect_request('Create a downloadable resume document.') == 'docx'
    assert ArtifactService.detect_request('Write a report here in the chat.') is None


def test_book_scale_work_is_handed_to_a_persistent_manuscript():
    assert ArtifactService.is_long_form_request(
        'Write a complete 70,000 word novel and send it as a Word document.'
    ) is True
    assert ArtifactService.is_long_form_request('Draft my full-length memoir from start to finish.') is True
    assert ArtifactService.is_long_form_request('Create a book summary PDF.') is False
    assert ArtifactService.is_long_form_request('Recommend a book about Georgia history.') is False


def test_word_export_has_real_hierarchy_table_metadata_and_page_number():
    data = service().docx(SAMPLE, profile='business')
    document = Document(BytesIO(data))
    assert document.core_properties.author == 'Ask Crump'
    assert document.core_properties.title == 'Product Brief'
    assert document.sections[0].top_margin.inches < 0.9
    assert document.styles['Title'].font.size.pt >= 24
    assert document.tables
    assert document.tables[0].cell(0, 0).text == 'Item'
    footer_xml = document.sections[0].footer._element.xml
    assert 'PAGE' in footer_xml
    assert 'ASK CRUMP' in document.sections[0].header.paragraphs[0].text


def test_academic_and_resume_profiles_use_professional_conventions():
    generator = service()
    assert generator.profile_for('', 'Write a college research essay in APA style', 'docx') == 'academic'
    assert generator.profile_for('', 'Create my résumé for a product role', 'docx') == 'resume'

    academic = Document(BytesIO(generator.docx('# Evidence and Judgment\n\nA finished paragraph.', profile='academic')))
    assert academic.styles['Normal'].font.name == 'Times New Roman'
    assert academic.styles['Normal'].font.size.pt == 12
    assert academic.styles['Normal'].paragraph_format.line_spacing == 2.0
    assert round(academic.sections[0].left_margin.inches, 2) == 1.0

    resume = Document(BytesIO(generator.docx('# Jordan Ellis\n\n## Experience\n\n- Led product discovery.', profile='resume')))
    assert resume.styles['Normal'].font.name == 'Aptos'
    assert resume.sections[0].header.paragraphs[0].text == ''
    assert resume.sections[0].left_margin.inches < 0.7


def test_long_academic_title_is_complete_not_repeated_and_has_neutral_footer():
    title = 'Governance Before Scale: A Human-Centered Standard for Generative AI in Higher Education'
    academic = Document(BytesIO(service().docx(f'# {title}\n\nA finished paragraph.', profile='academic')))
    assert academic.paragraphs[0].text == title
    assert sum(paragraph.text == title for paragraph in academic.paragraphs) == 1
    footer = academic.sections[0].footer
    assert 'Ask Crump' not in footer.paragraphs[0].text
    assert 'PAGE' in footer._element.xml


def test_presentation_export_uses_custom_widescreen_layout_and_readable_type():
    deck = Presentation(BytesIO(service().pptx(SAMPLE)))
    assert round(deck.slide_width / deck.slide_height, 2) == round(16 / 9, 2)
    assert len(deck.slides) >= 3
    assert len(deck.slides[0].placeholders) == 0
    text_shapes = [shape for shape in deck.slides[0].shapes if getattr(shape, 'has_text_frame', False)]
    title_shape = next(shape for shape in text_shapes if shape.text == 'Product Brief')
    assert title_shape.text_frame.paragraphs[0].font.size.pt >= 46
    assert any(shape.text == 'ASK CRUMP' for shape in text_shapes)
    for slide in list(deck.slides)[1:]:
        assert any(
            shape.text == 'ASK CRUMP'
            for shape in slide.shapes
            if getattr(shape, 'has_text_frame', False)
        )


def test_spreadsheet_export_is_structured_typed_filterable_and_safe():
    generator = service()
    workbook = load_workbook(BytesIO(generator.xlsx(SAMPLE)), data_only=False)
    assert workbook.sheetnames[0] == 'Overview'
    data_sheet = workbook[workbook.sheetnames[1]]
    assert workbook['Overview'].print_area == "'Overview'!$A$1:$F$15"
    assert data_sheet.freeze_panes == 'A2'
    assert data_sheet.print_area
    assert data_sheet.sheet_view.showGridLines is False
    assert data_sheet.tables
    assert data_sheet['B3'].value == 0.95
    assert data_sheet['B3'].number_format == '0.0%'
    assert data_sheet['B4'].value == 12500
    assert '$' in data_sheet['B4'].number_format
    assert isinstance(data_sheet['B5'].value, __import__('datetime').datetime)
    assert generator._typed_cell('=SUM(B2:B4)')[0] == '=SUM(B2:B4)'
    assert generator._typed_cell('=HYPERLINK("https://bad.example","open")')[0].startswith("'=")
    assert generator._typed_cell("='[external.xlsx]Sheet1'!A1")[0].startswith("'=")


def test_pdf_export_is_extractable_and_paginated():
    reader = PdfReader(BytesIO(service().pdf(SAMPLE)))
    assert reader.metadata.author == 'Ask Crump'
    extracted = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert 'Product Brief' in extracted
    assert 'ASK CRUMP' in extracted


def test_creation_guidance_guards_truth_and_matches_the_format():
    resume = ArtifactService.creation_guidance('docx', 'Create my résumé')
    academic = ArtifactService.creation_guidance('docx', 'Write a college essay with APA citations')
    slides = ArtifactService.creation_guidance('pptx', 'Create a board presentation')
    workbook = ArtifactService.creation_guidance('xlsx', 'Build a financial model')
    assert 'Never invent citations' in resume
    assert 'ATS-friendly' in resume and 'user supplied the number' in resume
    assert 'Cite only sources' in academic and 'defensible thesis' in academic
    assert 'one clear takeaway headline per slide' in slides
    assert 'Never invent business or financial data' in workbook
