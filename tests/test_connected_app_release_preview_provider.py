from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from backend import config
from backend.connected_app_contracts import (
    ConnectedAccountRef,
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    CredentialHandleRef,
)
from backend.connected_app_credential_vault import ConnectedCredentialMasterKey
from backend.connected_app_grant_cleanup import ProviderGrantRevocationSecret
from backend.connected_app_host_configuration import (
    ConnectedReleasePreviewConnectionConfiguration,
)
from backend.connected_app_https import ConnectedAccessToken
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_provider_oauth import (
    ProviderOAuthAccessToken,
    ProviderOAuthClientSecret,
    ProviderOAuthQuarantineRequired,
    ProviderOAuthQuarantineTokenSet,
    ProviderOAuthRefreshToken,
    ProviderOAuthRegistration,
    ProviderOAuthTokenBinding,
)
from backend.connected_app_release_preview_provider import (
    ConnectedGoogleReleasePreviewProbe,
    ConnectedMicrosoftReleasePreviewProbe,
    ConnectedPreparedReleasePreviewCredential,
    ConnectedReleasePreviewCredentialSource,
    ConnectedReleasePreviewProviderError,
)
from backend.connected_app_release_preview import (
    ConnectedReleasePreviewError,
    ConnectedReleasePreviewHarness,
)
from backend.connected_app_release_effect_ledger import (
    ConnectedReleasePreviewAuthorityPhase,
    ConnectedReleasePreviewEffectLedger,
    ConnectedReleasePreviewEffectPhase,
)
from backend.connected_app_scopes import delegated_scope_plan


NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
OWNER = str(uuid4())
INVOCATION = str(uuid4())
CONTRACT = hashlib.sha256(b"provider-preview-contract").hexdigest()
EXTERNAL = hashlib.sha256(b"dedicated-preview-account").hexdigest()


class NoDatabase:
    async def rpc(self, *_args, **_kwargs):
        raise AssertionError("monkeypatched credential preparation touched the database")


class EffectDatabase:
    def __init__(self) -> None:
        self.effects: list[dict[str, object]] = []
        self.authorities: list[dict[str, object]] = []
        self.failed = False

    async def rpc(self, name, payload, *, retry_transient=False):
        del retry_transient
        if name == "connected_app_release_preview_begin_v1":
            if not self.effects:
                self.effects = [
                    {
                        **row,
                        "invocation_id": payload["p_invocation_id"],
                        "phase": "pending",
                        "revision": 0,
                        "artifact_id_sha256": None,
                    }
                    for row in payload["p_effects"]
                ]
                self.authorities = [
                    {
                        "invocation_id": payload["p_invocation_id"],
                        "provider": provider,
                        "account_kind": kind,
                        "phase": "pending",
                        "revision": 0,
                        "provider_receipt_sha256": None,
                    }
                    for provider, kind in (
                        ("google", payload["p_google_account_kind"]),
                        ("microsoft", "personal"),
                        ("microsoft", "work_school"),
                    )
                ]
            return {"created": True}
        if name == "connected_app_release_preview_status_v1":
            return [dict(row) for row in self.effects]
        if name == "connected_app_release_preview_authority_status_v1":
            return [dict(row) for row in self.authorities]
        if name == "connected_app_release_preview_effect_v1":
            row = next(
                item
                for item in self.effects
                if item["effect_id"] == payload["p_effect_id"]
            )
            assert row["phase"] == payload["p_expected_phase"]
            assert row["revision"] == payload["p_expected_revision"]
            row["phase"] = payload["p_next_phase"]
            row["revision"] = int(row["revision"]) + 1
            if payload["p_artifact_id_sha256"] is not None:
                row["artifact_id_sha256"] = payload["p_artifact_id_sha256"]
            return dict(row)
        if name == "connected_app_release_preview_authority_v1":
            row = next(
                item
                for item in self.authorities
                if item["provider"] == payload["p_provider"]
                and item["account_kind"] == payload["p_account_kind"]
            )
            assert row["phase"] == payload["p_expected_phase"]
            assert row["revision"] == payload["p_expected_revision"]
            row["phase"] = payload["p_next_phase"]
            row["revision"] = int(row["revision"]) + 1
            row["provider_receipt_sha256"] = payload[
                "p_provider_receipt_sha256"
            ]
            return dict(row)
        if name == "connected_app_release_preview_fail_v1":
            if any(row["phase"] != "local_retired" for row in self.authorities):
                raise RuntimeError("authority unsettled")
            if any(row["phase"] in {"observed", "cleanup"} for row in self.effects):
                raise RuntimeError("artifact unsettled")
            for row in self.effects:
                if row["phase"] in {"pending", "dispatched"}:
                    row["phase"] = "effect_unknown"
                    row["revision"] = int(row["revision"]) + 1
            self.failed = True
            return {
                "invocation_id": payload["p_invocation_id"],
                "status": "failed",
                "unknown_effects": sum(
                    row["phase"] == "effect_unknown" for row in self.effects
                ),
            }
        raise AssertionError(name)


class TokenSource:
    async def issue_access_token(self, *, account, credential):
        return ConnectedAccessToken(
            owner_id=account.owner_id,
            connection_id=account.connection_id,
            provider=account.provider,
            credential_handle_sha256=hashlib.sha256(
                credential.handle_id.encode("utf-8")
            ).hexdigest(),
            expires_at=NOW + timedelta(minutes=30),
            token="preview-access-token-" + "x" * 48,
        )


class RetirementController:
    def __init__(self) -> None:
        self.retired: list[tuple[ConnectorProvider, ConnectorResource, str]] = []

    async def retire(self, prepared, *, invocation_id):
        self.retired.append(
            (prepared.account.provider, prepared.account.resource, invocation_id)
        )


class NoVault:
    async def erase(self, **_kwargs):
        return None


class NoSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class RetirementDatabase:
    def __init__(self, descriptor, credential_id: str) -> None:
        self.descriptor = descriptor
        self.credential_id = credential_id
        self.erased = False
        self.revoked = False
        self.fail_before_commit = 0
        self.lose_after_commit = False
        self.retirement_calls = 0
        self.events: list[str] = []

    def binding(self) -> dict[str, object]:
        return {
            "owner_id": self.descriptor.owner_id,
            "connection_id": self.descriptor.connection_id,
            "provider": self.descriptor.provider.value,
            "resource": self.descriptor.resource.value,
            "account_kind": self.descriptor.account_kind.value,
            "connection_incarnation_id": (
                self.descriptor.connection_incarnation_id
            ),
            "authorization_revision": 2 if self.revoked else 1,
            "authorization_state": "revoked" if self.revoked else "active",
            "authorization_snapshot_sha256": (
                self.descriptor.authorization_snapshot_sha256
            ),
            "authorization_issued_at": NOW.isoformat(),
            "granted_actions": sorted(
                action.value for action in self.descriptor.granted_actions
            ),
            "granted_actions_sha256": hashlib.sha256(b"actions").hexdigest(),
            "granted_scopes_sha256": hashlib.sha256(b"scopes").hexdigest(),
            "external_account_id_sha256": (
                self.descriptor.external_account_id_hash
            ),
            "broker_credential_ref": None if self.revoked else self.credential_id,
            "credential_ref_sha256": (
                None
                if self.revoked
                else self.descriptor.credential_handle_sha256
            ),
            "current_flow_nonce_sha256": (
                None if self.revoked else self.descriptor.current_flow_nonce_sha256
            ),
            "authorization_expires_at": (
                None if self.revoked else (NOW + timedelta(hours=1)).isoformat()
            ),
            "revoked_at": NOW.isoformat() if self.revoked else None,
        }

    async def rpc(self, name, payload, *, retry_transient=False):
        del retry_transient
        if name == "connected_app_get_binding_v2":
            return self.binding()
        if name == "connected_app_credential_read_v1":
            assert payload == {
                "p_credential_handle_sha256": (
                    self.descriptor.credential_handle_sha256
                )
            }
            return {
                "status": "erased" if self.erased else "present",
                "record": None if self.erased else {"redacted": True},
            }
        if name != "connected_app_release_preview_retire_connection_v1":
            raise AssertionError(name)
        self.events.append("retire")
        self.retirement_calls += 1
        assert self.erased is True
        if self.fail_before_commit:
            self.fail_before_commit -= 1
            raise TimeoutError
        self.revoked = True
        result = {
            "retired": True,
            "retirement_id": payload["p_retirement_id"],
            "retirement_binding_sha256": payload[
                "p_retirement_binding_sha256"
            ],
            "connection_id": self.descriptor.connection_id,
            "authorization_revision": 2,
            "revoked_at": NOW.isoformat(),
            "credential_erased": True,
        }
        if self.lose_after_commit:
            self.lose_after_commit = False
            raise TimeoutError
        return result


class RetirementVault:
    def __init__(self, database: RetirementDatabase) -> None:
        self.database = database
        self.calls = 0

    async def erase(self, **_kwargs) -> None:
        self.calls += 1
        self.database.events.append("erase")
        self.database.erased = True


def _actions(
    provider: ConnectorProvider,
    resource: ConnectorResource,
    account_kind: ConnectorAccountKind,
) -> frozenset[ConnectorActionKind]:
    if resource is ConnectorResource.MAIL:
        return frozenset(
            {
                ConnectorActionKind.MAIL_SEARCH,
                ConnectorActionKind.MAIL_CREATE_DRAFT,
                ConnectorActionKind.MAIL_SEND,
                ConnectorActionKind.MAIL_REPLY,
            }
        )
    actions = {
        ConnectorActionKind.CALENDAR_LIST,
        ConnectorActionKind.CALENDAR_CREATE,
        ConnectorActionKind.CALENDAR_UPDATE,
        ConnectorActionKind.CALENDAR_CANCEL,
    }
    if (
        provider is ConnectorProvider.GOOGLE
        or account_kind is ConnectorAccountKind.WORK_SCHOOL
    ):
        actions.add(ConnectorActionKind.CALENDAR_FREE_BUSY)
    return frozenset(actions)


def _registration(provider: ConnectorProvider) -> ProviderOAuthRegistration:
    client_id = (
        "preview.apps.googleusercontent.com"
        if provider is ConnectorProvider.GOOGLE
        else "00000000-0000-4000-8000-000000000099"
    )
    return ProviderOAuthRegistration(
        provider=provider,
        client_id=client_id,
        client_secret=ProviderOAuthClientSecret("client-secret-material-" + "z" * 32),
    )


def _sources_and_prepared(
    provider: ConnectorProvider,
    *,
    account_kind: ConnectorAccountKind = ConnectorAccountKind.PERSONAL,
):
    registration = _registration(provider)
    database = NoDatabase()
    controller = RetirementController()
    sources = {}
    prepared = {}
    for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR):
        connection_id = str(uuid4())
        incarnation = str(uuid4())
        completion = str(uuid4())
        handle = str(uuid4())
        actions = _actions(provider, resource, account_kind)
        scopes = frozenset(
            delegated_scope_plan(
                provider,
                actions,
                account_kind=account_kind,
            ).delegated_scopes
        )
        descriptor = ConnectedReleasePreviewConnectionConfiguration(
            provider=provider,
            resource=resource,
            owner_id=OWNER,
            connection_id=connection_id,
            connection_incarnation_id=incarnation,
            oauth_completion_id=completion,
            oauth_completion_binding_sha256=hashlib.sha256(
                f"completion:{connection_id}".encode()
            ).hexdigest(),
            current_flow_nonce_sha256=hashlib.sha256(
                f"flow:{connection_id}".encode()
            ).hexdigest(),
            credential_handle_sha256=hashlib.sha256(handle.encode()).hexdigest(),
            account_kind=account_kind,
            external_account_id_hash=EXTERNAL,
            authorization_snapshot_sha256=hashlib.sha256(
                f"authorization:{connection_id}".encode()
            ).hexdigest(),
            granted_actions=actions,
            granted_scopes=scopes,
        )
        sources[resource] = ConnectedReleasePreviewCredentialSource(
            database=database,
            credential_key=ConnectedCredentialMasterKey("preview-key", b"k" * 32),
            registration=registration,
            descriptor=descriptor,
            now=lambda: NOW,
        )
        account = ConnectedAccountRef(
            owner_id=OWNER,
            connection_id=connection_id,
            provider=provider,
            resource=resource,
            account_kind=account_kind,
            external_account_id_hash=EXTERNAL,
        )
        credential = CredentialHandleRef(
            owner_id=OWNER,
            connection_id=connection_id,
            provider=provider,
            handle_id=handle,
        )
        prepared[resource] = ConnectedPreparedReleasePreviewCredential(
            account=account,
            credential=credential,
            connection_incarnation_id=incarnation,
            source=TokenSource(),  # type: ignore[arg-type]
            refresh_token=ProviderGrantRevocationSecret("r" * 48),
            vault=NoVault(),  # type: ignore[arg-type]
            controller=controller,  # type: ignore[arg-type]
            authorization_revision=1,
            authorization_snapshot_sha256=descriptor.authorization_snapshot_sha256,
            current_flow_nonce_sha256=descriptor.current_flow_nonce_sha256,
        )
    return registration, sources, prepared, controller


