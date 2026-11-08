from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import inspect
import json
import pickle

import pytest

from backend import connected_app_oauth as oauth
from backend.connected_app_contracts import (
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    CredentialHandleRef,
)
from backend.connected_app_oauth import (
    OAuthAuthorizationCodeSecret,
    OAuthBrokerBeginResponseLost,
    OAuthBrokerFlowCommand,
    OAuthBrokerFlowLookup,
    OAuthBrokerFlowReceipt,
    OAuthBrokerGrant,
    OAuthBrokerStartRecovery,
    OAuthCallbackAttempt,
    OAuthCallbackSecrets,
    OAuthCompletion,
    OAuthCompletionCommand,
    OAuthCompletionInactive,
    OAuthCompletionResponseLost,
    OAuthConsumeCommand,
    OAuthConsumeResponseLost,
    OAuthContractError,
    OAuthExchangeAmbiguous,
    OAuthExchangeAttemptFence,
    OAuthExchangeCommand,
    OAuthExchangePermit,
    OAuthExchangePermitClaim,
    OAuthExchangePermitRecord,
    OAuthExchangePermitResponseLost,
    OAuthExchangeResponseLost,
    OAuthFlowConsumption,
    OAuthFlowCreateResponseLost,
    OAuthFlowRecord,
    OAuthFlowState,
    OAuthPkceVerifierSecret,
    OAuthRedirectAllowlist,
    OAuthStateSecret,
    OAuthCredentialCleanupCommand,
    OAuthCredentialCleanupReceipt,
    OAuthCredentialCleanupResponseLost,
    consume_oauth_flow_once,
    exchange_oauth_code_once,
    finalize_oauth_completion,
    pkce_s256_challenge,
    prepare_oauth_consumption,
    prepare_oauth_exchange,
    recover_oauth_flow_consumption,
    read_oauth_exchange_terminal,
    start_oauth_flow,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)


FLOW_ID = "00000000-0000-4000-8000-000000000001"
NONCE_ID = "00000000-0000-4000-8000-000000000002"
OWNER_ID = "00000000-0000-4000-8000-000000000003"
CONNECTION_ID = "00000000-0000-4000-8000-000000000004"
INCARNATION_ID = "00000000-0000-4000-8000-000000000007"
NEW_CONNECTION_ID = "00000000-0000-4000-8000-000000000008"
NEW_INCARNATION_ID = "00000000-0000-4000-8000-000000000009"
OTHER_ID = "00000000-0000-4000-8000-000000000006"
BASE_REVISION = 3
SESSION_HASH = "1" * 64
ACCOUNT_HASH = "2" * 64
STATE = "state-state-state-state-state-state-state-state"
OTHER_STATE = "other-other-other-other-other-other-other-other"
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
PERMIT_SECRET = "p" * 96
CODE = "authorization-code-value-12345"
REDIRECT = "https://askcrump.com/api/connected-apps/oauth/callback/google"
OTHER_REDIRECT = "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
GMAIL_READ = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
GOOGLE_IDENTITY = frozenset({"openid", "email"})
GMAIL_READ_SCOPES = frozenset({GMAIL_READ}) | GOOGLE_IDENTITY
DANGEROUS_GMAIL = "https://mail.google.com/"
NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
FLOW_NONCE_HASH = hashlib.sha256(NONCE_ID.encode("utf-8")).hexdigest()


