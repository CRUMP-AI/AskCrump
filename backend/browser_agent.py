"""Server-side page reader behind the ``browser.read`` capability.

This is a read, not browsing: the server fetches one public page over
HTTP, extracts its readable text, and returns it for the run ledger.
There is no browser session, no JavaScript, no cookies, and no form or
click interaction here -- that surface is ``browser.act``, which stays
planned until the interactive browser lands.

Safety model (fail closed, checked on every hop):

- Only ``http``/``https`` URLs are fetched.
- The host is resolved before every request -- including after each
  redirect -- and the fetch is blocked when any answer is a private,
  loopback, link-local, reserved, multicast, or otherwise non-global
  address. Literal IP hosts are checked directly.
- Redirects are followed manually, at most three, so the address check
  above runs for every destination.
- Responses are capped at 2 MB, time out after 10 seconds, and must be
  ``text/html`` or ``text/plain``.

Text extraction uses only the standard library (``html.parser``):
script/style and navigation boilerplate are dropped, whitespace is
collapsed, and the extracted text is capped at 20,000 characters.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from html.parser import HTMLParser
import inspect
import ipaddress
import json
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

CAPABILITY_ID = 'browser.read'

TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 20_000
# The run ledger fences stored payloads at MAX_PAYLOAD_BYTES in
# backend/agent_run_service.py; execute() keeps its serialized result
# inside the same bound.
MAX_RESULT_BYTES = 16_000
ALLOWED_CONTENT_TYPES = frozenset({'text/html', 'text/plain'})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
REQUEST_HEADERS = {
    'User-Agent': 'AskCrump/1.0 (server-side page reader)',
    'Accept': 'text/html, text/plain',
}

# A resolver maps a hostname to the IP address strings it answers with.
# It may be a plain callable or a coroutine callable; tests inject a
# fake so no real DNS or network is ever touched.
Resolver = Callable[[str], Any]


class BrowserAgentError(RuntimeError):
    def __init__(self, message: str, code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def _blocked(message: str = 'That page cannot be fetched.') -> BrowserAgentError:
    return BrowserAgentError(message, 'BROWSER_URL_BLOCKED', 400)


def _fetch_failed(message: str = 'The page could not be fetched.') -> BrowserAgentError:
    return BrowserAgentError(message, 'BROWSER_FETCH_FAILED', 502)


async def _default_resolver(hostname: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in addresses:
            addresses.append(address)
    return addresses


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split('%', 1)[0])
    except ValueError:
        return False
    return bool(address.is_global)


async def _resolve(hostname: str, resolver: Resolver) -> list[str]:
    try:
        result = resolver(hostname)
        if inspect.isawaitable(result):
            result = await result
    except BrowserAgentError:
        raise
    except Exception as exc:
        raise _fetch_failed('The page host could not be resolved.') from exc
    addresses = [str(item) for item in (result or [])]
    if not addresses:
        raise _fetch_failed('The page host could not be resolved.')
    return addresses


async def _ensure_public_url(url: str, resolver: Resolver) -> str:
    """Validate one fetch hop and return the URL unchanged.

    Raises BROWSER_URL_BLOCKED for a non-http(s) scheme, a URL carrying
    credentials, a malformed host, or any resolved address that is not
    a public (global) address.
    """
    try:
        parsed = urlparse(str(url or ''))
    except ValueError as exc:
        raise _blocked('That address is not a valid page URL.') from exc
    if parsed.scheme not in {'http', 'https'}:
        raise _blocked('Only http and https pages can be read.')
    if parsed.username or parsed.password:
        raise _blocked('Page URLs with embedded credentials cannot be read.')
    hostname = parsed.hostname
    if not hostname:
        raise _blocked('That address does not name a page host.')
    try:
        ipaddress.ip_address(hostname)
        addresses = [hostname]
    except ValueError:
        addresses = await _resolve(hostname, resolver)
    if any(not _is_public_address(address) for address in addresses):
        raise _blocked('That page resolves to a non-public address.')
    return url


_SKIP_TAGS = frozenset(
    {
        'script', 'style', 'nav', 'noscript', 'template', 'svg', 'iframe',
        'form', 'header', 'footer', 'aside', 'head', 'button', 'select',
        'textarea',
    }
)
_BLOCK_TAGS = frozenset(
    {
        'p', 'div', 'section', 'article', 'main', 'li', 'ul', 'ol', 'tr',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'table',
    }
)


class _TextExtractor(HTMLParser):
    """Collect <title> and readable body text, skipping boilerplate."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == 'title':
            self._in_title = True
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == 'br' and not self._skip_depth:
            self.text_parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag == 'title':
            self._in_title = False
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS and not self._skip_depth:
            self.text_parts.append('\n')

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip_depth:
            self.text_parts.append(data)

    @property
    def title(self) -> str:
        return re.sub(r'\s+', ' ', ''.join(self.title_parts)).strip()

    @property
    def text(self) -> str:
        return re.sub(r'\s+', ' ', ''.join(self.text_parts)).strip()