async def _dispatched_ledger(
    provider: ConnectorProvider,
    *,
    account_kind: ConnectorAccountKind,
) -> tuple[ConnectedReleasePreviewEffectLedger, EffectDatabase]:
    database = EffectDatabase()
    ledger = ConnectedReleasePreviewEffectLedger(
        database=database,
        invocation_id=INVOCATION,
    )
    await ledger.begin(
        google_account_kind=(
            account_kind
            if provider is ConnectorProvider.GOOGLE
            else ConnectorAccountKind.PERSONAL
        ),
        descriptor_matrix_sha256=CONTRACT,
        dedicated_account_attestation_sha256=CONTRACT,
        deployment={
            "composition_manifest_sha256": CONTRACT,
            "database_contract_sha256": CONTRACT,
            "database_target_fingerprint": "1" * 32,
            "provider_contract_sha256": CONTRACT,
            "deployment_id": "dpl_12345678abcd",
            "commit_sha": "a" * 40,
            "host_configuration_ciphertext_sha256": CONTRACT,
            "root_key_id": "gkms1",
        },
        release_preview_contract_sha256=CONTRACT,
    )
    for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR):
        state = await ledger.state_for(
            provider=provider,
            account_kind=account_kind,
            resource=resource,
        )
        await ledger.transition(
            state=state,
            next_phase=ConnectedReleasePreviewEffectPhase.DISPATCHED,
        )
    return ledger, database


async def _terminal_google_effects(
    ledger: ConnectedReleasePreviewEffectLedger,
) -> None:
    for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR):
        state = await ledger.state_for(
            provider=ConnectorProvider.GOOGLE,
            account_kind=ConnectorAccountKind.PERSONAL,
            resource=resource,
        )
        state = await ledger.transition(
            state=state,
            next_phase=ConnectedReleasePreviewEffectPhase.OBSERVED,
            artifact_id="artifact-" + resource.value,
        )
        state = await ledger.transition(
            state=state,
            next_phase=ConnectedReleasePreviewEffectPhase.CLEANUP,
        )
        await ledger.transition(
            state=state,
            next_phase=(
                ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
                if resource is ConnectorResource.MAIL
                else ConnectedReleasePreviewEffectPhase.CLEAN
            ),
        )


async def _google_authority_phase(
    ledger: ConnectedReleasePreviewEffectLedger,
    phase: ConnectedReleasePreviewAuthorityPhase,
) -> None:
    state = await ledger.authority_for(
        provider=ConnectorProvider.GOOGLE,
        account_kind=ConnectorAccountKind.PERSONAL,
    )
    state = await ledger.transition_authority(
        state=state,
        next_phase=ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED,
    )
    if phase is ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED:
        await ledger.transition_authority(
            state=state,
            next_phase=ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED,
            provider_receipt_sha256=CONTRACT,
        )
    elif phase is not ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED:
        raise AssertionError(phase)


@pytest.fixture(autouse=True)
def release_locks(monkeypatch):
    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)


