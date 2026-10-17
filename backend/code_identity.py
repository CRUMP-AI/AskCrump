"""Signed Vercel workload identity admission; never decode claims as authority.

Reference: https://vercel.com/docs/oidc/reference and the official
@vercel/oidc verify-vercel-oidc-token implementation. The latter pins the
global JWKS endpoint for both global and team issuers. Tokens cannot select
an issuer, URL, algorithm, key, audience, project, team or environment policy.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
import time
from typing import Any, Callable

import httpx
import jwt


JWKS_URL = "https://oidc.vercel.com/.well-known/jwks"
MAX_TOKEN_BYTES = 16_384
MAX_JWKS_BYTES = 65_536
MAX_JWKS_KEYS = 32
JWKS_FETCH_TIMEOUT_SECONDS = 4.0
_ISSUER = re.compile(r"https://oidc\.vercel\.com(?:/[A-Za-z0-9_-]{1,100})?\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_COMPACT_JWT = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\Z")


class CodeIdentityError(RuntimeError):
    """A bounded, content-free failure safe for operational error handling."""

    def __init__(self, code: str = "CODE_IDENTITY_INVALID") -> None:
        super().__init__("Autonomous Crump workload identity could not be verified.")
        self.code = code


@dataclass(frozen=True, slots=True)
class CodeIdentityPolicy:
    issuer: str
    audience: str
    project_id: str
    team_id: str
    environment: str

    @classmethod
    def from_settings(cls, settings: Any) -> CodeIdentityPolicy:
        values = {}
        for name in ("issuer", "audience", "project_id", "team_id", "environment"):
            value = getattr(settings, f"code_oidc_{name}", None)
            if not isinstance(value, str) or not value or value != value.strip():
                raise CodeIdentityError("CODE_IDENTITY_NOT_CONFIGURED")
            values[name] = value
        if (
            not _ISSUER.fullmatch(values["issuer"])
            or len(values["audience"]) > 512
            or "*" in values["audience"]
            or any(ord(c) < 33 or ord(c) > 126 for c in values["audience"])
            or any(not _IDENTIFIER.fullmatch(values[k]) for k in ("project_id", "team_id"))
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", values["environment"])
        ):
            raise CodeIdentityError("CODE_IDENTITY_NOT_CONFIGURED")
        return cls(**values)


@dataclass(frozen=True, slots=True)
class VerifiedCodeIdentity:
    project_id: str
    team_id: str
    issuer: str
    audience: str
    environment: str
    expires_at: int


def code_identity_token(settings: Any, headers: Any = None) -> str:
    """Read each invocation's token; an invalid supplied header cannot fall back."""
    header = headers.get("x-vercel-oidc-token") if headers is not None else None
    value = header if header is not None else getattr(settings, "vercel_oidc_token", None)
    return value.strip() if isinstance(value, str) else ""


