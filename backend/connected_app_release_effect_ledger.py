"""Durable content-free effect ledger for release-preview crash recovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re
from typing import Mapping, Protocol
from uuid import UUID, uuid5

from .connected_app_contracts import ConnectorAccountKind
from .connected_app_policy import ConnectorProvider, ConnectorResource


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ConnectedReleasePreviewEffectError(RuntimeError):
    def __init__(self) -> None:
        self.code = "CONNECTED_RELEASE_PREVIEW_EFFECT_FAILED"
        super().__init__(self.code)


class ConnectedReleasePreviewEffectPhase(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    OBSERVED = "observed"
    CLEANUP = "cleanup"
    CLEAN = "clean"
    RETAINED_TEST_ARTIFACT = "retained_test_artifact"
    EFFECT_UNKNOWN = "effect_unknown"


class ConnectedReleasePreviewAuthorityPhase(StrEnum):
    PENDING = "pending"
    REVOCATION_DISPATCHED = "revocation_dispatched"
    REVOCATION_ATTESTED = "revocation_attested"
    LOCAL_RETIRED = "local_retired"


class ConnectedReleasePreviewEffectRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedReleasePreviewEffectError()
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedReleasePreviewEffectError() from None
    if canonical != value:
        raise ConnectedReleasePreviewEffectError()
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ConnectedReleasePreviewEffectError()
    return value


def release_preview_marker(
    *,
    invocation_id: str,
    provider: ConnectorProvider,
    account_kind: ConnectorAccountKind,
    resource: ConnectorResource,
) -> str:
    _uuid(invocation_id)
    if (
        not isinstance(provider, ConnectorProvider)
        or not isinstance(account_kind, ConnectorAccountKind)
        or not isinstance(resource, ConnectorResource)
    ):
        raise ConnectedReleasePreviewEffectError()
    return (
        "askcrump-release-preview-"
        + invocation_id
        + "-"
        + provider.value
        + "-"
        + account_kind.value.replace("_", "-")
        + "-"
        + resource.value
    )


@dataclass(frozen=True, slots=True)
class ConnectedReleasePreviewEffectState:
    effect_id: str
    invocation_id: str
    provider: ConnectorProvider
    account_kind: ConnectorAccountKind
    resource: ConnectorResource
    marker_sha256: str
    phase: ConnectedReleasePreviewEffectPhase
    revision: int
    artifact_id_sha256: str | None

    def __post_init__(self) -> None:
        _uuid(self.effect_id)
        _uuid(self.invocation_id)
        _sha(self.marker_sha256)
        if (
            not isinstance(self.provider, ConnectorProvider)
            or not isinstance(self.account_kind, ConnectorAccountKind)
            or not isinstance(self.resource, ConnectorResource)
            or not isinstance(self.phase, ConnectedReleasePreviewEffectPhase)
            or type(self.revision) is not int
            or self.revision < 0
            or (
                self.artifact_id_sha256 is not None
                and _SHA256.fullmatch(self.artifact_id_sha256) is None
            )
        ):
            raise ConnectedReleasePreviewEffectError()


@dataclass(frozen=True, slots=True)
class ConnectedReleasePreviewAuthorityState:
    invocation_id: str
    provider: ConnectorProvider
    account_kind: ConnectorAccountKind
    phase: ConnectedReleasePreviewAuthorityPhase
    revision: int
    provider_receipt_sha256: str | None

    def __post_init__(self) -> None:
        _uuid(self.invocation_id)
        if (
            not isinstance(self.provider, ConnectorProvider)
            or not isinstance(self.account_kind, ConnectorAccountKind)
            or not isinstance(self.phase, ConnectedReleasePreviewAuthorityPhase)
            or type(self.revision) is not int
            or self.revision < 0
            or (
                self.provider_receipt_sha256 is not None
                and _SHA256.fullmatch(self.provider_receipt_sha256) is None
            )
            or (
                self.provider is ConnectorProvider.GOOGLE
                and (
                    (self.phase in {
                        ConnectedReleasePreviewAuthorityPhase.PENDING,
                        ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED,
                    })
                    is (self.provider_receipt_sha256 is not None)
                )
            )
            or (
                self.provider is ConnectorProvider.MICROSOFT
                and (
                    self.phase
                    not in {
                        ConnectedReleasePreviewAuthorityPhase.PENDING,
                        ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED,
                    }
                    or self.provider_receipt_sha256 is not None
                )
            )
        ):
            raise ConnectedReleasePreviewEffectError()


def _effect_manifest(
    *,
    invocation_id: str,
    google_account_kind: ConnectorAccountKind,
) -> tuple[list[dict[str, str]], str]:
    namespace = UUID(_uuid(invocation_id))
    rows: list[dict[str, str]] = []
    groups = (
        (ConnectorProvider.GOOGLE, google_account_kind),
        (ConnectorProvider.MICROSOFT, ConnectorAccountKind.PERSONAL),
        (ConnectorProvider.MICROSOFT, ConnectorAccountKind.WORK_SCHOOL),
    )
    for provider, account_kind in groups:
        for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR):
            marker = release_preview_marker(
                invocation_id=invocation_id,
                provider=provider,
                account_kind=account_kind,
                resource=resource,
            )
            rows.append(
                {
                    "effect_id": str(
                        uuid5(
                            namespace,
                            provider.value
                            + ":"
                            + account_kind.value
                            + ":"
                            + resource.value,
                        )
                    ),
                    "provider": provider.value,
                    "account_kind": account_kind.value,
                    "resource": resource.value,
                    "marker_sha256": hashlib.sha256(
                        marker.encode("ascii")
                    ).hexdigest(),
                }
            )
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    return rows, digest


class ConnectedReleasePreviewEffectLedger:
    __slots__ = ("_database", "_effect_manifest_sha256", "_invocation_id")

    def __init__(
        self,
        *,
        database: ConnectedReleasePreviewEffectRPC,
        invocation_id: str,
    ) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise ConnectedReleasePreviewEffectError()
        self._database = database
        self._invocation_id = _uuid(invocation_id)
        self._effect_manifest_sha256: str | None = None

    @property
    def invocation_id(self) -> str:
        return self._invocation_id

    @property
    def effect_manifest_sha256(self) -> str:
        if self._effect_manifest_sha256 is None:
            raise ConnectedReleasePreviewEffectError()
        return self._effect_manifest_sha256

    async def begin(
        self,
        *,
        google_account_kind: ConnectorAccountKind,
        descriptor_matrix_sha256: str,
        dedicated_account_attestation_sha256: str,
        deployment: Mapping[str, str],
        release_preview_contract_sha256: str,
    ) -> str:
        rows, manifest_sha256 = _effect_manifest(
            invocation_id=self._invocation_id,
            google_account_kind=google_account_kind,
        )
        required = {
            "composition_manifest_sha256",
            "database_contract_sha256",
            "database_target_fingerprint",
            "provider_contract_sha256",
            "deployment_id",
            "commit_sha",
            "host_configuration_ciphertext_sha256",
            "root_key_id",
        }
        if set(deployment) != required:
            raise ConnectedReleasePreviewEffectError()
        payload: dict[str, object] = {
            "p_invocation_id": self._invocation_id,
            "p_release_preview_contract_sha256": _sha(
                release_preview_contract_sha256
            ),
            "p_descriptor_matrix_sha256": _sha(descriptor_matrix_sha256),
            "p_dedicated_account_attestation_sha256": _sha(
                dedicated_account_attestation_sha256
            ),
            "p_effect_manifest_sha256": manifest_sha256,
            "p_google_account_kind": google_account_kind.value,
            "p_effects": rows,
        }
        payload.update({"p_" + key: value for key, value in deployment.items()})
        try:
            await self._database.rpc(
                "connected_app_release_preview_begin_v1",
                payload,
                retry_transient=False,
            )
        except Exception:
            pass
        if len(await self.states()) != 6:
            raise ConnectedReleasePreviewEffectError()
        if len(await self.authorities()) != 3:
            raise ConnectedReleasePreviewEffectError()
        self._effect_manifest_sha256 = manifest_sha256
        return manifest_sha256

    async def states(self) -> Mapping[str, ConnectedReleasePreviewEffectState]:
        try:
            value = await self._database.rpc(
                "connected_app_release_preview_status_v1",
                {"p_invocation_id": self._invocation_id},
                retry_transient=True,
            )
        except Exception:
            raise ConnectedReleasePreviewEffectError() from None
        if type(value) is not list or not value or len(value) > 6:
            raise ConnectedReleasePreviewEffectError()
        result: dict[str, ConnectedReleasePreviewEffectState] = {}
        keys = {
            "effect_id",
            "invocation_id",
            "provider",
            "account_kind",
            "resource",
            "marker_sha256",
            "phase",
            "revision",
            "artifact_id_sha256",
        }
        for item in value:
            if type(item) is not dict or set(item) != keys:
                raise ConnectedReleasePreviewEffectError()
            try:
                state = ConnectedReleasePreviewEffectState(
                    effect_id=item["effect_id"],
                    invocation_id=item["invocation_id"],
                    provider=ConnectorProvider(item["provider"]),
                    account_kind=ConnectorAccountKind(item["account_kind"]),
                    resource=ConnectorResource(item["resource"]),
                    marker_sha256=item["marker_sha256"],
                    phase=ConnectedReleasePreviewEffectPhase(item["phase"]),
                    revision=item["revision"],
                    artifact_id_sha256=item["artifact_id_sha256"],
                )
            except Exception:
                raise ConnectedReleasePreviewEffectError() from None
            if state.invocation_id != self._invocation_id or state.effect_id in result:
                raise ConnectedReleasePreviewEffectError()
            result[state.effect_id] = state
        return result

    async def transition(
        self,
        *,
        state: ConnectedReleasePreviewEffectState,
        next_phase: ConnectedReleasePreviewEffectPhase,
        artifact_id: str | None = None,
        artifact_id_sha256: str | None = None,
    ) -> ConnectedReleasePreviewEffectState:
        if (
            type(state) is not ConnectedReleasePreviewEffectState
            or state.invocation_id != self._invocation_id
            or not isinstance(next_phase, ConnectedReleasePreviewEffectPhase)
            or (artifact_id is not None and artifact_id_sha256 is not None)
            or (
                artifact_id_sha256 is not None
                and _SHA256.fullmatch(artifact_id_sha256) is None
            )
        ):
            raise ConnectedReleasePreviewEffectError()
        artifact_sha256 = (
            artifact_id_sha256
            if artifact_id_sha256 is not None
            else (
                hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()
                if artifact_id is not None
                else state.artifact_id_sha256
            )
        )
        payload = {
            "p_invocation_id": self._invocation_id,
            "p_effect_id": state.effect_id,
            "p_expected_revision": state.revision,
            "p_expected_phase": state.phase.value,
            "p_next_phase": next_phase.value,
            "p_artifact_id_sha256": artifact_sha256,
        }
        try:
            await self._database.rpc(
                "connected_app_release_preview_effect_v1",
                payload,
                retry_transient=False,
            )
        except Exception:
            pass
        observed = (await self.states()).get(state.effect_id)
        if (
            observed is None
            or observed.phase is not next_phase
            or observed.revision != state.revision + 1
            or observed.artifact_id_sha256 != artifact_sha256
        ):
            raise ConnectedReleasePreviewEffectError()
        return observed

    async def state_for(
        self,
        *,
        provider: ConnectorProvider,
        account_kind: ConnectorAccountKind,
        resource: ConnectorResource,
    ) -> ConnectedReleasePreviewEffectState:
        if (
            not isinstance(provider, ConnectorProvider)
            or not isinstance(account_kind, ConnectorAccountKind)
            or not isinstance(resource, ConnectorResource)
        ):
            raise ConnectedReleasePreviewEffectError()
        matches = tuple(
            state
            for state in (await self.states()).values()
            if state.provider is provider
            and state.account_kind is account_kind
            and state.resource is resource
        )
        if len(matches) != 1:
            raise ConnectedReleasePreviewEffectError()
        return matches[0]

    async def authorities(
        self,
    ) -> Mapping[str, ConnectedReleasePreviewAuthorityState]:
        try:
            value = await self._database.rpc(
                "connected_app_release_preview_authority_status_v1",
                {"p_invocation_id": self._invocation_id},
                retry_transient=True,
            )
        except Exception:
            raise ConnectedReleasePreviewEffectError() from None
        if type(value) is not list or len(value) != 3:
            raise ConnectedReleasePreviewEffectError()
        keys = {
            "invocation_id",
            "provider",
            "account_kind",
            "phase",
            "revision",
            "provider_receipt_sha256",
        }
        result: dict[str, ConnectedReleasePreviewAuthorityState] = {}
        for item in value:
            if type(item) is not dict or set(item) != keys:
                raise ConnectedReleasePreviewEffectError()
            try:
                state = ConnectedReleasePreviewAuthorityState(
                    invocation_id=item["invocation_id"],
                    provider=ConnectorProvider(item["provider"]),
                    account_kind=ConnectorAccountKind(item["account_kind"]),
                    phase=ConnectedReleasePreviewAuthorityPhase(item["phase"]),
                    revision=item["revision"],
                    provider_receipt_sha256=item["provider_receipt_sha256"],
                )
            except Exception:
                raise ConnectedReleasePreviewEffectError() from None
            key = state.provider.value + ":" + state.account_kind.value
            if state.invocation_id != self._invocation_id or key in result:
                raise ConnectedReleasePreviewEffectError()
            result[key] = state
        return result

    async def authority_for(
        self,
        *,
        provider: ConnectorProvider,
        account_kind: ConnectorAccountKind,
    ) -> ConnectedReleasePreviewAuthorityState:
        if not isinstance(provider, ConnectorProvider) or not isinstance(
            account_kind, ConnectorAccountKind
        ):
            raise ConnectedReleasePreviewEffectError()
        state = (await self.authorities()).get(
            provider.value + ":" + account_kind.value
        )
        if state is None:
            raise ConnectedReleasePreviewEffectError()
        return state

    async def transition_authority(
        self,
        *,
        state: ConnectedReleasePreviewAuthorityState,
        next_phase: ConnectedReleasePreviewAuthorityPhase,
        provider_receipt_sha256: str | None = None,
    ) -> ConnectedReleasePreviewAuthorityState:
        if (
            type(state) is not ConnectedReleasePreviewAuthorityState
            or state.invocation_id != self._invocation_id
            or not isinstance(next_phase, ConnectedReleasePreviewAuthorityPhase)
            or (
                provider_receipt_sha256 is not None
                and _SHA256.fullmatch(provider_receipt_sha256) is None
            )
        ):
            raise ConnectedReleasePreviewEffectError()
        receipt = (
            provider_receipt_sha256
            if provider_receipt_sha256 is not None
            else state.provider_receipt_sha256
        )
        payload = {
            "p_invocation_id": self._invocation_id,
            "p_provider": state.provider.value,
            "p_account_kind": state.account_kind.value,
            "p_expected_revision": state.revision,
            "p_expected_phase": state.phase.value,
            "p_next_phase": next_phase.value,
            "p_provider_receipt_sha256": receipt,
        }
        try:
            await self._database.rpc(
                "connected_app_release_preview_authority_v1",
                payload,
                retry_transient=False,
            )
        except Exception:
            pass
        observed = await self.authority_for(
            provider=state.provider,
            account_kind=state.account_kind,
        )
        if (
            observed.phase is not next_phase
            or observed.revision != state.revision + 1
            or observed.provider_receipt_sha256 != receipt
        ):
            raise ConnectedReleasePreviewEffectError()
        return observed

    async def finalize(self) -> None:
        try:
            value = await self._database.rpc(
                "connected_app_release_preview_finalize_v1",
                {"p_invocation_id": self._invocation_id},
                retry_transient=False,
            )
        except Exception:
            value = None
        if type(value) is not dict or value != {
            "invocation_id": self._invocation_id,
            "status": "clean",
            "unsettled_effects": 0,
        }:
            raise ConnectedReleasePreviewEffectError()

    async def fail(self) -> None:
        """Atomically terminalize a fully retired, non-attested invocation."""

        expected = None
        for _attempt in range(2):
            try:
                expected = await self._database.rpc(
                    "connected_app_release_preview_fail_v1",
                    {"p_invocation_id": self._invocation_id},
                    retry_transient=False,
                )
                break
            except Exception:
                continue
        if (
            type(expected) is not dict
            or set(expected) != {"invocation_id", "status", "unknown_effects"}
            or expected["invocation_id"] != self._invocation_id
            or expected["status"] != "failed"
            or type(expected["unknown_effects"]) is not int
            or not 0 <= expected["unknown_effects"] <= 6
        ):
            raise ConnectedReleasePreviewEffectError()


__all__ = [
    "ConnectedReleasePreviewAuthorityPhase",
    "ConnectedReleasePreviewAuthorityState",
    "ConnectedReleasePreviewEffectError",
    "ConnectedReleasePreviewEffectLedger",
    "ConnectedReleasePreviewEffectPhase",
    "ConnectedReleasePreviewEffectState",
    "release_preview_marker",
]