@pytest.mark.asyncio
async def test_google_exact_effects_cleanup_single_grant_revoke_and_local_retirement(
    monkeypatch,
) -> None:
    registration, sources, prepared, controller = _sources_and_prepared(
        ConnectorProvider.GOOGLE
    )

    async def prepare(self, **_kwargs):
        return prepared[self._descriptor.resource]

    monkeypatch.setattr(ConnectedReleasePreviewCredentialSource, "prepare", prepare)
    state: dict[str, object] = {
        "draft": None,
        "event": None,
        "calls": [],
        "sent": {},
    }

    def provider_handler(request: httpx.Request) -> httpx.Response:
        state["calls"].append((request.method, request.url.path, request.url.query))
        path = request.url.path
        if path.endswith("/profile") and request.method == "GET":
            return httpx.Response(200, json={"emailAddress": "preview@example.invalid"})
        if path.endswith("/messages/send") and request.method == "POST":
            body = json.loads(request.content)
            sent = state["sent"]
            message_id = f"sent-{len(sent) + 1}"
            thread_id = body.get("threadId", "thread-1")
            sent[message_id] = {"raw": body["raw"], "threadId": thread_id}
            return httpx.Response(
                200,
                json={"id": message_id, "threadId": thread_id},
            )
        if "/messages/sent-" in path and request.method == "GET":
            message_id = path.rsplit("/", 1)[-1]
            sent = state["sent"]
            return httpx.Response(
                200,
                json={"id": message_id, **sent[message_id]},
            )
        if path.endswith("/messages") and request.method == "GET":
            return httpx.Response(200, json={"messages": [], "resultSizeEstimate": 0})
        if path.endswith("/drafts") and request.method == "POST":
            body = json.loads(request.content)
            state["draft"] = body["message"]["raw"]
            return httpx.Response(200, json={"id": "draft-1"})
        if path.endswith("/drafts") and request.method == "GET":
            return httpx.Response(200, json={"drafts": [], "resultSizeEstimate": 0})
        if path.endswith("/drafts/draft-1") and request.method == "GET":
            if state["draft"] is None:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={"id": "draft-1", "message": {"raw": state["draft"]}},
            )
        if path.endswith("/drafts/draft-1") and request.method == "DELETE":
            state["draft"] = None
            return httpx.Response(204)
        if path.endswith("/events") and request.method == "GET":
            return httpx.Response(200, json={"items": []})
        if path.endswith("/freeBusy") and request.method == "POST":
            return httpx.Response(
                200,
                json={"calendars": {"primary": {"busy": []}}},
            )
        if path.endswith("/events") and request.method == "POST":
            body = json.loads(request.content)
            state["event"] = body
            return httpx.Response(200, json={"id": body["id"]})
        if "/events/" in path and request.method == "GET":
            event = state["event"]
            if event is None:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={
                    "id": event["id"],
                    "etag": '"etag-1"',
                    "summary": event["summary"],
                    "description": event["description"],
                        "status": "confirmed",
                        "attendees": [],
                        "organizer": {"self": True},
                        "extendedProperties": event["extendedProperties"],
                },
            )
        if "/events/" in path and request.method == "PATCH":
            state["event"]["description"] = json.loads(request.content)["description"]
            return httpx.Response(200, json={"id": state["event"]["id"]})
        if "/events/" in path and request.method == "DELETE":
            state["event"] = None
            return httpx.Response(204)
        raise AssertionError((request.method, str(request.url)))

    revoke_calls = []

    def revoke_handler(request: httpx.Request) -> httpx.Response:
        revoke_calls.append(request)
        return httpx.Response(200, json={})

    probe = ConnectedGoogleReleasePreviewProbe(
        sources=sources,
        contract_sha256=CONTRACT,
        provider_transport=httpx.MockTransport(provider_handler),
        revoke_transport=httpx.MockTransport(revoke_handler),
        sleep=NoSleep(),
        now=lambda: NOW,
    )
    try:
        receipt = await probe.preview(
            registration=registration,
            redirect_uri="https://www.askcrump.com/api/connected-apps/oauth/callback/google",
            invocation_id=INVOCATION,
            contract_sha256=CONTRACT,
        )
    except ConnectedReleasePreviewProviderError:
        pytest.fail("google calls:\n" + "\n".join(map(str, state["calls"])))
    assert receipt.provider_grant_revocation_attested is True
    assert receipt.local_connection_retirement_attested is True
    assert state["draft"] is None and state["event"] is None
    assert len(revoke_calls) == 1
    assert len(controller.retired) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "mode"),
    (
        (ConnectorProvider.GOOGLE, "mail_prepare_fails"),
        (ConnectorProvider.GOOGLE, "calendar_prepare_fails"),
        (ConnectorProvider.GOOGLE, "account_mismatch"),
        (ConnectorProvider.MICROSOFT, "mail_prepare_fails"),
        (ConnectorProvider.MICROSOFT, "calendar_prepare_fails"),
        (ConnectorProvider.MICROSOFT, "account_mismatch"),
    ),
)
async def test_partial_prepare_or_account_mismatch_retires_entire_group(
    monkeypatch,
    provider,
    mode,
) -> None:
    account_kind = ConnectorAccountKind.PERSONAL
    registration, sources, prepared, _controller = _sources_and_prepared(
        provider,
        account_kind=account_kind,
    )
    if mode == "account_mismatch":
        original = prepared[ConnectorResource.CALENDAR].account
        prepared[ConnectorResource.CALENDAR].account = ConnectedAccountRef(
            owner_id=original.owner_id,
            connection_id=original.connection_id,
            provider=original.provider,
            resource=original.resource,
            account_kind=original.account_kind,
            external_account_id_hash=hashlib.sha256(b"different-account").hexdigest(),
        )

    async def prepare(self, **_kwargs):
        if (
            (mode == "mail_prepare_fails"
             and self._descriptor.resource is ConnectorResource.MAIL)
            or (mode == "calendar_prepare_fails"
                and self._descriptor.resource is ConnectorResource.CALENDAR)
        ):
            raise ConnectedReleasePreviewProviderError()
        return prepared[self._descriptor.resource]

    async def revocation_secret(self):
        return ProviderGrantRevocationSecret("r" * 48)

    retired: list[ConnectorResource] = []

    async def retire_descriptor(self, *, invocation_id):
        assert invocation_id == INVOCATION
        retired.append(self._descriptor.resource)

    monkeypatch.setattr(ConnectedReleasePreviewCredentialSource, "prepare", prepare)
    monkeypatch.setattr(
        ConnectedReleasePreviewCredentialSource,
        "revocation_secret",
        revocation_secret,
    )
    monkeypatch.setattr(
        ConnectedReleasePreviewCredentialSource,
        "retire_descriptor",
        retire_descriptor,
    )
    ledger, _database = await _dispatched_ledger(
        provider,
        account_kind=account_kind,
    )
    revoke_calls: list[httpx.Request] = []

    def revoke(request: httpx.Request) -> httpx.Response:
        revoke_calls.append(request)
        return httpx.Response(200)

    common = {
        "sources": sources,
        "contract_sha256": CONTRACT,
        "provider_transport": httpx.MockTransport(
            lambda request: pytest.fail(f"provider effect dispatched: {request.url}")
        ),
        "sleep": NoSleep(),
        "now": lambda: NOW,
    }
    if provider is ConnectorProvider.GOOGLE:
        probe = ConnectedGoogleReleasePreviewProbe(
            **common,
            revoke_transport=httpx.MockTransport(revoke),
        )
        redirect = (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
        )
    else:
        probe = ConnectedMicrosoftReleasePreviewProbe(**common)
        redirect = (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
        )
    with pytest.raises(ConnectedReleasePreviewProviderError):
        await probe.preview(
            registration=registration,
            redirect_uri=redirect,
            invocation_id=INVOCATION,
            contract_sha256=CONTRACT,
            effect_ledger=ledger,
        )
    assert set(retired) == {ConnectorResource.MAIL, ConnectorResource.CALENDAR}
    authority = await ledger.authority_for(
        provider=provider,
        account_kind=account_kind,
    )
    assert authority.phase is ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED
    phases = []
    for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR):
        phases.append(
            (
                await ledger.state_for(
                    provider=provider,
                    account_kind=account_kind,
                    resource=resource,
                )
            ).phase
        )
    assert phases == [
        ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN,
        ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN,
    ]
    assert len(revoke_calls) == int(provider is ConnectorProvider.GOOGLE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authority_phase", "terminal_effects"),
    (
        (ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED, True),
        (ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED, True),
        (ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED, False),
        (ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED, False),
    ),
)
async def test_google_revocation_recovery_is_monotonic_and_never_repeats_effects(
    monkeypatch,
    authority_phase,
    terminal_effects,
) -> None:
    registration, sources, _prepared, _controller = _sources_and_prepared(
        ConnectorProvider.GOOGLE
    )
    ledger, _database = await _dispatched_ledger(
        ConnectorProvider.GOOGLE,
        account_kind=ConnectorAccountKind.PERSONAL,
    )
    if terminal_effects:
        await _terminal_google_effects(ledger)
    await _google_authority_phase(ledger, authority_phase)

    async def no_prepare(self, **_kwargs):
        raise AssertionError("revocation recovery repeated credential preparation")

    async def revocation_secret(self):
        return ProviderGrantRevocationSecret("r" * 48)

    retired: list[ConnectorResource] = []

    async def retire_descriptor(self, *, invocation_id):
        assert invocation_id == INVOCATION
        retired.append(self._descriptor.resource)

    monkeypatch.setattr(ConnectedReleasePreviewCredentialSource, "prepare", no_prepare)
    monkeypatch.setattr(
        ConnectedReleasePreviewCredentialSource,
        "revocation_secret",
        revocation_secret,
    )
    monkeypatch.setattr(
        ConnectedReleasePreviewCredentialSource,
        "retire_descriptor",
        retire_descriptor,
    )
    revoke_calls: list[httpx.Request] = []

    def revoke(request: httpx.Request) -> httpx.Response:
        revoke_calls.append(request)
        return httpx.Response(200)

    probe = ConnectedGoogleReleasePreviewProbe(
        sources=sources,
        contract_sha256=CONTRACT,
        provider_transport=httpx.MockTransport(
            lambda request: pytest.fail(f"provider effect repeated: {request.url}")
        ),
        revoke_transport=httpx.MockTransport(revoke),
        sleep=NoSleep(),
        now=lambda: NOW,
    )
    call = probe.preview(
        registration=registration,
        redirect_uri=(
            "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
        ),
        invocation_id=INVOCATION,
        contract_sha256=CONTRACT,
        effect_ledger=ledger,
    )
    if terminal_effects:
        receipt = await call
        assert receipt.cleanup_attested is True
    else:
        with pytest.raises(ConnectedReleasePreviewProviderError):
            await call
    assert set(retired) == {ConnectorResource.MAIL, ConnectorResource.CALENDAR}
    assert len(revoke_calls) == int(
        authority_phase
        is ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
    )
    authority = await ledger.authority_for(
        provider=ConnectorProvider.GOOGLE,
        account_kind=ConnectorAccountKind.PERSONAL,
    )
    assert authority.phase is ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED
    phases = {
        (
            await ledger.state_for(
                provider=ConnectorProvider.GOOGLE,
                account_kind=ConnectorAccountKind.PERSONAL,
                resource=resource,
            )
        ).phase
        for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR)
    }
    assert phases == (
        {
            ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT,
            ConnectedReleasePreviewEffectPhase.CLEAN,
        }
        if terminal_effects
        else {ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN}
    )


