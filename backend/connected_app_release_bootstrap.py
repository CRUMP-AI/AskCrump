"""Supervised, release-only OAuth bootstrap for dedicated preview accounts.

This module is deliberately not an HTTP route and is never imported by normal
application composition.  It reuses the production OAuth repositories, broker,
provider client, credential vault, and owner/session binding while keeping the
public connected-app release lock false.

The browser ceremony lives in ``scripts/bootstrap-connected-preview-oauth.py``.
Raw browser cookies, OAuth state, authorization codes, provider tokens, client
secrets, and root key material never cross the types in this module as
serializable values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
from types import MappingProxyType
from typing import Mapping, NoReturn
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID, UUID as UUIDValue, uuid5

from starlette.requests import Request

from . import config
from .auth_service import session_tokens_from_request, token_hash
from .config import PRODUCTION_SUPABASE_ORIGIN, Settings
from .connected_app_contracts import (
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
)
from .connected_app_credential_vault import (
    ConnectedCredentialVault,
)
from .connected_app_durable_stores import SupabaseConnectedCredentialSecretStore
from .connected_app_durable_oauth import (
    DurableOAuthCredentialBroker,
    SupabaseOAuthSecretStore,
)
from .connected_app_grant_cleanup import SupabaseConnectedGrantCleanupStore
from .connected_app_host_configuration import (
    ConnectedHostConfiguration,
    ConnectedReleasePreviewConnectionConfiguration,
)
from .connected_app_oauth import (
    OAuthBrokerFlowLookup,
    OAuthBrokerGrant,
    OAuthCallbackSecrets,
    OAuthCompletion,
    OAuthExchangeAmbiguous,
    OAuthFlowState,
    OAuthRedirectAllowlist,
    _completion_command,
    finalize_oauth_completion,
    prepare_oauth_exchange,
    read_oauth_exchange_terminal,
    recover_oauth_flow_consumption,
)
from .connected_app_oauth_control import ConnectedAppOAuthOrchestrator
from .connected_app_oauth_code_custody import (
    ConnectedOAuthAuthorizationCodeVault,
    SupabaseOAuthAuthorizationCodeCustodyStore,
)
from .connected_app_oauth_control_supabase import (
    SupabaseConnectedOAuthOperatorStore,
)
from .connected_app_oauth_supabase import (
    SupabaseConnectedAccountRegistry,
    SupabaseOAuthCompletionRepository,
    SupabaseOAuthFlowRepository,
)
from .connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from .connected_app_production_keys import ConnectedProductionKeys
from .connected_app_provider_oauth import (
    ProviderOAuthHTTPSClient,
    ProviderOAuthRegistration,
)
from .connected_app_release_database import (
    ConnectedReleasePreviewProductionDatabase,
)
from .connected_app_runtime import ConnectedAccountBinding
from .connected_app_service import (
    OAuthCallbackCommand,
    OAuthStartCommand,
    OAuthStartView,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COOKIE = re.compile(r"^[\x21-\x3a\x3c-\x7e]{1,16384}$")
_CALLBACK_SECRET = re.compile(r"^[^\x00-\x20\x7f]{1,4096}$")
_CALLBACK_OPTIONAL = re.compile(r"^[^\x00-\x1f\x7f]{1,2048}$")
_SCOPE_TOKEN = re.compile(r"^[\x21-\x7e]{1,512}$")
_BOOTSTRAP_NAMESPACE = UUIDValue("076e4e3a-3938-4daf-a323-e7a44888e39e")
_PRODUCTION_ORIGIN = "https://www.askcrump.com"
_REDIRECTS = MappingProxyType(
    {
        ConnectorProvider.GOOGLE: (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
        ),
        ConnectorProvider.MICROSOFT: (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
        ),
    }
)
_MAIL_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_SEARCH,
        ConnectorActionKind.MAIL_GET,
        ConnectorActionKind.MAIL_CREATE_DRAFT,
        ConnectorActionKind.MAIL_SEND,
        ConnectorActionKind.MAIL_REPLY,
    }
)
_CALENDAR_BASE_ACTIONS = frozenset(
    {
        ConnectorActionKind.CALENDAR_LIST,
        ConnectorActionKind.CALENDAR_GET,
        ConnectorActionKind.CALENDAR_CREATE,
        ConnectorActionKind.CALENDAR_UPDATE,
        ConnectorActionKind.CALENDAR_CANCEL,
    }
)
_CALENDAR_FREE_BUSY_ACTIONS = _CALENDAR_BASE_ACTIONS | {
    ConnectorActionKind.CALENDAR_FREE_BUSY
}


class ConnectedReleaseBootstrapError(RuntimeError):
    """A fixed, content-free bootstrap failure safe for the ceremony console."""

    _CODES = frozenset(
        {
            "CONNECTED_RELEASE_BOOTSTRAP_INVALID",
            "CONNECTED_RELEASE_BOOTSTRAP_NOT_RELEASED",
            "CONNECTED_RELEASE_BOOTSTRAP_AUTH_FAILED",
            "CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID",
            "CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_DENIED",
            "CONNECTED_RELEASE_BOOTSTRAP_REPLAYED",
            "CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED",
            "CONNECTED_RELEASE_BOOTSTRAP_CODE_LOST_AFTER_CONSUME",
            "CONNECTED_RELEASE_BOOTSTRAP_EXCHANGE_AMBIGUOUS",
            "CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = (
            code if code in self._CODES else "CONNECTED_RELEASE_BOOTSTRAP_INVALID"
        )
        super().__init__(self.code)


def _fail(code: str = "CONNECTED_RELEASE_BOOTSTRAP_INVALID") -> NoReturn:
    raise ConnectedReleaseBootstrapError(code)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        _fail()
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        _fail()
    if str(parsed) != value:
        _fail()
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail()
    return value


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_release_bootstrap_source_boundary() -> None:
    """Require preview source release while the public product stays locked."""

    if (
        config.connected_apps_release_candidate_source_released() is not True
    ):
        _fail("CONNECTED_RELEASE_BOOTSTRAP_NOT_RELEASED")


@dataclass(frozen=True, slots=True)
class ConnectedReleaseBootstrapTarget:
    """One machine-bound provider/account-kind/resource OAuth target."""

    ordinal: int
    provider: ConnectorProvider
    account_kind: ConnectorAccountKind
    resource: ConnectorResource
    actions: frozenset[ConnectorActionKind]

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int
            or not 0 <= self.ordinal < 6
            or not isinstance(self.provider, ConnectorProvider)
            or not isinstance(self.account_kind, ConnectorAccountKind)
            or not isinstance(self.resource, ConnectorResource)
            or not isinstance(self.actions, frozenset)
            or not self.actions
        ):
            _fail()
        expected = _MAIL_ACTIONS
        if self.resource is ConnectorResource.CALENDAR:
            expected = (
                _CALENDAR_BASE_ACTIONS
                if self.provider is ConnectorProvider.MICROSOFT
                and self.account_kind is ConnectorAccountKind.PERSONAL
                else _CALENDAR_FREE_BUSY_ACTIONS
            )
        if self.actions != expected:
            _fail()
        if (
            self.provider is ConnectorProvider.GOOGLE
            and self.account_kind is not ConnectorAccountKind.PERSONAL
        ):
            _fail()

    @property
    def key(self) -> str:
        return ".".join(
            (self.provider.value, self.account_kind.value, self.resource.value)
        )

    @property
    def redirect_uri(self) -> str:
        return _REDIRECTS[self.provider]


def _targets() -> tuple[ConnectedReleaseBootstrapTarget, ...]:
    values: list[ConnectedReleaseBootstrapTarget] = []
    ordinal = 0
    for provider, account_kinds in (
        (ConnectorProvider.GOOGLE, (ConnectorAccountKind.PERSONAL,)),
        (
            ConnectorProvider.MICROSOFT,
            (
                ConnectorAccountKind.PERSONAL,
                ConnectorAccountKind.WORK_SCHOOL,
            ),
        ),
    ):
        for account_kind in account_kinds:
            calendar_actions = (
                _CALENDAR_BASE_ACTIONS
                if provider is ConnectorProvider.MICROSOFT
                and account_kind is ConnectorAccountKind.PERSONAL
                else _CALENDAR_FREE_BUSY_ACTIONS
            )
            for resource, actions in (
                (ConnectorResource.MAIL, _MAIL_ACTIONS),
                (ConnectorResource.CALENDAR, calendar_actions),
            ):
                values.append(
                    ConnectedReleaseBootstrapTarget(
                        ordinal=ordinal,
                        provider=provider,
                        account_kind=account_kind,
                        resource=resource,
                        actions=actions,
                    )
                )
                ordinal += 1
    return tuple(values)


CONNECTED_RELEASE_BOOTSTRAP_TARGETS = _targets()


def target_for_key(value: str) -> ConnectedReleaseBootstrapTarget:
    matches = tuple(target for target in CONNECTED_RELEASE_BOOTSTRAP_TARGETS if target.key == value)
    if len(matches) != 1:
        _fail()
    return matches[0]


def bootstrap_request_id(
    *,
    ceremony_id: str,
    target: ConnectedReleaseBootstrapTarget,
    generation: int,
) -> str:
    """Derive a distinct durable request identity for every fresh OAuth state."""

    ceremony = _uuid(ceremony_id)
    if (
        type(target) is not ConnectedReleaseBootstrapTarget
        or type(generation) is not int
        or not 1 <= generation <= 100
    ):
        _fail()
    return str(
        uuid5(
            _BOOTSTRAP_NAMESPACE,
            f"{ceremony}\0{target.key}\0{generation}",
        )
    )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedReleaseBootstrapIdentity:
    """Current Ask Crump account and exact HttpOnly-session binding."""

    owner_id: str
    session_id: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_id", _uuid(self.owner_id))
        object.__setattr__(self, "session_id", _uuid(self.session_id))

    @property
    def session_binding_sha256(self) -> str:
        return _digest(self.session_id)

    def __repr__(self) -> str:
        return "ConnectedReleaseBootstrapIdentity(bindings='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("release-bootstrap identities cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("release-bootstrap identities cannot be serialized")


class ConnectedReleaseBootstrapPermit:
    """One-use explicit user confirmation for one supervised ceremony."""

    __slots__ = ("_ceremony_id", "_consumed", "_expires_at", "_issued_at")

    def __init__(self, *, ceremony_id: str, confirmation: str) -> None:
        ceremony = _uuid(ceremony_id)
        expected = f"CONFIRM CONNECTED PREVIEW {ceremony}"
        if not isinstance(confirmation, str) or not hmac.compare_digest(
            confirmation, expected
        ):
            _fail()
        issued = datetime.now(UTC)
        self._ceremony_id = ceremony
        self._consumed = False
        self._issued_at = issued
        self._expires_at = issued + timedelta(minutes=2)

    def consume(self, *, ceremony_id: str) -> None:
        reference = datetime.now(UTC)
        if (
            self._consumed
            or reference < self._issued_at
            or reference >= self._expires_at
            or not hmac.compare_digest(
                self._ceremony_id, _uuid(ceremony_id)
            )
        ):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_REPLAYED")
        self._consumed = True

    def __repr__(self) -> str:
        return "ConnectedReleaseBootstrapPermit(authority='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("release-bootstrap permits cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("release-bootstrap permits cannot be serialized")


class ConnectedReleaseDedicatedAccountPermit:
    """One-use operator attestation over the exact six sealed descriptors."""

    __slots__ = (
        "_attestation_sha256",
        "_ceremony_id",
        "_consumed",
        "_expires_at",
        "_issued_at",
        "_matrix_sha256",
        "_owner_id",
    )

    def __init__(
        self,
        *,
        ceremony_id: str,
        owner_id: str,
        descriptor_matrix_sha256: str,
        confirmation: str,
    ) -> None:
        ceremony = _uuid(ceremony_id)
        owner = _uuid(owner_id)
        matrix = _sha(descriptor_matrix_sha256)
        expected = (
            "CONFIRM THREE DEDICATED NON-CUSTOMER ACCOUNTS "
            f"{ceremony} {matrix[:16]}"
        )
        if not isinstance(confirmation, str) or not hmac.compare_digest(
            confirmation,
            expected,
        ):
            _fail()
        issued = datetime.now(UTC)
        self._ceremony_id = ceremony
        self._owner_id = owner
        self._matrix_sha256 = matrix
        self._issued_at = issued
        self._expires_at = issued + timedelta(minutes=2)
        self._consumed = False
        self._attestation_sha256 = _digest(
            "\0".join(
                (
                    "askcrump-release-preview-dedicated-account-attestation-v1",
                    ceremony,
                    owner,
                    matrix,
                    "three_dedicated_non_customer_accounts",
                )
            )
        )

    def consume(
        self,
        *,
        ceremony_id: str,
        owner_id: str,
        descriptor_matrix_sha256: str,
    ) -> str:
        reference = datetime.now(UTC)
        if (
            self._consumed
            or reference < self._issued_at
            or reference >= self._expires_at
            or not hmac.compare_digest(self._ceremony_id, _uuid(ceremony_id))
            or not hmac.compare_digest(self._owner_id, _uuid(owner_id))
            or not hmac.compare_digest(
                self._matrix_sha256,
                _sha(descriptor_matrix_sha256),
            )
        ):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_REPLAYED")
        self._consumed = True
        return self._attestation_sha256

    def __repr__(self) -> str:
        return "ConnectedReleaseDedicatedAccountPermit(authority='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("dedicated-account permits cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("dedicated-account permits cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedReleaseBootstrapCallback:
    """Memory-only provider callback captured before the network request."""

    provider: ConnectorProvider
    secrets: OAuthCallbackSecrets = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ConnectorProvider) or not isinstance(
            self.secrets, OAuthCallbackSecrets
        ):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")

    def __repr__(self) -> str:
        return (
            "ConnectedReleaseBootstrapCallback("
            f"provider={self.provider.value!r}, secrets='<redacted>')"
        )

    def __getstate__(self) -> object:
        raise TypeError("release-bootstrap callbacks cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("release-bootstrap callbacks cannot be serialized")


def parse_intercepted_callback(
    *,
    callback_url: str,
    target: ConnectedReleaseBootstrapTarget,
    expected_state_sha256: str,
) -> ConnectedReleaseBootstrapCallback:
    """Validate an exact fixed callback without retaining its raw URL."""

    if (
        not isinstance(callback_url, str)
        or len(callback_url) > 8192
        or type(target) is not ConnectedReleaseBootstrapTarget
    ):
        _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    expected_state = _sha(expected_state_sha256)
    try:
        parsed = urlsplit(callback_url)
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=8,
        )
    except ValueError:
        _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    expected = urlsplit(target.redirect_uri)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.askcrump.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path != expected.path
        or parsed.fragment
        or len({key for key, _value in pairs}) != len(pairs)
    ):
        _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    values = dict(pairs)
    keys = set(values)
    optional = (
        {"scope", "authuser", "prompt", "hd"}
        if target.provider is ConnectorProvider.GOOGLE
        else {"session_state", "client_info"}
    )
    raw_state = values.get("state")
    if (
        not isinstance(raw_state, str)
        or _CALLBACK_SECRET.fullmatch(raw_state) is None
        or not hmac.compare_digest(_digest(raw_state), expected_state)
    ):
        _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    if "error" in keys:
        if (
            "code" in keys
            or not {"error", "state"}.issubset(keys)
            or not keys.issubset(
                {"error", "error_description", "error_uri", "state"}
            )
            or values.get("error") != "access_denied"
        ):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
        for key in {"error", "error_description", "error_uri"} & keys:
            value = values[key]
            if (
                not isinstance(value, str)
                or _CALLBACK_OPTIONAL.fullmatch(value) is None
            ):
                _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
        _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_DENIED")
    if not {"code", "state"}.issubset(keys) or not keys.issubset(
        {"code", "state"} | optional
    ):
        _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    if _CALLBACK_SECRET.fullmatch(values["code"]) is None:
        _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    if "scope" in values:
        scopes = values["scope"].split(" ")
        if (
            not scopes
            or len(scopes) != len(set(scopes))
            or any(_SCOPE_TOKEN.fullmatch(scope) is None for scope in scopes)
        ):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    for key in optional - {"scope"}:
        if key in values and _CALLBACK_OPTIONAL.fullmatch(values[key]) is None:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    if target.provider is ConnectorProvider.GOOGLE and "authuser" in values:
        if re.fullmatch(r"[0-9]{1,3}", values["authuser"]) is None:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    if target.provider is ConnectorProvider.MICROSOFT and "session_state" in values:
        try:
            if str(UUID(values["session_state"])) != values["session_state"]:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    if any(
        character.isspace()
        for key in {"code", "state"}
        for character in values[key]
    ):
        _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    try:
        secrets = OAuthCallbackSecrets(
            authorization_code=values["code"],
            state=values["state"],
        )
    except (TypeError, ValueError):
        _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
    return ConnectedReleaseBootstrapCallback(
        provider=target.provider,
        secrets=secrets,
    )


class ConnectedReleaseOAuthBootstrap:
    """Exact production OAuth subgraph for the supervised bootstrap ceremony."""

    __slots__ = (
        "_accounts",
        "_broker",
        "_clients",
        "_completions",
        "_database",
        "_flows",
        "_host",
        "_operator",
        "_operator_store",
        "_settings",
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        _fail()

    @classmethod
    def build_production(
        cls,
        *,
        keys: ConnectedProductionKeys,
        host: ConnectedHostConfiguration,
    ) -> "ConnectedReleaseOAuthBootstrap":
        """Build only exact dependencies; transports/database/sleep are not injectable."""

        require_release_bootstrap_source_boundary()
        from .runtime import settings

        if (
            type(settings) is not Settings
            or settings.environment != "production"
            or settings.app_url.rstrip("/") not in {
                "https://askcrump.com",
                _PRODUCTION_ORIGIN,
            }
            or settings.supabase_url.rstrip("/") != PRODUCTION_SUPABASE_ORIGIN
            or not settings.supabase_service_key
            or type(keys) is not ConnectedProductionKeys
            or type(host) is not ConnectedHostConfiguration
            or host.composition_manifest_sha256
            != keys.composition_manifest_sha256
            or host.release_preview_connections
        ):
            _fail()
        now = lambda: datetime.now(UTC)
        database = ConnectedReleasePreviewProductionDatabase()
        if not database.production_eligible():
            _fail()
        registrations = dict(host.registrations)
        redirect_uris = dict(_REDIRECTS)
        clients = {
            provider: ProviderOAuthHTTPSClient(
                registrations[provider],
                transport=None,
                now=now,
            )
            for provider in ConnectorProvider
        }
        credential_vault = ConnectedCredentialVault(
            keys={keys.credential_envelope.key_id: keys.credential_envelope},
            active_key_id=keys.credential_envelope.key_id,
            store=SupabaseConnectedCredentialSecretStore(database),
            now=now,
        )
        flows = SupabaseOAuthFlowRepository(
            database=database,
            redirect_uris=redirect_uris,
            permit_keys={keys.oauth_permit.key_id: keys.oauth_permit},
            active_permit_key_id=keys.oauth_permit.key_id,
            now=now,
        )
        completions = SupabaseOAuthCompletionRepository(database)
        broker = DurableOAuthCredentialBroker(
            keys={keys.oauth_envelope.key_id: keys.oauth_envelope},
            active_key_id=keys.oauth_envelope.key_id,
            store=SupabaseOAuthSecretStore(database),
            permit_authority=flows,
            clients=clients,
            credential_vault=credential_vault,
            grant_cleanup_store=SupabaseConnectedGrantCleanupStore(database),
            now=now,
        )
        operator_store = SupabaseConnectedOAuthOperatorStore(
            database=database,
            flow_decoder=flows,
            redirect_uris=redirect_uris,
        )
        value = object.__new__(cls)
        value._settings = settings
        value._database = database
        value._host = host
        value._clients = clients
        value._flows = flows
        value._completions = completions
        value._accounts = SupabaseConnectedAccountRegistry(database)
        value._broker = broker
        value._operator_store = operator_store
        value._operator = ConnectedAppOAuthOrchestrator(
            store=operator_store,
            broker=broker,
            flows=flows,
            completions=completions,
            registrations=registrations,
            redirect_allowlists={
                provider: OAuthRedirectAllowlist(
                    frozenset({redirect_uris[provider]})
                )
                for provider in ConnectorProvider
            },
            now=now,
            authorization_code_custody=ConnectedOAuthAuthorizationCodeVault(
                key=keys.oauth_code_envelope,
                store=SupabaseOAuthAuthorizationCodeCustodyStore(database),
            ),
        )
        if not value.production_eligible():
            _fail()
        return value

    def production_eligible(self) -> bool:
        """Recursively prove that no test transport/database/sleep was injected."""

        return bool(
            type(self) is ConnectedReleaseOAuthBootstrap
            and type(self._database) is ConnectedReleasePreviewProductionDatabase
            and self._database.production_eligible()
            and type(self._operator) is ConnectedAppOAuthOrchestrator
            and type(self._operator._authorization_code_custody)
            is ConnectedOAuthAuthorizationCodeVault
            and type(self._operator._authorization_code_custody._store)
            is SupabaseOAuthAuthorizationCodeCustodyStore
            and self._operator._authorization_code_custody._store._rpc
            is self._database
            and type(self._flows) is SupabaseOAuthFlowRepository
            and type(self._completions) is SupabaseOAuthCompletionRepository
            and type(self._accounts) is SupabaseConnectedAccountRegistry
            and type(self._broker) is DurableOAuthCredentialBroker
            and type(self._operator_store) is SupabaseConnectedOAuthOperatorStore
            and set(self._clients) == set(ConnectorProvider)
            and all(
                type(client) is ProviderOAuthHTTPSClient
                and client._transport is None
                for client in self._clients.values()
            )
        )

    async def authenticate_cookie(
        self,
        cookie_header: str,
    ) -> ConnectedReleaseBootstrapIdentity:
        """Authenticate one captured Ask Crump HttpOnly cookie in memory only."""

        require_release_bootstrap_source_boundary()
        if (
            not self.production_eligible()
            or not isinstance(cookie_header, str)
            or _COOKIE.fullmatch(cookie_header) is None
        ):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_AUTH_FAILED")
        request = Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "scheme": "https",
                "path": "/app",
                "raw_path": b"/app",
                "query_string": b"",
                "headers": (
                    (b"host", b"www.askcrump.com"),
                    (b"cookie", cookie_header.encode("latin-1", errors="strict")),
                ),
                "client": ("127.0.0.1", 0),
                "server": ("www.askcrump.com", 443),
            }
        )
        try:
            tokens = session_tokens_from_request(request, self._settings)
            if len(tokens) != 1:
                _fail("CONNECTED_RELEASE_BOOTSTRAP_AUTH_FAILED")
            value = await self._database.rpc(
                "connected_app_release_bootstrap_authenticate_v1",
                {"p_session_token_sha256": token_hash(tokens[0])},
                retry_transient=False,
            )
            if (
                not isinstance(value, dict)
                or set(value) != {"authenticated", "owner_id", "session_id"}
                or value["authenticated"] is not True
            ):
                _fail("CONNECTED_RELEASE_BOOTSTRAP_AUTH_FAILED")
            return ConnectedReleaseBootstrapIdentity(
                owner_id=value["owner_id"],
                session_id=value["session_id"],
            )
        except ConnectedReleaseBootstrapError:
            raise
        except Exception:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_AUTH_FAILED")

    def begin(
        self,
        *,
        ceremony_id: str,
        permit: ConnectedReleaseBootstrapPermit,
        identity: ConnectedReleaseBootstrapIdentity,
    ) -> "ConnectedReleaseOAuthBootstrapSession":
        require_release_bootstrap_source_boundary()
        if (
            not self.production_eligible()
            or type(permit) is not ConnectedReleaseBootstrapPermit
            or type(identity) is not ConnectedReleaseBootstrapIdentity
        ):
            _fail()
        permit.consume(ceremony_id=ceremony_id)
        return ConnectedReleaseOAuthBootstrapSession(
            _bootstrap=self,
            _ceremony_id=_uuid(ceremony_id),
            _identity=identity,
        )

    def __repr__(self) -> str:
        return "ConnectedReleaseOAuthBootstrap(authority='production-exact')"

    def __getstate__(self) -> object:
        raise TypeError("release OAuth bootstrap graphs cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("release OAuth bootstrap graphs cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedReleaseOAuthBootstrapSession:
    """One owner/session-bound sequential bootstrap session."""

    _bootstrap: ConnectedReleaseOAuthBootstrap = field(repr=False, compare=False)
    _ceremony_id: str
    _identity: ConnectedReleaseBootstrapIdentity = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            type(self._bootstrap) is not ConnectedReleaseOAuthBootstrap
            or type(self._identity) is not ConnectedReleaseBootstrapIdentity
        ):
            _fail()
        _uuid(self._ceremony_id)

    @property
    def ceremony_id(self) -> str:
        return self._ceremony_id

    def require_same_identity(
        self,
        identity: ConnectedReleaseBootstrapIdentity,
    ) -> None:
        if type(identity) is not ConnectedReleaseBootstrapIdentity or not (
            hmac.compare_digest(identity.owner_id, self._identity.owner_id)
            and hmac.compare_digest(identity.session_id, self._identity.session_id)
        ):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_AUTH_FAILED")

    async def start(
        self,
        *,
        target: ConnectedReleaseBootstrapTarget,
        generation: int,
        identity: ConnectedReleaseBootstrapIdentity,
        connection_id: str | None = None,
    ) -> OAuthStartView:
        require_release_bootstrap_source_boundary()
        self.require_same_identity(identity)
        if type(target) is not ConnectedReleaseBootstrapTarget:
            _fail()
        request_id = bootstrap_request_id(
            ceremony_id=self._ceremony_id,
            target=target,
            generation=generation,
        )
        if connection_id is not None:
            connection_id = _uuid(connection_id)
        try:
            return await self._bootstrap._operator.start_once(
                OAuthStartCommand(
                    request_id=request_id,
                    owner_id=self._identity.owner_id,
                    session_binding_sha256=(
                        self._identity.session_binding_sha256
                    ),
                    provider=target.provider,
                    resource=target.resource,
                    account_kind=target.account_kind,
                    actions=target.actions,
                    redirect_uri=target.redirect_uri,
                    connection_id=connection_id,
                    requested_at=datetime.now(UTC),
                )
            )
        except Exception:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")

    async def read_start(
        self,
        *,
        target: ConnectedReleaseBootstrapTarget,
        generation: int,
        identity: ConnectedReleaseBootstrapIdentity,
    ) -> OAuthStartView | None:
        require_release_bootstrap_source_boundary()
        self.require_same_identity(identity)
        request_id = bootstrap_request_id(
            ceremony_id=self._ceremony_id,
            target=target,
            generation=generation,
        )
        try:
            result = await self._bootstrap._operator.read_start(
                owner_id=self._identity.owner_id,
                request_id=request_id,
            )
        except Exception:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")
        if result is not None and result.provider is not target.provider:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")
        return result

    async def complete(
        self,
        *,
        target: ConnectedReleaseBootstrapTarget,
        callback: ConnectedReleaseBootstrapCallback,
        identity: ConnectedReleaseBootstrapIdentity,
    ) -> None:
        require_release_bootstrap_source_boundary()
        self.require_same_identity(identity)
        if (
            type(target) is not ConnectedReleaseBootstrapTarget
            or type(callback) is not ConnectedReleaseBootstrapCallback
            or callback.provider is not target.provider
        ):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID")
        try:
            command = OAuthCallbackCommand.build(
                owner_id=self._identity.owner_id,
                session_id=self._identity.session_id,
                provider=target.provider,
                state=callback.secrets.state.value,
                code=callback.secrets.authorization_code.value,
                received_at=datetime.now(UTC),
            )
            result = await self._bootstrap._operator.complete_once(command)
            if (
                result.provider is not target.provider
                or result.resource is not target.resource
                or result.account_kind is not target.account_kind
            ):
                _fail("CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID")
        except ConnectedReleaseBootstrapError:
            raise
        except Exception:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")

    async def recover_descriptor(
        self,
        *,
        target: ConnectedReleaseBootstrapTarget,
        generation: int,
        identity: ConnectedReleaseBootstrapIdentity,
    ) -> ConnectedReleasePreviewConnectionConfiguration:
        """Recover terminal grant, completion-v3, and binding-v2 without callback secrets."""

        require_release_bootstrap_source_boundary()
        self.require_same_identity(identity)
        request_id = bootstrap_request_id(
            ceremony_id=self._ceremony_id,
            target=target,
            generation=generation,
        )
        try:
            reservation = await self._bootstrap._operator_store.read_start(
                owner_id=self._identity.owner_id,
                request_id=request_id,
            )
            if reservation is None:
                _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")
            command = reservation.command
            if (
                command.owner_id != self._identity.owner_id
                or command.session_binding_sha256
                != self._identity.session_binding_sha256
                or command.provider is not target.provider
                or command.resource is not target.resource
                or command.account_kind is not target.account_kind
                or command.actions != target.actions
            ):
                _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")
            lookup = OAuthBrokerFlowLookup(
                flow_id=reservation.flow_id,
                owner_id=command.owner_id,
                connection_id=reservation.connection_id,
                connection_incarnation_id=reservation.connection_incarnation_id,
                expected_base_revision=reservation.expected_base_revision,
                current_flow_nonce_sha256=(
                    reservation.current_flow_nonce_sha256
                ),
            )
            broker_record = await self._bootstrap._broker._store.read_flow(lookup)
            if broker_record is None:
                _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")
            raw_flow = await self._bootstrap._database.rpc(
                "connected_app_oauth_revalidate_flow_v2",
                {
                    "p_flow_id": reservation.flow_id,
                    "p_expected_flow_binding_sha256": (
                        broker_record.command.binding_sha256
                    ),
                },
                retry_transient=True,
            )
            flow = self._bootstrap._flows.decode_flow(raw_flow)
            if flow.state is OAuthFlowState.PENDING:
                _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")
            consumption = await recover_oauth_flow_consumption(
                repository=self._bootstrap._flows,
                flow=flow,
            )
            if consumption is None:
                _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")
            exchange = prepare_oauth_exchange(flow, consumption)
            terminal = await read_oauth_exchange_terminal(
                broker=self._bootstrap._broker,
                command=exchange,
            )
            if terminal is None:
                terminal = await self._bootstrap._operator.recover_exchange_once(
                    flow=flow,
                    consumption=consumption,
                )
            if isinstance(terminal, OAuthExchangeAmbiguous):
                _fail("CONNECTED_RELEASE_BOOTSTRAP_EXCHANGE_AMBIGUOUS")
            if not isinstance(terminal, OAuthBrokerGrant):
                _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")
            completion = await finalize_oauth_completion(
                flow,
                consumption,
                exchange,
                terminal,
                repository=self._bootstrap._completions,
            )
            completion_command = _completion_command(
                flow,
                consumption,
                exchange,
                terminal,
            )
            reread = await self._bootstrap._completions.read_completion(
                completion_command
            )
            binding = await self._bootstrap._accounts.get_binding(
                owner_id=self._identity.owner_id,
                connection_id=flow.connection_id,
            )
            return _descriptor_from_readback(
                target=target,
                flow=flow,
                completion=completion,
                reread=reread,
                binding=binding,
            )
        except ConnectedReleaseBootstrapError:
            raise
        except Exception:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")

    async def attest_dedicated_accounts(
        self,
        *,
        permit: ConnectedReleaseDedicatedAccountPermit,
        descriptor_matrix_sha256: str,
        identity: ConnectedReleaseBootstrapIdentity,
    ) -> str:
        """Persist the explicit action-time truth used by the final host seal."""

        require_release_bootstrap_source_boundary()
        self.require_same_identity(identity)
        if type(permit) is not ConnectedReleaseDedicatedAccountPermit:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID")
        matrix = _sha(descriptor_matrix_sha256)
        attestation = permit.consume(
            ceremony_id=self._ceremony_id,
            owner_id=self._identity.owner_id,
            descriptor_matrix_sha256=matrix,
        )
        payload = {
            "p_ceremony_id": self._ceremony_id,
            "p_owner_id": self._identity.owner_id,
            "p_session_id": self._identity.session_id,
            "p_session_binding_sha256": (
                self._identity.session_binding_sha256
            ),
            "p_descriptor_matrix_sha256": matrix,
            "p_dedicated_account_attestation_sha256": attestation,
        }
        try:
            value = await self._bootstrap._database.rpc(
                "connected_app_release_bootstrap_attest_dedicated_v1",
                payload,
                retry_transient=False,
            )
        except Exception:
            try:
                value = await self._bootstrap._database.rpc(
                    "connected_app_release_bootstrap_read_dedicated_v1",
                    {
                        "p_dedicated_account_attestation_sha256": (
                            attestation
                        )
                    },
                    retry_transient=False,
                )
            except Exception:
                _fail("CONNECTED_RELEASE_BOOTSTRAP_RECOVERY_REQUIRED")
        expected_keys = {
            "ceremony_id",
            "owner_id",
            "session_id",
            "descriptor_matrix_sha256",
            "dedicated_account_attestation_sha256",
            "confirmed_at",
        }
        if (
            not isinstance(value, dict)
            or set(value) != expected_keys
            or value["ceremony_id"] != self._ceremony_id
            or value["owner_id"] != self._identity.owner_id
            or value["session_id"] != self._identity.session_id
            or value["descriptor_matrix_sha256"] != matrix
            or value["dedicated_account_attestation_sha256"] != attestation
            or not isinstance(value["confirmed_at"], str)
            or not value["confirmed_at"]
            or len(value["confirmed_at"]) > 64
        ):
            _fail("CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID")
        try:
            confirmed_at = datetime.fromisoformat(
                value["confirmed_at"].replace("Z", "+00:00")
            )
        except ValueError:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID")
        if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
            _fail("CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID")
        return attestation

    def __repr__(self) -> str:
        return "ConnectedReleaseOAuthBootstrapSession(bindings='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("release OAuth bootstrap sessions cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("release OAuth bootstrap sessions cannot be serialized")


def _descriptor_from_readback(
    *,
    target: ConnectedReleaseBootstrapTarget,
    flow: object,
    completion: OAuthCompletion,
    reread: object,
    binding: ConnectedAccountBinding | None,
) -> ConnectedReleasePreviewConnectionConfiguration:
    if (
        type(target) is not ConnectedReleaseBootstrapTarget
        or not isinstance(completion, OAuthCompletion)
        or not isinstance(reread, OAuthCompletion)
        or reread != completion
        or not isinstance(binding, ConnectedAccountBinding)
    ):
        _fail("CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID")
    authorization: ConnectedAuthorizationSnapshot = completion.authorization
    account = binding.account
    if (
        binding.authorization != authorization
        or authorization.state is not ConnectionAuthorizationState.ACTIVE
        or authorization.provider is not target.provider
        or authorization.resource is not target.resource
        or authorization.account_kind is not target.account_kind
        or authorization.granted_actions != target.actions
        or account.external_account_id_hash != completion.external_account_id_hash
        or completion.credential.owner_id != authorization.owner_id
        or completion.credential.connection_id != authorization.connection_id
        or getattr(flow, "connection_incarnation_id", None)
        != completion.connection_incarnation_id
        or getattr(flow, "current_flow_nonce_sha256", None)
        != completion.current_flow_nonce_sha256
    ):
        _fail("CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID")
    return ConnectedReleasePreviewConnectionConfiguration(
        provider=target.provider,
        resource=target.resource,
        owner_id=authorization.owner_id,
        connection_id=authorization.connection_id,
        connection_incarnation_id=completion.connection_incarnation_id,
        oauth_completion_id=completion.consumption_id,
        oauth_completion_binding_sha256=(
            completion.completion_binding_sha256
        ),
        current_flow_nonce_sha256=completion.current_flow_nonce_sha256,
        credential_handle_sha256=_digest(completion.credential.handle_id),
        account_kind=target.account_kind,
        external_account_id_hash=completion.external_account_id_hash,
        authorization_snapshot_sha256=authorization.snapshot_sha256,
        granted_actions=authorization.granted_actions,
        granted_scopes=authorization.granted_scopes,
    )


def validate_complete_descriptor_matrix(
    descriptors: Mapping[
        ConnectorProvider,
        Mapping[
            ConnectorAccountKind,
            Mapping[
                ConnectorResource,
                ConnectedReleasePreviewConnectionConfiguration,
            ],
        ],
    ],
    *,
    registrations: Mapping[ConnectorProvider, ProviderOAuthRegistration],
    composition_manifest_sha256: str,
    dedicated_account_attestation_sha256: str,
) -> ConnectedHostConfiguration:
    """Use the host schema itself as the final six-binding release authority."""

    try:
        return ConnectedHostConfiguration(
            registrations=registrations,
            composition_manifest_sha256=_sha(composition_manifest_sha256),
            release_preview_connections=descriptors,
            release_preview_dedicated_account_attestation_sha256=_sha(
                dedicated_account_attestation_sha256
            ),
        )
    except Exception:
        _fail("CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID")


def release_preview_descriptor_matrix_sha256(
    descriptors: Mapping[
        ConnectorProvider,
        Mapping[
            ConnectorAccountKind,
            Mapping[
                ConnectorResource,
                ConnectedReleasePreviewConnectionConfiguration,
            ],
        ],
    ],
    *,
    registrations: Mapping[ConnectorProvider, ProviderOAuthRegistration],
    composition_manifest_sha256: str,
) -> str:
    """Return the host schema's canonical six-descriptor confirmation digest."""

    try:
        probe = ConnectedHostConfiguration(
            registrations=registrations,
            composition_manifest_sha256=_sha(composition_manifest_sha256),
            release_preview_connections=descriptors,
            release_preview_dedicated_account_attestation_sha256="0" * 64,
        )
        value = probe.release_preview_descriptor_matrix_sha256
        return _sha(value)
    except Exception:
        _fail("CONNECTED_RELEASE_BOOTSTRAP_DESCRIPTOR_INVALID")


@dataclass(frozen=True, slots=True)
class ConnectedReleaseBootstrapSimulatorAuthority:
    """Test-only authority marker; production graph builders reject this type."""

    name: str = "connected-release-bootstrap-simulator-v1"

    def __post_init__(self) -> None:
        if self.name != "connected-release-bootstrap-simulator-v1":
            _fail()


__all__ = [
    "CONNECTED_RELEASE_BOOTSTRAP_TARGETS",
    "ConnectedReleaseBootstrapCallback",
    "ConnectedReleaseBootstrapError",
    "ConnectedReleaseBootstrapIdentity",
    "ConnectedReleaseBootstrapPermit",
    "ConnectedReleaseDedicatedAccountPermit",
    "ConnectedReleaseBootstrapSimulatorAuthority",
    "ConnectedReleaseBootstrapTarget",
    "ConnectedReleaseOAuthBootstrap",
    "ConnectedReleaseOAuthBootstrapSession",
    "bootstrap_request_id",
    "parse_intercepted_callback",
    "release_preview_descriptor_matrix_sha256",
    "require_release_bootstrap_source_boundary",
    "target_for_key",
    "validate_complete_descriptor_matrix",
]
