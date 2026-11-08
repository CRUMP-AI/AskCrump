from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import itertools
from pathlib import Path
import pickle
from types import SimpleNamespace

import httpx
import pytest
from backend import config
from backend import connected_app_activation as activation_module
from backend import connected_app_bootstrap as bootstrap_module
from backend import connected_app_production as production_module
from backend import connected_app_request_activation as request_activation
from backend.connected_app_activation import ConnectedApplicationActivation
from backend.connected_app_key_derivation import (
    ConnectedKeyCustodyKind,
    ConnectedRootKeyMaterial,
)
from backend.connected_app_request_activation import (
    ConnectedRequestActivationCoordinator,
    ConnectedRequestActivationError,
    _ProductionRequestActivationHost,
    acquire_connected_request_activation,
    configure_connected_request_activation,
)


MANIFEST = hashlib.sha256(b"request-scoped-connected-operator").hexdigest()
ATTESTATION = hashlib.sha256(b"reviewed-kms-policy").hexdigest()
TOKEN = "a" * 80 + "." + "b" * 80 + "." + "c" * 80


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 11, 8, 16, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


class Loader:
    def __init__(self, clock: Clock, *, delay: float = 0) -> None:
        self.clock = clock
        self.delay = delay
        self.calls = 0

    async def load(self, *, assertion):
        del assertion
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return ConnectedRootKeyMaterial(
            key_id="gkms1",
            custody=ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS,
            attestation_sha256=ATTESTATION,
            loaded_at=self.clock(),
            expires_at=self.clock() + timedelta(minutes=5),
            secret=hashlib.sha256(b"test-root").digest(),
        )


@dataclass(slots=True)
class Inputs:
    keys: object


class Builder:
    def __init__(self, *, fail: bool = False, delay: float = 0) -> None:
        self.fail = fail
        self.delay = delay
        self.calls = 0

    async def build(self, *, keys, expected_manifest_sha256, assertion):
        assert expected_manifest_sha256 == MANIFEST
        assert "<redacted>" in repr(assertion)
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("secret builder detail")
        return Inputs(keys=keys)


class Activation:
    def __init__(self) -> None:
        self.active = True


class Host:
    def __init__(self) -> None:
        self.installs = 0
        self.replaces = 0
        self.shutdowns = 0

    async def install(self, *, inputs, keys, expected_manifest_sha256, now):
        assert inputs.keys is keys
        assert expected_manifest_sha256 == MANIFEST
        assert now().tzinfo is not None
        self.installs += 1
        return Activation()

    async def replace(self, *, current, inputs, keys, expected_manifest_sha256, now):
        assert current.active is True
        assert inputs.keys is keys
        assert expected_manifest_sha256 == MANIFEST
        assert now().tzinfo is not None
        current.active = False
        self.replaces += 1
        return Activation()

    async def shutdown(self, current):
        current.active = False
        self.shutdowns += 1
        return True


