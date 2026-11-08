"""Source-locked one-shot release preview for the connected operator.

This is deliberately not an HTTP route and never discovers credentials or
network access from the process environment. A supervised release process must
inject the exact request OIDC assertion, KMS loader, database boundary, and
reviewed Google/Microsoft preview probes. The one built-in gateway probe uses
the already reviewed request-OIDC gateway object.

The permit is consumed before KMS or provider I/O. A failure can therefore
never silently retry an external preview. The caller must run the harness in a
dedicated short-lived process and terminate that process after the content-free
result is captured; process termination is the plaintext-root destruction
boundary Python itself cannot guarantee.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
from typing import Callable, Mapping, Protocol
from uuid import UUID

from . import config
from .connected_app_host_bootstrap import (
    CONNECTED_DATABASE_CONTRACT_SHA256,
    CONNECTED_PROVIDER_CONTRACT_SHA256,
    SupabaseConnectedProductionReadinessProbe,
)
from .connected_app_host_configuration import ConnectedEncryptedHostConfiguration
from .connected_app_contracts import ConnectorAccountKind
from .connected_app_key_derivation import (
    ConnectedDerivedKeyset,
    ConnectedKeyCustodyKind,
    ConnectedRootKeyMaterial,
)
from .connected_app_kms import (
    ConnectedGoogleKMSRootLoader,
    ConnectedVercelOIDCAssertion,
)
from .connected_app_policy import ConnectorProvider
from .connected_app_production_keys import ConnectedProductionKeys
from .connected_app_release_preview_provider import (
    ConnectedGoogleReleasePreviewProbe,
    ConnectedMicrosoftReleasePreviewProbe,
    ConnectedProviderReleasePreviewReceipt,
    build_connected_release_preview_provider_probes,
)
from .connected_app_readiness_attestation import (
    ConnectedProviderSmokeAttestor,
    ConnectedProviderSmokeChallenge,
    ConnectedProviderSmokeDeployment,
)
from .connected_app_request_ai_gateway import (
    ConnectedRequestScopedAIGateway,
    ConnectedRequestScopedAIGatewayFactory,
)
from .connected_app_release_runtime_identity import (
    ConnectedVercelProductionIdentity,
    ConnectedVercelProductionRuntimeIdentity,
)
from .connected_app_release_database import (
    ConnectedReleasePreviewProductionDatabase,
)
from .connected_app_release_contract import (
    CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256,
    CONNECTED_RELEASE_PREVIEW_GOOGLE_REDIRECT,
    CONNECTED_RELEASE_PREVIEW_MICROSOFT_REDIRECT,
)
from .connected_app_release_effect_ledger import (
    ConnectedReleasePreviewEffectLedger,
    ConnectedReleasePreviewEffectPhase,
)
from .connected_app_policy import ConnectorResource


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{32}$")
_DEPLOYMENT = re.compile(r"^dpl_[A-Za-z0-9]{8,}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ROOT_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$")
_CONFIRMATION = "RUN_CONNECTED_RELEASE_PREVIEW_WITH_DEDICATED_NON_CUSTOMER_ACCOUNTS"
_MAX_PERMIT_LIFETIME = timedelta(minutes=15)
_MAX_PROBE_AGE = timedelta(minutes=15)
_MAX_DATABASE_RESPONSE_AGE = timedelta(seconds=60)
_FUTURE_SKEW = timedelta(seconds=5)
_GOOGLE_REDIRECT = CONNECTED_RELEASE_PREVIEW_GOOGLE_REDIRECT
_MICROSOFT_REDIRECT = CONNECTED_RELEASE_PREVIEW_MICROSOFT_REDIRECT


def _database_shape_eligible(database: object) -> bool:
    return type(database) is ConnectedReleasePreviewProductionDatabase


def _database_production_eligible(database: object) -> bool:
    return (
        _database_shape_eligible(database)
        and database.production_eligible() is True
    )


def _root_loader_source_eligible(
    loader: object,
    *,
    expected_manifest_sha256: str,
) -> bool:
    if (
        type(loader) is not ConnectedGoogleKMSRootLoader
        or loader._transport is not None
    ):
        return False
    configuration = loader._configuration
    return (
        configuration.project_number == config.CONNECTED_APPS_KMS_PROJECT_NUMBER
        and configuration.workload_identity_pool_id
        == config.CONNECTED_APPS_KMS_WIF_POOL_ID
        and configuration.workload_identity_provider_id
        == config.CONNECTED_APPS_KMS_WIF_PROVIDER_ID
        and configuration.service_account_email
        == config.CONNECTED_APPS_KMS_SERVICE_ACCOUNT_EMAIL
        and configuration.crypto_key_resource
        == config.CONNECTED_APPS_KMS_CRYPTO_KEY_RESOURCE
        and configuration.root_key_id == config.CONNECTED_APPS_KMS_ROOT_KEY_ID
        and configuration.composition_manifest_sha256
        == expected_manifest_sha256
        and configuration.custody_attestation_sha256
        == config.CONNECTED_APPS_KMS_CUSTODY_ATTESTATION_SHA256
        and configuration.expected_protection_level
        == config.CONNECTED_APPS_KMS_PROTECTION_LEVEL
        and configuration.expected_protection_level == "HSM"
        and configuration.root_ttl_seconds
        == config.CONNECTED_APPS_KMS_ROOT_TTL_SECONDS
        and hashlib.sha256(
            configuration.encrypted_root_b64.encode("ascii")
        ).hexdigest()
        == config.CONNECTED_APPS_KMS_ENCRYPTED_ROOT_SHA256
    )


def _gateway_factory_static_eligible(
    factory: object,
    *,
    database: object,
) -> bool:
    return (
        type(factory) is ConnectedRequestScopedAIGatewayFactory
        and factory._database is database
        and factory._model == "openai/gpt-oss-20b"
        and factory._provider == "groq"
    )


def _gateway_factory_runtime_eligible(
    factory: object,
    *,
    database: object,
    identity: ConnectedVercelProductionIdentity,
) -> bool:
    return (
        _gateway_factory_static_eligible(factory, database=database)
        and factory._deployment_id == identity.deployment_id
        and factory._commit_sha == identity.commit_sha
    )


class ConnectedReleasePreviewError(RuntimeError):
    """Content-free release-preview failure."""

    def __init__(self) -> None:
        self.code = "CONNECTED_RELEASE_PREVIEW_FAILED"
        super().__init__(self.code)


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedReleasePreviewError()
    return value.astimezone(UTC)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise ConnectedReleasePreviewError()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedReleasePreviewError() from None
    return _aware(parsed)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedReleasePreviewError()
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedReleasePreviewError() from None
    if canonical != value:
        raise ConnectedReleasePreviewError()
    return canonical


class ConnectedReleasePreviewPermit:
    """One explicit, bounded, nonserializable authorization for one ceremony."""

    __slots__ = (
        "_claimed",
        "_lock",
        "expires_at",
        "invocation_id",
        "issued_at",
        "recovery",
    )

    def __init__(
        self,
        *,
        invocation_id: str,
        issued_at: datetime,
        expires_at: datetime,
        confirmation: str,
        recovery: bool = False,
    ) -> None:
        issued = _aware(issued_at)
        expires = _aware(expires_at)
        if (
            config.connected_apps_release_candidate_source_released() is not True
            or confirmation != _CONFIRMATION
            or expires <= issued
            or expires - issued > _MAX_PERMIT_LIFETIME
            or type(recovery) is not bool
        ):
            raise ConnectedReleasePreviewError()
        self.invocation_id = _uuid(invocation_id)
        self.issued_at = issued
        self.expires_at = expires
        self.recovery = recovery
        self._claimed = False
        self._lock = asyncio.Lock()

    async def claim(self, *, now: datetime) -> None:
        reference = _aware(now)
        async with self._lock:
            if (
                self._claimed
                or reference < self.issued_at
                or reference >= self.expires_at
                or config.connected_apps_release_candidate_source_released() is not True
            ):
                raise ConnectedReleasePreviewError()
            self._claimed = True

    def __repr__(self) -> str:
        return "ConnectedReleasePreviewPermit(authorization='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("connected release-preview permits cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected release-preview permits cannot be serialized")


@dataclass(frozen=True, slots=True)
class ConnectedGatewayReleasePreviewReceipt:
    invocation_id: str
    contract_sha256: str
    checked_at: datetime
    request_oidc_attested: bool
    pinned_model_provider_attested: bool
    zero_retention_attested: bool
    cost_receipt_attested: bool

    def __post_init__(self) -> None:
        if (
            _uuid(self.invocation_id) != self.invocation_id
            or self.contract_sha256 != CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
            or not all(
                value is True
                for value in (
                    self.request_oidc_attested,
                    self.pinned_model_provider_attested,
                    self.zero_retention_attested,
                    self.cost_receipt_attested,
                )
            )
        ):
            raise ConnectedReleasePreviewError()
        object.__setattr__(self, "checked_at", _aware(self.checked_at))


class ConnectedReleasePreviewDatabase(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


class ConnectedAIGatewayReleaseProbe:
    """Concrete content-free smoke for the pinned request-OIDC gateway."""

    __slots__ = ("_now",)

    def __init__(self, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        if not callable(now):
            raise ConnectedReleasePreviewError()
        self._now = now

    async def preview(
        self,
        *,
        gateway: object,
        invocation_id: str,
        contract_sha256: str,
    ) -> ConnectedGatewayReleasePreviewReceipt:
        if (
            contract_sha256 != CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
            or not callable(getattr(gateway, "gateway_text", None))
        ):
            raise ConnectedReleasePreviewError()
        try:
            value = await gateway.gateway_text(
                system=(
                    "Return only this exact JSON object with no markdown or extra keys: "
                    '{"release_preview":"ok"}'
                ),
                prompt="Run the content-free Ask Crump connected release planning smoke.",
                max_tokens=128,
                timeout_seconds=10,
                user_id=_uuid(invocation_id),
                purpose="connected_app_plan",
            )
        except Exception:
            raise ConnectedReleasePreviewError() from None
        if value != '{"release_preview":"ok"}':
            raise ConnectedReleasePreviewError()
        return ConnectedGatewayReleasePreviewReceipt(
            invocation_id=invocation_id,
            contract_sha256=contract_sha256,
            checked_at=_aware(self._now()),
            request_oidc_attested=True,
            pinned_model_provider_attested=True,
            zero_retention_attested=True,
            cost_receipt_attested=True,
        )

    def __repr__(self) -> str:
        return "ConnectedAIGatewayReleaseProbe(content='none')"


@dataclass(frozen=True, slots=True)
class ConnectedReleasePreviewResult:
    invocation_id: str
    composition_manifest_sha256: str
    database_contract_sha256: str
    database_target_fingerprint: str
    provider_contract_sha256: str
    release_preview_contract_sha256: str
    deployment_id: str
    commit_sha: str
    host_configuration_ciphertext_sha256: str
    root_key_id: str
    provider_smoke_attestation_sha256: str
    checked_at: datetime
    expires_at: datetime
    process_exit_required: bool = True

    def __post_init__(self) -> None:
        if (
            _uuid(self.invocation_id) != self.invocation_id
            or not all(
                _SHA256.fullmatch(value)
                for value in (
                    self.composition_manifest_sha256,
                    self.database_contract_sha256,
                    self.provider_contract_sha256,
                    self.release_preview_contract_sha256,
                    self.host_configuration_ciphertext_sha256,
                    self.provider_smoke_attestation_sha256,
                )
            )
            or not _FINGERPRINT.fullmatch(self.database_target_fingerprint)
            or not _DEPLOYMENT.fullmatch(self.deployment_id)
            or not _COMMIT.fullmatch(self.commit_sha)
            or not _ROOT_KEY_ID.fullmatch(self.root_key_id)
            or self.process_exit_required is not True
        ):
            raise ConnectedReleasePreviewError()
        checked = _aware(self.checked_at)
        expires = _aware(self.expires_at)
        if expires <= checked:
            raise ConnectedReleasePreviewError()
        object.__setattr__(self, "checked_at", checked)
        object.__setattr__(self, "expires_at", expires)


class ConnectedReleasePreviewHarness:
    """Run all external previews once, then record and verify one HMAC receipt."""

    __slots__ = (
        "_ai_gateway_factory",
        "_ciphertext",
        "_database",
        "_database_target_fingerprint",
        "_gateway_probe",
        "_host_configuration_ciphertext_sha256",
        "_now",
        "_root_loader",
        "_runtime_identity",
    )

    def __init__(
        self,
        *,
        root_loader: ConnectedGoogleKMSRootLoader,
        ciphertext: ConnectedEncryptedHostConfiguration,
        database: ConnectedReleasePreviewDatabase,
        ai_gateway_factory: ConnectedRequestScopedAIGatewayFactory,
        gateway_probe: ConnectedAIGatewayReleaseProbe,
        runtime_identity: ConnectedVercelProductionRuntimeIdentity,
        database_target_fingerprint: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            # Production readiness can never be minted by a caller-injected
            # transport or duck-typed probe. The exact KMS loader uses the
            # fixed Google endpoints in connected_app_kms; its optional
            # transport exists only for isolated unit tests and is therefore
            # forbidden at this ceremony boundary.
            type(root_loader) is not ConnectedGoogleKMSRootLoader
            or root_loader._transport is not None
            or not _root_loader_source_eligible(
                root_loader,
                expected_manifest_sha256=(
                    config.CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256
                ),
            )
            or type(ciphertext) is not ConnectedEncryptedHostConfiguration
            or not _database_shape_eligible(database)
            or not _gateway_factory_static_eligible(
                ai_gateway_factory,
                database=database,
            )
            or type(gateway_probe) is not ConnectedAIGatewayReleaseProbe
            or type(runtime_identity)
            is not ConnectedVercelProductionRuntimeIdentity
            or not _FINGERPRINT.fullmatch(str(database_target_fingerprint or ""))
            or not callable(now)
        ):
            raise ConnectedReleasePreviewError()
        self._root_loader = root_loader
        self._ciphertext = ciphertext
        self._database = database
        self._ai_gateway_factory = ai_gateway_factory
        self._gateway_probe = gateway_probe
        self._runtime_identity = runtime_identity
        self._database_target_fingerprint = database_target_fingerprint
        self._host_configuration_ciphertext_sha256 = hashlib.sha256(
            ciphertext.value.encode("utf-8")
        ).hexdigest()
        self._now = now

    @staticmethod
    def _fresh(checked_at: datetime, *, reference: datetime) -> None:
        checked = _aware(checked_at)
        if checked > reference + _FUTURE_SKEW or reference - checked > _MAX_PROBE_AGE:
            raise ConnectedReleasePreviewError()

    async def _verify_dedicated_account_attestation(
        self,
        *,
        host: object,
        descriptor_matrix_sha256: str,
        attestation_sha256: str,
    ) -> None:
        try:
            groups = host.release_preview_connections  # type: ignore[attr-defined]
            owners = {
                descriptor.owner_id
                for provider_groups in groups.values()
                for resource_groups in provider_groups.values()
                for descriptor in resource_groups.values()
            }
        except Exception:
            raise ConnectedReleasePreviewError() from None
        if len(owners) != 1:
            raise ConnectedReleasePreviewError()
        owner_id = next(iter(owners))
        try:
            raw = await self._database.rpc(
                "connected_app_release_bootstrap_read_dedicated_v1",
                {
                    "p_dedicated_account_attestation_sha256": (
                        attestation_sha256
                    )
                },
                retry_transient=True,
            )
        except Exception:
            raise ConnectedReleasePreviewError() from None
        expected = {
            "ceremony_id",
            "owner_id",
            "session_id",
            "descriptor_matrix_sha256",
            "dedicated_account_attestation_sha256",
            "confirmed_at",
        }
        if type(raw) is not dict or set(raw) != expected:
            raise ConnectedReleasePreviewError()
        ceremony_id = _uuid(raw.get("ceremony_id"))
        _uuid(raw.get("session_id"))
        confirmed_at = _timestamp(raw.get("confirmed_at"))
        canonical = hashlib.sha256(
            b"askcrump-release-preview-dedicated-account-attestation-v1\0"
            + ceremony_id.encode("ascii")
            + b"\0"
            + owner_id.encode("ascii")
            + b"\0"
            + descriptor_matrix_sha256.encode("ascii")
            + b"\0three_dedicated_non_customer_accounts"
        ).hexdigest()
        if (
            raw.get("owner_id") != owner_id
            or raw.get("descriptor_matrix_sha256")
            != descriptor_matrix_sha256
            or raw.get("dedicated_account_attestation_sha256")
            != attestation_sha256
            or not hmac.compare_digest(canonical, attestation_sha256)
            or confirmed_at > _aware(self._now()) + _FUTURE_SKEW
        ):
            raise ConnectedReleasePreviewError()

    async def _issue_challenge(
        self,
        *,
        deployment: ConnectedProviderSmokeDeployment,
    ) -> ConnectedProviderSmokeChallenge:
        try:
            raw = await self._database.rpc(
                "connected_app_issue_provider_smoke_challenge_v1",
                {
                    "p_composition_manifest_sha256": (
                        deployment.composition_manifest_sha256
                    ),
                    "p_database_contract_sha256": deployment.database_contract_sha256,
                    "p_database_target_fingerprint": (
                        deployment.database_target_fingerprint
                    ),
                    "p_provider_contract_sha256": deployment.provider_contract_sha256,
                    "p_deployment_id": deployment.deployment_id,
                    "p_commit_sha": deployment.commit_sha,
                    "p_host_configuration_ciphertext_sha256": (
                        deployment.host_configuration_ciphertext_sha256
                    ),
                    "p_root_key_id": deployment.root_key_id,
                    "p_release_preview_contract_sha256": (
                        deployment.release_preview_contract_sha256
                    ),
                    "p_release_preview_descriptor_matrix_sha256": (
                        deployment.release_preview_descriptor_matrix_sha256
                    ),
                    "p_release_preview_dedicated_account_attestation_sha256": (
                        deployment.release_preview_dedicated_account_attestation_sha256
                    ),
                    "p_release_preview_invocation_id": (
                        deployment.release_preview_invocation_id
                    ),
                    "p_release_preview_effect_manifest_sha256": (
                        deployment.release_preview_effect_manifest_sha256
                    ),
                },
                retry_transient=False,
            )
        except Exception:
            raise ConnectedReleasePreviewError() from None
        if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
            raise ConnectedReleasePreviewError()
        row = raw[0]
        expected = {
            "challenge_id",
            "composition_manifest_sha256",
            "database_contract_sha256",
            "database_target_fingerprint",
            "provider_contract_sha256",
            "deployment_id",
            "commit_sha",
            "host_configuration_ciphertext_sha256",
            "root_key_id",
            "release_preview_contract_sha256",
            "release_preview_descriptor_matrix_sha256",
            "release_preview_dedicated_account_attestation_sha256",
            "release_preview_invocation_id",
            "release_preview_effect_manifest_sha256",
            "challenge_issued_at",
            "challenge_expires_at",
        }
        if set(row) != expected:
            raise ConnectedReleasePreviewError()
        issued = _timestamp(row["challenge_issued_at"])
        expires = _timestamp(row["challenge_expires_at"])
        reference = _aware(self._now())
        if (
            row["composition_manifest_sha256"]
            != deployment.composition_manifest_sha256
            or row["database_contract_sha256"]
            != deployment.database_contract_sha256
            or row["database_target_fingerprint"]
            != deployment.database_target_fingerprint
            or row["provider_contract_sha256"]
            != deployment.provider_contract_sha256
            or row["deployment_id"] != deployment.deployment_id
            or row["commit_sha"] != deployment.commit_sha
            or row["host_configuration_ciphertext_sha256"]
            != deployment.host_configuration_ciphertext_sha256
            or row["root_key_id"] != deployment.root_key_id
            or row["release_preview_contract_sha256"]
            != deployment.release_preview_contract_sha256
            or row["release_preview_descriptor_matrix_sha256"]
            != deployment.release_preview_descriptor_matrix_sha256
            or row[
                "release_preview_dedicated_account_attestation_sha256"
            ]
            != deployment.release_preview_dedicated_account_attestation_sha256
            or row["release_preview_invocation_id"]
            != deployment.release_preview_invocation_id
            or row["release_preview_effect_manifest_sha256"]
            != deployment.release_preview_effect_manifest_sha256
            or expires <= issued
            or expires - issued > _MAX_PERMIT_LIFETIME
            or issued > reference + _FUTURE_SKEW
            or reference - issued > _MAX_DATABASE_RESPONSE_AGE
            or expires <= reference
        ):
            raise ConnectedReleasePreviewError()
        return ConnectedProviderSmokeChallenge(
            deployment=deployment,
            challenge_id=row["challenge_id"],
            issued_at=issued,
        )

    async def _record(
        self,
        *,
        challenge: ConnectedProviderSmokeChallenge,
        receipt_sha256: str,
    ) -> None:
        deployment = challenge.deployment
        try:
            raw = await self._database.rpc(
                "connected_app_record_provider_smoke_v1",
                {
                    "p_composition_manifest_sha256": (
                        deployment.composition_manifest_sha256
                    ),
                    "p_database_contract_sha256": deployment.database_contract_sha256,
                    "p_database_target_fingerprint": (
                        deployment.database_target_fingerprint
                    ),
                    "p_provider_contract_sha256": deployment.provider_contract_sha256,
                    "p_deployment_id": deployment.deployment_id,
                    "p_commit_sha": deployment.commit_sha,
                    "p_host_configuration_ciphertext_sha256": (
                        deployment.host_configuration_ciphertext_sha256
                    ),
                    "p_root_key_id": deployment.root_key_id,
                    "p_challenge_id": challenge.challenge_id,
                    "p_provider_smoke_attestation_sha256": receipt_sha256,
                    "p_release_preview_contract_sha256": (
                        deployment.release_preview_contract_sha256
                    ),
                    "p_release_preview_descriptor_matrix_sha256": (
                        deployment.release_preview_descriptor_matrix_sha256
                    ),
                    "p_release_preview_dedicated_account_attestation_sha256": (
                        deployment.release_preview_dedicated_account_attestation_sha256
                    ),
                    "p_release_preview_invocation_id": (
                        deployment.release_preview_invocation_id
                    ),
                    "p_release_preview_effect_manifest_sha256": (
                        deployment.release_preview_effect_manifest_sha256
                    ),
                },
                retry_transient=False,
            )
        except Exception:
            raise ConnectedReleasePreviewError() from None
        if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
            raise ConnectedReleasePreviewError()
        row = raw[0]
        if (
            set(row)
            != {
                "composition_manifest_sha256",
                "database_contract_sha256",
                "database_target_fingerprint",
                "provider_contract_sha256",
                "deployment_id",
                "commit_sha",
                "host_configuration_ciphertext_sha256",
                "root_key_id",
                "release_preview_contract_sha256",
                "release_preview_descriptor_matrix_sha256",
                "release_preview_dedicated_account_attestation_sha256",
                "release_preview_invocation_id",
                "release_preview_effect_manifest_sha256",
                "provider_smoke_checked_at",
            }
            or row["composition_manifest_sha256"]
            != deployment.composition_manifest_sha256
            or row["database_contract_sha256"]
            != deployment.database_contract_sha256
            or row["database_target_fingerprint"]
            != deployment.database_target_fingerprint
            or row["provider_contract_sha256"]
            != deployment.provider_contract_sha256
            or row["deployment_id"] != deployment.deployment_id
            or row["commit_sha"] != deployment.commit_sha
            or row["host_configuration_ciphertext_sha256"]
            != deployment.host_configuration_ciphertext_sha256
            or row["root_key_id"] != deployment.root_key_id
            or row["release_preview_contract_sha256"]
            != deployment.release_preview_contract_sha256
            or row["release_preview_descriptor_matrix_sha256"]
            != deployment.release_preview_descriptor_matrix_sha256
            or row[
                "release_preview_dedicated_account_attestation_sha256"
            ]
            != deployment.release_preview_dedicated_account_attestation_sha256
            or row["release_preview_invocation_id"]
            != deployment.release_preview_invocation_id
            or row["release_preview_effect_manifest_sha256"]
            != deployment.release_preview_effect_manifest_sha256
        ):
            raise ConnectedReleasePreviewError()
        checked = _timestamp(row["provider_smoke_checked_at"])
        reference = _aware(self._now())
        if (
            checked < challenge.issued_at
            or checked > reference + _FUTURE_SKEW
            or reference - checked > _MAX_DATABASE_RESPONSE_AGE
        ):
            raise ConnectedReleasePreviewError()

    @staticmethod
    async def _terminalize_failed_provider_matrix(
        *,
        invocation_id: str,
        effect_ledger: ConnectedReleasePreviewEffectLedger,
        provider_probes: Mapping[
            ConnectorProvider,
            Mapping[
                ConnectorAccountKind,
                ConnectedGoogleReleasePreviewProbe
                | ConnectedMicrosoftReleasePreviewProbe,
            ],
        ],
    ) -> None:
        """Retire every safe group, then atomically terminalize the failure."""

        if (
            type(effect_ledger) is not ConnectedReleasePreviewEffectLedger
            or effect_ledger.invocation_id != invocation_id
            or set(provider_probes) != set(ConnectorProvider)
        ):
            raise ConnectedReleasePreviewError()
        cleanup_failed = False
        groups = 0
        for provider in ConnectorProvider:
            account_probes = provider_probes[provider]
            for account_kind, probe in account_probes.items():
                groups += 1
                if (
                    not isinstance(account_kind, ConnectorAccountKind)
                    or (
                        provider is ConnectorProvider.GOOGLE
                        and type(probe) is not ConnectedGoogleReleasePreviewProbe
                    )
                    or (
                        provider is ConnectorProvider.MICROSOFT
                        and type(probe) is not ConnectedMicrosoftReleasePreviewProbe
                    )
                ):
                    cleanup_failed = True
                    continue
                try:
                    await probe.abort_unstarted_or_revoked(
                        invocation_id=invocation_id,
                        effect_ledger=effect_ledger,
                    )
                except Exception:
                    # Continue sweeping later unstarted groups. The failed
                    # group retains its exact cleanup authority for recovery.
                    cleanup_failed = True
        if groups != 3:
            raise ConnectedReleasePreviewError()
        try:
            await effect_ledger.fail()
        except Exception:
            raise ConnectedReleasePreviewError() from None
        if cleanup_failed:
            # A sweep read/transition may lose its response after every
            # required retirement committed. The fail RPC is the final
            # authoritative, atomic readback and is allowed to settle that
            # exact case (including just after the 15-minute lease expires).
            return

    async def run(
        self,
        *,
        permit: ConnectedReleasePreviewPermit,
        assertion: ConnectedVercelOIDCAssertion,
        expected_manifest_sha256: str,
    ) -> ConnectedReleasePreviewResult:
        reference = _aware(self._now())
        if (
            config.connected_apps_release_candidate_source_released() is not True
            or type(permit) is not ConnectedReleasePreviewPermit
            or type(assertion) is not ConnectedVercelOIDCAssertion
            or not _SHA256.fullmatch(str(expected_manifest_sha256 or ""))
            or expected_manifest_sha256
            != config.CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256
            or self._database_target_fingerprint
            != config.CONNECTED_APPS_DATABASE_TARGET_FINGERPRINT
            # Recheck the sealed boundary at action time so a mutated harness
            # cannot consume its permit or reach KMS/database I/O.
            or not _database_production_eligible(self._database)
            or not _root_loader_source_eligible(
                self._root_loader,
                expected_manifest_sha256=expected_manifest_sha256,
            )
            or not _gateway_factory_static_eligible(
                self._ai_gateway_factory,
                database=self._database,
            )
            or type(self._gateway_probe) is not ConnectedAIGatewayReleaseProbe
            or type(self._runtime_identity)
            is not ConnectedVercelProductionRuntimeIdentity
        ):
            raise ConnectedReleasePreviewError()
        await permit.claim(now=reference)

        root: ConnectedRootKeyMaterial | None = None
        keyset: ConnectedDerivedKeyset | None = None
        keys: ConnectedProductionKeys | None = None
        host: object | None = None
        gateway: object | None = None
        identity: ConnectedVercelProductionIdentity | None = None
        effect_ledger: ConnectedReleasePreviewEffectLedger | None = None
        provider_probes: Mapping[
            ConnectorProvider,
            Mapping[
                ConnectorAccountKind,
                ConnectedGoogleReleasePreviewProbe
                | ConnectedMicrosoftReleasePreviewProbe,
            ],
        ] | None = None
        provider_matrix_started = False
        effects_finalized = False
        try:
            root = await self._root_loader.load(assertion=assertion)
            if (
                type(root) is not ConnectedRootKeyMaterial
                or root.custody is not ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS
                or not _ROOT_KEY_ID.fullmatch(root.key_id)
                or root.key_id != config.CONNECTED_APPS_KMS_ROOT_KEY_ID
                or root.attestation_sha256
                != config.CONNECTED_APPS_KMS_CUSTODY_ATTESTATION_SHA256
                or config.CONNECTED_APPS_KMS_PROTECTION_LEVEL != "HSM"
                or root.loaded_at < permit.issued_at - _FUTURE_SKEW
                or root.loaded_at > _aware(self._now()) + _FUTURE_SKEW
            ):
                raise ConnectedReleasePreviewError()
            identity = self._runtime_identity.attest(
                assertion=assertion,
                kms_root=root,
            )
            if (
                not _root_loader_source_eligible(
                    self._root_loader,
                    expected_manifest_sha256=expected_manifest_sha256,
                )
                or not _database_production_eligible(self._database)
                or not _gateway_factory_runtime_eligible(
                    self._ai_gateway_factory,
                    database=self._database,
                    identity=identity,
                )
            ):
                raise ConnectedReleasePreviewError()
            keyset = ConnectedDerivedKeyset(
                root=root,
                composition_manifest_sha256=expected_manifest_sha256,
                now=self._now,
            )
            keys = ConnectedProductionKeys.build(keyset, now=self._now)
            host = self._ciphertext.open(
                key=keys.host_configuration,
                composition_manifest_sha256=expected_manifest_sha256,
            )
            descriptor_matrix_sha256 = (
                host.release_preview_descriptor_matrix_sha256  # type: ignore[attr-defined]
            )
            dedicated_account_attestation_sha256 = (
                host.release_preview_dedicated_account_attestation_sha256  # type: ignore[attr-defined]
            )
            if (
                not isinstance(descriptor_matrix_sha256, str)
                or _SHA256.fullmatch(descriptor_matrix_sha256) is None
                or not isinstance(dedicated_account_attestation_sha256, str)
                or _SHA256.fullmatch(dedicated_account_attestation_sha256)
                is None
            ):
                raise ConnectedReleasePreviewError()
            await self._verify_dedicated_account_attestation(
                host=host,
                descriptor_matrix_sha256=descriptor_matrix_sha256,
                attestation_sha256=dedicated_account_attestation_sha256,
            )

            # Fail the content-free gateway proof before touching provider
            # accounts. A gateway failure can then be retried without having
            # retired the one-shot dedicated OAuth authorities.
            gateway = self._ai_gateway_factory.build(assertion=assertion)
            if (
                type(gateway) is not ConnectedRequestScopedAIGateway
                or gateway._database is not self._database
                or gateway._model != "openai/gpt-oss-20b"
                or gateway._provider != "groq"
                or gateway._deployment_id != identity.deployment_id
                or gateway._commit_sha != identity.commit_sha
                or gateway._transport is not None
            ):
                raise ConnectedReleasePreviewError()
            gateway_receipt = await self._gateway_probe.preview(
                gateway=gateway,
                invocation_id=permit.invocation_id,
                contract_sha256=CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256,
            )
            if (
                type(gateway_receipt) is not ConnectedGatewayReleasePreviewReceipt
                or gateway_receipt.invocation_id != permit.invocation_id
                or gateway_receipt.checked_at < permit.issued_at
            ):
                raise ConnectedReleasePreviewError()
            self._fresh(gateway_receipt.checked_at, reference=_aware(self._now()))

            google_account_kinds = tuple(
                host.release_preview_connections[  # type: ignore[attr-defined]
                    ConnectorProvider.GOOGLE
                ]
            )
            if len(google_account_kinds) != 1:
                raise ConnectedReleasePreviewError()
            effect_ledger = ConnectedReleasePreviewEffectLedger(
                database=self._database,
                invocation_id=permit.invocation_id,
            )
            effect_manifest_sha256 = await effect_ledger.begin(
                google_account_kind=google_account_kinds[0],
                descriptor_matrix_sha256=descriptor_matrix_sha256,
                dedicated_account_attestation_sha256=(
                    dedicated_account_attestation_sha256
                ),
                deployment={
                    "composition_manifest_sha256": expected_manifest_sha256,
                    "database_contract_sha256": CONNECTED_DATABASE_CONTRACT_SHA256,
                    "database_target_fingerprint": (
                        self._database_target_fingerprint
                    ),
                    "provider_contract_sha256": CONNECTED_PROVIDER_CONTRACT_SHA256,
                    "deployment_id": identity.deployment_id,
                    "commit_sha": identity.commit_sha,
                    "host_configuration_ciphertext_sha256": (
                        self._host_configuration_ciphertext_sha256
                    ),
                    "root_key_id": keys.root_key_id,
                },
                release_preview_contract_sha256=(
                    CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
                ),
            )

            redirects = {
                ConnectorProvider.GOOGLE: _GOOGLE_REDIRECT,
                ConnectorProvider.MICROSOFT: _MICROSOFT_REDIRECT,
            }
            provider_probes = build_connected_release_preview_provider_probes(
                database=self._database,
                credential_key=keys.credential_envelope,
                registrations=host.registrations,  # type: ignore[attr-defined]
                descriptors=host.release_preview_connections,  # type: ignore[attr-defined]
                contract_sha256=CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256,
                now=self._now,
            )
            provider_matrix_started = True
            for provider in ConnectorProvider:
                registration = host.registrations[provider]  # type: ignore[attr-defined]
                account_probes = provider_probes[provider]
                if (
                    (
                        provider is ConnectorProvider.GOOGLE
                        and len(account_probes) != 1
                    )
                    or (
                        provider is ConnectorProvider.MICROSOFT
                        and set(account_probes) != set(ConnectorAccountKind)
                    )
                ):
                    raise ConnectedReleasePreviewError()
                for account_kind, probe in account_probes.items():
                    if (
                        not isinstance(account_kind, ConnectorAccountKind)
                        or (
                            provider is ConnectorProvider.GOOGLE
                            and type(probe)
                            is not ConnectedGoogleReleasePreviewProbe
                        )
                        or (
                            provider is ConnectorProvider.MICROSOFT
                            and type(probe)
                            is not ConnectedMicrosoftReleasePreviewProbe
                        )
                        or probe.production_eligible(
                            database=self._database,
                            registration=registration,
                        )
                        is not True
                    ):
                        raise ConnectedReleasePreviewError()
                    for resource in (
                        ConnectorResource.MAIL,
                        ConnectorResource.CALENDAR,
                    ):
                        state = await effect_ledger.state_for(
                            provider=provider,
                            account_kind=account_kind,
                            resource=resource,
                        )
                        if state.phase is ConnectedReleasePreviewEffectPhase.PENDING:
                            await effect_ledger.transition(
                                state=state,
                                next_phase=(
                                    ConnectedReleasePreviewEffectPhase.DISPATCHED
                                ),
                            )
                        elif state.phase not in {
                            ConnectedReleasePreviewEffectPhase.DISPATCHED,
                            ConnectedReleasePreviewEffectPhase.OBSERVED,
                            ConnectedReleasePreviewEffectPhase.CLEANUP,
                            ConnectedReleasePreviewEffectPhase.CLEAN,
                            ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT,
                        }:
                            # The same invocation may resume only from an
                            # exact durable marker.  Unknown effects never
                            # dispatch again and cannot mint readiness.
                            raise ConnectedReleasePreviewError()
                    receipt = await probe.preview(
                        registration=registration,
                        redirect_uri=redirects[provider],
                        invocation_id=permit.invocation_id,
                        contract_sha256=CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256,
                        effect_ledger=effect_ledger,
                    )
                    if (
                        type(receipt)
                        is not ConnectedProviderReleasePreviewReceipt
                        or receipt.provider is not provider
                        or receipt.account_kind is not account_kind
                        or receipt.invocation_id != permit.invocation_id
                        or receipt.checked_at < permit.issued_at
                        or receipt.contract_sha256
                        != CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
                        or receipt.dedicated_account_binding_attested is not True
                        or receipt.oauth_callback_attested is not True
                        or receipt.mail_read_attested is not True
                        or receipt.mail_preview_write_attested is not True
                        or receipt.mail_send_attested is not True
                        or receipt.mail_reply_attested is not True
                        or receipt.calendar_read_attested is not True
                        or (
                            provider is ConnectorProvider.GOOGLE
                            and (
                                receipt.calendar_free_busy_attested is not True
                                or receipt.calendar_free_busy_exempt is not False
                            )
                        )
                        or (
                            provider is ConnectorProvider.MICROSOFT
                            and account_kind is ConnectorAccountKind.WORK_SCHOOL
                            and (
                                receipt.calendar_free_busy_attested is not True
                                or receipt.calendar_free_busy_exempt is not False
                            )
                        )
                        or (
                            provider is ConnectorProvider.MICROSOFT
                            and account_kind is ConnectorAccountKind.PERSONAL
                            and (
                                receipt.calendar_free_busy_attested is not False
                                or receipt.calendar_free_busy_exempt is not True
                            )
                        )
                        or receipt.calendar_preview_write_attested is not True
                        or receipt.cleanup_attested is not True
                        or receipt.local_connection_retirement_attested is not True
                        or receipt.local_credential_erasure_attested is not True
                        or (
                            provider is ConnectorProvider.GOOGLE
                            and (
                                receipt.provider_grant_revocation_attested
                                is not True
                                or receipt.revocation_mode
                                != "provider_grant_and_local_retirement"
                            )
                        )
                        or (
                            provider is ConnectorProvider.MICROSOFT
                            and (
                                receipt.provider_grant_revocation_attested
                                is not False
                                or receipt.revocation_mode
                                != "local_credential_and_connection_retirement"
                            )
                        )
                    ):
                        raise ConnectedReleasePreviewError()
                    self._fresh(
                        receipt.checked_at,
                        reference=_aware(self._now()),
                    )
                    observed_states = {}
                    for resource in (
                        ConnectorResource.MAIL,
                        ConnectorResource.CALENDAR,
                    ):
                        observed_states[resource] = await effect_ledger.state_for(
                            provider=provider,
                            account_kind=account_kind,
                            resource=resource,
                        )
                    if (
                        observed_states[ConnectorResource.MAIL].phase
                        is not ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                        or observed_states[ConnectorResource.MAIL].artifact_id_sha256
                        != receipt.mail_retained_test_artifact_sha256
                        or observed_states[ConnectorResource.CALENDAR].phase
                        is not ConnectedReleasePreviewEffectPhase.CLEAN
                        or observed_states[
                            ConnectorResource.CALENDAR
                        ].artifact_id_sha256
                        != receipt.calendar_cleanup_artifact_sha256
                    ):
                        raise ConnectedReleasePreviewError()

            await effect_ledger.finalize()
            effects_finalized = True
            keyset.require_current(now=_aware(self._now()))

            deployment = ConnectedProviderSmokeDeployment(
                composition_manifest_sha256=expected_manifest_sha256,
                database_contract_sha256=CONNECTED_DATABASE_CONTRACT_SHA256,
                database_target_fingerprint=self._database_target_fingerprint,
                provider_contract_sha256=CONNECTED_PROVIDER_CONTRACT_SHA256,
                deployment_id=identity.deployment_id,
                commit_sha=identity.commit_sha,
                host_configuration_ciphertext_sha256=(
                    self._host_configuration_ciphertext_sha256
                ),
                root_key_id=keys.root_key_id,
                release_preview_contract_sha256=(
                    CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
                ),
                release_preview_descriptor_matrix_sha256=(
                    descriptor_matrix_sha256
                ),
                release_preview_dedicated_account_attestation_sha256=(
                    dedicated_account_attestation_sha256
                ),
                release_preview_invocation_id=permit.invocation_id,
                release_preview_effect_manifest_sha256=(
                    effect_manifest_sha256
                ),
            )
            challenge = await self._issue_challenge(deployment=deployment)
            keyset.require_current(now=_aware(self._now()))
            receipt_sha256 = ConnectedProviderSmokeAttestor(
                keys.readiness_attestation
            ).sign(challenge)
            try:
                await self._record(
                    challenge=challenge,
                    receipt_sha256=receipt_sha256,
                )
            except ConnectedReleasePreviewError:
                # The record RPC is a one-use write. A response loss or a
                # malformed success body is ambiguous and must never trigger
                # a blind retry. The exact live readback below accepts only
                # this challenge's KMS-HMAC, so an older receipt for the same
                # deployment tuple cannot turn an uncertain record into a
                # false success.
                pass
            keyset.require_current(now=_aware(self._now()))
            readiness = await SupabaseConnectedProductionReadinessProbe(
                self._database,
                database_target_fingerprint=self._database_target_fingerprint,
                deployment_id=identity.deployment_id,
                commit_sha=identity.commit_sha,
                host_configuration_ciphertext_sha256=(
                    self._host_configuration_ciphertext_sha256
                ),
                now=self._now,
            ).attest(
                keys=keys,
                expected_manifest_sha256=expected_manifest_sha256,
                minimum_expires_at=keys.expires_at,
                expected_provider_smoke_attestation_sha256=receipt_sha256,
            )
            keyset.require_current(now=_aware(self._now()))
            return ConnectedReleasePreviewResult(
                invocation_id=permit.invocation_id,
                composition_manifest_sha256=expected_manifest_sha256,
                database_contract_sha256=CONNECTED_DATABASE_CONTRACT_SHA256,
                database_target_fingerprint=self._database_target_fingerprint,
                provider_contract_sha256=CONNECTED_PROVIDER_CONTRACT_SHA256,
                release_preview_contract_sha256=(
                    CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
                ),
                deployment_id=identity.deployment_id,
                commit_sha=identity.commit_sha,
                host_configuration_ciphertext_sha256=(
                    self._host_configuration_ciphertext_sha256
                ),
                root_key_id=keys.root_key_id,
                provider_smoke_attestation_sha256=receipt_sha256,
                checked_at=readiness.checked_at,
                expires_at=readiness.expires_at,
            )
        except Exception as exc:
            if (
                provider_matrix_started
                and not effects_finalized
                and effect_ledger is not None
                and provider_probes is not None
            ):
                try:
                    await self._terminalize_failed_provider_matrix(
                        invocation_id=permit.invocation_id,
                        effect_ledger=effect_ledger,
                        provider_probes=provider_probes,
                    )
                except Exception:
                    # A group with an unsettled external effect retains its
                    # exact durable marker and credential authority for the
                    # same-invocation recovery lease. It is never retired or
                    # mislabeled clean merely to make this request terminal.
                    pass
            if isinstance(exc, ConnectedReleasePreviewError):
                raise
            raise ConnectedReleasePreviewError() from None
        finally:
            # Python cannot promise an in-place wipe of immutable bytes. Drop
            # every local reference; the mandatory dedicated-process exit is
            # the actual plaintext-root and derived-key destruction boundary.
            gateway = None
            host = None
            keys = None
            keyset = None
            root = None
            identity = None

    def __repr__(self) -> str:
        return "ConnectedReleasePreviewHarness(network='source-locked')"

    def __getstate__(self) -> object:
        raise TypeError("connected release-preview harnesses cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected release-preview harnesses cannot be serialized")


__all__ = [
    "CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256",
    "ConnectedAIGatewayReleaseProbe",
    "ConnectedGatewayReleasePreviewReceipt",
    "ConnectedGoogleReleasePreviewProbe",
    "ConnectedMicrosoftReleasePreviewProbe",
    "ConnectedProviderReleasePreviewReceipt",
    "ConnectedReleasePreviewError",
    "ConnectedReleasePreviewHarness",
    "ConnectedReleasePreviewPermit",
    "ConnectedReleasePreviewResult",
]
