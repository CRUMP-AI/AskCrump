"""Fail-closed Microsoft Graph mail and calendar adapter.

The adapter is deliberately transport-injected.  It never receives an OAuth
token, never follows a provider URL supplied by a response, and never retries a
write whose effect might have happened.  Production credential resolution,
networking, routes, persistence, and release switches are intentionally outside
this module.

The proof strategy follows the Microsoft Graph v1.0 documentation:

* immutable Outlook IDs must be requested on every request, and a sent draft
  can then be read by the same ID in Sent Items:
  https://learn.microsoft.com/graph/outlook-immutable-id
* message collection ``$search`` cannot be combined with ``$filter`` or
  ``$orderby``:
  https://learn.microsoft.com/graph/search-query-parameter#using-search-on-message-collections
* message drafts and reply drafts require ``Mail.ReadWrite`` and sending the
  exact draft requires ``Mail.Send``:
  https://learn.microsoft.com/graph/api/user-post-messages
  https://learn.microsoft.com/graph/api/message-createreply
  https://learn.microsoft.com/graph/api/message-send
* calendar creates accept a client ``transactionId`` and calendar updates are
  partial patches:
  https://learn.microsoft.com/graph/api/resources/event
  https://learn.microsoft.com/graph/api/event-update
  https://learn.microsoft.com/graph/api/event-delete
* ``getSchedule`` is delegated work/school only:
  https://learn.microsoft.com/graph/api/calendar-getschedule
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence
from urllib.parse import parse_qsl, quote, urlsplit
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
    ConnectorAccountKind,
    CredentialHandleRef,
    EventSnapshot,
    FreeBusyWindow,
    MailDraftRequest,
    MailGetRequest,
    MailReplyRequest,
    MailSearchRequest,
    MailSendRequest,
    MessageSnapshot,
    MessageSummary,
    ProviderReceipt,
    validate_operation_inputs,
)
from .connected_app_policy import ConnectorProvider, ConnectorResource


GRAPH_HOST = "graph.microsoft.com"
GRAPH_ROOT = "/v1.0"
_MAX_RESPONSE_BYTES = 1_000_000
_MAX_BODY_TEXT_BYTES = 512_000
_MAX_PAGES = 100
_MAX_ATTACHMENTS = 100
_SEND_RECONCILIATION_DELAYS = (0.0, 0.05, 0.15)
_OPERATION_PROPERTY_ID = "String {6f23f3dc-8f7b-4b7e-9c2c-7a928fe87f1d} Name AskCrumpOperation"
_MAIL_PREFER = 'IdType="ImmutableId", outlook.body-content-type="text"'
_MAIL_SELECT = (
    "id,conversationId,parentFolderId,changeKey,receivedDateTime,subject,from,"
    "toRecipients,ccRecipients,bccRecipients,body,hasAttachments,isDraft,"
    "internetMessageId,internetMessageHeaders"
)
_EVENT_SELECT = (
    "id,changeKey,subject,body,start,end,location,locations,attendees,organizer,"
    "isCancelled,isOrganizer,responseStatus,showAs,isOnlineMeeting,transactionId"
)
_WELL_KNOWN_FOLDERS = frozenset(
    {
        "archive",
        "clutter",
        "conflicts",
        "conversationhistory",
        "deleteditems",
        "drafts",
        "inbox",
        "junkemail",
        "localfailures",
        "msgfolderroot",
        "outbox",
        "recoverableitemsdeletions",
        "scheduled",
        "searchfolders",
        "sentitems",
        "serverfailures",
        "syncissues",
    }
)
_ETAG = re.compile(r'^W/"([^"\x00-\x1f\x7f]{1,512})"$')
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,200}$")
_MESSAGE_ID = re.compile(r"^<[^<>\s@]+@[^<>\s@]+>$")


class MicrosoftProviderError(RuntimeError):
    """Categorical, content-free failure safe for an API boundary."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable

    def __repr__(self) -> str:
        return f"MicrosoftProviderError(code={self.code!r}, retryable={self.retryable!r})"


class MicrosoftNotDispatched(ConnectionError):
    """The credential transport proves no request bytes were dispatched."""

    def __init__(self, *_: object) -> None:
        super().__init__("MICROSOFT_NOT_DISPATCHED")


class MicrosoftEffectUnknown(TimeoutError):
    """A write may have reached Graph and its external effect is unknown."""

    def __init__(self, *_: object) -> None:
        super().__init__("MICROSOFT_EFFECT_UNKNOWN")


@dataclass(frozen=True, slots=True)
class MicrosoftTransportSecurityPolicy:
    scheme: str = "https"
    allowed_hosts: tuple[str, ...] = (GRAPH_HOST,)
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
            (GRAPH_HOST,),
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
            raise ValueError("Microsoft transport security policy must be locked down")