@pytest.fixture(autouse=True)
def released(monkeypatch):
    request_activation.connected_request_activation_coordinator = None
    activation_module.connected_application_activation = None
    activation_module._activation_transition = None
    activation_module._route_owner = None
    bootstrap_module.connected_application_factory = None
    production_module.connected_production_inputs_source = None
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        True,
    )
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", MANIFEST)
    monkeypatch.setattr(
        request_activation,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    yield
    request_activation.connected_request_activation_coordinator = None
    activation_module.connected_application_activation = None
    activation_module._activation_transition = None
    activation_module._route_owner = None
    bootstrap_module.connected_application_factory = None
    production_module.connected_production_inputs_source = None


def coordinator(
    *,
    clock: Clock | None = None,
    loader: Loader | None = None,
    builder: Builder | None = None,
    host: Host | None = None,
) -> tuple[ConnectedRequestActivationCoordinator, Clock, Loader, Builder, Host]:
    selected_clock = clock or Clock()
    selected_loader = loader or Loader(selected_clock)
    selected_builder = builder or Builder()
    selected_host = host or Host()
    value = ConnectedRequestActivationCoordinator(
        root_loader=selected_loader,
        inputs_builder=selected_builder,
        expected_manifest_sha256=MANIFEST,
        host=selected_host,
        now=selected_clock,
        renewal_margin=timedelta(minutes=1),
        drain_timeout_seconds=1,
    )
    return value, selected_clock, selected_loader, selected_builder, selected_host


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preview", "public", "multi"),
    [
        combination
        for combination in itertools.product((False, True), repeat=3)
        if combination != (True, True, True)
    ],
)
async def test_partial_source_lock_never_reads_assertion_or_calls_any_dependency(
    monkeypatch,
    preview,
    public,
    multi,
):
    value, _clock, loader, builder, host = coordinator()
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        preview,
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", public)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", multi)
    reads = 0

    def assertion_source():
        nonlocal reads
        reads += 1
        raise AssertionError("assertion must remain unread")

    with pytest.raises(
        ConnectedRequestActivationError,
        match="CONNECTED_REQUEST_ACTIVATION_NOT_RELEASED",
    ):
        await value.acquire(assertion_source)
    assert (reads, loader.calls, builder.calls, host.installs) == (0, 0, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("assertion_value", [None, "not-a-vercel-assertion"])
async def test_missing_or_invalid_assertion_fails_closed_before_loader(
    assertion_value,
):
    value, _clock, loader, builder, host = coordinator()
    with pytest.raises(
        ConnectedRequestActivationError,
        match="CONNECTED_REQUEST_ACTIVATION_NOT_READY",
    ):
        await value.acquire(lambda: assertion_value)
    assert (loader.calls, builder.calls, host.installs) == (0, 0, 0)


@pytest.mark.asyncio
async def test_false_lock_acquire_does_not_inspect_assertion_source(monkeypatch):
    value, _clock, loader, builder, host = coordinator()
    configure_connected_request_activation(value)
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", False)

    def forbidden_assertion_source():
        raise AssertionError("lock-false acquisition inspected the assertion source")

    assert await acquire_connected_request_activation(forbidden_assertion_source) is None
    assert (loader.calls, builder.calls, host.installs) == (0, 0, 0)


@pytest.mark.asyncio
async def test_concurrent_first_requests_have_one_kms_and_install_winner():
    clock = Clock()
    loader = Loader(clock, delay=0.02)
    value, _clock, loader, builder, host = coordinator(clock=clock, loader=loader)
    first, second = await asyncio.gather(
        value.acquire(lambda: TOKEN),
        value.acquire(lambda: TOKEN),
    )
    assert (loader.calls, builder.calls, host.installs, value.in_flight) == (1, 1, 1, 2)
    await first.release()
    await second.release()
    assert value.in_flight == 0

    reads = 0

    def must_not_refresh():
        nonlocal reads
        reads += 1
        return TOKEN

    third = await value.acquire(must_not_refresh)
    assert reads == 0
    await third.release()


@pytest.mark.asyncio
async def test_configuration_cannot_remove_an_in_progress_activation():
    class BlockingLoader(Loader):
        def __init__(self, clock):
            super().__init__(clock)
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def load(self, *, assertion):
            self.entered.set()
            await self.release.wait()
            return await super().load(assertion=assertion)

    clock = Clock()
    loader = BlockingLoader(clock)
    value, _clock, _loader, _builder, _host = coordinator(
        clock=clock,
        loader=loader,
    )
    configure_connected_request_activation(value)
    acquisition = asyncio.create_task(value.acquire(lambda: TOKEN))
    await asyncio.wait_for(loader.entered.wait(), timeout=1)
    with pytest.raises(
        ConnectedRequestActivationError,
        match="CONNECTED_REQUEST_ACTIVATION_NOT_READY",
    ):
        configure_connected_request_activation(None)
    loader.release.set()
    lease = await acquisition
    await lease.release()
    assert await value.shutdown() is True


@pytest.mark.asyncio
async def test_renewal_blocks_new_entries_and_waits_for_existing_request_to_drain():
    value, clock, loader, _builder, host = coordinator()
    first = await value.acquire(lambda: TOKEN)
    clock.value += timedelta(minutes=4, seconds=10)
    second_task = asyncio.create_task(value.acquire(lambda: TOKEN))
    for _ in range(100):
        if loader.calls == 2:
            break
        await asyncio.sleep(0.005)
    assert loader.calls == 2
    assert host.replaces == 0
    assert not second_task.done()

    await first.release()
    second = await asyncio.wait_for(second_task, timeout=1)
    assert host.replaces == 1
    assert value.in_flight == 1
    await second.release()


@pytest.mark.asyncio
async def test_renewal_failure_clears_stopped_graph_before_a_fresh_install():
    class OneFailedReplacementHost(Host):
        def __init__(self) -> None:
            super().__init__()
            self.fail_next_replacement = True

        async def replace(self, **kwargs):
            if self.fail_next_replacement:
                self.fail_next_replacement = False
                kwargs["current"].active = False
                self.replaces += 1
                raise RuntimeError("private replacement failure")
            return await super().replace(**kwargs)

    selected_host = OneFailedReplacementHost()
    value, clock, _loader, _builder, host = coordinator(host=selected_host)
    first = await value.acquire(lambda: TOKEN)
    await first.release()
    clock.value += timedelta(minutes=4, seconds=10)

    with pytest.raises(
        ConnectedRequestActivationError,
        match="CONNECTED_REQUEST_ACTIVATION_NOT_READY",
    ):
        await value.acquire(lambda: TOKEN)
    assert value.active is False
    assert host.replaces == 1

    recovered = await value.acquire(lambda: TOKEN)
    assert host.installs == 2
    await recovered.release()


@pytest.mark.asyncio
async def test_transition_timeout_is_bounded_and_never_installs_graph():
    value, _clock, loader, builder, host = coordinator(
        builder=Builder(delay=0.1)
    )
    value._drain_timeout_seconds = 0.02
    with pytest.raises(
        ConnectedRequestActivationError,
        match="CONNECTED_REQUEST_ACTIVATION_DRAIN_TIMEOUT",
    ):
        await value.acquire(lambda: TOKEN)
    assert (loader.calls, builder.calls, host.installs) == (1, 1, 0)


@pytest.mark.asyncio
async def test_shutdown_waits_for_counted_request_then_drains_once():
    value, _clock, _loader, _builder, host = coordinator()
    lease = await value.acquire(lambda: TOKEN)
    shutdown = asyncio.create_task(value.shutdown())
    await asyncio.sleep(0)
    assert host.shutdowns == 0
    await lease.release()
    assert await asyncio.wait_for(shutdown, timeout=1) is True
    assert host.shutdowns == 1
    with pytest.raises(
        ConnectedRequestActivationError,
        match="CONNECTED_REQUEST_ACTIVATION_CLOSED",
    ):
        await value.acquire(lambda: TOKEN)


@pytest.mark.asyncio
async def test_shutdown_during_first_activation_owns_and_drains_started_graph():
    class BlockingHost(Host):
        def __init__(self):
            super().__init__()
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def install(self, **kwargs):
            activation = await super().install(**kwargs)
            self.entered.set()
            await self.release.wait()
            return activation

    clock = Clock()
    selected_host = BlockingHost()
    value, _clock, _loader, _builder, host = coordinator(
        clock=clock,
        host=selected_host,
    )
    acquisition = asyncio.create_task(value.acquire(lambda: TOKEN))
    await asyncio.wait_for(selected_host.entered.wait(), timeout=1)
    shutdown = asyncio.create_task(value.shutdown())
    await asyncio.sleep(0)
    selected_host.release.set()
    with pytest.raises(
        ConnectedRequestActivationError,
        match="CONNECTED_REQUEST_ACTIVATION_CLOSED",
    ):
        await acquisition
    assert await asyncio.wait_for(shutdown, timeout=1) is True
    assert (host.installs, host.shutdowns, value.active) == (1, 1, False)


def test_application_does_not_install_a_broad_request_activation_middleware():
    source = (Path(__file__).resolve().parents[1] / "backend" / "application.py").read_text(
        encoding="utf-8"
    )
    assert "connected_request_activation_middleware" not in source


@pytest.mark.asyncio
async def test_fastapi_post_auth_route_contains_activation_failure(monkeypatch):
    from backend.application import create_app
    from backend.routes import connected_apps as connected_routes

    value, _clock, loader, builder, host = coordinator(builder=Builder(fail=True))
    configure_connected_request_activation(value)
    monkeypatch.setattr(
        connected_routes,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )

    async def authenticated_owner(_request):
        return (
            "00000000-0000-4000-8000-000000000001",
            "00000000-0000-4000-8000-000000000002",
        )

    monkeypatch.setattr(connected_routes, "_owner", authenticated_owner)
    application = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="https://www.askcrump.com",
    ) as client:
        health = await client.get("/api/health")
        connected = await client.get(
            "/api/connected-apps/connections",
            headers={"x-vercel-oidc-token": TOKEN},
        )
    assert health.status_code == 200
    assert health.json()["success"] is True
    assert connected.status_code == 503
    assert connected.json() == {
        "success": False,
        "code": "CONNECTED_APPS_NOT_READY",
        "retryable": True,
    }
    assert TOKEN.encode("ascii") not in connected.content
    assert connected.headers["x-content-type-options"] == "nosniff"
    assert connected.headers["cache-control"] == "no-store"
    assert (loader.calls, builder.calls, host.installs) == (1, 1, 0)


