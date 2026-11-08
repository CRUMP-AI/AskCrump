"""Durable, provider-neutral cleanup for externally issued OAuth grants.

The token exchange path creates an ``exchange_unknown`` obligation before a
provider request can leave the host.  Once encrypted token custody exists, the
obligation is rebound to that exact ciphertext record.  Cleanup workers claim
one durable job, recover a lost claim response by claim ID, and settle it only
after a bounded provider-specific revocation decision.

No raw token, provider account identifier, or customer content is logged or
included in a receipt.  Microsoft deliberately returns a user-action outcome:
there is no narrow delegated-token revocation endpoint equivalent to Google's
RFC-7009-style endpoint, and broad Graph session/consent operations are not an
honest substitute.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
import hashlib
import json
import re
from typing import Any, Protocol
from urllib.parse import urlencode
from uuid import UUID, uuid4

import certifi
import httpx

from .connected_app_policy import ConnectorProvider


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"[^\s\x00-\x1f\x7f]{16,16384}")
_MAX_ENCRYPTED_RECORD_BYTES = 256 * 1024
_MAX_RESPONSE_BYTES = 4096
_MAX_CLAIM = timedelta(seconds=120)
_GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"


class ConnectedGrantCleanupError(RuntimeError):
    """Content-free cleanup error safe for operational telemetry."""

    _ALLOWED = frozenset(
        {
            "GRANT_CLEANUP_AMBIGUOUS",
            "GRANT_CLEANUP_BINDING_MISMATCH",
            "GRANT_CLEANUP_INVALID",
            "GRANT_CLEANUP_STALE",
            "GRANT_CLEANUP_UNAVAILABLE",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            raise ValueError("invalid grant-cleanup error")
        self.code = code
        super().__init__(code)


class GrantCleanupRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID") from None
    if value != canonical:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
    return value.astimezone(UTC).isoformat()


def _object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
    return value


async def _rpc(boundary: GrantCleanupRPC, name: str, payload: dict[str, object]) -> object:
    try:
        return await boundary.rpc(name, payload, retry_transient=True)
    except ConnectedGrantCleanupError:
        raise
    except Exception:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_UNAVAILABLE") from None


@dataclass(frozen=True, slots=True)
class ConnectedGrantCleanupClaim:
    cleanup_id: str
    provider: ConnectorProvider
    source_kind: str
    source_binding_sha256: str
    encrypted_record: Mapping[str, object]
    claim_id: str
    claim_expires_at: datetime
    attempts: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "cleanup_id", _uuid(self.cleanup_id, "cleanup_id"))
        object.__setattr__(self, "claim_id", _uuid(self.claim_id, "claim_id"))
        if not isinstance(self.provider, ConnectorProvider):
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        if self.source_kind not in {"provisional", "credential"}:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        object.__setattr__(self, "source_binding_sha256", _sha(self.source_binding_sha256))
        if type(self.encrypted_record) is not dict:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        try:
            encoded = json.dumps(
                self.encrypted_record,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID") from None
        if not encoded or len(encoded) > _MAX_ENCRYPTED_RECORD_BYTES:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        expires = self.claim_expires_at
        if not isinstance(expires, datetime) or expires.tzinfo is None:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        object.__setattr__(self, "claim_expires_at", expires.astimezone(UTC))
        if type(self.attempts) is not int or not 1 <= self.attempts <= 32:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")

    def __repr__(self) -> str:
        return (
            "ConnectedGrantCleanupClaim("
            f"provider={self.provider.value!r}, source_kind={self.source_kind!r}, "
            "encrypted_record='<redacted>', binding='<redacted>')"
        )


_CLAIM_KEYS = frozenset(
    {
        "cleanup_id",
        "provider",
        "source_kind",
        "source_binding_sha256",
        "encrypted_record",
        "claim_id",
        "claim_expires_at",
        "attempts",
    }
)


def _claim_envelope(value: object) -> ConnectedGrantCleanupClaim | None:
    envelope = _object(value, frozenset({"status", "record"}))
    status = envelope["status"]
    if status in {"empty", "absent"} and envelope["record"] is None:
        return None
    if status == "stale" and envelope["record"] is None:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_STALE")
    if status != "claimed" or envelope["record"] is None:
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
    row = _object(envelope["record"], _CLAIM_KEYS)
    try:
        provider = ConnectorProvider(row["provider"])
    except (TypeError, ValueError):
        raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID") from None
    return ConnectedGrantCleanupClaim(
        cleanup_id=_uuid(row["cleanup_id"], "cleanup_id"),
        provider=provider,
        source_kind=row["source_kind"],
        source_binding_sha256=_sha(row["source_binding_sha256"]),
        encrypted_record=row["encrypted_record"],
        claim_id=_uuid(row["claim_id"], "claim_id"),
        claim_expires_at=_time(row["claim_expires_at"]),
        attempts=row["attempts"],
    )


class SupabaseConnectedGrantCleanupStore:
    """Strict durable cleanup outbox with exact response-loss recovery."""

    def __init__(self, rpc: GrantCleanupRPC) -> None:
        if not callable(getattr(rpc, "rpc", None)):
            raise TypeError("grant-cleanup RPC boundary is invalid")
        self._rpc = rpc

    @staticmethod
    def _status(value: object, allowed: frozenset[str]) -> str:
        row = _object(value, frozenset({"status", "cleanup_id"}))
        status = row["status"]
        _uuid(row["cleanup_id"], "cleanup_id")
        if status not in allowed:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        return status

    async def begin(
        self,
        *,
        cleanup_id: str,
        owner_id: str,
        connection_id: str,
        exchange_id: str,
        provider: ConnectorProvider,
        exchange_binding_sha256: str,
        deadline_at: datetime,
    ) -> None:
        if not isinstance(provider, ConnectorProvider):
            raise TypeError("provider must be ConnectorProvider")
        payload = {
            "p_cleanup_id": _uuid(cleanup_id, "cleanup_id"),
            "p_owner_id": _uuid(owner_id, "owner_id"),
            "p_connection_id": _uuid(connection_id, "connection_id"),
            "p_exchange_id": _uuid(exchange_id, "exchange_id"),
            "p_provider": provider.value,
            "p_exchange_binding_sha256": _sha(exchange_binding_sha256),
            "p_deadline_at": _iso(deadline_at),
        }
        try:
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_begin_v1", payload)
        except ConnectedGrantCleanupError:
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_begin_v1", payload)
        row = _object(
            result,
            frozenset(
                {"status", "cleanup_id", "source_binding_sha256", "created_at", "updated_at"}
            ),
        )
        if (
            row["status"] != "exchange_pending"
            or _uuid(row["cleanup_id"], "cleanup_id") != cleanup_id
            or _sha(row["source_binding_sha256"]) != exchange_binding_sha256
        ):
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_BINDING_MISMATCH")
        _time(row["created_at"])
        _time(row["updated_at"])

    async def attach(
        self,
        *,
        cleanup_id: str,
        exchange_binding_sha256: str,
        source_kind: str,
        source_binding_sha256: str,
        encrypted_record: Mapping[str, object],
    ) -> None:
        if source_kind not in {"provisional", "credential"} or type(encrypted_record) is not dict:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        payload = {
            "p_cleanup_id": _uuid(cleanup_id, "cleanup_id"),
            "p_exchange_binding_sha256": _sha(exchange_binding_sha256),
            "p_source_kind": source_kind,
            "p_source_binding_sha256": _sha(source_binding_sha256),
            "p_encrypted_record": dict(encrypted_record),
        }
        try:
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_attach_v1", payload)
        except ConnectedGrantCleanupError:
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_attach_v1", payload)
        row = _object(
            result,
            frozenset(
                {"status", "cleanup_id", "source_binding_sha256", "created_at", "updated_at"}
            ),
        )
        if (
            row["status"] != "retained"
            or _uuid(row["cleanup_id"], "cleanup_id") != cleanup_id
            or _sha(row["source_binding_sha256"]) != source_binding_sha256
        ):
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_BINDING_MISMATCH")
        _time(row["created_at"])
        _time(row["updated_at"])

    async def release(self, *, cleanup_id: str, source_binding_sha256: str) -> None:
        payload = {
            "p_cleanup_id": _uuid(cleanup_id, "cleanup_id"),
            "p_source_binding_sha256": _sha(source_binding_sha256),
        }
        try:
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_release_v1", payload)
        except ConnectedGrantCleanupError:
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_release_v1", payload)
        if self._status(result, frozenset({"released"})) != "released":
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")

    async def release_recover(
        self,
        *,
        cleanup_id: str,
        credential_handle_sha256: str,
    ) -> None:
        payload = {
            "p_cleanup_id": _uuid(cleanup_id, "cleanup_id"),
            "p_credential_handle_sha256": _sha(credential_handle_sha256),
        }
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_provider_cleanup_release_recover_v1",
                payload,
            )
        except ConnectedGrantCleanupError:
            result = await _rpc(
                self._rpc,
                "connected_app_provider_cleanup_release_recover_v1",
                payload,
            )
        if self._status(result, frozenset({"released"})) != "released":
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")

    async def recover(self, claim_id: str) -> ConnectedGrantCleanupClaim | None:
        result = await _rpc(
            self._rpc,
            "connected_app_provider_cleanup_recover_v1",
            {"p_claim_id": _uuid(claim_id, "claim_id")},
        )
        return _claim_envelope(result)

    async def claim_next(
        self,
        *,
        lease_for: timedelta = timedelta(seconds=30),
    ) -> ConnectedGrantCleanupClaim | None:
        if (
            not isinstance(lease_for, timedelta)
            or lease_for < timedelta(seconds=5)
            or lease_for > _MAX_CLAIM
            or lease_for.total_seconds() != int(lease_for.total_seconds())
        ):
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        claim_id = str(uuid4())
        payload = {"p_claim_id": claim_id, "p_lease_seconds": int(lease_for.total_seconds())}
        try:
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_claim_v1", payload)
        except ConnectedGrantCleanupError:
            try:
                recovered = await self.recover(claim_id)
            except ConnectedGrantCleanupError as exc:
                if exc.code == "GRANT_CLEANUP_STALE":
                    raise
                recovered = None
            if recovered is not None:
                return recovered
            # Recovery proved the first claim did not commit.  Reusing the same
            # claim ID is safe and prevents a second live winner.
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_claim_v1", payload)
        claim = _claim_envelope(result)
        if claim is not None and claim.claim_id != claim_id:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_BINDING_MISMATCH")
        return claim

    async def finish(
        self,
        claim: ConnectedGrantCleanupClaim,
        *,
        outcome: str,
        provider_receipt_sha256: str | None,
    ) -> str:
        if not isinstance(claim, ConnectedGrantCleanupClaim):
            raise TypeError("claim must be ConnectedGrantCleanupClaim")
        if outcome not in {"succeeded", "retry", "user_action_required"}:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        if (outcome == "succeeded") is (provider_receipt_sha256 is None):
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_INVALID")
        receipt = None if provider_receipt_sha256 is None else _sha(provider_receipt_sha256)
        payload = {
            "p_cleanup_id": claim.cleanup_id,
            "p_claim_id": claim.claim_id,
            "p_outcome": outcome,
            "p_provider_receipt_sha256": receipt,
        }
        try:
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_finish_v1", payload)
        except ConnectedGrantCleanupError:
            result = await _rpc(self._rpc, "connected_app_provider_cleanup_finish_v1", payload)
        status = self._status(
            result,
            frozenset({"succeeded", "retry", "user_action_required"}),
        )
        if status != outcome:
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_BINDING_MISMATCH")
        return status


class ProviderGrantCleanupOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    RETRY = "retry"
    USER_ACTION_REQUIRED = "user_action_required"


@dataclass(frozen=True, slots=True)
class ProviderGrantCleanupResult:
    outcome: ProviderGrantCleanupOutcome
    provider_receipt_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ProviderGrantCleanupOutcome):
            raise TypeError("outcome must be ProviderGrantCleanupOutcome")
        if (self.outcome is ProviderGrantCleanupOutcome.SUCCEEDED) is (
            self.provider_receipt_sha256 is None
        ):
            raise ValueError("successful cleanup requires exactly one receipt")
        if self.provider_receipt_sha256 is not None:
            object.__setattr__(self, "provider_receipt_sha256", _sha(self.provider_receipt_sha256))


class ProviderGrantRevocationSecret:
    """Ephemeral revocation token that refuses display or serialization."""

    __slots__ = ("__token",)

    def __init__(self, token: str) -> None:
        if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
            raise ValueError("provider revocation token is invalid")
        self.__token = token

    def reveal_for_google_revocation(self) -> str:
        return self.__token

    def __repr__(self) -> str:
        return "ProviderGrantRevocationSecret(token='<redacted>')"

    def __str__(self) -> str:
        return "<provider-grant-revocation-secret:redacted>"

    def __getstate__(self) -> object:
        raise TypeError("provider revocation token cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("provider revocation token cannot be serialized")


class ProviderGrantSecretResolver(Protocol):
    async def resolve(
        self,
        claim: ConnectedGrantCleanupClaim,
    ) -> ProviderGrantRevocationSecret: ...


class ProviderGrantRevoker(Protocol):
    async def revoke(
        self,
        secret: ProviderGrantRevocationSecret | None,
    ) -> ProviderGrantCleanupResult: ...


class GoogleOAuthGrantRevoker:
    """Bounded HTTPS POST to Google's fixed token revocation endpoint."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def revoke(
        self,
        secret: ProviderGrantRevocationSecret | None,
    ) -> ProviderGrantCleanupResult:
        if not isinstance(secret, ProviderGrantRevocationSecret):
            raise TypeError("Google revocation requires a revocation secret")
        body = urlencode({"token": secret.reveal_for_google_revocation()}).encode("ascii")
        timeout = httpx.Timeout(connect=5.0, write=10.0, read=15.0, pool=5.0)
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                verify=certifi.where(),
                timeout=timeout,
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
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return ProviderGrantCleanupResult(ProviderGrantCleanupOutcome.RETRY)
        except httpx.HTTPError:
            # A timeout/write/read error may have happened after dispatch.  Do
            # not claim success or keep retrying an unknown external effect.
            return ProviderGrantCleanupResult(ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED)
        if 300 <= response.status_code < 400:
            return ProviderGrantCleanupResult(ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED)
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                return ProviderGrantCleanupResult(
                    ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED
                )
            if not 0 <= size <= _MAX_RESPONSE_BYTES:
                return ProviderGrantCleanupResult(
                    ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED
                )
        if len(response.content) > _MAX_RESPONSE_BYTES:
            return ProviderGrantCleanupResult(ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED)
        if response.status_code == 200:
            receipt = hashlib.sha256(b"google\x00oauth-revoke\x00http-200").hexdigest()
            return ProviderGrantCleanupResult(
                ProviderGrantCleanupOutcome.SUCCEEDED,
                provider_receipt_sha256=receipt,
            )
        if response.status_code in {429, 500, 502, 503, 504}:
            return ProviderGrantCleanupResult(ProviderGrantCleanupOutcome.RETRY)
        return ProviderGrantCleanupResult(ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED)


