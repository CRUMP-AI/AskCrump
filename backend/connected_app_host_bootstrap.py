"""Secure Vercel host boundary for the connected operator.

The checked-in source lock and the operator switch are evaluated before this
module reads any connected-operator deployment setting.  Once released, the
only accepted long-lived deployment values are non-secret KMS/WIF identifiers
and ciphertexts.  The Vercel assertion itself is read later from the current
request's ``x-vercel-oidc-token`` header by request activation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Mapping, Protocol

from . import config
from .connected_app_composition import ConnectedProductionReadiness
from .connected_app_host_configuration import ConnectedEncryptedHostConfiguration
from .connected_app_key_derivation import ConnectedKeyCustodyKind
from .connected_app_kms import (
    ConnectedGoogleKMSConfiguration,
    ConnectedGoogleKMSRootLoader,
    ConnectedVercelOIDCAssertion,
)
from .connected_app_oauth import OAuthRedirectAllowlist
from .connected_app_policy import ConnectorProvider
from .connected_app_production_keys import ConnectedProductionKeys
from .connected_app_readiness_attestation import (
    ConnectedProviderSmokeAttestor,
    ConnectedProviderSmokeChallenge,
    ConnectedProviderSmokeDeployment,
)
from .connected_app_release_contract import (
    CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256,
)
from .connected_app_request_ai_gateway import ConnectedRequestScopedAIGatewayFactory

if TYPE_CHECKING:
    from .connected_app_production import ConnectedProductionGraphInputs
    from .connected_app_request_activation import ConnectedRequestActivationCoordinator


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{32}$")
_DEPLOYMENT = re.compile(r"^dpl_[A-Za-z0-9]{8,}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ROOT_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$")
_READINESS_RPC = "connected_app_runtime_readiness_v1"
_MAX_ENV_VALUE = 65_536
_FUTURE_SKEW = timedelta(seconds=5)
_MAX_READINESS_AGE = timedelta(seconds=60)
_MAX_READINESS_LIFETIME = timedelta(minutes=15)
_AI_GATEWAY_MODEL = "openai/gpt-oss-20b"
_AI_GATEWAY_PROVIDER = "groq"
_PRODUCTION_REDIRECT_URIS = MappingProxyType(
    {
        ConnectorProvider.GOOGLE: (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
        ),
        ConnectorProvider.MICROSOFT: (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
        ),
    }
)

# These are source identities, not operator-provided booleans.  The reviewed
# service-role readiness RPC must independently return both exact hashes after
# inspecting the live catalog and the durable KMS-HMAC receipt from the last
# bounded authenticated deployment preview.  A missing RPC, invalid receipt,
# expired runtime lease, or mismatched stack fails closed.
_DATABASE_CONTRACT_DOCUMENT = {
    "version": "askcrump-connected-database-contract-v1",
    "ordered_migrations": [
        "20261107190000",
        "20261107230000",
        "20261107231500",
        "20261107233000",
        "20261108020000",
        "20261108023000",
        "20261108040000",
        "20261108043000",
        "20261108050000",
        "20261108052000",
        "20261108054000",
        "20261108058000",
        "20261108061000",
        "20261108062000",
        "20261108063000",
        "20261108064000",
        "20261108065000",
        "20261108066000",
        "20261108067000",
        "20261108068000",
        "20261108068500",
        "20261108068600",
        "20261108068700",
        "20261108068800",
        "20261108068900",
        "20261108069000",
        "20261108069100",
    ],
    "readiness_rpc": _READINESS_RPC,
    "authority": "service_role_only_security_definer_empty_search_path",
    "required_invariants": [
        "owner_isolation",
        "encrypted_payload_and_credential_custody",
        "one_use_action_claims",
        "effect_unknown_fencing",
        "cross_host_refresh_serialization",
        "deletion_cleanup",
        "bounded_ciphertext_retention_purge",
        "schedule_and_multi_step_recovery",
        "calendar_cancel_snapshot_authority",
        "oauth_callback_owner_session_binding",
        "oauth_code_encrypted_one_use_custody",
        "unique_active_provider_account_kind_connection",
        "durable_release_preview_effect_recovery",
        "atomic_one_use_approval_consumption_and_effect_start",
    ],
}
CONNECTED_DATABASE_CONTRACT_SHA256 = hashlib.sha256(
    json.dumps(
        _DATABASE_CONTRACT_DOCUMENT,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

_PROVIDER_CONTRACT_DOCUMENT = {
    "version": "askcrump-connected-provider-contract-v1",
    "providers": ["google", "microsoft"],
    "resources": ["mail", "calendar"],
    "authorization": "oauth2_pkce_incremental_exact_scope",
    "transport": "https_no_redirect_no_ambient_proxy_bounded_response",
    "writes": "exact_preview_fresh_approval_idempotent_receipt",
    "calendar_cancel": "provider_get_snapshot_then_version_bound_cancel",
    "readiness": "kms_hmac_one_use_challenge_exact_deployment_tuple",
    "planning_gateway": {
        "model": _AI_GATEWAY_MODEL,
        "provider": _AI_GATEWAY_PROVIDER,
        "authentication": "current_vercel_request_oidc",
        "retention": "zero_data_retention_and_no_prompt_training",
    },
}
CONNECTED_PROVIDER_CONTRACT_SHA256 = hashlib.sha256(
    json.dumps(
        _PROVIDER_CONTRACT_DOCUMENT,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


class ConnectedHostBootstrapError(RuntimeError):
    """Content-free host failure safe for deployment logs and 503 paths."""

    _CODES = frozenset(
        {
            "CONNECTED_HOST_BOOTSTRAP_INVALID",
            "CONNECTED_HOST_BOOTSTRAP_NOT_READY",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = code if code in self._CODES else "CONNECTED_HOST_BOOTSTRAP_NOT_READY"
        super().__init__(self.code)


class ConnectedHostRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


class ConnectedHostAIGatewayFactory(Protocol):
    def build(self, *, assertion: ConnectedVercelOIDCAssertion) -> object: ...


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY")
    return value.astimezone(UTC)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY") from None
    return _aware(parsed)


class SupabaseConnectedProductionReadinessProbe:
    """Obtain a fresh catalog lease backed by one durable KMS-HMAC smoke."""

    __slots__ = (
        "_database",
        "_database_target_fingerprint",
        "_deployment_id",
        "_commit_sha",
        "_host_configuration_ciphertext_sha256",
        "_now",
    )

    def __init__(
        self,
        database: ConnectedHostRPC,
        *,
        database_target_fingerprint: str,
        deployment_id: str,
        commit_sha: str,
        host_configuration_ciphertext_sha256: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            not callable(getattr(database, "rpc", None))
            or not _FINGERPRINT.fullmatch(str(database_target_fingerprint or ""))
            or not _DEPLOYMENT.fullmatch(str(deployment_id or ""))
            or not _COMMIT.fullmatch(str(commit_sha or ""))
            or not _SHA256.fullmatch(str(host_configuration_ciphertext_sha256 or ""))
            or not callable(now)
        ):
            raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_INVALID")
        self._database = database
        self._database_target_fingerprint = database_target_fingerprint
        self._deployment_id = deployment_id
        self._commit_sha = commit_sha
        self._host_configuration_ciphertext_sha256 = (
            host_configuration_ciphertext_sha256
        )
        self._now = now

    async def attest(
        self,
        *,
        keys: ConnectedProductionKeys,
        expected_manifest_sha256: str,
        minimum_expires_at: datetime,
        expected_provider_smoke_attestation_sha256: str | None = None,
    ) -> ConnectedProductionReadiness:
        if (
            type(keys) is not ConnectedProductionKeys
            or not _SHA256.fullmatch(expected_manifest_sha256)
            or keys.composition_manifest_sha256 != expected_manifest_sha256
            or (
                expected_provider_smoke_attestation_sha256 is not None
                and (
                    not isinstance(
                        expected_provider_smoke_attestation_sha256,
                        str,
                    )
                    or not _SHA256.fullmatch(
                        expected_provider_smoke_attestation_sha256
                    )
                )
            )
        ):
            raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_INVALID")
        minimum = _aware(minimum_expires_at)
        reference = _aware(self._now())
        try:
            raw = await self._database.rpc(
                _READINESS_RPC,
                {
                    "p_expected_manifest_sha256": expected_manifest_sha256,
                    "p_expected_database_contract_sha256": (
                        CONNECTED_DATABASE_CONTRACT_SHA256
                    ),
                    "p_expected_database_target_fingerprint": (
                        self._database_target_fingerprint
                    ),
                    "p_expected_provider_contract_sha256": (
                        CONNECTED_PROVIDER_CONTRACT_SHA256
                    ),
                    "p_expected_deployment_id": self._deployment_id,
                    "p_expected_commit_sha": self._commit_sha,
                    "p_expected_host_configuration_ciphertext_sha256": (
                        self._host_configuration_ciphertext_sha256
                    ),
                    "p_expected_root_key_id": keys.root_key_id,
                    "p_expected_release_preview_contract_sha256": (
                        CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
                    ),
                },
                retry_transient=False,
            )
        except Exception:
            raise ConnectedHostBootstrapError(
                "CONNECTED_HOST_BOOTSTRAP_NOT_READY"
            ) from None
        if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
            raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY")
        row = raw[0]
        if set(row) != {
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
            "checked_at",
            "expires_at",
            "provider_smoke_checked_at",
            "provider_smoke_challenge_id",
            "provider_smoke_challenge_issued_at",
            "provider_smoke_attestation_sha256",
        }:
            raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY")
        checked = _timestamp(row.get("checked_at"))
        expires = _timestamp(row.get("expires_at"))
        provider_smoke_checked = _timestamp(row.get("provider_smoke_checked_at"))
        challenge_issued = _timestamp(
            row.get("provider_smoke_challenge_issued_at")
        )
        if (
            row.get("composition_manifest_sha256") != expected_manifest_sha256
            or row.get("database_contract_sha256")
            != CONNECTED_DATABASE_CONTRACT_SHA256
            or row.get("database_target_fingerprint")
            != self._database_target_fingerprint
            or row.get("provider_contract_sha256")
            != CONNECTED_PROVIDER_CONTRACT_SHA256
            or row.get("deployment_id") != self._deployment_id
            or row.get("commit_sha") != self._commit_sha
            or row.get("host_configuration_ciphertext_sha256")
            != self._host_configuration_ciphertext_sha256
            or row.get("root_key_id") != keys.root_key_id
            or row.get("release_preview_contract_sha256")
            != CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
            or not isinstance(row.get("provider_smoke_attestation_sha256"), str)
            or not _SHA256.fullmatch(row["provider_smoke_attestation_sha256"])
            or (
                expected_provider_smoke_attestation_sha256 is not None
                and row["provider_smoke_attestation_sha256"]
                != expected_provider_smoke_attestation_sha256
            )
            or checked > reference + _FUTURE_SKEW
            or reference - checked > _MAX_READINESS_AGE
            or expires <= reference
            or expires <= checked
            or expires < minimum
            or expires - checked > _MAX_READINESS_LIFETIME
            or provider_smoke_checked > reference + _FUTURE_SKEW
            or challenge_issued > reference + _FUTURE_SKEW
            or provider_smoke_checked < challenge_issued
            or provider_smoke_checked > checked + _FUTURE_SKEW
            or challenge_issued > checked + _FUTURE_SKEW
        ):
            raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY")
        try:
            deployment = ConnectedProviderSmokeDeployment(
                composition_manifest_sha256=expected_manifest_sha256,
                database_contract_sha256=CONNECTED_DATABASE_CONTRACT_SHA256,
                database_target_fingerprint=self._database_target_fingerprint,
                provider_contract_sha256=CONNECTED_PROVIDER_CONTRACT_SHA256,
                deployment_id=self._deployment_id,
                commit_sha=self._commit_sha,
                host_configuration_ciphertext_sha256=(
                    self._host_configuration_ciphertext_sha256
                ),
                root_key_id=keys.root_key_id,
                release_preview_contract_sha256=(
                    row.get("release_preview_contract_sha256")
                ),
                release_preview_descriptor_matrix_sha256=(
                    row.get("release_preview_descriptor_matrix_sha256")
                ),
                release_preview_dedicated_account_attestation_sha256=(
                    row.get(
                        "release_preview_dedicated_account_attestation_sha256"
                    )
                ),
                release_preview_invocation_id=row.get(
                    "release_preview_invocation_id"
                ),
                release_preview_effect_manifest_sha256=row.get(
                    "release_preview_effect_manifest_sha256"
                ),
            )
            challenge = ConnectedProviderSmokeChallenge(
                deployment=deployment,
                challenge_id=row.get("provider_smoke_challenge_id"),
                issued_at=challenge_issued,
            )
            if not ConnectedProviderSmokeAttestor(
                keys.readiness_attestation
            ).verify(challenge, row["provider_smoke_attestation_sha256"]):
                raise ConnectedHostBootstrapError(
                    "CONNECTED_HOST_BOOTSTRAP_NOT_READY"
                )
        except ConnectedHostBootstrapError:
            raise
        except Exception:
            raise ConnectedHostBootstrapError(
                "CONNECTED_HOST_BOOTSTRAP_NOT_READY"
            ) from None
        return ConnectedProductionReadiness(
            composition_manifest_sha256=expected_manifest_sha256,
            checked_at=checked,
            expires_at=expires,
            durable_control_plane=True,
            durable_payload_vault=True,
            payload_binding_contract_attested=True,
            durable_credential_vault=True,
            trusted_key_manager=True,
            cross_host_refresh_serialization=True,
            oauth_registrations_attested=True,
            provider_contracts_attested=True,
            provider_smoke_attested=True,
            scheduler_store_attested=True,
            deletion_cleanup_attested=True,
            no_browser_fallback_attested=True,
        )

    def __repr__(self) -> str:
        return (
            "SupabaseConnectedProductionReadinessProbe("
            "authority='live-rpc+kms-hmac')"
        )


class ConnectedProductionGraphInputsBuilder:
    """Open exact registrations and compose inputs only after KMS derivation."""

    __slots__ = (
        "_ciphertext",
        "_database",
        "_ai_gateway_factory",
        "_readiness",
        "_now",
    )

    def __init__(
        self,
        *,
        ciphertext: ConnectedEncryptedHostConfiguration,
        database: ConnectedHostRPC,
        ai_gateway_factory: ConnectedHostAIGatewayFactory,
        readiness: SupabaseConnectedProductionReadinessProbe,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            type(ciphertext) is not ConnectedEncryptedHostConfiguration
            or not callable(getattr(database, "rpc", None))
            or not callable(getattr(ai_gateway_factory, "build", None))
            or type(readiness) is not SupabaseConnectedProductionReadinessProbe
            or not callable(now)
        ):
            raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_INVALID")
        self._ciphertext = ciphertext
        self._database = database
        self._ai_gateway_factory = ai_gateway_factory
        self._readiness = readiness
        self._now = now

    async def build(
        self,
        *,
        keys: ConnectedProductionKeys,
        expected_manifest_sha256: str,
        assertion: ConnectedVercelOIDCAssertion,
    ) -> ConnectedProductionGraphInputs:
        if (
            type(keys) is not ConnectedProductionKeys
            or type(assertion) is not ConnectedVercelOIDCAssertion
            or keys.composition_manifest_sha256 != expected_manifest_sha256
            or not _SHA256.fullmatch(expected_manifest_sha256)
            or _aware(keys.expires_at) <= _aware(self._now())
        ):
            raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY")
        try:
            from .connected_app_production import ConnectedProductionGraphInputs

            attestation = await self._readiness.attest(
                keys=keys,
                expected_manifest_sha256=expected_manifest_sha256,
                minimum_expires_at=keys.expires_at,
            )
            # Keep the provider registrations encrypted until the live catalog
            # and durable KMS-HMAC deployment receipt have both passed.  A
            # missing/drifted readiness contract therefore never causes the
            # long-lived OAuth client secrets to be opened as a side effect.
            host = self._ciphertext.open(
                key=keys.host_configuration,
                composition_manifest_sha256=expected_manifest_sha256,
            )
            ai_gateway = self._ai_gateway_factory.build(assertion=assertion)
            if not callable(getattr(ai_gateway, "gateway_text", None)):
                raise ConnectedHostBootstrapError(
                    "CONNECTED_HOST_BOOTSTRAP_NOT_READY"
                )
            redirects = dict(_PRODUCTION_REDIRECT_URIS)
            return ConnectedProductionGraphInputs(
                database=self._database,
                readiness_source=lambda: attestation,
                keys=keys,
                key_custody=ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS,
                registrations=host.registrations,
                redirect_allowlists={
                    provider: OAuthRedirectAllowlist(
                        frozenset({redirects[provider]})
                    )
                    for provider in ConnectorProvider
                },
                redirect_uris=redirects,
                ai_gateway=ai_gateway,
                oauth_transports={provider: None for provider in ConnectorProvider},
                provider_transports={provider: None for provider in ConnectorProvider},
                google_revocation_transport=None,
            )
        except ConnectedHostBootstrapError:
            raise
        except Exception:
            raise ConnectedHostBootstrapError(
                "CONNECTED_HOST_BOOTSTRAP_NOT_READY"
            ) from None

    def __repr__(self) -> str:
        return "ConnectedProductionGraphInputsBuilder(config='<encrypted>')"

    def __getstate__(self) -> object:
        raise TypeError("connected graph-input builders cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected graph-input builders cannot be serialized")


def _required(environment: Mapping[str, str], name: str) -> str:
    try:
        value = environment[name]
    except (KeyError, TypeError):
        raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY") from None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_ENV_VALUE
        or value != value.strip()
        or "\x00" in value
    ):
        raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY")
    return value


def configure_connected_production_host(
    *,
    environment: Mapping[str, str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ConnectedRequestActivationCoordinator | None:
    """Install request activation, reading deployment ciphertext only if released."""

    # Deliberately return before importing process services or touching the
    # environment.  This is the lock-false guarantee used by every deployment.
    if config.connected_apps_release_candidate_source_released() is not True:
        return None
    # This helper reads only CRUMP_ENABLE_CONNECTED_APPS and itself
    # source-short-circuits.  In particular, do not import runtime/settings
    # before this check: ordinary Ask Crump AI may still have unrelated ambient
    # credentials which are never an authentication fallback for this host.
    if config.connected_apps_environment_released() is not True:
        return None
    from . import connected_app_request_activation as request_activation_module
    from .connected_app_request_activation import (
        ConnectedRequestActivationCoordinator,
        ConnectedRequestActivationError,
        configure_connected_request_activation,
    )
    from .runtime import db
    expected_manifest = config.CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256
    if not isinstance(expected_manifest, str) or not _SHA256.fullmatch(expected_manifest):
        raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY")
    existing = request_activation_module.connected_request_activation_coordinator
    if existing is not None:
        if (
            type(existing) is not ConnectedRequestActivationCoordinator
            or existing.expected_manifest_sha256 != expected_manifest
        ):
            raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_NOT_READY")
        return existing
    if not callable(now):
        raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_INVALID")
    selected_environment = os.environ if environment is None else environment
    if not isinstance(selected_environment, Mapping):
        raise ConnectedHostBootstrapError("CONNECTED_HOST_BOOTSTRAP_INVALID")
    try:
        database_target_fingerprint = (
            config.CONNECTED_APPS_DATABASE_TARGET_FINGERPRINT
        )
        if not _FINGERPRINT.fullmatch(str(database_target_fingerprint or "")):
            raise ConnectedHostBootstrapError(
                "CONNECTED_HOST_BOOTSTRAP_NOT_READY"
            )
        if not _ROOT_KEY_ID.fullmatch(
            str(config.CONNECTED_APPS_KMS_ROOT_KEY_ID or "")
        ):
            raise ConnectedHostBootstrapError(
                "CONNECTED_HOST_BOOTSTRAP_NOT_READY"
            )
        encrypted_root_b64 = _required(
            selected_environment,
            "CRUMP_CONNECTED_KMS_ENCRYPTED_ROOT_B64",
        )
        host_configuration_ciphertext = _required(
            selected_environment,
            "CRUMP_CONNECTED_HOST_CONFIGURATION_CIPHERTEXT",
        )
        deployment_id = _required(selected_environment, "VERCEL_DEPLOYMENT_ID")
        commit_sha = _required(selected_environment, "VERCEL_GIT_COMMIT_SHA")
        kms_configuration = ConnectedGoogleKMSConfiguration(
            project_number=config.CONNECTED_APPS_KMS_PROJECT_NUMBER,
            workload_identity_pool_id=config.CONNECTED_APPS_KMS_WIF_POOL_ID,
            workload_identity_provider_id=(
                config.CONNECTED_APPS_KMS_WIF_PROVIDER_ID
            ),
            service_account_email=(
                config.CONNECTED_APPS_KMS_SERVICE_ACCOUNT_EMAIL
            ),
            crypto_key_resource=config.CONNECTED_APPS_KMS_CRYPTO_KEY_RESOURCE,
            encrypted_root_b64=encrypted_root_b64,
            root_key_id=config.CONNECTED_APPS_KMS_ROOT_KEY_ID,
            composition_manifest_sha256=expected_manifest,
            custody_attestation_sha256=(
                config.CONNECTED_APPS_KMS_CUSTODY_ATTESTATION_SHA256
            ),
            expected_protection_level=(
                config.CONNECTED_APPS_KMS_PROTECTION_LEVEL
            ),
            root_ttl_seconds=config.CONNECTED_APPS_KMS_ROOT_TTL_SECONDS,
        )
        ciphertext = ConnectedEncryptedHostConfiguration(
            host_configuration_ciphertext
        )
        root_loader = ConnectedGoogleKMSRootLoader(
            kms_configuration,
            now=now,
        )
        readiness = SupabaseConnectedProductionReadinessProbe(
            db,
            database_target_fingerprint=database_target_fingerprint,
            deployment_id=deployment_id,
            commit_sha=commit_sha,
            host_configuration_ciphertext_sha256=hashlib.sha256(
                host_configuration_ciphertext.encode("utf-8")
            ).hexdigest(),
            now=now,
        )
        ai_gateway_factory = ConnectedRequestScopedAIGatewayFactory(
            database=db,
            model=_AI_GATEWAY_MODEL,
            provider=_AI_GATEWAY_PROVIDER,
            deployment_id=deployment_id,
            commit_sha=commit_sha,
        )
        builder = ConnectedProductionGraphInputsBuilder(
            ciphertext=ciphertext,
            database=db,
            ai_gateway_factory=ai_gateway_factory,
            readiness=readiness,
            now=now,
        )
        coordinator = ConnectedRequestActivationCoordinator(
            root_loader=root_loader,
            inputs_builder=builder,
            expected_manifest_sha256=expected_manifest,
            now=now,
        )
        configure_connected_request_activation(coordinator)
        return coordinator
    except (ConnectedHostBootstrapError, ConnectedRequestActivationError):
        raise
    except Exception:
        raise ConnectedHostBootstrapError(
            "CONNECTED_HOST_BOOTSTRAP_NOT_READY"
        ) from None


__all__ = [
    "CONNECTED_DATABASE_CONTRACT_SHA256",
    "CONNECTED_PROVIDER_CONTRACT_SHA256",
    "ConnectedHostBootstrapError",
    "ConnectedProductionGraphInputsBuilder",
    "SupabaseConnectedProductionReadinessProbe",
    "configure_connected_production_host",
]