def test_repr_and_configuration_never_expose_loader_builder_or_manifest():
    value, *_rest = coordinator()
    assert MANIFEST not in repr(value)
    assert "Loader" not in repr(value)
    assert "Builder" not in repr(value)
    with pytest.raises(TypeError):
        pickle.dumps(value)
    configure_connected_request_activation(value)
    with pytest.raises(ConnectedRequestActivationError):
        configure_connected_request_activation(object())  # type: ignore[arg-type]


def test_request_activation_source_has_no_oidc_environment_or_logging_fallback():
    source = Path(request_activation.__file__).read_text(encoding="utf-8")
    assert "VERCEL_OIDC_TOKEN" not in source
    assert "os.environ" not in source
    assert "getenv(" not in source
    assert "logger." not in source


def test_coordinator_requires_drain_budget_shorter_than_renewal_margin():
    clock = Clock()
    with pytest.raises(
        ConnectedRequestActivationError,
        match="CONNECTED_REQUEST_ACTIVATION_INVALID",
    ):
        ConnectedRequestActivationCoordinator(
            root_loader=Loader(clock),
            inputs_builder=Builder(),
            expected_manifest_sha256=MANIFEST,
            host=Host(),
            now=clock,
            renewal_margin=timedelta(seconds=30),
            drain_timeout_seconds=30,
        )