@pytest.mark.asyncio
async def test_outer_failure_sweep_retires_every_later_unstarted_group(
    monkeypatch,
) -> None:
    google_registration, google_sources, _prepared, _controller = (
        _sources_and_prepared(ConnectorProvider.GOOGLE)
    )
    microsoft_registration, microsoft_personal, _prepared, _controller = (
        _sources_and_prepared(
            ConnectorProvider.MICROSOFT,
            account_kind=ConnectorAccountKind.PERSONAL,
        )
    )
    _registration, microsoft_work, _prepared, _controller = (
        _sources_and_prepared(
            ConnectorProvider.MICROSOFT,
            account_kind=ConnectorAccountKind.WORK_SCHOOL,
        )
    )
    assert google_registration.provider is ConnectorProvider.GOOGLE
    assert microsoft_registration.provider is ConnectorProvider.MICROSOFT
    database = EffectDatabase()
    ledger = ConnectedReleasePreviewEffectLedger(
        database=database,
        invocation_id=INVOCATION,
    )
    await ledger.begin(
        google_account_kind=ConnectorAccountKind.PERSONAL,
        descriptor_matrix_sha256=CONTRACT,
        dedicated_account_attestation_sha256=CONTRACT,
        deployment={
            "composition_manifest_sha256": CONTRACT,
            "database_contract_sha256": CONTRACT,
            "database_target_fingerprint": "1" * 32,
            "provider_contract_sha256": CONTRACT,
            "deployment_id": "dpl_12345678abcd",
            "commit_sha": "a" * 40,
            "host_configuration_ciphertext_sha256": CONTRACT,
            "root_key_id": "gkms1",
        },
        release_preview_contract_sha256=CONTRACT,
    )
    # The first (Google) probe failed but conclusively reconciled its exact
    # group before the harness-level sweep. Both later Microsoft groups have
    # not started and must still be retired before terminal failure.
    for row in database.effects:
        if row["provider"] == "google":
            row["phase"] = "effect_unknown"
            row["revision"] = 1
    google_authority = next(
        row for row in database.authorities if row["provider"] == "google"
    )
    google_authority.update(
        {
            "phase": "local_retired",
            "revision": 3,
            "provider_receipt_sha256": CONTRACT,
        }
    )
    retired: list[tuple[ConnectorAccountKind, ConnectorResource]] = []

    async def retire_descriptor(self, *, invocation_id):
        assert invocation_id == INVOCATION
        retired.append(
            (self._descriptor.account_kind, self._descriptor.resource)
        )

    monkeypatch.setattr(
        ConnectedReleasePreviewCredentialSource,
        "retire_descriptor",
        retire_descriptor,
    )
    probes = {
        ConnectorProvider.GOOGLE: {
            ConnectorAccountKind.PERSONAL: ConnectedGoogleReleasePreviewProbe(
                sources=google_sources,
                contract_sha256=CONTRACT,
            )
        },
        ConnectorProvider.MICROSOFT: {
            ConnectorAccountKind.PERSONAL: ConnectedMicrosoftReleasePreviewProbe(
                sources=microsoft_personal,
                contract_sha256=CONTRACT,
            ),
            ConnectorAccountKind.WORK_SCHOOL: ConnectedMicrosoftReleasePreviewProbe(
                sources=microsoft_work,
                contract_sha256=CONTRACT,
            ),
        },
    }
    await ConnectedReleasePreviewHarness._terminalize_failed_provider_matrix(
        invocation_id=INVOCATION,
        effect_ledger=ledger,
        provider_probes=probes,
    )
    assert set(retired) == {
        (account_kind, resource)
        for account_kind in (
            ConnectorAccountKind.PERSONAL,
            ConnectorAccountKind.WORK_SCHOOL,
        )
        for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR)
    }
    assert database.failed is True
    assert {row["phase"] for row in database.authorities} == {"local_retired"}
    assert {row["phase"] for row in database.effects} == {"effect_unknown"}