def scope_hash(scopes: frozenset[str]) -> str:
    value = json.dumps(sorted(scopes), ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(value).hexdigest()


def action_hash(actions: frozenset[ConnectorActionKind]) -> str:
    value = json.dumps(
        sorted(action.value for action in actions),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(value).hexdigest()


def assert_content_free_error(error: OAuthContractError, code: str) -> None:
    rendered = f"{error!r} {error}"
    assert str(error) == code
    assert code in rendered
    assert "raw-secret-token" not in rendered
    assert "provider-body" not in rendered
    assert error.__cause__ is None


@pytest.fixture(autouse=True)
def deterministic_module_csprng(monkeypatch):
    calls: list[int] = []

    def token_urlsafe(size: int) -> str:
        calls.append(size)
        if size == 48:
            return STATE
        if size == 64:
            return VERIFIER
        if size == 72:
            return PERMIT_SECRET
        raise AssertionError(f"unexpected entropy size: {size}")

    monkeypatch.setattr(oauth.secrets, "token_urlsafe", token_urlsafe)
    return calls


def allowlist(*uris: str) -> OAuthRedirectAllowlist:
    return OAuthRedirectAllowlist(frozenset(uris or (REDIRECT,)))


class FakeBroker:
    """Models broker-internal custody and exact idempotency contracts."""

    def __init__(self, permit_authority: "FakeFlowRepository") -> None:
        if not isinstance(permit_authority, FakeFlowRepository):
            raise TypeError("permit_authority must be the trusted flow repository")
        # Composition owns this authority for the broker lifetime.  No exchange
        # caller can replace it or supply a prebuilt dispatch claim.
        self._permit_authority = permit_authority
        self.flow_bindings: dict[str, str] = {}
        self.flow_recoveries: dict[str, OAuthBrokerStartRecovery] = {}
        self.flow_receipts: dict[str, OAuthBrokerFlowReceipt] = {}
        self.states: dict[str, str] = {}
        self.verifiers: dict[str, str] = {}
        self.exchange_bindings: dict[str, str] = {}
        self.exchange_permit_bindings: dict[str, str] = {}
        self.exchange_terminals: dict[
            str,
            OAuthBrokerGrant | OAuthExchangeAmbiguous | OAuthExchangeAttemptFence,
        ] = {}
        self.begin_calls = 0
        self.read_flow_calls = 0
        self.exchange_calls = 0
        self.provider_exchange_calls = 0
        self.read_exchange_calls = 0
        self.lose_begin_before_store_once = False
        self.lose_begin_after_store_once = False
        self.lose_exchange_after_terminal_once = False
        self.lose_exchange_without_terminal_once = False
        self.hide_fence_read_once = False
        self.broker_now: datetime | None = None
        self.begin_exception: Exception | None = None
        self.read_flow_exception: Exception | None = None
        self.exchange_exception: Exception | None = None
        self.read_exchange_exception: Exception | None = None
        self._lost_begin_before = False
        self._lost_begin_after = False
        self._lost_exchange_after = False
        self._lost_exchange_without = False
        self.authority_drift_before_permit_consume: str | None = None

    @property
    def flow_repository(self) -> "FakeFlowRepository":
        """Expose the fixed fake composition for assertions, never replacement."""

        return self._permit_authority

    def _require_flow_binding(self, command: OAuthBrokerFlowCommand) -> None:
        existing = self.flow_bindings.get(command.flow_id)
        if existing is not None and existing != command.binding_sha256:
            raise OAuthContractError("OAUTH_BROKER_FLOW_BINDING_MISMATCH")

    async def begin_flow(
        self,
        *,
        command: OAuthBrokerFlowCommand,
        authorization_state: OAuthStateSecret,
        verifier: OAuthPkceVerifierSecret,
    ) -> OAuthBrokerStartRecovery:
        self.begin_calls += 1
        if self.begin_exception is not None:
            raise self.begin_exception
        self._require_flow_binding(command)
        if hashlib.sha256(authorization_state.value.encode()).hexdigest() != command.state_sha256:
            raise OAuthContractError("OAUTH_STATE_BROKER_MISMATCH")
        if pkce_s256_challenge(verifier.value) != command.pkce_challenge:
            raise OAuthContractError("OAUTH_PKCE_BROKER_MISMATCH")
        if self.lose_begin_before_store_once and not self._lost_begin_before:
            self._lost_begin_before = True
            raise OAuthBrokerBeginResponseLost()
        if command.flow_id in self.flow_recoveries:
            if (
                self.verifiers.get(command.flow_id) != verifier.value
                or self.states.get(command.flow_id) != authorization_state.value
            ):
                raise OAuthContractError("OAUTH_BROKER_VERIFIER_REPLAY_MISMATCH")
            return self.flow_recoveries[command.flow_id]
        receipt = OAuthBrokerFlowReceipt(
            flow_id=command.flow_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            expected_base_revision=command.expected_base_revision,
            current_flow_nonce_sha256=command.current_flow_nonce_sha256,
            flow_binding_sha256=command.binding_sha256,
            accepted_at=command.created_at + timedelta(seconds=1),
            expires_at=command.expires_at,
        )
        self.flow_bindings[command.flow_id] = command.binding_sha256
        self.flow_receipts[command.flow_id] = receipt
        self.states[command.flow_id] = authorization_state.value
        self.verifiers[command.flow_id] = verifier.value
        recovery = OAuthBrokerStartRecovery(
            command=command,
            receipt=receipt,
            authorization_state=OAuthStateSecret(authorization_state.value),
        )
        self.flow_recoveries[command.flow_id] = recovery
        if self.lose_begin_after_store_once and not self._lost_begin_after:
            self._lost_begin_after = True
            raise OAuthBrokerBeginResponseLost()
        return recovery

    async def read_flow(
        self,
        *,
        lookup: OAuthBrokerFlowLookup,
    ) -> OAuthBrokerStartRecovery | None:
        self.read_flow_calls += 1
        if self.read_flow_exception is not None:
            raise self.read_flow_exception
        recovery = self.flow_recoveries.get(lookup.flow_id)
        if recovery is None:
            return None
        command = recovery.command
        if (
            command.owner_id != lookup.owner_id
            or command.connection_id != lookup.connection_id
            or command.connection_incarnation_id != lookup.connection_incarnation_id
            or command.expected_base_revision != lookup.expected_base_revision
            or command.current_flow_nonce_sha256 != lookup.current_flow_nonce_sha256
        ):
            raise RuntimeError("sensitive broker lookup mismatch token=raw")
        return recovery

    def _require_exchange_binding(self, command: OAuthExchangeCommand) -> None:
        existing = self.exchange_bindings.get(command.exchange_id)
        if existing is not None and existing != command.binding_sha256:
            raise OAuthContractError("OAUTH_EXCHANGE_TERMINAL_BINDING_MISMATCH")

    def _grant(self, command: OAuthExchangeCommand) -> OAuthBrokerGrant:
        return OAuthBrokerGrant.build_for_exchange(
            command,
            credential=CredentialHandleRef(
                owner_id=command.owner_id,
                connection_id=command.connection_id,
                provider=command.provider,
                handle_id="broker-handle-opaque-00000001",
            ),
            external_account_id_hash=ACCOUNT_HASH,
            actual_scopes=GMAIL_READ_SCOPES,
            issued_at=command.issued_at + timedelta(seconds=1),
            expires_at=command.issued_at + timedelta(hours=1),
        )

    @staticmethod
    def _require_permit_claim(
        command: OAuthExchangeCommand,
        permit: OAuthExchangePermit,
        claim: OAuthExchangePermitClaim,
    ) -> None:
        if (
            not isinstance(permit, OAuthExchangePermit)
            or not isinstance(claim, OAuthExchangePermitClaim)
            or permit.permit_id != command.exchange_id
            or permit.exchange_binding_sha256 != command.binding_sha256
            or claim.permit_id != permit.permit_id
            or claim.exchange_binding_sha256 != command.binding_sha256
            or claim.permit_binding_sha256 != permit.permit_binding_sha256
            or claim.consumed_at < command.issued_at
            or claim.consumed_at >= command.deadline_at
        ):
            raise OAuthContractError("OAUTH_BROKER_EXCHANGE_PERMIT_MISMATCH")

    async def exchange_once(
        self,
        *,
        command: OAuthExchangeCommand,
        permit: OAuthExchangePermit,
        authorization_code: OAuthAuthorizationCodeSecret,
    ) -> OAuthBrokerGrant | OAuthExchangeAmbiguous | OAuthExchangeAttemptFence:
        self.exchange_calls += 1
        if self.exchange_exception is not None:
            raise self.exchange_exception
        self._require_exchange_binding(command)
        oauth._validate_exchange_permit(command, permit)
        if authorization_code.value != CODE:
            raise OAuthContractError("OAUTH_CODE_MISMATCH")
        if self.flow_bindings.get(command.flow_id) != command.flow_binding_sha256:
            raise OAuthContractError("OAUTH_BROKER_FLOW_BINDING_MISMATCH")
        verifier = self.verifiers.get(command.flow_id)
        if verifier is None:
            terminal = self.exchange_terminals.get(command.exchange_id)
            if terminal is None:
                raise OAuthContractError("OAUTH_BROKER_VERIFIER_MISSING")
            return terminal
        if pkce_s256_challenge(verifier) != command.pkce_challenge:
            raise OAuthContractError("OAUTH_PKCE_BROKER_MISMATCH")
        existing = self.exchange_terminals.get(command.exchange_id)
        if existing is not None:
            return existing
        # The broker owns the clock and writes the attempt fence before any
        # possible provider dispatch.
        self.exchange_bindings[command.exchange_id] = command.binding_sha256
        broker_now = self.broker_now or (command.issued_at + timedelta(seconds=1))
        if broker_now >= command.deadline_at:
            fence = OAuthExchangeAttemptFence(
                exchange_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                recorded_at=broker_now,
                reason="deadline_expired",
            )
            self.exchange_terminals[command.exchange_id] = fence
            return fence
        if self.authority_drift_before_permit_consume == "revoked":
            self._permit_authority.active = False
        elif self.authority_drift_before_permit_consume == "newer_flow":
            self._permit_authority.current_flow_nonce_sha256 = "9" * 64
        claim = await self._permit_authority.consume_exchange_permit_for_dispatch(
            command,
            permit,
        )
        self._require_permit_claim(command, permit, claim)
        existing_permit = self.exchange_permit_bindings.get(permit.permit_id)
        if (
            existing_permit is not None
            and existing_permit != permit.permit_binding_sha256
        ):
            raise OAuthContractError("OAUTH_BROKER_EXCHANGE_PERMIT_MISMATCH")
        if existing_permit is not None:
            raise OAuthContractError("OAUTH_BROKER_EXCHANGE_PERMIT_REPLAY")
        self.exchange_permit_bindings[permit.permit_id] = permit.permit_binding_sha256
        self.exchange_terminals[command.exchange_id] = OAuthExchangeAttemptFence(
            exchange_id=command.exchange_id,
            exchange_binding_sha256=command.binding_sha256,
            recorded_at=broker_now,
            reason="recovery_required",
        )
        if self.lose_exchange_without_terminal_once and not self._lost_exchange_without:
            self._lost_exchange_without = True
            self.provider_exchange_calls += 1
            raise OAuthExchangeResponseLost()
        self.provider_exchange_calls += 1
        grant = self._grant(command)
        # Persist terminal first, erase verifier second, then response.
        self.exchange_terminals[command.exchange_id] = grant
        del self.verifiers[command.flow_id]
        if self.lose_exchange_after_terminal_once and not self._lost_exchange_after:
            self._lost_exchange_after = True
            raise OAuthExchangeResponseLost()
        return grant

    async def read_exchange(
        self,
        *,
        command: OAuthExchangeCommand,
    ) -> OAuthBrokerGrant | OAuthExchangeAmbiguous | OAuthExchangeAttemptFence | None:
        self.read_exchange_calls += 1
        if self.read_exchange_exception is not None:
            raise self.read_exchange_exception
        self._require_exchange_binding(command)
        if self.hide_fence_read_once and isinstance(
            self.exchange_terminals.get(command.exchange_id),
            OAuthExchangeAttemptFence,
        ):
            self.hide_fence_read_once = False
            return None
        return self.exchange_terminals.get(command.exchange_id)


class FakeFlowRepository:
    def __init__(
        self,
        *,
        now: datetime = NOW + timedelta(minutes=1),
        connection_id: str = CONNECTION_ID,
        incarnation_id: str = INCARNATION_ID,
        revision: int = BASE_REVISION,
    ) -> None:
        self.now = now
        self.connection_id = connection_id
        self.incarnation_id = incarnation_id
        self.revision = revision
        self.owner_id = OWNER_ID
        self.session_binding_sha256 = SESSION_HASH
        self.provider = ConnectorProvider.GOOGLE
        self.resource = ConnectorResource.MAIL
        self.account_kind = ConnectorAccountKind.PERSONAL
        self.active = True
        self.replaced = False
        self.current_flow_nonce_sha256: str | None = None
        self.pending: dict[str, tuple[str, OAuthFlowRecord]] = {}
        self.records: dict[str, tuple[str, OAuthFlowConsumption]] = {}
        self.permits: dict[str, OAuthExchangePermitRecord] = {}
        # Models separate encrypted secret-vault custody, not the durable row.
        self.permit_vault: dict[str, OAuthExchangePermit] = {}
        self.create_calls = 0
        self.read_pending_calls = 0
        self.revalidate_pending_calls = 0
        self.consume_calls = 0
        self.read_calls = 0
        self.issue_permit_calls = 0
        self.read_permit_calls = 0
        self.consume_permit_calls = 0
        self.create_exception: Exception | None = None
        self.read_pending_exception: Exception | None = None
        self.revalidate_pending_exception: Exception | None = None
        self.consume_exception: Exception | None = None
        self.read_consumption_exception: Exception | None = None
        self.issue_permit_exception: Exception | None = None
        self.read_permit_exception: Exception | None = None
        self.consume_permit_exception: Exception | None = None
        self.lose_create_before_store_once = False
        self.lose_create_after_store_once = False
        self._lost_create_before = False
        self._lost_create_after = False
        self.lose_before_store_once = False
        self.lose_after_store_once = False
        self._lost_before = False
        self._lost_after = False
        self.lose_permit_before_store_once = False
        self.lose_permit_after_store_once = False
        self._lost_permit_before = False
        self._lost_permit_after = False
        self.lose_permit_consume_after_store_once = False
        self._lost_permit_consume_after = False

    async def create_pending(self, flow: OAuthFlowRecord) -> None:
        self.create_calls += 1
        if self.create_exception is not None:
            raise self.create_exception
        if self.lose_create_before_store_once and not self._lost_create_before:
            self._lost_create_before = True
            raise OAuthFlowCreateResponseLost()
        if (
            flow.connection_id != self.connection_id
            or flow.connection_incarnation_id != self.incarnation_id
            or flow.expected_base_revision != self.revision
            or flow.owner_id != self.owner_id
            or flow.session_binding_sha256 != self.session_binding_sha256
            or flow.provider is not self.provider
            or flow.resource is not self.resource
            or flow.account_kind is not self.account_kind
            or not self.active
            or self.replaced
        ):
            raise RuntimeError("sensitive stale connection token=raw")
        existing = self.pending.get(flow.flow_id)
        if existing is not None:
            if existing[0] != flow.binding_sha256:
                raise RuntimeError("sensitive pending binding body=raw")
            return
        self.pending[flow.flow_id] = (flow.binding_sha256, flow)
        self.current_flow_nonce_sha256 = flow.current_flow_nonce_sha256
        if self.lose_create_after_store_once and not self._lost_create_after:
            self._lost_create_after = True
            raise OAuthFlowCreateResponseLost()

    async def read_pending(
        self,
        *,
        flow_id: str,
        expected_flow_binding_sha256: str,
    ) -> OAuthFlowRecord | None:
        self.read_pending_calls += 1
        if self.read_pending_exception is not None:
            raise self.read_pending_exception
        existing = self.pending.get(flow_id)
        if existing is None:
            return None
        if existing[0] != expected_flow_binding_sha256:
            raise RuntimeError("sensitive pending read token=raw")
        return existing[1]

    async def revalidate_pending(self, flow: OAuthFlowRecord) -> OAuthFlowRecord:
        self.revalidate_pending_calls += 1
        if self.revalidate_pending_exception is not None:
            raise self.revalidate_pending_exception
        existing = self.pending.get(flow.flow_id)
        if existing is None or existing[0] != flow.binding_sha256 or existing[1] != flow:
            raise RuntimeError("sensitive pending replay binding token=raw")
        if (
            flow.connection_id != self.connection_id
            or flow.connection_incarnation_id != self.incarnation_id
            or flow.expected_base_revision != self.revision
            or flow.current_flow_nonce_sha256 != self.current_flow_nonce_sha256
            or flow.owner_id != self.owner_id
            or flow.session_binding_sha256 != self.session_binding_sha256
            or flow.provider is not self.provider
            or flow.resource is not self.resource
            or flow.account_kind is not self.account_kind
            or not self.active
            or self.replaced
        ):
            raise RuntimeError("sensitive stale pending replay token=raw")
        return existing[1]

    def _require_binding(self, command: OAuthConsumeCommand) -> None:
        existing = self.records.get(command.consumption_id)
        if existing is not None and existing[0] != command.binding_sha256:
            raise OAuthContractError("OAUTH_CONSUMPTION_BINDING_MISMATCH")

    def _require_live_consumption_authority(self, command: OAuthConsumeCommand) -> None:
        pending = self.pending.get(command.flow_id)
        if pending is None or pending[0] != command.flow_binding_sha256:
            raise RuntimeError("sensitive missing pending flow token=raw")
        flow = pending[1]
        if (
            command.connection_id != self.connection_id
            or command.connection_incarnation_id != self.incarnation_id
            or command.expected_base_revision != self.revision
            or command.current_flow_nonce_sha256 != self.current_flow_nonce_sha256
            or command.owner_id != self.owner_id
            or command.session_binding_sha256 != self.session_binding_sha256
            or command.provider is not self.provider
            or command.resource is not self.resource
            or command.account_kind is not self.account_kind
            or command.flow_id != flow.flow_id
            or command.flow_binding_sha256 != flow.binding_sha256
            or command.redirect_uri != flow.redirect_uri
            or command.state_sha256 != flow.state_sha256
            or not self.active
            or self.replaced
            or self.now >= command.flow_expires_at
        ):
            raise RuntimeError("sensitive stale pending authority token=raw")

    def _require_live_exchange_authority(self, command: OAuthExchangeCommand) -> None:
        record = self.records.get(command.consumption_id)
        pending = self.pending.get(command.flow_id)
        if record is None or pending is None:
            raise RuntimeError("sensitive missing consumption token=raw")
        consumption = record[1]
        flow = pending[1]
        if (
            record[0] != command.consume_binding_sha256
            or pending[0] != command.flow_binding_sha256
            or consumption.flow_binding_sha256 != command.flow_binding_sha256
            or consumption.connection_id != command.connection_id
            or consumption.connection_incarnation_id != command.connection_incarnation_id
            or consumption.expected_base_revision != command.expected_base_revision
            or consumption.current_flow_nonce_sha256 != command.current_flow_nonce_sha256
            or flow.owner_id != command.owner_id
            or flow.session_binding_sha256 != command.session_binding_sha256
            or flow.provider is not command.provider
            or flow.resource is not command.resource
            or flow.account_kind is not command.account_kind
            or command.connection_id != self.connection_id
            or command.connection_incarnation_id != self.incarnation_id
            or command.expected_base_revision != self.revision
            or command.current_flow_nonce_sha256 != self.current_flow_nonce_sha256
            or not self.active
            or self.replaced
            or self.now >= command.deadline_at
        ):
            raise RuntimeError("sensitive stale exchange authority token=raw")

    async def read_consumption(
        self,
        command: OAuthConsumeCommand,
    ) -> OAuthFlowConsumption | None:
        self.read_calls += 1
        if self.read_consumption_exception is not None:
            raise self.read_consumption_exception
        self._require_binding(command)
        existing = self.records.get(command.consumption_id)
        return existing[1] if existing else None

    async def consume_pending(self, command: OAuthConsumeCommand) -> OAuthFlowConsumption:
        self.consume_calls += 1
        if self.consume_exception is not None:
            raise self.consume_exception
        self._require_binding(command)
        self._require_live_consumption_authority(command)
        if self.lose_before_store_once and not self._lost_before:
            self._lost_before = True
            raise OAuthConsumeResponseLost()
        existing = self.records.get(command.consumption_id)
        if existing is not None:
            return existing[1]
        result = OAuthFlowConsumption.build_for_command(command, consumed_at=self.now)
        self.records[command.consumption_id] = (command.binding_sha256, result)
        if self.lose_after_store_once and not self._lost_after:
            self._lost_after = True
            raise OAuthConsumeResponseLost()
        return result

    async def read_exchange_permit(
        self,
        command: OAuthExchangeCommand,
    ) -> OAuthExchangePermit | None:
        self.read_permit_calls += 1
        if self.read_permit_exception is not None:
            raise self.read_permit_exception
        self._require_live_exchange_authority(command)
        existing = self.permits.get(command.exchange_id)
        if existing is None:
            return None
        oauth._validate_exchange_permit_record(command, existing)
        return self.permit_vault[command.exchange_id]

    async def issue_exchange_permit_once(
        self,
        command: OAuthExchangeCommand,
    ) -> OAuthExchangePermit:
        self.issue_permit_calls += 1
        if self.issue_permit_exception is not None:
            raise self.issue_permit_exception
        self._require_live_exchange_authority(command)
        if self.lose_permit_before_store_once and not self._lost_permit_before:
            self._lost_permit_before = True
            raise OAuthExchangePermitResponseLost()
        existing = self.permits.get(command.exchange_id)
        if existing is not None:
            oauth._validate_exchange_permit_record(command, existing)
            return self.permit_vault[command.exchange_id]
        record, permit = oauth._issue_exchange_permit(command, issued_at=self.now)
        self.permits[command.exchange_id] = record
        self.permit_vault[command.exchange_id] = permit
        if self.lose_permit_after_store_once and not self._lost_permit_after:
            self._lost_permit_after = True
            raise OAuthExchangePermitResponseLost()
        return permit

    async def consume_exchange_permit_for_dispatch(
        self,
        command: OAuthExchangeCommand,
        permit: OAuthExchangePermit,
    ) -> OAuthExchangePermitClaim:
        self.consume_permit_calls += 1
        if self.consume_permit_exception is not None:
            raise self.consume_permit_exception
        self._require_live_exchange_authority(command)
        existing = self.permits.get(command.exchange_id)
        if existing is None:
            raise OAuthContractError("OAUTH_EXCHANGE_PERMIT_UNKNOWN")
        record = existing
        oauth._validate_exchange_permit_record(command, record)
        if (
            not isinstance(permit, OAuthExchangePermit)
            or permit.permit_id != record.permit_id
            or permit.exchange_binding_sha256 != record.exchange_binding_sha256
            or permit.permit_binding_sha256 != record.binding_sha256
            or not hmac.compare_digest(
                oauth._exchange_permit_capability_sha256(permit),
                record.capability_sha256,
            )
        ):
            raise OAuthContractError("OAUTH_EXCHANGE_PERMIT_PROVENANCE_INVALID")
        if record.consumed_at is not None:
            raise OAuthContractError("OAUTH_EXCHANGE_PERMIT_ALREADY_CONSUMED")
        consumed_record = replace(record, consumed_at=self.now)
        self.permits[command.exchange_id] = consumed_record
        if (
            self.lose_permit_consume_after_store_once
            and not self._lost_permit_consume_after
        ):
            self._lost_permit_consume_after = True
            raise RuntimeError("sensitive permit claim response loss token=raw")
        return OAuthExchangePermitClaim(
            permit_id=record.permit_id,
            exchange_binding_sha256=record.exchange_binding_sha256,
            permit_binding_sha256=record.binding_sha256,
            consumed_at=self.now,
        )


class FakeCompletionRepository:
    def __init__(
        self,
        *,
        connection_id: str = CONNECTION_ID,
        incarnation_id: str = INCARNATION_ID,
        current_revision: int = BASE_REVISION,
        current_flow_nonce_sha256: str = FLOW_NONCE_HASH,
        external_account_id_hash: str | None = ACCOUNT_HASH,
    ) -> None:
        self.connection_id = connection_id
        self.incarnation_id = incarnation_id
        self.current_revisions: dict[str, int] = {connection_id: current_revision}
        self.current_flow_nonce_sha256 = current_flow_nonce_sha256
        self.external_account_id_hash = external_account_id_hash
        self.active = True
        self.replaced = False
        self.records: dict[str, tuple[str, OAuthCompletion]] = {}
        self.historicals: dict[str, tuple[str, OAuthCompletionInactive]] = {}
        self.cleanup_records: dict[
            str,
            tuple[str, OAuthCredentialCleanupReceipt],
        ] = {}
        self.complete_calls = 0
        self.read_calls = 0
        self.cleanup_calls = 0
        self.cleanup_read_calls = 0
        self.complete_exception: Exception | None = None
        self.read_exception: Exception | None = None
        self.cleanup_exception: Exception | None = None
        self.cleanup_read_exception: Exception | None = None
        self.lose_after_store_once = False
        self._lost_after = False
        self.lose_cleanup_after_store_once = False
        self._lost_cleanup_after = False

    def _require_binding(self, command: OAuthCompletionCommand) -> None:
        existing = self.records.get(command.completion_id)
        if existing is not None and existing[0] != command.binding_sha256:
            raise OAuthContractError("OAUTH_COMPLETION_BINDING_MISMATCH")

    def _inactive_reason(
        self,
        command: OAuthCompletionCommand,
        completion: OAuthCompletion | None,
    ) -> str | None:
        if command.connection_id != self.connection_id or self.replaced:
            return "replaced"
        if command.connection_incarnation_id != self.incarnation_id:
            return "incarnation_changed"
        if not self.active:
            return "revoked"
        if command.current_flow_nonce_sha256 != self.current_flow_nonce_sha256:
            return "newer_flow"
        expected_current_revision = (
            completion.authorization.revision
            if completion is not None
            else command.expected_base_revision
        )
        if self.current_revisions.get(command.connection_id) != expected_current_revision:
            return "revision_changed"
        if (
            self.external_account_id_hash is not None
            and command.external_account_id_hash != self.external_account_id_hash
        ):
            return "account_changed"
        return None

    def _inactive_terminal(
        self,
        command: OAuthCompletionCommand,
        reason: str,
    ) -> OAuthCompletionInactive:
        existing = self.historicals.get(command.completion_id)
        if existing is not None:
            if existing[0] != command.binding_sha256:
                raise RuntimeError("sensitive historical binding token=raw")
            return existing[1]
        terminal = OAuthCompletionInactive(
            completion_id=command.completion_id,
            completion_binding_sha256=command.binding_sha256,
            connection_id=command.connection_id,
            observed_at=command.issued_at + timedelta(seconds=2),
            reason=reason,
        )
        self.historicals[command.completion_id] = (command.binding_sha256, terminal)
        return terminal

    async def read_completion(
        self,
        command: OAuthCompletionCommand,
    ) -> OAuthCompletion | OAuthCompletionInactive | None:
        self.read_calls += 1
        if self.read_exception is not None:
            raise self.read_exception
        self._require_binding(command)
        historical = self.historicals.get(command.completion_id)
        if historical is not None:
            if historical[0] != command.binding_sha256:
                raise RuntimeError("sensitive historical read token=raw")
            return historical[1]
        existing = self.records.get(command.completion_id)
        if existing is None:
            return None
        reason = self._inactive_reason(command, existing[1])
        if reason is not None:
            return self._inactive_terminal(command, reason)
        return existing[1]

    async def complete_once(
        self,
        command: OAuthCompletionCommand,
    ) -> OAuthCompletion | OAuthCompletionInactive:
        self.complete_calls += 1
        if self.complete_exception is not None:
            raise self.complete_exception
        self._require_binding(command)
        historical = self.historicals.get(command.completion_id)
        if historical is not None:
            return historical[1]
        existing = self.records.get(command.completion_id)
        if existing is not None:
            reason = self._inactive_reason(command, existing[1])
            if reason is not None:
                return self._inactive_terminal(command, reason)
            return existing[1]
        reason = self._inactive_reason(command, None)
        if reason is not None:
            return self._inactive_terminal(command, reason)
        revision = command.expected_base_revision + 1
        authorization = ConnectedAuthorizationSnapshot.build(
            owner_id=command.owner_id,
            connection_id=command.connection_id,
            provider=command.provider,
            resource=command.resource,
            account_kind=command.account_kind,
            revision=revision,
            granted_actions=command.granted_actions,
            granted_scopes=command.granted_scopes,
            state=ConnectionAuthorizationState.ACTIVE,
            issued_at=command.issued_at,
            expires_at=command.expires_at,
        )
        completion = OAuthCompletion(
            consumption_id=command.consumption_id,
            exchange_id=command.exchange_id,
            connection_incarnation_id=command.connection_incarnation_id,
            expected_base_revision=command.expected_base_revision,
            current_flow_nonce_sha256=command.current_flow_nonce_sha256,
            completion_binding_sha256=command.binding_sha256,
            credential=command.credential,
            external_account_id_hash=command.external_account_id_hash,
            authorization=authorization,
        )
        # This models the required connection lock and atomic write: revision,
        # credential link, snapshot, and idempotency row become visible together.
        self.current_revisions[command.connection_id] = revision
        self.external_account_id_hash = command.external_account_id_hash
        self.records[command.completion_id] = (command.binding_sha256, completion)
        if self.lose_after_store_once and not self._lost_after:
            self._lost_after = True
            raise OAuthCompletionResponseLost()
        return completion

    async def read_cleanup(
        self,
        command: OAuthCredentialCleanupCommand,
    ) -> OAuthCredentialCleanupReceipt | None:
        self.cleanup_read_calls += 1
        if self.cleanup_read_exception is not None:
            raise self.cleanup_read_exception
        existing = self.cleanup_records.get(command.cleanup_id)
        if existing is None:
            return None
        if existing[0] != command.binding_sha256:
            raise RuntimeError("sensitive cleanup read token=raw")
        return existing[1]

    async def record_cleanup_once(
        self,
        command: OAuthCredentialCleanupCommand,
    ) -> OAuthCredentialCleanupReceipt:
        self.cleanup_calls += 1
        if self.cleanup_exception is not None:
            raise self.cleanup_exception
        existing = self.cleanup_records.get(command.cleanup_id)
        if existing is not None:
            if existing[0] != command.binding_sha256:
                raise RuntimeError("sensitive cleanup binding token=raw")
            return existing[1]
        receipt = OAuthCredentialCleanupReceipt(
            cleanup_id=command.cleanup_id,
            cleanup_binding_sha256=command.binding_sha256,
            recorded_at=NOW + timedelta(minutes=2),
        )
        self.cleanup_records[command.cleanup_id] = (command.binding_sha256, receipt)
        if self.lose_cleanup_after_store_once and not self._lost_cleanup_after:
            self._lost_cleanup_after = True
            raise OAuthCredentialCleanupResponseLost()
        return receipt


async def start(
    *,
    broker: FakeBroker | None = None,
    repository: FakeFlowRepository | None = None,
    **changes: object,
):
    flows = repository or (broker.flow_repository if broker is not None else FakeFlowRepository())
    store = broker or FakeBroker(flows)
    if store.flow_repository is not flows:
        raise ValueError("broker and flow repository must be composed together")
    values: dict[str, object] = {
        "flow_id": FLOW_ID,
        "nonce_id": NONCE_ID,
        "owner_id": OWNER_ID,
        "connection_id": CONNECTION_ID,
        "connection_incarnation_id": INCARNATION_ID,
        "expected_base_revision": BASE_REVISION,
        "current_flow_nonce_sha256": FLOW_NONCE_HASH,
        "session_binding_sha256": SESSION_HASH,
        "provider": ConnectorProvider.GOOGLE,
        "resource": ConnectorResource.MAIL,
        "account_kind": ConnectorAccountKind.PERSONAL,
        "actions": frozenset({ConnectorActionKind.MAIL_SEARCH}),
        "redirect_uri": REDIRECT,
        "redirect_allowlist": allowlist(),
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=10),
        "broker": store,
        "repository": flows,
    }
    values.update(changes)
    result = await start_oauth_flow(**values)  # type: ignore[arg-type]
    return result, store


def callback(**changes: object) -> OAuthCallbackAttempt:
    values: dict[str, object] = {
        "flow_id": FLOW_ID,
        "owner_id": OWNER_ID,
        "session_binding_sha256": SESSION_HASH,
        "provider": ConnectorProvider.GOOGLE,
        "resource": ConnectorResource.MAIL,
        "account_kind": ConnectorAccountKind.PERSONAL,
        "redirect_uri": REDIRECT,
        "secrets": OAuthCallbackSecrets(authorization_code=CODE, state=STATE),
    }
    values.update(changes)
    return OAuthCallbackAttempt(**values)  # type: ignore[arg-type]


def repository_for_flow(
    flow: OAuthFlowRecord,
    *,
    now: datetime = NOW + timedelta(minutes=1),
) -> FakeFlowRepository:
    repository = FakeFlowRepository(now=now)
    repository.pending[flow.flow_id] = (flow.binding_sha256, flow)
    repository.current_flow_nonce_sha256 = flow.current_flow_nonce_sha256
    return repository


async def exchange_parts(*, broker: FakeBroker | None = None):
    repository = broker.flow_repository if broker is not None else FakeFlowRepository()
    started, store = await start(broker=broker, repository=repository)
    consume_command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=1),
    )
    used = await consume_oauth_flow_once(repository=repository, command=consume_command)
    exchange_command = prepare_oauth_exchange(
        started.flow,
        used,
    )
    return started, store, consume_command, used, exchange_command


