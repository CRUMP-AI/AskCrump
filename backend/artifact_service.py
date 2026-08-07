"""Generate polished user-downloadable documents from Crump responses."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from pptx import Presentation
from pptx.util import Inches as PptInches, Pt as PptPt
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from .file_service import FileService


VALID_FORMATS = {'docx', 'pdf', 'pptx', 'xlsx', 'md', 'txt'}
MIME = {
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pdf': 'application/pdf',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'md': 'text/markdown',
    'txt': 'text/plain',
}


@dataclass(slots=True)
class ArtifactService:
    files: FileService

    @staticmethod
    def normalize_format(value: Any) -> str | None:
        raw = str(value or '').strip().lower().lstrip('.')
        aliases = {'word': 'docx', 'powerpoint': 'pptx', 'excel': 'xlsx', 'markdown': 'md', 'text': 'txt'}
        raw = aliases.get(raw, raw)
        return raw if raw in VALID_FORMATS else None

    @classmethod
    def detect_request(cls, message: str, explicit: Any = None) -> str | None:
        selected = cls.normalize_format(explicit)
        if selected:
            return selected
        text = str(message or '').lower().strip()
        if not re.search(r'\b(create|make|generate|export|deliver|build|produce|turn|convert|save)\b', text):
            return None
        formats = [
            (r'\b(powerpoint|pptx|slide deck|presentation)\b', 'pptx'),
            (r'\b(excel|xlsx|spreadsheet)\b', 'xlsx'),
            (r'\b(word document|docx|word file)\b', 'docx'),
            (r'\bpdf\b', 'pdf'),
            (r'\bmarkdown|\.md\b', 'md'),
            (r'\btext file|\.txt\b', 'txt'),
        ]
        for pattern, fmt in formats:
            if re.search(pattern, text):
                return fmt
        return None

    @staticmethod
    def title_from(text: str, fallback: str = 'Ask Crump') -> str:
        for line in str(text or '').splitlines():
            clean = re.sub(r'^#{1,6}\s*', '', line).strip()
            if clean:
                return clean[:80]
        return fallback

    @staticmethod
    def safe_stem(title: str) -> str:
        stem = re.sub(r'[^A-Za-z0-9 -]+', '', title).strip()
        stem = re.sub(r'\s+', '_', stem)[:60]
        return stem or 'Ask_Crump_Document'

    @staticmethod
    def blocks(markdown: str) -> list[tuple[str, str]]:
        blocks: list[tuple[str, str]] = []
        in_code = False
        code: list[str] = []
        paragraph: list[str] = []

        def flush_para() -> None:
            if paragraph:
                blocks.append(('p', ' '.join(part.strip() for part in paragraph if part.strip())))
                paragraph.clear()

        for raw in str(markdown or '').replace('\r\n', '\n').split('\n'):
            if raw.strip().startswith('```'):
                flush_para()
                if in_code:
                    blocks.append(('code', '\n'.join(code)))
                    code.clear()
                in_code = not in_code
                continue
            if in_code:
                code.append(raw)
                continue
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped:
                flush_para()
                continue
            heading = re.match(r'^(#{1,4})\s+(.+)$', stripped)
            if heading:
                flush_para()
                blocks.append((f'h{len(heading.group(1))}', heading.group(2).strip()))
                continue
            bullet = re.match(r'^[-*]\s+(.+)$', stripped)
            if bullet:
                flush_para()
                blocks.append(('li', bullet.group(1).strip()))
                continue
            paragraph.append(stripped)
        flush_para()
        if code:
            blocks.append(('code', '\n'.join(code)))
        return blocks

    def docx(self, markdown: str) -> bytes:
        doc = Document()
        section = doc.sections[0]
        section.top_margin = Inches(0.72)
        section.bottom_margin = Inches(0.72)
        section.left_margin = Inches(0.82)
        section.right_margin = Inches(0.82)
        styles = doc.styles
        styles['Normal'].font.name = 'Aptos'
        styles['Normal'].font.size = Pt(10.5)
        for name, size in [('Title', 24), ('Heading 1', 17), ('Heading 2', 14), ('Heading 3', 12)]:
            styles[name].font.name = 'Aptos Display'
            styles[name].font.size = Pt(size)
        title = self.title_from(markdown)
        p = doc.add_paragraph(style='Title')
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.add_run(title)
        first_title_skipped = False
        for kind, text in self.blocks(markdown):
            if not first_title_skipped and kind.startswith('h') and text == title:
                first_title_skipped = True
                continue
            if kind == 'h1':
                doc.add_heading(text, level=1)
            elif kind == 'h2':
                doc.add_heading(text, level=2)
            elif kind in {'h3', 'h4'}:
                doc.add_heading(text, level=3)
            elif kind == 'li':
                doc.add_paragraph(text, style='List Bullet')
            elif kind == 'code':
                para = doc.add_paragraph()
                run = para.add_run(text)
                run.font.name = 'Consolas'
                run.font.size = Pt(9)
            elif text:
                doc.add_paragraph(text)
        out = BytesIO()
        doc.save(out)
        return out.getvalue()

    def pdf(self, markdown: str) -> bytes:
        out = BytesIO()
        doc = SimpleDocTemplate(out, pagesize=LETTER, leftMargin=0.72 * inch, rightMargin=0.72 * inch,
                                topMargin=0.68 * inch, bottomMargin=0.68 * inch,
                                title=self.title_from(markdown))
        sample = getSampleStyleSheet()
        body = ParagraphStyle('CrumpBody', parent=sample['BodyText'], fontName='Helvetica', fontSize=10.5,
                              leading=15, textColor='#1A1A1A', alignment=TA_LEFT, spaceAfter=7)
        title_style = ParagraphStyle('CrumpTitle', parent=sample['Title'], fontName='Helvetica-Bold',
                                     fontSize=23, leading=28, textColor='#111111', spaceAfter=18)
        h1 = ParagraphStyle('CrumpH1', parent=sample['Heading1'], fontName='Helvetica-Bold', fontSize=16,
                            leading=20, textColor='#111111', spaceBefore=13, spaceAfter=7)
        h2 = ParagraphStyle('CrumpH2', parent=h1, fontSize=13.5, leading=17)
        code_style = ParagraphStyle('CrumpCode', parent=body, fontName='Courier', fontSize=8.6,
                                    leading=11, backColor='#F4F4F4', borderPadding=7)
        story: list[Any] = [Paragraph(self._xml(self.title_from(markdown)), title_style)]
        bullets: list[ListItem] = []

        def flush_bullets() -> None:
            nonlocal bullets
            if bullets:
                story.append(ListFlowable(bullets, bulletType='bullet', leftIndent=16, bulletFontSize=7))
                story.append(Spacer(1, 5))
                bullets = []

        first = True
        for kind, text in self.blocks(markdown):
            if first and kind.startswith('h') and text == self.title_from(markdown):
                first = False
                continue
            first = False
            if kind == 'li':
                bullets.append(ListItem(Paragraph(self._xml(text), body), leftIndent=10))
                continue
            flush_bullets()
            if kind == 'h1':
                story.append(Paragraph(self._xml(text), h1))
            elif kind in {'h2', 'h3', 'h4'}:
                story.append(Paragraph(self._xml(text), h2))
            elif kind == 'code':
                story.append(Paragraph(self._xml(text).replace('\n', '<br/>'), code_style))
            elif text:
                story.append(Paragraph(self._xml(text), body))
        flush_bullets()
        doc.build(story)
        return out.getvalue()

    @staticmethod
    def _xml(text: str) -> str:
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def pptx(self, markdown: str) -> bytes:
        prs = Presentation()
        prs.slide_width = PptInches(13.333)
        prs.slide_height = PptInches(7.5)
        title = self.title_from(markdown)
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = title
        if len(slide.placeholders) > 1:
            slide.placeholders[1].text = 'Created with Ask Crump'
        sections: list[tuple[str, list[str]]] = []
        current_title = 'Overview'
        current: list[str] = []
        for kind, text in self.blocks(markdown):
            if kind.startswith('h'):
                if current:
                    sections.append((current_title, current))
                current_title, current = text, []
            elif text:
                current.append(text)
        if current:
            sections.append((current_title, current))
        for heading, lines in sections[:20]:
            for start in range(0, len(lines), 6):
                slide = prs.slides.add_slide(prs.slide_layouts[1])
                slide.shapes.title.text = heading if start == 0 else f'{heading} — continued'
                frame = slide.placeholders[1].text_frame
                frame.clear()
                for index, line in enumerate(lines[start:start + 6]):
                    p = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
                    p.text = re.sub(r'[`*_#]+', '', line)[:500]
                    p.font.size = PptPt(22)
                    p.space_after = PptPt(9)
        out = BytesIO()
        prs.save(out)
        return out.getvalue()

    def xlsx(self, markdown: str) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = 'Ask Crump'
        lines = [line for line in str(markdown or '').splitlines() if line.strip()]
        tables = self._markdown_tables(lines)
        if tables:
            for table_index, table in enumerate(tables):
                if table_index:
                    ws.append([])
                for row_index, row in enumerate(table):
                    ws.append(row)
                    if row_index == 0:
                        for cell in ws[ws.max_row]:
                            cell.font = Font(bold=True)
                            cell.alignment = Alignment(wrap_text=True)
            for column in ws.columns:
                letter = column[0].column_letter
                ws.column_dimensions[letter].width = min(45, max(12, max(len(str(cell.value or '')) for cell in column) + 2))
        else:
            ws['A1'] = self.title_from(markdown)
            ws['A1'].font = Font(bold=True, size=18)
            for index, line in enumerate(lines, start=3):
                ws.cell(index, 1, re.sub(r'^#{1,6}\s*', '', line))
                ws.cell(index, 1).alignment = Alignment(wrap_text=True, vertical='top')
            ws.column_dimensions['A'].width = 100
        out = BytesIO()
        wb.save(out)
        return out.getvalue()

    @staticmethod
    def _markdown_tables(lines: list[str]) -> list[list[list[str]]]:
        tables: list[list[list[str]]] = []
        index = 0
        while index < len(lines) - 1:
            if '|' in lines[index] and re.match(r'^\s*\|?\s*:?-{3,}', lines[index + 1]):
                table: list[list[str]] = []
                header = [cell.strip() for cell in lines[index].strip().strip('|').split('|')]
                table.append(header)
                index += 2
                while index < len(lines) and '|' in lines[index]:
                    table.append([cell.strip() for cell in lines[index].strip().strip('|').split('|')])
                    index += 1
                tables.append(table)
                continue
            index += 1
        return tables

    async def create(
        self,
        *,
        user_id: str,
        markdown: str,
        format_name: str,
        chat_id: str | None,
        message_id: str | None,
        title: str | None = None,
    ) -> dict[str, Any]:
        fmt = self.normalize_format(format_name)
        if not fmt:
            raise ValueError('Unsupported document format.')
        resolved_title = (title or self.title_from(markdown)).strip()[:80]
        stem = self.safe_stem(resolved_title)
        if fmt == 'docx':
            data = self.docx(markdown)
        elif fmt == 'pdf':
            data = self.pdf(markdown)
        elif fmt == 'pptx':
            data = self.pptx(markdown)
        elif fmt == 'xlsx':
            data = self.xlsx(markdown)
        elif fmt == 'md':
            data = markdown.encode('utf-8')
        else:
            data = re.sub(r'[`*_#]+', '', markdown).encode('utf-8')
        row = await self.files.store_bytes(
            user_id=user_id,
            data=data,
            filename=f'{stem}.{fmt}',
            mime_type=MIME[fmt],
            kind='generated_document',
            chat_id=chat_id,
            message_id=message_id,
            metadata={'format': fmt, 'title': resolved_title},
        )
        result = self.files.public_file(row)
        result.update({'format': fmt, 'title': resolved_title})
        return result
