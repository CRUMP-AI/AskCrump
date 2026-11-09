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
- The validated answer is pinned for the fetch: the connection is
  opened to the validated IP address itself, never to a second DNS
  lookup of the hostname, so a rebinding answer between validation
  and connect cannot steer the request to a non-public address. The
  original hostname is preserved for the ``Host`` header and for TLS
  SNI / certificate verification.
- The default client is built with ``trust_env=False``: proxy and
  other settings are never taken from the process environment, since
  an environment proxy would resolve the hostname itself and defeat
  the pin.
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
    # ``is_global`` alone is not enough: the multicast ranges
    # (224.0.0.0/4 and ff00::/8) report as global on Python 3.12 even
    # though they are not public unicast destinations, and the safety
    # model above promises they are blocked.
    return bool(address.is_global and not address.is_multicast)


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


async def _validate_public_url(
    url: str, resolver: Resolver
) -> tuple[str, str, list[str]]:
    """Validate one fetch hop; return (url, hostname, addresses).

    Raises BROWSER_URL_BLOCKED for a non-http(s) scheme, a URL carrying
    credentials, a malformed host, or any resolved address that is not
    a public (global) address. The returned addresses are the exact
    answers validation checked; the default fetch path pins its
    connection to one of them instead of resolving the name again.
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
    return url, hostname, addresses


async def _ensure_public_url(url: str, resolver: Resolver) -> str:
    """Validate one fetch hop and return the URL unchanged."""
    validated, _hostname, _addresses = await _validate_public_url(url, resolver)
    return validated


def _ascii_hostname(hostname: str) -> str:
    """Return the IDNA (ASCII) form used on the wire for SNI and Host."""
    try:
        ipaddress.ip_address(hostname)
        return hostname
    except ValueError:
        pass
    try:
        return hostname.lower().encode('idna').decode('ascii')
    except (UnicodeError, ValueError):
        return hostname.lower()


class _PinnedAsyncTransport(httpx.AsyncBaseTransport):
    """Transport that connects to one pre-validated IP address.

    The request URL is rewritten to the validated address before the
    inner transport sees it, so the inner transport -- the real
    ``httpx.AsyncHTTPTransport`` by default -- opens its TCP connection
    to that address and performs no DNS lookup of its own. Two parts
    of the original request are preserved:

    - the ``Host`` header keeps the original hostname (with port when
      present), taken from the request the client already built;
    - the ``sni_hostname`` request extension carries the original
      hostname, which httpcore uses as the TLS server name, so SNI
      and certificate verification still check the hostname, not the
      pinned address.

    A request naming any other host is refused rather than fetched:
    one transport instance serves exactly one validated hop.
    """

    def __init__(
        self,
        hostname: str,
        address: str,
        *,
        inner: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._hostname = _ascii_hostname(hostname)
        self._address = str(address).split('%', 1)[0]
        # Never take proxy or other settings from the environment.
        self.trust_env = False
        self._owns_inner = inner is None
        self._inner: httpx.AsyncBaseTransport = (
            inner
            if inner is not None
            else httpx.AsyncHTTPTransport(trust_env=False)
        )

    @property
    def hostname(self) -> str:
        return self._hostname

    @property
    def address(self) -> str:
        return self._address

    @property
    def inner(self) -> httpx.AsyncBaseTransport:
        return self._inner

    async def handle_async_request(
        self, request: httpx.Request
    ) -> httpx.Response:
        # Compare in the same normalised form the pin was stored in:
        # httpx keeps internationalised hosts in Unicode in
        # ``url.host`` while the pin holds the IDNA form, and a raw
        # comparison would refuse every IDN request.
        if _ascii_hostname(str(request.url.host or '')) != self._hostname:
            raise httpx.ConnectError(
                'Pinned transport received a request for an unexpected host.',
                request=request,
            )
        pinned_url = request.url.copy_with(host=self._address)
        headers = httpx.Headers(request.headers)
        if 'host' not in headers:
            netloc = request.url.netloc
            headers['host'] = (
                netloc.decode('ascii')
                if isinstance(netloc, bytes)
                else str(netloc)
            )
        extensions = dict(request.extensions)
        extensions['sni_hostname'] = self._hostname
        pinned_request = httpx.Request(
            method=request.method,
            url=pinned_url,
            headers=headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await self._inner.handle_async_request(pinned_request)

    async def aclose(self) -> None:
        if self._owns_inner:
            await self._inner.aclose()


# Public alias for tests and for callers building a pinned client.
PinnedAsyncTransport = _PinnedAsyncTransport


def _make_pinned_client(
    hostname: str,
    address: str,
    *,
    inner_transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Build the default client for one hop, pinned to ``address``."""
    transport = _PinnedAsyncTransport(
        hostname, address, inner=inner_transport
    )
    return httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
    )


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
    every path with a fake transport and fake DNS answers. When a
    client is injected it is used exactly as given (the historical
    behaviour). Otherwise each hop is fetched through a fresh client
    whose transport is pinned to the address validation approved;
    ``transport`` may inject the pinned transport's inner transport
    (for example a fake one in tests) without changing that pinning.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        resolver: Resolver | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = http_client
        self._resolver: Resolver = resolver or _default_resolver
        self._transport = transport

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

    async def _fetch_hop(
        self, client: Any, url: str
    ) -> tuple[int, Any, bytes]:
        """Fetch one hop, mapping transport errors to BROWSER_FETCH_FAILED."""
        try:
            return await self._fetch_once(client, url)
        except BrowserAgentError:
            raise
        except httpx.HTTPError as exc:
            raise _fetch_failed() from exc

    async def read_page(self, user_id: str, url: str) -> dict[str, Any]:
        """Fetch ``url`` and return its readable content.

        Returns ``{finalUrl, title, text, fetchedAt, bytes}``. This is a
        server-side read of a single public page; it is not interactive
        browsing and runs no page scripts.
        """
        del user_id  # Reads are per-URL; the caller owns run attribution.
        current = str(url or '').strip()
        redirects = 0
        while True:
            if self._client is not None:
                # Injected client: keep the established behaviour.
                await _ensure_public_url(current, self._resolver)
                status, headers, content = await self._fetch_hop(
                    self._client, current
                )
            else:
                # Default client: resolve once, validate every answer,
                # then pin this hop to a validated address. Each
                # redirect hop re-enters here, so it is resolved,
                # validated, and pinned on its own.
                _validated, hostname, addresses = (
                    await _validate_public_url(current, self._resolver)
                )
                hop_client = _make_pinned_client(
                    hostname,
                    addresses[0],
                    inner_transport=self._transport,
                )
                try:
                    status, headers, content = await self._fetch_hop(
                        hop_client, current
                    )
                finally:
                    await hop_client.aclose()
            if status in REDIRECT_STATUSES:
                location = headers.get('location') if headers else None
                if not location:
                    raise _fetch_failed(
                        'The page redirected without a destination.'
                    )
                redirects += 1
                if redirects > MAX_REDIRECTS:
                    raise _fetch_failed('The page redirected too many times.')
                current = urljoin(current, str(location))
                continue
            break
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
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Module-level read; see BrowserAgent.read_page."""
    agent = BrowserAgent(
        http_client=http_client, resolver=resolver, transport=transport
    )
    return await agent.read_page(user_id, url)


async def execute(
    capability_id: str,
    user_id: str,
    payload: Any,
    *,
    http_client: httpx.AsyncClient | None = None,
    resolver: Resolver | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Module-level adapter; see BrowserAgent.execute."""
    agent = BrowserAgent(
        http_client=http_client, resolver=resolver, transport=transport
    )
    return await agent.execute(capability_id, user_id, payload)