def broker_grant(
    command: OAuthExchangeCommand,
    *,
    scopes: frozenset[str] = GMAIL_READ_SCOPES,
    owner_id: str = OWNER_ID,
    connection_id: str = CONNECTION_ID,
    provider: ConnectorProvider = ConnectorProvider.GOOGLE,
) -> OAuthBrokerGrant:
    return OAuthBrokerGrant.build_for_exchange(
        command,
        credential=CredentialHandleRef(
            owner_id=owner_id,
            connection_id=connection_id,
            provider=provider,
            handle_id="broker-handle-opaque-00000001",
        ),
        external_account_id_hash=ACCOUNT_HASH,
        actual_scopes=scopes,
        issued_at=command.issued_at + timedelta(seconds=1),
        expires_at=command.issued_at + timedelta(hours=1),
    )


def test_pkce_s256_matches_rfc_7636_example():
    assert pkce_s256_challenge(VERIFIER) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


@pytest.mark.asyncio
async def test_start_api_has_no_entropy_or_verifier_vault_injection():
    parameters = inspect.signature(start_oauth_flow).parameters
    for forbidden in (
        "_test_entropy",
        "entropy",
        "state",
        "raw_state",
        "verifier",
        "pkce_verifier",
        "vault",
    ):
        assert forbidden not in parameters
    assert not hasattr(oauth, "OAuthEntropySource")
    assert not hasattr(oauth, "SystemOAuthEntropySource")


