from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
from types import SimpleNamespace

import pytest

from backend import connected_app_activation as activation_module
from backend.connected_app_activation import (
    ConnectedApplicationActivation,
    ConnectedApplicationActivationError,
    ConnectedApplicationBundle,
    configure_connected_application_activation,
    connected_application_lifespan,
)
from backend.routes import chat, connected_apps


MANIFEST = hashlib.sha256(b"connected-application-exact-graph").hexdigest()
NOW = datetime(2026, 11, 8, 5, 0, tzinfo=UTC)


class Service:
    def __init__(self, *, ready: bool = True, manifest: str = MANIFEST) -> None:
        self.ready = ready
        self.calls = 0
        self.readiness = SimpleNamespace(composition_manifest_sha256=manifest)

    def require_ready(self) -> None:
        self.calls += 1
        if not self.ready:
            raise RuntimeError("stale")


class Chat:
    def __init__(self, *, ready: bool = True, manifest: str = MANIFEST) -> None:
        self.ready = ready
        self.calls = 0
        self.composition_manifest_sha256 = manifest

    def require_ready(self) -> None:
        self.calls += 1
        if not self.ready:
            raise RuntimeError("stale")

    async def handle(self, request):
        return request


class Results:
    def __init__(self, *, manifest: str = MANIFEST) -> None:
        self.composition_manifest_sha256 = manifest

    async def get(self, *, owner_id: str, result_reference_id: str):
        return owner_id, result_reference_id


class Background:
    def __init__(
        self,
        *,
        fail_start: bool = False,
        external_wake: bool = False,
        manifest: str = MANIFEST,
    ) -> None:
        self.fail_start = fail_start
        self.external_wake = external_wake
        self.composition_manifest_sha256 = manifest
        self.running = False
        self.start_calls = 0
        self.cycle_calls = 0
        self.shutdown_calls = []

    async def startup(self) -> None:
        self.start_calls += 1
        if self.fail_start:
            raise RuntimeError("unavailable")
        self.running = True

    async def run_cycle(self):
        self.cycle_calls += 1
        return None

    async def shutdown(self, *, timeout_seconds: float = 30.0) -> bool:
        self.shutdown_calls.append(timeout_seconds)
        self.running = False
        return True


class MultiStep:
    async def start_from_chat(self, **_kwargs):
        return None

    async def wake(self, **_kwargs):
        return None

    async def cancel(self, **_kwargs):
        return None

    async def status(self, **_kwargs):
        return None

    async def list_status(self, **_kwargs):
        return ()

    async def owner_status(self, **_kwargs):
        return None

    async def cancel_owner(self, **_kwargs):
        return None

    async def resume_after_approval(self, **_kwargs):
        return None


def bundle(
    *,
    service=None,
    operator=None,
    results=None,
    background=None,
    multi_step=None,
    multi_step_released=False,
):
    return ConnectedApplicationBundle(
        service=service or Service(),
        chat=operator or Chat(),
        read_results=results or Results(),
        background=background or Background(),
        composition_manifest_sha256=MANIFEST,
        multi_step_worker=multi_step,
        multi_step_released=multi_step_released,
    )


@pytest.fixture(autouse=True)
def clear_application_graph(monkeypatch):
    activation_module.connected_application_activation = None
    activation_module._activation_transition = None
    activation_module._route_owner = None
    connected_apps.connected_app_service = None
    connected_apps.connected_read_result_service = None
    connected_apps.connected_background_worker = None
    connected_apps.connected_multi_step_worker = None
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    chat.connected_operator_chat_service = None
    yield
    activation_module.connected_application_activation = None
    activation_module._activation_transition = None
    activation_module._route_owner = None
    connected_apps.connected_app_service = None
    connected_apps.connected_read_result_service = None
    connected_apps.connected_background_worker = None
    connected_apps.connected_multi_step_worker = None
    chat.connected_operator_chat_service = None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_released", "environment_enabled"),
    ((False, True), (True, False), (False, False)),
)
async def test_either_release_lock_keeps_every_surface_inert(
    source_released, environment_enabled
):
    value = bundle()
    activation = ConnectedApplicationActivation(
        source_released=source_released,
        environment_enabled=environment_enabled,
        expected_manifest_sha256=MANIFEST,
        bundle=value,
        now=lambda: NOW,
    )
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_NOT_RELEASED",
    ):
        await activation.startup()
    assert value.background.start_calls == 0
    assert connected_apps.connected_app_service is None
    assert connected_apps.connected_read_result_service is None
    assert connected_apps.connected_background_worker is None
    assert chat.connected_operator_chat_service is None


@pytest.mark.asyncio
async def test_manifest_or_service_readiness_drift_fails_before_worker_start():
    for expected, service, operator in (
        (hashlib.sha256(b"wrong").hexdigest(), Service(), Chat()),
        (MANIFEST, Service(ready=False), Chat()),
        (MANIFEST, Service(), Chat(ready=False)),
    ):
        value = bundle(service=service, operator=operator)
        activation = ConnectedApplicationActivation(
            source_released=True,
            environment_enabled=True,
            expected_manifest_sha256=expected,
            bundle=value,
            now=lambda: NOW,
        )
        with pytest.raises(
            ConnectedApplicationActivationError,
            match="CONNECTED_APPLICATION_NOT_READY",
        ):
            await activation.startup()
        assert value.background.start_calls == 0


def test_bundle_refuses_any_component_bound_to_a_different_manifest():
    wrong = hashlib.sha256(b"wrong-component").hexdigest()
    for values in (
        {"service": Service(manifest=wrong)},
        {"operator": Chat(manifest=wrong)},
        {"results": Results(manifest=wrong)},
        {"background": Background(manifest=wrong)},
    ):
        with pytest.raises(
            ConnectedApplicationActivationError,
            match="CONNECTED_APPLICATION_GRAPH_INVALID",
        ):
            bundle(**values)


