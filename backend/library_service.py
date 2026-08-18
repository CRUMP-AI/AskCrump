"""Ask Crump 5.7 book library and external manuscript import."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
import re
from typing import Any
from uuid import uuid4
import xml.etree.ElementTree as ET
import zipfile

from docx import Document
from pypdf import PdfReader

from .db import SupabaseDB, eq, in_
from .file_service import FileService, FileServiceError
from .manuscript_service import ManuscriptService, ManuscriptError, word_count
from .project_service import ProjectService, ProjectNotFoundError
from .security import normalize_chat_id


MAX_IMPORTED_TEXT_CHARS = 2_500_000
MAX_IMPORTED_WORDS = 350_000
MAX_SECTION_CHARS = 200_000

SUPPORTED_SOURCE_MIME = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
    "application/epub+zip",
    "text/plain",
    "text/markdown",
}
SUPPORTED_SOURCE_EXTENSIONS = {".docx", ".pdf", ".epub", ".txt", ".md"}

HEADING_RE = re.compile(
    r"^(?:"
    r"prologue|epilogue|preface|introduction|afterword|acknowledg(?:e)?ments?|"
    r"chapter(?:\s+(?:\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty))?"
    r"(?:\s*[:.\-–—]\s*.+)?|"
    r"part\s+(?:\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"(?:\s*[:.\-–—]\s*.+)?"
    r")$",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _extension(name: str) -> str:
    lowered = str(name or "").lower()
    for ext in sorted(SUPPORTED_SOURCE_EXTENSIONS, key=len, reverse=True):
        if lowered.endswith(ext):
            return ext
    return ""


def _filename_title(name: str) -> str:
    raw = str(name or "Untitled Manuscript").replace("\\", "/").split("/")[-1]
    ext = _extension(raw)
    if ext:
        raw = raw[: -len(ext)]
    raw = re.sub(r"[_\-]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:180] or "Untitled Manuscript"


def _summary(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    return normalized[:600]


def _section_type(title: str) -> str:
    lowered = str(title or "").lower()
    if lowered in {"prologue", "preface", "introduction"}:
        return "frontmatter"
    if lowered in {"epilogue", "afterword", "acknowledgment", "acknowledgments", "acknowledgement", "acknowledgements"}:
        return "backmatter"
    return "chapter"


def _looks_like_heading(value: str) -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or len(text) > 180:
        return False
    return bool(HEADING_RE.fullmatch(text))


def _chunk_plain_text(text: str, prefix: str = "Part") -> list[tuple[str, str]]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", str(text or "")) if part.strip()]
    if not paragraphs:
        return []

    chunks: list[tuple[str, str]] = []
    current: list[str] = []
    current_chars = 0
    index = 1

    for paragraph in paragraphs:
        # One enormous paragraph is split deterministically rather than silently truncated.
        pieces = [
            paragraph[offset : offset + MAX_SECTION_CHARS]
            for offset in range(0, len(paragraph), MAX_SECTION_CHARS)
        ] or [paragraph]
        for piece in pieces:
            addition = len(piece) + (2 if current else 0)
            if current and current_chars + addition > MAX_SECTION_CHARS:
                chunks.append((f"{prefix} {index}", "\n\n".join(current).strip()))
                index += 1
                current = []
                current_chars = 0
            current.append(piece)
            current_chars += len(piece) + (2 if len(current) > 1 else 0)

    if current:
        chunks.append((f"{prefix} {index}", "\n\n".join(current).strip()))
    return chunks


def _split_by_heading_lines(text: str) -> list[tuple[str, str]]:
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heading_indexes: list[int] = []

    for index, line in enumerate(lines):
        if _looks_like_heading(line):
            heading_indexes.append(index)

    if not heading_indexes:
        return _chunk_plain_text(text)

    sections: list[tuple[str, str]] = []
    preface = "\n".join(lines[: heading_indexes[0]]).strip()
    if preface:
        sections.extend(_chunk_plain_text(preface, "Opening"))

    for position, heading_index in enumerate(heading_indexes):
        next_index = heading_indexes[position + 1] if position + 1 < len(heading_indexes) else len(lines)
        title = re.sub(r"\s+", " ", lines[heading_index]).strip()[:180] or f"Section {position + 1}"
        body = "\n".join(lines[heading_index + 1 : next_index]).strip()
        if len(body) <= MAX_SECTION_CHARS:
            sections.append((title, body))
        else:
            chunks = _chunk_plain_text(body, title)
            for chunk_index, (_, chunk_body) in enumerate(chunks, start=1):
                chunk_title = title if chunk_index == 1 else f"{title} — Part {chunk_index}"
                sections.append((chunk_title[:180], chunk_body))
    return sections


class _HTMLText(HTMLParser):
    BLOCKS = {
        "p", "div", "section", "article", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote", "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        value = "".join(self.parts)
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n[ \t]+", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_docx(data: bytes) -> tuple[str, list[tuple[str, str]]]:
    document = Document(BytesIO(data))
    suggested = _clean(document.core_properties.title, 180)
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_body: list[str] = []
    saw_heading = False
    leading: list[str] = []

    def flush() -> None:
        nonlocal current_body
        if not current_title:
            return
        body = "\n\n".join(current_body).strip()
        if len(body) <= MAX_SECTION_CHARS:
            sections.append((current_title[:180], body))
        else:
            chunks = _chunk_plain_text(body, current_title)
            for chunk_index, (_, chunk_body) in enumerate(chunks, start=1):
                title = current_title if chunk_index == 1 else f"{current_title} — Part {chunk_index}"
                sections.append((title[:180], chunk_body))
        current_body = []

    for paragraph in document.paragraphs:
        text = str(paragraph.text or "").strip()
        if not text:
            if current_title and current_body and current_body[-1] != "":
                current_body.append("")
            continue
        style_name = str(getattr(paragraph.style, "name", "") or "").lower()
        is_heading = style_name.startswith("heading") or _looks_like_heading(text)
        if is_heading:
            saw_heading = True
            if current_title:
                flush()
            elif leading:
                lead_text = "\n\n".join(leading).strip()
                sections.extend(_chunk_plain_text(lead_text, "Opening"))
                leading = []
            current_title = text[:180]
        elif current_title:
            current_body.append(text)
        else:
            leading.append(text)

    if current_title:
        flush()

    if not saw_heading:
        text = "\n\n".join(leading).strip()
        sections = _split_by_heading_lines(text)
    elif leading:
        sections = _chunk_plain_text("\n\n".join(leading).strip(), "Opening") + sections

    return suggested, sections


def _parse_pdf(data: bytes) -> tuple[str, list[tuple[str, str]]]:
    reader = PdfReader(BytesIO(data))
    suggested = ""
    try:
        metadata = reader.metadata or {}
        suggested = _clean(getattr(metadata, "title", "") or metadata.get("/Title"), 180)
    except Exception:
        suggested = ""

    pages: list[str] = []
    for page in reader.pages:
        extracted = str(page.extract_text() or "").strip()
        if extracted:
            pages.append(extracted)
    return suggested, _split_by_heading_lines("\n\n".join(pages))


def _parse_epub(data: bytes) -> tuple[str, list[tuple[str, str]]]:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        names = set(archive.namelist())
        opf_path = ""

        if "META-INF/container.xml" in names:
            container_root = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container_root.find(".//{*}rootfile")
            if rootfile is not None:
                opf_path = str(rootfile.attrib.get("full-path") or "")

        if not opf_path:
            opf_path = next((name for name in names if name.lower().endswith(".opf")), "")

        if not opf_path or opf_path not in names:
            raise ValueError("EPUB package metadata could not be found.")

        opf_root = ET.fromstring(archive.read(opf_path))
        title_node = opf_root.find(".//{*}title")
        suggested = _clean(title_node.text if title_node is not None else "", 180)

        manifest: dict[str, tuple[str, str]] = {}
        for item in opf_root.findall(".//{*}manifest/{*}item"):
            item_id = str(item.attrib.get("id") or "")
            href = str(item.attrib.get("href") or "")
            media_type = str(item.attrib.get("media-type") or "")
            if item_id and href:
                manifest[item_id] = (href, media_type)

        spine_ids = [
            str(item.attrib.get("idref") or "")
            for item in opf_root.findall(".//{*}spine/{*}itemref")
            if item.attrib.get("idref")
        ]

        base = PurePosixPath(opf_path).parent
        documents: list[str] = []
        for item_id in spine_ids:
            href, media_type = manifest.get(item_id, ("", ""))
            if not href or media_type not in {"application/xhtml+xml", "text/html"}:
                continue
            path = str(base / href).replace("\\", "/")
            # Drop fragment identifiers if present.
            path = path.split("#", 1)[0]
            if path not in names:
                continue
            parser = _HTMLText()
            parser.feed(_decode_text(archive.read(path)))
            text = parser.text()
            if text:
                documents.append(text)

        if not documents:
            for name in sorted(names):
                if not name.lower().endswith((".xhtml", ".html", ".htm")):
                    continue
                parser = _HTMLText()
                parser.feed(_decode_text(archive.read(name)))
                text = parser.text()
                if text:
                    documents.append(text)

        return suggested, _split_by_heading_lines("\n\n".join(documents))


@dataclass(slots=True)
class LibraryError(RuntimeError):
    message: str
    code: str = "LIBRARY_ERROR"
    status_code: int = 400

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


class LibraryService:
    def __init__(
        self,
        db: SupabaseDB,
        files: FileService,
        manuscripts: ManuscriptService,
        projects: ProjectService,
    ) -> None:
        self.db = db
        self.files = files
        self.manuscripts = manuscripts
        self.projects = projects

    async def _asset_rows(self, user_id: str, manuscript_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        ids: list[str] = []
        for row in manuscript_rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            for key in ("sourceFileId", "frontCoverFileId", "backCoverFileId"):
                value = str(metadata.get(key) or "").strip()
                if value and value not in ids:
                    ids.append(value)
        if not ids:
            return {}
        rows = await self.db.select(
            "user_files",
            filters={
                "id": in_(ids),
                "user_id": eq(user_id),
                "status": eq("ready"),
                "deleted_at": "is.null",
            },
            limit=min(1000, max(1, len(ids))),
        )
        return {str(row.get("id")): row for row in rows if row.get("id")}

    async def list_books(self, *, user_id: str, deleted: bool = False) -> list[dict[str, Any]]:
        rows = await self.db.select(
            "manuscripts",
            filters={"user_id": eq(user_id), "archived_at": "not.is.null" if deleted else "is.null"},
            order="updated_at.desc",
            limit=250,
        )
        if not rows:
            return []

        projects = {str(row.get("id")): row for row in await self.projects.list(user_id)}
        assets = await self._asset_rows(user_id, rows)
        manuscript_ids = [str(row["id"]) for row in rows if row.get("id")]
        section_rows = await self.db.select(
            "manuscript_sections",
            columns="manuscript_id,word_count,status",
            filters={"user_id": eq(user_id), "manuscript_id": in_(manuscript_ids)},
            limit=10000,
        )

        progress: dict[str, dict[str, int]] = {}
        for section in section_rows:
            manuscript_id = str(section.get("manuscript_id") or "")
            bucket = progress.setdefault(
                manuscript_id,
                {"wordCount": 0, "sectionCount": 0, "finalSections": 0},
            )
            bucket["wordCount"] += int(section.get("word_count") or 0)
            bucket["sectionCount"] += 1
            if str(section.get("status") or "") == "final":
                bucket["finalSections"] += 1

        output: list[dict[str, Any]] = []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            trash = metadata.get("libraryTrash") if isinstance(metadata.get("libraryTrash"), dict) else {}
            project = projects.get(str(row.get("project_id") or ""), {})
            book_progress = progress.get(
                str(row.get("id") or ""),
                {"wordCount": 0, "sectionCount": 0, "finalSections": 0},
            )

            def public_asset(key: str) -> dict[str, Any] | None:
                file_id = str(metadata.get(key) or "")
                asset = assets.get(file_id)
                return self.files.public_file(asset) if asset else None

            output.append(
                {
                    "id": row.get("id"),
                    "projectId": row.get("project_id"),
                    "projectName": project.get("name") or "",
                    "title": row.get("title") or "Untitled manuscript",
                    "subtitle": row.get("subtitle") or "",
                    "authorName": row.get("author_name") or "",
                    "status": row.get("status") or "draft",
                    "trimCode": row.get("trim_code") or "6x9",
                    "origin": metadata.get("origin") or "created",
                    "importFormat": metadata.get("importFormat") or "",
                    "importedAt": metadata.get("importedAt"),
                    "sourceFile": public_asset("sourceFileId"),
                    "frontCover": public_asset("frontCoverFileId"),
                    "backCover": public_asset("backCoverFileId"),
                    "wordCount": book_progress["wordCount"],
                    "sectionCount": book_progress["sectionCount"],
                    "finalSections": book_progress["finalSections"],
                    "createdAt": row.get("created_at"),
                    "updatedAt": row.get("updated_at"),
                    "trashedAt": row.get("archived_at"),
                    "sourceDeleted": bool(trash.get("sourceDeleted")),
                }
            )
        return output

    async def _validate_source(self, *, user_id: str, file_id: str) -> dict[str, Any]:
        try:
            row = await self.files.get_owned(user_id=user_id, file_id=file_id)
        except FileServiceError as exc:
            raise LibraryError("The manuscript source file could not be found.", "SOURCE_FILE_NOT_FOUND", 404) from exc
        mime = str(row.get("mime_type") or "").lower()
        ext = _extension(str(row.get("file_name") or ""))
        if mime not in SUPPORTED_SOURCE_MIME and ext not in SUPPORTED_SOURCE_EXTENSIONS:
            raise LibraryError(
                "Import a DOCX, PDF, EPUB, TXT, or Markdown manuscript.",
                "UNSUPPORTED_MANUSCRIPT_FORMAT",
                415,
            )
        return row

    async def _validate_cover(
        self,
        *,
        user_id: str,
        file_id: str | None,
        label: str,
    ) -> dict[str, Any] | None:
        value = str(file_id or "").strip()
        if not value:
            return None
        try:
            row = await self.files.get_owned(user_id=user_id, file_id=value)
        except FileServiceError as exc:
            raise LibraryError(f"The {label} cover image could not be found.", "COVER_FILE_NOT_FOUND", 404) from exc
        if not str(row.get("mime_type") or "").lower().startswith("image/"):
            raise LibraryError(f"The {label} cover must be an image.", "INVALID_COVER_FILE", 415)
        return row

    def _parse_source(self, row: dict[str, Any], data: bytes) -> tuple[str, list[tuple[str, str]]]:
        mime = str(row.get("mime_type") or "").lower()
        name = str(row.get("file_name") or "")
        ext = _extension(name)

        try:
            if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or ext == ".docx":
                suggested, sections = _parse_docx(data)
            elif mime == "application/pdf" or ext == ".pdf":
                suggested, sections = _parse_pdf(data)
            elif mime == "application/epub+zip" or ext == ".epub":
                suggested, sections = _parse_epub(data)
            else:
                suggested = ""
                sections = _split_by_heading_lines(_decode_text(data))
        except LibraryError:
            raise
        except Exception as exc:
            raise LibraryError(
                "Crump could not read that manuscript. Try DOCX, PDF, EPUB, TXT, or Markdown.",
                "MANUSCRIPT_PARSE_FAILED",
                422,
            ) from exc

        normalized: list[tuple[str, str]] = []
        total_chars = 0
        total_words = 0
        for index, (title, content) in enumerate(sections, start=1):
            clean_title = _clean(title, 180) or f"Section {index}"
            text = str(content or "").strip()
            if not text and len(sections) == 1:
                continue
            if len(text) > MAX_SECTION_CHARS:
                raise LibraryError("An imported section is too large to store safely.", "SECTION_TOO_LARGE", 413)
            total_chars += len(text)
            total_words += word_count(text)
            normalized.append((clean_title, text))

        if not normalized or total_words <= 0:
            raise LibraryError(
                "No readable manuscript text was found in that file.",
                "MANUSCRIPT_TEXT_EMPTY",
                422,
            )
        if total_chars > MAX_IMPORTED_TEXT_CHARS or total_words > MAX_IMPORTED_WORDS:
            raise LibraryError(
                "That manuscript is larger than the current Library import limit.",
                "MANUSCRIPT_TOO_LARGE",
                413,
            )
        return suggested or _filename_title(name), normalized

    async def import_book(
        self,
        *,
        user_id: str,
        source_file_id: str,
        title: str = "",
        subtitle: str = "",
        author_name: str = "",
        project_id: str | None = None,
        front_cover_file_id: str | None = None,
        back_cover_file_id: str | None = None,
    ) -> dict[str, Any]:
        source = await self._validate_source(user_id=user_id, file_id=source_file_id)
        front = await self._validate_cover(user_id=user_id, file_id=front_cover_file_id, label="front")
        back = await self._validate_cover(user_id=user_id, file_id=back_cover_file_id, label="back")

        try:
            data = await self.files.download_bytes(row=source, max_bytes=50 * 1024 * 1024)
        except FileServiceError as exc:
            raise LibraryError("Crump could not read the uploaded manuscript yet.", "SOURCE_READ_FAILED", 503) from exc

        suggested_title, parsed_sections = self._parse_source(source, data)
        resolved_title = _clean(title, 180) or suggested_title
        resolved_title = resolved_title or _filename_title(str(source.get("file_name") or ""))

        project_created = False
        project: dict[str, Any]
        if project_id:
            try:
                project = await self.projects.get(user_id, project_id)
            except ProjectNotFoundError as exc:
                raise LibraryError("The selected Project could not be found.", "PROJECT_NOT_FOUND", 404) from exc
        else:
            project = await self.projects.create(
                user_id=user_id,
                name=resolved_title[:100],
                description="Book workspace created by Ask Crump Library import.",
                instructions="Preserve the author's manuscript canon and original source unless the user explicitly asks for changes.",
            )
            project_created = True

        total_words = sum(word_count(content) for _, content in parsed_sections)
        metadata = {
            "origin": "imported",
            "sourceFileId": str(source["id"]),
            "frontCoverFileId": str(front["id"]) if front else None,
            "backCoverFileId": str(back["id"]) if back else None,
            "sourceFileName": source.get("file_name") or "",
            "importFormat": _extension(str(source.get("file_name") or "")).lstrip(".")
            or str(source.get("mime_type") or ""),
            "importedAt": _now(),
            "importedWordCount": total_words,
            "targetWords": max(20_000, min(150_000, total_words)),
            "premise": "",
        }

        manuscript: dict[str, Any] | None = None
        try:
            manuscript = await self.manuscripts.create(
                user_id=user_id,
                project_id=str(project["id"]),
                title=resolved_title,
                subtitle=_clean(subtitle, 240),
                author_name=_clean(author_name, 160),
                metadata=metadata,
            )

            section_rows: list[dict[str, Any]] = []
            for position, (section_title, content) in enumerate(parsed_sections, start=1):
                section_rows.append(
                    {
                        "id": str(uuid4()),
                        "user_id": user_id,
                        "manuscript_id": manuscript["id"],
                        "section_type": _section_type(section_title),
                        "title": section_title,
                        "position": position,
                        "content": content,
                        "summary": _summary(content),
                        "word_count": word_count(content),
                        "status": "draft",
                        "updated_at": _now(),
                    }
                )
            await self.db.insert("manuscript_sections", section_rows)

            await self.projects.attach_file(
                user_id=user_id,
                project_id=str(project["id"]),
                file_id=str(source["id"]),
                role="manuscript_source",
            )
            if front:
                await self.projects.attach_file(
                    user_id=user_id,
                    project_id=str(project["id"]),
                    file_id=str(front["id"]),
                    role="front_cover",
                )
            if back:
                await self.projects.attach_file(
                    user_id=user_id,
                    project_id=str(project["id"]),
                    file_id=str(back["id"]),
                    role="back_cover",
                )
        except (LibraryError, ManuscriptError):
            if manuscript:
                await self.db.delete(
                    "manuscripts",
                    filters={"id": eq(manuscript["id"]), "user_id": eq(user_id)},
                )
            if project_created:
                await self.projects.archive(user_id, str(project["id"]))
            raise
        except Exception as exc:
            if manuscript:
                try:
                    await self.db.delete(
                        "manuscripts",
                        filters={"id": eq(manuscript["id"]), "user_id": eq(user_id)},
                    )
                except Exception:
                    pass
            if project_created:
                try:
                    await self.projects.archive(user_id, str(project["id"]))
                except Exception:
                    pass
            raise LibraryError("The manuscript import could not be completed.", "MANUSCRIPT_IMPORT_FAILED", 503) from exc

        books = await self.list_books(user_id=user_id)
        created = next((item for item in books if str(item.get("id")) == str(manuscript["id"])), None)
        if not created:
            raise LibraryError("The imported book could not be reloaded.", "MANUSCRIPT_RELOAD_FAILED", 503)
        return created

    async def update_book(
        self,
        *,
        user_id: str,
        manuscript_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            manuscript = await self.manuscripts.get(user_id=user_id, manuscript_id=manuscript_id)
        except ManuscriptError as exc:
            raise LibraryError(exc.message, exc.code, exc.status_code) from exc

        updates: dict[str, Any] = {"updated_at": _now()}
        metadata = manuscript.get("metadata") if isinstance(manuscript.get("metadata"), dict) else {}
        metadata = dict(metadata)

        if "title" in changes:
            title = _clean(changes.get("title"), 180)
            if not title:
                raise LibraryError("A book title is required.", "TITLE_REQUIRED")
            updates["title"] = title
        if "subtitle" in changes:
            updates["subtitle"] = _clean(changes.get("subtitle"), 240)
        if "authorName" in changes:
            updates["author_name"] = _clean(changes.get("authorName"), 160)
        if "status" in changes:
            status = str(changes.get("status") or "").strip().lower()
            if status not in {"draft", "revising", "final"}:
                raise LibraryError("Choose draft, revising, or final.", "INVALID_STATUS")
            updates["status"] = status

        for payload_key, metadata_key, label in (
            ("frontCoverFileId", "frontCoverFileId", "front"),
            ("backCoverFileId", "backCoverFileId", "back"),
        ):
            if payload_key not in changes:
                continue
            incoming = str(changes.get(payload_key) or "").strip()
            if incoming:
                cover = await self._validate_cover(user_id=user_id, file_id=incoming, label=label)
                metadata[metadata_key] = str(cover["id"])
                await self.projects.attach_file(
                    user_id=user_id,
                    project_id=str(manuscript["project_id"]),
                    file_id=str(cover["id"]),
                    role=f"{label}_cover",
                )
            else:
                metadata[metadata_key] = None

        updates["metadata"] = metadata
        result = await self.db.update(
            "manuscripts",
            updates,
            filters={"id": eq(manuscript["id"]), "user_id": eq(user_id)},
        )
        if not result:
            raise LibraryError("The book could not be updated.", "BOOK_UPDATE_FAILED", 503)

        books = await self.list_books(user_id=user_id)
        item = next((book for book in books if str(book.get("id")) == str(manuscript["id"])), None)
        if not item:
            raise LibraryError("The updated book could not be reloaded.", "BOOK_RELOAD_FAILED", 503)
        return item

    async def _get_book_any(self, *, user_id: str, manuscript_id: str) -> dict[str, Any]:
        try:
            normalized = normalize_chat_id(manuscript_id)
        except Exception as exc:
            raise LibraryError("Book not found.", "BOOK_NOT_FOUND", 404) from exc
        row = await self.db.select_one(
            "manuscripts",
            filters={"id": eq(normalized), "user_id": eq(user_id)},
        )
        if not row:
            raise LibraryError("Book not found.", "BOOK_NOT_FOUND", 404)
        return row

    async def _active_run_exists(self, *, user_id: str, manuscript_id: str) -> bool:
        row = await self.db.select_one(
            "manuscript_runs",
            columns="id,status",
            filters={
                "user_id": eq(user_id),
                "manuscript_id": eq(manuscript_id),
                "status": in_(["queued", "running", "paused", "awaiting_credits"]),
            },
        )
        return bool(row)

    async def _source_is_referenced_elsewhere(
        self,
        *,
        user_id: str,
        manuscript_id: str,
        source_file_id: str,
    ) -> bool:
        if not source_file_id:
            return False
        rows = await self.db.select(
            "manuscripts",
            columns="id,metadata",
            filters={"user_id": eq(user_id)},
            limit=500,
        )
        for row in rows:
            if str(row.get("id") or "") == str(manuscript_id):
                continue
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            if str(metadata.get("sourceFileId") or "") == str(source_file_id):
                return True
        return False

    async def trash_book(
        self,
        *,
        user_id: str,
        manuscript_id: str,
        delete_source: bool = False,
    ) -> dict[str, Any]:
        try:
            manuscript = await self.manuscripts.get(user_id=user_id, manuscript_id=manuscript_id)
        except ManuscriptError as exc:
            raise LibraryError(exc.message, exc.code, exc.status_code) from exc

        if await self._active_run_exists(user_id=user_id, manuscript_id=str(manuscript["id"])):
            raise LibraryError(
                "Stop or cancel the active manuscript run before moving this book to Recently Deleted.",
                "MANUSCRIPT_RUN_ACTIVE",
                409,
            )

        metadata = manuscript.get("metadata") if isinstance(manuscript.get("metadata"), dict) else {}
        metadata = dict(metadata)
        source_id = str(metadata.get("sourceFileId") or "").strip()
        source_deleted = False
        source_kept = False

        if delete_source and source_id:
            source_kept = await self._source_is_referenced_elsewhere(
                user_id=user_id,
                manuscript_id=str(manuscript["id"]),
                source_file_id=source_id,
            )
            if not source_kept:
                try:
                    await self.files.soft_delete(user_id=user_id, file_id=source_id)
                    source_deleted = True
                except FileServiceError as exc:
                    if exc.code == "FILE_NOT_FOUND":
                        source_deleted = True
                    else:
                        raise LibraryError(
                            "The manuscript is safe, but its original source file could not be moved out of Files.",
                            "SOURCE_TRASH_FAILED",
                            503,
                        ) from exc

        trashed_at = _now()
        metadata["libraryTrash"] = {
            "trashedAt": trashed_at,
            "sourceFileId": source_id or None,
            "sourceDeleted": source_deleted,
        }

        try:
            updated = await self.db.update(
                "manuscripts",
                {"archived_at": trashed_at, "metadata": metadata, "updated_at": trashed_at},
                filters={"id": eq(manuscript["id"]), "user_id": eq(user_id)},
            )
        except Exception as exc:
            if source_deleted and source_id:
                try:
                    await self.files.restore_soft_deleted(user_id=user_id, file_id=source_id)
                except Exception:
                    pass
            raise LibraryError("The book could not be moved to Recently Deleted.", "BOOK_TRASH_FAILED", 503) from exc

        if not updated:
            if source_deleted and source_id:
                try:
                    await self.files.restore_soft_deleted(user_id=user_id, file_id=source_id)
                except Exception:
                    pass
            raise LibraryError("The book could not be moved to Recently Deleted.", "BOOK_TRASH_FAILED", 503)

        books = await self.list_books(user_id=user_id, deleted=True)
        item = next((book for book in books if str(book.get("id")) == str(manuscript["id"])), None)
        if not item:
            item = {"id": manuscript["id"], "title": manuscript.get("title") or "Manuscript", "trashedAt": trashed_at}
        item["sourceFileKept"] = source_kept
        return item

    async def restore_book(self, *, user_id: str, manuscript_id: str) -> dict[str, Any]:
        manuscript = await self._get_book_any(user_id=user_id, manuscript_id=manuscript_id)
        if manuscript.get("archived_at") is None:
            books = await self.list_books(user_id=user_id)
            item = next((book for book in books if str(book.get("id")) == str(manuscript["id"])), None)
            if item:
                return item
            raise LibraryError("The book is already active.", "BOOK_ALREADY_ACTIVE", 409)

        metadata = manuscript.get("metadata") if isinstance(manuscript.get("metadata"), dict) else {}
        metadata = dict(metadata)
        trash = metadata.get("libraryTrash") if isinstance(metadata.get("libraryTrash"), dict) else {}
        source_id = str(trash.get("sourceFileId") or metadata.get("sourceFileId") or "").strip()
        source_restored = False
        if bool(trash.get("sourceDeleted")) and source_id:
            try:
                await self.files.restore_soft_deleted(user_id=user_id, file_id=source_id)
                source_restored = True
            except FileServiceError as exc:
                if exc.code != "FILE_NOT_FOUND":
                    raise LibraryError(
                        "The book is recoverable, but its original source file could not be restored yet.",
                        "SOURCE_RESTORE_FAILED",
                        503,
                    ) from exc

        metadata.pop("libraryTrash", None)
        now = _now()
        updated = await self.db.update(
            "manuscripts",
            {"archived_at": None, "metadata": metadata, "updated_at": now},
            filters={"id": eq(manuscript["id"]), "user_id": eq(user_id)},
        )
        if not updated:
            raise LibraryError("The book could not be restored.", "BOOK_RESTORE_FAILED", 503)

        books = await self.list_books(user_id=user_id)
        item = next((book for book in books if str(book.get("id")) == str(manuscript["id"])), None)
        if not item:
            raise LibraryError("The restored book could not be reloaded.", "BOOK_RELOAD_FAILED", 503)
        item["sourceRestored"] = source_restored
        return item

    async def delete_book_permanently(self, *, user_id: str, manuscript_id: str) -> dict[str, Any]:
        manuscript = await self._get_book_any(user_id=user_id, manuscript_id=manuscript_id)
        if manuscript.get("archived_at") is None:
            raise LibraryError(
                "Move the book to Recently Deleted before deleting it permanently.",
                "BOOK_NOT_TRASHED",
                409,
            )
        if await self._active_run_exists(user_id=user_id, manuscript_id=str(manuscript["id"])):
            raise LibraryError(
                "This manuscript still has an active generation run and cannot be deleted permanently yet.",
                "MANUSCRIPT_RUN_ACTIVE",
                409,
            )

        metadata = manuscript.get("metadata") if isinstance(manuscript.get("metadata"), dict) else {}
        trash = metadata.get("libraryTrash") if isinstance(metadata.get("libraryTrash"), dict) else {}
        source_id = str(trash.get("sourceFileId") or metadata.get("sourceFileId") or "").strip()
        remove_source = bool(trash.get("sourceDeleted")) and bool(source_id)
        if remove_source:
            remove_source = not await self._source_is_referenced_elsewhere(
                user_id=user_id,
                manuscript_id=str(manuscript["id"]),
                source_file_id=source_id,
            )

        # Delete the manuscript first. Chapters and durable runs cascade from the
        # manuscript row. Source-object cleanup happens afterward so a storage
        # outage can never destroy the original file while leaving the book behind.
        deleted = await self.db.delete(
            "manuscripts",
            filters={"id": eq(manuscript["id"]), "user_id": eq(user_id)},
        )
        if not deleted:
            raise LibraryError("The book could not be permanently deleted.", "BOOK_DELETE_FAILED", 503)

        source_removed = False
        source_cleanup_pending = False
        if remove_source and source_id:
            try:
                await self.files.hard_delete(user_id=user_id, file_id=source_id)
                source_removed = True
            except FileServiceError as exc:
                if exc.code != "FILE_NOT_FOUND":
                    # The book deletion already succeeded. Keep the source soft-
                    # deleted and report cleanup as pending instead of pretending
                    # the manuscript itself still exists.
                    source_cleanup_pending = True

        return {
            "id": manuscript["id"],
            "sourceFileRemoved": source_removed,
            "sourceCleanupPending": source_cleanup_pending,
        }