class CodeIdentityVerifier:
    """One bounded public-key cache per ASGI process, with async single-flight refresh.

    An unknown kid may refresh once per 30 seconds for rotation. Errors never
    extend key expiry or use expired keys. Neither tokens nor verified payloads
    are cached. An injected transport/clock is solely an offline test seam.
    """

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._keys: dict[str, Any] = {}
        self._expires = 0.0
        self._refresh_after = 0.0
        self._lock = asyncio.Lock()

    async def _fetch_keys(self) -> dict[str, Any]:
        try:
            async with asyncio.timeout(JWKS_FETCH_TIMEOUT_SECONDS), httpx.AsyncClient(
                timeout=httpx.Timeout(3.0, connect=2.0),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ) as client:
                async with client.stream("GET", JWKS_URL, headers={"Accept": "application/json"}) as response:
                    if response.status_code != 200:
                        raise ValueError("Unavailable key set")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_JWKS_BYTES:
                            raise ValueError("Key set size limit")
                        body.extend(chunk)
            document = json.loads(body)
            keys = document.get("keys") if isinstance(document, dict) else None
            if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_JWKS_KEYS:
                raise ValueError("Invalid key set")
            parsed: dict[str, Any] = {}
            for item in keys:
                if not isinstance(item, dict):
                    raise ValueError("Invalid key")
                if item.get("kty") != "RSA" or item.get("alg", "RS256") != "RS256":
                    continue
                kid = item.get("kid")
                if (
                    not isinstance(kid, str) or not 1 <= len(kid) <= 128
                    or any(ord(c) < 33 or ord(c) > 126 for c in kid)
                    or kid in parsed or item.get("use", "sig") != "sig"
                    or any(k in item for k in ("d", "p", "q", "dp", "dq", "qi", "oth"))
                    or not isinstance(item.get("n"), str) or len(item["n"]) > 1400
                    or not isinstance(item.get("e"), str) or len(item["e"]) > 16
                ):
                    raise ValueError("Invalid signing key")
                operations = item.get("key_ops")
                if operations is not None and operations != ["verify"]:
                    raise ValueError("Not a verification key")
                public_key = jwt.PyJWK.from_dict(item, algorithm="RS256").key
                if not 2048 <= public_key.key_size <= 4096:
                    raise ValueError("RSA key size limit")
                parsed[kid] = public_key
            if not parsed:
                raise ValueError("No verification keys")
            return parsed
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, OverflowError, jwt.PyJWTError):
            raise CodeIdentityError("CODE_IDENTITY_UNAVAILABLE") from None

    async def _key(self, kid: str) -> Any:
        now = self._clock()
        if now < self._expires and kid in self._keys:
            return self._keys[kid]
        async with self._lock:
            now = self._clock()
            if now < self._expires and kid in self._keys:
                return self._keys[kid]
            if now < self._refresh_after:
                raise CodeIdentityError("CODE_IDENTITY_UNAVAILABLE")
            self._refresh_after = now + 30.0
            keys = await self._fetch_keys()
            self._keys = keys
            self._expires = self._clock() + 300.0
            if kid not in keys:
                raise CodeIdentityError()
            return keys[kid]

    async def verify(self, token: str, policy: CodeIdentityPolicy) -> VerifiedCodeIdentity:
        if (
            not isinstance(token, str) or len(token) > MAX_TOKEN_BYTES
            or not _COMPACT_JWT.fullmatch(token)
        ):
            raise CodeIdentityError()
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if (
                header.get("alg") != "RS256"
                or str(header.get("typ", "")).upper() != "JWT"
                or not isinstance(kid, str) or not 1 <= len(kid) <= 128
                or any(ord(c) < 33 or ord(c) > 126 for c in kid)
                or any(k in header for k in ("crit", "jku", "jwk", "x5u", "x5c", "b64"))
            ):
                raise CodeIdentityError()
            key = await self._key(kid)
            claims = jwt.decode(
                token, key, algorithms=["RS256"], issuer=policy.issuer, audience=policy.audience,
                options={"strict_aud": True, "require": [
                    "iss", "aud", "sub", "iat", "nbf", "exp",
                    "project_id", "owner_id", "environment",
                ]},
            )
            if (
                claims.get("project_id") != policy.project_id
                or claims.get("owner_id") != policy.team_id
                or claims.get("environment") != policy.environment
                or not isinstance(claims.get("sub"), str) or not 1 <= len(claims["sub"]) <= 512
                or any(type(claims[k]) is not int or not 0 < claims[k] < 2**53
                       for k in ("iat", "nbf", "exp"))
                or claims["exp"] <= max(claims["iat"], claims["nbf"])
            ):
                raise CodeIdentityError()
            return VerifiedCodeIdentity(
                project_id=policy.project_id, team_id=policy.team_id,
                issuer=policy.issuer, audience=policy.audience,
                environment=policy.environment, expires_at=claims["exp"],
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            raise CodeIdentityError() from None


_default_verifier = CodeIdentityVerifier()


async def verify_code_identity(
    token: str, settings: Any, *, verifier: CodeIdentityVerifier | None = None,
) -> VerifiedCodeIdentity:
    policy = CodeIdentityPolicy.from_settings(settings)
    return await (verifier or _default_verifier).verify(token, policy)