@pytest.mark.asyncio
async def test_start_uses_module_csprng_and_broker_internal_verifier_custody(
    deterministic_module_csprng,
):
    started, broker = await start()
    assert deterministic_module_csprng == [48, 64]
    assert started.authorization_state.value == STATE
    assert broker.verifiers[FLOW_ID] == VERIFIER
    assert started.flow.pkce_challenge == pkce_s256_challenge(VERIFIER)
    assert started.flow.broker_flow_binding_sha256 == started.flow.binding_sha256
    assert not hasattr(started, "verifier")
    assert not hasattr(started.flow, "pkce_verifier")
    for rendered in (repr(started), repr(started.flow)):
        assert STATE not in rendered
        assert VERIFIER not in rendered
        assert started.flow.binding_sha256 not in rendered


@pytest.mark.asyncio
async def test_broker_begin_response_loss_after_durable_store_uses_readback():
    broker = FakeBroker(FakeFlowRepository())
    broker.lose_begin_after_store_once = True
    started, _ = await start(broker=broker)
    assert started.flow.flow_id == FLOW_ID
    assert broker.begin_calls == 1
    assert broker.read_flow_calls == 3
    assert broker.verifiers[FLOW_ID] == VERIFIER


@pytest.mark.asyncio
async def test_broker_begin_loss_before_store_retries_same_idempotency_binding():
    broker = FakeBroker(FakeFlowRepository())
    broker.lose_begin_before_store_once = True
    started, _ = await start(broker=broker)
    assert started.flow.flow_id == FLOW_ID
    assert broker.begin_calls == 2
    assert broker.read_flow_calls == 3
    assert len(broker.flow_receipts) == 1


@pytest.mark.asyncio
async def test_broker_begin_exact_replay_returns_same_receipt_and_mismatch_refuses():
    started, broker = await start()
    command = OAuthBrokerFlowCommand(
        flow_id=started.flow.flow_id,
        nonce_id=started.flow.nonce_id,
        owner_id=started.flow.owner_id,
        connection_id=started.flow.connection_id,
        connection_incarnation_id=started.flow.connection_incarnation_id,
        expected_base_revision=started.flow.expected_base_revision,
        current_flow_nonce_sha256=started.flow.current_flow_nonce_sha256,
        session_binding_sha256=started.flow.session_binding_sha256,
        provider=started.flow.provider,
        resource=started.flow.resource,
        account_kind=started.flow.account_kind,
        actions=started.flow.actions,
        actions_sha256=started.flow.actions_sha256,
        requested_scopes=started.flow.requested_scopes,
        requested_scopes_sha256=started.flow.requested_scopes_sha256,
        state_sha256=started.flow.state_sha256,
        pkce_challenge=started.flow.pkce_challenge,
        redirect_uri=started.flow.redirect_uri,
        created_at=started.flow.created_at,
        expires_at=started.flow.expires_at,
    )
    lookup = OAuthBrokerFlowLookup(
        flow_id=command.flow_id,
        owner_id=command.owner_id,
        connection_id=command.connection_id,
        connection_incarnation_id=command.connection_incarnation_id,
        expected_base_revision=command.expected_base_revision,
        current_flow_nonce_sha256=command.current_flow_nonce_sha256,
    )
    first = await broker.read_flow(lookup=lookup)
    replay = await broker.begin_flow(
        command=command,
        authorization_state=OAuthStateSecret(STATE),
        verifier=OAuthPkceVerifierSecret(VERIFIER),
    )
    assert replay is first
    mismatched = replace(command, redirect_uri=OTHER_REDIRECT)
    with pytest.raises(OAuthContractError, match="FLOW_BINDING_MISMATCH"):
        await broker.begin_flow(
            command=mismatched,
            authorization_state=OAuthStateSecret(STATE),
            verifier=OAuthPkceVerifierSecret(VERIFIER),
        )
    assert broker.verifiers[FLOW_ID] == VERIFIER


@pytest.mark.asyncio
async def test_start_crash_after_broker_custody_recovers_without_regenerating_secrets(
    deterministic_module_csprng,
):
    repository = FakeFlowRepository()
    broker = FakeBroker(repository)
    repository.create_exception = RuntimeError("raw-secret-token provider-body")
    with pytest.raises(OAuthContractError) as caught:
        await start(broker=broker, repository=repository)
    assert_content_free_error(caught.value, "OAUTH_FLOW_CREATE_FAILED")
    first_recovery = broker.flow_recoveries[FLOW_ID]
    assert deterministic_module_csprng == [48, 64]
    repository.create_exception = None
    recovered, _ = await start(broker=broker, repository=repository)
    assert deterministic_module_csprng == [48, 64]
    assert recovered.authorization_state.value == STATE
    assert recovered.flow.binding_sha256 == first_recovery.command.binding_sha256
    assert recovered.flow.pkce_challenge == first_recovery.command.pkce_challenge
    assert repository.pending[FLOW_ID][1] == recovered.flow


@pytest.mark.asyncio
async def test_pending_flow_create_response_loss_recovers_exact_durable_record():
    for loss_attr, expected_calls in (
        ("lose_create_after_store_once", 1),
        ("lose_create_before_store_once", 2),
    ):
        repository = FakeFlowRepository()
        broker = FakeBroker(repository)
        setattr(repository, loss_attr, True)
        started, _ = await start(broker=broker, repository=repository)
        assert repository.create_calls == expected_calls
        assert repository.pending[FLOW_ID][1] == started.flow
        assert broker.begin_calls == 1


@pytest.mark.asyncio
async def test_unpersisted_broker_start_response_never_creates_app_pending_flow():
    class UnpersistedStartBroker(FakeBroker):
        async def begin_flow(self, *, command, authorization_state, verifier):
            receipt = OAuthBrokerFlowReceipt(
                flow_id=command.flow_id,
                connection_id=command.connection_id,
                connection_incarnation_id=command.connection_incarnation_id,
                expected_base_revision=command.expected_base_revision,
                current_flow_nonce_sha256=command.current_flow_nonce_sha256,
                flow_binding_sha256=command.binding_sha256,
                accepted_at=command.created_at + timedelta(seconds=1),
                expires_at=command.expires_at,
            )
            return OAuthBrokerStartRecovery(
                command=command,
                receipt=receipt,
                authorization_state=authorization_state,
            )

    repository = FakeFlowRepository()
    with pytest.raises(OAuthContractError, match="OAUTH_BROKER_CUSTODY_UNCONFIRMED"):
        await start(
            broker=UnpersistedStartBroker(repository),
            repository=repository,
        )
    assert repository.pending == {}


@pytest.mark.asyncio
async def test_flow_binds_connection_revision_incarnation_and_current_nonce_end_to_end_start():
    repository = FakeFlowRepository()
    broker = FakeBroker(repository)
    started, _ = await start(broker=broker, repository=repository)
    recovery = broker.flow_recoveries[FLOW_ID]
    receipt = recovery.receipt
    assert started.flow.connection_incarnation_id == INCARNATION_ID
    assert started.flow.expected_base_revision == BASE_REVISION
    assert started.flow.current_flow_nonce_sha256 == FLOW_NONCE_HASH
    assert receipt.connection_incarnation_id == INCARNATION_ID
    assert receipt.expected_base_revision == BASE_REVISION
    assert receipt.current_flow_nonce_sha256 == FLOW_NONCE_HASH
    assert repository.current_flow_nonce_sha256 == FLOW_NONCE_HASH


@pytest.mark.parametrize(
    "drift",
    [
        "revoked",
        "replaced",
        "revision",
        "incarnation",
        "newer_flow",
        "owner",
        "session",
        "provider",
        "resource",
        "account_kind",
    ],
)
@pytest.mark.asyncio
async def test_pending_start_replay_revalidates_live_connection_before_returning_state(
    drift,
    deterministic_module_csprng,
):
    repository = FakeFlowRepository()
    broker = FakeBroker(repository)
    initial, _ = await start(broker=broker, repository=repository)
    assert initial.authorization_state.value == STATE
    if drift == "revoked":
        repository.active = False
    elif drift == "replaced":
        repository.replaced = True
    elif drift == "revision":
        repository.revision += 1
    elif drift == "incarnation":
        repository.incarnation_id = OTHER_ID
    elif drift == "newer_flow":
        repository.current_flow_nonce_sha256 = "9" * 64
    elif drift == "owner":
        repository.owner_id = OTHER_ID
    elif drift == "session":
        repository.session_binding_sha256 = "9" * 64
    elif drift == "provider":
        repository.provider = ConnectorProvider.MICROSOFT
    elif drift == "resource":
        repository.resource = ConnectorResource.CALENDAR
    else:
        repository.account_kind = ConnectorAccountKind.WORK_SCHOOL
    with pytest.raises(OAuthContractError) as caught:
        await start(broker=broker, repository=repository)
    assert_content_free_error(caught.value, "OAUTH_FLOW_REVALIDATE_FAILED")
    assert broker.begin_calls == 1
    assert deterministic_module_csprng == [48, 64]


@pytest.mark.asyncio
async def test_pending_start_replay_rejects_durable_binding_drift_without_new_state(
    deterministic_module_csprng,
):
    repository = FakeFlowRepository()
    broker = FakeBroker(repository)
    initial, _ = await start(broker=broker, repository=repository)
    repository.pending[FLOW_ID] = ("9" * 64, initial.flow)
    with pytest.raises(OAuthContractError) as caught:
        await start(broker=broker, repository=repository)
    assert_content_free_error(caught.value, "OAUTH_FLOW_READ_FAILED")
    assert deterministic_module_csprng == [48, 64]
    assert broker.begin_calls == 1


@pytest.mark.asyncio
async def test_start_quarantines_every_broker_and_repository_exception():
    cases = (
        ("broker_read", "OAUTH_BROKER_FLOW_READ_FAILED"),
        ("broker_begin", "OAUTH_BROKER_BEGIN_FAILED"),
        ("repository_read", "OAUTH_FLOW_READ_FAILED"),
        ("repository_create", "OAUTH_FLOW_CREATE_FAILED"),
        ("repository_revalidate", "OAUTH_FLOW_REVALIDATE_FAILED"),
    )
    for case, code in cases:
        repository = FakeFlowRepository()
        broker = FakeBroker(repository)
        hostile = OAuthContractError("raw-secret-token provider-body")
        if case == "broker_read":
            broker.read_flow_exception = hostile
        elif case == "broker_begin":
            broker.begin_exception = hostile
        elif case == "repository_read":
            repository.read_pending_exception = hostile
        elif case == "repository_revalidate":
            repository.revalidate_pending_exception = hostile
        else:
            repository.create_exception = hostile
        with pytest.raises(OAuthContractError) as caught:
            await start(broker=broker, repository=repository)
        assert_content_free_error(caught.value, code)


@pytest.mark.asyncio
async def test_exact_action_plan_prevents_arbitrary_dangerous_and_cross_resource_scopes():
    started, _ = await start()
    assert started.flow.actions == frozenset({ConnectorActionKind.MAIL_SEARCH})
    assert started.flow.requested_scopes == GMAIL_READ_SCOPES
    assert started.flow.actions_sha256 == action_hash(started.flow.actions)
    assert started.flow.requested_scopes_sha256 == scope_hash(started.flow.requested_scopes)
    for scopes in (
        frozenset({GMAIL_SEND}),
        frozenset({DANGEROUS_GMAIL}),
        frozenset({GMAIL_READ, GMAIL_SEND}) | GOOGLE_IDENTITY,
    ):
        with pytest.raises(ValueError, match="exactly match"):
            replace(
                started.flow,
                requested_scopes=scopes,
                requested_scopes_sha256=scope_hash(scopes),
            )
    with pytest.raises(ValueError, match="flow resource"):
        await start(actions=frozenset({ConnectorActionKind.CALENDAR_LIST}))
    with pytest.raises(ValueError, match="no safe delegated"):
        await start(actions=frozenset({ConnectorActionKind.MAIL_LIST}))


@pytest.mark.parametrize(
    "secret",
    [OAuthStateSecret(STATE), OAuthPkceVerifierSecret(VERIFIER), OAuthAuthorizationCodeSecret(CODE)],
)
def test_raw_secrets_are_redacted_and_unserializable(secret):
    assert secret.value not in repr(secret)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(secret)


