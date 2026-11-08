from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from backend import connected_app_activation as activation_module
from backend import connected_app_bootstrap as bootstrap
from backend import config
from backend.connected_app_activation import (
    ConnectedApplicationActivationError,
    ConnectedApplicationBundle,
)


MANIFEST = hashlib.sha256(b"connected-production-bootstrap-v1").hexdigest()
NOW = datetime(2026, 11, 8, 7, 0, tzinfo=UTC)


class Service:
    readiness = SimpleNamespace(composition_manifest_sha256=MANIFEST)

    def require_ready(self) -> None:
        return None


class Chat:
    composition_manifest_sha256 = MANIFEST

    def require_ready(self) -> None:
        return None

    async def handle(self, request):
        return request


class Results:
    composition_manifest_sha256 = MANIFEST

    async def get(self, *, owner_id, result_reference_id):
        return owner_id, result_reference_id


class Background:
    composition_manifest_sha256 = MANIFEST
    external_wake = False
    running = False

    async def startup(self) -> None:
        self.running = True

    async def run_cycle(self):
        return None

    async def shutdown(self, *, timeout_seconds=30.0) -> bool:
        self.running = False
        return True


def bundle() -> ConnectedApplicationBundle:
    return ConnectedApplicationBundle(
        service=Service(),
        chat=Chat(),
        read_results=Results(),
        background=Background(),
        composition_manifest_sha256=MANIFEST,
    )


class Factory:
    def __init__(self, value=None, *, fail=False) -> None:
        self.value = value or bundle()
        self.fail = fail
        self.calls = []

    def build(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("secret dependency detail")
        return self.value


@pytest.fixture(autouse=True)
def clear_bootstrap(monkeypatch):
    activation_module.connected_application_activation = None
    activation_module._activation_transition = None
    activation_module._route_owner = None
    bootstrap.connected_application_factory = None
    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)
    monkeypatch.setattr(
        bootstrap,
        "settings",
        SimpleNamespace(connected_apps_enabled=False),
    )
    yield
    activation_module.connected_application_activation = None
    activation_module._activation_transition = None
    activation_module._route_owner = None
    bootstrap.connected_application_factory = None


def test_unreleased_bootstrap_is_inert_without_touching_dependencies(monkeypatch):
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", False)
    factory = Factory()
    bootstrap.configure_connected_application_factory(factory)
    assert bootstrap.prepare_connected_application_activation(now=lambda: NOW) is None
    assert factory.calls == []


def test_exact_released_bootstrap_constructs_and_configures_once(monkeypatch):
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", MANIFEST)
    monkeypatch.setattr(
        bootstrap,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    factory = Factory()
    bootstrap.configure_connected_application_factory(factory)
    activation = bootstrap.prepare_connected_application_activation(now=lambda: NOW)
    assert activation is activation_module.connected_application_activation
    assert activation is bootstrap.prepare_connected_application_activation(now=lambda: NOW)
    assert factory.calls == [
        {"expected_manifest_sha256": MANIFEST, "now": ANY}
    ]


@pytest.mark.parametrize("manifest", ("", "0" * 63, "G" * 64))
def test_released_bootstrap_refuses_unpinned_manifest(monkeypatch, manifest):
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", manifest)
    monkeypatch.setattr(
        bootstrap,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    with pytest.raises(
        ConnectedApplicationActivationError,
        match="CONNECTED_APPLICATION_NOT_READY",
    ):
        bootstrap.prepare_connected_application_activation(now=lambda: NOW)


def test_factory_failure_is_quarantined_and_wrong_manifest_is_refused(monkeypatch):
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", MANIFEST)
    monkeypatch.setattr(
        bootstrap,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    for factory in (
        Factory(fail=True),
        Factory(value=SimpleNamespace(composition_manifest_sha256=MANIFEST)),
    ):
        bootstrap.connected_application_factory = factory
        with pytest.raises(
            ConnectedApplicationActivationError,
            match="CONNECTED_APPLICATION_NOT_READY",
        ) as caught:
            bootstrap.prepare_connected_application_activation(now=lambda: NOW)
        assert "secret dependency detail" not in str(caught.value)
