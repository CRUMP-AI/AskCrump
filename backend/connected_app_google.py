"""Direct Google Gmail and Calendar adapter with an injected credential transport.

This module never receives bearer or refresh tokens and never constructs a
caller-controlled URL.  It is deliberately uncomposed: production networking,
credential resolution, routes, and release switches live outside this boundary.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import getaddresses
import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .connected_app_contracts import (
    AmbiguousProviderResult,
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarFreeBusyRequest,
    CalendarGetRequest,
    CalendarListRequest,
    CalendarUpdateRequest,
    ConnectedAccountRef,
    CredentialHandleRef,
    EventSnapshot,
    FreeBusyWindow,
    MailDraftRequest,
    MailGetRequest,
    MailQuery,
    MailReplyRequest,
    MailSearchRequest,
    MailSendRequest,
    MessageSnapshot,
    MessageSummary,
    ProviderReceipt,
    validate_operation_inputs,
)
from .connected_app_policy import ConnectorProvider, ConnectorResource


GMAIL_HOST = "gmail.googleapis.com"
CALENDAR_HOST = "www.googleapis.com"
_MAX_RESPONSE_BYTES = 1_000_000
_MAX_BODY_TEXT_BYTES = 512_000
_MAX_PAGES = 100
_MESSAGE_ID = re.compile(r"^<[^<>\s@]+@[^<>\s@]+>$")
_INTERNAL_DATE = re.compile(r"^-?(?:0|[1-9][0-9]*)$")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_GMAIL_SYSTEM_LABEL_ALIASES = {
    "inbox": "INBOX",
    "spam": "SPAM",
    "trash": "TRASH",
    "sent": "SENT",
    "draft": "DRAFT",
    "starred": "STARRED",
    "important": "IMPORTANT",
    "unread": "UNREAD",
    "category_personal": "CATEGORY_PERSONAL",
    "category_social": "CATEGORY_SOCIAL",
    "category_promotions": "CATEGORY_PROMOTIONS",
    "category_updates": "CATEGORY_UPDATES",
    "category_forums": "CATEGORY_FORUMS",
}


class GoogleProviderError(RuntimeError):
    """Categorical, content-free provider failure safe for an API boundary."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable

    def __repr__(self) -> str:
        return f"GoogleProviderError(code={self.code!r}, retryable={self.retryable!r})"


class GoogleNotDispatched(ConnectionError):
    """The transport proves that no request bytes were dispatched."""

    def __init__(self, *_: object) -> None:
        super().__init__("GOOGLE_NOT_DISPATCHED")


class GoogleEffectUnknown(TimeoutError):
    """The request may have been dispatched and its external effect is unknown."""

    def __init__(self, *_: object) -> None:
        super().__init__("GOOGLE_EFFECT_UNKNOWN")


@dataclass(frozen=True, slots=True)
class GoogleTransportSecurityPolicy:
    """Attested requirements for any future credential-aware HTTPS transport.

    The adapter remains transport-injected and performs no networking.  A
    transport is accepted only when it attests this exact, non-configurable
    policy; a production implementation must enforce the same policy while
    streaming both compressed and decompressed response bytes.
    """

    scheme: str = "https"
    allowed_hosts: tuple[str, ...] = (GMAIL_HOST, CALENDAR_HOST)
    require_host_header_match: bool = True
    require_sni_match: bool = True
    follow_redirects: bool = False
    automatic_retries: bool = False
    use_environment_proxies: bool = False
    max_raw_response_bytes: int = _MAX_RESPONSE_BYTES
    max_decompressed_response_bytes: int = _MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        expected = (
            "https",
            (GMAIL_HOST, CALENDAR_HOST),
            True,
            True,
            False,
            False,
            False,
            _MAX_RESPONSE_BYTES,
            _MAX_RESPONSE_BYTES,
        )
        actual = (
            self.scheme,
            self.allowed_hosts,
            self.require_host_header_match,
            self.require_sni_match,
            self.follow_redirects,
            self.automatic_retries,
            self.use_environment_proxies,
            self.max_raw_response_bytes,
            self.max_decompressed_response_bytes,
        )
        if actual != expected:
            raise ValueError("Google transport security policy must be locked down")