@pytest.mark.asyncio
async def test_exchange_permit_is_opaque_unserializable_and_repository_authenticated():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    permit = await broker.flow_repository.issue_exchange_permit_once(command)
    record = broker.flow_repository.permits[command.exchange_id]
    rendered = f"{permit!r} {record!r}"
    assert PERMIT_SECRET not in rendered
    assert record.capability_sha256 not in rendered
    assert "capability_secret" not in {item.name for item in fields(record)}
    assert record.capability_sha256 == hashlib.sha256(PERMIT_SECRET.encode()).hexdigest()
    assert not hasattr(permit, "value")
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(permit)
    with pytest.raises(TypeError, match="repository-issued"):
        OAuthExchangePermit(
            permit_id=command.exchange_id,
            exchange_binding_sha256=command.binding_sha256,
            permit_binding_sha256=record.binding_sha256,
            capability_secret="f" * 96,
            _factory_key=object(),
        )


def test_callback_never_accepts_or_exposes_verifier():
    parameters = inspect.signature(OAuthCallbackSecrets).parameters
    assert "verifier" not in parameters
    assert "pkce_verifier" not in parameters
    item = OAuthCallbackSecrets(authorization_code=CODE, state=STATE)
    assert not hasattr(item, "pkce_verifier")
    for raw in (CODE, STATE, VERIFIER):
        assert raw not in repr(item)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(item)


@pytest.mark.parametrize(
    "uri",
    [
        "http://askcrump.com/api/connected-apps/oauth/callback/google",
        "https://user@askcrump.com/api/connected-apps/oauth/callback/google",
        "https://askcrump.com:443/api/connected-apps/oauth/callback/google",
        f"{REDIRECT}?next=https://evil.example",
        f"{REDIRECT}#fragment",
        "https://askcrump.com//api/connected-apps/oauth/callback/google",
        "https://askcrump.com/api/../oauth/callback/google",
        "https://askcrump.com/api/%2e%2e/oauth/callback/google",
        "https://ASKCRUMP.com/api/connected-apps/oauth/callback/google",
    ],
)
def test_redirect_uri_rejects_origin_and_path_confusion(uri: str):
    with pytest.raises(ValueError):
        OAuthRedirectAllowlist(frozenset({uri}))


@pytest.mark.asyncio
async def test_start_requires_exact_allowlist_member_and_max_ten_minute_ttl():
    with pytest.raises(OAuthContractError, match="OAUTH_REDIRECT_NOT_ALLOWED"):
        await start(redirect_allowlist=allowlist(OTHER_REDIRECT))
    started, _ = await start()
    assert started.flow.expires_at - started.flow.created_at == timedelta(minutes=10)
    with pytest.raises(ValueError, match="at most 10 minutes"):
        await start(expires_at=NOW + timedelta(minutes=10, microseconds=1))


@pytest.mark.parametrize(
    "changes",
    [
        {"flow_id": OTHER_ID},
        {"owner_id": OTHER_ID},
        {"session_binding_sha256": "9" * 64},
        {"provider": ConnectorProvider.MICROSOFT},
        {"resource": ConnectorResource.CALENDAR},
        {"account_kind": ConnectorAccountKind.WORK_SCHOOL},
        {"redirect_uri": OTHER_REDIRECT},
    ],
)
@pytest.mark.asyncio
async def test_callback_binding_mismatch_rejects_origin_and_authority(changes):
    started, _ = await start()
    with pytest.raises(OAuthContractError, match="OAUTH_CALLBACK_BINDING_MISMATCH"):
        prepare_oauth_consumption(
            started.flow,
            callback(**changes),
            now=NOW + timedelta(minutes=1),
        )


@pytest.mark.asyncio
async def test_callback_state_expiry_and_replay_are_exclusive_and_one_use():
    started, _ = await start()
    wrong = callback(secrets=OAuthCallbackSecrets(authorization_code=CODE, state=OTHER_STATE))
    with pytest.raises(OAuthContractError, match="OAUTH_STATE_MISMATCH"):
        prepare_oauth_consumption(started.flow, wrong, now=NOW + timedelta(minutes=1))
    with pytest.raises(OAuthContractError, match="OAUTH_FLOW_EXPIRED_OR_CONSUMED"):
        prepare_oauth_consumption(started.flow, callback(), now=started.flow.expires_at)
    consumed = replace(
        started.flow,
        state=OAuthFlowState.CONSUMED,
        consumed_at=NOW + timedelta(minutes=1),
    )
    with pytest.raises(OAuthContractError, match="OAUTH_FLOW_EXPIRED_OR_CONSUMED"):
        prepare_oauth_consumption(consumed, callback(), now=NOW + timedelta(minutes=2))
    with pytest.raises(ValueError, match="exclusive OAuth expiry"):
        replace(started.flow, state=OAuthFlowState.CONSUMED, consumed_at=started.flow.expires_at)


@pytest.mark.asyncio
async def test_consume_response_loss_after_store_recovers_without_second_write():
    started, _ = await start()
    command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=1),
    )
    repository = repository_for_flow(started.flow)
    repository.lose_after_store_once = True
    result = await consume_oauth_flow_once(repository=repository, command=command)
    assert result.consume_binding_sha256 == command.binding_sha256
    assert repository.consume_calls == 1
    assert repository.read_calls == 1


@pytest.mark.asyncio
async def test_consume_loss_before_store_retries_exact_idempotency_binding():
    started, _ = await start()
    command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=1),
    )
    repository = repository_for_flow(started.flow)
    repository.lose_before_store_once = True
    result = await consume_oauth_flow_once(repository=repository, command=command)
    assert result.consumption_id == FLOW_ID
    assert repository.consume_calls == 2
    assert len(repository.records) == 1


@pytest.mark.asyncio
async def test_consume_cannot_synthesize_a_record_without_exact_durable_pending_flow():
    started, _ = await start()
    command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=1),
    )
    empty_repository = FakeFlowRepository()
    with pytest.raises(OAuthContractError) as caught:
        await consume_oauth_flow_once(repository=empty_repository, command=command)
    assert_content_free_error(caught.value, "OAUTH_CONSUMPTION_WRITE_FAILED")
    assert empty_repository.records == {}


@pytest.mark.parametrize(
    "drift",
    [
        "revision",
        "incarnation",
        "nonce",
        "owner",
        "session",
        "provider",
        "resource",
        "account_kind",
        "revoked",
        "replaced",
    ],
)
@pytest.mark.asyncio
async def test_atomic_consume_revalidates_pending_flow_and_live_connection(drift):
    started, _ = await start()
    command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=1),
    )
    repository = repository_for_flow(started.flow)
    if drift == "revision":
        repository.revision += 1
    elif drift == "incarnation":
        repository.incarnation_id = OTHER_ID
    elif drift == "nonce":
        repository.current_flow_nonce_sha256 = "9" * 64
    elif drift == "owner":
        repository.owner_id = OTHER_ID
    elif drift == "session":
        repository.session_binding_sha256 = "9" * 64
    elif drift == "provider":
        repository.provider = ConnectorProvider.MICROSOFT
    elif drift == "resource":
        repository.resource = ConnectorResource.CALENDAR
    elif drift == "account_kind":
        repository.account_kind = ConnectorAccountKind.WORK_SCHOOL
    elif drift == "revoked":
        repository.active = False
    else:
        repository.replaced = True
    with pytest.raises(OAuthContractError) as caught:
        await consume_oauth_flow_once(repository=repository, command=command)
    assert_content_free_error(caught.value, "OAUTH_CONSUMPTION_WRITE_FAILED")
    assert repository.records == {}


@pytest.mark.asyncio
async def test_repository_clock_rejects_atomic_consume_at_exact_expiry():
    started, _ = await start()
    command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=started.flow.expires_at - timedelta(microseconds=1),
    )
    repository = repository_for_flow(started.flow, now=started.flow.expires_at)
    with pytest.raises(OAuthContractError, match="OAUTH_CONSUMPTION_WRITE_FAILED"):
        await consume_oauth_flow_once(repository=repository, command=command)
    assert repository.records == {}


@pytest.mark.asyncio
async def test_process_restart_reads_existing_consumption_before_mutation():
    started, _ = await start()
    command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=1),
    )
    repository = repository_for_flow(started.flow)
    first = await repository.consume_pending(command)
    replay_command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=2),
    )
    assert replay_command.binding_sha256 == command.binding_sha256
    recovered = await consume_oauth_flow_once(repository=repository, command=command)
    assert recovered is first
    assert repository.consume_calls == 2
    mismatched = replace(command, redirect_uri=OTHER_REDIRECT)
    with pytest.raises(OAuthContractError, match="OAUTH_CONSUMPTION_WRITE_FAILED"):
        await consume_oauth_flow_once(repository=repository, command=mismatched)


@pytest.mark.asyncio
async def test_process_restart_recovers_consumption_without_callback_secrets():
    started, _ = await start()
    command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=1),
    )
    repository = repository_for_flow(started.flow)
    first = await repository.consume_pending(command)
    consumed_flow = replace(
        started.flow,
        state=OAuthFlowState.CONSUMED,
        consumed_at=first.consumed_at,
    )
    recovered = await recover_oauth_flow_consumption(
        repository=repository,
        flow=consumed_flow,
    )
    assert recovered is first


@pytest.mark.asyncio
async def test_consumption_quarantines_read_and_write_exceptions():
    started, _ = await start()
    command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=1),
    )
    for attr, code in (
        ("read_consumption_exception", "OAUTH_CONSUMPTION_READ_FAILED"),
        ("consume_exception", "OAUTH_CONSUMPTION_WRITE_FAILED"),
    ):
        repository = repository_for_flow(started.flow)
        setattr(repository, attr, RuntimeError("raw-secret-token provider-body"))
        if attr == "read_consumption_exception":
            repository.lose_after_store_once = True
        with pytest.raises(OAuthContractError) as caught:
            await consume_oauth_flow_once(repository=repository, command=command)
        assert_content_free_error(caught.value, code)


@pytest.mark.asyncio
async def test_exchange_command_never_accepts_verifier_and_binds_exact_redirect():
    started, _broker, _consume_command, used, command = await exchange_parts()
    assert "verifier" not in inspect.signature(prepare_oauth_exchange).parameters
    assert command.redirect_uri == started.flow.redirect_uri == REDIRECT
    assert command.flow_binding_sha256 == started.flow.binding_sha256
    assert command.consume_binding_sha256 == used.consume_binding_sha256
    assert used.connection_incarnation_id == INCARNATION_ID
    assert used.expected_base_revision == BASE_REVISION
    assert used.current_flow_nonce_sha256 == FLOW_NONCE_HASH
    assert command.connection_incarnation_id == INCARNATION_ID
    assert command.expected_base_revision == BASE_REVISION
    assert command.current_flow_nonce_sha256 == FLOW_NONCE_HASH
    assert command.deadline_at - command.issued_at <= timedelta(minutes=2)
    rendered = repr(command)
    for hidden in (
        SESSION_HASH,
        command.actions_sha256,
        command.requested_scopes_sha256,
        command.flow_binding_sha256,
        command.consume_binding_sha256,
        command.pkce_challenge,
    ):
        assert hidden not in rendered


@pytest.mark.asyncio
async def test_exchange_rejects_forged_consumption_binding_before_broker_use():
    started, _broker, _consume_command, used, _command = await exchange_parts()
    with pytest.raises(OAuthContractError, match="CONSUMPTION_BINDING_MISMATCH"):
        prepare_oauth_exchange(
            started.flow,
            replace(used, consume_binding_sha256="9" * 64),
        )


@pytest.mark.asyncio
async def test_exchange_deadline_is_exclusive_before_any_broker_call():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_DEADLINE_EXPIRED"):
        await exchange_oauth_code_once(
            broker=broker,
            repository=broker.flow_repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.deadline_at,
        )
    assert broker.exchange_calls == 0
    assert broker.read_exchange_calls == 1


@pytest.mark.asyncio
async def test_successful_exchange_is_broker_internal_and_erases_verifier_after_terminal():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    result = await exchange_oauth_code_once(
        broker=broker,
        repository=broker.flow_repository,
        command=command,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
        now=command.issued_at,
    )
    assert isinstance(result, OAuthBrokerGrant)
    assert result.redirect_uri == REDIRECT
    assert result.verifier_erased_after_terminal is True
    assert FLOW_ID not in broker.verifiers
    assert broker.provider_exchange_calls == 1
    assert broker.read_exchange_calls == 1
    assert result.connection_incarnation_id == INCARNATION_ID
    assert result.expected_base_revision == BASE_REVISION
    assert result.current_flow_nonce_sha256 == FLOW_NONCE_HASH