@dataclass(frozen=True, slots=True, repr=False)
class MicrosoftTransportRequest:
    method: str
    host: str
    path: str
    query: tuple[tuple[str, str], ...] = ()
    headers: tuple[tuple[str, str], ...] = ()
    json_body: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.method not in {"GET", "POST", "PATCH", "DELETE"}:
            raise ValueError("unsupported Microsoft transport method")
        if self.host != GRAPH_HOST:
            raise ValueError("unsupported Microsoft transport host")
        if (
            not self.path.startswith(f"{GRAPH_ROOT}/")
            or self.path.startswith("//")
            or "://" in self.path
            or "?" in self.path
            or "#" in self.path
            or "\\" in self.path
            or any(ord(char) < 32 or ord(char) == 127 for char in self.path)
            or ".." in self.path.split("/")
        ):
            raise ValueError("Microsoft transport path must be a fixed v1.0 host-relative path")
        names: set[str] = set()
        for name, value in self.headers:
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("Microsoft transport metadata must be text")
            folded = name.casefold()
            if folded in names:
                raise ValueError("Microsoft transport request headers must be unique")
            names.add(folded)
            if not _HEADER_NAME.fullmatch(name) or any(
                ord(char) < 32 or ord(char) == 127 for char in value
            ):
                raise ValueError("Microsoft transport metadata is malformed")
            if folded in {"authorization", "host", "proxy-authorization"}:
                raise ValueError("credential and routing metadata belongs to the transport")
        if len(self.query) > 40:
            raise ValueError("Microsoft transport query is too large")
        query_names: set[str] = set()
        for name, value in self.query:
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("Microsoft transport metadata must be text")
            try:
                value_size = len(value.encode("utf-8"))
            except UnicodeError:
                raise ValueError("Microsoft transport query is malformed") from None
            if name in query_names or len(name) > 100 or value_size > 16_384:
                raise ValueError("Microsoft transport query is malformed")
            query_names.add(name)
            if any(ord(char) < 32 or ord(char) == 127 for char in name + value):
                raise ValueError("Microsoft transport metadata is malformed")
        if self.json_body is not None:
            try:
                encoded = json.dumps(
                    self.json_body,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
                raise ValueError("Microsoft request body must be bounded JSON data") from exc
            if len(encoded) > _MAX_RESPONSE_BYTES:
                raise ValueError("Microsoft request body exceeds the adapter limit")

    def __repr__(self) -> str:
        return (
            "MicrosoftTransportRequest("
            f"method={self.method!r}, host={self.host!r}, path='<redacted>', "
            "query='<redacted>', body='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class MicrosoftTransportResponse:
    status: int
    body: object | None = field(default=None, repr=False, compare=False)
    headers: object = field(default_factory=dict, repr=False, compare=False)
    raw_size_bytes: int | None = field(default=None, repr=False, compare=False)
    decompressed_size_bytes: int | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.status) is not int or not 100 <= self.status <= 599:
            raise ValueError("invalid Microsoft response status")
        source = self.headers
        if isinstance(source, Mapping):
            items = list(source.items())
        elif isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
            items = list(source)
        else:
            raise TypeError("Microsoft response headers must be a mapping or pair sequence")
        if len(items) > 100:
            raise ValueError("Microsoft response contains too many headers")
        normalized: dict[str, str] = {}
        for item in items:
            if not isinstance(item, Sequence) or isinstance(item, (str, bytes)) or len(item) != 2:
                raise TypeError("Microsoft response headers must contain pairs")
            name, value = item
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("Microsoft response headers must be text")
            folded = name.casefold()
            if folded in normalized:
                raise ValueError("Microsoft response contains duplicate headers")
            if not _HEADER_NAME.fullmatch(name) or any(
                ord(char) < 32 or ord(char) == 127 for char in value
            ):
                raise ValueError("Microsoft response headers are malformed")
            try:
                header_size = len(value.encode("utf-8"))
            except UnicodeError:
                raise ValueError("Microsoft response headers are malformed") from None
            if header_size > 8192:
                raise ValueError("Microsoft response header exceeds its limit")
            normalized[folded] = value
        object.__setattr__(self, "headers", normalized)
        try:
            encoded = json.dumps(
                self.body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise ValueError("Microsoft response body must be bounded JSON data") from exc
        encoded_size = len(encoded)
        raw = encoded_size if self.raw_size_bytes is None else self.raw_size_bytes
        decompressed = (
            encoded_size if self.decompressed_size_bytes is None else self.decompressed_size_bytes
        )
        if (
            type(raw) is not int
            or type(decompressed) is not int
            or raw < 0
            or decompressed < encoded_size
            or raw > _MAX_RESPONSE_BYTES
            or decompressed > _MAX_RESPONSE_BYTES
        ):
            raise ValueError("Microsoft response size attestation is invalid")
        object.__setattr__(self, "raw_size_bytes", raw)
        object.__setattr__(self, "decompressed_size_bytes", decompressed)

    def __repr__(self) -> str:
        return f"MicrosoftTransportResponse(status={self.status}, body='<redacted>')"


class MicrosoftCredentialTransport(Protocol):
    security_policy: MicrosoftTransportSecurityPolicy

    async def request(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: MicrosoftTransportRequest,
    ) -> MicrosoftTransportResponse: ...


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resource(account: ConnectedAccountRef, expected: ConnectorResource) -> None:
    if account.provider is not ConnectorProvider.MICROSOFT or account.resource is not expected:
        raise MicrosoftProviderError("MICROSOFT_ACCOUNT_RESOURCE_MISMATCH")


def _dict(value: object, code: str = "MICROSOFT_RESPONSE_MALFORMED") -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise MicrosoftProviderError(code)
    return value


def _list(value: object, *, maximum: int) -> list[object]:
    if not isinstance(value, list) or len(value) > maximum:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    return value


def _optional_list(row: Mapping[str, object], key: str, *, maximum: int) -> list[object]:
    value = row.get(key)
    return [] if value is None else _list(value, maximum=maximum)


def _text(value: object, *, maximum: int = 8192, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    try:
        encoded_size = len(value.encode("utf-8"))
    except UnicodeError:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED") from None
    if encoded_size > maximum:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    if not allow_empty and not value:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    if any(ord(char) < 32 and char not in "\t\r\n" for char in value) or "\x7f" in value:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    return value


def _identifier(value: object, *, maximum: int = 512) -> str:
    result = _text(value, maximum=maximum)
    if any(ord(char) <= 32 or ord(char) == 127 for char in result):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    return result


def _valid_message_id(value: str) -> bool:
    return _MESSAGE_ID.fullmatch(value) is not None and all(
        33 <= ord(char) <= 126 for char in value
    )


def _contract(factory: Callable[[], Any]) -> Any:
    try:
        return factory()
    except MicrosoftProviderError:
        raise
    except (TypeError, ValueError, OverflowError, OSError, ZoneInfoNotFoundError):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED") from None


def _response_error(response: MicrosoftTransportResponse) -> None:
    if 200 <= response.status < 300:
        return
    if response.status in {409, 412}:
        raise MicrosoftProviderError("MICROSOFT_RESOURCE_VERSION_CONFLICT")
    if response.status in {401, 403}:
        raise MicrosoftProviderError("MICROSOFT_AUTHORIZATION_REJECTED")
    if response.status == 404:
        raise MicrosoftProviderError("MICROSOFT_RESOURCE_NOT_FOUND")
    if response.status == 429 or response.status >= 500:
        raise MicrosoftProviderError("MICROSOFT_PROVIDER_UNAVAILABLE", retryable=True)
    raise MicrosoftProviderError("MICROSOFT_REQUEST_REJECTED")


def _version(row: Mapping[str, object]) -> str:
    etag = _text(row.get("@odata.etag"), maximum=512)
    change_key = _text(row.get("changeKey"), maximum=512)
    match = _ETAG.fullmatch(etag)
    if match is None or match.group(1) != change_key:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_VERSION_MISMATCH")
    return etag


def _parse_instant(value: object) -> datetime:
    raw = _text(value, maximum=128)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    return parsed


class _BoundedHTMLText(HTMLParser):
    _BLOCKS = {"br", "div", "p", "li", "tr", "table", "section", "article", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored = 0
        self._chunks: list[str] = []
        self._size = 0

    def _append(self, value: str) -> None:
        self._size += len(value.encode("utf-8"))
        if self._size > _MAX_BODY_TEXT_BYTES:
            raise MicrosoftProviderError("MICROSOFT_RESPONSE_TOO_LARGE")
        self._chunks.append(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.casefold()
        if normalized in {"script", "style", "template", "noscript"}:
            self._ignored += 1
        elif not self._ignored and normalized in self._BLOCKS:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in {"script", "style", "template", "noscript"}:
            if self._ignored:
                self._ignored -= 1
        elif not self._ignored and normalized in self._BLOCKS:
            self._append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self._append(data)

    def result(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self._chunks).splitlines())
        return "\n".join(line for line in lines if line)


def _body_text(value: object) -> str:
    row = _dict(value)
    kind = _text(row.get("contentType"), maximum=16).casefold()
    content = _text(row.get("content"), maximum=_MAX_BODY_TEXT_BYTES, allow_empty=True)
    if kind == "text":
        return content
    if kind != "html":
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    parser = _BoundedHTMLText()
    try:
        parser.feed(content)
        parser.close()
        return parser.result()
    except MicrosoftProviderError:
        raise
    except Exception:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED") from None


def _recipient(value: object) -> str:
    row = _dict(value)
    email = _dict(row.get("emailAddress"))
    return _text(email.get("address"), maximum=320)


def _recipient_group(row: Mapping[str, object], key: str) -> tuple[str, ...]:
    if key not in row:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    values = tuple(_recipient(item) for item in _list(row[key], maximum=100))
    folded = tuple(item.casefold() for item in values)
    if len(set(folded)) != len(folded):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    return values


def _all_recipients(row: Mapping[str, object]) -> tuple[tuple[str, ...], ...]:
    groups = (
        _recipient_group(row, "toRecipients"),
        _recipient_group(row, "ccRecipients"),
        _recipient_group(row, "bccRecipients"),
    )
    flattened = tuple(item.casefold() for group in groups for item in group)
    if len(set(flattened)) != len(flattened):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    return groups


def _internet_headers(row: Mapping[str, object]) -> dict[str, list[str]]:
    if "internetMessageHeaders" not in row:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    headers: dict[str, list[str]] = {}
    for item in _list(row["internetMessageHeaders"], maximum=200):
        header = _dict(item)
        name = _text(header.get("name"), maximum=200).casefold()
        value = _text(header.get("value"), maximum=16_384, allow_empty=True)
        if not _HEADER_NAME.fullmatch(name):
            raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
        headers.setdefault(name, []).append(value)
    return headers


def _critical_source_headers(row: Mapping[str, object]) -> tuple[str, str | None]:
    internet_id = _text(row.get("internetMessageId"), maximum=2048)
    if not _valid_message_id(internet_id):
        raise MicrosoftProviderError("MICROSOFT_REPLY_MESSAGE_ID_INVALID")
    headers = _internet_headers(row)
    if headers.get("message-id") != [internet_id]:
        raise MicrosoftProviderError("MICROSOFT_REPLY_HEADER_CARDINALITY_INVALID")
    if len(headers.get("references", [])) > 1 or len(headers.get("in-reply-to", [])) > 1:
        raise MicrosoftProviderError("MICROSOFT_REPLY_HEADER_CARDINALITY_INVALID")
    references = headers.get("references", [None])[0]
    if references is not None:
        tokens = references.split()
        if len(tokens) > 50 or any(not _valid_message_id(item) for item in tokens):
            raise MicrosoftProviderError("MICROSOFT_REPLY_REFERENCES_INVALID")
    return internet_id, references


def _critical_reply_headers(row: Mapping[str, object], source_message_id: str) -> None:
    headers = _internet_headers(row)
    if headers.get("in-reply-to") != [source_message_id]:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    references = headers.get("references")
    if references is None or len(references) != 1:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    tokens = references[0].split()
    if (
        not tokens
        or tokens[-1] != source_message_id
        or len(tokens) > 50
        or any(not _valid_message_id(item) for item in tokens)
    ):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")


def _marker(row: Mapping[str, object]) -> str:
    values: list[str] = []
    for item in _optional_list(row, "singleValueExtendedProperties", maximum=20):
        prop = _dict(item)
        if _text(prop.get("id"), maximum=512) == _OPERATION_PROPERTY_ID:
            values.append(_text(prop.get("value"), maximum=128))
    if len(values) != 1:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    return values[0]


def _normalize_body(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _message_identity(
    row: Mapping[str, object], expected_id: str | None = None
) -> tuple[str, str, str]:
    message_id = _identifier(row.get("id"))
    if expected_id is not None and message_id != expected_id:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    conversation_id = _identifier(row.get("conversationId"))
    return message_id, conversation_id, _version(row)


def _message_summary(
    row: Mapping[str, object],
    *,
    attachment_count: int,
    non_inline_attachment_count: int,
) -> MessageSummary:
    message_id, conversation_id, version = _message_identity(row)
    received = _parse_instant(row.get("receivedDateTime"))
    sender = _recipient(row.get("from"))
    to, cc, _ = _all_recipients(row)
    parent = _identifier(row.get("parentFolderId"))
    has_attachments = row.get("hasAttachments")
    if type(has_attachments) is not bool or has_attachments != (non_inline_attachment_count > 0):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    return _contract(
        lambda: MessageSummary(
            message_id=message_id,
            thread_id=conversation_id,
            resource_version=version,
            received_at=received,
            subject=_text(row.get("subject") or "", maximum=8192, allow_empty=True),
            sender=sender,
            recipients=(*to, *cc),
            labels=(parent,),
            has_attachments=attachment_count > 0,
        )
    )


def _message_snapshot(
    row: Mapping[str, object],
    *,
    attachment_count: int,
    non_inline_attachment_count: int,
) -> MessageSnapshot:
    message_id, conversation_id, version = _message_identity(row)
    received = _parse_instant(row.get("receivedDateTime"))
    sender = _recipient(row.get("from"))
    to, cc, _ = _all_recipients(row)
    has_attachments = row.get("hasAttachments")
    if type(has_attachments) is not bool or has_attachments != (non_inline_attachment_count > 0):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    return _contract(
        lambda: MessageSnapshot(
            message_id=message_id,
            thread_id=conversation_id,
            resource_version=version,
            received_at=received,
            subject=_text(row.get("subject") or "", maximum=8192, allow_empty=True),
            sender=sender,
            recipients=(*to, *cc),
            body_text=_body_text(row.get("body")),
            attachment_count=attachment_count,
        )
    )


def _approved_message(
    row: Mapping[str, object],
    *,
    spec: object,
    expected_id: str,
    expected_folder_id: str,
    expected_marker: str,
    attachment_count: int,
    non_inline_attachment_count: int,
    is_draft: bool,
    expected_conversation_id: str | None = None,
    source_message_id: str | None = None,
) -> str:
    _, conversation_id, version = _message_identity(row, expected_id)
    if expected_conversation_id is not None and conversation_id != expected_conversation_id:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if _identifier(row.get("parentFolderId")) != expected_folder_id:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if row.get("isDraft") is not is_draft:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if _marker(row) != expected_marker:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    to, cc, bcc = _all_recipients(row)
    if tuple(item.casefold() for item in to) != tuple(item.casefold() for item in spec.to):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if tuple(item.casefold() for item in cc) != tuple(item.casefold() for item in spec.cc):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if tuple(item.casefold() for item in bcc) != tuple(item.casefold() for item in spec.bcc):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if _text(row.get("subject") or "", maximum=8192, allow_empty=True) != spec.subject:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if _normalize_body(_body_text(row.get("body"))) != _normalize_body(spec.body_text):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    has_attachments = row.get("hasAttachments")
    if (
        type(has_attachments) is not bool
        or has_attachments
        or attachment_count != 0
        or non_inline_attachment_count != 0
    ):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if source_message_id is not None and not is_draft:
        _critical_reply_headers(row, source_message_id)
    return version


def _mail_body(spec: object, marker: str) -> dict[str, Any]:
    def recipients(values: tuple[str, ...]) -> list[dict[str, dict[str, str]]]:
        return [{"emailAddress": {"address": value}} for value in values]

    return {
        "subject": spec.subject,
        "body": {"contentType": "Text", "content": spec.body_text},
        "toRecipients": recipients(spec.to),
        "ccRecipients": recipients(spec.cc),
        "bccRecipients": recipients(spec.bcc),
        "singleValueExtendedProperties": [{"id": _OPERATION_PROPERTY_ID, "value": marker}],
    }


def _next_page(
    row: Mapping[str, object],
    *,
    expected_path: str,
    base_query: tuple[tuple[str, str], ...],
    seen: set[str],
    page_count: int,
) -> tuple[tuple[str, str], ...] | None:
    value = row.get("@odata.nextLink")
    if value is None:
        return None
    link = _text(value, maximum=16_384)
    try:
        parsed = urlsplit(link)
        if (
            parsed.scheme != "https"
            or parsed.hostname != GRAPH_HOST
            or parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.path != expected_path
        ):
            raise ValueError
        pairs = tuple(parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True))
    except (ValueError, UnicodeError):
        raise MicrosoftProviderError("MICROSOFT_PAGINATION_INVALID") from None
    if len(pairs) > 40 or len({name for name, _ in pairs}) != len(pairs):
        raise MicrosoftProviderError("MICROSOFT_PAGINATION_INVALID")
    base = Counter(base_query)
    actual = Counter(pairs)
    extras = list((actual - base).elements())
    missing = list((base - actual).elements())
    if missing or len(extras) != 1 or extras[0][0] not in {"$skiptoken", "$skip"}:
        raise MicrosoftProviderError("MICROSOFT_PAGINATION_INVALID")
    token = extras[0][1]
    if not token or link in seen or page_count >= _MAX_PAGES:
        raise MicrosoftProviderError("MICROSOFT_PAGINATION_INVALID")
    seen.add(link)
    return pairs


def _graph_datetime(value: datetime, zone_name: str) -> dict[str, str]:
    _reject_ambiguous_local_time(value, zone_name)
    local = value.astimezone(ZoneInfo(zone_name))
    return {
        "dateTime": local.replace(tzinfo=None).isoformat(timespec="microseconds"),
        "timeZone": zone_name,
    }


def _reject_ambiguous_local_time(value: datetime, zone_name: str) -> None:
    try:
        zone = ZoneInfo(zone_name)
        local = value.astimezone(zone)
        wall = local.replace(tzinfo=None)
        first = wall.replace(tzinfo=zone, fold=0)
        second = wall.replace(tzinfo=zone, fold=1)
    except (ValueError, OverflowError, ZoneInfoNotFoundError):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED") from None
    if first.utcoffset() != second.utcoffset():
        raise MicrosoftProviderError("MICROSOFT_AMBIGUOUS_LOCAL_TIME_UNSUPPORTED")


def _validate_event_spec_times(spec: object) -> None:
    _reject_ambiguous_local_time(spec.starts_at, spec.time_zone)
    _reject_ambiguous_local_time(spec.ends_at, spec.time_zone)


def _parse_datetime_timezone(value: object) -> tuple[datetime, str]:
    row = _dict(value)
    raw = _text(row.get("dateTime"), maximum=128)
    zone_name = _text(row.get("timeZone"), maximum=100)
    try:
        zone = ZoneInfo(zone_name)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            first = parsed.replace(tzinfo=zone, fold=0)
            second = parsed.replace(tzinfo=zone, fold=1)
            if first.utcoffset() != second.utcoffset():
                raise MicrosoftProviderError("MICROSOFT_AMBIGUOUS_LOCAL_TIME_UNSUPPORTED")
            parsed = first
            round_trip = parsed.astimezone(timezone.utc).astimezone(zone)
            if (
                round_trip.replace(tzinfo=None) != parsed.replace(tzinfo=None)
                or round_trip.fold != parsed.fold
            ):
                raise ValueError
        else:
            parsed = parsed.astimezone(zone)
    except (ValueError, ZoneInfoNotFoundError):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED") from None
    return parsed, zone_name


def _event_attendees(
    row: Mapping[str, object],
    *,
    require_complete: bool,
) -> tuple[tuple[str, ...], dict[str, dict[str, Any]]]:
    if "attendees" not in row:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_ATTENDEES_INCOMPLETE")
    addresses: list[str] = []
    full: dict[str, dict[str, Any]] = {}
    for item in _list(row["attendees"], maximum=100):
        attendee = _dict(item)
        address = _recipient(attendee)
        key = address.casefold()
        if key in full:
            raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
        if require_complete:
            if "type" not in attendee or "status" not in attendee:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_ATTENDEES_INCOMPLETE")
            kind = _text(attendee.get("type"), maximum=32)
            if kind not in {"required", "optional", "resource"}:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_ATTENDEES_INCOMPLETE")
            status = _dict(attendee.get("status"))
            if "response" not in status or "time" not in status:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_ATTENDEES_INCOMPLETE")
            response = _text(status.get("response"), maximum=32)
            if response not in {
                "none",
                "organizer",
                "tentativelyAccepted",
                "accepted",
                "declined",
                "notResponded",
            }:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_ATTENDEES_INCOMPLETE")
            _parse_instant(status.get("time"))
        addresses.append(address)
        full[key] = attendee
    return tuple(addresses), full


def _detached_json(value: object) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED") from None


def _validate_location_row(value: object) -> dict[str, Any]:
    location = _dict(value)
    _text(location.get("displayName") or "", maximum=8192, allow_empty=True)
    for key in ("locationType", "uniqueId", "uniqueIdType"):
        field_value = location.get(key)
        if field_value is not None:
            _text(field_value, maximum=512, allow_empty=True)
    for key in ("address", "coordinates"):
        field_value = location.get(key)
        if field_value is not None:
            _dict(field_value)
    return _detached_json(location)


def _event_location_state(
    row: Mapping[str, object],
) -> tuple[str, dict[str, Any], tuple[dict[str, Any], ...]]:
    if "location" not in row or "locations" not in row:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_LOCATION_INCOMPLETE")
    primary = _validate_location_row(row["location"])
    locations = tuple(
        _validate_location_row(value) for value in _list(row["locations"], maximum=100)
    )
    display_name = _text(primary.get("displayName") or "", maximum=8192, allow_empty=True)
    return display_name, primary, locations


def _normalized_scalar_location(
    state: tuple[str, Mapping[str, object], Sequence[Mapping[str, object]]],
) -> bool:
    display_name, primary, locations = state
    exact_fields = {"displayName", "locationType", "uniqueId", "uniqueIdType"}

    def normalized_row(row: Mapping[str, object], *, unique_id_type: str) -> bool:
        return (
            set(row) == exact_fields
            and _text(row.get("displayName") or "", maximum=8192, allow_empty=True) == display_name
            and row.get("locationType") == "default"
            and row.get("uniqueId") == display_name
            and row.get("uniqueIdType") == unique_id_type
        )

    return (
        normalized_row(primary, unique_id_type="private")
        and len(locations) == 1
        and normalized_row(locations[0], unique_id_type="unknown")
    )


def _event_provider_state(
    row: Mapping[str, object],
) -> tuple[str, str, bool, bool, dict[str, Any]]:
    is_cancelled = row.get("isCancelled")
    is_organizer = row.get("isOrganizer")
    show_as = _text(row.get("showAs"), maximum=32)
    if (
        type(is_cancelled) is not bool
        or type(is_organizer) is not bool
        or show_as
        not in {
            "free",
            "tentative",
            "busy",
            "oof",
            "workingElsewhere",
            "unknown",
        }
    ):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    response_status = _dict(row.get("responseStatus"))
    response = _text(response_status.get("response"), maximum=32)
    if response not in {
        "none",
        "organizer",
        "tentativelyAccepted",
        "accepted",
        "declined",
        "notResponded",
    }:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    _parse_instant(response_status.get("time"))
    if is_organizer != (response == "organizer"):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if is_cancelled or response == "declined":
        status = "cancelled"
    elif response in {"none", "tentativelyAccepted", "notResponded"}:
        status = "tentative"
    else:
        status = "confirmed"
    return status, show_as, is_cancelled, is_organizer, _detached_json(response_status)


def _event(
    row: Mapping[str, object],
    *,
    calendar_id: str,
) -> EventSnapshot:
    event_id = _identifier(row.get("id"))
    version = _version(row)
    starts_at, start_zone = _parse_datetime_timezone(row.get("start"))
    ends_at, end_zone = _parse_datetime_timezone(row.get("end"))
    if start_zone != end_zone:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    attendees, _ = _event_attendees(row, require_complete=True)
    organizer_row = row.get("organizer")
    organizer = _recipient(organizer_row) if organizer_row is not None else None
    is_online_meeting = row.get("isOnlineMeeting")
    if type(is_online_meeting) is not bool:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
    status, _, _, _, _ = _event_provider_state(row)
    location, _, _ = _event_location_state(row)
    return _contract(
        lambda: EventSnapshot(
            event_id=event_id,
            calendar_id=calendar_id,
            resource_version=version,
            starts_at=starts_at,
            ends_at=ends_at,
            time_zone=start_zone,
            title=_text(row.get("subject") or "(untitled)", maximum=8192),
            description=_body_text(row.get("body")),
            location=location,
            attendees=attendees,
            organizer=organizer,
            status=status,
        )
    )


def _event_body(spec: object, *, transaction_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "subject": spec.title,
        "body": {"contentType": "Text", "content": spec.description},
        "start": _graph_datetime(spec.starts_at, spec.time_zone),
        "end": _graph_datetime(spec.ends_at, spec.time_zone),
        "location": {"displayName": spec.location},
        "attendees": [
            {"emailAddress": {"address": address}, "type": "required"} for address in spec.attendees
        ],
    }
    if transaction_id is not None:
        body["transactionId"] = transaction_id
    return body


def _approved_event(
    row: Mapping[str, object],
    *,
    spec: object,
    expected_id: str,
    expected_transaction_id: str | None = None,
    expected_existing_attendees: Mapping[str, Mapping[str, object]] | None = None,
    expected_provider_state: tuple[str, str, bool, bool, dict[str, Any]] | None = None,
    expected_location_state: tuple[str, dict[str, Any], tuple[dict[str, Any], ...]] | None = None,
    require_normalized_scalar_location: bool = False,
    require_organizer: bool = False,
) -> EventSnapshot:
    if _identifier(row.get("id")) != expected_id:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    snapshot = _event(
        row,
        calendar_id=spec.calendar_id,
    )
    expected = {item.casefold() for item in spec.attendees}
    actual = {item.casefold() for item in snapshot.attendees}
    equivalent = (
        snapshot.title == spec.title
        and snapshot.description == spec.description
        and snapshot.location == spec.location
        and snapshot.starts_at.astimezone(timezone.utc) == spec.starts_at.astimezone(timezone.utc)
        and snapshot.ends_at.astimezone(timezone.utc) == spec.ends_at.astimezone(timezone.utc)
        and snapshot.time_zone == spec.time_zone
        and actual == expected
        and len(snapshot.attendees) == len(expected)
    )
    if not equivalent:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if expected_transaction_id is not None:
        if _text(row.get("transactionId"), maximum=128) != expected_transaction_id:
            raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if expected_existing_attendees is not None:
        _, actual_rows = _event_attendees(row, require_complete=True)
        desired = {item.casefold() for item in spec.attendees}
        for address, expected_row in expected_existing_attendees.items():
            if address in desired and actual_rows.get(address) != expected_row:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    provider_state = _event_provider_state(row)
    if expected_provider_state is not None and provider_state != expected_provider_state:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if require_organizer and (
        provider_state[2]
        or not provider_state[3]
        or provider_state[4].get("response") != "organizer"
    ):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    location_state = _event_location_state(row)
    if expected_location_state is not None and location_state != expected_location_state:
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    if require_normalized_scalar_location and not _normalized_scalar_location(location_state):
        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
    return snapshot


def _event_patch(current: Mapping[str, object], spec: object) -> dict[str, Any]:
    snapshot = _event(
        current,
        calendar_id=spec.calendar_id,
    )
    patch: dict[str, Any] = {}
    if snapshot.title != spec.title:
        patch["subject"] = spec.title
    if snapshot.description != spec.description:
        if current.get("isOnlineMeeting") is True:
            # Microsoft documents that overwriting an online meeting body can
            # remove its meeting blob.  The neutral contract has no structured
            # blob-preservation field, so this mutation is deliberately denied.
            raise MicrosoftProviderError("MICROSOFT_ONLINE_MEETING_BODY_UPDATE_UNSUPPORTED")
        patch["body"] = {"contentType": "Text", "content": spec.description}
    if snapshot.location != spec.location:
        if not _normalized_scalar_location(_event_location_state(current)):
            raise MicrosoftProviderError("MICROSOFT_COMPLEX_LOCATION_UPDATE_UNSUPPORTED")
        patch["location"] = {"displayName": spec.location}
    if (
        snapshot.starts_at.astimezone(timezone.utc) != spec.starts_at.astimezone(timezone.utc)
        or snapshot.time_zone != spec.time_zone
    ):
        patch["start"] = _graph_datetime(spec.starts_at, spec.time_zone)
    if (
        snapshot.ends_at.astimezone(timezone.utc) != spec.ends_at.astimezone(timezone.utc)
        or snapshot.time_zone != spec.time_zone
    ):
        patch["end"] = _graph_datetime(spec.ends_at, spec.time_zone)
    current_addresses, current_rows = _event_attendees(current, require_complete=True)
    desired = {item.casefold() for item in spec.attendees}
    if {item.casefold() for item in current_addresses} != desired or len(current_addresses) != len(
        desired
    ):
        patch["attendees"] = [
            current_rows.get(
                address.casefold(),
                {"emailAddress": {"address": address}, "type": "required"},
            )
            for address in spec.attendees
        ]
    return patch


class MicrosoftConnectedAppProvider:
    """Typed Microsoft Graph v1.0 provider behind an opaque transport."""

    def __init__(
        self,
        transport: MicrosoftCredentialTransport,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        try:
            policy = getattr(transport, "security_policy", None)
        except Exception:
            raise ValueError("Microsoft transport policy attestation failed") from None
        if (
            type(policy) is not MicrosoftTransportSecurityPolicy
            or policy != MicrosoftTransportSecurityPolicy()
        ):
            raise ValueError("Microsoft transport has not attested the locked-down policy")
        self._transport = transport
        self._now = now
        if not callable(sleep):
            raise TypeError("Microsoft reconciliation sleeper must be callable")
        self._sleep = sleep

    async def _call(
        self,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: MicrosoftTransportRequest,
        *,
        effectful: bool = False,
    ) -> MicrosoftTransportResponse:
        if (
            account.owner_id != credential.owner_id
            or account.connection_id != credential.connection_id
            or account.provider is not credential.provider
            or credential.provider is not ConnectorProvider.MICROSOFT
        ):
            raise MicrosoftProviderError("MICROSOFT_CREDENTIAL_BINDING_MISMATCH")
        try:
            response = await self._transport.request(
                account=account,
                credential=credential,
                request=request,
            )
        except MicrosoftNotDispatched:
            raise MicrosoftProviderError(
                "MICROSOFT_TRANSPORT_NOT_DISPATCHED",
                retryable=True,
            ) from None
        except MicrosoftEffectUnknown:
            if effectful:
                raise MicrosoftEffectUnknown() from None
            raise MicrosoftProviderError(
                "MICROSOFT_TRANSPORT_UNAVAILABLE", retryable=True
            ) from None
        except Exception:
            if effectful:
                raise MicrosoftEffectUnknown() from None
            raise MicrosoftProviderError(
                "MICROSOFT_TRANSPORT_UNAVAILABLE", retryable=True
            ) from None
        if not isinstance(response, MicrosoftTransportResponse):
            if effectful:
                raise MicrosoftEffectUnknown()
            raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
        if effectful and (response.status == 429 or response.status >= 500):
            raise MicrosoftEffectUnknown()
        _response_error(response)
        return response

    def _mail_headers(self) -> tuple[tuple[str, str], ...]:
        return (("Prefer", _MAIL_PREFER),)

    def _calendar_headers(self, zone: str) -> tuple[tuple[str, str], ...]:
        return (
            (
                "Prefer",
                f'IdType="ImmutableId", outlook.timezone="{zone}", '
                'outlook.body-content-type="text"',
            ),
        )

    def _ambiguous(self, operation_id: str, resource: ConnectorResource, key: str):
        return AmbiguousProviderResult(
            operation_id=operation_id,
            provider=ConnectorProvider.MICROSOFT,
            resource=resource,
            idempotency_key_hash=_digest(key),
            observed_at=self._now(),
        )

    def _receipt(
        self,
        *,
        operation_id: str,
        resource: ConnectorResource,
        outcome: str,
        key: str,
        response: MicrosoftTransportResponse,
        resource_id: str,
        resource_version: str,
    ) -> ProviderReceipt:
        request_id = response.headers.get("request-id") or operation_id
        return _contract(
            lambda: ProviderReceipt(
                operation_id=operation_id,
                provider=ConnectorProvider.MICROSOFT,
                resource=resource,
                outcome=outcome,
                provider_request_id_hash=_digest(request_id),
                resource_id_hash=_digest(resource_id),
                resource_version=resource_version,
                idempotency_key_hash=_digest(key),
                observed_at=self._now(),
            )
        )

    async def _folder_id(self, account, credential, folder_id: str) -> str:
        path = f"{GRAPH_ROOT}/me/mailFolders/{quote(folder_id, safe='')}"
        response = await self._call(
            account,
            credential,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                path,
                (("$select", "id"),),
                self._mail_headers(),
            ),
        )
        result = _identifier(_dict(response.body).get("id"))
        if folder_id.casefold() not in _WELL_KNOWN_FOLDERS and result != folder_id:
            raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
        return result

    async def _attachment_count(
        self,
        account,
        credential,
        message_id: str,
    ) -> tuple[int, int]:
        path = f"{GRAPH_ROOT}/me/messages/{quote(message_id, safe='')}/attachments"
        base_query = (("$select", "id,isInline"), ("$top", str(_MAX_ATTACHMENTS)))
        query = base_query
        seen_links: set[str] = set()
        seen_ids: set[str] = set()
        page_count = 0
        count = 0
        non_inline_count = 0
        while True:
            response = await self._call(
                account,
                credential,
                MicrosoftTransportRequest("GET", GRAPH_HOST, path, query, self._mail_headers()),
            )
            page_count += 1
            page = _dict(response.body)
            for value in _optional_list(page, "value", maximum=_MAX_ATTACHMENTS):
                row = _dict(value)
                attachment_id = _identifier(row.get("id"))
                is_inline = row.get("isInline")
                if attachment_id in seen_ids or type(is_inline) is not bool:
                    raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
                seen_ids.add(attachment_id)
                count += 1
                if not is_inline:
                    non_inline_count += 1
                if count > _MAX_ATTACHMENTS:
                    raise MicrosoftProviderError("MICROSOFT_RESPONSE_TOO_LARGE")
            next_query = _next_page(
                page,
                expected_path=path,
                base_query=base_query,
                seen=seen_links,
                page_count=page_count,
            )
            if next_query is None:
                return count, non_inline_count
            query = next_query

    async def _read_message_row(
        self,
        account,
        credential,
        message_id: str,
    ) -> tuple[dict[str, Any], int, int, MicrosoftTransportResponse]:
        path = f"{GRAPH_ROOT}/me/messages/{quote(message_id, safe='')}"
        response = await self._call(
            account,
            credential,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                path,
                (
                    ("$select", _MAIL_SELECT),
                    (
                        "$expand",
                        f"singleValueExtendedProperties($filter=id eq '{_OPERATION_PROPERTY_ID}')",
                    ),
                ),
                self._mail_headers(),
            ),
        )
        row = _dict(response.body)
        _message_identity(row, message_id)
        count, non_inline_count = await self._attachment_count(account, credential, message_id)
        return row, count, non_inline_count, response

    async def search_mail(self, *, account, credential, request: MailSearchRequest):
        _resource(account, ConnectorResource.MAIL)
        query = request.query
        summaries: list[MessageSummary] = []
        seen_messages: set[str] = set()
        resolved_folders: set[str] = set()
        for requested_folder in query.folder_ids:
            folder_id = await self._folder_id(account, credential, requested_folder)
            if folder_id in resolved_folders:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
            resolved_folders.add(folder_id)
            path = f"{GRAPH_ROOT}/me/mailFolders/{quote(requested_folder, safe='')}/messages"
            remaining = query.limit - len(summaries)
            base: list[tuple[str, str]] = [("$select", "id"), ("$top", str(remaining))]
            if query.query:
                # Graph rejects message requests that combine $search with
                # $filter or $orderby.  Date and folder constraints are
                # authoritatively rechecked on each full immutable-ID read.
                escaped = query.query.replace("\\", "\\\\").replace('"', '\\"')
                base.append(("$search", f'"{escaped}"'))
            else:
                base.append(("$orderby", "receivedDateTime desc"))
                filters: list[str] = []
                if query.after is not None:
                    filters.append(
                        "receivedDateTime gt "
                        + query.after.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    )
                if query.before is not None:
                    filters.append(
                        "receivedDateTime lt "
                        + query.before.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    )
                if filters:
                    base.append(("$filter", " and ".join(filters)))
            base_query = tuple(base)
            page_query = base_query
            seen_links: set[str] = set()
            page_count = 0
            while len(summaries) < query.limit:
                response = await self._call(
                    account,
                    credential,
                    MicrosoftTransportRequest(
                        "GET", GRAPH_HOST, path, page_query, self._mail_headers()
                    ),
                )
                page_count += 1
                page = _dict(response.body)
                for item in _optional_list(page, "value", maximum=query.limit):
                    message_id = _identifier(_dict(item).get("id"))
                    if message_id in seen_messages:
                        raise MicrosoftProviderError("MICROSOFT_PAGINATION_INVALID")
                    seen_messages.add(message_id)
                    row, attachment_count, non_inline_count, _ = await self._read_message_row(
                        account, credential, message_id
                    )
                    if _identifier(row.get("parentFolderId")) != folder_id:
                        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
                    received = _parse_instant(row.get("receivedDateTime")).astimezone(timezone.utc)
                    outside = (
                        query.after is not None and received <= query.after.astimezone(timezone.utc)
                    ) or (
                        query.before is not None
                        and received >= query.before.astimezone(timezone.utc)
                    )
                    if outside:
                        if query.query:
                            continue
                        raise MicrosoftProviderError("MICROSOFT_RESPONSE_OUT_OF_BOUNDS")
                    summaries.append(
                        _message_summary(
                            row,
                            attachment_count=attachment_count,
                            non_inline_attachment_count=non_inline_count,
                        )
                    )
                    if len(summaries) >= query.limit:
                        return tuple(summaries)
                next_query = _next_page(
                    page,
                    expected_path=path,
                    base_query=base_query,
                    seen=seen_links,
                    page_count=page_count,
                )
                if next_query is None:
                    break
                page_query = next_query
        return tuple(summaries)

    async def get_message(self, *, account, credential, request: MailGetRequest):
        _resource(account, ConnectorResource.MAIL)
        row, attachment_count, non_inline_count, _ = await self._read_message_row(
            account, credential, request.message_id
        )
        result = _message_snapshot(
            row,
            attachment_count=attachment_count,
            non_inline_attachment_count=non_inline_count,
        )
        if (
            request.expected_resource_version is not None
            and result.resource_version != request.expected_resource_version
        ):
            raise MicrosoftProviderError("MICROSOFT_RESOURCE_VERSION_CONFLICT")
        return result

    async def create_draft(
        self, *, account, credential, request: MailDraftRequest, operation_id, idempotency_key
    ):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account,
            credential=credential,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
        )
        _resource(account, ConnectorResource.MAIL)
        drafts_id = await self._folder_id(account, credential, "drafts")
        marker = _digest(f"mail.draft:{operation_id}:{idempotency_key}")
        try:
            response = await self._call(
                account,
                credential,
                MicrosoftTransportRequest(
                    "POST",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/messages",
                    headers=self._mail_headers(),
                    json_body=_mail_body(request.spec, marker),
                ),
                effectful=True,
            )
        except MicrosoftEffectUnknown:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        try:
            if response.status != 201:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_STATUS_MISMATCH")
            created = _dict(response.body)
            message_id, _, _ = _message_identity(created)
            row, count, non_inline_count, read_response = await self._read_message_row(
                account, credential, message_id
            )
            version = _approved_message(
                row,
                spec=request.spec,
                expected_id=message_id,
                expected_folder_id=drafts_id,
                expected_marker=marker,
                attachment_count=count,
                non_inline_attachment_count=non_inline_count,
                is_draft=True,
            )
            return self._receipt(
                operation_id=operation_id,
                resource=ConnectorResource.MAIL,
                outcome="drafted",
                key=idempotency_key,
                response=read_response,
                resource_id=message_id,
                resource_version=version,
            )
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)

    async def _send_prepared_draft(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        spec: object,
        operation_id: str,
        idempotency_key: str,
        draft_id: str,
        drafts_id: str,
        sent_id: str,
        marker: str,
        expected_conversation_id: str | None = None,
        source_message_id: str | None = None,
    ):
        try:
            draft_row, count, non_inline_count, _ = await self._read_message_row(
                account, credential, draft_id
            )
            _approved_message(
                draft_row,
                spec=spec,
                expected_id=draft_id,
                expected_folder_id=drafts_id,
                expected_marker=marker,
                attachment_count=count,
                non_inline_attachment_count=non_inline_count,
                is_draft=True,
                expected_conversation_id=expected_conversation_id,
            )
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        try:
            await self._call(
                account,
                credential,
                MicrosoftTransportRequest(
                    "POST",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/messages/{quote(draft_id, safe='')}/send",
                    headers=self._mail_headers(),
                ),
                effectful=True,
            )
        except MicrosoftEffectUnknown:
            # Acceptance may have been received by Graph.  Never redispatch;
            # reconcile only by the immutable ID that was proven pre-send.
            pass
        return await self._reconcile_sent_draft(
            account=account,
            credential=credential,
            spec=spec,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            draft_id=draft_id,
            sent_id=sent_id,
            marker=marker,
            expected_conversation_id=expected_conversation_id,
            source_message_id=source_message_id,
        )

    async def _reconcile_sent_draft(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        spec: object,
        operation_id: str,
        idempotency_key: str,
        draft_id: str,
        sent_id: str,
        marker: str,
        expected_conversation_id: str | None,
        source_message_id: str | None,
    ):
        """Poll the immutable ID briefly; never recreate or resend an uncertain message."""

        for delay in _SEND_RECONCILIATION_DELAYS:
            try:
                if delay:
                    # The runtime may cancel this await at its execution
                    # deadline; cancellation is intentionally not swallowed.
                    await self._sleep(delay)
                (
                    sent_row,
                    sent_count,
                    sent_non_inline_count,
                    read_response,
                ) = await self._read_message_row(account, credential, draft_id)
                version = _approved_message(
                    sent_row,
                    spec=spec,
                    expected_id=draft_id,
                    expected_folder_id=sent_id,
                    expected_marker=marker,
                    attachment_count=sent_count,
                    non_inline_attachment_count=sent_non_inline_count,
                    is_draft=False,
                    expected_conversation_id=expected_conversation_id,
                    source_message_id=source_message_id,
                )
                return self._receipt(
                    operation_id=operation_id,
                    resource=ConnectorResource.MAIL,
                    outcome="sent",
                    key=idempotency_key,
                    response=read_response,
                    resource_id=draft_id,
                    resource_version=version,
                )
            except Exception:
                continue
        return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)

    async def send_mail(
        self, *, account, credential, request: MailSendRequest, operation_id, idempotency_key
    ):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account,
            credential=credential,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
        )
        _resource(account, ConnectorResource.MAIL)
        drafts_id = await self._folder_id(account, credential, "drafts")
        sent_id = await self._folder_id(account, credential, "sentitems")
        marker = _digest(f"mail.send:{operation_id}:{idempotency_key}")
        try:
            response = await self._call(
                account,
                credential,
                MicrosoftTransportRequest(
                    "POST",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/messages",
                    headers=self._mail_headers(),
                    json_body=_mail_body(request.spec, marker),
                ),
                effectful=True,
            )
        except MicrosoftEffectUnknown:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        try:
            if response.status != 201:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_STATUS_MISMATCH")
            created = _dict(response.body)
            draft_id, conversation_id, _ = _message_identity(created)
            if _identifier(created.get("parentFolderId")) != drafts_id:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        return await self._send_prepared_draft(
            account=account,
            credential=credential,
            spec=request.spec,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            draft_id=draft_id,
            drafts_id=drafts_id,
            sent_id=sent_id,
            marker=marker,
            expected_conversation_id=conversation_id,
        )

    async def reply_mail(
        self, *, account, credential, request: MailReplyRequest, operation_id, idempotency_key
    ):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account,
            credential=credential,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
        )
        _resource(account, ConnectorResource.MAIL)
        spec = request.spec
        source_id = spec.reply_to_message_id or ""
        source_row, _, _, _ = await self._read_message_row(account, credential, source_id)
        _, source_conversation, source_version = _message_identity(source_row, source_id)
        if source_version != spec.expected_resource_version:
            raise MicrosoftProviderError("MICROSOFT_RESOURCE_VERSION_CONFLICT")
        source_message_id, _ = _critical_source_headers(source_row)
        drafts_id = await self._folder_id(account, credential, "drafts")
        sent_id = await self._folder_id(account, credential, "sentitems")
        marker = _digest(f"mail.reply:{operation_id}:{idempotency_key}")
        try:
            create_response = await self._call(
                account,
                credential,
                MicrosoftTransportRequest(
                    "POST",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/messages/{quote(source_id, safe='')}/createReply",
                    headers=self._mail_headers(),
                ),
                effectful=True,
            )
        except MicrosoftEffectUnknown:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        try:
            if create_response.status != 201:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_STATUS_MISMATCH")
            create_row = _dict(create_response.body)
            draft_id, conversation_id, draft_version = _message_identity(create_row)
            if (
                conversation_id != source_conversation
                or _identifier(create_row.get("parentFolderId")) != drafts_id
                or create_row.get("isDraft") is not True
            ):
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        try:
            patch_response = await self._call(
                account,
                credential,
                MicrosoftTransportRequest(
                    "PATCH",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/messages/{quote(draft_id, safe='')}",
                    headers=(*self._mail_headers(), ("If-Match", draft_version)),
                    json_body=_mail_body(spec, marker),
                ),
                effectful=True,
            )
        except MicrosoftEffectUnknown:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        if patch_response.status != 200:
            return self._ambiguous(operation_id, ConnectorResource.MAIL, idempotency_key)
        return await self._send_prepared_draft(
            account=account,
            credential=credential,
            spec=spec,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            draft_id=draft_id,
            drafts_id=drafts_id,
            sent_id=sent_id,
            marker=marker,
            expected_conversation_id=source_conversation,
            source_message_id=source_message_id,
        )

    async def list_events(self, *, account, credential, request: CalendarListRequest):
        _resource(account, ConnectorResource.CALENDAR)
        results: list[EventSnapshot] = []
        seen_events: set[tuple[str, str]] = set()
        start = request.query.starts_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end = request.query.ends_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        for calendar_id in request.query.calendar_ids:
            path = f"{GRAPH_ROOT}/me/calendars/{quote(calendar_id, safe='')}/calendarView"
            remaining = request.query.limit - len(results)
            base_query = (
                ("startDateTime", start),
                ("endDateTime", end),
                ("$top", str(remaining)),
                ("$select", _EVENT_SELECT),
                ("$orderby", "start/dateTime"),
            )
            page_query = base_query
            seen_links: set[str] = set()
            page_count = 0
            while len(results) < request.query.limit:
                response = await self._call(
                    account,
                    credential,
                    MicrosoftTransportRequest(
                        "GET",
                        GRAPH_HOST,
                        path,
                        page_query,
                        self._calendar_headers(request.query.time_zone),
                    ),
                )
                page_count += 1
                page = _dict(response.body)
                for item in _optional_list(page, "value", maximum=request.query.limit):
                    row = _dict(item)
                    event = _event(row, calendar_id=calendar_id)
                    if event.time_zone != request.query.time_zone:
                        raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
                    key = (calendar_id, event.event_id)
                    if key in seen_events:
                        raise MicrosoftProviderError("MICROSOFT_PAGINATION_INVALID")
                    seen_events.add(key)
                    if not (
                        event.starts_at.astimezone(timezone.utc)
                        < request.query.ends_at.astimezone(timezone.utc)
                        and event.ends_at.astimezone(timezone.utc)
                        > request.query.starts_at.astimezone(timezone.utc)
                    ):
                        raise MicrosoftProviderError("MICROSOFT_RESPONSE_OUT_OF_BOUNDS")
                    results.append(event)
                    if len(results) >= request.query.limit:
                        return tuple(results)
                next_query = _next_page(
                    page,
                    expected_path=path,
                    base_query=base_query,
                    seen=seen_links,
                    page_count=page_count,
                )
                if next_query is None:
                    break
                page_query = next_query
        return tuple(results)

    async def free_busy(self, *, account, credential, request: CalendarFreeBusyRequest):
        _resource(account, ConnectorResource.CALENDAR)
        if account.account_kind is not ConnectorAccountKind.WORK_SCHOOL:
            raise MicrosoftProviderError("MICROSOFT_FREEBUSY_ACCOUNT_UNSUPPORTED")
        query = request.query
        response = await self._call(
            account,
            credential,
            MicrosoftTransportRequest(
                "POST",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/calendar/getSchedule",
                headers=self._calendar_headers(query.time_zone),
                json_body={
                    "schedules": list(query.calendar_ids),
                    "startTime": _graph_datetime(query.starts_at, query.time_zone),
                    "endTime": _graph_datetime(query.ends_at, query.time_zone),
                    "availabilityViewInterval": 5,
                },
            ),
        )
        page = _dict(response.body)
        rows = _optional_list(page, "value", maximum=len(query.calendar_ids))
        expected = {item.casefold(): item for item in query.calendar_ids}
        seen: set[str] = set()
        windows: list[FreeBusyWindow] = []
        status_map = {
            "busy": "busy",
            "tentative": "tentative",
            "oof": "out_of_office",
            "workingElsewhere": "working_elsewhere",
        }
        for item in rows:
            schedule = _dict(item)
            schedule_id = _text(schedule.get("scheduleId"), maximum=512)
            folded = schedule_id.casefold()
            if folded not in expected or folded in seen:
                raise MicrosoftProviderError("MICROSOFT_FREEBUSY_INCOMPLETE")
            seen.add(folded)
            error = schedule.get("error")
            if error is not None and error != {}:
                raise MicrosoftProviderError("MICROSOFT_FREEBUSY_REJECTED")
            for value in _optional_list(schedule, "scheduleItems", maximum=1000):
                row = _dict(value)
                status = _text(row.get("status"), maximum=32)
                if status == "free":
                    continue
                if status not in status_map:
                    raise MicrosoftProviderError("MICROSOFT_RESPONSE_MALFORMED")
                starts_at, start_zone = _parse_datetime_timezone(row.get("start"))
                ends_at, end_zone = _parse_datetime_timezone(row.get("end"))
                if start_zone != query.time_zone or end_zone != query.time_zone:
                    raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
                if not (
                    query.starts_at.astimezone(timezone.utc)
                    <= starts_at.astimezone(timezone.utc)
                    < ends_at.astimezone(timezone.utc)
                    <= query.ends_at.astimezone(timezone.utc)
                ):
                    raise MicrosoftProviderError("MICROSOFT_RESPONSE_OUT_OF_BOUNDS")
                windows.append(
                    _contract(
                        lambda schedule_id=schedule_id, starts_at=starts_at, ends_at=ends_at, status=status: (
                            FreeBusyWindow(
                                schedule_id,
                                starts_at,
                                ends_at,
                                status_map[status],
                            )
                        )
                    )
                )
                if len(windows) > 1000:
                    raise MicrosoftProviderError("MICROSOFT_RESPONSE_TOO_LARGE")
        if seen != set(expected):
            raise MicrosoftProviderError("MICROSOFT_FREEBUSY_INCOMPLETE")
        return tuple(windows)

    async def _read_event(
        self, account, credential, calendar_id: str, event_id: str, zone: str
    ) -> tuple[dict[str, Any], MicrosoftTransportResponse]:
        response = await self._call(
            account,
            credential,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
                (("$select", _EVENT_SELECT),),
                self._calendar_headers(zone),
            ),
        )
        row = _dict(response.body)
        if _identifier(row.get("id")) != event_id:
            raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
        return row, response

    async def get_event(self, *, account, credential, request: CalendarGetRequest):
        _resource(account, ConnectorResource.CALENDAR)
        row, _ = await self._read_event(
            account, credential, request.calendar_id, request.event_id, "UTC"
        )
        event = _event(row, calendar_id=request.calendar_id)
        if event.time_zone != "UTC":
            raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
        if (
            request.expected_resource_version is not None
            and event.resource_version != request.expected_resource_version
        ):
            raise MicrosoftProviderError("MICROSOFT_RESOURCE_VERSION_CONFLICT")
        return event

    async def create_event(
        self, *, account, credential, request: CalendarCreateRequest, operation_id, idempotency_key
    ):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account,
            credential=credential,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
        )
        _resource(account, ConnectorResource.CALENDAR)
        spec = request.spec
        _validate_event_spec_times(spec)
        transaction_id = _digest(f"calendar.create:{operation_id}:{idempotency_key}")
        try:
            response = await self._call(
                account,
                credential,
                MicrosoftTransportRequest(
                    "POST",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/calendars/{quote(spec.calendar_id, safe='')}/events",
                    headers=self._calendar_headers(spec.time_zone),
                    json_body=_event_body(spec, transaction_id=transaction_id),
                ),
                effectful=True,
            )
        except MicrosoftEffectUnknown:
            return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)
        try:
            if response.status != 201:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_STATUS_MISMATCH")
            created = _dict(response.body)
            event_id = _identifier(created.get("id"))
            if _text(created.get("transactionId"), maximum=128) != transaction_id:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
            row, read_response = await self._read_event(
                account, credential, spec.calendar_id, event_id, spec.time_zone
            )
            event = _approved_event(
                row,
                spec=spec,
                expected_id=event_id,
                expected_transaction_id=transaction_id,
                require_normalized_scalar_location=True,
                require_organizer=True,
            )
            return self._receipt(
                operation_id=operation_id,
                resource=ConnectorResource.CALENDAR,
                outcome="created",
                key=idempotency_key,
                response=read_response,
                resource_id=event_id,
                resource_version=event.resource_version,
            )
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)

    async def update_event(
        self, *, account, credential, request: CalendarUpdateRequest, operation_id, idempotency_key
    ):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account,
            credential=credential,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
        )
        _resource(account, ConnectorResource.CALENDAR)
        spec = request.spec
        event_id = spec.source_event_id or ""
        current, current_response = await self._read_event(
            account, credential, spec.calendar_id, event_id, spec.time_zone
        )
        current_version = _version(current)
        if current_version != spec.expected_resource_version:
            raise MicrosoftProviderError("MICROSOFT_RESOURCE_VERSION_CONFLICT")
        _validate_event_spec_times(spec)
        current_event = _event(current, calendar_id=spec.calendar_id)
        provider_state = _event_provider_state(current)
        location_state = _event_location_state(current)
        location_changed = current_event.location != spec.location
        patch = _event_patch(current, spec)
        _, existing_attendees = _event_attendees(current, require_complete=True)
        if not patch:
            event = _approved_event(
                current,
                spec=spec,
                expected_id=event_id,
                expected_provider_state=provider_state,
                expected_location_state=location_state,
            )
            return self._receipt(
                operation_id=operation_id,
                resource=ConnectorResource.CALENDAR,
                outcome="updated",
                key=idempotency_key,
                response=current_response,
                resource_id=event_id,
                resource_version=event.resource_version,
            )
        try:
            response = await self._call(
                account,
                credential,
                MicrosoftTransportRequest(
                    "PATCH",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/calendars/{quote(spec.calendar_id, safe='')}/events/{quote(event_id, safe='')}",
                    headers=(
                        *self._calendar_headers(spec.time_zone),
                        ("If-Match", current_version),
                    ),
                    json_body=patch,
                ),
                effectful=True,
            )
        except MicrosoftEffectUnknown:
            return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)
        if response.status != 200:
            return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)
        try:
            row, read_response = await self._read_event(
                account, credential, spec.calendar_id, event_id, spec.time_zone
            )
            event = _approved_event(
                row,
                spec=spec,
                expected_id=event_id,
                expected_existing_attendees=existing_attendees,
                expected_provider_state=provider_state,
                expected_location_state=None if location_changed else location_state,
                require_normalized_scalar_location=location_changed,
            )
            return self._receipt(
                operation_id=operation_id,
                resource=ConnectorResource.CALENDAR,
                outcome="updated",
                key=idempotency_key,
                response=read_response,
                resource_id=event_id,
                resource_version=event.resource_version,
            )
        except Exception:
            return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)

    async def cancel_event(
        self, *, account, credential, request: CalendarCancelRequest, operation_id, idempotency_key
    ):
        operation_id, idempotency_key = validate_operation_inputs(
            account=account,
            credential=credential,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
        )
        _resource(account, ConnectorResource.CALENDAR)
        current, _ = await self._read_event(
            account, credential, request.calendar_id, request.event_id, "UTC"
        )
        if _version(current) != request.expected_resource_version:
            raise MicrosoftProviderError("MICROSOFT_RESOURCE_VERSION_CONFLICT")
        _, _, _, is_organizer, _ = _event_provider_state(current)
        if not is_organizer:
            raise MicrosoftProviderError("MICROSOFT_EVENT_CANCEL_ATTENDEE_UNSUPPORTED")
        try:
            response = await self._call(
                account,
                credential,
                MicrosoftTransportRequest(
                    "DELETE",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/calendars/{quote(request.calendar_id, safe='')}/events/{quote(request.event_id, safe='')}",
                    headers=(
                        *self._calendar_headers("UTC"),
                        ("If-Match", request.expected_resource_version),
                    ),
                ),
                effectful=True,
            )
        except MicrosoftEffectUnknown:
            return await self._reconcile_cancel(
                account,
                credential,
                request,
                operation_id,
                idempotency_key,
            )
        except MicrosoftProviderError as exc:
            if exc.code == "MICROSOFT_RESOURCE_NOT_FOUND":
                return await self._reconcile_cancel(
                    account,
                    credential,
                    request,
                    operation_id,
                    idempotency_key,
                )
            raise
        if response.status == 204 and response.body is None:
            return self._receipt(
                operation_id=operation_id,
                resource=ConnectorResource.CALENDAR,
                outcome="cancelled",
                key=idempotency_key,
                response=response,
                resource_id=request.event_id,
                resource_version=request.expected_resource_version,
            )
        return await self._reconcile_cancel(
            account,
            credential,
            request,
            operation_id,
            idempotency_key,
        )

    async def _reconcile_cancel(self, account, credential, request, operation_id, idempotency_key):
        try:
            response = await self._call(
                account,
                credential,
                MicrosoftTransportRequest(
                    "GET",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/events/{quote(request.event_id, safe='')}",
                    (("$select", "id"),),
                    self._calendar_headers("UTC"),
                ),
            )
            if _identifier(_dict(response.body).get("id")) != request.event_id:
                raise MicrosoftProviderError("MICROSOFT_RESPONSE_RESOURCE_MISMATCH")
        except MicrosoftProviderError as exc:
            if exc.code == "MICROSOFT_RESOURCE_NOT_FOUND":
                return self._receipt(
                    operation_id=operation_id,
                    resource=ConnectorResource.CALENDAR,
                    outcome="cancelled",
                    key=idempotency_key,
                    response=MicrosoftTransportResponse(204, None),
                    resource_id=request.event_id,
                    resource_version=request.expected_resource_version,
                )
        except Exception:
            pass
        return self._ambiguous(operation_id, ConnectorResource.CALENDAR, idempotency_key)