def test_application_factory_defers_eager_graph_when_request_edge_is_configured(
    monkeypatch,
):
    from backend import application

    order: list[str] = []
    monkeypatch.setattr(
        application,
        "connected_request_activation_deferred",
        lambda: True,
    )
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
    assert order == []


@pytest.mark.asyncio
async def test_production_host_clears_inactive_global_after_startup_failure(
    monkeypatch,
):
    host = _ProductionRequestActivationHost()
    candidate = object.__new__(ConnectedApplicationActivation)
    candidate._active = False

    monkeypatch.setattr(
        _ProductionRequestActivationHost,
        "_require_inputs",
        staticmethod(lambda _inputs, _keys, _manifest: None),
    )

    def register():
        factory = production_module.ConnectedProductionApplicationFactory(
            lambda: object()  # type: ignore[arg-type,return-value]
        )
        bootstrap_module.connected_application_factory = factory
        return factory

    def prepare(*, now):
        del now
        activation_module.connected_application_activation = candidate
        return candidate

    async def fail_startup(_self):
        raise RuntimeError("private startup failure")

    monkeypatch.setattr(
        production_module,
        "register_connected_production_application_factory",
        register,
    )
    monkeypatch.setattr(
        bootstrap_module,
        "prepare_connected_application_activation",
        prepare,
    )
    monkeypatch.setattr(ConnectedApplicationActivation, "startup", fail_startup)

    with pytest.raises(RuntimeError, match="private startup failure"):
        await host.install(
            inputs=object(),
            keys=object(),  # type: ignore[arg-type]
            expected_manifest_sha256=MANIFEST,
            now=Clock(),
        )
    assert activation_module.connected_application_activation is None
    assert host._inputs is None


@pytest.mark.asyncio
async def test_production_host_rolls_back_partial_source_registration(monkeypatch):
    host = _ProductionRequestActivationHost()
    monkeypatch.setattr(
        _ProductionRequestActivationHost,
        "_require_inputs",
        staticmethod(lambda _inputs, _keys, _manifest: None),
    )

    def fail_registration():
        raise RuntimeError("private registration failure")

    monkeypatch.setattr(
        production_module,
        "register_connected_production_application_factory",
        fail_registration,
    )
    with pytest.raises(RuntimeError, match="private registration failure"):
        await host.install(
            inputs=object(),
            keys=object(),  # type: ignore[arg-type]
            expected_manifest_sha256=MANIFEST,
            now=Clock(),
        )
    assert production_module.connected_production_inputs_source is None
    assert bootstrap_module.connected_application_factory is None
    assert host._inputs is None