@pytest.mark.parametrize(
    "loss_attr, expected_issue_calls",
    [
        ("lose_permit_after_store_once", 1),
        ("lose_permit_before_store_once", 2),
    ],
)
@pytest.mark.asyncio
async def test_exchange_permit_response_loss_recovers_exact_durable_permit(
    loss_attr,
    expected_issue_calls,
):
    _started, broker, _consume_command, _used, command = await exchange_parts()
    repository = broker.flow_repository
    setattr(repository, loss_attr, True)
    result = await exchange_oauth_code_once(
        broker=broker,
        repository=repository,
        command=command,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
        now=command.issued_at,
    )
    assert isinstance(result, OAuthBrokerGrant)
    assert repository.issue_permit_calls == expected_issue_calls
    assert len(repository.permits) == 1
    assert broker.provider_exchange_calls == 1


@pytest.mark.parametrize("drift", ["revoked", "replaced", "revision", "newer_flow"])
@pytest.mark.asyncio
async def test_connection_drift_between_consume_and_exchange_blocks_dispatch(drift):
    _started, broker, _consume_command, _used, command = await exchange_parts()
    repository = broker.flow_repository
    if drift == "revoked":
        repository.active = False
    elif drift == "replaced":
        repository.replaced = True
    elif drift == "revision":
        repository.revision += 1
    else:
        repository.current_flow_nonce_sha256 = "9" * 64
    with pytest.raises(OAuthContractError) as caught:
        await exchange_oauth_code_once(
            broker=broker,
            repository=repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at,
        )
    assert_content_free_error(caught.value, "OAUTH_EXCHANGE_PERMIT_READ_FAILED")
    assert broker.exchange_calls == 0
    assert broker.provider_exchange_calls == 0


@pytest.mark.asyncio
async def test_preissued_permit_is_revalidated_after_disconnect_before_dispatch():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    repository = broker.flow_repository
    permit = await repository.issue_exchange_permit_once(command)
    repository.active = False
    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_PERMIT_READ_FAILED"):
        await exchange_oauth_code_once(
            broker=broker,
            repository=repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at,
        )
    assert permit.permit_id == command.exchange_id
    assert broker.exchange_calls == 0


@pytest.mark.parametrize("drift", ["revoked", "newer_flow"])
@pytest.mark.asyncio
async def test_authority_drift_after_issue_at_broker_fence_blocks_provider_dispatch(drift):
    _started, broker, _consume_command, _used, command = await exchange_parts()
    repository = broker.flow_repository
    broker.authority_drift_before_permit_consume = drift
    with pytest.raises(OAuthContractError) as caught:
        await exchange_oauth_code_once(
            broker=broker,
            repository=repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at,
        )
    assert_content_free_error(caught.value, "OAUTH_EXCHANGE_DISPATCH_FAILED")
    assert broker.exchange_calls == 1
    assert repository.consume_permit_calls == 1
    assert repository.permits[command.exchange_id].consumed_at is None
    assert broker.provider_exchange_calls == 0
    assert command.exchange_id not in broker.exchange_terminals


@pytest.mark.asyncio
async def test_permit_claim_response_loss_is_durably_fenced_without_dispatch_retry():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    repository = broker.flow_repository
    repository.lose_permit_consume_after_store_once = True
    for _ in range(2):
        with pytest.raises(OAuthContractError) as caught:
            await exchange_oauth_code_once(
                broker=broker,
                repository=repository,
                command=command,
                authorization_code=OAuthAuthorizationCodeSecret(CODE),
                now=command.issued_at,
            )
        assert_content_free_error(caught.value, "OAUTH_EXCHANGE_DISPATCH_FAILED")
    assert repository.permits[command.exchange_id].consumed_at == repository.now
    assert repository.consume_permit_calls == 2
    assert broker.provider_exchange_calls == 0
    assert command.exchange_id not in broker.exchange_terminals


@pytest.mark.asyncio
async def test_exchange_permit_boundaries_quarantine_every_repository_exception():
    for attr, code in (
        ("read_permit_exception", "OAUTH_EXCHANGE_PERMIT_READ_FAILED"),
        ("issue_permit_exception", "OAUTH_EXCHANGE_PERMIT_WRITE_FAILED"),
    ):
        _started, broker, _consume_command, _used, command = await exchange_parts()
        repository = broker.flow_repository
        setattr(repository, attr, OAuthContractError("raw-secret-token provider-body"))
        with pytest.raises(OAuthContractError) as caught:
            await exchange_oauth_code_once(
                broker=broker,
                repository=repository,
                command=command,
                authorization_code=OAuthAuthorizationCodeSecret(CODE),
                now=command.issued_at,
            )
        assert_content_free_error(caught.value, code)
        assert broker.provider_exchange_calls == 0


