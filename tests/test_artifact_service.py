from io import BytesIO
import zipfile

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