@pytest.mark.asyncio
async def test_outer_failure_sweep_preserves_unsettled_group_but_retires_later_groups(
    monkeypatch,
) -> None:
    _registration, google_sources, _prepared, _controller = _sources_and_prepared(
        ConnectorProvider.GOOGLE
    )
    _registration, microsoft_personal, _prepared, _controller = (
        _sources_and_prepared(
            ConnectorProvider.MICROSOFT,
            account_kind=ConnectorAccountKind.PERSONAL,
        )
    )
    _registration, microsoft_work, _prepared, _controller = (
        _sources_and_prepared(
            ConnectorProvider.MICROSOFT,
            account_kind=ConnectorAccountKind.WORK_SCHOOL,
        )
    )
    ledger, database = await _dispatched_ledger(
        ConnectorProvider.GOOGLE,
        account_kind=ConnectorAccountKind.PERSONAL,
    )
    retired: list[tuple[ConnectorAccountKind, ConnectorResource]] = []

    async def retire_descriptor(self, *, invocation_id):
        assert invocation_id == INVOCATION
        retired.append(
            (self._descriptor.account_kind, self._descriptor.resource)
        )

    monkeypatch.setattr(
        ConnectedReleasePreviewCredentialSource,
        "retire_descriptor",
        retire_descriptor,
    )
    probes = {
        ConnectorProvider.GOOGLE: {
            ConnectorAccountKind.PERSONAL: ConnectedGoogleReleasePreviewProbe(
                sources=google_sources,
                contract_sha256=CONTRACT,
            )
        },
        ConnectorProvider.MICROSOFT: {
            ConnectorAccountKind.PERSONAL: ConnectedMicrosoftReleasePreviewProbe(
                sources=microsoft_personal,
                contract_sha256=CONTRACT,
            ),
            ConnectorAccountKind.WORK_SCHOOL: ConnectedMicrosoftReleasePreviewProbe(
                sources=microsoft_work,
                contract_sha256=CONTRACT,
            ),
        },
    }
    with pytest.raises(ConnectedReleasePreviewError):
        await ConnectedReleasePreviewHarness._terminalize_failed_provider_matrix(
            invocation_id=INVOCATION,
            effect_ledger=ledger,
            provider_probes=probes,
        )
    assert database.failed is False
    assert set(retired) == {
        (account_kind, resource)
        for account_kind in (
            ConnectorAccountKind.PERSONAL,
            ConnectorAccountKind.WORK_SCHOOL,
        )
        for resource in (ConnectorResource.MAIL, ConnectorResource.CALENDAR)
    }
    assert next(
        row for row in database.authorities if row["provider"] == "google"
    )["phase"] == "pending"
    assert {
        row["phase"]
        for row in database.authorities
        if row["provider"] == "microsoft"
    } == {"local_retired"}


@pytest.mark.asyncio
async def test_google_ambiguous_draft_never_receipts_and_late_artifact_is_deleted(
    monkeypatch,
) -> None:
    registration, sources, prepared, controller = _sources_and_prepared(
        ConnectorProvider.GOOGLE
    )

    async def prepare(self, **_kwargs):
        return prepared[self._descriptor.resource]

    monkeypatch.setattr(ConnectedReleasePreviewCredentialSource, "prepare", prepare)
    state = {
        "draft_raw": None,
        "list_count": 0,
        "deleted": False,
        "calls": [],
    }

    def provider_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        state["calls"].append((request.method, path, request.url.query))
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [], "resultSizeEstimate": 0})
        if path.endswith("/drafts") and request.method == "POST":
            state["draft_raw"] = json.loads(request.content)["message"]["raw"]
            raise httpx.ReadTimeout("lost after dispatch", request=request)
        if path.endswith("/drafts") and request.method == "GET":
            state["list_count"] += 1
            visible = state["list_count"] >= 2 and not state["deleted"]
            return httpx.Response(
                200,
                json={
                    "drafts": [{"id": "late-draft"}] if visible else [],
                    "resultSizeEstimate": int(visible),
                },
            )
        if path.endswith("/drafts/late-draft") and request.method == "GET":
            if state["deleted"]:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={
                    "id": "late-draft",
                    "message": {"raw": state["draft_raw"]},
                },
            )
        if path.endswith("/drafts/late-draft") and request.method == "DELETE":
            state["deleted"] = True
            return httpx.Response(204)
        raise AssertionError((request.method, str(request.url)))

    probe = ConnectedGoogleReleasePreviewProbe(
        sources=sources,
        contract_sha256=CONTRACT,
        provider_transport=httpx.MockTransport(provider_handler),
        revoke_transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
        sleep=NoSleep(),
        now=lambda: NOW,
    )
    with pytest.raises(ConnectedReleasePreviewProviderError):
        await probe.preview(
            registration=registration,
            redirect_uri="https://www.askcrump.com/api/connected-apps/oauth/callback/google",
            invocation_id=INVOCATION,
            contract_sha256=CONTRACT,
        )
    assert state["deleted"] is True, "\n".join(map(str, state["calls"]))
    # Ambiguity never mints a receipt. Once marker discovery proves the
    # artifact was deleted, both dedicated credentials are retired rather
    # than leaving a live authority behind after a terminal failed preview.
    assert len(controller.retired) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "account_kind",
    (ConnectorAccountKind.PERSONAL, ConnectorAccountKind.WORK_SCHOOL),
)
async def test_microsoft_exact_effects_use_canonical_prefer_and_attendee_safe_delete(
    monkeypatch,
    account_kind,
) -> None:
    registration, sources, prepared, controller = _sources_and_prepared(
        ConnectorProvider.MICROSOFT,
        account_kind=account_kind,
    )

    async def prepare(self, **_kwargs):
        return prepared[self._descriptor.resource]

    monkeypatch.setattr(ConnectedReleasePreviewCredentialSource, "prepare", prepare)
    state: dict[str, object] = {
        "draft": None,
        "event": None,
        "delete_if_match": None,
        "paths": [],
        "sent": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        state["paths"].append(path)
        if path.endswith("/me") and request.method == "GET":
            return httpx.Response(
                200,
                json={"mail": "preview@example.invalid", "userPrincipalName": None},
            )
        if path.endswith("/me/calendar/getSchedule") and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "scheduleId": "preview@example.invalid",
                            "availabilityView": "00000000",
                            "scheduleItems": [],
                        }
                    ]
                },
            )
        if path.endswith("/mailFolders/inbox/messages"):
            return httpx.Response(200, json={"value": []})
        if path.endswith("/mailFolders/sentitems/messages"):
            return httpx.Response(200, json={"value": []})
        if path.endswith("/messages/sent-1/createReply") and request.method == "POST":
            sent = state["sent"]
            sent["sent-2"] = {
                "id": "sent-2",
                "conversationId": "conversation-1",
                "subject": "",
                "body": {"contentType": "Text", "content": ""},
                "isDraft": True,
            }
            return httpx.Response(201, json=sent["sent-2"])
        if path.endswith("/messages/sent-2") and request.method == "PATCH":
            body = json.loads(request.content)
            state["sent"]["sent-2"].update(body)
            return httpx.Response(204)
        if path.endswith("/messages/sent-1/send") and request.method == "POST":
            state["sent"]["sent-1"]["isDraft"] = False
            return httpx.Response(202)
        if path.endswith("/messages/sent-2/send") and request.method == "POST":
            state["sent"]["sent-2"]["isDraft"] = False
            return httpx.Response(202)
        if (
            (path.endswith("/messages/sent-1") or path.endswith("/messages/sent-2"))
            and request.method == "GET"
        ):
            return httpx.Response(200, json=state["sent"][path.rsplit("/", 1)[-1]])
        if path.endswith("/me/messages") and request.method == "POST":
            body = json.loads(request.content)
            if body["subject"].endswith("-send"):
                state["sent"]["sent-1"] = {
                    "id": "sent-1",
                    "conversationId": "conversation-1",
                    "subject": body["subject"],
                    "body": body["body"],
                    "isDraft": True,
                }
                return httpx.Response(201, json=state["sent"]["sent-1"])
            state["draft"] = body
            return httpx.Response(201, json={"id": "draft-1", "isDraft": True})
        if path.endswith("/mailFolders/drafts/messages"):
            return httpx.Response(200, json={"value": []})
        if path.endswith("/messages/draft-1") and request.method == "GET":
            if state["draft"] is None:
                return httpx.Response(404)
            assert request.headers["prefer"] == (
                'IdType="ImmutableId", outlook.body-content-type="text"'
            )
            draft = state["draft"]
            return httpx.Response(
                200,
                json={
                    "id": "draft-1",
                    "subject": draft["subject"],
                    "body": draft["body"],
                    "isDraft": True,
                },
            )
        if path.endswith("/messages/draft-1") and request.method == "DELETE":
            state["draft"] = None
            return httpx.Response(204)
        if path.endswith("/calendar/events") and request.method == "GET":
            return httpx.Response(200, json={"value": []})
        if path.endswith("/me/events") and request.method == "POST":
            body = json.loads(request.content)
            assert body["attendees"] == []
            state["event"] = body
            return httpx.Response(201, json={"id": "event-1"})
        if path.endswith("/events/event-1") and request.method == "GET":
            if state["event"] is None:
                return httpx.Response(404)
            event = state["event"]
            return httpx.Response(
                200,
                json={
                    "id": "event-1",
                    "changeKey": "change-1",
                    "subject": event["subject"],
                    "body": event["body"],
                    "isCancelled": False,
                    "attendees": [],
                    "isOrganizer": True,
                    "transactionId": event["transactionId"],
                },
            )
        if path.endswith("/events/event-1") and request.method == "PATCH":
            state["event"]["body"] = json.loads(request.content)["body"]
            return httpx.Response(204)
        if path.endswith("/events/event-1") and request.method == "DELETE":
            state["delete_if_match"] = request.headers.get("if-match")
            state["event"] = None
            return httpx.Response(204)
        raise AssertionError((request.method, str(request.url)))

    probe = ConnectedMicrosoftReleasePreviewProbe(
        sources=sources,
        contract_sha256=CONTRACT,
        provider_transport=httpx.MockTransport(handler),
        sleep=NoSleep(),
        now=lambda: NOW,
    )
    receipt = await probe.preview(
        registration=registration,
        redirect_uri=(
            "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
        ),
        invocation_id=INVOCATION,
        contract_sha256=CONTRACT,
    )
    assert receipt.provider_grant_revocation_attested is False
    assert receipt.calendar_free_busy_attested is (
        account_kind is ConnectorAccountKind.WORK_SCHOOL
    )
    assert receipt.calendar_free_busy_exempt is (
        account_kind is ConnectorAccountKind.PERSONAL
    )
    assert receipt.revocation_mode == "local_credential_and_connection_retirement"
    assert state["delete_if_match"] == "change-1"
    assert state["draft"] is None and state["event"] is None
    assert not any(path.endswith("revokeSignInSessions") for path in state["paths"])
    assert len(controller.retired) == 2