@pytest.mark.asyncio
async def test_broker_requires_exact_one_use_repository_permit_for_dispatch():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    repository = broker.flow_repository
    permit = await repository.issue_exchange_permit_once(command)
    with pytest.raises(TypeError):
        await broker.exchange_once(  # type: ignore[call-arg]
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
        )
    first = await broker.exchange_once(
        command=command,
        permit=permit,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    replay = await broker.exchange_once(
        command=command,
        permit=permit,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    assert replay is first
    assert broker.provider_exchange_calls == 1


def test_exchange_signatures_expose_no_substitutable_authority_or_claim():
    protocol_parameters = inspect.signature(
        oauth.OAuthCredentialBroker.exchange_once
    ).parameters
    fake_parameters = inspect.signature(FakeBroker.exchange_once).parameters
    assert tuple(protocol_parameters) == (
        "self",
        "command",
        "permit",
        "authorization_code",
    )
    assert tuple(fake_parameters) == tuple(protocol_parameters)
    for boundary in (
        start_oauth_flow,
        prepare_oauth_exchange,
        exchange_oauth_code_once,
        read_oauth_exchange_terminal,
        oauth.OAuthCredentialBroker.exchange_once,
        FakeBroker.exchange_once,
    ):
        exposed = inspect.signature(boundary).parameters
        assert "permit_authority" not in exposed
        assert "claim" not in exposed


@pytest.mark.parametrize("drift", ["revoked", "newer_flow"])
@pytest.mark.asyncio
async def test_forged_authority_claim_and_capability_cannot_bypass_bound_authority(drift):
    _started, broker, _consume_command, _used, command = await exchange_parts()
    real_authority = broker.flow_repository
    permit = await real_authority.issue_exchange_permit_once(command)
    if drift == "revoked":
        real_authority.active = False
    else:
        real_authority.current_flow_nonce_sha256 = "9" * 64

    forged_authority = FakeFlowRepository()
    forged_claim = OAuthExchangePermitClaim(
        permit_id=permit.permit_id,
        exchange_binding_sha256=command.binding_sha256,
        permit_binding_sha256=permit.permit_binding_sha256,
        consumed_at=command.issued_at + timedelta(seconds=1),
    )
    exchange_arguments = {
        "command": command,
        "permit": permit,
        "authorization_code": OAuthAuthorizationCodeSecret(CODE),
    }
    with pytest.raises(TypeError):
        await broker.exchange_once(  # type: ignore[call-arg]
            **exchange_arguments,
            permit_authority=forged_authority,
        )
    with pytest.raises(TypeError):
        await broker.exchange_once(  # type: ignore[call-arg]
            **exchange_arguments,
            claim=forged_claim,
        )

    forged_permit = object.__new__(OAuthExchangePermit)
    object.__setattr__(forged_permit, "_permit_id", permit.permit_id)
    object.__setattr__(
        forged_permit,
        "_exchange_binding_sha256",
        permit.exchange_binding_sha256,
    )
    object.__setattr__(
        forged_permit,
        "_permit_binding_sha256",
        permit.permit_binding_sha256,
    )
    object.__setattr__(forged_permit, "_capability_secret", "f" * 96)
    with pytest.raises(RuntimeError, match="sensitive stale exchange authority"):
        await broker.exchange_once(
            command=command,
            permit=forged_permit,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
        )

    assert broker.provider_exchange_calls == 0
    assert broker.exchange_calls == 1
    assert real_authority.consume_permit_calls == 1
    assert forged_authority.consume_permit_calls == 0
    assert real_authority.permits[command.exchange_id].consumed_at is None


@pytest.mark.asyncio
async def test_broker_rejects_forged_shape_and_forged_capability_without_dispatch():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    permit = await broker.flow_repository.issue_exchange_permit_once(command)

    class ForgedPermitShape:
        permit_id = permit.permit_id
        exchange_binding_sha256 = permit.exchange_binding_sha256
        permit_binding_sha256 = permit.permit_binding_sha256

    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_PERMIT_BINDING_MISMATCH"):
        await broker.exchange_once(
            command=command,
            permit=ForgedPermitShape(),  # type: ignore[arg-type]
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
        )

    forged = object.__new__(OAuthExchangePermit)
    object.__setattr__(forged, "_permit_id", permit.permit_id)
    object.__setattr__(
        forged,
        "_exchange_binding_sha256",
        permit.exchange_binding_sha256,
    )
    object.__setattr__(
        forged,
        "_permit_binding_sha256",
        permit.permit_binding_sha256,
    )
    object.__setattr__(forged, "_capability_secret", "f" * 96)
    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_PERMIT_PROVENANCE_INVALID"):
        await broker.exchange_once(
            command=command,
            permit=forged,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
        )
    assert broker.provider_exchange_calls == 0
    assert broker.flow_repository.consume_permit_calls == 1
    assert broker.flow_repository.permits[command.exchange_id].consumed_at is None


@pytest.mark.asyncio
async def test_tampered_durable_permit_row_cannot_reach_broker_or_provider():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    repository = broker.flow_repository
    await repository.issue_exchange_permit_once(command)
    repository.permits[command.exchange_id] = replace(
        repository.permits[command.exchange_id],
        owner_id=OTHER_ID,
    )
    with pytest.raises(OAuthContractError) as caught:
        await exchange_oauth_code_once(
            broker=broker,
            repository=repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at,
        )
    assert_content_free_error(caught.value, "OAUTH_EXCHANGE_PERMIT_READ_FAILED")
    assert broker.exchange_calls == 0
    assert broker.provider_exchange_calls == 0


@pytest.mark.asyncio
async def test_exchange_response_loss_after_terminal_recovers_by_readback_without_repeat():
    broker = FakeBroker(FakeFlowRepository())
    broker.lose_exchange_after_terminal_once = True
    _started, broker, _consume_command, _used, command = await exchange_parts(broker=broker)
    result = await exchange_oauth_code_once(
        broker=broker,
        repository=broker.flow_repository,
        command=command,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
        now=command.issued_at,
    )
    assert isinstance(result, OAuthBrokerGrant)
    assert broker.provider_exchange_calls == 1
    assert broker.exchange_calls == 1
    assert broker.read_exchange_calls == 2
    assert FLOW_ID not in broker.verifiers


@pytest.mark.asyncio
async def test_unknown_exchange_loss_never_blindly_repeats_or_erases_verifier():
    broker = FakeBroker(FakeFlowRepository())
    broker.lose_exchange_without_terminal_once = True
    broker.hide_fence_read_once = True
    _started, broker, _consume_command, _used, command = await exchange_parts(broker=broker)
    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_RECOVERY_REQUIRED"):
        await exchange_oauth_code_once(
            broker=broker,
            repository=broker.flow_repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at,
        )
    assert broker.provider_exchange_calls == 1
    assert broker.exchange_calls == 1
    assert broker.read_exchange_calls == 2
    assert broker.verifiers[FLOW_ID] == VERIFIER
    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_RECOVERY_REQUIRED"):
        await exchange_oauth_code_once(
            broker=broker,
            repository=broker.flow_repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at + timedelta(seconds=30),
        )
    assert broker.provider_exchange_calls == 1
    assert broker.exchange_calls == 1


@pytest.mark.asyncio
async def test_ambiguous_result_is_returned_only_from_durable_broker_readback():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    durable = OAuthExchangeAmbiguous(
        exchange_id=command.exchange_id,
        exchange_binding_sha256=command.binding_sha256,
        observed_at=command.issued_at,
    )
    broker.exchange_bindings[command.exchange_id] = command.binding_sha256
    broker.exchange_terminals[command.exchange_id] = durable
    result = await exchange_oauth_code_once(
        broker=broker,
        repository=broker.flow_repository,
        command=command,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
        now=command.issued_at,
    )
    assert result is durable
    assert broker.exchange_calls == 0
    assert broker.provider_exchange_calls == 0
    assert broker.read_exchange_calls == 1


@pytest.mark.asyncio
async def test_unpersisted_direct_ambiguous_result_is_never_returned():
    class UnpersistedAmbiguousBroker(FakeBroker):
        async def exchange_once(
            self,
            *,
            command,
            permit,
            authorization_code,
        ):
            claim = await self._permit_authority.consume_exchange_permit_for_dispatch(
                command,
                permit,
            )
            self._require_permit_claim(command, permit, claim)
            self.exchange_calls += 1
            return OAuthExchangeAmbiguous(
                exchange_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                observed_at=command.issued_at,
            )

    broker = UnpersistedAmbiguousBroker(FakeFlowRepository())
    _started, broker, _consume_command, _used, command = await exchange_parts(broker=broker)
    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_RECOVERY_REQUIRED"):
        await exchange_oauth_code_once(
            broker=broker,
            repository=broker.flow_repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at,
        )
    assert broker.exchange_calls == 1


@pytest.mark.asyncio
async def test_broker_clock_atomically_fences_deadline_despite_backdated_caller_time():
    broker = FakeBroker(FakeFlowRepository())
    _started, broker, _consume_command, _used, command = await exchange_parts(broker=broker)
    broker.broker_now = command.deadline_at
    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_DEADLINE_EXPIRED"):
        await exchange_oauth_code_once(
            broker=broker,
            repository=broker.flow_repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at,
        )
    assert broker.provider_exchange_calls == 0
    assert isinstance(broker.exchange_terminals[command.exchange_id], OAuthExchangeAttemptFence)
    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_DEADLINE_EXPIRED"):
        await exchange_oauth_code_once(
            broker=broker,
            repository=broker.flow_repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at,
        )
    assert broker.exchange_calls == 1
    assert broker.read_exchange_calls == 2
    assert broker.verifiers[FLOW_ID] == VERIFIER


@pytest.mark.asyncio
async def test_exchange_quarantines_broker_read_and_dispatch_exceptions():
    for attr, code in (
        ("read_exchange_exception", "OAUTH_EXCHANGE_READ_FAILED"),
        ("exchange_exception", "OAUTH_EXCHANGE_DISPATCH_FAILED"),
    ):
        broker = FakeBroker(FakeFlowRepository())
        _started, broker, _consume_command, _used, command = await exchange_parts(
            broker=broker
        )
        setattr(broker, attr, OAuthContractError("raw-secret-token provider-body"))
        with pytest.raises(OAuthContractError) as caught:
            await exchange_oauth_code_once(
                broker=broker,
                repository=broker.flow_repository,
                command=command,
                authorization_code=OAuthAuthorizationCodeSecret(CODE),
                now=command.issued_at,
            )
        assert_content_free_error(caught.value, code)


@pytest.mark.asyncio
async def test_exchange_command_is_time_stable_across_callback_process_restart():
    started, _broker, consume_command, used, command = await exchange_parts()
    later_consume_command = prepare_oauth_consumption(
        started.flow,
        callback(),
        now=NOW + timedelta(minutes=1, seconds=30),
    )
    assert later_consume_command.binding_sha256 == consume_command.binding_sha256
    later_command = prepare_oauth_exchange(started.flow, used)
    assert later_command == command
    assert later_command.binding_sha256 == command.binding_sha256


@pytest.mark.asyncio
async def test_existing_exchange_is_recoverable_after_deadline_without_new_provider_call():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    first = await broker.exchange_once(
        command=command,
        permit=await broker.flow_repository.issue_exchange_permit_once(command),
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    recovered = await exchange_oauth_code_once(
        broker=broker,
        repository=broker.flow_repository,
        command=command,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
        now=command.deadline_at + timedelta(hours=1),
    )
    assert recovered is first
    assert broker.provider_exchange_calls == 1


@pytest.mark.asyncio
async def test_process_restart_reads_existing_exchange_before_provider_call():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    first = await broker.exchange_once(
        command=command,
        permit=await broker.flow_repository.issue_exchange_permit_once(command),
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    recovered = await exchange_oauth_code_once(
        broker=broker,
        repository=broker.flow_repository,
        command=command,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
        now=command.issued_at,
    )
    assert recovered is first
    assert broker.exchange_calls == 1
    assert broker.provider_exchange_calls == 1


@pytest.mark.asyncio
async def test_process_restart_can_recover_exchange_without_raw_code():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    first = await broker.exchange_once(
        command=command,
        permit=await broker.flow_repository.issue_exchange_permit_once(command),
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    recovered = await read_oauth_exchange_terminal(broker=broker, command=command)
    assert recovered is first
    assert broker.provider_exchange_calls == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"consumption_id": OTHER_ID},
        {"flow_id": OTHER_ID},
        {"nonce_id": OTHER_ID},
        {"owner_id": OTHER_ID},
        {"connection_id": OTHER_ID},
        {"connection_incarnation_id": OTHER_ID},
        {"expected_base_revision": BASE_REVISION + 1},
        {"current_flow_nonce_sha256": "5" * 64},
        {"session_binding_sha256": "9" * 64},
        {"provider": ConnectorProvider.MICROSOFT},
        {"resource": ConnectorResource.CALENDAR},
        {"account_kind": ConnectorAccountKind.WORK_SCHOOL},
        {"redirect_uri": OTHER_REDIRECT},
        {"actions_sha256": "8" * 64},
        {"requested_scopes_sha256": "7" * 64},
        {"consume_binding_sha256": "6" * 64},
    ],
)
@pytest.mark.asyncio
async def test_broker_grant_rejects_every_mutated_authority_and_redirect_binding(changes):
    _started, broker, _consume_command, _used, command = await exchange_parts()
    tampered = replace(broker_grant(command), **changes)
    broker.exchange_terminals[command.exchange_id] = tampered
    broker.exchange_bindings[command.exchange_id] = command.binding_sha256
    with pytest.raises(OAuthContractError, match="TERMINAL_BINDING_MISMATCH"):
        await exchange_oauth_code_once(
            broker=broker,
            repository=broker.flow_repository,
            command=command,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
            now=command.issued_at,
        )


@pytest.mark.asyncio
async def test_exchange_same_key_mismatched_redirect_binding_refuses_without_provider_call():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    first = await broker.exchange_once(
        command=command,
        permit=await broker.flow_repository.issue_exchange_permit_once(command),
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    assert isinstance(first, OAuthBrokerGrant)
    mismatched = replace(command, redirect_uri=OTHER_REDIRECT)
    with pytest.raises(OAuthContractError, match="TERMINAL_BINDING_MISMATCH"):
        await broker.read_exchange(command=mismatched)
    with pytest.raises(OAuthContractError, match="TERMINAL_BINDING_MISMATCH"):
        await broker.exchange_once(
            command=mismatched,
            permit=await broker.flow_repository.read_exchange_permit(command),
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
        )
    assert broker.provider_exchange_calls == 1


@pytest.mark.asyncio
async def test_scope_downgrade_or_expansion_rejects_before_completion():
    _started, broker, _consume_command, _used, command = await exchange_parts()
    for scopes in (frozenset({GMAIL_SEND}), frozenset({GMAIL_READ, GMAIL_SEND})):
        broker.exchange_terminals[command.exchange_id] = broker_grant(command, scopes=scopes)
        broker.exchange_bindings[command.exchange_id] = command.binding_sha256
        with pytest.raises(OAuthContractError, match="OAUTH_SCOPE_SET_MISMATCH"):
            await exchange_oauth_code_once(
                broker=broker,
                repository=broker.flow_repository,
                command=command,
                authorization_code=OAuthAuthorizationCodeSecret(CODE),
                now=command.issued_at,
            )
        broker.exchange_terminals.clear()
        broker.exchange_bindings.clear()


@pytest.mark.asyncio
async def test_finalization_has_no_caller_revision_and_repository_allocates_next_under_lock():
    started, _broker, _consume_command, used, command = await exchange_parts()
    assert "revision" not in inspect.signature(finalize_oauth_completion).parameters
    repository = FakeCompletionRepository(current_revision=BASE_REVISION)
    result = await finalize_oauth_completion(
        started.flow,
        used,
        command,
        broker_grant(command),
        repository=repository,
    )
    assert result.authorization.revision == BASE_REVISION + 1
    assert repository.current_revisions[CONNECTION_ID] == BASE_REVISION + 1
    assert result.connection_incarnation_id == INCARNATION_ID
    assert result.expected_base_revision == BASE_REVISION
    assert result.current_flow_nonce_sha256 == FLOW_NONCE_HASH
    assert result.authorization.granted_scopes == GMAIL_READ_SCOPES
    assert result.credential.handle_id == "broker-handle-opaque-00000001"
    assert "broker-handle-opaque" not in repr(result)
    assert ACCOUNT_HASH not in repr(result)


@pytest.mark.asyncio
async def test_completion_exact_replay_is_idempotent_and_does_not_advance_revision():
    started, _broker, _consume_command, used, command = await exchange_parts()
    repository = FakeCompletionRepository(current_revision=3)
    grant = broker_grant(command)
    first = await finalize_oauth_completion(
        started.flow,
        used,
        command,
        grant,
        repository=repository,
    )
    replay = await finalize_oauth_completion(
        started.flow,
        used,
        command,
        grant,
        repository=repository,
    )
    assert replay is first
    assert first.authorization.revision == 4
    assert repository.current_revisions[CONNECTION_ID] == 4
    assert repository.complete_calls == 1


@pytest.mark.asyncio
async def test_completion_response_loss_and_process_restart_use_durable_readback():
    started, _broker, _consume_command, used, command = await exchange_parts()
    repository = FakeCompletionRepository(current_revision=BASE_REVISION)
    repository.lose_after_store_once = True
    grant = broker_grant(command)
    result = await finalize_oauth_completion(
        started.flow,
        used,
        command,
        grant,
        repository=repository,
    )
    assert result.authorization.revision == BASE_REVISION + 1
    assert repository.complete_calls == 1
    recovered = await finalize_oauth_completion(
        started.flow,
        used,
        command,
        grant,
        repository=repository,
    )
    assert recovered is result
    assert repository.complete_calls == 1
    assert repository.current_revisions[CONNECTION_ID] == BASE_REVISION + 1


@pytest.mark.asyncio
async def test_completion_quarantines_repository_read_and_write_exceptions():
    started, _broker, _consume_command, used, command = await exchange_parts()
    for attr, code in (
        ("read_exception", "OAUTH_COMPLETION_READ_FAILED"),
        ("complete_exception", "OAUTH_COMPLETION_WRITE_FAILED"),
    ):
        repository = FakeCompletionRepository()
        setattr(repository, attr, RuntimeError("raw-secret-token provider-body"))
        with pytest.raises(OAuthContractError) as caught:
            await finalize_oauth_completion(
                started.flow,
                used,
                command,
                broker_grant(command),
                repository=repository,
            )
        assert_content_free_error(caught.value, code)


@pytest.mark.parametrize(
    "drift",
    ["revision", "incarnation", "new_flow", "disconnected", "replaced"],
)
@pytest.mark.asyncio
async def test_completion_rejects_stale_disconnect_replacement_and_new_flow_races(drift):
    started, _broker, _consume_command, used, command = await exchange_parts()
    repository = FakeCompletionRepository()
    if drift == "revision":
        repository.current_revisions[CONNECTION_ID] = BASE_REVISION + 1
    elif drift == "incarnation":
        repository.incarnation_id = OTHER_ID
    elif drift == "new_flow":
        repository.current_flow_nonce_sha256 = "9" * 64
    elif drift == "disconnected":
        repository.active = False
    else:
        repository.replaced = True
    with pytest.raises(OAuthContractError) as caught:
        await finalize_oauth_completion(
            started.flow,
            used,
            command,
            broker_grant(command),
            repository=repository,
        )
    assert_content_free_error(caught.value, "OAUTH_COMPLETION_STALE_CONNECTION")
    assert repository.records == {}
    assert len(repository.cleanup_records) == 1


@pytest.mark.parametrize("drift", ["revoked", "replaced", "new_flow", "revision"])
@pytest.mark.asyncio
async def test_completed_authority_replay_revalidates_live_state_and_queues_cleanup(drift):
    started, _broker, _consume_command, used, command = await exchange_parts()
    repository = FakeCompletionRepository()
    grant = broker_grant(command)
    completed = await finalize_oauth_completion(
        started.flow,
        used,
        command,
        grant,
        repository=repository,
    )
    assert completed.authorization.state is ConnectionAuthorizationState.ACTIVE
    if drift == "revoked":
        repository.active = False
    elif drift == "replaced":
        repository.replaced = True
    elif drift == "new_flow":
        repository.current_flow_nonce_sha256 = "9" * 64
    else:
        repository.current_revisions[CONNECTION_ID] += 1

    for _ in range(2):
        with pytest.raises(OAuthContractError) as caught:
            await finalize_oauth_completion(
                started.flow,
                used,
                command,
                grant,
                repository=repository,
            )
        assert_content_free_error(caught.value, "OAUTH_COMPLETION_STALE_CONNECTION")
    assert repository.complete_calls == 1
    assert len(repository.historicals) == 1
    inactive = next(iter(repository.historicals.values()))[1]
    assert isinstance(inactive, OAuthCompletionInactive)
    assert not hasattr(inactive, "credential")
    assert grant.credential.handle_id not in repr(inactive)
    assert len(repository.cleanup_records) == 1
    assert repository.cleanup_calls == 1


@pytest.mark.asyncio
async def test_stale_completion_cleanup_response_loss_is_recovered_idempotently():
    started, _broker, _consume_command, used, command = await exchange_parts()
    repository = FakeCompletionRepository()
    repository.active = False
    repository.lose_cleanup_after_store_once = True
    grant = broker_grant(command)
    with pytest.raises(OAuthContractError, match="OAUTH_COMPLETION_STALE_CONNECTION"):
        await finalize_oauth_completion(
            started.flow,
            used,
            command,
            grant,
            repository=repository,
        )
    assert repository.cleanup_calls == 1
    assert repository.cleanup_read_calls == 2
    assert len(repository.cleanup_records) == 1
    with pytest.raises(OAuthContractError, match="OAUTH_COMPLETION_STALE_CONNECTION"):
        await finalize_oauth_completion(
            started.flow,
            used,
            command,
            grant,
            repository=repository,
        )
    assert repository.cleanup_calls == 1


@pytest.mark.parametrize(
    "attr, code",
    [
        ("cleanup_read_exception", "OAUTH_CREDENTIAL_CLEANUP_READ_FAILED"),
        ("cleanup_exception", "OAUTH_CREDENTIAL_CLEANUP_WRITE_FAILED"),
    ],
)
@pytest.mark.asyncio
async def test_cleanup_outbox_quarantines_every_repository_exception(attr, code):
    started, _broker, _consume_command, used, command = await exchange_parts()
    repository = FakeCompletionRepository()
    repository.active = False
    setattr(repository, attr, OAuthContractError("raw-secret-token provider-body"))
    with pytest.raises(OAuthContractError) as caught:
        await finalize_oauth_completion(
            started.flow,
            used,
            command,
            broker_grant(command),
            repository=repository,
        )
    assert_content_free_error(caught.value, code)


@pytest.mark.parametrize("bad_revision", [BASE_REVISION, BASE_REVISION + 2, 99])
@pytest.mark.asyncio
async def test_completion_requires_exact_base_revision_plus_one(bad_revision):
    started, _broker, _consume_command, used, command = await exchange_parts()
    repository = FakeCompletionRepository()
    completed = await finalize_oauth_completion(
        started.flow,
        used,
        command,
        broker_grant(command),
        repository=repository,
    )
    bad_authorization = replace(completed.authorization, revision=bad_revision)
    malformed = replace(completed, authorization=bad_authorization)
    completion_binding = repository.records[command.exchange_id][0]
    repository.records[command.exchange_id] = (completion_binding, malformed)
    repository.current_revisions[CONNECTION_ID] = bad_revision
    with pytest.raises(OAuthContractError, match="OAUTH_COMPLETION_BINDING_MISMATCH"):
        await finalize_oauth_completion(
            started.flow,
            used,
            command,
            broker_grant(command),
            repository=repository,
        )


def test_negative_base_revision_is_rejected_before_completion():
    with pytest.raises(ValueError, match="nonnegative"):
        OAuthCompletionCommand(
            completion_id=FLOW_ID,
            consumption_id=FLOW_ID,
            exchange_id=FLOW_ID,
            owner_id=OWNER_ID,
            connection_id=CONNECTION_ID,
            connection_incarnation_id=INCARNATION_ID,
            expected_base_revision=-1,
            current_flow_nonce_sha256=FLOW_NONCE_HASH,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.MAIL,
            account_kind=ConnectorAccountKind.PERSONAL,
            redirect_uri=REDIRECT,
            flow_binding_sha256="3" * 64,
            exchange_binding_sha256="4" * 64,
            credential=CredentialHandleRef(
                owner_id=OWNER_ID,
                connection_id=CONNECTION_ID,
                provider=ConnectorProvider.GOOGLE,
                handle_id="broker-handle-opaque-00000001",
            ),
            external_account_id_hash=ACCOUNT_HASH,
            granted_actions=frozenset({ConnectorActionKind.MAIL_SEARCH}),
            granted_actions_sha256=action_hash(
                frozenset({ConnectorActionKind.MAIL_SEARCH})
            ),
            granted_scopes=GMAIL_READ_SCOPES,
            granted_scopes_sha256=scope_hash(GMAIL_READ_SCOPES),
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )


@pytest.mark.asyncio
async def test_completion_rejects_external_account_swap_for_existing_connection():
    started, _broker, _consume_command, used, command = await exchange_parts()
    repository = FakeCompletionRepository(external_account_id_hash=ACCOUNT_HASH)
    swapped = replace(broker_grant(command), external_account_id_hash="9" * 64)
    with pytest.raises(OAuthContractError) as caught:
        await finalize_oauth_completion(
            started.flow,
            used,
            command,
            swapped,
            repository=repository,
        )
    assert_content_free_error(caught.value, "OAUTH_COMPLETION_STALE_CONNECTION")
    assert repository.records == {}
    assert len(repository.cleanup_records) == 1


@pytest.mark.asyncio
async def test_replacement_account_requires_new_connection_id_and_invalidates_old_grant():
    old_started, _broker, _consume_command, old_used, old_command = await exchange_parts()
    old_repository = FakeCompletionRepository()
    old_repository.replaced = True
    with pytest.raises(OAuthContractError, match="OAUTH_COMPLETION_STALE_CONNECTION"):
        await finalize_oauth_completion(
            old_started.flow,
            old_used,
            old_command,
            broker_grant(old_command),
            repository=old_repository,
        )
    assert len(old_repository.cleanup_records) == 1

    new_nonce_hash = hashlib.sha256(OTHER_ID.encode()).hexdigest()
    new_flow_repository = FakeFlowRepository(
        connection_id=NEW_CONNECTION_ID,
        incarnation_id=NEW_INCARNATION_ID,
        revision=0,
    )
    new_started, _ = await start(
        repository=new_flow_repository,
        flow_id=OTHER_ID,
        nonce_id=OTHER_ID,
        connection_id=NEW_CONNECTION_ID,
        connection_incarnation_id=NEW_INCARNATION_ID,
        expected_base_revision=0,
        current_flow_nonce_sha256=new_nonce_hash,
    )
    # Callback has no connection ID field; the flow/session binding supplies it.
    new_callback = OAuthCallbackAttempt(
        flow_id=OTHER_ID,
        owner_id=OWNER_ID,
        session_binding_sha256=SESSION_HASH,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        redirect_uri=REDIRECT,
        secrets=OAuthCallbackSecrets(authorization_code=CODE, state=STATE),
    )
    consume_command = prepare_oauth_consumption(
        new_started.flow,
        new_callback,
        now=NOW + timedelta(minutes=1),
    )
    used = await consume_oauth_flow_once(
        repository=new_flow_repository,
        command=consume_command,
    )
    exchange_command = prepare_oauth_exchange(new_started.flow, used)
    new_repository = FakeCompletionRepository(
        connection_id=NEW_CONNECTION_ID,
        incarnation_id=NEW_INCARNATION_ID,
        current_revision=0,
        current_flow_nonce_sha256=new_nonce_hash,
        external_account_id_hash=None,
    )
    completed = await finalize_oauth_completion(
        new_started.flow,
        used,
        exchange_command,
        broker_grant(
            exchange_command,
            connection_id=NEW_CONNECTION_ID,
        ),
        repository=new_repository,
    )
    assert completed.authorization.connection_id == NEW_CONNECTION_ID
    assert completed.authorization.revision == 1


@pytest.mark.asyncio
async def test_completion_same_key_mismatched_grant_refuses_without_revision_change():
    started, _broker, _consume_command, used, command = await exchange_parts()
    repository = FakeCompletionRepository(current_revision=BASE_REVISION)
    grant = broker_grant(command)
    first = await finalize_oauth_completion(
        started.flow,
        used,
        command,
        grant,
        repository=repository,
    )
    assert first.authorization.revision == BASE_REVISION + 1
    mismatched = replace(grant, external_account_id_hash="9" * 64)
    with pytest.raises(OAuthContractError, match="OAUTH_COMPLETION_READ_FAILED"):
        await finalize_oauth_completion(
            started.flow,
            used,
            command,
            mismatched,
            repository=repository,
        )
    assert repository.current_revisions[CONNECTION_ID] == BASE_REVISION + 1
    assert repository.complete_calls == 1


@pytest.mark.asyncio
async def test_completion_rejects_redirect_mismatch_even_with_rebound_exchange_hash():
    started, _broker, _consume_command, used, command = await exchange_parts()
    mismatched_command = replace(command, redirect_uri=OTHER_REDIRECT)
    mismatched_grant = broker_grant(mismatched_command)
    with pytest.raises(OAuthContractError, match="OAUTH_COMPLETION_BINDING_MISMATCH"):
        await finalize_oauth_completion(
            started.flow,
            used,
            mismatched_command,
            mismatched_grant,
            repository=FakeCompletionRepository(),
        )


def test_all_persistable_reprs_redact_hashes_and_raw_secrets():
    classes = (
        OAuthBrokerFlowCommand,
        OAuthBrokerFlowReceipt,
        OAuthFlowRecord,
        OAuthConsumeCommand,
        OAuthFlowConsumption,
        OAuthExchangeCommand,
        OAuthExchangePermitRecord,
        OAuthExchangePermitClaim,
        OAuthBrokerGrant,
        OAuthCompletionCommand,
        OAuthCompletion,
        OAuthCompletionInactive,
        OAuthCredentialCleanupCommand,
        OAuthCredentialCleanupReceipt,
    )
    for contract in classes:
        names = {item.name for item in fields(contract)}
        assert "access_token" not in names
        assert "refresh_token" not in names
        assert "authorization_code" not in names
        assert "pkce_verifier" not in names


@pytest.mark.asyncio
async def test_runtime_reprs_never_leak_binding_hashes_codes_state_or_verifier():
    started, broker, consume_command, used, exchange_command = await exchange_parts()
    permit = await broker.flow_repository.issue_exchange_permit_once(exchange_command)
    permit_record = broker.flow_repository.permits[exchange_command.exchange_id]
    grant = broker_grant(exchange_command)
    completion_command = OAuthCompletionCommand(
        completion_id=used.consumption_id,
        consumption_id=used.consumption_id,
        exchange_id=exchange_command.exchange_id,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        connection_incarnation_id=INCARNATION_ID,
        expected_base_revision=BASE_REVISION,
        current_flow_nonce_sha256=FLOW_NONCE_HASH,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        redirect_uri=REDIRECT,
        flow_binding_sha256=started.flow.binding_sha256,
        exchange_binding_sha256=exchange_command.binding_sha256,
        credential=grant.credential,
        external_account_id_hash=ACCOUNT_HASH,
        granted_actions=started.flow.actions,
        granted_actions_sha256=started.flow.actions_sha256,
        granted_scopes=grant.actual_scopes,
        granted_scopes_sha256=grant.actual_scopes_sha256,
        issued_at=grant.issued_at,
        expires_at=grant.expires_at,
    )
    inactive = OAuthCompletionInactive(
        completion_id=completion_command.completion_id,
        completion_binding_sha256=completion_command.binding_sha256,
        connection_id=completion_command.connection_id,
        observed_at=grant.issued_at,
        reason="revoked",
    )
    cleanup = OAuthCredentialCleanupCommand(
        cleanup_id=completion_command.exchange_id,
        completion_id=completion_command.completion_id,
        exchange_id=completion_command.exchange_id,
        owner_id=completion_command.owner_id,
        connection_id=completion_command.connection_id,
        connection_incarnation_id=completion_command.connection_incarnation_id,
        provider=completion_command.provider,
        credential=completion_command.credential,
        exchange_binding_sha256=completion_command.exchange_binding_sha256,
        completion_binding_sha256=completion_command.binding_sha256,
    )
    cleanup_receipt = OAuthCredentialCleanupReceipt(
        cleanup_id=cleanup.cleanup_id,
        cleanup_binding_sha256=cleanup.binding_sha256,
        recorded_at=grant.issued_at,
    )
    objects = (
        started.flow,
        consume_command,
        used,
        exchange_command,
        permit_record,
        permit,
        grant,
        completion_command,
        inactive,
        cleanup,
        cleanup_receipt,
    )
    hidden = {
        STATE,
        CODE,
        VERIFIER,
        SESSION_HASH,
        ACCOUNT_HASH,
        started.flow.binding_sha256,
        consume_command.binding_sha256,
        exchange_command.binding_sha256,
        permit.permit_binding_sha256,
        permit_record.capability_sha256,
        PERMIT_SECRET,
        completion_command.binding_sha256,
        cleanup.binding_sha256,
    }
    for item in objects:
        rendered = repr(item)
        assert all(value not in rendered for value in hidden)
