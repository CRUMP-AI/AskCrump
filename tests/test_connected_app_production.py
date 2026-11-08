from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import inspect
import pickle
from types import SimpleNamespace

import httpx
import pytest

from backend import connected_app_activation as activation_module
from backend import connected_app_bootstrap as bootstrap_module
from backend import connected_app_production as production_module
from backend import config
from backend.connected_app_activation import ConnectedApplicationActivationError
from backend.connected_app_calendar_cancel_snapshot import (
    ConnectedCalendarCancelSnapshotCoordinator,
    SupabaseConnectedCalendarCancelSnapshotStage,
)
from backend.connected_app_cleanup_reconciliation import (
    ConnectedExternalReconciliationCoordinator,
)
from backend.connected_app_composition import ConnectedProductionReadiness
from backend.connected_app_key_derivation import (
    ConnectedDerivedKeyset,
    ConnectedKeyCustodyKind,
    ConnectedRootKeyMaterial,
)
from backend.connected_app_multi_step import (
    ConnectedMultiStepCoordinator,
    ConnectedMultiStepStartCommand,
)
from backend.connected_app_multi_step_adapters import (
    ConnectedOperatorMultiStepWorker,
    SupabaseConnectedMultiStepActionStage,
    SupabaseConnectedMultiStepEnvelopeStore,
    SupabaseConnectedMultiStepStore,
)
from backend.connected_app_multi_step_continuation import (
    ConnectedMultiStepContinuationWorker,
    ConnectedMultiStepInstructionSource,
    SupabaseConnectedMultiStepContinuationStore,
)
from backend.connected_app_oauth import OAuthRedirectAllowlist
from backend.connected_app_payload_retention import SupabaseConnectedPayloadRetentionPurger
from backend.connected_app_policy import ConnectorProvider
from backend.connected_app_production import (
    ConnectedProductionApplicationFactory,
    ConnectedProductionGraphError,
    ConnectedProductionGraphInputs,
)
from backend.connected_app_production_keys import ConnectedProductionKeys
from backend.connected_app_provider_oauth import (
    ProviderOAuthClientSecret,
    ProviderOAuthRegistration,
)
from backend.connected_app_service import ConnectedAppServiceError
from backend.routes import chat as chat_routes
from backend.routes import connected_apps as connected_routes


NOW = datetime(2026, 11, 8, 15, 0, tzinfo=UTC)
MANIFEST = hashlib.sha256(b"connected-production-graph-v1").hexdigest()
OWNER_ID = "11111111-1111-4111-8111-111111111111"


class Clock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        return self.value


class FakeDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def rpc(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("factory construction must not call the database")


class FakeAIGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def gateway_text(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return '{"disposition":"none"}'


def readiness(*, manifest: str = MANIFEST) -> ConnectedProductionReadiness:
    return ConnectedProductionReadiness(
        composition_manifest_sha256=manifest,
        checked_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
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


def production_keys(
    *,
    manifest: str = MANIFEST,
    expires_at: datetime = NOW + timedelta(minutes=10),
) -> ConnectedProductionKeys:
    root = ConnectedRootKeyMaterial(
        key_id="test-kms-root",
        custody=ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS,
        attestation_sha256=hashlib.sha256(b"kms attestation").hexdigest(),
        loaded_at=NOW,
        expires_at=expires_at,
        secret=b"k" * 32,
    )
    keyset = ConnectedDerivedKeyset(
        root=root,
        composition_manifest_sha256=manifest,
        now=lambda: NOW,
    )
    return ConnectedProductionKeys.build(keyset, now=lambda: NOW)


def _transport() -> httpx.MockTransport:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("factory construction must not call a provider")

    return httpx.MockTransport(refuse)


def graph_inputs(
    *,
    clock: Clock | None = None,
    keys: ConnectedProductionKeys | None = None,
    ready: ConnectedProductionReadiness | None = None,
) -> tuple[ConnectedProductionGraphInputs, FakeDatabase, FakeAIGateway]:
    del clock
    database = FakeDatabase()
    gateway = FakeAIGateway()
    registrations = {
        provider: ProviderOAuthRegistration(
            provider=provider,
            client_id=f"ask-crump-{provider.value}-client",
            client_secret=ProviderOAuthClientSecret(
                f"test-{provider.value}-client-secret-value"
            ),
        )
        for provider in ConnectorProvider
    }
    redirects = {
        ConnectorProvider.GOOGLE: (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
        ),
        ConnectorProvider.MICROSOFT: (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
        ),
    }
    allowlists = {
        provider: OAuthRedirectAllowlist(frozenset({redirects[provider]}))
        for provider in ConnectorProvider
    }
    value = ConnectedProductionGraphInputs(
        database=database,
        readiness_source=lambda: ready or readiness(),
        keys=keys or production_keys(),
        key_custody=ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS,
        registrations=registrations,
        redirect_allowlists=allowlists,
        redirect_uris=redirects,
        ai_gateway=gateway,
        oauth_transports={provider: _transport() for provider in ConnectorProvider},
        provider_transports={provider: _transport() for provider in ConnectorProvider},
        google_revocation_transport=_transport(),
    )
    return value, database, gateway


@pytest.fixture(autouse=True)
def clear_process_graph(monkeypatch):
    activation_module.connected_application_activation = None
    activation_module._activation_transition = None
    activation_module._route_owner = None
    bootstrap_module.connected_application_factory = None
    production_module.connected_production_inputs_source = None
    connected_routes.connected_app_service = None
    connected_routes.connected_read_result_service = None
    connected_routes.connected_background_worker = None
    connected_routes.connected_multi_step_worker = None
    chat_routes.connected_operator_chat_service = None
    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)
    monkeypatch.setattr(
        production_module,
        "settings",
        SimpleNamespace(connected_apps_enabled=False),
    )
    yield
    activation_module.connected_application_activation = None
    activation_module._activation_transition = None
    activation_module._route_owner = None
    bootstrap_module.connected_application_factory = None
    production_module.connected_production_inputs_source = None
    connected_routes.connected_app_service = None
    connected_routes.connected_read_result_service = None
    connected_routes.connected_background_worker = None
    connected_routes.connected_multi_step_worker = None
    chat_routes.connected_operator_chat_service = None


def test_default_registration_is_inert_without_evaluating_secure_inputs(monkeypatch):
    calls = 0

    def source():
        nonlocal calls
        calls += 1
        raise AssertionError("unreleased source must remain untouched")

    production_module.configure_connected_production_inputs_source(source)
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", False)
    assert production_module.register_connected_production_application_factory() is None
    assert bootstrap_module.connected_application_factory is None
    assert calls == 0


def test_released_registration_requires_explicit_secure_host_source(monkeypatch):
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(
        production_module,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_NOT_READY",
    ):
        production_module.register_connected_production_application_factory()
    assert bootstrap_module.connected_application_factory is None


def test_released_registration_refuses_the_former_protocol_only_fallback(monkeypatch):
    class ProtocolOnlyFactory:
        def build(self, **_kwargs):
            raise AssertionError("fallback graph must not be evaluated")

    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(
        production_module,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    bootstrap_module.connected_application_factory = ProtocolOnlyFactory()
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_NOT_READY",
    ):
        production_module.register_connected_production_application_factory()


def test_full_graph_is_exact_external_wake_and_has_no_construction_io():
    inputs, database, _gateway = graph_inputs()
    bundle = ConnectedProductionApplicationFactory(lambda: inputs).build(
        expected_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )

    assert bundle.composition_manifest_sha256 == MANIFEST
    assert bundle.service.readiness.composition_manifest_sha256 == MANIFEST
    assert bundle.chat.composition_manifest_sha256 == MANIFEST
    assert bundle.read_results.composition_manifest_sha256 == MANIFEST
    assert bundle.background.composition_manifest_sha256 == MANIFEST
    assert bundle.background.external_wake is True
    assert bundle.background.execution_mode == "external_wake"
    assert type(bundle.background._reconciler) is ConnectedExternalReconciliationCoordinator
    assert type(bundle.background._payload_retention) is (
        SupabaseConnectedPayloadRetentionPurger
    )
    assert bundle.chat._connections is bundle.service._control_plane
    assert config.CONNECTED_MULTI_STEP_SOURCE_RELEASED is True
    assert bundle.multi_step_released is True
    assert bundle.chat._multi_step_enabled is True
    assert bundle.background._continuation_released is True
    assert type(bundle.chat._multi_step) is ConnectedOperatorMultiStepWorker
    assert bundle.multi_step_worker is bundle.chat._multi_step
    assert type(bundle.background._multi_step_continuation) is (
        ConnectedMultiStepContinuationWorker
    )
    continuation = bundle.background._multi_step_continuation
    assert type(continuation._store) is SupabaseConnectedMultiStepContinuationStore
    assert type(continuation._instructions) is ConnectedMultiStepInstructionSource
    assert continuation._worker is bundle.multi_step_worker
    assert continuation._connections is bundle.service._control_plane
    assert callable(bundle.multi_step_worker.wake)
    assert callable(bundle.multi_step_worker.cancel)
    assert type(bundle.chat._actions._multi_step_stage) is SupabaseConnectedMultiStepActionStage
    coordinator = bundle.chat._multi_step._coordinator
    assert type(coordinator) is ConnectedMultiStepCoordinator
    assert type(coordinator._store) is SupabaseConnectedMultiStepStore
    assert type(coordinator._vault._store) is SupabaseConnectedMultiStepEnvelopeStore
    assert coordinator._vault._active_master_key_id == inputs.keys.loop_envelope.key_id
    assert (
        coordinator._vault._active_commitment_key_id
        == inputs.keys.loop_commitment.key_id
    )
    snapshots = bundle.chat._actions._cancellation_snapshots
    assert type(snapshots) is ConnectedCalendarCancelSnapshotCoordinator
    assert (
        bundle.background._scheduler._resolver._approvals._cancellation_snapshots
        is snapshots
    )
    assert snapshots._runtime is bundle.background._scheduler._runtime
    assert snapshots._authorities is bundle.service._control_plane
    assert type(snapshots._stage) is SupabaseConnectedCalendarCancelSnapshotStage
    assert snapshots._stage._preparations is bundle.service._control_plane
    assert database.calls == []


def test_application_bundle_rejects_partial_multi_step_exposure():
    inputs, *_rest = graph_inputs()
    bundle = ConnectedProductionApplicationFactory(lambda: inputs).build(
        expected_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_GRAPH_INVALID",
    ):
        replace(bundle, multi_step_worker=object())


def test_factory_model_is_owner_bound_and_never_uses_a_global_user():
    inputs, _database, gateway = graph_inputs()
    bundle = ConnectedProductionApplicationFactory(lambda: inputs).build(
        expected_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    model = bundle.chat._plans._planner._model
    result = asyncio.run(
        model.complete(
            owner_id=OWNER_ID,
            system="Bounded connected-app planning system.",
            prompt="List today's meetings.",
            max_tokens=128,
            timeout_seconds=5.0,
        )
    )
    assert result == '{"disposition":"none"}'
    assert gateway.calls == [
        {
            "system": "Bounded connected-app planning system.",
            "prompt": "List today's meetings.",
            "max_tokens": 128,
            "timeout_seconds": 5.0,
            "user_id": OWNER_ID,
            "purpose": "connected_app_plan",
        }
    ]


def test_readiness_is_renewable_and_key_expiry_fences_every_component():
    clock = Clock()
    keys = production_keys(expires_at=NOW + timedelta(minutes=2))
    inputs, _database, _gateway = graph_inputs(keys=keys)
    bundle = ConnectedProductionApplicationFactory(lambda: inputs).build(
        expected_manifest_sha256=MANIFEST,
        now=clock,
    )
    bundle.service.require_ready()
    bundle.chat.require_ready()

    clock.value = NOW + timedelta(minutes=3)
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPS_NOT_READY"):
        bundle.service.require_ready()
    with pytest.raises(Exception, match="CONNECTED_OPERATOR_CHAT_NOT_READY"):
        bundle.chat.require_ready()
    command = ConnectedMultiStepStartCommand.build(
        owner_id=OWNER_ID,
        session_id="22222222-2222-4222-8222-222222222222",
        session_binding_sha256=hashlib.sha256(b"session").hexdigest(),
        chat_id="33333333-3333-4333-8333-333333333333",
        message_id="44444444-4444-4444-8444-444444444444",
        turn_id="55555555-5555-4555-8555-555555555555",
        turn_claim_token="66666666-6666-4666-8666-666666666666",
        time_zone="UTC",
        request_binding_sha256=hashlib.sha256(b"request").hexdigest(),
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    with pytest.raises(ConnectedAppServiceError, match="CONNECTED_APPS_NOT_READY"):
        asyncio.run(bundle.multi_step_worker.cancel(command=command))


def test_factory_rejects_manifest_and_oauth_registration_drift():
    wrong_manifest = hashlib.sha256(b"wrong production graph").hexdigest()
    inputs, _database, _gateway = graph_inputs(
        keys=production_keys(manifest=wrong_manifest),
        ready=readiness(manifest=wrong_manifest),
    )
    with pytest.raises(
        ConnectedProductionGraphError,
        match="CONNECTED_PRODUCTION_GRAPH_NOT_READY",
    ):
        ConnectedProductionApplicationFactory(lambda: inputs).build(
            expected_manifest_sha256=MANIFEST,
            now=lambda: NOW,
        )

    valid, *_rest = graph_inputs()
    bad_redirects = dict(valid.redirect_uris)
    bad_redirects[ConnectorProvider.GOOGLE] = (
        "https://evil.example/api/connected-apps/oauth/callback/google"
    )
    with pytest.raises(
        ConnectedProductionGraphError,
        match="CONNECTED_PRODUCTION_GRAPH_NOT_READY",
    ):
        replace(valid, redirect_uris=bad_redirects)

    expanded_allowlists = dict(valid.redirect_allowlists)
    expanded_allowlists[ConnectorProvider.GOOGLE] = OAuthRedirectAllowlist(
        frozenset(
            {
                valid.redirect_uris[ConnectorProvider.GOOGLE],
                "https://askcrump.com/api/connected-apps/oauth/callback/google",
            }
        )
    )
    with pytest.raises(
        ConnectedProductionGraphError,
        match="CONNECTED_PRODUCTION_GRAPH_NOT_READY",
    ):
        replace(valid, redirect_allowlists=expanded_allowlists)

    duplicate_registrations = dict(valid.registrations)
    duplicate_registrations[ConnectorProvider.MICROSOFT] = ProviderOAuthRegistration(
        provider=ConnectorProvider.MICROSOFT,
        client_id=valid.registrations[ConnectorProvider.GOOGLE].client_id,
        client_secret=ProviderOAuthClientSecret(
            "test-microsoft-replacement-client-secret"
        ),
    )
    with pytest.raises(
        ConnectedProductionGraphError,
        match="CONNECTED_PRODUCTION_GRAPH_NOT_READY",
    ):
        replace(valid, registrations=duplicate_registrations)


def test_factory_rejects_root_identifier_and_domain_key_splicing():
    valid, *_rest = graph_inputs()

    invalid_root = replace(valid.keys, root_key_id="invalid/root")
    with pytest.raises(
        ConnectedProductionGraphError,
        match="CONNECTED_PRODUCTION_GRAPH_NOT_READY",
    ):
        ConnectedProductionApplicationFactory(
            lambda: replace(valid, keys=invalid_root)
        ).build(expected_manifest_sha256=MANIFEST, now=lambda: NOW)

    foreign_readiness = replace(
        valid.keys.readiness_attestation,
        key_id=(
            "foreign-kms-root.readiness_attestation."
            + valid.keys.composition_manifest_sha256[:10]
        ),
    )
    spliced = replace(valid.keys, readiness_attestation=foreign_readiness)
    with pytest.raises(
        ConnectedProductionGraphError,
        match="CONNECTED_PRODUCTION_GRAPH_NOT_READY",
    ):
        ConnectedProductionApplicationFactory(lambda: replace(valid, keys=spliced)).build(
            expected_manifest_sha256=MANIFEST,
            now=lambda: NOW,
        )


def test_factory_quarantines_dependency_details_and_redacts_all_reprs():
    inputs, *_rest = graph_inputs()

    def broken_source():
        raise RuntimeError("raw-oauth-secret-must-never-escape")

    factory = ConnectedProductionApplicationFactory(broken_source)
    with pytest.raises(ConnectedProductionGraphError) as caught:
        factory.build(expected_manifest_sha256=MANIFEST, now=lambda: NOW)
    assert "raw-oauth-secret" not in str(caught.value)
    assert "secret-value" not in repr(inputs)
    assert "secret-value" not in repr(factory)
    with pytest.raises(TypeError):
        pickle.dumps(inputs)
    with pytest.raises(TypeError):
        pickle.dumps(factory)


def test_calendar_preview_dependency_failure_is_redacted_and_exposes_no_routes(
    monkeypatch,
):
    inputs, database, _gateway = graph_inputs()

    def broken_calendar_preview(**_kwargs):
        raise RuntimeError("provider-calendar-secret-must-not-escape")

    monkeypatch.setattr(
        production_module,
        "ConnectedCalendarCancelSnapshotCoordinator",
        broken_calendar_preview,
    )
    with pytest.raises(ConnectedProductionGraphError) as caught:
        ConnectedProductionApplicationFactory(lambda: inputs).build(
            expected_manifest_sha256=MANIFEST,
            now=lambda: NOW,
        )

    assert str(caught.value) == "CONNECTED_PRODUCTION_GRAPH_NOT_READY"
    assert "provider-calendar-secret" not in repr(caught.value)
    assert database.calls == []
    assert connected_routes.connected_app_service is None
    assert connected_routes.connected_read_result_service is None
    assert connected_routes.connected_background_worker is None
    assert chat_routes.connected_operator_chat_service is None


def test_production_composition_has_no_raw_key_env_or_browser_fallback():
    source = inspect.getsource(production_module)
    for forbidden in (
        "os.environ",
        "os.getenv",
        "getenv(",
        "playwright",
        "selenium",
        "browser automation",
    ):
        assert forbidden not in source.casefold()


def test_activation_failure_never_exposes_a_partial_route_graph(monkeypatch):
    clock = Clock()
    inputs, *_rest = graph_inputs(
        keys=production_keys(expires_at=NOW + timedelta(minutes=2))
    )
    bootstrap_module.configure_connected_application_factory(
        ConnectedProductionApplicationFactory(lambda: inputs)
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", MANIFEST)
    monkeypatch.setattr(
        bootstrap_module,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    monkeypatch.setattr(
        connected_routes,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    activation = bootstrap_module.prepare_connected_application_activation(now=clock)
    assert activation is not None
    clock.value = NOW + timedelta(minutes=3)

    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_NOT_READY",
    ):
        asyncio.run(activation.startup())
    assert connected_routes.connected_app_service is None
    assert connected_routes.connected_read_result_service is None
    assert connected_routes.connected_background_worker is None
    assert chat_routes.connected_operator_chat_service is None


def test_application_entrypoint_registers_before_preparing(monkeypatch):
    from backend import application

    order: list[str] = []
    monkeypatch.setattr(
        application,
        "register_connected_production_application_factory",
        lambda: order.append("register"),
    )
    monkeypatch.setattr(
        application,
        "prepare_connected_application_activation",
        lambda: order.append("prepare"),
    )
    application.create_app()
    assert order == ["register", "prepare"]