@dataclass(frozen=True, slots=True, repr=False)
class GoogleTransportRequest:
    method: str
    host: str
    path: str
    query: tuple[tuple[str, str], ...] = ()
    headers: tuple[tuple[str, str], ...] = ()
    json_body: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.method not in {"GET", "POST", "PATCH", "DELETE"}:
            raise ValueError("unsupported Google transport method")
        if self.host not in {GMAIL_HOST, CALENDAR_HOST}:
            raise ValueError("unsupported Google transport host")
        if (
            not self.path.startswith("/")
            or self.path.startswith("//")
            or "://" in self.path
            or "?" in self.path
            or "#" in self.path
            or "\\" in self.path
            or any(ord(char) < 32 or ord(char) == 127 for char in self.path)
            or ".." in self.path.split("/")
        ):
            raise ValueError("Google transport path must be an absolute host-relative path")
        for name, value in (*self.query, *self.headers):
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("Google transport metadata must be text")
            if any(ord(char) < 32 or ord(char) == 127 for char in name + value):
                raise ValueError("Google transport metadata contains control characters")
        if any(name.casefold() == "authorization" for name, _ in self.headers):
            raise ValueError("credential material belongs to the injected transport")

    def __repr__(self) -> str:
        return (
            "GoogleTransportRequest("
            f"method={self.method!r}, host={self.host!r}, path='<redacted>', "
            "query='<redacted>', body='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class GoogleTransportResponse:
    status: int
    body: object | None = field(default=None, repr=False, compare=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False, compare=False)
    raw_size_bytes: int | None = field(default=None, repr=False, compare=False)
    decompressed_size_bytes: int | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.status) is not int or not 100 <= self.status <= 599:
            raise ValueError("invalid Google response status")
        if len(self.headers) > 100:
            raise ValueError("Google response contains too many headers")
        normalized: dict[str, str] = {}
        for name, value in self.headers.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("Google response headers must be text")
            if any(ord(char) < 32 or ord(char) == 127 for char in name + value):
                raise ValueError("Google response headers contain control characters")
            if len(name) > 200 or len(value.encode("utf-8")) > 8192:
                raise ValueError("Google response header exceeds its limit")
            normalized[name.casefold()] = value
        object.__setattr__(self, "headers", normalized)
        try:
            encoded = json.dumps(self.body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("Google response body must be bounded JSON data") from exc
        encoded_size = len(encoded)
        raw_size = encoded_size if self.raw_size_bytes is None else self.raw_size_bytes
        decompressed_size = (
            encoded_size
            if self.decompressed_size_bytes is None
            else self.decompressed_size_bytes
        )
        if (
            type(raw_size) is not int
            or type(decompressed_size) is not int
            or raw_size < 0
            or decompressed_size < encoded_size
        ):
            raise ValueError("Google response size attestation is invalid")
        if raw_size > _MAX_RESPONSE_BYTES or decompressed_size > _MAX_RESPONSE_BYTES:
            raise ValueError("Google response body exceeds the adapter limit")
        object.__setattr__(self, "raw_size_bytes", raw_size)
        object.__setattr__(self, "decompressed_size_bytes", decompressed_size)

    def __repr__(self) -> str:
        return f"GoogleTransportResponse(status={self.status}, body='<redacted>')"


class GoogleCredentialTransport(Protocol):
    security_policy: GoogleTransportSecurityPolicy

    async def request(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: GoogleTransportRequest,
    ) -> GoogleTransportResponse: ...


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _uuid(value: str) -> str:
    parsed = UUID(value)
    if str(parsed) != value:
        raise ValueError("operation_id must be canonical")
    return value


def _resource(account: ConnectedAccountRef, expected: ConnectorResource) -> None:
    if account.provider is not ConnectorProvider.GOOGLE or account.resource is not expected:
        raise GoogleProviderError("GOOGLE_ACCOUNT_RESOURCE_MISMATCH")


def _dict(value: object, code: str = "GOOGLE_RESPONSE_MALFORMED") -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise GoogleProviderError(code)
    return value


def _list(value: object, *, maximum: int) -> list[object]:
    if not isinstance(value, list) or len(value) > maximum:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
    return value


def _optional_list(row: Mapping[str, object], key: str, *, maximum: int) -> list[object]:
    value = row.get(key)
    return [] if value is None else _list(value, maximum=maximum)


def _text(value: object, *, maximum: int = 8192, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8")) > maximum:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
    if not allow_empty and not value:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
    return value


def _contract(factory: Callable[[], Any]) -> Any:
    try:
        return factory()
    except GoogleProviderError:
        raise
    except (TypeError, ValueError, OverflowError, OSError, ZoneInfoNotFoundError):
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED") from None


def _response_error(response: GoogleTransportResponse) -> None:
    if 200 <= response.status < 300:
        return
    if response.status in {409, 412}:
        raise GoogleProviderError("GOOGLE_RESOURCE_VERSION_CONFLICT")
    if response.status in {401, 403}:
        raise GoogleProviderError("GOOGLE_AUTHORIZATION_REJECTED")
    if response.status == 404:
        raise GoogleProviderError("GOOGLE_RESOURCE_NOT_FOUND")
    if response.status == 429 or response.status >= 500:
        raise GoogleProviderError("GOOGLE_PROVIDER_UNAVAILABLE", retryable=True)
    raise GoogleProviderError("GOOGLE_REQUEST_REJECTED")


def _header_map(payload: object) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in _list([] if payload is None else payload, maximum=200):
        row = _dict(item)
        name = _text(row.get("name"), maximum=200).casefold()
        value = _text(row.get("value"), maximum=16_384, allow_empty=True)
        values.setdefault(name, value)
    return values


def _addresses(*values: str) -> tuple[str, ...]:
    parsed = tuple(address for _, address in getaddresses(values) if address)
    if len(parsed) > 100:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
    return parsed


def _gmail_version(body: dict[str, Any]) -> str:
    return _text(body.get("historyId"), maximum=512)


def _gmail_labels(body: Mapping[str, object]) -> frozenset[str]:
    """Return a complete, validated Gmail label snapshot."""

    if "labelIds" not in body:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
    labels: list[str] = []
    seen: set[str] = set()
    for value in _list(body["labelIds"], maximum=100):
        label = _text(value, maximum=200)
        if label in seen:
            raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
        seen.add(label)
        labels.append(label)
    return frozenset(labels)


def _require_gmail_state(
    body: Mapping[str, object],
    *,
    required: str,
    forbidden: frozenset[str] = frozenset(),
) -> None:
    labels = _gmail_labels(body)
    if required not in labels or labels.intersection(forbidden):
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")


def _received(body: dict[str, Any]) -> datetime:
    raw = _text(body.get("internalDate"), maximum=32)
    if _INTERNAL_DATE.fullmatch(raw) is None:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
    try:
        value = int(raw)
        return _EPOCH + timedelta(milliseconds=value)
    except (ValueError, OverflowError, OSError):
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED") from None


def _gmail_search_labels(folder_ids: tuple[str, ...]) -> tuple[str, ...]:
    labels = tuple(
        _GMAIL_SYSTEM_LABEL_ALIASES.get(value.casefold(), value)
        for value in folder_ids
    )
    if len(set(labels)) != len(labels):
        raise GoogleProviderError("GOOGLE_REQUEST_INVALID")
    return labels


def _epoch_seconds(value: datetime, *, ceiling: bool) -> int:
    delta = value.astimezone(timezone.utc) - _EPOCH
    seconds = delta.days * 86_400 + delta.seconds
    if ceiling and delta.microseconds:
        seconds += 1
    return seconds


def _validate_mail_search_detail(
    row: dict[str, Any],
    *,
    query: MailQuery,
    required_labels: tuple[str, ...],
) -> None:
    labels = _gmail_labels(row)
    if not set(required_labels).issubset(labels):
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    received_at = _received(row).astimezone(timezone.utc)
    # MailQuery names strict boundaries: after < internalDate < before.
    if query.after is not None and received_at <= query.after.astimezone(timezone.utc):
        raise GoogleProviderError("GOOGLE_RESPONSE_OUT_OF_BOUNDS")
    if query.before is not None and received_at >= query.before.astimezone(timezone.utc):
        raise GoogleProviderError("GOOGLE_RESPONSE_OUT_OF_BOUNDS")


def _decode_part(data: object) -> str:
    raw = _text(data, maximum=700_000, allow_empty=True)
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        text = decoded.decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED") from None
    if len(text.encode("utf-8")) > _MAX_BODY_TEXT_BYTES:
        raise GoogleProviderError("GOOGLE_RESPONSE_TOO_LARGE")
    return text


class _BoundedHTMLText(HTMLParser):
    """Minimal non-rendering HTML-to-text fallback for untrusted mail."""

    _BLOCKS = {"br", "div", "p", "li", "tr", "table", "section", "article", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._chunks: list[str] = []
        self._size = 0

    def _append(self, value: str) -> None:
        self._size += len(value.encode("utf-8"))
        if self._size > _MAX_BODY_TEXT_BYTES:
            raise GoogleProviderError("GOOGLE_RESPONSE_TOO_LARGE")
        self._chunks.append(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() in {"script", "style", "template", "noscript"}:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and tag.casefold() in self._BLOCKS:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in {"script", "style", "template", "noscript"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
        elif self._ignored_depth == 0 and normalized in self._BLOCKS:
            self._append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self._append(data)

    def result(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self._chunks).splitlines())
        return "\n".join(line for line in lines if line)


def _html_to_text(value: str) -> str:
    parser = _BoundedHTMLText()
    try:
        parser.feed(value)
        parser.close()
    except (GoogleProviderError, RecursionError):
        raise
    except Exception:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED") from None
    result = parser.result()
    if len(result.encode("utf-8")) > _MAX_BODY_TEXT_BYTES:
        raise GoogleProviderError("GOOGLE_RESPONSE_TOO_LARGE")
    return result


def _content_disposition(headers: object) -> str:
    return _header_map(headers).get("content-disposition", "").casefold()


def _part_is_attachment(
    row: dict[str, Any],
    body: dict[str, Any],
    mime: str,
) -> bool:
    filename = row.get("filename")
    if filename is not None and _text(filename, maximum=1024, allow_empty=True):
        return True
    attachment_id = body.get("attachmentId")
    if attachment_id is not None:
        _text(attachment_id, maximum=1024)
        return True
    headers_value = row.get("headers")
    if _content_disposition([] if headers_value is None else headers_value).lstrip().startswith(
        "attachment"
    ):
        return True
    return (
        not mime.startswith("multipart/")
        and mime not in {"text/plain", "text/html"}
        and body.get("data") is not None
    )


def _body_and_attachments(
    part: object,
    *,
    depth: int = 0,
    require_full: bool = False,
) -> tuple[str, int, int]:
    """Return selected text, its preference (plain > html), and attachment count."""

    if depth > 20:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
    row = _dict(part)
    parts = _optional_list(row, "parts", maximum=100)
    mime = _text(row.get("mimeType") or "application/octet-stream", maximum=256).casefold()
    body = _dict(row.get("body") or {})
    if require_full:
        if mime.startswith("multipart/"):
            # A metadata-shaped Gmail MessagePart can contain headers and a
            # size-only body while omitting the MIME children.  Treat that as
            # incomplete rather than reporting a false attachment-free result.
            if "parts" not in row or not parts:
                raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
        elif "body" not in row:
            raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
        elif "data" not in body and "attachmentId" not in body:
            size = body.get("size")
            if type(size) is not int or size != 0:
                raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
    if _part_is_attachment(row, body, mime):
        return "", 0, 1

    if not parts:
        data = body.get("data")
        if mime == "text/plain" and data is not None:
            return _decode_part(data), 2, 0
        if mime == "text/html" and data is not None:
            return _html_to_text(_decode_part(data)), 1, 0
        return "", 0, 0

    selected: list[tuple[str, int]] = []
    attachments = 0
    for child in parts:
        child_text, preference, child_attachments = _body_and_attachments(
            child,
            depth=depth + 1,
            require_full=require_full,
        )
        if child_text:
            selected.append((child_text, preference))
        attachments += child_attachments
    if attachments > 100:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")

    if mime == "multipart/alternative" and selected:
        best = max(preference for _, preference in selected)
        selected = [next(item for item in selected if item[1] == best)]
    joined = "\n".join(text for text, _ in selected)
    if len(joined.encode("utf-8")) > _MAX_BODY_TEXT_BYTES:
        raise GoogleProviderError("GOOGLE_RESPONSE_TOO_LARGE")
    return joined, max((preference for _, preference in selected), default=0), attachments


def _summary(body: object) -> MessageSummary:
    row = _dict(body)
    payload = _dict(row.get("payload") or {})
    headers = _header_map(payload.get("headers"))
    _, _, attachments = _body_and_attachments(payload, require_full=True)
    labels = _gmail_labels(row)
    return _contract(
        lambda: MessageSummary(
            message_id=_text(row.get("id"), maximum=512),
            thread_id=_text(row.get("threadId"), maximum=512) if row.get("threadId") else None,
            resource_version=_gmail_version(row),
            received_at=_received(row),
            subject=headers.get("subject", ""),
            sender=headers.get("from", "unknown@example.invalid"),
            recipients=_addresses(headers.get("to", ""), headers.get("cc", "")),
            labels=tuple(sorted(labels)),
            has_attachments=attachments > 0,
        )
    )


def _message(body: object) -> MessageSnapshot:
    row = _dict(body)
    payload = _dict(row.get("payload") or {})
    headers = _header_map(payload.get("headers"))
    text, _, attachments = _body_and_attachments(payload)
    _gmail_labels(row)
    return _contract(
        lambda: MessageSnapshot(
            message_id=_text(row.get("id"), maximum=512),
            thread_id=_text(row.get("threadId"), maximum=512) if row.get("threadId") else None,
            resource_version=_gmail_version(row),
            received_at=_received(row),
            subject=headers.get("subject", ""),
            sender=headers.get("from", "unknown@example.invalid"),
            recipients=_addresses(headers.get("to", ""), headers.get("cc", "")),
            body_text=text,
            attachment_count=attachments,
        )
    )


def _mime_unchecked(
    spec: object,
    *,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> str:
    draft = spec
    message = EmailMessage(policy=SMTP)
    message["To"] = ", ".join(draft.to)
    if draft.cc:
        message["Cc"] = ", ".join(draft.cc)
    if draft.bcc:
        message["Bcc"] = ", ".join(draft.bcc)
    message["Subject"] = draft.subject
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = references or in_reply_to
    message.set_content(draft.body_text)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def _mime(
    spec: object,
    *,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> str:
    try:
        return _mime_unchecked(
            spec,
            in_reply_to=in_reply_to,
            references=references,
        )
    except GoogleProviderError:
        raise
    except Exception:
        raise GoogleProviderError("GOOGLE_REQUEST_ENCODING_FAILED") from None


def _valid_message_id(value: str) -> bool:
    return (
        _MESSAGE_ID.fullmatch(value) is not None
        and all(33 <= ord(char) <= 126 for char in value)
    )


def _reply_headers(headers: object, approved_subject: str) -> tuple[str, str]:
    critical = {"subject", "message-id", "references", "in-reply-to"}
    values: dict[str, list[str]] = {name: [] for name in critical}
    for item in _list([] if headers is None else headers, maximum=200):
        row = _dict(item)
        name = _text(row.get("name"), maximum=200).casefold()
        value = _text(row.get("value"), maximum=16_384, allow_empty=True)
        if name in values:
            values[name].append(value)
    if (
        len(values["subject"]) != 1
        or len(values["message-id"]) != 1
        or len(values["references"]) > 1
        or len(values["in-reply-to"]) > 1
    ):
        # Identical duplicates are still ambiguous provider state.  Never let
        # first-wins header folding choose the source of a reply.
        raise GoogleProviderError("GOOGLE_REPLY_HEADER_CARDINALITY_INVALID")
    if values["subject"][0] != approved_subject:
        raise GoogleProviderError("GOOGLE_REPLY_SUBJECT_CONFLICT")
    message_id = values["message-id"][0]
    if not _valid_message_id(message_id):
        raise GoogleProviderError("GOOGLE_REPLY_MESSAGE_ID_INVALID")
    references_value = values["references"][0] if values["references"] else ""
    references: list[str] = []
    if references_value:
        if any(ord(char) < 32 and char not in "\t " for char in references_value):
            raise GoogleProviderError("GOOGLE_REPLY_REFERENCES_INVALID")
        references = references_value.split()
        if len(references) > 50 or any(not _valid_message_id(item) for item in references):
            raise GoogleProviderError("GOOGLE_REPLY_REFERENCES_INVALID")
    if not references or references[-1] != message_id:
        references.append(message_id)
    joined = " ".join(references)
    if len(joined.encode("utf-8")) > 16_384:
        raise GoogleProviderError("GOOGLE_REPLY_REFERENCES_INVALID")
    return message_id, joined


def _normalized_mail_body(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _approved_mail_message(
    body: object,
    *,
    spec: object,
    expected_message_id: str,
    expected_thread_id: str | None = None,
    expected_history_id: str | None = None,
    required_label: str,
    forbidden_labels: frozenset[str] = frozenset(),
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict[str, Any]:
    """Validate an authoritative full Gmail message against approved content."""

    row = _dict(body)
    if _text(row.get("id"), maximum=512) != expected_message_id:
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    actual_thread_id = _text(row.get("threadId"), maximum=512)
    if expected_thread_id is not None and actual_thread_id != expected_thread_id:
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    actual_history_id = _gmail_version(row)
    if expected_history_id is not None and actual_history_id != expected_history_id:
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    _require_gmail_state(
        row,
        required=required_label,
        forbidden=forbidden_labels,
    )
    payload = _dict(row.get("payload"))
    approved_names = {"to", "cc", "bcc", "subject", "in-reply-to", "references"}
    header_values: dict[str, list[str]] = {name: [] for name in approved_names}
    for item in _optional_list(payload, "headers", maximum=200):
        header = _dict(item)
        name = _text(header.get("name"), maximum=200).casefold()
        if name in approved_names:
            header_values[name].append(
                _text(header.get("value"), maximum=16_384, allow_empty=True)
            )
    if any(len(values) > 1 for values in header_values.values()):
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    expected_headers = {
        "to": spec.to,
        "cc": spec.cc,
        "bcc": spec.bcc,
    }
    for name, expected in expected_headers.items():
        values = header_values[name]
        if (name == "to" or expected) and len(values) != 1:
            raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
        if name != "to" and not expected and values:
            raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
        actual = _addresses(values[0]) if values else ()
        if tuple(value.casefold() for value in actual) != tuple(
            value.casefold() for value in expected
        ):
            raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    if header_values["subject"] != [spec.subject]:
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    expected_reply_headers = {
        "in-reply-to": in_reply_to,
        "references": references,
    }
    for name, expected in expected_reply_headers.items():
        values = header_values[name]
        if expected is None:
            if values:
                raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
        elif values != [expected]:
            raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    body_text, preference, attachment_count = _body_and_attachments(payload)
    actual_body = _normalized_mail_body(body_text)
    expected_body = _normalized_mail_body(spec.body_text)
    if actual_body.endswith("\n") and not expected_body.endswith("\n"):
        actual_body = actual_body[:-1]
    if preference != 2 or attachment_count != 0 or actual_body != expected_body:
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    return row


def _next_page_token(
    row: dict[str, Any],
    seen: set[str],
    *,
    page_count: int,
) -> str | None:
    value = row.get("nextPageToken")
    if value is None:
        return None
    token = _text(value, maximum=2048)
    if token in seen or page_count >= _MAX_PAGES:
        raise GoogleProviderError("GOOGLE_PAGINATION_INVALID")
    seen.add(token)
    return token


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object, zone_name: str) -> datetime:
    text = _text(value, maximum=128)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(ZoneInfo(zone_name))
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED") from None


def _event(body: object, *, calendar_id: str) -> EventSnapshot:
    row = _dict(body)
    start = _dict(row.get("start"))
    end = _dict(row.get("end"))
    if "dateTime" not in start or "dateTime" not in end:
        raise GoogleProviderError("GOOGLE_ALL_DAY_EVENT_UNSUPPORTED")
    zone_name = _text(start.get("timeZone") or end.get("timeZone") or "UTC", maximum=100)
    attendees: list[str] = []
    for item in _optional_list(row, "attendees", maximum=100):
        attendees.append(_text(_dict(item).get("email"), maximum=320))
    organizer_row = _dict(row.get("organizer") or {})
    organizer = organizer_row.get("email")
    return _contract(
        lambda: EventSnapshot(
            event_id=_text(row.get("id"), maximum=512),
            calendar_id=calendar_id,
            resource_version=_text(row.get("etag"), maximum=512),
            starts_at=_parse_datetime(start["dateTime"], zone_name),
            ends_at=_parse_datetime(end["dateTime"], zone_name),
            time_zone=zone_name,
            title=_text(row.get("summary") or "(untitled)", maximum=8192),
            description=_text(row.get("description") or "", maximum=200_000, allow_empty=True),
            location=_text(row.get("location") or "", maximum=8192, allow_empty=True),
            attendees=tuple(attendees),
            organizer=_text(organizer, maximum=320) if organizer else None,
            status=_text(row.get("status") or "confirmed", maximum=32),
        )
    )


def _event_body(spec: object, *, event_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": spec.title,
        "description": spec.description,
        "location": spec.location,
        "start": {"dateTime": spec.starts_at.isoformat(), "timeZone": spec.time_zone},
        "end": {"dateTime": spec.ends_at.isoformat(), "timeZone": spec.time_zone},
        "attendees": [{"email": address} for address in spec.attendees],
    }
    if event_id is not None:
        body["id"] = event_id
    return body


def _event_id_and_version(body: object, *, expected_id: str) -> tuple[str, str]:
    row = _dict(body)
    event_id = _text(row.get("id"), maximum=512)
    version = _text(row.get("etag"), maximum=512)
    if event_id != expected_id:
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    return event_id, version


def _complete_attendees(row: Mapping[str, object]) -> None:
    if "attendeesOmitted" not in row:
        return
    value = row["attendeesOmitted"]
    if type(value) is not bool:
        raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
    if value:
        raise GoogleProviderError("GOOGLE_RESPONSE_ATTENDEES_INCOMPLETE")


def _approved_event(
    body: object,
    *,
    spec: object,
    expected_id: str,
    expected_status: str = "confirmed",
) -> EventSnapshot:
    """Validate the exact approved Calendar fields after an external effect."""

    row = _dict(body)
    _complete_attendees(row)
    snapshot = _event(row, calendar_id=spec.calendar_id)
    start = _dict(row.get("start"))
    end = _dict(row.get("end"))
    start_zone = _text(start.get("timeZone"), maximum=100)
    end_zone = _text(end.get("timeZone"), maximum=100)
    expected_attendees = {address.casefold() for address in spec.attendees}
    actual_attendees = {address.casefold() for address in snapshot.attendees}
    actual_status = _text(row.get("status"), maximum=32)
    equivalent = (
        snapshot.event_id == expected_id
        and snapshot.title == spec.title
        and snapshot.description == spec.description
        and snapshot.location == spec.location
        and snapshot.starts_at.astimezone(timezone.utc)
        == spec.starts_at.astimezone(timezone.utc)
        and snapshot.ends_at.astimezone(timezone.utc)
        == spec.ends_at.astimezone(timezone.utc)
        and start_zone == spec.time_zone
        and end_zone == spec.time_zone
        and snapshot.time_zone == spec.time_zone
        and actual_attendees == expected_attendees
        and len(snapshot.attendees) == len(expected_attendees)
        and actual_status == expected_status
        and snapshot.status == expected_status
    )
    if not equivalent:
        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
    return snapshot


def _merged_attendees(
    current_value: object,
    desired: tuple[str, ...],
) -> tuple[list[dict[str, Any]], bool]:
    current_rows = [] if current_value is None else _list(current_value, maximum=100)
    current: dict[str, dict[str, Any]] = {}
    for value in current_rows:
        row = _dict(value)
        email = _text(row.get("email"), maximum=320)
        key = email.casefold()
        if key in current:
            raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
        # A JSON round trip makes a bounded, detached copy while preserving
        # every provider-owned response/optional field for unchanged members.
        try:
            copied = json.loads(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
        except (TypeError, ValueError, RecursionError):
            raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED") from None
        current[key] = copied
    desired_keys = {item.casefold() for item in desired}
    changed = desired_keys != set(current)
    merged = [current.get(item.casefold(), {"email": item}) for item in desired]
    return merged, changed


class GoogleConnectedAppProvider:
    """Typed provider adapter.  It cannot resolve credentials or enable itself."""

    def __init__(
        self,
        transport: GoogleCredentialTransport,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        try:
            policy = getattr(transport, "security_policy", None)
        except Exception:
            raise ValueError("Google transport policy attestation failed") from None
        if (
            type(policy) is not GoogleTransportSecurityPolicy
            or policy != GoogleTransportSecurityPolicy()
        ):
            raise ValueError("Google transport has not attested the locked-down policy")
        self._transport = transport
        self._now = now

    async def _call(
        self,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: GoogleTransportRequest,
        *,
        effectful: bool = False,
    ) -> GoogleTransportResponse:
        if account.owner_id != credential.owner_id or account.connection_id != credential.connection_id:
            raise GoogleProviderError("GOOGLE_CREDENTIAL_BINDING_MISMATCH")
        if account.provider is not credential.provider or credential.provider is not ConnectorProvider.GOOGLE:
            raise GoogleProviderError("GOOGLE_CREDENTIAL_BINDING_MISMATCH")
        try:
            response = await self._transport.request(
                account=account,
                credential=credential,
                request=request,
            )
        except GoogleNotDispatched:
            raise GoogleProviderError(
                "GOOGLE_TRANSPORT_NOT_DISPATCHED",
                retryable=True,
            ) from None
        except GoogleEffectUnknown:
            if effectful:
                raise GoogleEffectUnknown() from None
            raise GoogleProviderError("GOOGLE_TRANSPORT_UNAVAILABLE", retryable=True) from None
        except Exception:
            if effectful:
                raise GoogleEffectUnknown() from None
            raise GoogleProviderError("GOOGLE_TRANSPORT_UNAVAILABLE", retryable=True) from None
        if not isinstance(response, GoogleTransportResponse):
            if effectful:
                raise GoogleEffectUnknown()
            raise GoogleProviderError("GOOGLE_RESPONSE_MALFORMED")
        if effectful and response.status >= 500:
            raise GoogleEffectUnknown()
        _response_error(response)
        return response

    async def search_mail(self, *, account, credential, request: MailSearchRequest):
        _resource(account, ConnectorResource.MAIL)
        query = request.query
        required_labels = _gmail_search_labels(query.folder_ids)
        q_parts = [query.query] if query.query else []
        if query.after is not None:
            # Gmail's q operator has only whole-second precision.  Use the
            # conservative floor, then enforce the exact millisecond boundary
            # against authoritative internalDate on every returned detail.
            q_parts.append(f"after:{_epoch_seconds(query.after, ceiling=False)}")
        if query.before is not None:
            # Ceiling avoids dropping valid messages in the boundary second;
            # authoritative detail validation rejects the widened edge.
            q_parts.append(f"before:{_epoch_seconds(query.before, ceiling=True)}")
        summaries: list[MessageSummary] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        seen_messages: set[str] = set()
        page_count = 0
        while len(summaries) < query.limit:
            remaining = query.limit - len(summaries)
            query_items = [("maxResults", str(remaining))]
            if q_parts:
                query_items.insert(0, ("q", " ".join(q_parts)))
            query_items.extend(("labelIds", label) for label in required_labels)
            if page_token is not None:
                query_items.append(("pageToken", page_token))
            response = await self._call(
                account,
                credential,
                GoogleTransportRequest(
                    "GET",
                    GMAIL_HOST,
                    "/gmail/v1/users/me/messages",
                    tuple(query_items),
                ),
            )
            page_count += 1
            page = _dict(response.body)
            rows = _optional_list(page, "messages", maximum=remaining)
            for item in rows:
                message_id = _text(_dict(item).get("id"), maximum=512)
                if message_id in seen_messages:
                    raise GoogleProviderError("GOOGLE_PAGINATION_INVALID")
                seen_messages.add(message_id)
                detail = await self._call(
                    account,
                    credential,
                    GoogleTransportRequest(
                        "GET",
                        GMAIL_HOST,
                        f"/gmail/v1/users/me/messages/{quote(message_id, safe='')}",
                        (("format", "full"),),
                    ),
                )
                detail_row = _dict(detail.body)
                if _text(detail_row.get("id"), maximum=512) != message_id:
                    raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
                _validate_mail_search_detail(
                    detail_row,
                    query=query,
                    required_labels=required_labels,
                )
                summaries.append(_summary(detail_row))
            if len(summaries) >= query.limit:
                break
            page_token = _next_page_token(page, seen_tokens, page_count=page_count)
            if page_token is None:
                break
        return tuple(summaries)

    async def get_message(self, *, account, credential, request: MailGetRequest):
        _resource(account, ConnectorResource.MAIL)
        response = await self._call(
            account,
            credential,
            GoogleTransportRequest(
                "GET",
                GMAIL_HOST,
                f"/gmail/v1/users/me/messages/{quote(request.message_id, safe='')}",
                (("format", "full"),),
            ),
        )
        row = _dict(response.body)
        if _text(row.get("id"), maximum=512) != request.message_id:
            raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
        result = _message(row)
        if request.expected_resource_version and result.resource_version != request.expected_resource_version:
            raise GoogleProviderError("GOOGLE_RESOURCE_VERSION_CONFLICT")
        return result

    def _ambiguous(self, operation_id: str, resource: ConnectorResource, key: str):
        return AmbiguousProviderResult(
            operation_id=operation_id,
            provider=ConnectorProvider.GOOGLE,
            resource=resource,
            idempotency_key_hash=_digest(key),
            observed_at=self._now(),
        )

    def _receipt(
        self,
        operation_id,
        resource,
        outcome,
        key,
        response,
        body,
        *,
        expected_resource_id: str | None = None,
    ):
        row = _dict(body)
        resource_id = _text(row.get("id"), maximum=512)
        if expected_resource_id is not None and resource_id != expected_resource_id:
            raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
        version = _text(row.get("historyId") or row.get("etag"), maximum=512)
        request_id = response.headers.get("x-goog-request-id") or operation_id
        return _contract(
            lambda: ProviderReceipt(
                operation_id=operation_id,
                provider=ConnectorProvider.GOOGLE,
                resource=resource,
                outcome=outcome,
                provider_request_id_hash=_digest(request_id),
                resource_id_hash=_digest(resource_id),
                resource_version=version,
                idempotency_key_hash=_digest(key),
                observed_at=self._now(),
            )
        )

    async def _read_approved_message(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        message_id: str,
        spec: object,
        expected_thread_id: str | None = None,
        expected_history_id: str | None = None,
        required_label: str,
        forbidden_labels: frozenset[str] = frozenset(),
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> dict[str, Any]:
        response = await self._call(
            account,
            credential,
            GoogleTransportRequest(
                "GET",
                GMAIL_HOST,
                f"/gmail/v1/users/me/messages/{quote(message_id, safe='')}",
                (("format", "full"),),
            ),
        )
        return _approved_mail_message(
            response.body,
            spec=spec,
            expected_message_id=message_id,
            expected_thread_id=expected_thread_id,
            expected_history_id=expected_history_id,
            required_label=required_label,
            forbidden_labels=forbidden_labels,
            in_reply_to=in_reply_to,
            references=references,
        )

    async def create_draft(self, *, account, credential, request: MailDraftRequest, operation_id, idempotency_key):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account, credential=credential, operation_id=operation_id, idempotency_key=idempotency_key
        )
        _resource(account, ConnectorResource.MAIL)
        try:
            response = await self._call(
                account,
                credential,
                GoogleTransportRequest("POST", GMAIL_HOST, "/gmail/v1/users/me/drafts", json_body={"message": {"raw": _mime(request.spec)}}),
                effectful=True,
            )
        except GoogleEffectUnknown:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        try:
            create_row = _dict(response.body)
            draft_id = _text(create_row.get("id"), maximum=512)
            create_message = create_row.get("message")
            create_message_row = (
                _dict(create_message) if create_message is not None else None
            )
            create_message_id = (
                _text(create_message_row.get("id"), maximum=512)
                if create_message_row is not None and create_message_row.get("id") is not None
                else None
            )
            draft_response = await self._call(
                account,
                credential,
                GoogleTransportRequest(
                    "GET",
                    GMAIL_HOST,
                    f"/gmail/v1/users/me/drafts/{quote(draft_id, safe='')}",
                    (("format", "full"),),
                ),
            )
            draft_row = _dict(draft_response.body)
            if _text(draft_row.get("id"), maximum=512) != draft_id:
                raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
            nested = _dict(draft_row.get("message"))
            message_id = _text(nested.get("id"), maximum=512)
            if create_message_id is not None and create_message_id != message_id:
                raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")

            wrapper_thread = (
                _text(nested.get("threadId"), maximum=512)
                if nested.get("threadId") is not None
                else None
            )
            wrapper_history = (
                _gmail_version(nested) if nested.get("historyId") is not None else None
            )
            if create_message_row is not None:
                if create_message_row.get("threadId") is not None:
                    if _text(create_message_row.get("threadId"), maximum=512) != wrapper_thread:
                        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
                if create_message_row.get("historyId") is not None:
                    if _gmail_version(create_message_row) != wrapper_history:
                        raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")

            if "payload" in nested:
                authoritative = _approved_mail_message(
                    nested,
                    spec=request.spec,
                    expected_message_id=message_id,
                    expected_thread_id=wrapper_thread,
                    expected_history_id=wrapper_history,
                    required_label="DRAFT",
                    forbidden_labels=frozenset({"SENT"}),
                )
            else:
                if "labelIds" in nested:
                    _require_gmail_state(
                        nested,
                        required="DRAFT",
                        forbidden=frozenset({"SENT"}),
                    )
                authoritative = await self._read_approved_message(
                    account=account,
                    credential=credential,
                    message_id=message_id,
                    spec=request.spec,
                    expected_thread_id=wrapper_thread,
                    expected_history_id=wrapper_history,
                    required_label="DRAFT",
                    forbidden_labels=frozenset({"SENT"}),
                )
            history_id = _gmail_version(authoritative)
            synthetic = {"id": draft_id, "historyId": history_id}
            return self._receipt(operation_id, ConnectorResource.MAIL, "drafted", idempotency_key, response, synthetic)
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)

    async def send_mail(self, *, account, credential, request: MailSendRequest, operation_id, idempotency_key):
        return await self._send(account, credential, request.spec, operation_id, idempotency_key)

    async def reply_mail(self, *, account, credential, request: MailReplyRequest, operation_id, idempotency_key):
        spec = request.spec
        source = await self._call(
            account,
            credential,
            GoogleTransportRequest("GET", GMAIL_HOST, f"/gmail/v1/users/me/messages/{quote(spec.reply_to_message_id or '', safe='')}", (("format", "metadata"),)),
        )
        row = _dict(source.body)
        if _text(row.get("id"), maximum=512) != spec.reply_to_message_id:
            raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
        if _gmail_version(row) != spec.expected_resource_version:
            raise GoogleProviderError("GOOGLE_RESOURCE_VERSION_CONFLICT")
        headers = _dict(row.get("payload") or {}).get("headers")
        thread_id = _text(row.get("threadId"), maximum=512)
        in_reply_to, references = _reply_headers(headers, spec.subject)
        return await self._send(
            account,
            credential,
            spec,
            operation_id,
            idempotency_key,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
        )

    async def _send(
        self,
        account,
        credential,
        spec,
        operation_id,
        idempotency_key,
        *,
        thread_id=None,
        in_reply_to=None,
        references=None,
    ):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account, credential=credential, operation_id=operation_id, idempotency_key=idempotency_key
        )
        _resource(account, ConnectorResource.MAIL)
        body = {
            "raw": _mime(
                spec,
                in_reply_to=in_reply_to,
                references=references,
            )
        }
        if thread_id:
            body["threadId"] = thread_id
        try:
            response = await self._call(
                account,
                credential,
                GoogleTransportRequest("POST", GMAIL_HOST, "/gmail/v1/users/me/messages/send", json_body=body),
                effectful=True,
            )
        except GoogleEffectUnknown:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        try:
            response_row = _dict(response.body)
            message_id = _text(response_row.get("id"), maximum=512)
            response_thread = _text(response_row.get("threadId"), maximum=512)
            response_history = _gmail_version(response_row)
            _require_gmail_state(
                response_row,
                required="SENT",
                forbidden=frozenset({"DRAFT"}),
            )
            if thread_id is not None and response_thread != thread_id:
                raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
            authoritative = await self._read_approved_message(
                account=account,
                credential=credential,
                message_id=message_id,
                spec=spec,
                expected_thread_id=response_thread,
                expected_history_id=response_history,
                required_label="SENT",
                forbidden_labels=frozenset({"DRAFT"}),
                in_reply_to=in_reply_to,
                references=references,
            )
            return self._receipt(
                operation_id,
                ConnectorResource.MAIL,
                "sent",
                idempotency_key,
                response,
                authoritative,
                expected_resource_id=message_id,
            )
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)

    async def list_events(self, *, account, credential, request: CalendarListRequest):
        _resource(account, ConnectorResource.CALENDAR)
        results: list[EventSnapshot] = []
        for calendar_id in request.query.calendar_ids:
            page_token: str | None = None
            seen_tokens: set[str] = set()
            seen_events: set[str] = set()
            page_count = 0
            while len(results) < request.query.limit:
                remaining = request.query.limit - len(results)
                query_items = [
                    ("timeMin", _rfc3339(request.query.starts_at)),
                    ("timeMax", _rfc3339(request.query.ends_at)),
                    ("singleEvents", "true"),
                    ("maxResults", str(remaining)),
                ]
                if page_token is not None:
                    query_items.append(("pageToken", page_token))
                response = await self._call(
                    account,
                    credential,
                    GoogleTransportRequest(
                        "GET",
                        CALENDAR_HOST,
                        f"/calendar/v3/calendars/{quote(calendar_id, safe='')}/events",
                        tuple(query_items),
                    ),
                )
                page_count += 1
                page = _dict(response.body)
                for item in _optional_list(page, "items", maximum=remaining):
                    event = _event(item, calendar_id=calendar_id)
                    starts_at = event.starts_at.astimezone(timezone.utc)
                    ends_at = event.ends_at.astimezone(timezone.utc)
                    query_start = request.query.starts_at.astimezone(timezone.utc)
                    query_end = request.query.ends_at.astimezone(timezone.utc)
                    if not (starts_at < query_end and ends_at > query_start):
                        raise GoogleProviderError("GOOGLE_RESPONSE_OUT_OF_BOUNDS")
                    if event.event_id in seen_events:
                        raise GoogleProviderError("GOOGLE_PAGINATION_INVALID")
                    seen_events.add(event.event_id)
                    results.append(event)
                if len(results) >= request.query.limit:
                    return tuple(results)
                page_token = _next_page_token(page, seen_tokens, page_count=page_count)
                if page_token is None:
                    break
        return tuple(results)

    async def free_busy(self, *, account, credential, request: CalendarFreeBusyRequest):
        _resource(account, ConnectorResource.CALENDAR)
        query = request.query
        response = await self._call(
            account,
            credential,
            GoogleTransportRequest(
                "POST",
                CALENDAR_HOST,
                "/calendar/v3/freeBusy",
                json_body={"timeMin": _rfc3339(query.starts_at), "timeMax": _rfc3339(query.ends_at), "timeZone": query.time_zone, "items": [{"id": item} for item in query.calendar_ids]},
            ),
        )
        response_row = _dict(response.body)
        query_start = query.starts_at.astimezone(timezone.utc)
        query_end = query.ends_at.astimezone(timezone.utc)
        response_start = _parse_datetime(
            response_row.get("timeMin"),
            query.time_zone,
        ).astimezone(timezone.utc)
        response_end = _parse_datetime(
            response_row.get("timeMax"),
            query.time_zone,
        ).astimezone(timezone.utc)
        if response_start != query_start or response_end != query_end:
            raise GoogleProviderError("GOOGLE_RESPONSE_OUT_OF_BOUNDS")
        calendars = _dict(response_row.get("calendars"))
        windows: list[FreeBusyWindow] = []
        for calendar_id in query.calendar_ids:
            if calendar_id not in calendars:
                raise GoogleProviderError("GOOGLE_FREEBUSY_INCOMPLETE")
            calendar = _dict(calendars[calendar_id])
            errors = _optional_list(calendar, "errors", maximum=20)
            if errors:
                reasons = {
                    _text(_dict(error).get("reason"), maximum=128)
                    for error in errors
                }
                if "internalError" in reasons:
                    raise GoogleProviderError(
                        "GOOGLE_PROVIDER_UNAVAILABLE",
                        retryable=True,
                    )
                raise GoogleProviderError("GOOGLE_FREEBUSY_REJECTED")
            for item in _optional_list(calendar, "busy", maximum=250):
                row = _dict(item)
                starts_at = _parse_datetime(row.get("start"), query.time_zone)
                ends_at = _parse_datetime(row.get("end"), query.time_zone)
                starts_at_utc = starts_at.astimezone(timezone.utc)
                ends_at_utc = ends_at.astimezone(timezone.utc)
                if not (
                    query_start <= starts_at_utc
                    and starts_at_utc < ends_at_utc
                    and ends_at_utc <= query_end
                ):
                    raise GoogleProviderError("GOOGLE_RESPONSE_OUT_OF_BOUNDS")
                windows.append(
                    _contract(
                        lambda: FreeBusyWindow(
                            calendar_id,
                            starts_at,
                            ends_at,
                        )
                    )
                )
                if len(windows) > 1000:
                    raise GoogleProviderError("GOOGLE_RESPONSE_TOO_LARGE")
        return tuple(windows)

    async def get_event(self, *, account, credential, request: CalendarGetRequest):
        _resource(account, ConnectorResource.CALENDAR)
        response = await self._call(
            account,
            credential,
            GoogleTransportRequest("GET", CALENDAR_HOST, f"/calendar/v3/calendars/{quote(request.calendar_id, safe='')}/events/{quote(request.event_id, safe='')}")
        )
        row = _dict(response.body)
        if _text(row.get("id"), maximum=512) != request.event_id:
            raise GoogleProviderError("GOOGLE_RESPONSE_RESOURCE_MISMATCH")
        result = _event(row, calendar_id=request.calendar_id)
        if request.expected_resource_version and result.resource_version != request.expected_resource_version:
            raise GoogleProviderError("GOOGLE_RESOURCE_VERSION_CONFLICT")
        return result

    async def create_event(self, *, account, credential, request: CalendarCreateRequest, operation_id, idempotency_key):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account, credential=credential, operation_id=operation_id, idempotency_key=idempotency_key
        )
        _resource(account, ConnectorResource.CALENDAR)
        event_id = "ac" + hashlib.sha256((operation_id + idempotency_key).encode()).hexdigest()[:30]
        try:
            response = await self._call(
                account,
                credential,
                GoogleTransportRequest(
                    "POST",
                    CALENDAR_HOST,
                    f"/calendar/v3/calendars/{quote(request.spec.calendar_id, safe='')}/events",
                    (("sendUpdates", "all" if request.spec.attendees else "none"),),
                    json_body=_event_body(request.spec, event_id=event_id),
                ),
                effectful=True,
            )
        except GoogleEffectUnknown:
            return await self._reconcile_created_event(
                account=account,
                credential=credential,
                spec=request.spec,
                event_id=event_id,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
            )
        try:
            _approved_event(
                response.body,
                spec=request.spec,
                expected_id=event_id,
            )
            return self._receipt(
                operation_id,
                ConnectorResource.CALENDAR,
                "created",
                idempotency_key,
                response,
                response.body,
                expected_resource_id=event_id,
            )
        except Exception:
            return await self._reconcile_created_event(
                account=account,
                credential=credential,
                spec=request.spec,
                event_id=event_id,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
            )

    async def _reconcile_created_event(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        spec: object,
        event_id: str,
        operation_id: str,
        idempotency_key: str,
    ):
        """Read the deterministic event ID once; never repost an uncertain create."""

        try:
            response = await self._call(
                account,
                credential,
                GoogleTransportRequest(
                    "GET",
                    CALENDAR_HOST,
                    f"/calendar/v3/calendars/{quote(spec.calendar_id, safe='')}/events/{quote(event_id, safe='')}",
                ),
            )
            _approved_event(
                response.body,
                spec=spec,
                expected_id=event_id,
            )
            return self._receipt(
                operation_id,
                ConnectorResource.CALENDAR,
                "created",
                idempotency_key,
                response,
                response.body,
                expected_resource_id=event_id,
            )
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)

    async def update_event(self, *, account, credential, request: CalendarUpdateRequest, operation_id, idempotency_key):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account, credential=credential, operation_id=operation_id, idempotency_key=idempotency_key
        )
        _resource(account, ConnectorResource.CALENDAR)
        spec = request.spec
        event_id = spec.source_event_id or ""
        current_response = await self._call(
            account,
            credential,
            GoogleTransportRequest(
                "GET",
                CALENDAR_HOST,
                f"/calendar/v3/calendars/{quote(spec.calendar_id, safe='')}/events/{quote(event_id, safe='')}",
            ),
        )
        current = _dict(current_response.body)
        current_id, current_version = _event_id_and_version(current, expected_id=event_id)
        del current_id
        _complete_attendees(current)
        _event(current, calendar_id=spec.calendar_id)
        if current_version != spec.expected_resource_version:
            raise GoogleProviderError("GOOGLE_RESOURCE_VERSION_CONFLICT")
        attendees, membership_changed = _merged_attendees(
            current.get("attendees"),
            spec.attendees,
        )
        patch_body = _event_body(spec)
        patch_body["attendees"] = attendees
        try:
            response = await self._call(
                account,
                credential,
                GoogleTransportRequest(
                    "PATCH",
                    CALENDAR_HOST,
                    f"/calendar/v3/calendars/{quote(spec.calendar_id, safe='')}/events/{quote(event_id, safe='')}",
                    (("sendUpdates", "all" if spec.attendees or membership_changed else "none"),),
                    (("If-Match", spec.expected_resource_version or ""),),
                    patch_body,
                ),
                effectful=True,
            )
        except GoogleEffectUnknown:
            return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)
        try:
            _approved_event(
                response.body,
                spec=spec,
                expected_id=event_id,
            )
            return self._receipt(
                operation_id,
                ConnectorResource.CALENDAR,
                "updated",
                idempotency_key,
                response,
                response.body,
                expected_resource_id=event_id,
            )
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)

    async def cancel_event(self, *, account, credential, request: CalendarCancelRequest, operation_id, idempotency_key):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account, credential=credential, operation_id=operation_id, idempotency_key=idempotency_key
        )
        _resource(account, ConnectorResource.CALENDAR)
        try:
            response = await self._call(
                account,
                credential,
                GoogleTransportRequest(
                    "DELETE",
                    CALENDAR_HOST,
                    f"/calendar/v3/calendars/{quote(request.calendar_id, safe='')}/events/{quote(request.event_id, safe='')}",
                    (("sendUpdates", "all"),),
                    (("If-Match", request.expected_resource_version),),
                ),
                effectful=True,
            )
        except GoogleEffectUnknown:
            return await self._reconcile_cancelled_event(
                account=account,
                credential=credential,
                request=request,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
            )
        if response.status != 204 or response.body is not None:
            return await self._reconcile_cancelled_event(
                account=account,
                credential=credential,
                request=request,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
            )
        try:
            return self._cancel_receipt(
                request=request,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
                response=response,
            )
        except Exception:
            return await self._reconcile_cancelled_event(
                account=account,
                credential=credential,
                request=request,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
            )

    def _cancel_receipt(
        self,
        *,
        request: CalendarCancelRequest,
        operation_id: str,
        idempotency_key: str,
        response: GoogleTransportResponse,
    ) -> ProviderReceipt:
        request_id = response.headers.get("x-goog-request-id") or operation_id
        return ProviderReceipt(
            operation_id=operation_id,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.CALENDAR,
            outcome="cancelled",
            provider_request_id_hash=_digest(request_id),
            resource_id_hash=_digest(request.event_id),
            resource_version=request.expected_resource_version,
            idempotency_key_hash=_digest(idempotency_key),
            observed_at=self._now(),
        )

    async def _reconcile_cancelled_event(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: CalendarCancelRequest,
        operation_id: str,
        idempotency_key: str,
    ):
        """A single authoritative absence check; never redispatch DELETE."""

        try:
            await self._call(
                account,
                credential,
                GoogleTransportRequest(
                    "GET",
                    CALENDAR_HOST,
                    f"/calendar/v3/calendars/{quote(request.calendar_id, safe='')}/events/{quote(request.event_id, safe='')}",
                ),
            )
        except GoogleProviderError as exc:
            if exc.code == "GOOGLE_RESOURCE_NOT_FOUND":
                synthetic = GoogleTransportResponse(204, None)
                return self._cancel_receipt(
                    request=request,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                    response=synthetic,
                )
        except Exception:
            pass
        return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)