class MicrosoftOAuthGrantRevoker:
    """Honest no-network result for Microsoft's missing narrow revoke API."""

    async def revoke(
        self,
        secret: ProviderGrantRevocationSecret | None,
    ) -> ProviderGrantCleanupResult:
        del secret
        return ProviderGrantCleanupResult(ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED)


class ConnectedGrantCleanupWorker:
    """Claims, revokes, and exactly settles one durable cleanup obligation."""

    def __init__(
        self,
        *,
        store: SupabaseConnectedGrantCleanupStore,
        secret_resolver: ProviderGrantSecretResolver,
        google: ProviderGrantRevoker,
        microsoft: ProviderGrantRevoker,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(store, SupabaseConnectedGrantCleanupStore):
            raise TypeError("store must be SupabaseConnectedGrantCleanupStore")
        if not callable(getattr(secret_resolver, "resolve", None)):
            raise TypeError("secret_resolver must implement resolve")
        if not callable(getattr(google, "revoke", None)) or not callable(
            getattr(microsoft, "revoke", None)
        ):
            raise TypeError("provider revokers are invalid")
        if not callable(now):
            raise TypeError("now must be callable")
        self._store = store
        self._secret_resolver = secret_resolver
        self._revokers = {
            ConnectorProvider.GOOGLE: google,
            ConnectorProvider.MICROSOFT: microsoft,
        }
        self._now = now

    async def run_once(self) -> str:
        claim = await self._store.claim_next()
        if claim is None:
            return "empty"
        reference = self._now()
        if (
            not isinstance(reference, datetime)
            or reference.tzinfo is None
            or claim.claim_expires_at <= reference.astimezone(UTC)
        ):
            raise ConnectedGrantCleanupError("GRANT_CLEANUP_STALE")
        secret: ProviderGrantRevocationSecret | None = None
        if claim.provider is ConnectorProvider.GOOGLE:
            try:
                secret = await self._secret_resolver.resolve(claim)
            except Exception:
                result = ProviderGrantCleanupResult(
                    ProviderGrantCleanupOutcome.USER_ACTION_REQUIRED
                )
            else:
                result = await self._revokers[claim.provider].revoke(secret)
        else:
            result = await self._revokers[claim.provider].revoke(None)
        return await self._store.finish(
            claim,
            outcome=result.outcome.value,
            provider_receipt_sha256=result.provider_receipt_sha256,
        )