@pytest.mark.asyncio
async def test_microsoft_dispatched_draft_recovery_discovers_before_post(
    monkeypatch,
) -> None:
    _registration, sources, prepared, _controller = _sources_and_prepared(
        ConnectorProvider.MICROSOFT,
        account_kind=ConnectorAccountKind.PERSONAL,
    )

    async def prepare(self, **_kwargs):
        return prepared[self._descriptor.resource]

    monkeypatch.setattr(ConnectedReleasePreviewCredentialSource, "prepare", prepare)
    marker = "askcrump-release-preview-ms-draft-recovery"
    state: dict[str, object] = {"draft": None, "posts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/mailFolders/drafts/messages"):
            draft = state["draft"]
            return httpx.Response(
                200,
                json={
                    "value": (
                        []
                        if draft is None
                        else [
                            {
                                "id": "draft-1",
                                "subject": marker,
                                "body": {
                                    "contentType": "Text",
                                    "content": marker,
                                },
                                "isDraft": True,
                            }
                        ]
                    )
                },
            )
        if path.endswith("/me/messages") and request.method == "POST":
            state["posts"] = int(state["posts"]) + 1
            state["draft"] = json.loads(request.content)
            return httpx.Response(201, json={"id": "draft-1", "isDraft": True})
        if path.endswith("/messages/draft-1") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "draft-1",
                    "subject": marker,
                    "body": {"contentType": "Text", "content": marker},
                    "isDraft": True,
                },
            )
        raise AssertionError((request.method, str(request.url)))

    probe = ConnectedMicrosoftReleasePreviewProbe(
        sources=sources,
        contract_sha256=CONTRACT,
        provider_transport=httpx.MockTransport(handler),
        sleep=NoSleep(),
        now=lambda: NOW,
    )
    credential = prepared[ConnectorResource.MAIL]
    assert await probe._draft_write(credential, marker=marker) == "draft-1"
    assert await probe._draft_write(credential, marker=marker) == "draft-1"
    assert state["posts"] == 1


@pytest.mark.asyncio
async def test_microsoft_dispatched_draft_recovery_refuses_multiple_matches() -> None:
    _registration, sources, prepared, _controller = _sources_and_prepared(
        ConnectorProvider.MICROSOFT,
        account_kind=ConnectorAccountKind.PERSONAL,
    )
    marker = "askcrump-release-preview-ms-draft-collision"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/mailFolders/drafts/messages"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": draft_id,
                            "subject": marker,
                            "body": {"contentType": "Text", "content": marker},
                            "isDraft": True,
                        }
                        for draft_id in ("draft-1", "draft-2")
                    ]
                },
            )
        raise AssertionError((request.method, str(request.url)))

    probe = ConnectedMicrosoftReleasePreviewProbe(
        sources=sources,
        contract_sha256=CONTRACT,
        provider_transport=httpx.MockTransport(handler),
        sleep=NoSleep(),
        now=lambda: NOW,
    )
    with pytest.raises(ConnectedReleasePreviewProviderError):
        await probe._draft_write(
            prepared[ConnectorResource.MAIL],
            marker=marker,
        )