@pytest.mark.asyncio
async def test_runtime_setting_must_match_activation_environment_gate(monkeypatch):
    value = bundle()
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(connected_apps_enabled=False),
    )
    activation = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=value,
        now=lambda: NOW,
    )
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_NOT_RELEASED",
    ):
        await activation.startup()
    assert value.background.start_calls == 0


@pytest.mark.asyncio
async def test_startup_installs_entire_graph_and_shutdown_clears_before_drain():
    value = bundle()
    activation = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=value,
        shutdown_timeout_seconds=17,
        now=lambda: NOW,
    )
    await activation.startup()
    assert activation.active is True
    assert connected_apps.connected_app_service is value.service
    assert connected_apps.connected_read_result_service is value.read_results
    assert connected_apps.connected_background_worker is None
    assert chat.connected_operator_chat_service is value.chat
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_ALREADY_ACTIVE",
    ):
        await activation.startup()

    assert await activation.shutdown() is True
    assert activation.active is False
    assert connected_apps.connected_app_service is None
    assert connected_apps.connected_read_result_service is None
    assert connected_apps.connected_background_worker is None
    assert chat.connected_operator_chat_service is None
    assert value.background.shutdown_calls == [17.0]


@pytest.mark.asyncio
async def test_worker_start_failure_cannot_publish_a_partial_graph():
    value = bundle(background=Background(fail_start=True))
    activation = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=value,
        now=lambda: NOW,
    )
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_NOT_READY",
    ):
        await activation.startup()
    assert connected_apps.connected_app_service is None
    assert connected_apps.connected_read_result_service is None
    assert connected_apps.connected_background_worker is None
    assert chat.connected_operator_chat_service is None
    assert value.background.shutdown_calls == [30.0]


@pytest.mark.asyncio
async def test_startup_transition_has_one_process_owner_and_owned_shutdown():
    class BlockingBackground(Background):
        def __init__(self) -> None:
            super().__init__()
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def startup(self) -> None:
            self.start_calls += 1
            self.entered.set()
            await self.release.wait()
            self.running = True

    blocking = BlockingBackground()
    first_bundle = bundle(background=blocking)
    second_bundle = bundle()
    first = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=first_bundle,
        now=lambda: NOW,
    )
    second = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=second_bundle,
        now=lambda: NOW,
    )

    first_start = asyncio.create_task(first.startup())
    await asyncio.wait_for(blocking.entered.wait(), timeout=1)
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_ALREADY_ACTIVE",
    ):
        configure_connected_application_activation(second)

    second_start = asyncio.create_task(second.startup())
    blocking.release.set()
    await first_start
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_ALREADY_ACTIVE",
    ):
        await second_start
    assert connected_apps.connected_app_service is first_bundle.service
    assert blocking.running is True
    assert second_bundle.background.running is False

    assert await second.shutdown() is True
    assert connected_apps.connected_app_service is first_bundle.service
    assert first.active is True
    assert await first.shutdown() is True


@pytest.mark.asyncio
async def test_fastapi_lifespan_uses_only_the_preconfigured_exact_activation():
    value = bundle()
    activation = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=value,
        now=lambda: NOW,
    )
    configure_connected_application_activation(activation)
    async with connected_application_lifespan(None):  # type: ignore[arg-type]
        assert activation.active is True
        assert connected_apps.connected_app_service is value.service
        with pytest.raises(
            ConnectedApplicationActivationError,
            match="CONNECTED_APPLICATION_ALREADY_ACTIVE",
        ):
            configure_connected_application_activation(None)
    assert activation.active is False
    assert connected_apps.connected_app_service is None


def test_bundle_and_activation_repr_never_disclose_dependencies():
    value = bundle()
    activation = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=value,
        now=lambda: NOW,
    )
    assert "Service" not in repr(value)
    assert "Background" not in repr(value)
    assert MANIFEST not in repr(value)
    assert MANIFEST not in repr(activation)


@pytest.mark.asyncio
async def test_external_wake_worker_is_installed_and_cleared_only_with_route_owner():
    value = bundle(background=Background(external_wake=True))
    activation = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=value,
        now=lambda: NOW,
    )

    assert connected_apps.connected_background_worker is None
    await activation.startup()
    assert connected_apps.connected_background_worker is value.background
    assert value.background.cycle_calls == 0

    assert await activation.shutdown() is True
    assert connected_apps.connected_background_worker is None


@pytest.mark.asyncio
async def test_multi_step_route_requires_its_separate_source_release_lock():
    worker = MultiStep()
    unreleased_bundle = bundle(multi_step=worker, multi_step_released=False)
    unreleased = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=unreleased_bundle,
        now=lambda: NOW,
    )
    await unreleased.startup()
    assert connected_apps.connected_multi_step_worker is None
    assert await unreleased.shutdown() is True

    released_bundle = bundle(multi_step=worker, multi_step_released=True)
    released = ConnectedApplicationActivation(
        source_released=True,
        environment_enabled=True,
        expected_manifest_sha256=MANIFEST,
        bundle=released_bundle,
        now=lambda: NOW,
    )
    await released.startup()
    assert connected_apps.connected_multi_step_worker is worker
    assert await released.shutdown() is True
    assert connected_apps.connected_multi_step_worker is None


def test_multi_step_release_refuses_a_missing_worker():
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_GRAPH_INVALID",
    ):
        bundle(multi_step=None, multi_step_released=True)
