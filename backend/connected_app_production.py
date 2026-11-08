"""Concrete, fail-closed production graph for connected mail and calendars.

The secure host supplies every secret-bearing or externally attested input as
an already-typed value.  This module never reads a key, OAuth registration, or
provider credential from process environment variables and importing it is
inert.  The ordinary application factory calls :func:`register_...` before the
activation bootstrap; with the checked-in release lock false that call does
not evaluate the input source or construct any dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from types import MappingProxyType
from typing import Callable, Mapping, Protocol

import httpx

from . import connected_app_activation as activation_module
from . import connected_app_bootstrap as bootstrap_module
from . import config
from .connected_app_activation import (
    ConnectedApplicationActivationError,
    ConnectedApplicationBundle,
)
from .connected_app_agent import ConnectedOperatorPlanner
from .connected_app_ai_model import ConnectedOperatorAIModel, ConnectedOperatorTextGateway
from .connected_app_background import (
    CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE,
    ConnectedOperatorBackgroundSupervisor,
)
from .connected_app_calendar_cancel_snapshot import (
    ConnectedCalendarCancelSnapshotCoordinator,
    SupabaseConnectedCalendarCancelSnapshotStage,
)
from .connected_app_chat_action_stage import SupabaseConnectedChatActionStage
from .connected_app_chat_completion import (
    ConnectedChatCompletionKey,
    SupabaseConnectedChatCompletionStore,
)
from .connected_app_chat_operator import ConnectedOperatorChatService
from .connected_app_chat_turn import ConnectedChatBindingKey, SupabaseConnectedChatTurnStore
from .connected_app_cleanup_reconciliation import (
    ConnectedExternalReconciliationCoordinator,
    EncryptedProviderGrantSecretResolver,
    SupabaseConnectedOAuthExpiryReconciler,
)
from .connected_app_composition import (
    ConnectedProductionDependencies,
    ConnectedProductionReadiness,
    compose_connected_operator,
)
from .connected_app_credential_vault import (
    ConnectedAccessTokenBroker,
    ConnectedCredentialMasterKey,
    ConnectedCredentialVault,
)
from .connected_app_delegated_responder import ConnectedOperatorDelegatedTextResponder
from .connected_app_durable_oauth import (
    ConnectedOAuthMasterKey,
    DurableOAuthCredentialBroker,
    SupabaseOAuthSecretStore,
)
from .connected_app_durable_stores import (
    SupabaseConnectedCredentialRefreshCoordinator,
    SupabaseConnectedCredentialSecretStore,
    SupabaseConnectedPayloadStore,
)
from .connected_app_execution_outbox import (
    ConnectedDispatchCoordinator,
    SupabaseConnectedDispatchStore,
)
from .connected_app_google import GoogleConnectedAppProvider
from .connected_app_grant_cleanup import (
    ConnectedGrantCleanupWorker,
    GoogleOAuthGrantRevoker,
    MicrosoftOAuthGrantRevoker,
    SupabaseConnectedGrantCleanupStore,
)
from .connected_app_https import (
    GoogleHTTPSCredentialTransport,
    MicrosoftHTTPSCredentialTransport,
)
from .connected_app_host_configuration import ConnectedHostConfigurationKey
from .connected_app_key_derivation import ConnectedKeyCustodyKind
from .connected_app_microsoft import MicrosoftConnectedAppProvider
from .connected_app_multi_step import (
    ConnectedMultiStepCommitmentKey,
    ConnectedMultiStepCoordinator,
    ConnectedMultiStepMasterKey,
    ConnectedMultiStepProposalVault,
)
from .connected_app_multi_step_adapters import (
    ConnectedOperatorMultiStepExecutor,
    ConnectedOperatorMultiStepObservationSource,
    ConnectedOperatorMultiStepProposer,
    ConnectedOperatorMultiStepWorker,
    SupabaseConnectedMultiStepActionStage,
    SupabaseConnectedMultiStepEnvelopeStore,
    SupabaseConnectedMultiStepStore,
)
from .connected_app_multi_step_continuation import (
    ConnectedMultiStepContinuationWorker,
    ConnectedMultiStepInstructionSource,
    SupabaseConnectedMultiStepContinuationStore,
)
from .connected_app_oauth import OAuthRedirectAllowlist
from .connected_app_oauth_code_custody import (
    ConnectedOAuthAuthorizationCodeVault,
    SupabaseOAuthAuthorizationCodeCustodyStore,
)
from .connected_app_oauth_control import ConnectedAppOAuthOrchestrator
from .connected_app_oauth_control_supabase import SupabaseConnectedOAuthOperatorStore
from .connected_app_oauth_supabase import (
    SupabaseConnectedAccountRegistry,
    SupabaseOAuthCompletionRepository,
    SupabaseOAuthFlowRepository,
)
from .connected_app_operator_adapters import (
    ConnectedOperatorActionCoordinator,
)
from .connected_app_payload_resolution import ConnectedActionPayloadResolver
from .connected_app_payload_retention import SupabaseConnectedPayloadRetentionPurger
from .connected_app_payload_vault import (
    ConnectedPayloadCommitmentKey,
    ConnectedPayloadMasterKey,
    ConnectedPayloadVault,
)
from .connected_app_plan_once import (
    ConnectedPlanBindingKey,
    ConnectedPlanOnceCoordinator,
    SupabaseConnectedPlanControlPlane,
    SupabaseConnectedPlanEnvelopeStore,
)
from .connected_app_plan_vault import (
    ConnectedPlanCommitmentKey,
    ConnectedPlanEnvelopeVault,
    ConnectedPlanMasterKey,
)
from .connected_app_policy import ConnectorProvider
from .connected_app_production_keys import ConnectedProductionKeys
from .connected_app_provider_oauth import (
    ProviderOAuthHTTPSClient,
    ProviderOAuthRegistration,
)
from .connected_app_read_results import (
    ConnectedReadResultCoordinator,
    SupabaseConnectedReadResultStore,
)
from .connected_app_readiness_attestation import ConnectedReadinessAttestationKey
from .connected_app_read_surface import (
    ConnectedOwnerReadResultService,
    SupabaseConnectedOwnerReadResultIndex,
)
from .connected_app_review_resolution import ConnectedApprovalPreviewVaultResolver
from .connected_app_runtime import ConnectedAppRuntime
from .connected_app_runtime_adapters import (
    SupabaseConnectedActionLedger,
    SupabaseConnectedCredentialGateway,
)
from .connected_app_schedule_adapters import (
    ConnectedOperatorScheduleCoordinator,
    ConnectedScheduleTemplateCommitmentKey,
    ConnectedScheduleTemplateKey,
    ConnectedScheduleTemplateResolver,
    ConnectedScheduleTemplateVault,
    SupabaseConnectedChatScheduleStage,
    SupabaseConnectedScheduleStore,
)
from .connected_app_schedule_approval import (
    ConnectedScheduleApprovalCoordinator,
    SupabaseConnectedScheduleApprovalStore,
)
from .connected_app_service import (
    ConnectedAppReadiness,
    ConnectedAppService,
    connected_app_readiness_attestation_sha256,
)
from .connected_app_supabase_control_plane import SupabaseConnectedAppControlPlane
from .runtime import settings


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ROOT_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$")
_PROVIDERS = frozenset(ConnectorProvider)
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
class ConnectedProductionGraphError(RuntimeError):
    """Content-free composition failure safe for bootstrap quarantine."""

    _CODES = frozenset(
        {
            "CONNECTED_PRODUCTION_GRAPH_INVALID",
            "CONNECTED_PRODUCTION_GRAPH_NOT_READY",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = code if code in self._CODES else "CONNECTED_PRODUCTION_GRAPH_INVALID"
        super().__init__(self.code)

    def __repr__(self) -> str:
        return f"ConnectedProductionGraphError(code={self.code!r})"


class ConnectedProductionRPC(Protocol):
    async def rpc(
        self,
        function: str,
        params: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
    return value.astimezone(UTC)


def _exact_provider_mapping(value: object, *, name: str) -> dict[ConnectorProvider, object]:
    del name
    if not isinstance(value, Mapping):
        raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
    try:
        if set(value) != _PROVIDERS:
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
        return {provider: value[provider] for provider in ConnectorProvider}
    except ConnectedProductionGraphError:
        raise
    except Exception:
        raise ConnectedProductionGraphError(
            "CONNECTED_PRODUCTION_GRAPH_INVALID"
        ) from None


def _key_suffix(purpose: str, manifest: str) -> str:
    return f".{purpose}.{manifest[:10]}"


def _validate_keys(keys: ConnectedProductionKeys, *, manifest: str) -> None:
    if type(keys) is not ConnectedProductionKeys:
        raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
    if keys.composition_manifest_sha256 != manifest or not _SHA256.fullmatch(
        keys.custody_attestation_sha256
    ):
        raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_NOT_READY")
    if not isinstance(keys.root_key_id, str) or not _ROOT_KEY_ID.fullmatch(
        keys.root_key_id
    ):
        raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_NOT_READY")
    domains: tuple[tuple[object, type[object], str], ...] = (
        (
            keys.host_configuration,
            ConnectedHostConfigurationKey,
            "host_configuration",
        ),
        (
            keys.readiness_attestation,
            ConnectedReadinessAttestationKey,
            "readiness_attestation",
        ),
        (keys.oauth_envelope, ConnectedOAuthMasterKey, "oauth_envelope"),
        (keys.oauth_permit, ConnectedOAuthMasterKey, "oauth_permit"),
        (keys.credential_envelope, ConnectedCredentialMasterKey, "credential_envelope"),
        (keys.payload_envelope, ConnectedPayloadMasterKey, "payload_envelope"),
        (keys.payload_commitment, ConnectedPayloadCommitmentKey, "payload_commitment"),
        (keys.plan_envelope, ConnectedPlanMasterKey, "plan_envelope"),
        (keys.plan_commitment, ConnectedPlanCommitmentKey, "plan_commitment"),
        (keys.plan_binding, ConnectedPlanBindingKey, "plan_binding"),
        (keys.schedule_envelope, ConnectedScheduleTemplateKey, "schedule_envelope"),
        (
            keys.schedule_commitment,
            ConnectedScheduleTemplateCommitmentKey,
            "schedule_commitment",
        ),
        (keys.chat_binding, ConnectedChatBindingKey, "chat_binding"),
        (keys.chat_completion, ConnectedChatCompletionKey, "chat_completion"),
        (keys.loop_envelope, ConnectedMultiStepMasterKey, "loop_envelope"),
        (keys.loop_commitment, ConnectedMultiStepCommitmentKey, "loop_commitment"),
    )
    identifiers: list[str] = []
    for value, expected_type, purpose in domains:
        if type(value) is not expected_type:
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
        key_id = getattr(value, "key_id", None)
        expected_key_id = keys.root_key_id + _key_suffix(purpose, manifest)
        if not isinstance(key_id, str) or key_id != expected_key_id:
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_NOT_READY")
        identifiers.append(key_id)
    if len(set(identifiers)) != len(identifiers):
        raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_NOT_READY")
    _aware(keys.expires_at)


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedProductionGraphInputs:
    """Trusted, explicit inputs to one exact connected-operator graph."""

    database: ConnectedProductionRPC
    readiness_source: Callable[[], ConnectedProductionReadiness]
    keys: ConnectedProductionKeys
    key_custody: ConnectedKeyCustodyKind
    registrations: Mapping[ConnectorProvider, ProviderOAuthRegistration]
    redirect_allowlists: Mapping[ConnectorProvider, OAuthRedirectAllowlist]
    redirect_uris: Mapping[ConnectorProvider, str]
    ai_gateway: ConnectedOperatorTextGateway
    oauth_transports: Mapping[ConnectorProvider, httpx.AsyncBaseTransport | None]
    provider_transports: Mapping[ConnectorProvider, httpx.AsyncBaseTransport | None]
    google_revocation_transport: httpx.AsyncBaseTransport | None

    def __post_init__(self) -> None:
        if not callable(getattr(self.database, "rpc", None)):
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
        if not callable(self.readiness_source) or not callable(
            getattr(self.ai_gateway, "gateway_text", None)
        ):
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
        if not isinstance(self.key_custody, ConnectedKeyCustodyKind):
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")

        registrations = _exact_provider_mapping(self.registrations, name="registrations")
        allowlists = _exact_provider_mapping(self.redirect_allowlists, name="redirect allowlists")
        redirects = _exact_provider_mapping(self.redirect_uris, name="redirect uris")
        oauth_transports = _exact_provider_mapping(self.oauth_transports, name="OAuth transports")
        provider_transports = _exact_provider_mapping(
            self.provider_transports,
            name="provider transports",
        )
        client_id_hashes: set[str] = set()
        for provider in ConnectorProvider:
            registration = registrations[provider]
            allowlist = allowlists[provider]
            redirect_uri = redirects[provider]
            if (
                type(registration) is not ProviderOAuthRegistration
                or registration.provider is not provider
                or type(allowlist) is not OAuthRedirectAllowlist
                or not isinstance(redirect_uri, str)
                or redirect_uri != _PRODUCTION_REDIRECT_URIS[provider]
                or allowlist.allowed_redirect_uris
                != frozenset({_PRODUCTION_REDIRECT_URIS[provider]})
            ):
                raise ConnectedProductionGraphError(
                    "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
                )
            if registration.client_id_sha256 in client_id_hashes:
                raise ConnectedProductionGraphError(
                    "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
                )
            client_id_hashes.add(registration.client_id_sha256)
            try:
                allowlist.require(redirect_uri)
            except Exception:
                raise ConnectedProductionGraphError(
                    "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
                ) from None
            for transport in (oauth_transports[provider], provider_transports[provider]):
                if transport is not None and not isinstance(
                    transport, httpx.AsyncBaseTransport
                ):
                    raise ConnectedProductionGraphError(
                        "CONNECTED_PRODUCTION_GRAPH_INVALID"
                    )
        if self.google_revocation_transport is not None and not isinstance(
            self.google_revocation_transport,
            httpx.AsyncBaseTransport,
        ):
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")

        object.__setattr__(self, "registrations", MappingProxyType(registrations))
        object.__setattr__(self, "redirect_allowlists", MappingProxyType(allowlists))
        object.__setattr__(self, "redirect_uris", MappingProxyType(redirects))
        object.__setattr__(self, "oauth_transports", MappingProxyType(oauth_transports))
        object.__setattr__(self, "provider_transports", MappingProxyType(provider_transports))

    def __repr__(self) -> str:
        return "ConnectedProductionGraphInputs(authority='external', secrets='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("connected production graph inputs cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected production graph inputs cannot be serialized")


class ConnectedProductionApplicationFactory:
    """Build every production adapter from one trusted, renewable input source."""

    __slots__ = ("_source",)

    def __init__(self, source: Callable[[], ConnectedProductionGraphInputs]) -> None:
        if not callable(source):
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
        self._source = source

    def __repr__(self) -> str:
        return "ConnectedProductionApplicationFactory(source='trusted', secrets='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("connected production application factory cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected production application factory cannot be serialized")

    def build(
        self,
        *,
        expected_manifest_sha256: str,
        now: Callable[[], datetime],
    ) -> ConnectedApplicationBundle:
        if (
            not isinstance(expected_manifest_sha256, str)
            or not _SHA256.fullmatch(expected_manifest_sha256)
            or not callable(now)
        ):
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
        try:
            inputs = self._source()
            if type(inputs) is not ConnectedProductionGraphInputs:
                raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_INVALID")
            return self._build_exact(
                inputs=inputs,
                expected_manifest_sha256=expected_manifest_sha256,
                now=now,
            )
        except ConnectedProductionGraphError:
            raise
        except Exception:
            raise ConnectedProductionGraphError(
                "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
            ) from None

    @staticmethod
    def _build_exact(
        *,
        inputs: ConnectedProductionGraphInputs,
        expected_manifest_sha256: str,
        now: Callable[[], datetime],
    ) -> ConnectedApplicationBundle:
        reference = _aware(now())
        keys = inputs.keys
        _validate_keys(keys, manifest=expected_manifest_sha256)
        if _aware(keys.expires_at) <= reference:
            raise ConnectedProductionGraphError("CONNECTED_PRODUCTION_GRAPH_NOT_READY")

        def production_readiness() -> ConnectedProductionReadiness:
            try:
                value = inputs.readiness_source()
            except Exception:
                raise ConnectedProductionGraphError(
                    "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
                ) from None
            current = _aware(now())
            if (
                type(value) is not ConnectedProductionReadiness
                or not value.is_ready(
                    expected_manifest_sha256=expected_manifest_sha256,
                    now=current,
                )
                or keys.composition_manifest_sha256 != expected_manifest_sha256
                or _aware(keys.expires_at) <= current
            ):
                raise ConnectedProductionGraphError(
                    "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
                )
            return value

        def service_readiness() -> ConnectedAppReadiness:
            attested = production_readiness()
            expires_at = min(attested.expires_at, _aware(keys.expires_at))
            if expires_at <= attested.checked_at:
                raise ConnectedProductionGraphError(
                    "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
                )
            return ConnectedAppReadiness(
                ready=True,
                attestation_sha256=connected_app_readiness_attestation_sha256(
                    ready=True,
                    composition_manifest_sha256=expected_manifest_sha256,
                    checked_at=attested.checked_at,
                    expires_at=expires_at,
                ),
                composition_manifest_sha256=expected_manifest_sha256,
                checked_at=attested.checked_at,
                expires_at=expires_at,
            )

        # Refuse a stale or mismatched renewable source before allocating any
        # network-capable adapter.
        production_readiness()

        database = inputs.database
        registrations = dict(inputs.registrations)
        redirect_allowlists = dict(inputs.redirect_allowlists)
        redirect_uris = dict(inputs.redirect_uris)

        payload_store = SupabaseConnectedPayloadStore(database)
        payload_vault = ConnectedPayloadVault(
            keys={keys.payload_envelope.key_id: keys.payload_envelope},
            active_key_id=keys.payload_envelope.key_id,
            commitment_keys={keys.payload_commitment.key_id: keys.payload_commitment},
            active_commitment_key_id=keys.payload_commitment.key_id,
            store=payload_store,
            now=now,
        )
        credential_store = SupabaseConnectedCredentialSecretStore(database)
        credential_vault = ConnectedCredentialVault(
            keys={keys.credential_envelope.key_id: keys.credential_envelope},
            active_key_id=keys.credential_envelope.key_id,
            store=credential_store,
            now=now,
        )
        oauth_clients = {
            provider: ProviderOAuthHTTPSClient(
                registrations[provider],
                transport=inputs.oauth_transports[provider],
                now=now,
            )
            for provider in ConnectorProvider
        }
        credential_refresh = SupabaseConnectedCredentialRefreshCoordinator(
            database,
            now=now,
        )
        token_broker = ConnectedAccessTokenBroker(
            vault=credential_vault,
            clients=oauth_clients,
            refresh_coordinator=credential_refresh,
            now=now,
        )

        grant_cleanup_store = SupabaseConnectedGrantCleanupStore(database)
        oauth_flows = SupabaseOAuthFlowRepository(
            database=database,
            redirect_uris=redirect_uris,
            permit_keys={keys.oauth_permit.key_id: keys.oauth_permit},
            active_permit_key_id=keys.oauth_permit.key_id,
            now=now,
        )
        oauth_completions = SupabaseOAuthCompletionRepository(database)
        accounts = SupabaseConnectedAccountRegistry(database)
        oauth_secret_store = SupabaseOAuthSecretStore(database)
        oauth_broker = DurableOAuthCredentialBroker(
            keys={keys.oauth_envelope.key_id: keys.oauth_envelope},
            active_key_id=keys.oauth_envelope.key_id,
            store=oauth_secret_store,
            permit_authority=oauth_flows,
            clients=oauth_clients,
            credential_vault=credential_vault,
            grant_cleanup_store=grant_cleanup_store,
            now=now,
        )
        oauth_operator_store = SupabaseConnectedOAuthOperatorStore(
            database=database,
            flow_decoder=oauth_flows,
            redirect_uris=redirect_uris,
        )
        authorization_code_custody = ConnectedOAuthAuthorizationCodeVault(
            key=keys.oauth_code_envelope,
            store=SupabaseOAuthAuthorizationCodeCustodyStore(database),
        )
        oauth_operator = ConnectedAppOAuthOrchestrator(
            store=oauth_operator_store,
            broker=oauth_broker,
            flows=oauth_flows,
            completions=oauth_completions,
            registrations=registrations,
            redirect_allowlists=redirect_allowlists,
            now=now,
            authorization_code_custody=authorization_code_custody,
        )
        preview_resolver = ConnectedApprovalPreviewVaultResolver(
            references=payload_store,
            payloads=payload_vault,
        )
        control_plane = SupabaseConnectedAppControlPlane(
            database=database,
            oauth=oauth_operator,
            previews=preview_resolver,
            now=now,
        )
        service = ConnectedAppService(
            control_plane=control_plane,
            readiness_source=service_readiness,
            expected_composition_manifest_sha256=expected_manifest_sha256,
            redirect_allowlist={
                provider: redirect_allowlists[provider].allowed_redirect_uris
                for provider in ConnectorProvider
            },
            oauth_client_ids={
                provider: registrations[provider].client_id
                for provider in ConnectorProvider
            },
            now=now,
        )

        credential_gateway = SupabaseConnectedCredentialGateway(
            database=database,
            tokens=token_broker,
            now=now,
        )
        google_transport = GoogleHTTPSCredentialTransport(
            credential_gateway,
            transport=inputs.provider_transports[ConnectorProvider.GOOGLE],
            now=now,
        )
        microsoft_transport = MicrosoftHTTPSCredentialTransport(
            credential_gateway,
            transport=inputs.provider_transports[ConnectorProvider.MICROSOFT],
            now=now,
        )
        google_provider = GoogleConnectedAppProvider(google_transport, now=now)
        microsoft_provider = MicrosoftConnectedAppProvider(microsoft_transport, now=now)
        ledger = SupabaseConnectedActionLedger(database)

        read_result_store = SupabaseConnectedReadResultStore(database)
        read_result_coordinator = ConnectedReadResultCoordinator(
            vault=payload_vault,
            references=payload_store,
            store=read_result_store,
            now=now,
        )
        action_payloads = ConnectedActionPayloadResolver(
            references=payload_store,
            payloads=payload_vault,
        )

        plan_control = SupabaseConnectedPlanControlPlane(database)
        plan_store = SupabaseConnectedPlanEnvelopeStore(database)
        plan_vault = ConnectedPlanEnvelopeVault(
            store=plan_store,
            master_keys={keys.plan_envelope.key_id: keys.plan_envelope},
            active_master_key_id=keys.plan_envelope.key_id,
            commitment_keys={keys.plan_commitment.key_id: keys.plan_commitment},
            active_commitment_key_id=keys.plan_commitment.key_id,
        )
        planner = ConnectedOperatorPlanner(
            ConnectedOperatorAIModel(inputs.ai_gateway),
            now=now,
        )
        plans = ConnectedPlanOnceCoordinator(
            planner=planner,
            control_plane=plan_control,
            vault=plan_vault,
            now=now,
        )

        schedule_vault = ConnectedScheduleTemplateVault(
            primary_key=keys.schedule_envelope,
            commitment_key=keys.schedule_commitment,
        )
        schedule_stage = SupabaseConnectedChatScheduleStage(database)
        schedules = ConnectedOperatorScheduleCoordinator(
            planning_key=keys.plan_binding,
            plans=plan_control,
            authorities=control_plane,
            vault=schedule_vault,
            stage=schedule_stage,
            now=now,
        )
        schedule_store = SupabaseConnectedScheduleStore(database)
        schedule_approval_store = SupabaseConnectedScheduleApprovalStore(database)
        cancellation_snapshots: ConnectedCalendarCancelSnapshotCoordinator | None = None

        def build_schedule_resolver(
            runtime: ConnectedAppRuntime,
        ) -> ConnectedScheduleTemplateResolver:
            nonlocal cancellation_snapshots
            if cancellation_snapshots is not None:
                raise ConnectedProductionGraphError(
                    "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
                )
            snapshot_stage = SupabaseConnectedCalendarCancelSnapshotStage(
                database=database,
                preparations=control_plane,
            )
            snapshots = ConnectedCalendarCancelSnapshotCoordinator(
                planning_key=keys.plan_binding,
                authorities=control_plane,
                payload_vault=payload_vault,
                payloads=action_payloads,
                stage=snapshot_stage,
                runtime=runtime,
                now=now,
            )
            approvals = ConnectedScheduleApprovalCoordinator(
                store=schedule_approval_store,
                payload_vault=payload_vault,
                cancellation_snapshots=snapshots,
                now=now,
            )
            resolver = ConnectedScheduleTemplateResolver(
                templates=schedule_store,
                vault=schedule_vault,
                approvals=approvals,
            )
            cancellation_snapshots = snapshots
            return resolver

        composition = compose_connected_operator(
            source_released=True,
            readiness_source=production_readiness,
            expected_manifest_sha256=expected_manifest_sha256,
            dependencies=ConnectedProductionDependencies(
                accounts=accounts,
                credentials=credential_gateway,
                ledger=ledger,
                lease_consumer=credential_gateway,
                google_provider=google_provider,
                microsoft_provider=microsoft_provider,
                read_results=read_result_coordinator,
                schedule_store=schedule_store,
                schedule_resolver=None,
                schedule_resolver_factory=build_schedule_resolver,
            ),
            now=now,
        )
        snapshots = cancellation_snapshots
        if type(snapshots) is not ConnectedCalendarCancelSnapshotCoordinator:
            raise ConnectedProductionGraphError(
                "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
            )

        action_stage = SupabaseConnectedChatActionStage(
            database=database,
            preparations=control_plane,
        )
        multi_step_action_stage = SupabaseConnectedMultiStepActionStage(
            database=database,
            preparations=control_plane,
        )
        actions = ConnectedOperatorActionCoordinator(
            planning_key=keys.plan_binding,
            authorities=control_plane,
            payload_vault=payload_vault,
            payloads=action_payloads,
            stage=action_stage,
            runtime=composition.runtime,
            durable_read_results_attested=True,
            cancellation_snapshots=snapshots,
            multi_step_stage=multi_step_action_stage,
            now=now,
        )
        read_results = ConnectedOwnerReadResultService(
            index=SupabaseConnectedOwnerReadResultIndex(database),
            results=read_result_coordinator,
            composition_manifest_sha256=expected_manifest_sha256,
            now=now,
        )
        multi_step_vault = ConnectedMultiStepProposalVault(
            store=SupabaseConnectedMultiStepEnvelopeStore(database=database),
            master_keys={keys.loop_envelope.key_id: keys.loop_envelope},
            active_master_key_id=keys.loop_envelope.key_id,
            commitment_keys={keys.loop_commitment.key_id: keys.loop_commitment},
            active_commitment_key_id=keys.loop_commitment.key_id,
        )
        multi_step_store = SupabaseConnectedMultiStepStore(database=database)
        multi_step_coordinator = ConnectedMultiStepCoordinator(
            store=multi_step_store,
            vault=multi_step_vault,
            proposer=ConnectedOperatorMultiStepProposer(planner=planner),
            executor=ConnectedOperatorMultiStepExecutor(actions=actions, now=now),
            observations=ConnectedOperatorMultiStepObservationSource(
                results=read_results
            ),
            require_ready=service.require_ready,
            now=now,
        )
        multi_step_worker = ConnectedOperatorMultiStepWorker(
            coordinator=multi_step_coordinator,
            require_ready=service.require_ready,
        )
        continuation_store = SupabaseConnectedMultiStepContinuationStore(database)
        multi_step_continuation = ConnectedMultiStepContinuationWorker(
            store=continuation_store,
            instructions=ConnectedMultiStepInstructionSource(
                store=continuation_store,
                binding_key=keys.chat_binding,
            ),
            connections=control_plane,
            worker=multi_step_worker,
            require_ready=service.require_ready,
            now=now,
        )
        chat = ConnectedOperatorChatService(
            binding_key=keys.chat_binding,
            planning_key=keys.plan_binding,
            completion_key=keys.chat_completion,
            turns=SupabaseConnectedChatTurnStore(database),
            plans=plans,
            completions=SupabaseConnectedChatCompletionStore(database),
            connections=control_plane,
            actions=actions,
            delegated=ConnectedOperatorDelegatedTextResponder(inputs.ai_gateway),
            schedules=schedules,
            multi_step=multi_step_worker,
            multi_step_enabled=config.CONNECTED_MULTI_STEP_SOURCE_RELEASED,
            composition_manifest_sha256=expected_manifest_sha256,
            require_ready=service.require_ready,
            now=now,
        )

        dispatch = ConnectedDispatchCoordinator(
            store=SupabaseConnectedDispatchStore(database=database),
            payloads=action_payloads,
            runtime=composition.runtime,
            require_ready=service.require_ready,
        )
        cleanup_secret_resolver = EncryptedProviderGrantSecretResolver(
            credential_keys={keys.credential_envelope.key_id: keys.credential_envelope},
            oauth_keys={keys.oauth_envelope.key_id: keys.oauth_envelope},
        )
        cleanup_worker = ConnectedGrantCleanupWorker(
            store=grant_cleanup_store,
            secret_resolver=cleanup_secret_resolver,
            google=GoogleOAuthGrantRevoker(
                transport=inputs.google_revocation_transport
            ),
            microsoft=MicrosoftOAuthGrantRevoker(),
            now=now,
        )
        reconciler = ConnectedExternalReconciliationCoordinator(
            cleanup=cleanup_worker,
            oauth_expiry=SupabaseConnectedOAuthExpiryReconciler(database),
            now=now,
        )
        payload_retention = SupabaseConnectedPayloadRetentionPurger(database)
        background = ConnectedOperatorBackgroundSupervisor(
            source_released=True,
            readiness_attested=True,
            require_ready=service.require_ready,
            composition_manifest_sha256=expected_manifest_sha256,
            dispatch=dispatch,
            scheduler=composition.scheduler,
            reconciler=reconciler,
            multi_step_continuation=multi_step_continuation,
            continuation_released=config.CONNECTED_MULTI_STEP_SOURCE_RELEASED,
            payload_retention=payload_retention,
            execution_mode=CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE,
        )
        return ConnectedApplicationBundle(
            service=service,
            chat=chat,
            read_results=read_results,
            background=background,
            composition_manifest_sha256=expected_manifest_sha256,
            multi_step_worker=multi_step_worker,
            multi_step_released=config.CONNECTED_MULTI_STEP_SOURCE_RELEASED,
        )


connected_production_inputs_source: (
    Callable[[], ConnectedProductionGraphInputs] | None
) = None


def configure_connected_production_inputs_source(
    source: Callable[[], ConnectedProductionGraphInputs] | None,
) -> None:
    """Install the secure-host source without evaluating it or enabling routes."""

    global connected_production_inputs_source
    if (
        activation_module.connected_application_activation is not None
        or bootstrap_module.connected_application_factory is not None
    ):
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_ALREADY_ACTIVE"
        )
    if source is not None and not callable(source):
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_GRAPH_INVALID"
        )
    connected_production_inputs_source = source


def register_connected_production_application_factory() -> object | None:
    """Register the concrete graph before bootstrap, remaining inert by default."""

    if (
        config.connected_apps_release_candidate_source_released() is not True
        or settings.connected_apps_enabled is not True
    ):
        return None
    existing = bootstrap_module.connected_application_factory
    if existing is not None:
        if type(existing) is not ConnectedProductionApplicationFactory:
            # Do not silently retain the former protocol-only bootstrap or a
            # test/fallback graph once production locks are true.
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_NOT_READY"
            )
        return existing
    source = connected_production_inputs_source
    if source is None:
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_NOT_READY"
        )
    factory = ConnectedProductionApplicationFactory(source)
    bootstrap_module.configure_connected_application_factory(factory)
    return factory


__all__ = [
    "ConnectedProductionApplicationFactory",
    "ConnectedProductionGraphError",
    "ConnectedProductionGraphInputs",
    "configure_connected_production_inputs_source",
    "register_connected_production_application_factory",
]
