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
