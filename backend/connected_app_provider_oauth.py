"""Fixed-endpoint OAuth clients for Google and Microsoft connected apps.

This module owns provider-facing authorization URL construction, code/refresh
exchange, and stable external-account discovery.  Secrets are redacted and
unserializable; provider response bodies never appear in raised exceptions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Callable
from urllib.parse import urlencode
from uuid import UUID

import certifi
import httpx

from backend.connected_app_oauth import (
    OAuthAuthorizationCodeSecret,
    OAuthBrokerFlowCommand,
    OAuthPkceVerifierSecret,
    OAuthStateSecret,
)
from backend.connected_app_contracts import ConnectorAccountKind
from backend.connected_app_policy import ConnectorProvider


_CLIENT_ID = re.compile(r"[A-Za-z0-9._:@/-]{8,512}")
_TOKEN = re.compile(r"[^\s\x00-\x1f\x7f]{16,16384}")
_SCOPE = re.compile(r"[^\s\x00-\x1f\x7f]{1,512}")
_HOSTED_DOMAIN = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)
_MAX_RESPONSE_BYTES = 64 * 1024
_GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
_MICROSOFT_AUTHORIZE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
_MICROSOFT_TOKEN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_MICROSOFT_ME = "https://graph.microsoft.com/v1.0/me"


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _uuid(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} must be a canonical UUID") from None
    if value != canonical:
        raise ValueError(f"{name} must be a canonical UUID")
    return canonical


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _microsoft_tenant(account_kind: ConnectorAccountKind) -> str:
    if account_kind is ConnectorAccountKind.PERSONAL:
        return "consumers"
    if account_kind is ConnectorAccountKind.WORK_SCHOOL:
        return "organizations"
    raise TypeError("account_kind must be ConnectorAccountKind")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


async def _json(response: httpx.Response) -> dict[str, object]:
    encoding = response.headers.get("content-encoding", "identity").strip().casefold()
    if encoding not in {"", "identity"}:
        raise ProviderOAuthEffectUnknown()
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError:
            raise ProviderOAuthEffectUnknown() from None
        if not 0 <= declared_size <= _MAX_RESPONSE_BYTES:
            raise ProviderOAuthEffectUnknown()
    if response.is_stream_consumed:
        content = response.content
    else:
        collected = bytearray()
        async for chunk in response.aiter_bytes():
            collected.extend(chunk)
            if len(collected) > _MAX_RESPONSE_BYTES:
                raise ProviderOAuthEffectUnknown()
        content = bytes(collected)
    if len(content) > _MAX_RESPONSE_BYTES:
        raise ProviderOAuthEffectUnknown()
    content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
    if content_type not in {"application/json", "text/json"} and not content_type.endswith("+json"):
        raise ProviderOAuthEffectUnknown()
    try:
        parsed = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise ProviderOAuthEffectUnknown() from None
    if type(parsed) is not dict:
        raise ProviderOAuthEffectUnknown()
    return parsed


def _text(row: dict[str, object], key: str, *, maximum: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ProviderOAuthEffectUnknown()
    return value


class ProviderOAuthError(RuntimeError):
    code = "PROVIDER_OAUTH_ERROR"

    def __init__(self) -> None:
        super().__init__(self.code)


class ProviderOAuthNotDispatched(ProviderOAuthError):
    code = "PROVIDER_OAUTH_NOT_DISPATCHED"


class ProviderOAuthEffectUnknown(ProviderOAuthError):
    code = "PROVIDER_OAUTH_EFFECT_UNKNOWN"


class ProviderOAuthRejected(ProviderOAuthError):
    code = "PROVIDER_OAUTH_REJECTED"


class ProviderOAuthQuarantineRequired(ProviderOAuthEffectUnknown):
    """A 200 response issued usable tokens but failed semantic validation.

    The attached token set is deliberately redacted and non-serializable.  It
    exists only so the durable broker can place every safely parsed token into
    encrypted cleanup custody before recording the exchange as ambiguous.
    """

    code = "PROVIDER_OAUTH_QUARANTINE_REQUIRED"
    __slots__ = ("token_set",)

    def __init__(self, token_set: "ProviderOAuthQuarantineTokenSet") -> None:
        if not isinstance(token_set, ProviderOAuthQuarantineTokenSet):
            raise TypeError("token_set must be ProviderOAuthQuarantineTokenSet")
        self.token_set = token_set
        super().__init__()


class _Secret:
    __slots__ = ("_value",)
    label = "secret"

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not _TOKEN.fullmatch(value):
            raise ValueError(f"provider OAuth {self.label} is invalid")
        self._value = value

    def _reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.label}='<redacted>')"

    def __getstate__(self) -> None:
        raise TypeError(f"provider OAuth {self.label} cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError(f"provider OAuth {self.label} cannot be serialized")


class ProviderOAuthClientSecret(_Secret):
    label = "client secret"


@dataclass(frozen=True, slots=True)
class ProviderOAuthTokenBinding:
    """Immutable provenance that prevents cross-provider/client token use.

    Fresh code-exchange tokens are flow-bound and therefore have no credential
    handle or external-account hash yet. Persisted/refreshable tokens must set
    both optional values together; the credential vault reconstructs that exact
    binding after authenticated decryption.
    """

    provider: ConnectorProvider
    oauth_client_id_sha256: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    account_kind: ConnectorAccountKind
    credential_handle_sha256: str | None = None
    external_account_id_hash: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be ConnectorProvider")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be ConnectorAccountKind")
        object.__setattr__(
            self,
            "oauth_client_id_sha256",
            _sha(self.oauth_client_id_sha256, "oauth_client_id_sha256"),
        )
        for name in ("owner_id", "connection_id", "connection_incarnation_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if (self.credential_handle_sha256 is None) != (self.external_account_id_hash is None):
            raise ValueError("credential and external-account provenance must appear together")
        if self.credential_handle_sha256 is not None:
            object.__setattr__(
                self,
                "credential_handle_sha256",
                _sha(self.credential_handle_sha256, "credential_handle_sha256"),
            )
            object.__setattr__(
                self,
                "external_account_id_hash",
                _sha(self.external_account_id_hash or "", "external_account_id_hash"),
            )

    @property
    def persisted(self) -> bool:
        return self.credential_handle_sha256 is not None

    def __repr__(self) -> str:
        return (
            "ProviderOAuthTokenBinding("
            f"provider={self.provider.value!r}, account_kind={self.account_kind.value!r}, "
            "identity='<redacted>')"
        )


class _BoundTokenSecret:
    __slots__ = ("_value", "binding")
    label = "token"

    def __init__(self, value: str, binding: ProviderOAuthTokenBinding) -> None:
        if not isinstance(value, str) or not _TOKEN.fullmatch(value):
            raise ValueError(f"provider OAuth {self.label} is invalid")
        if not isinstance(binding, ProviderOAuthTokenBinding):
            raise TypeError("provider OAuth token binding is invalid")
        self._value = value
        self.binding = binding

    def _reveal(self) -> str:
        return self._value

    def require_binding(self, expected: ProviderOAuthTokenBinding) -> str:
        if not isinstance(expected, ProviderOAuthTokenBinding) or self.binding != expected:
            raise ProviderOAuthRejected()
        return self._value

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}({self.label}='<redacted>', "
            f"provider={self.binding.provider.value!r}, binding='<redacted>')"
        )

    def __getstate__(self) -> None:
        raise TypeError(f"provider OAuth {self.label} cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError(f"provider OAuth {self.label} cannot be serialized")


class ProviderOAuthAccessToken(_BoundTokenSecret):
    label = "access token"


class ProviderOAuthRefreshToken(_BoundTokenSecret):
    label = "refresh token"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderOAuthRegistration:
    provider: ConnectorProvider
    client_id: str
    client_secret: ProviderOAuthClientSecret = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be ConnectorProvider")
        if not isinstance(self.client_id, str) or not _CLIENT_ID.fullmatch(self.client_id):
            raise ValueError("provider OAuth client ID is invalid")
        if not isinstance(self.client_secret, ProviderOAuthClientSecret):
            raise TypeError("client_secret must be ProviderOAuthClientSecret")

    def __repr__(self) -> str:
        return (
            "ProviderOAuthRegistration("
            f"provider={self.provider.value!r}, client_id_sha256={_digest(self.client_id)!r}, "
            "client_secret='<redacted>')"
        )

    @property
    def client_id_sha256(self) -> str:
        return _digest(self.client_id)

    def token_binding_for_flow(self, command: OAuthBrokerFlowCommand) -> ProviderOAuthTokenBinding:
        if command.provider is not self.provider:
            raise ValueError("OAuth flow provider does not match registration")
        return ProviderOAuthTokenBinding(
            provider=self.provider,
            oauth_client_id_sha256=self.client_id_sha256,
            owner_id=command.owner_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            account_kind=command.account_kind,
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProviderOAuthTokenSet:
    provider: ConnectorProvider
    access_token: ProviderOAuthAccessToken = field(repr=False, compare=False)
    refresh_token: ProviderOAuthRefreshToken | None = field(repr=False, compare=False)
    granted_scopes: frozenset[str] = field(repr=False)
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be ConnectorProvider")
        if not isinstance(self.access_token, ProviderOAuthAccessToken):
            raise TypeError("access_token must be ProviderOAuthAccessToken")
        if self.refresh_token is not None and not isinstance(
            self.refresh_token, ProviderOAuthRefreshToken
        ):
            raise TypeError("refresh_token must be ProviderOAuthRefreshToken")
        if self.access_token.binding.provider is not self.provider:
            raise ValueError("access-token provider binding is invalid")
        if (
            self.refresh_token is not None
            and self.refresh_token.binding != self.access_token.binding
        ):
            raise ValueError("access and refresh token provenance differs")
        if not isinstance(self.granted_scopes, frozenset) or not self.granted_scopes:
            raise ValueError("granted_scopes must be a nonempty frozen set")
        normalized: set[str] = set()
        for scope in self.granted_scopes:
            if not isinstance(scope, str) or not _SCOPE.fullmatch(scope):
                raise ValueError("granted OAuth scope is invalid")
            normalized.add(scope)
        object.__setattr__(self, "granted_scopes", frozenset(normalized))
        issued = _aware(self.issued_at, "issued_at")
        expires = _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        if expires <= issued or expires - issued > timedelta(days=1):
            raise ValueError("provider access-token lifetime is invalid")

    def __repr__(self) -> str:
        return (
            "ProviderOAuthTokenSet("
            f"provider={self.provider.value!r}, scope_count={len(self.granted_scopes)}, "
            f"expires_at={self.expires_at!r}, tokens='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProviderOAuthQuarantineTokenSet:
    """Parsed provider tokens that are cleanup material, never authority."""

    provider: ConnectorProvider
    access_token: ProviderOAuthAccessToken | None = field(repr=False, compare=False)
    refresh_token: ProviderOAuthRefreshToken | None = field(repr=False, compare=False)
    requested_scopes: frozenset[str] = field(repr=False)
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be ConnectorProvider")
        if self.access_token is not None and not isinstance(
            self.access_token, ProviderOAuthAccessToken
        ):
            raise TypeError("access_token must be ProviderOAuthAccessToken or None")
        if self.refresh_token is not None and not isinstance(
            self.refresh_token, ProviderOAuthRefreshToken
        ):
            raise TypeError("refresh_token must be ProviderOAuthRefreshToken or None")
        if self.access_token is None and self.refresh_token is None:
            raise ValueError("quarantine requires at least one usable token")
        tokens = tuple(
            token
            for token in (self.access_token, self.refresh_token)
            if token is not None
        )
        if any(token.binding.provider is not self.provider for token in tokens):
            raise ValueError("quarantine-token provider binding is invalid")
        if any(token.binding != tokens[0].binding for token in tokens[1:]):
            raise ValueError("quarantine-token provenance differs")
        if not isinstance(self.requested_scopes, frozenset) or not self.requested_scopes:
            raise ValueError("requested_scopes must be a nonempty frozen set")
        if any(
            not isinstance(scope, str) or not _SCOPE.fullmatch(scope)
            for scope in self.requested_scopes
        ):
            raise ValueError("requested OAuth scopes are invalid")
        issued = _aware(self.issued_at, "issued_at")
        expires = _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        if expires <= issued or expires - issued > timedelta(days=1):
            raise ValueError("quarantine-token lifetime is invalid")

    @property
    def binding(self) -> ProviderOAuthTokenBinding:
        token = self.refresh_token or self.access_token
        assert token is not None
        return token.binding

    def __repr__(self) -> str:
        return (
            "ProviderOAuthQuarantineTokenSet("
            f"provider={self.provider.value!r}, scope_count={len(self.requested_scopes)}, "
            f"access_present={self.access_token is not None}, "
            f"refresh_present={self.refresh_token is not None}, tokens='<redacted>')"
        )


@dataclass(frozen=True, slots=True)
class ProviderExternalAccount:
    provider: ConnectorProvider
    account_kind: ConnectorAccountKind
    external_account_id_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be ConnectorProvider")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be ConnectorAccountKind")
        if not re.fullmatch(r"[0-9a-f]{64}", self.external_account_id_hash):
            raise ValueError("external account ID hash is invalid")


def build_authorization_url(
    *,
    registration: ProviderOAuthRegistration,
    command: OAuthBrokerFlowCommand,
    state: OAuthStateSecret,
) -> str:
    if registration.provider is not command.provider:
        raise ValueError("OAuth registration provider does not match flow")
    if not isinstance(state, OAuthStateSecret) or _digest(state.value) != command.state_sha256:
        raise ValueError("OAuth state does not match flow")
    scopes = " ".join(sorted(command.requested_scopes))
    common = {
        "client_id": registration.client_id,
        "redirect_uri": command.redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "state": state.value,
        "code_challenge": command.pkce_challenge,
        "code_challenge_method": "S256",
    }
    if command.provider is ConnectorProvider.GOOGLE:
        common.update(
            {
                "access_type": "offline",
                "include_granted_scopes": "false",
                "prompt": "consent",
            }
        )
        endpoint = _GOOGLE_AUTHORIZE
    else:
        common["response_mode"] = "query"
        endpoint = _MICROSOFT_AUTHORIZE.format(tenant=_microsoft_tenant(command.account_kind))
    return endpoint + "?" + urlencode(common)


class ProviderOAuthHTTPSClient:
    """No-redirect, no-proxy, bounded OAuth HTTP client."""

    def __init__(
        self,
        registration: ProviderOAuthRegistration,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(registration, ProviderOAuthRegistration):
            raise TypeError("registration must be ProviderOAuthRegistration")
        self._registration = registration
        self._transport = transport
        self._now = now or (lambda: datetime.now(UTC))

    def _require_registration_binding(self, binding: ProviderOAuthTokenBinding) -> None:
        if (
            not isinstance(binding, ProviderOAuthTokenBinding)
            or binding.provider is not self._registration.provider
            or binding.oauth_client_id_sha256 != self._registration.client_id_sha256
        ):
            raise ProviderOAuthRejected()

    async def _post_token(
        self,
        form: dict[str, str],
        *,
        account_kind: ConnectorAccountKind,
    ) -> dict[str, object]:
        endpoint = (
            _GOOGLE_TOKEN
            if self._registration.provider is ConnectorProvider.GOOGLE
            else _MICROSOFT_TOKEN.format(tenant=_microsoft_tenant(account_kind))
        )
        timeout = httpx.Timeout(20.0, connect=7.0, write=10.0, pool=5.0)
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
                    "POST",
                    endpoint,
                    data=form,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    if response.is_redirect:
                        raise ProviderOAuthEffectUnknown()
                    if response.status_code in {400, 401, 403}:
                        # Parse only enough to prove it is bounded JSON; never
                        # expose provider descriptions, request IDs, or tokens.
                        await _json(response)
                        raise ProviderOAuthRejected()
                    if response.status_code != 200:
                        raise ProviderOAuthEffectUnknown()
                    return await _json(response)
        except ProviderOAuthError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise ProviderOAuthNotDispatched() from None
        except Exception:
            raise ProviderOAuthEffectUnknown() from None

    def _quarantine_token_set(
        self,
        body: dict[str, object],
        *,
        expected_scopes: frozenset[str],
        binding: ProviderOAuthTokenBinding,
    ) -> ProviderOAuthQuarantineTokenSet | None:
        """Parse only bounded token values; provider metadata grants no authority."""

        self._require_registration_binding(binding)
        access: ProviderOAuthAccessToken | None = None
        refresh: ProviderOAuthRefreshToken | None = None
        raw_access = body.get("access_token")
        if isinstance(raw_access, str):
            try:
                access = ProviderOAuthAccessToken(raw_access, binding)
            except (TypeError, ValueError):
                access = None
        raw_refresh = body.get("refresh_token")
        if isinstance(raw_refresh, str):
            try:
                refresh = ProviderOAuthRefreshToken(raw_refresh, binding)
            except (TypeError, ValueError):
                refresh = None
        if access is None and refresh is None:
            return None
        issued = _aware(self._now(), "now")
        raw_expires = body.get("expires_in")
        seconds = raw_expires if type(raw_expires) is int and 1 <= raw_expires <= 86_400 else 3600
        return ProviderOAuthQuarantineTokenSet(
            provider=self._registration.provider,
            access_token=access,
            refresh_token=refresh,
            requested_scopes=expected_scopes,
            issued_at=issued,
            expires_at=issued + timedelta(seconds=seconds),
        )

    def _token_set(
        self,
        body: dict[str, object],
        *,
        expected_scopes: frozenset[str],
        require_refresh: bool,
        binding: ProviderOAuthTokenBinding,
        retained_refresh: ProviderOAuthRefreshToken | None = None,
    ) -> ProviderOAuthTokenSet:
        quarantine = self._quarantine_token_set(
            body,
            expected_scopes=expected_scopes,
            binding=binding,
        )
        try:
            return self._validated_token_set(
                body,
                expected_scopes=expected_scopes,
                require_refresh=require_refresh,
                binding=binding,
                retained_refresh=retained_refresh,
            )
        except (ProviderOAuthEffectUnknown, ProviderOAuthRejected):
            if quarantine is not None:
                raise ProviderOAuthQuarantineRequired(quarantine) from None
            raise

    def _validated_token_set(
        self,
        body: dict[str, object],
        *,
        expected_scopes: frozenset[str],
        require_refresh: bool,
        binding: ProviderOAuthTokenBinding,
        retained_refresh: ProviderOAuthRefreshToken | None = None,
    ) -> ProviderOAuthTokenSet:
        token_type = _text(body, "token_type", maximum=32)
        if token_type.casefold() != "bearer":
            raise ProviderOAuthEffectUnknown()
        expires_in = body.get("expires_in")
        if type(expires_in) is not int or not 1 <= expires_in <= 86_400:
            raise ProviderOAuthEffectUnknown()
        self._require_registration_binding(binding)
        try:
            access = ProviderOAuthAccessToken(_text(body, "access_token", maximum=16_384), binding)
            raw_refresh = body.get("refresh_token")
            if raw_refresh is None:
                refresh = retained_refresh
            elif isinstance(raw_refresh, str):
                refresh = ProviderOAuthRefreshToken(raw_refresh, binding)
            else:
                raise ProviderOAuthEffectUnknown()
        except ProviderOAuthError:
            raise
        except (TypeError, ValueError):
            raise ProviderOAuthEffectUnknown() from None
        if refresh is not None and refresh.binding != binding:
            raise ProviderOAuthRejected()
        if require_refresh and refresh is None:
            raise ProviderOAuthRejected()
        raw_scope = body.get("scope")
        if raw_scope is None:
            # RFC 6749 section 5.1 permits omission when the issued scope is
            # identical to the requested scope. Preserve the exact reviewed
            # grant rather than rejecting a standards-compliant response.
            actual_scopes = expected_scopes
        elif isinstance(raw_scope, str):
            try:
                normalized_scope = _text(
                    {"scope": raw_scope}, "scope", maximum=16_384
                )
            except ProviderOAuthError:
                raise
            except Exception:
                raise ProviderOAuthEffectUnknown() from None
            actual_scopes = frozenset(normalized_scope.split())
            if self._registration.provider is ConnectorProvider.MICROSOFT:
                # ``offline_access`` is protocol authority evidenced by the
                # refresh token, not necessarily an access-token scope. Every
                # API/identity scope must still be present and no unexpected
                # resource scope may appear.
                access_scopes = expected_scopes.difference({"offline_access"})
                if (
                    not access_scopes.issubset(actual_scopes)
                    or not actual_scopes.issubset(expected_scopes)
                ):
                    raise ProviderOAuthRejected()
            elif actual_scopes != expected_scopes:
                raise ProviderOAuthRejected()
        else:
            raise ProviderOAuthEffectUnknown()
        issued = _aware(self._now(), "now")
        return ProviderOAuthTokenSet(
            provider=self._registration.provider,
            access_token=access,
            refresh_token=refresh,
            # The durable grant is the exact requested authority. For
            # Microsoft, refresh-token custody attests ``offline_access`` when
            # that protocol scope is omitted from the access-token scope text.
            granted_scopes=expected_scopes,
            issued_at=issued,
            expires_at=issued + timedelta(seconds=expires_in),
        )

    async def exchange_code(
        self,
        *,
        command: OAuthBrokerFlowCommand,
        authorization_code: OAuthAuthorizationCodeSecret,
        verifier: OAuthPkceVerifierSecret,
    ) -> ProviderOAuthTokenSet:
        if command.provider is not self._registration.provider:
            raise ValueError("OAuth flow provider does not match registration")
        if not isinstance(authorization_code, OAuthAuthorizationCodeSecret):
            raise TypeError("authorization_code must be OAuthAuthorizationCodeSecret")
        if not isinstance(verifier, OAuthPkceVerifierSecret):
            raise TypeError("verifier must be OAuthPkceVerifierSecret")
        binding = self._registration.token_binding_for_flow(command)
        body = await self._post_token(
            {
                "client_id": self._registration.client_id,
                "client_secret": self._registration.client_secret._reveal(),
                "code": authorization_code.value,
                "code_verifier": verifier.value,
                "grant_type": "authorization_code",
                "redirect_uri": command.redirect_uri,
            },
            account_kind=command.account_kind,
        )
        return self._token_set(
            body,
            expected_scopes=command.requested_scopes,
            require_refresh=True,
            binding=binding,
        )

    async def refresh(
        self,
        *,
        refresh_token: ProviderOAuthRefreshToken,
        expected_scopes: frozenset[str],
        binding: ProviderOAuthTokenBinding,
    ) -> ProviderOAuthTokenSet:
        if not isinstance(refresh_token, ProviderOAuthRefreshToken):
            raise TypeError("refresh_token must be ProviderOAuthRefreshToken")
        if not isinstance(expected_scopes, frozenset) or not expected_scopes:
            raise ValueError("expected_scopes must be a nonempty frozen set")
        if not isinstance(binding, ProviderOAuthTokenBinding) or not binding.persisted:
            raise ValueError("refresh requires persisted credential provenance")
        self._require_registration_binding(binding)
        refresh_value = refresh_token.require_binding(binding)
        form = {
            "client_id": self._registration.client_id,
            "client_secret": self._registration.client_secret._reveal(),
            "grant_type": "refresh_token",
            "refresh_token": refresh_value,
        }
        if self._registration.provider is ConnectorProvider.MICROSOFT:
            form["scope"] = " ".join(sorted(expected_scopes))
        body = await self._post_token(form, account_kind=binding.account_kind)
        return self._token_set(
            body,
            expected_scopes=expected_scopes,
            require_refresh=True,
            binding=binding,
            retained_refresh=refresh_token,
        )

    async def identify(
        self,
        access_token: ProviderOAuthAccessToken,
        *,
        binding: ProviderOAuthTokenBinding,
    ) -> ProviderExternalAccount:
        if not isinstance(access_token, ProviderOAuthAccessToken):
            raise TypeError("access_token must be ProviderOAuthAccessToken")
        self._require_registration_binding(binding)
        access_value = access_token.require_binding(binding)
        if self._registration.provider is ConnectorProvider.GOOGLE:
            endpoint = _GOOGLE_USERINFO
            query = None
        else:
            endpoint = _MICROSOFT_ME
            query = {"$select": "id"}
        timeout = httpx.Timeout(20.0, connect=7.0, write=10.0, pool=5.0)
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
                    "GET",
                    endpoint,
                    params=query,
                    headers={
                        "Authorization": f"Bearer {access_value}",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    if response.is_redirect or response.status_code != 200:
                        raise ProviderOAuthEffectUnknown()
                    body = await _json(response)
        except ProviderOAuthError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise ProviderOAuthNotDispatched() from None
        except Exception:
            raise ProviderOAuthEffectUnknown() from None
        key = "sub" if self._registration.provider is ConnectorProvider.GOOGLE else "id"
        stable_id = _text(body, key, maximum=512)
        if self._registration.provider is ConnectorProvider.GOOGLE:
            verified = body.get("email_verified")
            if verified is not True:
                raise ProviderOAuthRejected()
            has_hosted_domain = "hd" in body
            hosted_domain = body.get("hd")
            if has_hosted_domain and (
                not isinstance(hosted_domain, str)
                or _HOSTED_DOMAIN.fullmatch(hosted_domain) is None
            ):
                raise ProviderOAuthRejected()
            if has_hosted_domain != (
                binding.account_kind is ConnectorAccountKind.WORK_SCHOOL
            ):
                raise ProviderOAuthRejected()
        return ProviderExternalAccount(
            provider=self._registration.provider,
            account_kind=binding.account_kind,
            external_account_id_hash=_digest(f"{self._registration.provider.value}\x00{stable_id}"),
        )
