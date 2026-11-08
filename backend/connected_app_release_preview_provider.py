"""Sealed dedicated-account provider effects for the one-shot release preview.

The public application remains disabled while this ceremony runs. Each probe
opens only the exact encrypted credential described inside the KMS-sealed host
configuration, refreshes and identifies that account through the fixed OAuth
client, then uses the existing fixed-host credential transports for bounded
mail/calendar reads and reversible preview writes. Every created artifact is
read back and removed before provider grant revocation and local credential
erasure. No customer content is returned or persisted.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import SMTP
import hashlib
import hmac
import json
from typing import Awaitable, Callable, Mapping, Protocol
from urllib.parse import quote, urlencode
from uuid import UUID, uuid5

import certifi
import httpx

from . import config
from .connected_app_contracts import (
    ConnectedAccountRef,
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    CredentialHandleRef,
)
from .connected_app_credential_vault import (
    ConnectedCredentialMasterKey,
    ConnectedCredentialVault,
)
from .connected_app_durable_stores import (
    SupabaseConnectedCredentialRefreshCoordinator,
    SupabaseConnectedCredentialSecretStore,
)
from .connected_app_google import (
    CALENDAR_HOST,
    GMAIL_HOST,
    GoogleTransportRequest,
)
from .connected_app_grant_cleanup import ProviderGrantRevocationSecret
from .connected_app_host_configuration import (
    ConnectedReleasePreviewConnectionConfiguration,
)
from .connected_app_https import (
    ConnectedAccessToken,
    GoogleHTTPSCredentialTransport,
    MicrosoftHTTPSCredentialTransport,
)
from .connected_app_microsoft import (
    GRAPH_HOST,
    GRAPH_ROOT,
    MicrosoftTransportRequest,
    _MAIL_PREFER as _MICROSOFT_MAIL_PREFER,
)
from .connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from .connected_app_provider_oauth import (
    ProviderOAuthAccessToken,
    ProviderOAuthEffectUnknown,
    ProviderOAuthHTTPSClient,
    ProviderOAuthQuarantineRequired,
    ProviderOAuthRegistration,
    ProviderOAuthTokenBinding,
)
from .connected_app_release_effect_ledger import (
    ConnectedReleasePreviewAuthorityPhase,
    ConnectedReleasePreviewAuthorityState,
    ConnectedReleasePreviewEffectLedger,
    ConnectedReleasePreviewEffectPhase,
    ConnectedReleasePreviewEffectState,
    release_preview_marker,
)
from .connected_app_scopes import scopes_cover


_BINDING_KEYS = frozenset(
    {
        "owner_id",
        "connection_id",
        "provider",
        "resource",
        "account_kind",
        "connection_incarnation_id",
        "authorization_revision",
        "authorization_state",
        "authorization_snapshot_sha256",
        "authorization_issued_at",
        "granted_actions",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "external_account_id_sha256",
        "broker_credential_ref",
        "credential_ref_sha256",
        "current_flow_nonce_sha256",
        "authorization_expires_at",
        "revoked_at",
    }
)
_COMPLETION_KEYS = frozenset(
    {
        "completed",
        "active",
        "owner_id",
        "connection_id",
        "connection_incarnation_id",
        "consumption_id",
        "exchange_id",
        "completion_id",
        "completion_binding_sha256",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "authorization_issued_at",
        "granted_actions",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "external_account_id_sha256",
        "broker_credential_ref",
        "credential_ref_sha256",
        "authorization_expires_at",
    }
)
_RETIREMENT_KEYS = frozenset(
    {
        "retired",
        "retirement_id",
        "retirement_binding_sha256",
        "connection_id",
        "authorization_revision",
        "revoked_at",
        "credential_erased",
    }
)
_CREDENTIAL_STATE_KEYS = frozenset({"status", "record"})
_GOOGLE_REDIRECT = "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
_MICROSOFT_REDIRECT = (
    "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
)
_MAIL_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_SEARCH,
        ConnectorActionKind.MAIL_CREATE_DRAFT,
        ConnectorActionKind.MAIL_SEND,
        ConnectorActionKind.MAIL_REPLY,
    }
)
_CALENDAR_ACTIONS = frozenset(
    {
        ConnectorActionKind.CALENDAR_LIST,
        ConnectorActionKind.CALENDAR_CREATE,
        ConnectorActionKind.CALENDAR_UPDATE,
        ConnectorActionKind.CALENDAR_CANCEL,
    }
)
_AMBIGUOUS_DISCOVERY_DELAYS = (0.0, 1.0, 2.0, 4.0, 8.0)
_GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
_MAX_REVOKE_RESPONSE_BYTES = 16_384


class ConnectedReleasePreviewProviderError(RuntimeError):
    def __init__(self) -> None:
        self.code = "CONNECTED_RELEASE_PREVIEW_PROVIDER_FAILED"
        super().__init__(self.code)


class ConnectedReleasePreviewRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


async def _google_preview_revoke(
    secret: ProviderGrantRevocationSecret,
    *,
    transport: httpx.AsyncBaseTransport | None,
    recovering_dispatched: bool,
) -> str:
    """Observe exact Google revocation, including lost-response recovery.

    A 400 is accepted only after the durable database fence proves the same
    exact token was already dispatched for revocation.  The token was proven
    usable earlier in this invocation, so an exact recovery request observing
    it as invalid is provider-side non-usability evidence, not a caller claim.
    """

    if not isinstance(secret, ProviderGrantRevocationSecret) or type(
        recovering_dispatched
    ) is not bool:
        raise ConnectedReleasePreviewProviderError()
    body = urlencode(
        {"token": secret.reveal_for_google_revocation()}
    ).encode("ascii")
    try:
        async with httpx.AsyncClient(
            transport=transport,
            verify=certifi.where(),
            timeout=httpx.Timeout(connect=5.0, write=10.0, read=15.0, pool=5.0),
            follow_redirects=False,
            trust_env=False,
            http2=True,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "AskCrump-ConnectedApps/1",
            },
        ) as client:
            response = await client.post(_GOOGLE_REVOKE, content=body)
    except httpx.HTTPError:
        raise ConnectedReleasePreviewProviderError() from None
    if (
        response.is_redirect
        or len(response.content) > _MAX_REVOKE_RESPONSE_BYTES
        or response.status_code not in ({200, 400} if recovering_dispatched else {200})
    ):
        raise ConnectedReleasePreviewProviderError()
    mode = "http-200" if response.status_code == 200 else "recovery-invalid-token"
    return _canonical_hash(
        {
            "version": "askcrump-google-release-preview-revocation-v1",
            "provider": "google",
            "mode": mode,
        }
    )


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedReleasePreviewProviderError()
    return value.astimezone(UTC)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise ConnectedReleasePreviewProviderError()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedReleasePreviewProviderError() from None
    return _aware(parsed)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedReleasePreviewProviderError()
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedReleasePreviewProviderError() from None
    if canonical != value:
        raise ConnectedReleasePreviewProviderError()
    return canonical


def _object(value: object, *, keys: frozenset[str] | None = None) -> dict[str, object]:
    if type(value) is not dict or (keys is not None and frozenset(value) != keys):
        raise ConnectedReleasePreviewProviderError()
    return value  # type: ignore[return-value]


def _list(value: object, *, maximum: int = 100) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        raise ConnectedReleasePreviewProviderError()
    return value


def _text(value: object, *, maximum: int = 1024) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ConnectedReleasePreviewProviderError()
    return value


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _opened_refresh_secret(
    value: object | None,
) -> ProviderGrantRevocationSecret | None:
    if value is None:
        return None
    try:
        refresh_token = value.refresh_token  # type: ignore[attr-defined]
        return ProviderGrantRevocationSecret(
            refresh_token.require_binding(refresh_token.binding)
        )
    except Exception:
        raise ConnectedReleasePreviewProviderError() from None


def _scope_hash(values: frozenset[str]) -> str:
    encoded = json.dumps(
        sorted(values),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_hash(value: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            dict(value),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ConnectedReleasePreviewProviderError() from None
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ConnectedProviderReleasePreviewReceipt:
    provider: ConnectorProvider
    account_kind: ConnectorAccountKind
    invocation_id: str
    contract_sha256: str
    checked_at: datetime
    dedicated_account_binding_attested: bool
    oauth_callback_attested: bool
    mail_read_attested: bool
    mail_preview_write_attested: bool
    mail_send_attested: bool
    mail_reply_attested: bool
    mail_retained_test_artifact_sha256: str
    calendar_read_attested: bool
    calendar_free_busy_attested: bool
    calendar_free_busy_exempt: bool
    calendar_preview_write_attested: bool
    calendar_cleanup_artifact_sha256: str
    cleanup_attested: bool
    provider_grant_revocation_attested: bool
    local_connection_retirement_attested: bool
    local_credential_erasure_attested: bool
    revocation_mode: str

    def __post_init__(self) -> None:
        common = (
            self.dedicated_account_binding_attested,
            self.oauth_callback_attested,
            self.mail_read_attested,
            self.mail_preview_write_attested,
            self.mail_send_attested,
            self.mail_reply_attested,
            self.calendar_read_attested,
            self.calendar_preview_write_attested,
            self.cleanup_attested,
            self.local_connection_retirement_attested,
            self.local_credential_erasure_attested,
        )
        if (
            not isinstance(self.provider, ConnectorProvider)
            or not isinstance(self.account_kind, ConnectorAccountKind)
            or _uuid(self.invocation_id) != self.invocation_id
            or not isinstance(self.contract_sha256, str)
            or len(self.contract_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.contract_sha256
            )
            or any(value is not True for value in common)
            or len(self.mail_retained_test_artifact_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.mail_retained_test_artifact_sha256
            )
            or len(self.calendar_cleanup_artifact_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.calendar_cleanup_artifact_sha256
            )
            or (
                self.provider is ConnectorProvider.GOOGLE
                and (
                    self.calendar_free_busy_attested is not True
                    or self.calendar_free_busy_exempt is not False
                )
            )
            or (
                self.provider is ConnectorProvider.MICROSOFT
                and self.account_kind is ConnectorAccountKind.WORK_SCHOOL
                and (
                    self.calendar_free_busy_attested is not True
                    or self.calendar_free_busy_exempt is not False
                )
            )
            or (
                self.provider is ConnectorProvider.MICROSOFT
                and self.account_kind is ConnectorAccountKind.PERSONAL
                and (
                    self.calendar_free_busy_attested is not False
                    or self.calendar_free_busy_exempt is not True
                )
            )
            or (
                self.provider is ConnectorProvider.GOOGLE
                and (
                    self.provider_grant_revocation_attested is not True
                    or self.revocation_mode
                    != "provider_grant_and_local_retirement"
                )
            )
            or (
                self.provider is ConnectorProvider.MICROSOFT
                and (
                    self.provider_grant_revocation_attested is not False
                    or self.revocation_mode
                    != "local_credential_and_connection_retirement"
                )
            )
        ):
            raise ConnectedReleasePreviewProviderError()
        object.__setattr__(self, "checked_at", _aware(self.checked_at))


@dataclass(slots=True, repr=False)
class _PreviewAccessTokenSource:
    account: ConnectedAccountRef
    credential: CredentialHandleRef
    access_token: ProviderOAuthAccessToken = field(repr=False)
    binding: ProviderOAuthTokenBinding = field(repr=False)
    expires_at: datetime

    async def issue_access_token(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
    ) -> ConnectedAccessToken:
        if account != self.account or credential != self.credential:
            raise ConnectedReleasePreviewProviderError()
        token = self.access_token.require_binding(self.binding)
        return ConnectedAccessToken(
            owner_id=account.owner_id,
            connection_id=account.connection_id,
            provider=account.provider,
            credential_handle_sha256=_sha256(credential.handle_id),
            expires_at=self.expires_at,
            token=token,
        )

    def __repr__(self) -> str:
        return "_PreviewAccessTokenSource(token='<redacted>')"


@dataclass(slots=True, repr=False)
class ConnectedPreparedReleasePreviewCredential:
    account: ConnectedAccountRef
    credential: CredentialHandleRef
    connection_incarnation_id: str
    source: _PreviewAccessTokenSource = field(repr=False)
    refresh_token: ProviderGrantRevocationSecret = field(repr=False)
    vault: ConnectedCredentialVault = field(repr=False)
    controller: ConnectedReleasePreviewCredentialSource = field(repr=False)
    authorization_revision: int
    authorization_snapshot_sha256: str
    current_flow_nonce_sha256: str = field(repr=False)

    async def erase(self) -> None:
        await self.vault.erase(
            account=self.account,
            credential=self.credential,
            connection_incarnation_id=self.connection_incarnation_id,
        )

    async def retire(self, *, invocation_id: str) -> None:
        await self.controller.retire(self, invocation_id=invocation_id)

    def __repr__(self) -> str:
        return (
            "ConnectedPreparedReleasePreviewCredential("
            f"provider={self.account.provider.value!r}, credential='<redacted>')"
        )


class ConnectedReleasePreviewCredentialSource:
    """Open, refresh, and live-identify one exact encrypted preview credential."""

    __slots__ = (
        "_client",
        "_database",
        "_descriptor",
        "_now",
        "_oauth_transport",
        "_registration",
        "_vault",
    )

    def __init__(
        self,
        *,
        database: ConnectedReleasePreviewRPC,
        credential_key: ConnectedCredentialMasterKey,
        registration: ProviderOAuthRegistration,
        descriptor: ConnectedReleasePreviewConnectionConfiguration,
        oauth_transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            not callable(getattr(database, "rpc", None))
            or not isinstance(credential_key, ConnectedCredentialMasterKey)
            or type(registration) is not ProviderOAuthRegistration
            or type(descriptor)
            is not ConnectedReleasePreviewConnectionConfiguration
            or registration.provider is not descriptor.provider
            or not callable(now)
        ):
            raise ConnectedReleasePreviewProviderError()
        self._database = database
        self._registration = registration
        self._descriptor = descriptor
        self._now = now
        self._oauth_transport = oauth_transport
        self._vault = ConnectedCredentialVault(
            keys={credential_key.key_id: credential_key},
            active_key_id=credential_key.key_id,
            store=SupabaseConnectedCredentialSecretStore(database),
            now=now,
        )
        self._client = ProviderOAuthHTTPSClient(
            registration,
            transport=oauth_transport,
            now=now,
        )

    def production_eligible(
        self,
        *,
        database: ConnectedReleasePreviewRPC,
        registration: ProviderOAuthRegistration,
    ) -> bool:
        return (
            type(self) is ConnectedReleasePreviewCredentialSource
            and self._database is database
            and self._registration is registration
            and self._oauth_transport is None
            and self._client._transport is None
        )

    async def _completion(self) -> dict[str, object]:
        descriptor = self._descriptor
        try:
            value = await self._database.rpc(
                "connected_app_oauth_read_completion_v3",
                {
                    "p_completion_id": descriptor.oauth_completion_id,
                    "p_completion_binding_sha256": (
                        descriptor.oauth_completion_binding_sha256
                    ),
                    "p_owner_id": descriptor.owner_id,
                    "p_connection_id": descriptor.connection_id,
                },
                retry_transient=True,
            )
        except Exception:
            raise ConnectedReleasePreviewProviderError() from None
        row = _object(value, keys=_COMPLETION_KEYS)
        if (
            row["completed"] is not True
            or row["active"] is not True
            or row["owner_id"] != descriptor.owner_id
            or row["connection_id"] != descriptor.connection_id
            or row["connection_incarnation_id"]
            != descriptor.connection_incarnation_id
            or row["completion_id"] != descriptor.oauth_completion_id
            or row["completion_binding_sha256"]
            != descriptor.oauth_completion_binding_sha256
            or row["authorization_snapshot_sha256"]
            != descriptor.authorization_snapshot_sha256
            or row["external_account_id_sha256"]
            != descriptor.external_account_id_hash
            or row["credential_ref_sha256"]
            != descriptor.credential_handle_sha256
            or _sha256(_uuid(row["broker_credential_ref"]))
            != descriptor.credential_handle_sha256
        ):
            raise ConnectedReleasePreviewProviderError()
        return row

    async def _binding(
        self,
    ) -> tuple[ConnectedAccountRef, CredentialHandleRef, ConnectedAuthorizationSnapshot]:
        descriptor = self._descriptor
        completion = await self._completion()
        try:
            value = await self._database.rpc(
                "connected_app_get_binding_v2",
                {
                    "p_owner_id": descriptor.owner_id,
                    "p_connection_id": descriptor.connection_id,
                },
                retry_transient=True,
            )
        except Exception:
            raise ConnectedReleasePreviewProviderError() from None
        row = _object(value, keys=_BINDING_KEYS)
        try:
            actions_raw = row["granted_actions"]
            actions = (
                frozenset(ConnectorActionKind(item) for item in actions_raw)
                if type(actions_raw) is list
                else frozenset()
            )
            credential_id = _uuid(row["broker_credential_ref"])
            issued = _timestamp(row["authorization_issued_at"])
            expires = _timestamp(row["authorization_expires_at"])
            authorization = ConnectedAuthorizationSnapshot.build(
                owner_id=descriptor.owner_id,
                connection_id=descriptor.connection_id,
                provider=descriptor.provider,
                resource=descriptor.resource,
                account_kind=descriptor.account_kind,
                revision=int(row["authorization_revision"]),
                granted_actions=actions,
                granted_scopes=descriptor.granted_scopes,
                state=ConnectionAuthorizationState.ACTIVE,
                issued_at=issued,
                expires_at=expires,
            )
        except Exception:
            raise ConnectedReleasePreviewProviderError() from None
        required_actions = _MAIL_ACTIONS
        if descriptor.resource is ConnectorResource.CALENDAR:
            required_actions = _CALENDAR_ACTIONS
            if (
                descriptor.provider is ConnectorProvider.GOOGLE
                or descriptor.account_kind is ConnectorAccountKind.WORK_SCHOOL
            ):
                required_actions = required_actions | {
                    ConnectorActionKind.CALENDAR_FREE_BUSY
                }
        if (
            row["owner_id"] != descriptor.owner_id
            or row["connection_id"] != descriptor.connection_id
            or row["provider"] != descriptor.provider.value
            or row["resource"] != descriptor.resource.value
            or row["account_kind"] != descriptor.account_kind.value
            or row["connection_incarnation_id"]
            != descriptor.connection_incarnation_id
            or row["authorization_state"] != "active"
            or row["authorization_snapshot_sha256"]
            != descriptor.authorization_snapshot_sha256
            or authorization.snapshot_sha256
            != descriptor.authorization_snapshot_sha256
            or row["granted_actions_sha256"]
            != authorization.granted_actions_sha256
            or row["granted_scopes_sha256"]
            != authorization.granted_scopes_sha256
            or row["granted_scopes_sha256"]
            != _scope_hash(descriptor.granted_scopes)
            or row["external_account_id_sha256"]
            != descriptor.external_account_id_hash
            or _sha256(credential_id) != descriptor.credential_handle_sha256
            or row["credential_ref_sha256"] != descriptor.credential_handle_sha256
            or row["revoked_at"] is not None
            or row["current_flow_nonce_sha256"]
            != descriptor.current_flow_nonce_sha256
            or row["authorization_revision"]
            != completion["authorization_revision"]
            or row["authorization_issued_at"]
            != completion["authorization_issued_at"]
            or row["authorization_expires_at"]
            != completion["authorization_expires_at"]
            or row["granted_actions"] != completion["granted_actions"]
            or row["granted_actions_sha256"]
            != completion["granted_actions_sha256"]
            or row["granted_scopes_sha256"]
            != completion["granted_scopes_sha256"]
            or not required_actions.issubset(actions)
            or not scopes_cover(
                provider=descriptor.provider,
                granted_scopes=descriptor.granted_scopes,
                actions=required_actions,
                account_kind=descriptor.account_kind,
            )
            or not authorization.active_at(_aware(self._now()))
        ):
            raise ConnectedReleasePreviewProviderError()
        account = ConnectedAccountRef(
            owner_id=descriptor.owner_id,
            connection_id=descriptor.connection_id,
            provider=descriptor.provider,
            resource=descriptor.resource,
            account_kind=descriptor.account_kind,
            external_account_id_hash=descriptor.external_account_id_hash,
        )
        credential = CredentialHandleRef(
            owner_id=descriptor.owner_id,
            connection_id=descriptor.connection_id,
            provider=descriptor.provider,
            handle_id=credential_id,
        )
        return account, credential, authorization

    async def prepare(
        self,
        *,
        invocation_id: str,
        google_revocation_transport: httpx.AsyncBaseTransport | None = None,
        effect_ledger: ConnectedReleasePreviewEffectLedger | None = None,
    ) -> ConnectedPreparedReleasePreviewCredential:
        if (
            config.connected_apps_release_candidate_source_released() is not True
            or (
                effect_ledger is not None
                and (
                    type(effect_ledger) is not ConnectedReleasePreviewEffectLedger
                    or effect_ledger.invocation_id != invocation_id
                )
            )
        ):
            raise ConnectedReleasePreviewProviderError()
        _uuid(invocation_id)
        account, credential, authorization = await self._binding()
        current = None
        refresh_lease = None
        coordinator = SupabaseConnectedCredentialRefreshCoordinator(
            self._database,
            now=self._now,
        )
        try:
            current = await self._vault.open(
                account=account,
                credential=credential,
                connection_incarnation_id=self._descriptor.connection_incarnation_id,
                authorization=authorization,
            )
            refresh_lease = await coordinator.claim(
                credential=credential,
                expected_record_binding_sha256=(
                    current.record.record_binding_sha256
                ),
                lease_for=timedelta(seconds=30),
            )
            current = await self._vault.open(
                account=account,
                credential=credential,
                connection_incarnation_id=self._descriptor.connection_incarnation_id,
                authorization=authorization,
            )
            token_set = await self._client.refresh(
                refresh_token=current.refresh_token,
                expected_scopes=current.granted_scopes,
                binding=current.refresh_token.binding,
            )
            if (
                token_set.provider is not account.provider
                or token_set.granted_scopes != authorization.granted_scopes
                or token_set.refresh_token is None
                or token_set.expires_at <= _aware(self._now()) + timedelta(minutes=2)
            ):
                raise ConnectedReleasePreviewProviderError()
            old_refresh = current.refresh_token.require_binding(
                current.refresh_token.binding
            )
            new_refresh = token_set.refresh_token.require_binding(
                current.refresh_token.binding
            )
            if not hmac.compare_digest(old_refresh, new_refresh):
                await self._vault.rotate(
                    current,
                    token_set.refresh_token,
                    refresh_coordinator=coordinator,
                    refresh_lease=refresh_lease,
                )
                refresh_lease = None
                current = await self._vault.open(
                    account=account,
                    credential=credential,
                    connection_incarnation_id=(
                        self._descriptor.connection_incarnation_id
                    ),
                    authorization=authorization,
                )
            else:
                await coordinator.finish(refresh_lease)
                refresh_lease = None
            identity = await self._client.identify(
                token_set.access_token,
                binding=current.refresh_token.binding,
            )
            if (
                identity.provider is not account.provider
                or identity.account_kind is not account.account_kind
                or identity.external_account_id_hash
                != account.external_account_id_hash
            ):
                raise ConnectedReleasePreviewProviderError()
            source = _PreviewAccessTokenSource(
                account=account,
                credential=credential,
                access_token=token_set.access_token,
                binding=current.refresh_token.binding,
                expires_at=token_set.expires_at,
            )
            return ConnectedPreparedReleasePreviewCredential(
                account=account,
                credential=credential,
                connection_incarnation_id=self._descriptor.connection_incarnation_id,
                source=source,
                refresh_token=ProviderGrantRevocationSecret(new_refresh),
                vault=self._vault,
                controller=self,
                authorization_revision=authorization.revision,
                authorization_snapshot_sha256=authorization.snapshot_sha256,
                current_flow_nonce_sha256=self._descriptor.current_flow_nonce_sha256,
            )
        except ProviderOAuthQuarantineRequired as quarantined:
            quarantine_secret = _opened_refresh_secret(current)
            if (
                current is not None
                and refresh_lease is not None
                and quarantined.token_set.refresh_token is not None
                and quarantined.token_set.binding == current.refresh_token.binding
            ):
                quarantine_secret = ProviderGrantRevocationSecret(
                    quarantined.token_set.refresh_token.require_binding(
                        current.refresh_token.binding
                    )
                )
                try:
                    await self._vault.rotate(
                        current,
                        quarantined.token_set.refresh_token,
                        refresh_coordinator=coordinator,
                        refresh_lease=refresh_lease,
                    )
                    refresh_lease = None
                    current = await self._vault.open(
                        account=account,
                        credential=credential,
                        connection_incarnation_id=(
                            self._descriptor.connection_incarnation_id
                        ),
                        authorization=authorization,
                    )
                except Exception:
                    try:
                        await coordinator.quarantine(refresh_lease)
                    except Exception:
                        pass
                    refresh_lease = None
                    try:
                        current = await self._vault.open(
                            account=account,
                            credential=credential,
                            connection_incarnation_id=(
                                self._descriptor.connection_incarnation_id
                            ),
                            authorization=authorization,
                        )
                        opened_secret = _opened_refresh_secret(current)
                        if (
                            account.provider is not ConnectorProvider.GOOGLE
                            or quarantine_secret is None
                            or opened_secret is None
                            or hmac.compare_digest(
                                opened_secret.reveal_for_google_revocation(),
                                quarantine_secret.reveal_for_google_revocation(),
                            )
                        ):
                            quarantine_secret = opened_secret
                    except Exception:
                        # The durable release-preview effect remains DISPATCHED
                        # if cleanup below cannot settle.  The provider-issued
                        # replacement is still sufficient to revoke Google's
                        # grant without trusting a stale local readback.
                        current = None
                    await self._cleanup_failed_prepare(
                        account=account,
                        credential=credential,
                        authorization=authorization,
                        google_revocation_secret=quarantine_secret,
                        invocation_id=invocation_id,
                        google_revocation_transport=google_revocation_transport,
                        effect_ledger=effect_ledger,
                    )
                    raise ConnectedReleasePreviewProviderError() from None
            elif refresh_lease is not None:
                try:
                    await coordinator.quarantine(refresh_lease)
                except Exception:
                    pass
                refresh_lease = None
            await self._cleanup_failed_prepare(
                account=account,
                credential=credential,
                authorization=authorization,
                google_revocation_secret=quarantine_secret,
                invocation_id=invocation_id,
                google_revocation_transport=google_revocation_transport,
                effect_ledger=effect_ledger,
            )
            raise ConnectedReleasePreviewProviderError() from None
        except ProviderOAuthEffectUnknown:
            if refresh_lease is not None:
                try:
                    await coordinator.quarantine(refresh_lease)
                except Exception:
                    pass
                refresh_lease = None
            await self._cleanup_failed_prepare(
                account=account,
                credential=credential,
                authorization=authorization,
                google_revocation_secret=_opened_refresh_secret(current),
                invocation_id=invocation_id,
                google_revocation_transport=google_revocation_transport,
                effect_ledger=effect_ledger,
            )
            raise ConnectedReleasePreviewProviderError() from None
        except ConnectedReleasePreviewProviderError:
            await self._cleanup_failed_prepare(
                account=account,
                credential=credential,
                authorization=authorization,
                google_revocation_secret=_opened_refresh_secret(current),
                invocation_id=invocation_id,
                google_revocation_transport=google_revocation_transport,
                effect_ledger=effect_ledger,
            )
            raise
        except Exception:
            await self._cleanup_failed_prepare(
                account=account,
                credential=credential,
                authorization=authorization,
                google_revocation_secret=_opened_refresh_secret(current),
                invocation_id=invocation_id,
                google_revocation_transport=google_revocation_transport,
                effect_ledger=effect_ledger,
            )
            raise ConnectedReleasePreviewProviderError() from None
        finally:
            if refresh_lease is not None:
                try:
                    await coordinator.finish(refresh_lease)
                except Exception:
                    pass

    async def revocation_secret(
        self,
    ) -> ProviderGrantRevocationSecret:
        """Open the exact active refresh credential without provider I/O.

        Recovery uses this after a durable revocation-dispatch fence.  It
        deliberately does not refresh or identify the account, so a prior
        successful provider revocation cannot turn recovery into a new grant
        or a second business effect.
        """

        if config.connected_apps_release_candidate_source_released() is not True:
            raise ConnectedReleasePreviewProviderError()
        account, credential, authorization = await self._binding()
        try:
            current = await self._vault.open(
                account=account,
                credential=credential,
                connection_incarnation_id=(
                    self._descriptor.connection_incarnation_id
                ),
                authorization=authorization,
            )
            value = current.refresh_token.require_binding(
                current.refresh_token.binding
            )
        except Exception:
            raise ConnectedReleasePreviewProviderError() from None
        return ProviderGrantRevocationSecret(value)

    async def retirement_attested(self, *, invocation_id: str) -> bool:
        _uuid(invocation_id)
        descriptor = self._descriptor
        try:
            value = await self._database.rpc(
                "connected_app_get_binding_v2",
                {
                    "p_owner_id": descriptor.owner_id,
                    "p_connection_id": descriptor.connection_id,
                },
                retry_transient=True,
            )
            row = _object(value, keys=_BINDING_KEYS)
        except Exception:
            raise ConnectedReleasePreviewProviderError() from None
        exact = bool(
            row["owner_id"] == descriptor.owner_id
            and row["connection_id"] == descriptor.connection_id
            and row["provider"] == descriptor.provider.value
            and row["resource"] == descriptor.resource.value
            and row["account_kind"] == descriptor.account_kind.value
            and row["connection_incarnation_id"]
            == descriptor.connection_incarnation_id
            and row["authorization_state"] == "revoked"
            and row["authorization_snapshot_sha256"]
            == descriptor.authorization_snapshot_sha256
            and row["external_account_id_sha256"]
            == descriptor.external_account_id_hash
            and row["broker_credential_ref"] is None
            and row["credential_ref_sha256"] is None
            and row["current_flow_nonce_sha256"] is None
            and row["authorization_expires_at"] is None
            and row["revoked_at"] is not None
        )
        if not exact:
            return False
        revision = row["authorization_revision"]
        if type(revision) is not int or revision < 2:
            raise ConnectedReleasePreviewProviderError()
        try:
            credential_state = _object(
                await self._database.rpc(
                    "connected_app_credential_read_v1",
                    {
                        "p_credential_handle_sha256": (
                            descriptor.credential_handle_sha256
                        )
                    },
                    retry_transient=True,
                ),
                keys=_CREDENTIAL_STATE_KEYS,
            )
        except Exception:
            raise ConnectedReleasePreviewProviderError() from None
        if (
            credential_state["status"] != "erased"
            or credential_state["record"] is not None
        ):
            raise ConnectedReleasePreviewProviderError()
        account = ConnectedAccountRef(
            owner_id=descriptor.owner_id,
            connection_id=descriptor.connection_id,
            provider=descriptor.provider,
            resource=descriptor.resource,
            account_kind=descriptor.account_kind,
            external_account_id_hash=descriptor.external_account_id_hash,
        )
        await self._retire_authority(
            account=account,
            credential_ref_sha256=descriptor.credential_handle_sha256,
            authorization_revision=revision - 1,
            authorization_snapshot_sha256=(
                descriptor.authorization_snapshot_sha256
            ),
            current_flow_nonce_sha256=descriptor.current_flow_nonce_sha256,
            connection_incarnation_id=descriptor.connection_incarnation_id,
            invocation_id=invocation_id,
        )
        return True

    async def retire_descriptor(self, *, invocation_id: str) -> None:
        """Retire an active descriptor or attest its exact idempotent replay."""

        _uuid(invocation_id)
        if await self.retirement_attested(invocation_id=invocation_id):
            return
        account, credential, authorization = await self._binding()
        await self._vault.erase(
            account=account,
            credential=credential,
            connection_incarnation_id=self._descriptor.connection_incarnation_id,
        )
        await self._retire_authority(
            account=account,
            credential_ref_sha256=self._descriptor.credential_handle_sha256,
            authorization_revision=authorization.revision,
            authorization_snapshot_sha256=authorization.snapshot_sha256,
            current_flow_nonce_sha256=self._descriptor.current_flow_nonce_sha256,
            connection_incarnation_id=self._descriptor.connection_incarnation_id,
            invocation_id=invocation_id,
        )
        if await self.retirement_attested(invocation_id=invocation_id) is not True:
            raise ConnectedReleasePreviewProviderError()

    async def _cleanup_failed_prepare(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        authorization: ConnectedAuthorizationSnapshot,
        google_revocation_secret: ProviderGrantRevocationSecret | None,
        invocation_id: str,
        google_revocation_transport: httpx.AsyncBaseTransport | None,
        effect_ledger: ConnectedReleasePreviewEffectLedger | None,
    ) -> None:
        if account.provider is ConnectorProvider.GOOGLE:
            if effect_ledger is None:
                if google_revocation_secret is None:
                    raise ConnectedReleasePreviewProviderError()
                await _google_preview_revoke(
                    google_revocation_secret,
                    transport=google_revocation_transport,
                    recovering_dispatched=False,
                )
            else:
                authority = await effect_ledger.authority_for(
                    provider=ConnectorProvider.GOOGLE,
                    account_kind=account.account_kind,
                )
                recovering_dispatched = (
                    authority.phase
                    is ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
                )
                if authority.phase is ConnectedReleasePreviewAuthorityPhase.PENDING:
                    authority = await effect_ledger.transition_authority(
                        state=authority,
                        next_phase=(
                            ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
                        ),
                    )
                if (
                    authority.phase
                    is ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
                ):
                    if google_revocation_secret is None:
                        raise ConnectedReleasePreviewProviderError()
                    receipt = await _google_preview_revoke(
                        google_revocation_secret,
                        transport=google_revocation_transport,
                        recovering_dispatched=recovering_dispatched,
                    )
                    authority = await effect_ledger.transition_authority(
                        state=authority,
                        next_phase=(
                            ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED
                        ),
                        provider_receipt_sha256=receipt,
                    )
                if authority.phase not in {
                    ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED,
                    ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED,
                }:
                    raise ConnectedReleasePreviewProviderError()
        await self._vault.erase(
            account=account,
            credential=credential,
            connection_incarnation_id=self._descriptor.connection_incarnation_id,
        )
        await self._retire_authority(
            account=account,
            credential_ref_sha256=self._descriptor.credential_handle_sha256,
            authorization_revision=authorization.revision,
            authorization_snapshot_sha256=authorization.snapshot_sha256,
            current_flow_nonce_sha256=(
                self._descriptor.current_flow_nonce_sha256
            ),
            connection_incarnation_id=(
                self._descriptor.connection_incarnation_id
            ),
            invocation_id=invocation_id,
        )

    async def retire(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        invocation_id: str,
    ) -> None:
        if (
            not isinstance(prepared, ConnectedPreparedReleasePreviewCredential)
            or prepared.controller is not self
            or prepared.account.connection_id != self._descriptor.connection_id
            or prepared.credential.handle_id is None
        ):
            raise ConnectedReleasePreviewProviderError()
        await prepared.erase()
        await self._retire_authority(
            account=prepared.account,
            credential_ref_sha256=_sha256(prepared.credential.handle_id),
            authorization_revision=prepared.authorization_revision,
            authorization_snapshot_sha256=prepared.authorization_snapshot_sha256,
            current_flow_nonce_sha256=prepared.current_flow_nonce_sha256,
            connection_incarnation_id=prepared.connection_incarnation_id,
            invocation_id=invocation_id,
        )

    async def _retire_authority(
        self,
        *,
        account: ConnectedAccountRef,
        credential_ref_sha256: str,
        authorization_revision: int,
        authorization_snapshot_sha256: str,
        current_flow_nonce_sha256: str,
        connection_incarnation_id: str,
        invocation_id: str,
    ) -> None:
        if (
            not isinstance(credential_ref_sha256, str)
            or len(credential_ref_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in credential_ref_sha256
            )
        ):
            raise ConnectedReleasePreviewProviderError()
        retirement_id = str(
            uuid5(
                UUID(_uuid(invocation_id)),
                "askcrump-release-preview-retire:"
                + account.provider.value
                + ":"
                + account.account_kind.value
                + ":"
                + account.resource.value,
            )
        )

        retirement_binding = _canonical_hash(
            {
                "version": "askcrump-release-preview-retirement-v1",
                "retirement_id": retirement_id,
                "invocation_id": invocation_id,
                "owner_id": account.owner_id,
                "connection_id": account.connection_id,
                "connection_incarnation_id": connection_incarnation_id,
                "provider": account.provider.value,
                "account_kind": account.account_kind.value,
                "resource": account.resource.value,
                "authorization_revision": authorization_revision,
                "authorization_snapshot_sha256": authorization_snapshot_sha256,
                "current_flow_nonce_sha256": current_flow_nonce_sha256,
                "credential_handle_sha256": credential_ref_sha256,
            }
        )
        payload = {
            "p_owner_id": account.owner_id,
            "p_connection_id": account.connection_id,
            "p_connection_incarnation_id": connection_incarnation_id,
            "p_expected_authorization_revision": authorization_revision,
            "p_current_flow_nonce_sha256": current_flow_nonce_sha256,
            "p_authorization_snapshot_sha256": authorization_snapshot_sha256,
            "p_credential_ref_sha256": credential_ref_sha256,
            "p_retirement_id": retirement_id,
            "p_retirement_binding_sha256": retirement_binding,
        }
        result = None
        for _attempt in range(2):
            try:
                result = await self._database.rpc(
                    "connected_app_release_preview_retire_connection_v1",
                    payload,
                    retry_transient=False,
                )
                break
            except Exception:
                continue
        if result is None:
            raise ConnectedReleasePreviewProviderError()
        row = _object(result, keys=_RETIREMENT_KEYS)
        if (
            row["retired"] is not True
            or row["retirement_id"] != retirement_id
            or row["retirement_binding_sha256"] != retirement_binding
            or row["connection_id"] != account.connection_id
            or row["authorization_revision"] != authorization_revision + 1
            or row["credential_erased"] is not True
        ):
            raise ConnectedReleasePreviewProviderError()
        _timestamp(row["revoked_at"])
        try:
            value = await self._database.rpc(
                "connected_app_get_binding_v2",
                {
                    "p_owner_id": account.owner_id,
                    "p_connection_id": account.connection_id,
                },
                retry_transient=True,
            )
            observed = _object(value, keys=_BINDING_KEYS)
        except Exception:
            raise ConnectedReleasePreviewProviderError() from None
        if (
            observed["owner_id"] != account.owner_id
            or observed["connection_id"] != account.connection_id
            or observed["connection_incarnation_id"]
            != connection_incarnation_id
            or observed["authorization_state"] != "revoked"
            or observed["broker_credential_ref"] is not None
            or observed["credential_ref_sha256"] is not None
            or observed["current_flow_nonce_sha256"] is not None
            or observed["authorization_expires_at"] is not None
            or observed["revoked_at"] is None
            or observed["authorization_revision"]
            != authorization_revision + 1
        ):
            raise ConnectedReleasePreviewProviderError()

    def __repr__(self) -> str:
        return (
            "ConnectedReleasePreviewCredentialSource("
            f"provider={self._descriptor.provider.value!r}, credential='<redacted>')"
        )


def _provider_sources(
    value: Mapping[ConnectorResource, ConnectedReleasePreviewCredentialSource],
    *,
    provider: ConnectorProvider,
) -> dict[ConnectorResource, ConnectedReleasePreviewCredentialSource]:
    if not isinstance(value, Mapping) or set(value) != {
        ConnectorResource.MAIL,
        ConnectorResource.CALENDAR,
    }:
        raise ConnectedReleasePreviewProviderError()
    sources = dict(value)
    if any(
        type(source) is not ConnectedReleasePreviewCredentialSource
        or source._descriptor.provider is not provider
        or source._descriptor.resource is not resource
        for resource, source in sources.items()
    ):
        raise ConnectedReleasePreviewProviderError()
    return sources


def _marker(
    invocation_id: str,
    *,
    provider: ConnectorProvider,
    account_kind: ConnectorAccountKind,
    resource: ConnectorResource,
) -> str:
    return release_preview_marker(
        invocation_id=_uuid(invocation_id),
        provider=provider,
        account_kind=account_kind,
        resource=resource,
    )


async def _mark_group_effects_unknown(
    *,
    effect_ledger: ConnectedReleasePreviewEffectLedger,
    provider: ConnectorProvider,
    account_kind: ConnectorAccountKind,
) -> None:
    """Set only unsettled effects to the truthful terminal failure phase."""

    for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR):
        state = await effect_ledger.state_for(
            provider=provider,
            account_kind=account_kind,
            resource=resource,
        )
        if state.phase in {
            ConnectedReleasePreviewEffectPhase.DISPATCHED,
            ConnectedReleasePreviewEffectPhase.OBSERVED,
            ConnectedReleasePreviewEffectPhase.CLEANUP,
        }:
            await effect_ledger.transition(
                state=state,
                next_phase=ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN,
            )
        elif state.phase not in {
            ConnectedReleasePreviewEffectPhase.CLEAN,
            ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT,
            ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN,
        }:
            raise ConnectedReleasePreviewProviderError()


def _google_raw_mail(marker: str) -> str:
    message = EmailMessage(policy=SMTP)
    message["To"] = "askcrump-preview@example.invalid"
    message["Subject"] = marker
    message["X-Ask-Crump-Release-Preview"] = marker
    message.set_content(marker)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def _google_send_raw(
    *,
    marker: str,
    recipient: str,
    in_reply_to: str | None = None,
) -> str:
    message = EmailMessage(policy=SMTP)
    message["To"] = recipient
    message["Subject"] = ("Re: " if in_reply_to else "") + marker
    message["X-Ask-Crump-Release-Preview"] = marker
    message_id = (
        "<"
        + hashlib.sha256(marker.encode("ascii")).hexdigest()[:40]
        + "@release-preview.askcrump.invalid>"
    )
    message["Message-ID"] = message_id
    if in_reply_to is not None:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to
    message.set_content(marker)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def _decode_google_raw(value: object) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 1_000_000:
        raise ConnectedReleasePreviewProviderError()
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        raise ConnectedReleasePreviewProviderError() from None
    if not decoded or len(decoded) > 512_000:
        raise ConnectedReleasePreviewProviderError()
    return decoded


def _google_raw_has_marker(raw: bytes, marker: str) -> bool:
    """Validate the marker after MIME/quoted-printable unfolding.

    Release-preview markers are deliberately account- and invocation-bound and
    can exceed the RFC 5322 recommended line length.  Searching the encoded
    wire bytes would therefore reject a valid message after normal header or
    quoted-printable folding.  Parsing also prevents a marker appearing only
    in unrelated encoded bytes from being accepted as provenance.
    """

    try:
        message = BytesParser(policy=SMTP).parsebytes(raw)
        if message["X-Ask-Crump-Release-Preview"] != marker:
            return False
        body = message.get_body(preferencelist=("plain",))
        if body is None:
            return False
        content = body.get_content()
    except (KeyError, TypeError, ValueError, UnicodeError):
        return False
    return isinstance(content, str) and content.rstrip("\r\n") == marker


class ConnectedGoogleReleasePreviewProbe:
    """Concrete Google OAuth/Gmail/Calendar preview with observed cleanup."""

    __slots__ = (
        "_contract_sha256",
        "_now",
        "_provider_transport",
        "_revoke_transport",
        "_sleep",
        "_sources",
    )

    def __init__(
        self,
        *,
        sources: Mapping[ConnectorResource, ConnectedReleasePreviewCredentialSource],
        contract_sha256: str,
        provider_transport: httpx.AsyncBaseTransport | None = None,
        revoke_transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        sources_copy = _provider_sources(sources, provider=ConnectorProvider.GOOGLE)
        if (
            not isinstance(contract_sha256, str)
            or len(contract_sha256) != 64
            or any(character not in "0123456789abcdef" for character in contract_sha256)
            or not callable(now)
            or not callable(sleep)
        ):
            raise ConnectedReleasePreviewProviderError()
        self._sources = sources_copy
        self._contract_sha256 = contract_sha256
        self._provider_transport = provider_transport
        self._revoke_transport = revoke_transport
        self._sleep = sleep
        self._now = now

    def production_eligible(
        self,
        *,
        database: ConnectedReleasePreviewRPC,
        registration: ProviderOAuthRegistration,
    ) -> bool:
        return (
            type(self) is ConnectedGoogleReleasePreviewProbe
            and self._provider_transport is None
            and self._revoke_transport is None
            and self._sleep is asyncio.sleep
            and type(registration) is ProviderOAuthRegistration
            and registration.provider is ConnectorProvider.GOOGLE
            and all(
                source.production_eligible(
                    database=database,
                    registration=registration,
                )
                for source in self._sources.values()
            )
        )

    async def abort_unstarted_or_revoked(
        self,
        *,
        invocation_id: str,
        effect_ledger: ConnectedReleasePreviewEffectLedger,
    ) -> None:
        """Retire this exact group without repeating an unsettled effect."""

        if (
            type(effect_ledger) is not ConnectedReleasePreviewEffectLedger
            or effect_ledger.invocation_id != invocation_id
        ):
            raise ConnectedReleasePreviewProviderError()
        account_kind = self._sources[
            ConnectorResource.MAIL
        ]._descriptor.account_kind
        states = tuple(
            await effect_ledger.state_for(
                provider=ConnectorProvider.GOOGLE,
                account_kind=account_kind,
                resource=resource,
            )
            for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR)
        )
        authority = await effect_ledger.authority_for(
            provider=ConnectorProvider.GOOGLE,
            account_kind=account_kind,
        )
        if authority.phase is ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED:
            return
        if (
            authority.phase is ConnectedReleasePreviewAuthorityPhase.PENDING
            and any(
                state.phase is not ConnectedReleasePreviewEffectPhase.PENDING
                for state in states
            )
        ) or any(
            state.phase
            in {
                ConnectedReleasePreviewEffectPhase.OBSERVED,
                ConnectedReleasePreviewEffectPhase.CLEANUP,
            }
            for state in states
        ):
            raise ConnectedReleasePreviewProviderError()
        recovering = (
            authority.phase
            is ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
        )
        if authority.phase is ConnectedReleasePreviewAuthorityPhase.PENDING:
            authority = await effect_ledger.transition_authority(
                state=authority,
                next_phase=(
                    ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
                ),
            )
        if (
            authority.phase
            is ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
        ):
            receipt = await _google_preview_revoke(
                await self._sources[
                    ConnectorResource.MAIL
                ].revocation_secret(),
                transport=self._revoke_transport,
                recovering_dispatched=recovering,
            )
            authority = await effect_ledger.transition_authority(
                state=authority,
                next_phase=(
                    ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED
                ),
                provider_receipt_sha256=receipt,
            )
        if (
            authority.phase
            is ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED
        ):
            for source in self._sources.values():
                await source.retire_descriptor(invocation_id=invocation_id)
            authority = await effect_ledger.transition_authority(
                state=authority,
                next_phase=ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED,
            )
        if authority.phase is not ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED:
            raise ConnectedReleasePreviewProviderError()

    @staticmethod
    async def _request(
        prepared: ConnectedPreparedReleasePreviewCredential,
        request: GoogleTransportRequest,
        *,
        transport: httpx.AsyncBaseTransport | None,
        now: Callable[[], datetime],
    ):
        boundary = GoogleHTTPSCredentialTransport(
            prepared.source,
            transport=transport,
            now=now,
        )
        return await boundary.request(
            account=prepared.account,
            credential=prepared.credential,
            request=request,
        )

    async def _mail_read(
        self, prepared: ConnectedPreparedReleasePreviewCredential
    ) -> None:
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                GMAIL_HOST,
                "/gmail/v1/users/me/messages",
                (("labelIds", "INBOX"), ("maxResults", "1")),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if response.status != 200 or set(body).difference(
            {"messages", "nextPageToken", "resultSizeEstimate"}
        ):
            raise ConnectedReleasePreviewProviderError()
        for item in _list(body.get("messages", []), maximum=1):
            _text(_object(item).get("id"), maximum=512)

    async def _mail_self_address(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
    ) -> str:
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                GMAIL_HOST,
                "/gmail/v1/users/me/profile",
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        address = _text(body.get("emailAddress"), maximum=320)
        if (
            response.status != 200
            or address.count("@") != 1
            or address.startswith("@")
            or address.endswith("@")
        ):
            raise ConnectedReleasePreviewProviderError()
        return address

    async def _sent_message_read(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        message_id: str,
        marker: str,
    ) -> str:
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                GMAIL_HOST,
                f"/gmail/v1/users/me/messages/{quote(message_id, safe='')}",
                (("format", "raw"),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        raw = _decode_google_raw(body.get("raw"))
        thread_id = _text(body.get("threadId"), maximum=512)
        if (
            response.status != 200
            or body.get("id") != message_id
            or not _google_raw_has_marker(raw, marker)
        ):
            raise ConnectedReleasePreviewProviderError()
        return thread_id

    async def _sent_ids_for_marker(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
    ) -> dict[str, str]:
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                GMAIL_HOST,
                "/gmail/v1/users/me/messages",
                (("q", f'in:sent "{marker}"'), ("maxResults", "10")),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if response.status != 200 or body.get("nextPageToken") is not None:
            raise ConnectedReleasePreviewProviderError()
        found: dict[str, str] = {}
        for item in _list(body.get("messages", []), maximum=10):
            message_id = _text(_object(item).get("id"), maximum=512)
            if message_id in found:
                raise ConnectedReleasePreviewProviderError()
            found[message_id] = await self._sent_message_read(
                prepared,
                message_id=message_id,
                marker=marker,
            )
        return found

    async def _send_one_to_self(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
        recipient: str,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> tuple[str, str]:
        found = await self._sent_ids_for_marker(prepared, marker=marker)
        if len(found) == 1:
            return next(iter(found.items()))
        if found:
            raise ConnectedReleasePreviewProviderError()
        try:
            response = await self._request(
                prepared,
                GoogleTransportRequest(
                    "POST",
                    GMAIL_HOST,
                    "/gmail/v1/users/me/messages/send",
                    json_body={
                        "raw": _google_send_raw(
                            marker=marker,
                            recipient=recipient,
                            in_reply_to=in_reply_to,
                        ),
                        **({"threadId": thread_id} if thread_id else {}),
                    },
                ),
                transport=self._provider_transport,
                now=self._now,
            )
            body = _object(response.body)
            message_id = _text(body.get("id"), maximum=512)
            observed_thread = _text(body.get("threadId"), maximum=512)
            if response.status != 200:
                raise ConnectedReleasePreviewProviderError()
            read_thread = await self._sent_message_read(
                prepared,
                message_id=message_id,
                marker=marker,
            )
            if read_thread != observed_thread or (
                thread_id is not None and read_thread != thread_id
            ):
                raise ConnectedReleasePreviewProviderError()
            return message_id, read_thread
        except Exception:
            for delay in _AMBIGUOUS_DISCOVERY_DELAYS:
                if delay:
                    await self._sleep(delay)
                found = await self._sent_ids_for_marker(prepared, marker=marker)
                if len(found) == 1:
                    return next(iter(found.items()))
                if len(found) > 1:
                    break
            raise ConnectedReleasePreviewProviderError() from None

    async def _send_reply_proof(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
    ) -> str:
        recipient = await self._mail_self_address(prepared)
        sent_marker = marker + "-send"
        reply_marker = marker + "-reply"
        sent_id, thread_id = await self._send_one_to_self(
            prepared,
            marker=sent_marker,
            recipient=recipient,
        )
        original_message_id = (
            "<"
            + hashlib.sha256(sent_marker.encode("ascii")).hexdigest()[:40]
            + "@release-preview.askcrump.invalid>"
        )
        reply_id, reply_thread = await self._send_one_to_self(
            prepared,
            marker=reply_marker,
            recipient=recipient,
            thread_id=thread_id,
            in_reply_to=original_message_id,
        )
        if reply_thread != thread_id or reply_id == sent_id:
            raise ConnectedReleasePreviewProviderError()
        return _canonical_hash(
            {
                "version": "askcrump-release-preview-retained-mail-v1",
                "provider": "google",
                "account_kind": prepared.account.account_kind.value,
                "sent_id_sha256": _sha256(sent_id),
                "reply_id_sha256": _sha256(reply_id),
                "thread_id_sha256": _sha256(thread_id),
            }
        )

    async def _draft_read(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        draft_id: str,
        marker: str,
    ) -> None:
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                GMAIL_HOST,
                f"/gmail/v1/users/me/drafts/{quote(draft_id, safe='')}",
                (("format", "raw"),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        message = _object(body.get("message"))
        raw = _decode_google_raw(message.get("raw"))
        if (
            response.status != 200
            or body.get("id") != draft_id
            or not _google_raw_has_marker(raw, marker)
        ):
            raise ConnectedReleasePreviewProviderError()

    async def _draft_ids_for_marker(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
    ) -> set[str]:
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                GMAIL_HOST,
                "/gmail/v1/users/me/drafts",
                (("q", f'in:drafts "{marker}"'), ("maxResults", "10")),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if response.status != 200 or set(body).difference(
            {"drafts", "nextPageToken", "resultSizeEstimate"}
        ):
            raise ConnectedReleasePreviewProviderError()
        values: set[str] = set()
        for item in _list(body.get("drafts", []), maximum=10):
            draft_id = _text(_object(item).get("id"), maximum=512)
            if draft_id in values:
                raise ConnectedReleasePreviewProviderError()
            await self._draft_read(prepared, draft_id=draft_id, marker=marker)
            values.add(draft_id)
        if body.get("nextPageToken") is not None:
            raise ConnectedReleasePreviewProviderError()
        return values

    async def _cleanup_drafts(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
        known_id: str | None,
    ) -> None:
        if known_id is not None:
            await self._draft_delete(prepared, draft_id=known_id)
            if await self._draft_ids_for_marker(prepared, marker=marker):
                raise ConnectedReleasePreviewProviderError()
            return
        consecutive_empty = 0
        for delay in _AMBIGUOUS_DISCOVERY_DELAYS:
            if delay:
                await self._sleep(delay)
            draft_ids = await self._draft_ids_for_marker(prepared, marker=marker)
            if draft_ids:
                consecutive_empty = 0
                for draft_id in sorted(draft_ids):
                    await self._draft_delete(prepared, draft_id=draft_id)
            else:
                consecutive_empty += 1
        if consecutive_empty < 2 or await self._draft_ids_for_marker(
            prepared,
            marker=marker,
        ):
            raise ConnectedReleasePreviewProviderError()

    async def _draft_delete(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        draft_id: str,
    ) -> None:
        deleted = await self._request(
            prepared,
            GoogleTransportRequest(
                "DELETE",
                GMAIL_HOST,
                f"/gmail/v1/users/me/drafts/{quote(draft_id, safe='')}",
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if deleted.status not in {204, 404}:
            raise ConnectedReleasePreviewProviderError()
        observed = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                GMAIL_HOST,
                f"/gmail/v1/users/me/drafts/{quote(draft_id, safe='')}",
                (("format", "minimal"),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if observed.status != 404:
            raise ConnectedReleasePreviewProviderError()

    async def _draft_write(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
    ) -> str:
        existing = await self._draft_ids_for_marker(prepared, marker=marker)
        if len(existing) == 1:
            return next(iter(existing))
        if existing:
            raise ConnectedReleasePreviewProviderError()
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "POST",
                GMAIL_HOST,
                "/gmail/v1/users/me/drafts",
                json_body={"message": {"raw": _google_raw_mail(marker)}},
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        draft_id = _text(body.get("id"), maximum=512)
        if response.status != 200:
            raise ConnectedReleasePreviewProviderError()
        await self._draft_read(
            prepared,
            draft_id=draft_id,
            marker=marker,
        )
        return draft_id

    async def _calendar_read(
        self, prepared: ConnectedPreparedReleasePreviewCredential, *, now: datetime
    ) -> None:
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                CALENDAR_HOST,
                "/calendar/v3/calendars/primary/events",
                (
                    ("maxResults", "1"),
                    ("singleEvents", "true"),
                    ("timeMin", now.isoformat().replace("+00:00", "Z")),
                    (
                        "timeMax",
                        (now + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                    ),
                ),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if response.status != 200 or set(body).difference(
            {"items", "nextPageToken", "nextSyncToken", "kind", "etag", "summary"}
        ):
            raise ConnectedReleasePreviewProviderError()
        for item in _list(body.get("items", []), maximum=1):
            _text(_object(item).get("id"), maximum=512)

    async def _calendar_free_busy(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        now: datetime,
    ) -> None:
        end = now + timedelta(hours=4)
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "POST",
                CALENDAR_HOST,
                "/calendar/v3/freeBusy",
                json_body={
                    "timeMin": now.isoformat().replace("+00:00", "Z"),
                    "timeMax": end.isoformat().replace("+00:00", "Z"),
                    "timeZone": "UTC",
                    "items": [{"id": "primary"}],
                },
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        calendars = _object(body.get("calendars"))
        if response.status != 200 or set(calendars) != {"primary"}:
            raise ConnectedReleasePreviewProviderError()
        primary = _object(calendars["primary"])
        if primary.get("errors") not in (None, []):
            raise ConnectedReleasePreviewProviderError()
        for item in _list(primary.get("busy", []), maximum=100):
            row = _object(item)
            start = _timestamp(row.get("start"))
            finish = _timestamp(row.get("end"))
            if finish <= start or start < now or finish > end:
                raise ConnectedReleasePreviewProviderError()

    async def _event_get(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        event_id: str,
        marker: str,
    ) -> str:
        existing = await self._draft_ids_for_marker(prepared, marker=marker)
        if len(existing) == 1:
            return next(iter(existing))
        if existing:
            raise ConnectedReleasePreviewProviderError()
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                CALENDAR_HOST,
                f"/calendar/v3/calendars/primary/events/{quote(event_id, safe='')}",
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if (
            response.status != 200
            or body.get("id") != event_id
            or body.get("description") != marker
            or body.get("summary") != "Ask Crump release preview"
            or body.get("status") not in {None, "confirmed"}
            or body.get("attendees", []) != []
            or _object(body.get("organizer")).get("self") is not True
            or _object(_object(body.get("extendedProperties")).get("private")).get(
                "askCrumpReleasePreview"
            )
            != marker.removesuffix("-updated")
        ):
            raise ConnectedReleasePreviewProviderError()
        return _text(body.get("etag"), maximum=512)

    async def _event_write(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        event_id: str,
        marker: str,
        now: datetime,
    ) -> None:
        updated_marker = marker + "-updated"
        try:
            await self._event_get(
                prepared,
                event_id=event_id,
                marker=updated_marker,
            )
            return
        except ConnectedReleasePreviewProviderError:
            pass
        existing_etag: str | None = None
        try:
            existing_etag = await self._event_get(
                prepared,
                event_id=event_id,
                marker=marker,
            )
        except ConnectedReleasePreviewProviderError:
            pass
        start = now + timedelta(hours=2)
        end = start + timedelta(minutes=15)
        if existing_etag is None:
            created = await self._request(
                prepared,
                GoogleTransportRequest(
                    "POST",
                    CALENDAR_HOST,
                    "/calendar/v3/calendars/primary/events",
                    (("sendUpdates", "none"),),
                    json_body={
                        "id": event_id,
                        "summary": "Ask Crump release preview",
                        "description": marker,
                        "attendees": [],
                        "extendedProperties": {
                            "private": {"askCrumpReleasePreview": marker}
                        },
                        "start": {"dateTime": start.isoformat()},
                        "end": {"dateTime": end.isoformat()},
                    },
                ),
                transport=self._provider_transport,
                now=self._now,
            )
            if created.status != 200 or _object(created.body).get("id") != event_id:
                raise ConnectedReleasePreviewProviderError()
            existing_etag = await self._event_get(
                prepared,
                event_id=event_id,
                marker=marker,
            )
        updated = await self._request(
            prepared,
            GoogleTransportRequest(
                "PATCH",
                CALENDAR_HOST,
                f"/calendar/v3/calendars/primary/events/{quote(event_id, safe='')}",
                (("sendUpdates", "none"),),
                (("If-Match", existing_etag),),
                {"description": updated_marker},
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if updated.status != 200 or _object(updated.body).get("id") != event_id:
            raise ConnectedReleasePreviewProviderError()
        await self._event_get(
            prepared,
            event_id=event_id,
            marker=updated_marker,
        )

    async def _event_delete(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        event_id: str,
        marker: str,
    ) -> None:
        etag = await self._event_get(
            prepared,
            event_id=event_id,
            marker=marker,
        )
        response = await self._request(
            prepared,
            GoogleTransportRequest(
                "DELETE",
                CALENDAR_HOST,
                f"/calendar/v3/calendars/primary/events/{quote(event_id, safe='')}",
                (("sendUpdates", "none"),),
                (("If-Match", etag),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if response.status not in {204, 404, 410}:
            raise ConnectedReleasePreviewProviderError()
        observed = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                CALENDAR_HOST,
                f"/calendar/v3/calendars/primary/events/{quote(event_id, safe='')}",
                (("showDeleted", "true"),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if observed.status not in {404, 410}:
            body = _object(observed.body)
            if observed.status != 200 or body.get("status") != "cancelled":
                raise ConnectedReleasePreviewProviderError()

    async def _event_cleanup_recovered(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        event_id: str,
        marker: str,
    ) -> None:
        for candidate in (marker, marker + "-updated"):
            try:
                await self._event_delete(
                    prepared,
                    event_id=event_id,
                    marker=candidate,
                )
                return
            except ConnectedReleasePreviewProviderError:
                continue
        observed = await self._request(
            prepared,
            GoogleTransportRequest(
                "GET",
                CALENDAR_HOST,
                f"/calendar/v3/calendars/primary/events/{quote(event_id, safe='')}",
                (("showDeleted", "true"),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if observed.status in {404, 410}:
            return
        body = _object(observed.body)
        if observed.status != 200 or body.get("status") != "cancelled":
            raise ConnectedReleasePreviewProviderError()

    async def preview(
        self,
        *,
        registration: ProviderOAuthRegistration,
        redirect_uri: str,
        invocation_id: str,
        contract_sha256: str,
        effect_ledger: ConnectedReleasePreviewEffectLedger | None = None,
    ) -> ConnectedProviderReleasePreviewReceipt:
        if (
            config.connected_apps_release_candidate_source_released() is not True
            or type(registration) is not ProviderOAuthRegistration
            or registration.provider is not ConnectorProvider.GOOGLE
            or redirect_uri != _GOOGLE_REDIRECT
            or contract_sha256 != self._contract_sha256
        ):
            raise ConnectedReleasePreviewProviderError()
        account_kind = self._sources[
            ConnectorResource.MAIL
        ]._descriptor.account_kind
        mail_marker = _marker(
            invocation_id,
            provider=ConnectorProvider.GOOGLE,
            account_kind=account_kind,
            resource=ConnectorResource.MAIL,
        )
        calendar_marker = _marker(
            invocation_id,
            provider=ConnectorProvider.GOOGLE,
            account_kind=account_kind,
            resource=ConnectorResource.CALENDAR,
        )
        event_id = "ac" + hashlib.sha256(
            calendar_marker.encode("ascii")
        ).hexdigest()[:30]
        mail: ConnectedPreparedReleasePreviewCredential | None = None
        calendar: ConnectedPreparedReleasePreviewCredential | None = None
        draft_id: str | None = None
        retained_mail_sha256: str | None = None
        draft_attempted = False
        event_attempted = False
        effects_ok = False
        cleanup_ok = True
        provider_revoked = False
        retired = 0
        failure: BaseException | None = None
        mail_state: ConnectedReleasePreviewEffectState | None = None
        calendar_state: ConnectedReleasePreviewEffectState | None = None
        authority_state: ConnectedReleasePreviewAuthorityState | None = None
        try:
            if effect_ledger is not None:
                if (
                    type(effect_ledger) is not ConnectedReleasePreviewEffectLedger
                    or effect_ledger.invocation_id != invocation_id
                ):
                    raise ConnectedReleasePreviewProviderError()
                mail_state = await effect_ledger.state_for(
                    provider=ConnectorProvider.GOOGLE,
                    account_kind=account_kind,
                    resource=ConnectorResource.MAIL,
                )
                calendar_state = await effect_ledger.state_for(
                    provider=ConnectorProvider.GOOGLE,
                    account_kind=account_kind,
                    resource=ConnectorResource.CALENDAR,
                )
                authority_state = await effect_ledger.authority_for(
                    provider=ConnectorProvider.GOOGLE,
                    account_kind=account_kind,
                )
                allowed = {
                    ConnectedReleasePreviewEffectPhase.DISPATCHED,
                    ConnectedReleasePreviewEffectPhase.OBSERVED,
                    ConnectedReleasePreviewEffectPhase.CLEANUP,
                    ConnectedReleasePreviewEffectPhase.CLEAN,
                    ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT,
                    ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN,
                }
                if mail_state.phase not in allowed or calendar_state.phase not in allowed:
                    raise ConnectedReleasePreviewProviderError()
                if (
                    mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                ):
                    retained_mail_sha256 = mail_state.artifact_id_sha256
                effects_ok = bool(
                    mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                    and calendar_state.phase
                    is ConnectedReleasePreviewEffectPhase.CLEAN
                    and retained_mail_sha256 is not None
                )
                if (
                    authority_state.phase
                    is ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED
                ):
                    if not effects_ok:
                        raise ConnectedReleasePreviewProviderError()
                    provider_revoked = True
                    retired = 2
                if not effects_ok and (
                    authority_state.phase
                    is not ConnectedReleasePreviewAuthorityPhase.PENDING
                    or mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN
                    or calendar_state.phase
                    is ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN
                ):
                    raise ConnectedReleasePreviewProviderError()

            needs_provider_effects = not effects_ok and (
                effect_ledger is None
                or mail_state is None
                or calendar_state is None
                or mail_state.phase
                is not ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                or calendar_state.phase
                is not ConnectedReleasePreviewEffectPhase.CLEAN
            )
            if needs_provider_effects:
                mail = await self._sources[ConnectorResource.MAIL].prepare(
                    invocation_id=invocation_id,
                    google_revocation_transport=self._revoke_transport,
                    effect_ledger=effect_ledger,
                )
                calendar = await self._sources[ConnectorResource.CALENDAR].prepare(
                    invocation_id=invocation_id,
                    google_revocation_transport=self._revoke_transport,
                    effect_ledger=effect_ledger,
                )
                if (
                    mail.account.external_account_id_hash
                    != calendar.account.external_account_id_hash
                ):
                    raise ConnectedReleasePreviewProviderError()
                reference = _aware(self._now())
                if (
                    effect_ledger is None
                    or mail_state is None
                    or mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.DISPATCHED
                ):
                    await self._mail_read(mail)
                    draft_attempted = True
                    draft_id = await self._draft_write(mail, marker=mail_marker)
                    retained_mail_sha256 = await self._send_reply_proof(
                        mail,
                        marker=mail_marker,
                    )
                    if effect_ledger is not None and mail_state is not None:
                        mail_state = await effect_ledger.transition(
                            state=mail_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.OBSERVED,
                            artifact_id_sha256=retained_mail_sha256,
                        )
                elif mail_state.phase in {
                    ConnectedReleasePreviewEffectPhase.OBSERVED,
                    ConnectedReleasePreviewEffectPhase.CLEANUP,
                }:
                    retained_mail_sha256 = mail_state.artifact_id_sha256
                    draft_attempted = True

                if (
                    effect_ledger is None
                    or calendar_state is None
                    or calendar_state.phase
                    is ConnectedReleasePreviewEffectPhase.DISPATCHED
                ):
                    await self._calendar_read(calendar, now=reference)
                    await self._calendar_free_busy(calendar, now=reference)
                    event_attempted = True
                    await self._event_write(
                        calendar,
                        event_id=event_id,
                        marker=calendar_marker,
                        now=reference,
                    )
                    if effect_ledger is not None and calendar_state is not None:
                        calendar_state = await effect_ledger.transition(
                            state=calendar_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.OBSERVED,
                            artifact_id_sha256=_sha256(event_id),
                        )
                elif calendar_state.phase in {
                    ConnectedReleasePreviewEffectPhase.OBSERVED,
                    ConnectedReleasePreviewEffectPhase.CLEANUP,
                }:
                    event_attempted = True
                effects_ok = True
        except BaseException as exc:
            failure = exc
        finally:
            if mail is not None and draft_attempted:
                try:
                    if (
                        effect_ledger is not None
                        and mail_state is not None
                        and mail_state.phase
                        is ConnectedReleasePreviewEffectPhase.OBSERVED
                    ):
                        mail_state = await effect_ledger.transition(
                            state=mail_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.CLEANUP,
                        )
                    await self._cleanup_drafts(
                        mail,
                        marker=mail_marker,
                        known_id=draft_id,
                    )
                    if (
                        effect_ledger is not None
                        and mail_state is not None
                        and mail_state.phase
                        is ConnectedReleasePreviewEffectPhase.CLEANUP
                    ):
                        mail_state = await effect_ledger.transition(
                            state=mail_state,
                            next_phase=(
                                ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                            ),
                        )
                except Exception:
                    cleanup_ok = False
            if calendar is not None and event_attempted:
                try:
                    if (
                        effect_ledger is not None
                        and calendar_state is not None
                        and calendar_state.phase
                        is ConnectedReleasePreviewEffectPhase.OBSERVED
                    ):
                        calendar_state = await effect_ledger.transition(
                            state=calendar_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.CLEANUP,
                        )
                    await self._event_cleanup_recovered(
                        calendar,
                        event_id=event_id,
                        marker=calendar_marker,
                    )
                    if (
                        effect_ledger is not None
                        and calendar_state is not None
                        and calendar_state.phase
                        is ConnectedReleasePreviewEffectPhase.CLEANUP
                    ):
                        calendar_state = await effect_ledger.transition(
                            state=calendar_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.CLEAN,
                        )
                except Exception:
                    cleanup_ok = False
            if effect_ledger is not None and mail_state is not None:
                effects_ok = bool(
                    mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                    and calendar_state is not None
                    and calendar_state.phase
                    is ConnectedReleasePreviewEffectPhase.CLEAN
                )
            if (
                cleanup_ok
                and (failure is not None or effects_ok)
                and not provider_revoked
            ):
                if effect_ledger is None:
                    prepared_values = tuple(
                        value for value in (mail, calendar) if value is not None
                    )
                    if prepared_values:
                        try:
                            await _google_preview_revoke(
                                prepared_values[0].refresh_token,
                                transport=self._revoke_transport,
                                recovering_dispatched=(
                                    failure is not None
                                    and len(prepared_values) < 2
                                ),
                            )
                            provider_revoked = True
                            for prepared in prepared_values:
                                await prepared.retire(invocation_id=invocation_id)
                                retired += 1
                        except Exception:
                            cleanup_ok = False
                elif authority_state is not None:
                    try:
                        authority_state = await effect_ledger.authority_for(
                            provider=ConnectorProvider.GOOGLE,
                            account_kind=account_kind,
                        )
                        recovering_dispatched = (
                            authority_state.phase
                            is ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
                        )
                        if (
                            authority_state.phase
                            is ConnectedReleasePreviewAuthorityPhase.PENDING
                        ):
                            authority_state = await effect_ledger.transition_authority(
                                state=authority_state,
                                next_phase=(
                                    ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
                                ),
                            )
                        if (
                            authority_state.phase
                            is ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
                        ):
                            prepared_values = tuple(
                                value
                                for value in (mail, calendar)
                                if value is not None
                            )
                            secret = (
                                prepared_values[0].refresh_token
                                if prepared_values
                                else await self._sources[
                                    ConnectorResource.MAIL
                                ].revocation_secret()
                            )
                            receipt_sha256 = await _google_preview_revoke(
                                secret,
                                transport=self._revoke_transport,
                                recovering_dispatched=recovering_dispatched,
                            )
                            authority_state = await effect_ledger.transition_authority(
                                state=authority_state,
                                next_phase=(
                                    ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED
                                ),
                                provider_receipt_sha256=receipt_sha256,
                            )
                        if (
                            authority_state.phase
                            is ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED
                        ):
                            for source in self._sources.values():
                                await source.retire_descriptor(
                                    invocation_id=invocation_id
                                )
                            authority_state = await effect_ledger.transition_authority(
                                state=authority_state,
                                next_phase=(
                                    ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED
                                ),
                            )
                        provider_revoked = (
                            authority_state.phase
                            is ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED
                        )
                        retired = 2 if provider_revoked else 0
                        if failure is not None and provider_revoked:
                            await _mark_group_effects_unknown(
                                effect_ledger=effect_ledger,
                                provider=ConnectorProvider.GOOGLE,
                                account_kind=account_kind,
                            )
                    except Exception:
                        cleanup_ok = False
        if (
            failure is not None
            or not effects_ok
            or not cleanup_ok
            or not provider_revoked
            or retired != 2
        ):
            raise ConnectedReleasePreviewProviderError()
        return ConnectedProviderReleasePreviewReceipt(
            provider=ConnectorProvider.GOOGLE,
            account_kind=account_kind,
            invocation_id=invocation_id,
            contract_sha256=contract_sha256,
            checked_at=_aware(self._now()),
            dedicated_account_binding_attested=True,
            oauth_callback_attested=True,
            mail_read_attested=True,
            mail_preview_write_attested=True,
            mail_send_attested=True,
            mail_reply_attested=True,
            mail_retained_test_artifact_sha256=retained_mail_sha256,
            calendar_read_attested=True,
            calendar_free_busy_attested=True,
            calendar_free_busy_exempt=False,
            calendar_preview_write_attested=True,
            calendar_cleanup_artifact_sha256=_sha256(event_id),
            cleanup_attested=True,
            provider_grant_revocation_attested=True,
            local_connection_retirement_attested=True,
            local_credential_erasure_attested=True,
            revocation_mode="provider_grant_and_local_retirement",
        )

    def __repr__(self) -> str:
        return "ConnectedGoogleReleasePreviewProbe(content='none')"


class ConnectedMicrosoftReleasePreviewProbe:
    """Concrete Microsoft OAuth/Graph preview with observed cleanup/revocation."""

    __slots__ = (
        "_contract_sha256",
        "_now",
        "_provider_transport",
        "_sleep",
        "_sources",
    )

    def __init__(
        self,
        *,
        sources: Mapping[ConnectorResource, ConnectedReleasePreviewCredentialSource],
        contract_sha256: str,
        provider_transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        sources_copy = _provider_sources(
            sources,
            provider=ConnectorProvider.MICROSOFT,
        )
        if (
            not isinstance(contract_sha256, str)
            or len(contract_sha256) != 64
            or any(character not in "0123456789abcdef" for character in contract_sha256)
            or not callable(now)
            or not callable(sleep)
        ):
            raise ConnectedReleasePreviewProviderError()
        self._sources = sources_copy
        self._contract_sha256 = contract_sha256
        self._provider_transport = provider_transport
        self._sleep = sleep
        self._now = now

    def production_eligible(
        self,
        *,
        database: ConnectedReleasePreviewRPC,
        registration: ProviderOAuthRegistration,
    ) -> bool:
        return (
            type(self) is ConnectedMicrosoftReleasePreviewProbe
            and self._provider_transport is None
            and self._sleep is asyncio.sleep
            and type(registration) is ProviderOAuthRegistration
            and registration.provider is ConnectorProvider.MICROSOFT
            and all(
                source.production_eligible(
                    database=database,
                    registration=registration,
                )
                for source in self._sources.values()
            )
        )

    async def abort_unstarted_or_revoked(
        self,
        *,
        invocation_id: str,
        effect_ledger: ConnectedReleasePreviewEffectLedger,
    ) -> None:
        """Retire an unstarted group; never erase unsettled cleanup authority."""

        if (
            type(effect_ledger) is not ConnectedReleasePreviewEffectLedger
            or effect_ledger.invocation_id != invocation_id
        ):
            raise ConnectedReleasePreviewProviderError()
        account_kind = self._sources[
            ConnectorResource.MAIL
        ]._descriptor.account_kind
        states = tuple(
            [
                await effect_ledger.state_for(
                    provider=ConnectorProvider.MICROSOFT,
                    account_kind=account_kind,
                    resource=resource,
                )
                for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR)
            ]
        )
        authority = await effect_ledger.authority_for(
            provider=ConnectorProvider.MICROSOFT,
            account_kind=account_kind,
        )
        if authority.phase is ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED:
            return
        if authority.phase is not ConnectedReleasePreviewAuthorityPhase.PENDING or any(
            state.phase is not ConnectedReleasePreviewEffectPhase.PENDING
            for state in states
        ):
            raise ConnectedReleasePreviewProviderError()
        for source in self._sources.values():
            await source.retire_descriptor(invocation_id=invocation_id)
        authority = await effect_ledger.transition_authority(
            state=authority,
            next_phase=ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED,
        )
        if authority.phase is not ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED:
            raise ConnectedReleasePreviewProviderError()

    @staticmethod
    async def _request(
        prepared: ConnectedPreparedReleasePreviewCredential,
        request: MicrosoftTransportRequest,
        *,
        transport: httpx.AsyncBaseTransport | None,
        now: Callable[[], datetime],
    ):
        boundary = MicrosoftHTTPSCredentialTransport(
            prepared.source,
            transport=transport,
            now=now,
        )
        return await boundary.request(
            account=prepared.account,
            credential=prepared.credential,
            request=request,
        )

    async def _mail_read(
        self, prepared: ConnectedPreparedReleasePreviewCredential
    ) -> None:
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/mailFolders/inbox/messages",
                (("$select", "id"), ("$top", "1")),
                (("Prefer", 'IdType="ImmutableId"'),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if response.status != 200 or set(body).difference({"value", "@odata.nextLink"}):
            raise ConnectedReleasePreviewProviderError()
        for item in _list(body.get("value", []), maximum=1):
            _text(_object(item).get("id"), maximum=512)

    async def _mail_self_address(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
    ) -> str:
        profile = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me",
                (("$select", "mail,userPrincipalName"),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(profile.body)
        address = _text(
            body.get("mail") or body.get("userPrincipalName"),
            maximum=320,
        )
        if (
            profile.status != 200
            or address.count("@") != 1
            or address.startswith("@")
            or address.endswith("@")
        ):
            raise ConnectedReleasePreviewProviderError()
        return address

    async def _sent_message_read(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        message_id: str,
        marker: str,
    ) -> str:
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/messages/{quote(message_id, safe='')}",
                (("$select", "id,conversationId,subject,body,isDraft"),),
                (("Prefer", _MICROSOFT_MAIL_PREFER),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if (
            response.status != 200
            or body.get("id") != message_id
            or body.get("subject") != marker
            or body.get("isDraft") is not False
            or _object(body.get("body")).get("content") != marker
        ):
            raise ConnectedReleasePreviewProviderError()
        return _text(body.get("conversationId"), maximum=512)

    async def _sent_ids_for_marker(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
    ) -> dict[str, str]:
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/mailFolders/sentitems/messages",
                (
                    ("$select", "id,conversationId,subject,body,isDraft"),
                    ("$filter", f"subject eq '{marker}' and isDraft eq false"),
                    ("$top", "10"),
                ),
                (("Prefer", _MICROSOFT_MAIL_PREFER),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if response.status != 200 or body.get("@odata.nextLink") is not None:
            raise ConnectedReleasePreviewProviderError()
        found: dict[str, str] = {}
        for item_value in _list(body.get("value", []), maximum=10):
            item = _object(item_value)
            message_id = _text(item.get("id"), maximum=512)
            if (
                message_id in found
                or item.get("subject") != marker
                or item.get("isDraft") is not False
                or _object(item.get("body")).get("content") != marker
            ):
                raise ConnectedReleasePreviewProviderError()
            found[message_id] = _text(item.get("conversationId"), maximum=512)
        return found

    async def _send_draft_to_self(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
        recipient: str,
        reply_to_id: str | None = None,
        expected_conversation_id: str | None = None,
    ) -> tuple[str, str]:
        found = await self._sent_ids_for_marker(prepared, marker=marker)
        if len(found) == 1:
            return next(iter(found.items()))
        if found:
            raise ConnectedReleasePreviewProviderError()
        try:
            if reply_to_id is None:
                created = await self._request(
                    prepared,
                    MicrosoftTransportRequest(
                        "POST",
                        GRAPH_HOST,
                        f"{GRAPH_ROOT}/me/messages",
                        headers=(("Prefer", _MICROSOFT_MAIL_PREFER),),
                        json_body={
                            "subject": marker,
                            "body": {"contentType": "Text", "content": marker},
                            "toRecipients": [
                                {"emailAddress": {"address": recipient}}
                            ],
                        },
                    ),
                    transport=self._provider_transport,
                    now=self._now,
                )
            else:
                created = await self._request(
                    prepared,
                    MicrosoftTransportRequest(
                        "POST",
                        GRAPH_HOST,
                        f"{GRAPH_ROOT}/me/messages/{quote(reply_to_id, safe='')}/createReply",
                        headers=(("Prefer", _MICROSOFT_MAIL_PREFER),),
                    ),
                    transport=self._provider_transport,
                    now=self._now,
                )
            row = _object(created.body)
            draft_id = _text(row.get("id"), maximum=512)
            conversation_id = _text(row.get("conversationId"), maximum=512)
            if created.status != 201 or row.get("isDraft") is not True:
                raise ConnectedReleasePreviewProviderError()
            if (
                expected_conversation_id is not None
                and conversation_id != expected_conversation_id
            ):
                raise ConnectedReleasePreviewProviderError()
            if reply_to_id is not None:
                patched = await self._request(
                    prepared,
                    MicrosoftTransportRequest(
                        "PATCH",
                        GRAPH_HOST,
                        f"{GRAPH_ROOT}/me/messages/{quote(draft_id, safe='')}",
                        headers=(("Prefer", _MICROSOFT_MAIL_PREFER),),
                        json_body={
                            "subject": marker,
                            "body": {"contentType": "Text", "content": marker},
                        },
                    ),
                    transport=self._provider_transport,
                    now=self._now,
                )
                if patched.status not in {200, 204}:
                    raise ConnectedReleasePreviewProviderError()
            sent = await self._request(
                prepared,
                MicrosoftTransportRequest(
                    "POST",
                    GRAPH_HOST,
                    f"{GRAPH_ROOT}/me/messages/{quote(draft_id, safe='')}/send",
                    headers=(("Prefer", 'IdType="ImmutableId"'),),
                ),
                transport=self._provider_transport,
                now=self._now,
            )
            if sent.status not in {200, 202}:
                raise ConnectedReleasePreviewProviderError()
            for delay in _AMBIGUOUS_DISCOVERY_DELAYS:
                if delay:
                    await self._sleep(delay)
                try:
                    observed = await self._sent_message_read(
                        prepared,
                        message_id=draft_id,
                        marker=marker,
                    )
                    if observed != conversation_id:
                        raise ConnectedReleasePreviewProviderError()
                    return draft_id, conversation_id
                except ConnectedReleasePreviewProviderError:
                    continue
        except Exception:
            pass
        for delay in _AMBIGUOUS_DISCOVERY_DELAYS:
            if delay:
                await self._sleep(delay)
            found = await self._sent_ids_for_marker(prepared, marker=marker)
            if len(found) == 1:
                return next(iter(found.items()))
            if len(found) > 1:
                break
        raise ConnectedReleasePreviewProviderError()

    async def _send_reply_proof(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
    ) -> str:
        recipient = await self._mail_self_address(prepared)
        sent_marker = marker + "-send"
        reply_marker = marker + "-reply"
        sent_id, conversation_id = await self._send_draft_to_self(
            prepared,
            marker=sent_marker,
            recipient=recipient,
        )
        reply_id, reply_conversation = await self._send_draft_to_self(
            prepared,
            marker=reply_marker,
            recipient=recipient,
            reply_to_id=sent_id,
            expected_conversation_id=conversation_id,
        )
        if reply_id == sent_id or reply_conversation != conversation_id:
            raise ConnectedReleasePreviewProviderError()
        return _canonical_hash(
            {
                "version": "askcrump-release-preview-retained-mail-v1",
                "provider": "microsoft",
                "account_kind": prepared.account.account_kind.value,
                "sent_id_sha256": _sha256(sent_id),
                "reply_id_sha256": _sha256(reply_id),
                "conversation_id_sha256": _sha256(conversation_id),
            }
        )

    async def _calendar_free_busy(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        now: datetime,
    ) -> None:
        if prepared.account.account_kind is ConnectorAccountKind.PERSONAL:
            return
        mailbox = await self._mail_self_address(prepared)
        end = now + timedelta(hours=4)
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "POST",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/calendar/getSchedule",
                json_body={
                    "schedules": [mailbox],
                    "startTime": {
                        "dateTime": now.isoformat(),
                        "timeZone": "UTC",
                    },
                    "endTime": {
                        "dateTime": end.isoformat(),
                        "timeZone": "UTC",
                    },
                    "availabilityViewInterval": 30,
                },
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        rows = _list(_object(response.body).get("value"), maximum=1)
        if response.status != 200 or len(rows) != 1:
            raise ConnectedReleasePreviewProviderError()
        row = _object(rows[0])
        availability = row.get("availabilityView")
        if (
            str(row.get("scheduleId", "")).casefold() != mailbox.casefold()
            or row.get("error") not in (None, {})
            or not isinstance(availability, str)
            or len(availability) > 1024
        ):
            raise ConnectedReleasePreviewProviderError()
        _list(row.get("scheduleItems", []), maximum=100)

    async def _draft_read(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        draft_id: str,
        marker: str,
    ) -> None:
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/messages/{quote(draft_id, safe='')}",
                (("$select", "id,subject,body,isDraft"),),
                (("Prefer", _MICROSOFT_MAIL_PREFER),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        content = _object(body.get("body")).get("content")
        if (
            response.status != 200
            or body.get("id") != draft_id
            or body.get("subject") != marker
            or body.get("isDraft") is not True
            or content != marker
        ):
            raise ConnectedReleasePreviewProviderError()

    async def _draft_ids_for_marker(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
    ) -> set[str]:
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/mailFolders/drafts/messages",
                (
                    ("$select", "id,subject,body,isDraft"),
                    ("$filter", f"subject eq '{marker}' and isDraft eq true"),
                    ("$top", "10"),
                ),
                (("Prefer", _MICROSOFT_MAIL_PREFER),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if response.status != 200 or set(body).difference({"value", "@odata.nextLink"}):
            raise ConnectedReleasePreviewProviderError()
        values: set[str] = set()
        for item_value in _list(body.get("value", []), maximum=10):
            item = _object(item_value)
            draft_id = _text(item.get("id"), maximum=512)
            if (
                draft_id in values
                or item.get("subject") != marker
                or item.get("isDraft") is not True
                or _object(item.get("body")).get("content") != marker
            ):
                raise ConnectedReleasePreviewProviderError()
            values.add(draft_id)
        if body.get("@odata.nextLink") is not None:
            raise ConnectedReleasePreviewProviderError()
        return values

    async def _cleanup_drafts(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
        known_id: str | None,
    ) -> None:
        if known_id is not None:
            await self._draft_delete(prepared, draft_id=known_id)
            if await self._draft_ids_for_marker(prepared, marker=marker):
                raise ConnectedReleasePreviewProviderError()
            return
        consecutive_empty = 0
        for delay in _AMBIGUOUS_DISCOVERY_DELAYS:
            if delay:
                await self._sleep(delay)
            draft_ids = await self._draft_ids_for_marker(prepared, marker=marker)
            if draft_ids:
                consecutive_empty = 0
                for draft_id in sorted(draft_ids):
                    await self._draft_delete(prepared, draft_id=draft_id)
            else:
                consecutive_empty += 1
        if consecutive_empty < 2 or await self._draft_ids_for_marker(
            prepared,
            marker=marker,
        ):
            raise ConnectedReleasePreviewProviderError()

    async def _draft_write(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
    ) -> str:
        existing = await self._draft_ids_for_marker(
            prepared,
            marker=marker,
        )
        if len(existing) > 1:
            raise ConnectedReleasePreviewProviderError()
        if existing:
            draft_id = next(iter(existing))
            await self._draft_read(
                prepared,
                draft_id=draft_id,
                marker=marker,
            )
            return draft_id
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "POST",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/messages",
                headers=(("Prefer", 'IdType="ImmutableId"'),),
                json_body={
                    "subject": marker,
                    "body": {"contentType": "Text", "content": marker},
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": "askcrump-preview@example.invalid"
                            }
                        }
                    ],
                },
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        draft_id = _text(body.get("id"), maximum=512)
        if response.status != 201 or body.get("isDraft") is not True:
            raise ConnectedReleasePreviewProviderError()
        await self._draft_read(
            prepared,
            draft_id=draft_id,
            marker=marker,
        )
        return draft_id

    async def _draft_delete(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        draft_id: str,
    ) -> None:
        deleted = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "DELETE",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/messages/{quote(draft_id, safe='')}",
                headers=(("Prefer", 'IdType="ImmutableId"'),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if deleted.status not in {204, 404}:
            raise ConnectedReleasePreviewProviderError()
        observed = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/messages/{quote(draft_id, safe='')}",
                (("$select", "id"),),
                (("Prefer", 'IdType="ImmutableId"'),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if observed.status != 404:
            raise ConnectedReleasePreviewProviderError()

    async def _calendar_read(
        self, prepared: ConnectedPreparedReleasePreviewCredential, *, now: datetime
    ) -> None:
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/calendar/events",
                (
                    ("$select", "id"),
                    ("$top", "1"),
                    (
                        "$filter",
                        "start/dateTime ge '"
                        + now.isoformat()
                        + "' and start/dateTime lt '"
                        + (now + timedelta(days=1)).isoformat()
                        + "'",
                    ),
                ),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if response.status != 200 or set(body).difference({"value", "@odata.nextLink"}):
            raise ConnectedReleasePreviewProviderError()
        for item in _list(body.get("value", []), maximum=1):
            _text(_object(item).get("id"), maximum=512)

    async def _event_get(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        event_id: str,
        marker: str,
        transaction_id: str,
    ) -> str:
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/events/{quote(event_id, safe='')}",
                (
                    (
                        "$select",
                        "id,changeKey,subject,body,isCancelled,attendees,"
                        "isOrganizer,transactionId",
                    ),
                ),
                (("Prefer", 'outlook.body-content-type="text"'),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if (
            response.status != 200
            or body.get("id") != event_id
            or body.get("subject") != "Ask Crump release preview"
            or _object(body.get("body")).get("content") != marker
            or body.get("isCancelled") is not False
            or body.get("attendees") != []
            or body.get("isOrganizer") is not True
            or body.get("transactionId") != transaction_id
        ):
            raise ConnectedReleasePreviewProviderError()
        return _text(body.get("changeKey"), maximum=512)

    async def _event_write(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
        transaction_id: str,
        now: datetime,
    ) -> str:
        existing = await self._event_ids_for_marker(
            prepared,
            marker=marker,
            transaction_id=transaction_id,
        )
        if len(existing) > 1:
            raise ConnectedReleasePreviewProviderError()
        if existing:
            event_id = next(iter(existing))
            try:
                await self._event_get(
                    prepared,
                    event_id=event_id,
                    marker=marker + "-updated",
                    transaction_id=transaction_id,
                )
                return event_id
            except ConnectedReleasePreviewProviderError:
                change_key = await self._event_get(
                    prepared,
                    event_id=event_id,
                    marker=marker,
                    transaction_id=transaction_id,
                )
                updated = await self._request(
                    prepared,
                    MicrosoftTransportRequest(
                        "PATCH",
                        GRAPH_HOST,
                        f"{GRAPH_ROOT}/me/events/{quote(event_id, safe='')}",
                        headers=(("If-Match", change_key),),
                        json_body={
                            "body": {
                                "contentType": "Text",
                                "content": marker + "-updated",
                            }
                        },
                    ),
                    transport=self._provider_transport,
                    now=self._now,
                )
                if updated.status not in {200, 204}:
                    raise ConnectedReleasePreviewProviderError()
                await self._event_get(
                    prepared,
                    event_id=event_id,
                    marker=marker + "-updated",
                    transaction_id=transaction_id,
                )
                return event_id
        start = now + timedelta(hours=2)
        end = start + timedelta(minutes=15)
        created = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "POST",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/events",
                json_body={
                    "subject": "Ask Crump release preview",
                    "body": {"contentType": "Text", "content": marker},
                    "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
                    "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
                    "attendees": [],
                    "transactionId": transaction_id,
                },
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(created.body)
        event_id = _text(body.get("id"), maximum=512)
        if created.status != 201:
            raise ConnectedReleasePreviewProviderError()
        change_key = await self._event_get(
            prepared,
            event_id=event_id,
            marker=marker,
            transaction_id=transaction_id,
        )
        updated_marker = marker + "-updated"
        updated = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "PATCH",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/events/{quote(event_id, safe='')}",
                headers=(("If-Match", change_key),),
                json_body={
                    "body": {"contentType": "Text", "content": updated_marker}
                },
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if updated.status not in {200, 204}:
            raise ConnectedReleasePreviewProviderError()
        await self._event_get(
            prepared,
            event_id=event_id,
            marker=updated_marker,
            transaction_id=transaction_id,
        )
        return event_id

    async def _event_delete(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        event_id: str,
        marker: str,
        transaction_id: str,
    ) -> None:
        change_key = await self._event_get(
            prepared,
            event_id=event_id,
            marker=marker,
            transaction_id=transaction_id,
        )
        deleted = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "DELETE",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/events/{quote(event_id, safe='')}",
                headers=(("If-Match", change_key),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if deleted.status not in {204, 404, 410}:
            raise ConnectedReleasePreviewProviderError()
        observed = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/events/{quote(event_id, safe='')}",
                (("$select", "id,isCancelled"),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        if observed.status not in {404, 410}:
            body = _object(observed.body)
            if observed.status != 200 or body.get("isCancelled") is not True:
                raise ConnectedReleasePreviewProviderError()

    async def _event_ids_for_marker(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
        transaction_id: str,
    ) -> set[str]:
        response = await self._request(
            prepared,
            MicrosoftTransportRequest(
                "GET",
                GRAPH_HOST,
                f"{GRAPH_ROOT}/me/calendar/events",
                (
                    ("$select", "id,subject,body,isCancelled,transactionId"),
                    ("$filter", "subject eq 'Ask Crump release preview'"),
                    ("$top", "10"),
                ),
                (("Prefer", 'outlook.body-content-type="text"'),),
            ),
            transport=self._provider_transport,
            now=self._now,
        )
        body = _object(response.body)
        if response.status != 200 or set(body).difference({"value", "@odata.nextLink"}):
            raise ConnectedReleasePreviewProviderError()
        values: set[str] = set()
        for item_value in _list(body.get("value", []), maximum=10):
            item = _object(item_value)
            if (
                item.get("transactionId") != transaction_id
                or _object(item.get("body")).get("content")
                not in {marker, marker + "-updated"}
            ):
                continue
            event_id = _text(item.get("id"), maximum=512)
            if event_id in values:
                raise ConnectedReleasePreviewProviderError()
            values.add(event_id)
        if body.get("@odata.nextLink") is not None:
            raise ConnectedReleasePreviewProviderError()
        return values

    async def _cleanup_events(
        self,
        prepared: ConnectedPreparedReleasePreviewCredential,
        *,
        marker: str,
        transaction_id: str,
        known_id: str | None,
    ) -> None:
        if known_id is not None:
            await self._event_delete(
                prepared,
                event_id=known_id,
                marker=marker + "-updated",
                transaction_id=transaction_id,
            )
            if await self._event_ids_for_marker(
                prepared,
                marker=marker,
                transaction_id=transaction_id,
            ):
                raise ConnectedReleasePreviewProviderError()
            return
        consecutive_empty = 0
        for delay in _AMBIGUOUS_DISCOVERY_DELAYS:
            if delay:
                await self._sleep(delay)
            event_ids = await self._event_ids_for_marker(
                prepared,
                marker=marker,
                transaction_id=transaction_id,
            )
            if event_ids:
                consecutive_empty = 0
                for event_id in sorted(event_ids):
                    # Ambiguous creation may have failed before the update.
                    # Read the original marker first; if the update committed,
                    # retry the exact updated marker without deleting an
                    # unverified/concurrently edited meeting.
                    try:
                        await self._event_delete(
                            prepared,
                            event_id=event_id,
                            marker=marker,
                            transaction_id=transaction_id,
                        )
                    except ConnectedReleasePreviewProviderError:
                        await self._event_delete(
                            prepared,
                            event_id=event_id,
                            marker=marker + "-updated",
                            transaction_id=transaction_id,
                        )
            else:
                consecutive_empty += 1
        if consecutive_empty < 2 or await self._event_ids_for_marker(
            prepared,
            marker=marker,
            transaction_id=transaction_id,
        ):
            raise ConnectedReleasePreviewProviderError()

    async def preview(
        self,
        *,
        registration: ProviderOAuthRegistration,
        redirect_uri: str,
        invocation_id: str,
        contract_sha256: str,
        effect_ledger: ConnectedReleasePreviewEffectLedger | None = None,
    ) -> ConnectedProviderReleasePreviewReceipt:
        if (
            config.connected_apps_release_candidate_source_released() is not True
            or type(registration) is not ProviderOAuthRegistration
            or registration.provider is not ConnectorProvider.MICROSOFT
            or redirect_uri != _MICROSOFT_REDIRECT
            or contract_sha256 != self._contract_sha256
        ):
            raise ConnectedReleasePreviewProviderError()
        account_kind = self._sources[
            ConnectorResource.MAIL
        ]._descriptor.account_kind
        mail_marker = _marker(
            invocation_id,
            provider=ConnectorProvider.MICROSOFT,
            account_kind=account_kind,
            resource=ConnectorResource.MAIL,
        )
        calendar_marker = _marker(
            invocation_id,
            provider=ConnectorProvider.MICROSOFT,
            account_kind=account_kind,
            resource=ConnectorResource.CALENDAR,
        )
        transaction_id = str(
            uuid5(UUID(invocation_id), calendar_marker)
        )
        mail: ConnectedPreparedReleasePreviewCredential | None = None
        calendar: ConnectedPreparedReleasePreviewCredential | None = None
        draft_id: str | None = None
        event_id: str | None = None
        retained_mail_sha256: str | None = None
        draft_attempted = False
        event_attempted = False
        effects_ok = False
        cleanup_ok = True
        retired = 0
        failure: BaseException | None = None
        mail_state: ConnectedReleasePreviewEffectState | None = None
        calendar_state: ConnectedReleasePreviewEffectState | None = None
        authority_state: ConnectedReleasePreviewAuthorityState | None = None
        try:
            if effect_ledger is not None:
                if (
                    type(effect_ledger) is not ConnectedReleasePreviewEffectLedger
                    or effect_ledger.invocation_id != invocation_id
                ):
                    raise ConnectedReleasePreviewProviderError()
                mail_state = await effect_ledger.state_for(
                    provider=ConnectorProvider.MICROSOFT,
                    account_kind=account_kind,
                    resource=ConnectorResource.MAIL,
                )
                calendar_state = await effect_ledger.state_for(
                    provider=ConnectorProvider.MICROSOFT,
                    account_kind=account_kind,
                    resource=ConnectorResource.CALENDAR,
                )
                authority_state = await effect_ledger.authority_for(
                    provider=ConnectorProvider.MICROSOFT,
                    account_kind=account_kind,
                )
                allowed = {
                    ConnectedReleasePreviewEffectPhase.DISPATCHED,
                    ConnectedReleasePreviewEffectPhase.OBSERVED,
                    ConnectedReleasePreviewEffectPhase.CLEANUP,
                    ConnectedReleasePreviewEffectPhase.CLEAN,
                    ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT,
                    ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN,
                }
                if mail_state.phase not in allowed or calendar_state.phase not in allowed:
                    raise ConnectedReleasePreviewProviderError()
                if (
                    mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                ):
                    retained_mail_sha256 = mail_state.artifact_id_sha256
                effects_ok = bool(
                    mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                    and calendar_state.phase
                    is ConnectedReleasePreviewEffectPhase.CLEAN
                    and retained_mail_sha256 is not None
                )
                if (
                    authority_state.phase
                    is ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED
                ):
                    if not effects_ok:
                        raise ConnectedReleasePreviewProviderError()
                    retired = 2
                if not effects_ok and (
                    authority_state.phase
                    is not ConnectedReleasePreviewAuthorityPhase.PENDING
                    or mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN
                    or calendar_state.phase
                    is ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN
                ):
                    raise ConnectedReleasePreviewProviderError()

            needs_provider_effects = not effects_ok and (
                effect_ledger is None
                or mail_state is None
                or calendar_state is None
                or mail_state.phase
                is not ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                or calendar_state.phase
                is not ConnectedReleasePreviewEffectPhase.CLEAN
            )
            if needs_provider_effects:
                mail = await self._sources[ConnectorResource.MAIL].prepare(
                    invocation_id=invocation_id,
                    effect_ledger=effect_ledger,
                )
                calendar = await self._sources[ConnectorResource.CALENDAR].prepare(
                    invocation_id=invocation_id,
                    effect_ledger=effect_ledger,
                )
                if (
                    mail.account.external_account_id_hash
                    != calendar.account.external_account_id_hash
                ):
                    raise ConnectedReleasePreviewProviderError()
                reference = _aware(self._now())
                if (
                    effect_ledger is None
                    or mail_state is None
                    or mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.DISPATCHED
                ):
                    await self._mail_read(mail)
                    draft_attempted = True
                    draft_id = await self._draft_write(mail, marker=mail_marker)
                    retained_mail_sha256 = await self._send_reply_proof(
                        mail,
                        marker=mail_marker,
                    )
                    if effect_ledger is not None and mail_state is not None:
                        mail_state = await effect_ledger.transition(
                            state=mail_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.OBSERVED,
                            artifact_id_sha256=retained_mail_sha256,
                        )
                elif mail_state.phase in {
                    ConnectedReleasePreviewEffectPhase.OBSERVED,
                    ConnectedReleasePreviewEffectPhase.CLEANUP,
                }:
                    retained_mail_sha256 = mail_state.artifact_id_sha256
                    draft_attempted = True

                if (
                    effect_ledger is None
                    or calendar_state is None
                    or calendar_state.phase
                    is ConnectedReleasePreviewEffectPhase.DISPATCHED
                ):
                    await self._calendar_read(calendar, now=reference)
                    await self._calendar_free_busy(calendar, now=reference)
                    event_attempted = True
                    event_id = await self._event_write(
                        calendar,
                        marker=calendar_marker,
                        transaction_id=transaction_id,
                        now=reference,
                    )
                    if effect_ledger is not None and calendar_state is not None:
                        calendar_state = await effect_ledger.transition(
                            state=calendar_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.OBSERVED,
                            artifact_id_sha256=_sha256(event_id),
                        )
                elif calendar_state.phase in {
                    ConnectedReleasePreviewEffectPhase.OBSERVED,
                    ConnectedReleasePreviewEffectPhase.CLEANUP,
                }:
                    event_attempted = True
                    event_id = None
                effects_ok = True
        except BaseException as exc:
            failure = exc
        finally:
            if mail is not None and draft_attempted:
                try:
                    if (
                        effect_ledger is not None
                        and mail_state is not None
                        and mail_state.phase
                        is ConnectedReleasePreviewEffectPhase.OBSERVED
                    ):
                        mail_state = await effect_ledger.transition(
                            state=mail_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.CLEANUP,
                        )
                    await self._cleanup_drafts(
                        mail,
                        marker=mail_marker,
                        known_id=draft_id,
                    )
                    if (
                        effect_ledger is not None
                        and mail_state is not None
                        and mail_state.phase
                        is ConnectedReleasePreviewEffectPhase.CLEANUP
                    ):
                        mail_state = await effect_ledger.transition(
                            state=mail_state,
                            next_phase=(
                                ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                            ),
                        )
                except Exception:
                    cleanup_ok = False
            if calendar is not None and event_attempted:
                try:
                    if (
                        effect_ledger is not None
                        and calendar_state is not None
                        and calendar_state.phase
                        is ConnectedReleasePreviewEffectPhase.OBSERVED
                    ):
                        calendar_state = await effect_ledger.transition(
                            state=calendar_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.CLEANUP,
                        )
                    await self._cleanup_events(
                        calendar,
                        marker=calendar_marker,
                        transaction_id=transaction_id,
                        known_id=event_id,
                    )
                    if (
                        effect_ledger is not None
                        and calendar_state is not None
                        and calendar_state.phase
                        is ConnectedReleasePreviewEffectPhase.CLEANUP
                    ):
                        calendar_state = await effect_ledger.transition(
                            state=calendar_state,
                            next_phase=ConnectedReleasePreviewEffectPhase.CLEAN,
                        )
                except Exception:
                    cleanup_ok = False
            if effect_ledger is not None and mail_state is not None:
                effects_ok = bool(
                    mail_state.phase
                    is ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                    and calendar_state is not None
                    and calendar_state.phase
                    is ConnectedReleasePreviewEffectPhase.CLEAN
                )
            # Microsoft has no least-scope immediate provider-revocation API.
            # The durable authority row becomes terminal only after both
            # exact local connections and credential envelopes are retired.
            if (
                cleanup_ok
                and (failure is not None or effects_ok)
                and retired != 2
            ):
                if effect_ledger is None:
                    for prepared in tuple(
                        value for value in (mail, calendar) if value is not None
                    ):
                        try:
                            await prepared.retire(invocation_id=invocation_id)
                            retired += 1
                        except Exception:
                            cleanup_ok = False
                elif authority_state is not None:
                    try:
                        authority_state = await effect_ledger.authority_for(
                            provider=ConnectorProvider.MICROSOFT,
                            account_kind=account_kind,
                        )
                        if (
                            authority_state.phase
                            is ConnectedReleasePreviewAuthorityPhase.PENDING
                        ):
                            for source in self._sources.values():
                                await source.retire_descriptor(
                                    invocation_id=invocation_id
                                )
                            authority_state = await effect_ledger.transition_authority(
                                state=authority_state,
                                next_phase=(
                                    ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED
                                ),
                            )
                        retired = (
                            2
                            if authority_state.phase
                            is ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED
                            else 0
                        )
                        if failure is not None and retired == 2:
                            await _mark_group_effects_unknown(
                                effect_ledger=effect_ledger,
                                provider=ConnectorProvider.MICROSOFT,
                                account_kind=account_kind,
                            )
                    except Exception:
                        cleanup_ok = False
        if failure is not None or not effects_ok or not cleanup_ok or retired != 2:
            raise ConnectedReleasePreviewProviderError()
        return ConnectedProviderReleasePreviewReceipt(
            provider=ConnectorProvider.MICROSOFT,
            account_kind=account_kind,
            invocation_id=invocation_id,
            contract_sha256=contract_sha256,
            checked_at=_aware(self._now()),
            dedicated_account_binding_attested=True,
            oauth_callback_attested=True,
            mail_read_attested=True,
            mail_preview_write_attested=True,
            mail_send_attested=True,
            mail_reply_attested=True,
            mail_retained_test_artifact_sha256=retained_mail_sha256,
            calendar_read_attested=True,
            calendar_free_busy_attested=(
                account_kind is ConnectorAccountKind.WORK_SCHOOL
            ),
            calendar_free_busy_exempt=(
                account_kind is ConnectorAccountKind.PERSONAL
            ),
            calendar_preview_write_attested=True,
            calendar_cleanup_artifact_sha256=(
                calendar_state.artifact_id_sha256
                if calendar_state is not None
                else _sha256(event_id)
            ),
            cleanup_attested=True,
            provider_grant_revocation_attested=False,
            local_connection_retirement_attested=True,
            local_credential_erasure_attested=True,
            revocation_mode="local_credential_and_connection_retirement",
        )

    def __repr__(self) -> str:
        return "ConnectedMicrosoftReleasePreviewProbe(content='none')"


def build_connected_release_preview_provider_probes(
    *,
    database: ConnectedReleasePreviewRPC,
    credential_key: ConnectedCredentialMasterKey,
    registrations: Mapping[ConnectorProvider, ProviderOAuthRegistration],
    descriptors: Mapping[
        ConnectorProvider,
        Mapping[
            ConnectorAccountKind,
            Mapping[
                ConnectorResource,
                ConnectedReleasePreviewConnectionConfiguration,
            ],
        ],
    ],
    contract_sha256: str,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Mapping[
    ConnectorProvider,
    Mapping[
        ConnectorAccountKind,
        ConnectedGoogleReleasePreviewProbe | ConnectedMicrosoftReleasePreviewProbe,
    ],
]:
    if (
        set(registrations) != set(ConnectorProvider)
        or set(descriptors) != set(ConnectorProvider)
    ):
        raise ConnectedReleasePreviewProviderError()
    sources: dict[
        ConnectorProvider,
        dict[
            ConnectorAccountKind,
            dict[ConnectorResource, ConnectedReleasePreviewCredentialSource],
        ],
    ] = {}
    for provider in ConnectorProvider:
        if (
            provider is ConnectorProvider.GOOGLE
            and len(descriptors[provider]) != 1
        ) or (
            provider is ConnectorProvider.MICROSOFT
            and set(descriptors[provider]) != set(ConnectorAccountKind)
        ):
            raise ConnectedReleasePreviewProviderError()
        sources[provider] = {}
        for account_kind, account_descriptors in descriptors[provider].items():
            if (
                not isinstance(account_kind, ConnectorAccountKind)
                or set(account_descriptors)
                != {ConnectorResource.MAIL, ConnectorResource.CALENDAR}
            ):
                raise ConnectedReleasePreviewProviderError()
            sources[provider][account_kind] = {
                resource: ConnectedReleasePreviewCredentialSource(
                    database=database,
                    credential_key=credential_key,
                    registration=registrations[provider],
                    descriptor=account_descriptors[resource],
                    now=now,
                )
                for resource in (
                    ConnectorResource.MAIL,
                    ConnectorResource.CALENDAR,
                )
            }
    return {
        provider: {
            account_kind: (
                ConnectedGoogleReleasePreviewProbe(
                    sources=account_sources,
                    contract_sha256=contract_sha256,
                    now=now,
                )
                if provider is ConnectorProvider.GOOGLE
                else ConnectedMicrosoftReleasePreviewProbe(
                    sources=account_sources,
                    contract_sha256=contract_sha256,
                    now=now,
                )
            )
            for account_kind, account_sources in sources[provider].items()
        }
        for provider in ConnectorProvider
    }


__all__ = [
    "ConnectedGoogleReleasePreviewProbe",
    "ConnectedMicrosoftReleasePreviewProbe",
    "ConnectedProviderReleasePreviewReceipt",
    "ConnectedReleasePreviewCredentialSource",
    "ConnectedReleasePreviewProviderError",
    "build_connected_release_preview_provider_probes",
]
