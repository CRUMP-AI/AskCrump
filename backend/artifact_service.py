"""Generate polished, editable, user-downloadable Ask Crump artifacts.

The model writes the source content. This deterministic finishing layer applies
format-aware typography, safe spreadsheet behavior, restrained branding,
document metadata, and layouts that remain editable in Office applications.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import re
from typing import Any

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor as DocxRGBColor
from openpyxl import Workbook
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table as XlsxTable, TableStyleInfo
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches as PptInches, Pt as PptPt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

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
INK = '171B24'
NAVY = '202532'
GOLD = 'C9A95E'
CREAM = 'F6F1E7'
MUTED = '677080'
LINE = 'D9DDE4'


@dataclass(slots=True)
class ArtifactService:
    files: FileService

    ACTION_PATTERN = re.compile(
        r"\b(create|make|generate|export|deliver|build|produce|turn|convert|save|"
        r"write|draft|compose|prepare|format|package|send|provide|give|download)\b", re.I,
    )
    LONG_FORM_PATTERN = re.compile(
        r"\b(novel|book|memoir|manuscript|screenplay|dissertation|thesis)\b", re.I,
    )
    SHORT_FORM_PATTERN = re.compile(
        r"\b(summary|synopsis|outline|review|blurb|proposal|query letter|book report)\b", re.I,
    )
    RESUME_PATTERN = re.compile(
        r"\b(resume|r[ée]sum[ée]|curriculum vitae|\bcv\b|cover letter|job application)\b", re.I,
    )
    ACADEMIC_PATTERN = re.compile(
        r"\b(college|university|academic|essay|research paper|term paper|literature review|"
        r"dissertation|thesis|mla|apa|chicago style|works cited|bibliography)\b", re.I,
    )

    @staticmethod
    def normalize_format(value: Any) -> str | None:
        raw = str(value or '').strip().lower().lstrip('.')
        aliases = {'word': 'docx', 'powerpoint': 'pptx', 'excel': 'xlsx', 'markdown': 'md', 'text': 'txt'}
        raw = aliases.get(raw, raw)
        return raw if raw in VALID_FORMATS else None

    @classmethod
    def is_long_form_request(cls, message: str) -> bool:
        text = str(message or '').strip()
        if not text or not cls.ACTION_PATTERN.search(text) or not cls.LONG_FORM_PATTERN.search(text):
            return False
        if cls.SHORT_FORM_PATTERN.search(text):
            return False
        explicit_length = bool(re.search(
            r"\b(full[ -]?length|complete|entire|book[ -]?length|from start to finish)\b|"
            r"\b\d{2,3}(?:,\d{3})+\s*words?\b", text, re.I,
        ))
        writing_verb = bool(re.search(r"\b(write|draft|compose|author|create|produce|build)\b", text, re.I))
        substantial_kind = bool(re.search(
            r"\b(novel|memoir|manuscript|screenplay|dissertation|thesis)\b", text, re.I,
        ))
        return explicit_length or (writing_verb and substantial_kind) or bool(
            writing_verb and re.search(r"\bbook\b", text, re.I)
        )

    @classmethod
    def detect_request(cls, message: str, explicit: Any = None) -> str | None:
        selected = cls.normalize_format(explicit)
        if selected:
            return selected
        text = str(message or '').lower().strip()
        if not cls.ACTION_PATTERN.search(text):
            return None
        formats = [
            (r'\b(powerpoint|pptx|slide deck|presentation)\b', 'pptx'),
            (r'\b(excel|xlsx|spreadsheet|workbook)\b', 'xlsx'),
            (r'\bdocx\b|\bmicrosoft\s+word\b|\bword\s+(?:document(?:ed)?|doc|file|manuscript)\b', 'docx'),
            (r'\bpdf\b', 'pdf'),
            (r'\bmarkdown|\.md\b', 'md'),
            (r'\btext file|\.txt\b', 'txt'),
        ]
        for pattern, fmt in formats:
            if re.search(pattern, text):
                return fmt
        if re.search(
            r'\b(document|manuscript|report|letter|resume|r[ée]sum[ée]|essay|paper)\b', text,
        ) and re.search(r'\b(file|download|attachment|send|deliver|export|document)\b', text):
            return 'docx'
        return None

    @classmethod
    def profile_for(cls, markdown: str = '', brief: str = '', format_name: str = '') -> str:
        evidence = f'{brief}\n{markdown[:8000]}'.strip()
        if cls.RESUME_PATTERN.search(evidence):
            return 'resume'
        if cls.ACADEMIC_PATTERN.search(evidence):
            return 'academic'
        if cls.normalize_format(format_name) == 'pptx':
            return 'presentation'
        if cls.normalize_format(format_name) == 'xlsx':
            return 'spreadsheet'
        return 'business'

    @classmethod
    def creation_guidance(cls, format_name: str, brief: str = '') -> str:
        """Return a model-facing contract for the requested deliverable."""
        fmt = cls.normalize_format(format_name) or 'docx'
        profile = cls.profile_for('', brief, fmt)
        shared = (
            'Return only the finished source content—no production notes, promises, or commentary about '
            'creating a file. Follow every supplied fact and requirement. Never invent citations, employers, '
            'degrees, dates, metrics, quotations, research findings, or financial inputs. When a required fact '
            'is unavailable, use a clearly labeled placeholder or state the limitation instead of fabricating it.'
        )
        if profile == 'resume':
            return (
                f'{shared} Build an ATS-friendly résumé with a concise professional summary, relevant skills, '
                'reverse-chronological experience, and accomplishment bullets. Quantify impact only when the '
                'user supplied the number. Do not use tables, columns, icons, headshots, ratings, or references.'
            )
        if profile == 'academic':
            return (
                f'{shared} Build a coherent academic draft with a defensible thesis, logical sections, evidence '
                'and analysis, an appropriate counterpoint, and a substantive conclusion. Cite only sources '
                'present in supplied context or verified research results. Match the requested citation style; '
                'include a references section only when grounded source details are available.'
            )
        if fmt == 'pptx':
            return (
                f'{shared} Write a presentation outline in Markdown. Use one clear takeaway headline per slide, '
                'short supporting points, and no more than five points per slide. Prefer a narrative arc: context, '
                'insight, recommendation, execution, next step. Put grounded sources in a final Sources section.'
            )
        if fmt == 'xlsx':
            return (
                f'{shared} Provide structured Markdown tables with explicit assumptions, inputs, units, and '
                'outputs. Put formulas in cells beginning with = and keep formulas limited to normal cell '
                'references and standard spreadsheet functions. Never invent business or financial data.'
            )
        return (
            f'{shared} Use a clear title, executive-quality hierarchy, concise paragraphs, descriptive headings, '
            'useful lists, and tables where comparison or structured data benefits from them.'
        )

    @staticmethod
    def title_from(text: str, fallback: str = 'Ask Crump') -> str:
        for line in str(text or '').splitlines():
            clean = re.sub(r'^#{1,6}\s*', '', line).strip()
            if clean and not clean.startswith('|'):
                return clean[:160]
        return fallback

    @staticmethod
    def safe_stem(title: str) -> str:
        stem = re.sub(r'[^A-Za-z0-9 -]+', '', title).strip()
        stem = re.sub(r'\s+', '_', stem)[:60]
        return stem or 'Ask_Crump_Document'

    @staticmethod
    def _table_separator(line: str) -> bool:
        cells = [cell.strip() for cell in str(line).strip().strip('|').split('|')]
        return bool(cells) and all(re.fullmatch(r':?-{3,}:?', cell or '') for cell in cells)

    @classmethod
    def blocks(cls, markdown: str) -> list[tuple[str, Any]]:
        """Parse the conservative Markdown subset used across exported formats."""
        source = str(markdown or '').replace('\r\n', '\n').split('\n')
        output: list[tuple[str, Any]] = []
        paragraph: list[str] = []
        code: list[str] = []
        in_code = False
        index = 0

        def flush_para() -> None:
            if paragraph:
                output.append(('p', ' '.join(part.strip() for part in paragraph if part.strip())))
                paragraph.clear()

        while index < len(source):
            raw = source[index]
            stripped = raw.strip()
            if stripped.startswith('```'):
                flush_para()
                if in_code:
                    output.append(('code', '\n'.join(code)))
                    code.clear()
                in_code = not in_code
                index += 1
                continue
            if in_code:
                code.append(raw)
                index += 1
                continue
            if not stripped:
                flush_para()
                index += 1
                continue
            if '|' in stripped and index + 1 < len(source) and cls._table_separator(source[index + 1]):
                flush_para()
                rows = [[cell.strip() for cell in stripped.strip('|').split('|')]]
                index += 2
                while index < len(source) and '|' in source[index] and source[index].strip():
                    rows.append([cell.strip() for cell in source[index].strip().strip('|').split('|')])
                    index += 1
                output.append(('table', rows))
                continue
            heading = re.match(r'^(#{1,4})\s+(.+)$', stripped)
            if heading:
                flush_para()
                output.append((f'h{len(heading.group(1))}', heading.group(2).strip()))
            else:
                bullet = re.match(r'^[-*+]\s+(.+)$', stripped)
                ordered = re.match(r'^\d+[.)]\s+(.+)$', stripped)
                quote = re.match(r'^>\s?(.+)$', stripped)
                if bullet:
                    flush_para(); output.append(('li', bullet.group(1).strip()))
                elif ordered:
                    flush_para(); output.append(('ol', ordered.group(1).strip()))
                elif quote:
                    flush_para(); output.append(('quote', quote.group(1).strip()))
                elif re.fullmatch(r'[-*_]{3,}', stripped):
                    flush_para(); output.append(('hr', ''))
                else:
                    paragraph.append(stripped)
            index += 1
        flush_para()
        if code:
            output.append(('code', '\n'.join(code)))
        return output

    @staticmethod
    def _set_cell_shading(cell: Any, color: str) -> None:
        props = cell._tc.get_or_add_tcPr()
        shading = props.find(qn('w:shd'))
        if shading is None:
            shading = OxmlElement('w:shd'); props.append(shading)
        shading.set(qn('w:fill'), color)

    @staticmethod
    def _set_cell_margins(cell: Any, top: int = 90, start: int = 100, bottom: int = 90, end: int = 100) -> None:
        props = cell._tc.get_or_add_tcPr()
        margins = props.first_child_found_in('w:tcMar')
        if margins is None:
            margins = OxmlElement('w:tcMar'); props.append(margins)
        for name, value in {'top': top, 'start': start, 'bottom': bottom, 'end': end}.items():
            node = margins.find(qn(f'w:{name}'))
            if node is None:
                node = OxmlElement(f'w:{name}'); margins.append(node)
            node.set(qn('w:w'), str(value)); node.set(qn('w:type'), 'dxa')

    @staticmethod
    def _add_page_number(paragraph: Any) -> None:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = paragraph.add_run()
        begin = OxmlElement('w:fldChar'); begin.set(qn('w:fldCharType'), 'begin')
        instruction = OxmlElement('w:instrText'); instruction.set(qn('xml:space'), 'preserve'); instruction.text = ' PAGE '
        end = OxmlElement('w:fldChar'); end.set(qn('w:fldCharType'), 'end')
        run._r.extend([begin, instruction, end])

    @staticmethod
    def _clean_inline(text: str) -> str:
        value = re.sub(r'!\[([^]]*)\]\([^)]+\)', r'\1', str(text or ''))
        value = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', value)
        return re.sub(r'[`*_~]+', '', value).strip()

    @classmethod
    def _same_title(cls, candidate: str, resolved_title: str) -> bool:
        left = re.sub(r'\s+', ' ', cls._clean_inline(candidate)).strip().casefold()
        right = re.sub(r'\s+', ' ', cls._clean_inline(resolved_title)).strip().casefold()
        if not left or not right:
            return False
        return left == right or (min(len(left), len(right)) >= 30 and (left.startswith(right) or right.startswith(left)))

    @classmethod
    def _add_docx_inline(cls, paragraph: Any, text: str) -> None:
        pattern = re.compile(
            r'(\*\*[^*]+\*\*|__[^_]+__|(?<!\*)\*[^*]+\*(?!\*)|(?<!_)_[^_]+_(?!_)|`[^`]+`|\[[^]]+\]\([^)]+\))'
        )
        cursor = 0
        for match in pattern.finditer(str(text or '')):
            if match.start() > cursor:
                paragraph.add_run(text[cursor:match.start()])
            token = match.group(0); run = paragraph.add_run()
            if token.startswith(('**', '__')):
                run.text = token[2:-2]; run.bold = True
            elif token.startswith(('*', '_')):
                run.text = token[1:-1]; run.italic = True
            elif token.startswith('`'):
                run.text = token[1:-1]; run.font.name = 'Consolas'; run.font.size = Pt(9)
            else:
                link = re.match(r'\[([^]]+)\]\(([^)]+)\)', token)
                run.text = link.group(1) if link else token
                run.font.color.rgb = DocxRGBColor(33, 88, 148); run.underline = True
            cursor = match.end()
        if cursor < len(text):
            paragraph.add_run(text[cursor:])

    @staticmethod
    def _shade_paragraph(paragraph: Any, color: str) -> None:
        shading = OxmlElement('w:shd'); shading.set(qn('w:fill'), color)
        paragraph._p.get_or_add_pPr().append(shading)

    def docx(self, markdown: str, *, profile: str | None = None, title: str | None = None) -> bytes:
        resolved_title = (title or self.title_from(markdown)).strip()[:160]
        resolved_profile = profile or self.profile_for(markdown)
        doc = Document(); section = doc.sections[0]
        if resolved_profile == 'academic':
            margins = (1.0, 1.0, 1.0, 1.0); body_font, body_size, spacing = 'Times New Roman', 12, 2.0
            display_font = 'Times New Roman'
        elif resolved_profile == 'resume':
            margins = (0.58, 0.58, 0.62, 0.62); body_font, body_size, spacing = 'Aptos', 10, 1.05
            display_font = 'Aptos Display'
        else:
            margins = (0.78, 0.78, 0.82, 0.82); body_font, body_size, spacing = 'Aptos', 10.5, 1.14
            display_font = 'Aptos Display'
        section.top_margin, section.right_margin = Inches(margins[0]), Inches(margins[1])
        section.bottom_margin, section.left_margin = Inches(margins[2]), Inches(margins[3])

        normal = doc.styles['Normal']; normal.font.name = body_font; normal.font.size = Pt(body_size)
        normal.font.color.rgb = DocxRGBColor.from_string(INK)
        normal.paragraph_format.line_spacing = spacing
        normal.paragraph_format.space_after = Pt(0 if resolved_profile == 'academic' else 6)
        normal.paragraph_format.widow_control = True
        if resolved_profile == 'academic':
            normal.paragraph_format.first_line_indent = Inches(0.5)
        sizes = {'academic': (16, 14, 12.5, 12), 'resume': (24, 12, 10.5, 10), 'business': (25, 17, 14, 12)}[
            resolved_profile if resolved_profile in {'academic', 'resume'} else 'business'
        ]
        for name, size in zip(('Title', 'Heading 1', 'Heading 2', 'Heading 3'), sizes):
            style = doc.styles[name]; style.font.name = display_font; style.font.size = Pt(size)
            style.font.bold = name != 'Title' or resolved_profile != 'academic'
            style.font.color.rgb = DocxRGBColor.from_string(INK if resolved_profile == 'academic' else NAVY)
            style.paragraph_format.keep_with_next = True; style.paragraph_format.keep_together = True
            style.paragraph_format.space_before = Pt(11 if name != 'Title' else 0)
            style.paragraph_format.space_after = Pt(5 if name != 'Title' else 10)
            style.paragraph_format.first_line_indent = Inches(0)
            if resolved_profile == 'academic':
                style_properties = style.element.get_or_add_pPr()
                inherited_border = style_properties.find(qn('w:pBdr'))
                if inherited_border is not None:
                    style_properties.remove(inherited_border)

        doc.core_properties.title = resolved_title; doc.core_properties.author = 'Ask Crump'
        doc.core_properties.subject = f'{resolved_profile.title()} document'
        doc.core_properties.keywords = 'Ask Crump, AI workspace, editable document'
        if resolved_profile == 'business':
            header = section.header.paragraphs[0]; header.text = 'ASK CRUMP  /  AI WORKSPACE'
            header.runs[0].font.size = Pt(7.5); header.runs[0].font.bold = True
            header.runs[0].font.color.rgb = DocxRGBColor.from_string(GOLD)
        if resolved_profile != 'resume':
            footer = section.footer.paragraphs[0]
            if resolved_profile == 'business':
                footer.add_run('Ask Crump  •  ')
                footer.runs[0].font.name = body_font; footer.runs[0].font.size = Pt(8)
                footer.runs[0].font.color.rgb = DocxRGBColor.from_string(MUTED)
            self._add_page_number(footer)

        title_p = doc.add_paragraph(style='Title')
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER if resolved_profile == 'academic' else WD_ALIGN_PARAGRAPH.LEFT
        title_p.paragraph_format.first_line_indent = Inches(0); self._add_docx_inline(title_p, resolved_title)
        if resolved_profile == 'business':
            borders = OxmlElement('w:pBdr'); bottom = OxmlElement('w:bottom')
            for key, value in {'val': 'single', 'sz': '10', 'space': '7', 'color': GOLD}.items():
                bottom.set(qn(f'w:{key}'), value)
            borders.append(bottom); title_p._p.get_or_add_pPr().append(borders)

        skipped = False
        for kind, content in self.blocks(markdown):
            if not skipped and kind.startswith('h') and self._same_title(str(content), resolved_title):
                skipped = True; continue
            if kind.startswith('h'):
                p = doc.add_heading('', level=min(3, max(1, int(kind[1:])))); self._add_docx_inline(p, str(content))
            elif kind in {'li', 'ol'}:
                p = doc.add_paragraph(style='List Bullet' if kind == 'li' else 'List Number')
                p.paragraph_format.first_line_indent = Inches(0); self._add_docx_inline(p, str(content))
            elif kind == 'quote':
                p = doc.add_paragraph(style='Quote'); p.paragraph_format.first_line_indent = Inches(0)
                self._add_docx_inline(p, str(content))
            elif kind == 'code':
                p = doc.add_paragraph(); p.paragraph_format.first_line_indent = Inches(0)
                p.paragraph_format.left_indent = Inches(0.18); p.paragraph_format.space_after = Pt(8)
                run = p.add_run(str(content)); run.font.name = 'Consolas'; run.font.size = Pt(8.7)
                self._shade_paragraph(p, 'F1F3F6')
            elif kind == 'hr':
                p = doc.add_paragraph(); p.paragraph_format.first_line_indent = Inches(0)
                borders = OxmlElement('w:pBdr'); bottom = OxmlElement('w:bottom')
                for key, value in {'val': 'single', 'sz': '6', 'space': '1', 'color': LINE}.items():
                    bottom.set(qn(f'w:{key}'), value)
                borders.append(bottom); p._p.get_or_add_pPr().append(borders)
            elif kind == 'table':
                rows = content
                if not rows: continue
                width = max(len(row) for row in rows); table = doc.add_table(rows=len(rows), cols=width)
                table.autofit = True; table.style = 'Table Grid'
                table.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
                for row_index, values in enumerate(rows):
                    for column_index in range(width):
                        cell = table.cell(row_index, column_index); cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                        self._set_cell_margins(cell)
                        if row_index == 0: self._set_cell_shading(cell, NAVY)
                        elif row_index % 2 == 0: self._set_cell_shading(cell, 'F5F6F8')
                        p = cell.paragraphs[0]; p.paragraph_format.first_line_indent = Inches(0); p.paragraph_format.space_after = Pt(0)
                        self._add_docx_inline(p, str(values[column_index] if column_index < len(values) else ''))
                        for run in p.runs:
                            run.font.size = Pt(9.2)
                            if row_index == 0: run.bold = True; run.font.color.rgb = DocxRGBColor(255, 255, 255)
                doc.add_paragraph().paragraph_format.space_after = Pt(0)
            elif content:
                p = doc.add_paragraph()
                if resolved_profile != 'academic': p.paragraph_format.first_line_indent = Inches(0)
                self._add_docx_inline(p, str(content))
        out = BytesIO(); doc.save(out); return out.getvalue()

    @staticmethod
    def _xml(text: str) -> str:
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    @classmethod
    def _rl_markup(cls, text: str) -> str:
        value = cls._xml(text)
        value = re.sub(r'\*\*(.+?)\*\*|__(.+?)__', lambda m: f'<b>{m.group(1) or m.group(2)}</b>', value)
        value = re.sub(r'(?<!\*)\*(.+?)\*(?!\*)|(?<!_)_(.+?)_(?!_)', lambda m: f'<i>{m.group(1) or m.group(2)}</i>', value)
        value = re.sub(r'`(.+?)`', r'<font name="Courier">\1</font>', value)
        value = re.sub(r'\[([^]]+)\]\(([^)]+)\)', r'<u>\1</u>', value)
        return value

    def pdf(self, markdown: str, *, profile: str | None = None, title: str | None = None) -> bytes:
        resolved_title = (title or self.title_from(markdown)).strip()[:160]
        resolved_profile = profile or self.profile_for(markdown); academic = resolved_profile == 'academic'
        out = BytesIO(); margin = 1.0 if academic else 0.76
        document = SimpleDocTemplate(
            out, pagesize=LETTER, leftMargin=margin * inch, rightMargin=margin * inch,
            topMargin=(0.86 if academic else 0.72) * inch, bottomMargin=(0.82 if academic else 0.7) * inch,
            title=resolved_title, author='Ask Crump', subject=f'{resolved_profile.title()} document',
        )
        sample = getSampleStyleSheet(); body_font = 'Times-Roman' if academic else 'Helvetica'
        body = ParagraphStyle(
            'CrumpBody', parent=sample['BodyText'], fontName=body_font, fontSize=12 if academic else 10.5,
            leading=24 if academic else 15, textColor=colors.HexColor(f'#{INK}'), alignment=TA_LEFT,
            spaceAfter=0 if academic else 7, firstLineIndent=0.5 * inch if academic else 0,
        )
        title_style = ParagraphStyle(
            'CrumpTitle', parent=sample['Title'], fontName='Times-Bold' if academic else 'Helvetica-Bold',
            fontSize=16 if academic else 23, leading=20 if academic else 28,
            textColor=colors.HexColor(f'#{INK if academic else NAVY}'),
            alignment=TA_CENTER if academic else TA_LEFT, spaceAfter=18,
        )
        h1 = ParagraphStyle(
            'CrumpH1', parent=sample['Heading1'], fontName='Times-Bold' if academic else 'Helvetica-Bold',
            fontSize=14 if academic else 16, leading=18 if academic else 20,
            textColor=colors.HexColor(f'#{INK if academic else NAVY}'), spaceBefore=14, spaceAfter=7, keepWithNext=True,
        )
        h2 = ParagraphStyle('CrumpH2', parent=h1, fontSize=12.5 if academic else 13.5, leading=16 if academic else 17)
        code_style = ParagraphStyle('CrumpCode', parent=body, fontName='Courier', fontSize=8.6, leading=11, backColor=colors.HexColor('#F1F3F6'), borderPadding=7, firstLineIndent=0, spaceAfter=8)
        quote_style = ParagraphStyle('CrumpQuote', parent=body, fontName='Times-Italic' if academic else 'Helvetica-Oblique', leftIndent=18, rightIndent=10, firstLineIndent=0, textColor=colors.HexColor(f'#{MUTED}'), borderColor=colors.HexColor(f'#{GOLD}'), borderWidth=1.5, borderPadding=7, spaceAfter=10)
        story: list[Any] = [Paragraph(self._rl_markup(resolved_title), title_style)]
        pending: list[ListItem] = []; pending_type = 'bullet'
        def flush_lists() -> None:
            nonlocal pending
            if pending:
                story.append(ListFlowable(pending, bulletType=pending_type, leftIndent=20, bulletFontSize=7)); story.append(Spacer(1, 5)); pending = []
        skipped = False
        for kind, content in self.blocks(markdown):
            if not skipped and kind.startswith('h') and self._same_title(str(content), resolved_title):
                skipped = True; continue
            if kind in {'li', 'ol'}:
                desired = '1' if kind == 'ol' else 'bullet'
                if pending and pending_type != desired: flush_lists()
                pending_type = desired; pending.append(ListItem(Paragraph(self._rl_markup(str(content)), body), leftIndent=10)); continue
            flush_lists()
            if kind == 'h1': story.append(Paragraph(self._rl_markup(str(content)), h1))
            elif kind in {'h2', 'h3', 'h4'}: story.append(Paragraph(self._rl_markup(str(content)), h2))
            elif kind == 'code': story.append(Paragraph(self._xml(str(content)).replace('\n', '<br/>'), code_style))
            elif kind == 'quote': story.append(Paragraph(self._rl_markup(str(content)), quote_style))
            elif kind == 'hr':
                story.extend([Spacer(1, 5), Table([['']], colWidths=[document.width], rowHeights=[1], style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(f'#{GOLD}'))])), Spacer(1, 7)])
            elif kind == 'table' and content:
                width = max(len(row) for row in content); table_rows = []
                for row in content:
                    padded = [*row, *([''] * (width - len(row)))]
                    table_rows.append([Paragraph(self._rl_markup(str(value)), body) for value in padded])
                table = Table(table_rows, colWidths=[document.width / width] * width, repeatRows=1, hAlign='LEFT')
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(f'#{NAVY}')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8.8),
                    ('LEADING', (0, 0), (-1, -1), 11), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor(f'#{LINE}')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F6F8')]),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ])); story.extend([table, Spacer(1, 10)])
            elif content: story.append(Paragraph(self._rl_markup(str(content)), body))
        flush_lists()
        def footer(canvas: Any, doc_template: Any) -> None:
            canvas.saveState(); canvas.setFont('Helvetica', 7.5); canvas.setFillColor(colors.HexColor(f'#{MUTED}'))
            label = str(canvas.getPageNumber()) if academic else f'ASK CRUMP  •  {canvas.getPageNumber()}'
            canvas.drawRightString(doc_template.pagesize[0] - doc_template.rightMargin, 0.42 * inch, label); canvas.restoreState()
        document.build(story, onFirstPage=footer, onLaterPages=footer); return out.getvalue()

    @staticmethod
    def _ppt_add_text(slide: Any, text: str, left: float, top: float, width: float, height: float, *, size: float, color: str, bold: bool = False, font: str = 'Aptos', align: Any = PP_ALIGN.LEFT) -> Any:
        box = slide.shapes.add_textbox(PptInches(left), PptInches(top), PptInches(width), PptInches(height))
        frame = box.text_frame; frame.clear(); frame.word_wrap = True
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        frame.vertical_anchor = MSO_ANCHOR.TOP; paragraph = frame.paragraphs[0]
        paragraph.text = text; paragraph.alignment = align; paragraph.font.name = font
        paragraph.font.size = PptPt(size); paragraph.font.bold = bold
        paragraph.font.color.rgb = RGBColor.from_string(color); return box

    @staticmethod
    def _ppt_background(slide: Any, color: str = INK) -> None:
        fill = slide.background.fill; fill.solid(); fill.fore_color.rgb = RGBColor.from_string(color)

    def _ppt_brand(self, slide: Any, number: int) -> None:
        rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, PptInches(0.64), PptInches(7.13), PptInches(12.02), PptInches(0.015))
        rule.fill.solid(); rule.fill.fore_color.rgb = RGBColor.from_string('66552F'); rule.line.fill.background()
        self._ppt_add_text(slide, 'ASK CRUMP', 0.66, 7.18, 2.0, 0.16, size=7.5, color=GOLD, bold=True)
        self._ppt_add_text(slide, str(number), 12.1, 7.18, 0.55, 0.16, size=7.5, color='8D93A0', align=PP_ALIGN.RIGHT)

    def pptx(self, markdown: str, *, title: str | None = None) -> bytes:
        prs = Presentation(); prs.slide_width = PptInches(13.333); prs.slide_height = PptInches(7.5)
        resolved_title = (title or self.title_from(markdown)).strip()[:160]
        prs.core_properties.title = resolved_title; prs.core_properties.author = 'Ask Crump'
        cover = prs.slides.add_slide(prs.slide_layouts[6]); self._ppt_background(cover)
        accent = cover.shapes.add_shape(MSO_SHAPE.RECTANGLE, PptInches(0.72), PptInches(0.76), PptInches(0.08), PptInches(5.65))
        accent.fill.solid(); accent.fill.fore_color.rgb = RGBColor.from_string(GOLD); accent.line.fill.background()
        self._ppt_add_text(cover, 'ASK CRUMP  /  PRESENTATION', 1.06, 0.88, 5.2, 0.25, size=9, color=GOLD, bold=True)
        title_size = 48 if len(resolved_title) <= 60 else (40 if len(resolved_title) <= 95 else 34)
        self._ppt_add_text(cover, resolved_title, 1.02, 1.55, 10.9, 2.35, size=title_size, color=CREAM, bold=True, font='Aptos Display')
        subtitle = 'Clear thinking. Structured for decisions.'
        for kind, content in self.blocks(markdown):
            if kind == 'p' and self._clean_inline(str(content)) != self._clean_inline(resolved_title):
                subtitle = self._clean_inline(str(content))[:170]; break
        self._ppt_add_text(cover, subtitle, 1.06, 4.55, 9.4, 0.85, size=18, color='B8BDC7')
        self._ppt_add_text(cover, datetime.now().strftime('%B %Y').upper(), 1.06, 6.55, 3.2, 0.2, size=8.5, color='8D93A0')
        self._ppt_brand(cover, 1)

        groups: list[tuple[str, list[Any]]] = []; current_title = 'Executive overview'; current: list[Any] = []; first_heading = False
        for kind, content in self.blocks(markdown):
            if kind.startswith('h'):
                clean = self._clean_inline(str(content))
                if not first_heading and self._same_title(clean, resolved_title):
                    first_heading = True; continue
                if current: groups.append((current_title, current))
                current_title, current, first_heading = clean, [], True
            elif kind != 'hr': current.append((kind, content))
        if current: groups.append((current_title, current))
        if not groups: groups = [('Executive overview', [('p', 'A clear, decision-ready summary.')])]

        for heading, items in groups[:18]:
            text_items: list[str] = []; table_items: list[list[list[str]]] = []
            for kind, content in items:
                if kind == 'table': table_items.append(content)
                else: text_items.append(self._clean_inline(str(content).replace('\n', ' ')))
            for start in range(0, len(text_items), 5):
                page_items = [item for item in text_items[start:start + 5] if item]
                if not page_items: continue
                slide = prs.slides.add_slide(prs.slide_layouts[6]); self._ppt_background(slide)
                self._ppt_add_text(slide, f'{len(prs.slides):02d}  /  {heading.upper()[:55]}', 0.72, 0.5, 10.8, 0.25, size=8.5, color=GOLD, bold=True)
                display = heading if start == 0 else f'{heading} — continued'
                self._ppt_add_text(slide, display, 0.72, 0.93, 11.7, 0.9, size=32, color=CREAM, bold=True, font='Aptos Display')
                y = 2.12
                for item in page_items:
                    marker = slide.shapes.add_shape(MSO_SHAPE.OVAL, PptInches(0.76), PptInches(y + 0.12), PptInches(0.11), PptInches(0.11))
                    marker.fill.solid(); marker.fill.fore_color.rgb = RGBColor.from_string(GOLD); marker.line.fill.background()
                    self._ppt_add_text(slide, item[:460], 1.08, y, 10.9, 0.72, size=18.5, color='E6E1D8'); y += 0.91
                self._ppt_brand(slide, len(prs.slides))
            for table_rows in table_items:
                if not table_rows: continue
                chunks = [table_rows[:8]]
                if len(table_rows) > 8:
                    chunks.extend([[table_rows[0], *table_rows[index:index + 7]] for index in range(8, len(table_rows), 7)])
                for chunk_index, rows in enumerate(chunks[:3]):
                    width = min(6, max(len(row) for row in rows)); slide = prs.slides.add_slide(prs.slide_layouts[6]); self._ppt_background(slide)
                    display = heading if chunk_index == 0 else f'{heading} — continued'
                    self._ppt_add_text(slide, 'DATA  /  DECISION SUPPORT', 0.72, 0.5, 6.2, 0.25, size=8.5, color=GOLD, bold=True)
                    self._ppt_add_text(slide, display, 0.72, 0.93, 11.7, 0.7, size=30, color=CREAM, bold=True, font='Aptos Display')
                    table = slide.shapes.add_table(len(rows), width, PptInches(0.72), PptInches(1.88), PptInches(11.9), PptInches(4.8)).table
                    for row_index, row in enumerate(rows):
                        for col_index in range(width):
                            cell = table.cell(row_index, col_index); cell.text = self._clean_inline(str(row[col_index] if col_index < len(row) else ''))[:160]
                            cell.fill.solid(); cell.fill.fore_color.rgb = RGBColor.from_string(NAVY if row_index == 0 else ('252A35' if row_index % 2 else '1D222C'))
                            cell.margin_left = cell.margin_right = PptInches(0.08); cell.margin_top = cell.margin_bottom = PptInches(0.05)
                            p = cell.text_frame.paragraphs[0]; p.font.name = 'Aptos'; p.font.size = PptPt(11.5); p.font.bold = row_index == 0
                            p.font.color.rgb = RGBColor.from_string(GOLD if row_index == 0 else 'E6E1D8')
                    self._ppt_brand(slide, len(prs.slides))
        out = BytesIO(); prs.save(out); return out.getvalue()

    @staticmethod
    def _safe_sheet_name(value: str, fallback: str) -> str:
        name = re.sub(r'[\\/*?:\[\]]+', ' ', str(value or '')).strip(); name = re.sub(r'\s+', ' ', name)[:31]
        return name or fallback

    @staticmethod
    def _safe_table_name(value: str, index: int) -> str:
        stem = re.sub(r'[^A-Za-z0-9_]+', '_', str(value or '')).strip('_')
        if not stem or stem[0].isdigit(): stem = f'Table_{stem}'
        return f'{stem[:200]}_{index}'

    @staticmethod
    def _safe_formula(value: str) -> bool:
        formula = str(value or '').strip()
        if not formula.startswith('=') or len(formula) > 500: return False
        if re.search(r"\b(HYPERLINK|WEBSERVICE|FILTERXML|RTD|DDE|CALL|REGISTER)\s*\(", formula, re.I): return False
        if re.search(r"https?://|file:|cmd\||powershell|\[[^]]+\]|'[^']+'!", formula, re.I): return False
        return bool(re.fullmatch(r"=[A-Za-z0-9_.$!(),:+\-*/^%<>=\s\"]+", formula))

    @classmethod
    def _typed_cell(cls, value: Any) -> tuple[Any, str | None]:
        raw = str(value or '').strip()
        if not raw: return '', None
        if raw.startswith('='): return (raw, None) if cls._safe_formula(raw) else (f"'{raw}", None)
        if re.fullmatch(r'\(?\$\s*[-+]?\d[\d,]*(?:\.\d+)?\)?', raw):
            negative = raw.startswith('(') and raw.endswith(')'); number = float(re.sub(r'[$,()\s]', '', raw))
            return (-number if negative else number), '$#,##0.00;[Red]-$#,##0.00'
        if re.fullmatch(r'[-+]?\d[\d,]*(?:\.\d+)?%', raw): return float(raw.replace(',', '').replace('%', '')) / 100, '0.0%'
        if re.fullmatch(r'[-+]?\d[\d,]*', raw): return int(raw.replace(',', '')), '#,##0'
        if re.fullmatch(r'[-+]?\d[\d,]*\.\d+', raw): return float(raw.replace(',', '')), '#,##0.00'
        for date_format in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
            try: return datetime.strptime(raw, date_format), 'mmm d, yyyy'
            except ValueError: continue
        return cls._clean_inline(raw), None

    @classmethod
    def _tables_with_titles(cls, markdown: str) -> list[tuple[str, list[list[str]]]]:
        output: list[tuple[str, list[list[str]]]] = []; heading = 'Data'
        for kind, content in cls.blocks(markdown):
            if kind.startswith('h'): heading = cls._clean_inline(str(content))
            elif kind == 'table': output.append((heading, content))
        return output

    @classmethod
    def _markdown_tables(cls, lines: list[str]) -> list[list[list[str]]]:
        return [table for _, table in cls._tables_with_titles('\n'.join(lines))]

    def _style_xlsx_sheet(self, sheet: Any) -> None:
        sheet.sheet_view.showGridLines = False; sheet.freeze_panes = 'A2'; sheet.print_title_rows = '1:1'
        sheet.sheet_properties.pageSetUpPr.fitToPage = True; sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.fitToWidth = 1; sheet.page_setup.fitToHeight = 0
        sheet.print_area = sheet.dimensions
        sheet.page_margins.left = sheet.page_margins.right = 0.35
        sheet.page_margins.top = sheet.page_margins.bottom = 0.5
        sheet.oddFooter.center.text = 'ASK CRUMP  •  &[Page] of &[Pages]'; sheet.oddFooter.center.size = 8; sheet.oddFooter.center.color = MUTED
        thin = Side(style='thin', color=LINE)
        for cell in sheet[1]:
            cell.fill = PatternFill('solid', fgColor=NAVY); cell.font = Font(name='Aptos Display', size=10, bold=True, color='FFFFFF')
            cell.alignment = Alignment(vertical='center', wrap_text=True); cell.border = Border(bottom=Side(style='medium', color=GOLD))
        sheet.row_dimensions[1].height = 28
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.font = Font(name='Aptos', size=10, color=INK); cell.alignment = Alignment(vertical='top', wrap_text=True)
                cell.border = Border(bottom=thin)
        for column in sheet.columns:
            letter = column[0].column_letter; values = [len(str(cell.value or '')) for cell in column[:100]]
            sheet.column_dimensions[letter].width = min(42, max(11, max(values, default=8) + 2))
        sheet.sheet_properties.tabColor = GOLD

    @staticmethod
    def _header_number_format(header: str) -> str | None:
        label = str(header or '').strip().casefold()
        if re.search(r'\b(mrr|arr|revenue|price|cost|budget|spend|income|amount|cash|sales|profit)\b', label):
            return '$#,##0.00;[Red]-$#,##0.00'
        if re.search(r'\b(rate|growth|conversion|churn|margin|percentage|percent)\b|%', label):
            return '0.0%'
        if re.search(r'\b(users?|customers?|leads?|count|quantity|units?|months?)\b', label):
            return '#,##0'
        return None

    def xlsx(self, markdown: str, *, title: str | None = None) -> bytes:
        resolved_title = (title or self.title_from(markdown)).strip()[:160]
        workbook = Workbook(); overview = workbook.active; overview.title = 'Overview'; overview.sheet_view.showGridLines = False
        overview.sheet_properties.tabColor = GOLD; overview.merge_cells('A1:F2'); overview['A1'] = resolved_title
        overview['A1'].font = Font(name='Aptos Display', size=22, bold=True, color='FFFFFF'); overview['A1'].fill = PatternFill('solid', fgColor=NAVY)
        overview['A1'].alignment = Alignment(vertical='center'); overview['A4'] = 'ASK CRUMP / EDITABLE WORKBOOK'
        overview['A4'].font = Font(name='Aptos', size=8, bold=True, color=GOLD); overview['A6'] = 'Workbook guide'
        overview['A6'].font = Font(name='Aptos Display', size=14, bold=True, color=INK)
        overview['A7'] = 'Each structured table is placed on its own filterable sheet. Inputs, formulas, dates, currencies, and percentages remain editable.'
        overview['A7'].alignment = Alignment(wrap_text=True, vertical='top'); overview['A7'].font = Font(name='Aptos', size=10, color=MUTED)
        overview.column_dimensions['A'].width = 74; overview.row_dimensions[7].height = 42
        overview.sheet_properties.pageSetUpPr.fitToPage = True; overview.page_setup.orientation = 'portrait'
        overview.page_setup.fitToWidth = 1; overview.page_setup.fitToHeight = 1
        overview.print_area = 'A1:F15'; overview.page_margins.left = overview.page_margins.right = 0.45
        overview.page_margins.top = overview.page_margins.bottom = 0.55

        tables = self._tables_with_titles(markdown)
        if tables:
            used_names = {'overview'}
            for index, (heading, rows) in enumerate(tables, start=1):
                base = self._safe_sheet_name(heading, f'Data {index}'); name = base; suffix = 2
                while name.casefold() in used_names:
                    tail = f' {suffix}'; name = f'{base[:31 - len(tail)]}{tail}'; suffix += 1
                used_names.add(name.casefold()); sheet = workbook.create_sheet(name); width = max(len(row) for row in rows)
                headers = [self._clean_inline(str(rows[0][column] if column < len(rows[0]) else f'Column {column + 1}')) or f'Column {column + 1}' for column in range(width)]
                seen: dict[str, int] = {}
                for column, header in enumerate(headers):
                    key = header.casefold(); seen[key] = seen.get(key, 0) + 1
                    if seen[key] > 1: headers[column] = f'{header} {seen[key]}'
                sheet.append(headers)
                for row in rows[1:]:
                    typed = []; formats: dict[int, str] = {}
                    for column in range(width):
                        value, number_format = self._typed_cell(row[column] if column < len(row) else '')
                        typed.append(value)
                        if number_format: formats[column + 1] = number_format
                    sheet.append(typed)
                    for column, number_format in formats.items():
                        sheet.cell(sheet.max_row, column).number_format = number_format
                self._style_xlsx_sheet(sheet)
                for column, header in enumerate(headers, start=1):
                    inferred_format = self._header_number_format(header)
                    if not inferred_format:
                        continue
                    for row_index in range(2, sheet.max_row + 1):
                        cell = sheet.cell(row_index, column)
                        if cell.number_format == 'General' and (
                            isinstance(cell.value, (int, float)) or str(cell.value or '').startswith('=')
                        ):
                            cell.number_format = inferred_format
                if sheet.max_row >= 2:
                    table = XlsxTable(displayName=self._safe_table_name(name, index), ref=sheet.dimensions)
                    table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
                    sheet.add_table(table)
                    for column in range(1, sheet.max_column + 1):
                        numeric = [sheet.cell(row, column).value for row in range(2, sheet.max_row + 1)]
                        if sum(isinstance(value, (int, float)) for value in numeric) >= 3:
                            letter = sheet.cell(1, column).column_letter
                            sheet.conditional_formatting.add(f'{letter}2:{letter}{sheet.max_row}', DataBarRule(start_type='min', end_type='max', color=GOLD, showValue=True))
                overview.cell(9 + index, 1, name); overview.cell(9 + index, 2, f'{max(0, len(rows) - 1)} rows')
                overview.cell(9 + index, 1).hyperlink = f"#'{name}'!A1"; overview.cell(9 + index, 1).style = 'Hyperlink'
        else:
            sheet = workbook.create_sheet('Brief'); sheet.sheet_view.showGridLines = False
            sheet.column_dimensions['A'].width = 24; sheet.column_dimensions['B'].width = 82; row = 1
            for kind, content in self.blocks(markdown):
                if kind.startswith('h'):
                    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2); cell = sheet.cell(row, 1, self._clean_inline(str(content)))
                    cell.fill = PatternFill('solid', fgColor=NAVY if row == 1 else 'EDEFF3'); cell.font = Font(name='Aptos Display', size=16 if row == 1 else 12, bold=True, color='FFFFFF' if row == 1 else INK)
                    cell.alignment = Alignment(vertical='center', wrap_text=True); sheet.row_dimensions[row].height = 30
                elif kind != 'table':
                    sheet.cell(row, 1, kind.upper()); sheet.cell(row, 1).font = Font(name='Aptos', size=8, bold=True, color=GOLD)
                    sheet.cell(row, 2, self._clean_inline(str(content))); sheet.cell(row, 2).font = Font(name='Aptos', size=10, color=INK)
                    sheet.cell(row, 2).alignment = Alignment(wrap_text=True, vertical='top'); sheet.row_dimensions[row].height = max(24, min(90, 15 * (1 + len(str(content)) // 90)))
                row += 1
            sheet.freeze_panes = 'A2'; sheet.sheet_properties.tabColor = GOLD
        workbook.calculation.calcMode = 'auto'; workbook.calculation.fullCalcOnLoad = True; workbook.calculation.forceFullCalc = True
        workbook.properties.title = resolved_title; workbook.properties.creator = 'Ask Crump'; workbook.properties.subject = 'Editable Ask Crump workbook'
        out = BytesIO(); workbook.save(out); return out.getvalue()

    async def create(self, *, user_id: str, markdown: str, format_name: str, chat_id: str | None, message_id: str | None, title: str | None = None, brief: str | None = None) -> dict[str, Any]:
        fmt = self.normalize_format(format_name)
        if not fmt: raise ValueError('Unsupported document format.')
        resolved_title = (title or self.title_from(markdown)).strip()[:160]; profile = self.profile_for(markdown, brief or '', fmt)
        stem = self.safe_stem(resolved_title)
        if fmt == 'docx': data = self.docx(markdown, profile=profile, title=resolved_title)
        elif fmt == 'pdf': data = self.pdf(markdown, profile=profile, title=resolved_title)
        elif fmt == 'pptx': data = self.pptx(markdown, title=resolved_title)
        elif fmt == 'xlsx': data = self.xlsx(markdown, title=resolved_title)
        elif fmt == 'md': data = markdown.encode('utf-8')
        else: data = self._clean_inline(markdown).encode('utf-8')
        row = await self.files.store_bytes(
            user_id=user_id, data=data, filename=f'{stem}.{fmt}', mime_type=MIME[fmt],
            kind='generated_document', chat_id=chat_id, message_id=message_id,
            metadata={'format': fmt, 'title': resolved_title, 'profile': profile},
        )
        result = self.files.public_file(row); result.update({'format': fmt, 'title': resolved_title, 'profile': profile}); return result
