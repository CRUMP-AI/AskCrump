"""Credential-aware, bounded HTTPS transports for connected provider APIs.

The typed Google and Microsoft adapters deliberately know nothing about bearer
tokens or networking.  This module is their production transport boundary.  It
accepts only fixed provider hosts, obtains one short-lived access token from a
credential broker, disables environment proxies and redirects, streams a
bounded response, and never logs or serializes credential material.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Protocol
import zlib

import certifi
import httpx

from .connected_app_contracts import (
    ConnectedAccountRef,
    CredentialHandleRef,
)
from .connected_app_google import (
    GoogleEffectUnknown,
    GoogleNotDispatched,
    GoogleTransportRequest,
    GoogleTransportResponse,
    GoogleTransportSecurityPolicy,
)
from .connected_app_microsoft import (
    MicrosoftEffectUnknown,
    MicrosoftNotDispatched,
    MicrosoftTransportRequest,
    MicrosoftTransportResponse,
    MicrosoftTransportSecurityPolicy,
)
from .connected_app_policy import ConnectorProvider


_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_MAX_HEADER_COUNT = 64
_MAX_HEADER_BYTES = 32 * 1024
_TOKEN_MIN_REMAINING = timedelta(seconds=15)
_TOKEN_MAX_LIFETIME = timedelta(hours=2)
_CONNECT_TIMEOUT_SECONDS = 5.0
_WRITE_TIMEOUT_SECONDS = 10.0
_READ_TIMEOUT_SECONDS = 20.0
_POOL_TIMEOUT_SECONDS = 5.0


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("provider response contains duplicate JSON keys")
        result[key] = value
    return result


class ConnectedAccessToken:
    """Ephemeral broker result that refuses representation and serialization."""

    __slots__ = (
        "owner_id",
        "connection_id",
        "provider",
        "credential_handle_sha256",
        "expires_at",
        "__token",
    )

    def __init__(
        self,
        *,
        owner_id: str,
        connection_id: str,
        provider: ConnectorProvider,
        credential_handle_sha256: str,
        expires_at: datetime,
        token: str,
    ) -> None:
        if not isinstance(provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(credential_handle_sha256, str) or len(credential_handle_sha256) != 64:
            raise ValueError("credential handle binding is invalid")
        if any(character not in "0123456789abcdef" for character in credential_handle_sha256):
            raise ValueError("credential handle binding is invalid")
        if not isinstance(token, str) or not 32 <= len(token) <= 16_384:
            raise ValueError("access token is invalid")
        if any(ord(character) < 33 or ord(character) == 127 for character in token):
            raise ValueError("access token is invalid")
        self.owner_id = owner_id
        self.connection_id = connection_id
        self.provider = provider
        self.credential_handle_sha256 = credential_handle_sha256
        self.expires_at = _aware(expires_at, "expires_at")
        self.__token = token

    def reveal_for_transport(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        now: datetime,
    ) -> str:
        reference = _aware(now, "now")
        if (
            account.owner_id != self.owner_id
            or account.connection_id != self.connection_id
            or account.provider is not self.provider
            or credential.owner_id != self.owner_id
            or credential.connection_id != self.connection_id
            or credential.provider is not self.provider
            or _digest(credential.handle_id) != self.credential_handle_sha256
            or self.expires_at <= reference + _TOKEN_MIN_REMAINING
            or self.expires_at > reference + _TOKEN_MAX_LIFETIME
        ):
            raise ValueError("access token binding is invalid")
        return self.__token

    def __repr__(self) -> str:
        return (
            "ConnectedAccessToken("
            f"provider={self.provider.value!r}, credential='<redacted>', token='<redacted>')"
        )

    def __str__(self) -> str:
        return "<connected-access-token:redacted>"

    def __getstate__(self) -> object:
        raise TypeError("ConnectedAccessToken cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("ConnectedAccessToken cannot be serialized")


class ConnectedAccessTokenSource(Protocol):
    """Trusted broker boundary; raw tokens never cross into model or route code."""

    async def issue_access_token(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
    ) -> ConnectedAccessToken: ...


class _BoundedProviderHTTPS:
    def __init__(
        self,
        token_source: ConnectedAccessTokenSource,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not callable(getattr(token_source, "issue_access_token", None)):
            raise TypeError("token_source must implement issue_access_token")
        if not callable(now):
            raise TypeError("now must be callable")
        self._token_source = token_source
        self._transport = transport
        self._now = now

    @staticmethod
    def _request_headers(
        headers: tuple[tuple[str, str], ...],
        token: str,
        *,
        has_body: bool,
    ) -> dict[str, str]:
        result: dict[str, str] = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, identity",
            "Authorization": f"Bearer {token}",
            "User-Agent": "AskCrump-ConnectedApps/1",
        }
        blocked = {"authorization", "host", "proxy-authorization", "accept-encoding"}
        for name, value in headers:
            folded = name.casefold()
            if folded in blocked or folded in {key.casefold() for key in result}:
                raise ValueError("provider request contains transport-owned headers")
            result[name] = value
        if has_body:
            result["Content-Type"] = "application/json; charset=utf-8"
        if len(result) > _MAX_HEADER_COUNT:
            raise ValueError("provider request contains too many headers")
        total = sum(
            len(name.encode("ascii")) + len(value.encode("utf-8")) for name, value in result.items()
        )
        if total > _MAX_HEADER_BYTES:
            raise ValueError("provider request headers exceed their limit")
        return result

    @staticmethod
    def _encode_body(value: object | None) -> bytes | None:
        if value is None:
            return None
        try:
            encoded = json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise ValueError("provider request body is invalid") from exc
        if len(encoded) > _MAX_REQUEST_BYTES:
            raise ValueError("provider request body exceeds its limit")
        return encoded

    @staticmethod
    async def _bounded_body(
        response: httpx.Response,
        *,
        raw_limit: int,
        decompressed_limit: int,
    ) -> tuple[bytes, int, int]:
        declared_size: int | None = None
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                declared_size = int(declared)
            except ValueError:
                raise ValueError("provider content length is invalid") from None
            if declared_size < 0 or declared_size > raw_limit:
                raise ValueError("provider raw response exceeds its limit")

        encoding = response.headers.get("content-encoding", "identity").strip().casefold()
        if encoding not in {"", "identity", "gzip"}:
            raise ValueError("provider content encoding is unsupported")
        # Mock transports and a few custom httpx transports may return an
        # already-buffered response even when the caller requested streaming.
        # httpx has already decoded any content-encoding in that case, so use
        # its independently tracked wire-byte count and enforce both limits.
        # A buffered compressed response has lost the raw framing needed to
        # prove that there was exactly one gzip member; reject it rather than
        # silently accepting concatenated/trailing data.
        if response.is_stream_consumed:
            if encoding == "gzip":
                raise ValueError("buffered compressed provider response is unverifiable")
            buffered = response.content
            raw_size = max(
                response.num_bytes_downloaded or len(buffered),
                declared_size or 0,
            )
            if raw_size > raw_limit:
                raise ValueError("provider raw response exceeds its limit")
            if len(buffered) > decompressed_limit:
                raise ValueError("provider decompressed response exceeds its limit")
            return buffered, raw_size, len(buffered)

        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
        output = bytearray()
        raw_size = 0
        async for chunk in response.aiter_raw():
            raw_size += len(chunk)
            if raw_size > raw_limit:
                raise ValueError("provider raw response exceeds its limit")
            if decompressor is None:
                decoded = chunk
            else:
                remaining = decompressed_limit - len(output)
                decoded = decompressor.decompress(chunk, remaining + 1)
                if decompressor.unconsumed_tail or decompressor.unused_data:
                    raise ValueError("provider decompressed response exceeds its limit")
            output.extend(decoded)
            if len(output) > decompressed_limit:
                raise ValueError("provider decompressed response exceeds its limit")
        if decompressor is not None:
            remaining = decompressed_limit - len(output)
            output.extend(decompressor.flush(remaining + 1))
            if (
                len(output) > decompressed_limit
                or not decompressor.eof
                or decompressor.unused_data
                or decompressor.unconsumed_tail
            ):
                raise ValueError("provider compressed response is invalid")
        return bytes(output), raw_size, len(output)

    @staticmethod
    def _parse_json(response: httpx.Response, body: bytes) -> object | None:
        if not body:
            return None
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        if content_type not in {"application/json", "text/json"} and not content_type.endswith(
            "+json"
        ):
            raise ValueError("provider response is not JSON")
        try:
            return json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_json_no_duplicates,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ValueError("provider response JSON is invalid") from exc

    async def _dispatch(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        method: str,
        host: str,
        path: str,
        query: tuple[tuple[str, str], ...],
        headers: tuple[tuple[str, str], ...],
        json_body: object | None,
        raw_limit: int,
        decompressed_limit: int,
        not_dispatched: type[Exception],
        effect_unknown: type[Exception],
    ) -> tuple[int, object | None, Mapping[str, str], int, int]:
        try:
            issued = await self._token_source.issue_access_token(
                account=account,
                credential=credential,
            )
            if type(issued) is not ConnectedAccessToken:
                raise TypeError("token source returned an invalid value")
            token = issued.reveal_for_transport(
                account=account,
                credential=credential,
                now=_aware(self._now(), "now"),
            )
            body = self._encode_body(json_body)
            request_headers = self._request_headers(headers, token, has_body=body is not None)
        except Exception:
            raise not_dispatched() from None

        timeout = httpx.Timeout(
            _READ_TIMEOUT_SECONDS,
            connect=_CONNECT_TIMEOUT_SECONDS,
            write=_WRITE_TIMEOUT_SECONDS,
            pool=_POOL_TIMEOUT_SECONDS,
        )
        try:
            async with httpx.AsyncClient(
                http2=True,
                verify=certifi.where(),
                follow_redirects=False,
                trust_env=False,
                timeout=timeout,
                transport=self._transport,
            ) as client:
                async with client.stream(
                    method,
                    f"https://{host}{path}",
                    params=list(query),
                    headers=request_headers,
                    content=body,
                ) as response:
                    response_body, raw_size, decompressed_size = await self._bounded_body(
                        response,
                        raw_limit=raw_limit,
                        decompressed_limit=decompressed_limit,
                    )
                    parsed = self._parse_json(response, response_body)
                    # The typed adapter contracts attest the serialized JSON
                    # representation.  An empty HTTP entity maps to JSON null,
                    # whose canonical representation is four bytes.
                    if parsed is None:
                        decompressed_size = max(decompressed_size, 4)
                    return (
                        response.status_code,
                        parsed,
                        dict(response.headers),
                        raw_size,
                        decompressed_size,
                    )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise not_dispatched() from None
        except Exception:
            # Once the connection is established, a write/read/parse failure may
            # have occurred after provider dispatch.  The typed adapter decides
            # whether that uncertainty is effectful or merely retryable.
            raise effect_unknown() from None


class GoogleHTTPSCredentialTransport(_BoundedProviderHTTPS):
    security_policy = GoogleTransportSecurityPolicy()

    async def request(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: GoogleTransportRequest,
    ) -> GoogleTransportResponse:
        if (
            type(request) is not GoogleTransportRequest
            or account.provider is not ConnectorProvider.GOOGLE
        ):
            raise GoogleNotDispatched()
        result = await self._dispatch(
            account=account,
            credential=credential,
            method=request.method,
            host=request.host,
            path=request.path,
            query=request.query,
            headers=request.headers,
            json_body=request.json_body,
            raw_limit=self.security_policy.max_raw_response_bytes,
            decompressed_limit=self.security_policy.max_decompressed_response_bytes,
            not_dispatched=GoogleNotDispatched,
            effect_unknown=GoogleEffectUnknown,
        )
        return GoogleTransportResponse(
            status=result[0],
            body=result[1],
            headers=result[2],
            raw_size_bytes=result[3],
            decompressed_size_bytes=result[4],
        )


class MicrosoftHTTPSCredentialTransport(_BoundedProviderHTTPS):
    security_policy = MicrosoftTransportSecurityPolicy()

    async def request(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: MicrosoftTransportRequest,
    ) -> MicrosoftTransportResponse:
        if (
            type(request) is not MicrosoftTransportRequest
            or account.provider is not ConnectorProvider.MICROSOFT
        ):
            raise MicrosoftNotDispatched()
        result = await self._dispatch(
            account=account,
            credential=credential,
            method=request.method,
            host=request.host,
            path=request.path,
            query=request.query,
            headers=request.headers,
            json_body=request.json_body,
            raw_limit=self.security_policy.max_raw_response_bytes,
            decompressed_limit=self.security_policy.max_decompressed_response_bytes,
            not_dispatched=MicrosoftNotDispatched,
            effect_unknown=MicrosoftEffectUnknown,
        )
        return MicrosoftTransportResponse(
            status=result[0],
            body=result[1],
            headers=result[2],
            raw_size_bytes=result[3],
            decompressed_size_bytes=result[4],
        )