def _extract(html_text: str) -> tuple[str, str]:
    parser = _TextExtractor()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:
        # Malformed markup still yields whatever text was collected.
        pass
    return parser.title, parser.text[:MAX_TEXT_CHARS]


def _decode(content: bytes, content_type: str) -> str:
    charset = 'utf-8'
    for part in content_type.split(';')[1:]:
        name, _, value = part.strip().partition('=')
        if name.strip().lower() == 'charset' and value.strip():
            charset = value.strip().strip('"')
    try:
        return content.decode(charset, errors='replace')
    except (LookupError, UnicodeDecodeError):
        return content.decode('utf-8', errors='replace')


class BrowserAgent:
    """Fetch one public page and return its readable text.

    ``http_client`` and ``resolver`` are injectable so tests can drive
    every path with a fake transport and fake DNS answers.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self._client = http_client
        self._resolver: Resolver = resolver or _default_resolver

    async def _fetch_once(
        self, client: Any, url: str
    ) -> tuple[int, Any, bytes]:
        """Fetch one hop without following redirects, enforcing the cap."""
        if hasattr(client, 'stream'):
            async with client.stream(
                'GET', url, headers=REQUEST_HEADERS, follow_redirects=False
            ) as response:
                declared = response.headers.get('content-length')
                if declared is not None:
                    try:
                        declared_size = int(declared)
                    except ValueError:
                        declared_size = 0
                    if declared_size > MAX_RESPONSE_BYTES:
                        raise BrowserAgentError(
                            'That page is too large to read.',
                            'BROWSER_TOO_LARGE',
                            502,
                        )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise BrowserAgentError(
                            'That page is too large to read.',
                            'BROWSER_TOO_LARGE',
                            502,
                        )
                return response.status_code, response.headers, bytes(body)
        request = getattr(client, 'get', None) or client.request
        if request is client.request:
            response = await request(
                'GET', url, headers=REQUEST_HEADERS, follow_redirects=False
            )
        else:
            response = await request(
                url, headers=REQUEST_HEADERS, follow_redirects=False
            )
        content = bytes(response.content or b'')
        if len(content) > MAX_RESPONSE_BYTES:
            raise BrowserAgentError(
                'That page is too large to read.', 'BROWSER_TOO_LARGE', 502
            )
        return response.status_code, response.headers, content

    async def read_page(self, user_id: str, url: str) -> dict[str, Any]:
        """Fetch ``url`` and return its readable content.

        Returns ``{finalUrl, title, text, fetchedAt, bytes}``. This is a
        server-side read of a single public page; it is not interactive
        browsing and runs no page scripts.
        """
        del user_id  # Reads are per-URL; the caller owns run attribution.
        current = str(url or '').strip()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS, follow_redirects=False
        )
        try:
            redirects = 0
            while True:
                await _ensure_public_url(current, self._resolver)
                try:
                    status, headers, content = await self._fetch_once(client, current)
                except BrowserAgentError:
                    raise
                except httpx.HTTPError as exc:
                    raise _fetch_failed() from exc
                if status in REDIRECT_STATUSES:
                    location = headers.get('location') if headers else None
                    if not location:
                        raise _fetch_failed('The page redirected without a destination.')
                    redirects += 1
                    if redirects > MAX_REDIRECTS:
                        raise _fetch_failed('The page redirected too many times.')
                    current = urljoin(current, str(location))
                    continue
                break
        finally:
            if owns_client:
                await client.aclose()
        if status >= 400:
            raise _fetch_failed(f'The page returned status {status}.')
        content_type = ''
        if headers is not None:
            content_type = str(headers.get('content-type') or '')
        media_type = content_type.split(';', 1)[0].strip().lower()
        if media_type not in ALLOWED_CONTENT_TYPES:
            raise BrowserAgentError(
                'Only HTML and plain-text pages can be read.',
                'BROWSER_UNSUPPORTED_TYPE',
                502,
            )
        decoded = _decode(content, content_type)
        if media_type == 'text/html':
            title, text = _extract(decoded)
        else:
            title = ''
            text = re.sub(r'\s+', ' ', decoded).strip()[:MAX_TEXT_CHARS]
        return {
            'finalUrl': current,
            'title': title,
            'text': text,
            'fetchedAt': datetime.now(timezone.utc).isoformat(),
            'bytes': len(content),
        }

    async def execute(
        self, capability_id: str, user_id: str, payload: Any
    ) -> dict[str, Any]:
        """Adapter entry point used by the run executor for browser.read.

        Validates the ``{url}`` payload, performs the read, and returns
        a redacted summary plus the extracted text. The stored text is
        truncated so the serialized result stays within the run
        ledger's payload fence, and truncation is flagged in the result.
        """
        if str(capability_id or '').strip() != CAPABILITY_ID:
            raise BrowserAgentError(
                'That capability is not available.', 'CAPABILITY_NOT_FOUND', 404
            )
        if not isinstance(payload, dict):
            raise BrowserAgentError(
                'Run input must be an object.', 'INVALID_RUN_INPUT', 400
            )
        url = payload.get('url')
        if not isinstance(url, str) or not url.strip():
            raise BrowserAgentError(
                'Missing required input: url.', 'INVALID_RUN_INPUT', 400
            )
        page = await self.read_page(user_id, url.strip())
        full_text = page['text']
        summary = {
            'finalUrl': page['finalUrl'],
            'title': page['title'],
            'bytes': page['bytes'],
            'fetchedAt': page['fetchedAt'],
            'textLength': len(full_text),
            'truncated': False,
        }
        result: dict[str, Any] = {
            'finalUrl': page['finalUrl'],
            'title': page['title'],
            'fetchedAt': page['fetchedAt'],
            'bytes': page['bytes'],
            'textLength': len(full_text),
            'truncated': False,
            'summary': summary,
            'text': full_text,
        }
        encoded = len(json.dumps(result, default=str).encode('utf-8'))
        if encoded > MAX_RESULT_BYTES:
            result['truncated'] = True
            summary['truncated'] = True
            encoded = len(json.dumps(result, default=str).encode('utf-8'))
            # Shrink the stored text by the overflow (UTF-8 bytes are at
            # least one per character, so one pass is enough in practice;
            # the loop guarantees the bound).
            while encoded > MAX_RESULT_BYTES and result['text']:
                overflow = encoded - MAX_RESULT_BYTES
                keep = max(0, len(result['text']) - overflow)
                result['text'] = result['text'][:keep]
                encoded = len(json.dumps(result, default=str).encode('utf-8'))
        return result


async def read_page(
    user_id: str,
    url: str,
    *,
    http_client: httpx.AsyncClient | None = None,
    resolver: Resolver | None = None,
) -> dict[str, Any]:
    """Module-level read; see BrowserAgent.read_page."""
    agent = BrowserAgent(http_client=http_client, resolver=resolver)
    return await agent.read_page(user_id, url)


async def execute(
    capability_id: str,
    user_id: str,
    payload: Any,
    *,
    http_client: httpx.AsyncClient | None = None,
    resolver: Resolver | None = None,
) -> dict[str, Any]:
    """Module-level adapter; see BrowserAgent.execute."""
    agent = BrowserAgent(http_client=http_client, resolver=resolver)
    return await agent.execute(capability_id, user_id, payload)