def _retirement_fixture():
    _registration_value, sources, prepared, _controller = _sources_and_prepared(
        ConnectorProvider.MICROSOFT,
        account_kind=ConnectorAccountKind.PERSONAL,
    )
    source = sources[ConnectorResource.MAIL]
    original = prepared[ConnectorResource.MAIL]
    database = RetirementDatabase(source._descriptor, original.credential.handle_id)
    vault = RetirementVault(database)
    source._database = database
    source._vault = vault
    value = ConnectedPreparedReleasePreviewCredential(
        account=original.account,
        credential=original.credential,
        connection_incarnation_id=original.connection_incarnation_id,
        source=original.source,
        refresh_token=original.refresh_token,
        vault=vault,  # type: ignore[arg-type]
        controller=source,
        authorization_revision=original.authorization_revision,
        authorization_snapshot_sha256=original.authorization_snapshot_sha256,
        current_flow_nonce_sha256=original.current_flow_nonce_sha256,
    )
    return source, value, database, vault


@pytest.mark.asyncio
async def test_retirement_erases_before_rpc_and_recovers_lost_response() -> None:
    source, prepared, database, vault = _retirement_fixture()
    database.lose_after_commit = True
    await source.retire(prepared, invocation_id=INVOCATION)
    assert database.events[:3] == ["erase", "retire", "retire"]
    assert database.revoked is True
    assert vault.calls == 1
    assert database.retirement_calls == 2
    assert await source.retirement_attested(invocation_id=INVOCATION) is True
    assert database.retirement_calls == 3


@pytest.mark.asyncio
async def test_retirement_crash_after_erasure_recovers_without_token_access() -> None:
    source, prepared, database, vault = _retirement_fixture()
    database.fail_before_commit = 2
    with pytest.raises(ConnectedReleasePreviewProviderError):
        await source.retire(prepared, invocation_id=INVOCATION)
    assert database.erased is True
    assert database.revoked is False
    assert vault.calls == 1

    # A fresh bounded retry needs only descriptor/binding metadata.  Erasure is
    # idempotent and the token source is never consulted by this transition.
    await source.retire(prepared, invocation_id=INVOCATION)
    assert database.revoked is True
    assert vault.calls == 2
    assert database.events == [
        "erase",
        "retire",
        "retire",
        "erase",
        "retire",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_before_raise", (False, True))
async def test_quarantine_rotation_failure_recovers_authoritative_cleanup_secret(
    monkeypatch,
    commit_before_raise,
) -> None:
    registration, sources, prepared, _controller = _sources_and_prepared(
        ConnectorProvider.GOOGLE
    )
    source = sources[ConnectorResource.MAIL]
    descriptor = source._descriptor
    account = prepared[ConnectorResource.MAIL].account
    credential = prepared[ConnectorResource.MAIL].credential
    authorization = ConnectedAuthorizationSnapshot.build(
        owner_id=descriptor.owner_id,
        connection_id=descriptor.connection_id,
        provider=descriptor.provider,
        resource=descriptor.resource,
        account_kind=descriptor.account_kind,
        revision=1,
        granted_actions=descriptor.granted_actions,
        granted_scopes=descriptor.granted_scopes,
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )
    binding = ProviderOAuthTokenBinding(
        provider=ConnectorProvider.GOOGLE,
        oauth_client_id_sha256=registration.client_id_sha256,
        owner_id=account.owner_id,
        connection_id=account.connection_id,
        connection_incarnation_id=descriptor.connection_incarnation_id,
        account_kind=account.account_kind,
        credential_handle_sha256=descriptor.credential_handle_sha256,
        external_account_id_hash=account.external_account_id_hash,
    )
    old = ProviderOAuthRefreshToken("old-refresh-token-" + "o" * 32, binding)
    new = ProviderOAuthRefreshToken("new-refresh-token-" + "n" * 32, binding)

    def opened(token):
        return SimpleNamespace(
            record=SimpleNamespace(record_binding_sha256=CONTRACT),
            refresh_token=token,
            granted_scopes=descriptor.granted_scopes,
        )

    class Vault:
        def __init__(self):
            self.current = opened(old)

        async def open(self, **_kwargs):
            return self.current

        async def rotate(self, *_args, **_kwargs):
            if commit_before_raise:
                self.current = opened(new)
            raise TimeoutError

    class Coordinator:
        quarantined = 0

        def __init__(self, *_args, **_kwargs):
            pass

        async def claim(self, **_kwargs):
            return object()

        async def quarantine(self, _lease):
            self.quarantined += 1

        async def finish(self, _lease):
            raise AssertionError("ambiguous lease was released")

    class Client:
        async def refresh(self, **_kwargs):
            raise ProviderOAuthQuarantineRequired(
                ProviderOAuthQuarantineTokenSet(
                    provider=ConnectorProvider.GOOGLE,
                    access_token=ProviderOAuthAccessToken(
                        "quarantine-access-token-" + "a" * 32,
                        binding,
                    ),
                    refresh_token=new,
                    requested_scopes=descriptor.granted_scopes,
                    issued_at=NOW,
                    expires_at=NOW + timedelta(hours=1),
                )
            )

    async def binding_read(self):
        return account, credential, authorization

    cleanup_secrets: list[str] = []

    async def cleanup(self, **kwargs):
        secret = kwargs["google_revocation_secret"]
        cleanup_secrets.append(secret.reveal_for_google_revocation())

    monkeypatch.setattr(
        "backend.connected_app_release_preview_provider."
        "SupabaseConnectedCredentialRefreshCoordinator",
        Coordinator,
    )
    monkeypatch.setattr(
        ConnectedReleasePreviewCredentialSource,
        "_binding",
        binding_read,
    )
    monkeypatch.setattr(
        ConnectedReleasePreviewCredentialSource,
        "_cleanup_failed_prepare",
        cleanup,
    )
    source._vault = Vault()
    source._client = Client()
    with pytest.raises(ConnectedReleasePreviewProviderError):
        await source.prepare(invocation_id=INVOCATION)
    assert cleanup_secrets == [new.require_binding(binding)]


def test_injected_transports_and_sleep_are_never_production_eligible() -> None:
    for provider, probe_type in (
        (ConnectorProvider.GOOGLE, ConnectedGoogleReleasePreviewProbe),
        (ConnectorProvider.MICROSOFT, ConnectedMicrosoftReleasePreviewProbe),
    ):
        registration, sources, _prepared, _controller = _sources_and_prepared(provider)
        kwargs = {
            "sources": sources,
            "contract_sha256": CONTRACT,
            "provider_transport": httpx.MockTransport(
                lambda _request: pytest.fail("must not dispatch")
            ),
            "sleep": NoSleep(),
            "now": lambda: NOW,
        }
        if provider is ConnectorProvider.GOOGLE:
            kwargs["revoke_transport"] = httpx.MockTransport(
                lambda _request: pytest.fail("must not revoke")
            )
        probe = probe_type(**kwargs)
        assert probe.production_eligible(
            database=sources[ConnectorResource.MAIL]._database,
            registration=registration,
        ) is False
