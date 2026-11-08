"""Encrypted production host configuration for the connected operator.

OAuth client secrets are long-lived deployment credentials.  They are never
accepted as individual environment variables: the deployment may carry only
this bounded ciphertext, which is opened after a request-scoped KMS root has
been unwrapped and domain-separated for host configuration.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import re
import secrets
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .connected_app_contracts import ConnectorAccountKind
from .connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from .connected_app_provider_oauth import (
    ProviderOAuthClientSecret,
    ProviderOAuthRegistration,
)


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_B64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_MAX_ENVELOPE_CHARS = 32_768
_MAX_PLAINTEXT_BYTES = 16_384
_VERSION = "askcrump-connected-host-v1"
_AAD_PREFIX = b"askcrump.connected-host-configuration/v1\0"
_SCOPE = re.compile(r"^[\x21-\x7e]{1,512}$")


class ConnectedHostConfigurationError(RuntimeError):
    """Content-free configuration failure safe for request quarantine."""

    _CODES = frozenset(
        {
            "CONNECTED_HOST_CONFIGURATION_INVALID",
            "CONNECTED_HOST_CONFIGURATION_DECRYPT_FAILED",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = (
            code
            if code in self._CODES
            else "CONNECTED_HOST_CONFIGURATION_INVALID"
        )
        super().__init__(self.code)


def _json_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _decode_b64url(value: str, *, exact: int | None = None) -> bytes:
    if not isinstance(value, str) or not value or not _B64URL.fullmatch(value):
        raise ConnectedHostConfigurationError(
            "CONNECTED_HOST_CONFIGURATION_INVALID"
        )
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        raise ConnectedHostConfigurationError(
            "CONNECTED_HOST_CONFIGURATION_INVALID"
        ) from None
    if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value:
        raise ConnectedHostConfigurationError(
            "CONNECTED_HOST_CONFIGURATION_INVALID"
        )
    if exact is not None and len(decoded) != exact:
        raise ConnectedHostConfigurationError(
            "CONNECTED_HOST_CONFIGURATION_INVALID"
        )
    return decoded


def _exact_provider_client_id(provider: ConnectorProvider, value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedHostConfigurationError(
            "CONNECTED_HOST_CONFIGURATION_INVALID"
        )
    if provider is ConnectorProvider.GOOGLE:
        if not value.endswith(".apps.googleusercontent.com"):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        return value
    if provider is ConnectorProvider.MICROSOFT:
        try:
            canonical = str(UUID(value))
        except (ValueError, TypeError, AttributeError):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            ) from None
        if value != canonical:
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        return value
    raise ConnectedHostConfigurationError("CONNECTED_HOST_CONFIGURATION_INVALID")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedHostConfigurationKey:
    """One manifest-bound AES key derived solely for host configuration."""

    key_id: str
    secret: bytes = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.key_id, str)
            or not _KEY_ID.fullmatch(self.key_id)
            or type(self.secret) is not bytes
            or len(self.secret) != 32
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )

    def __repr__(self) -> str:
        return (
            "ConnectedHostConfigurationKey("
            f"key_id={self.key_id!r}, secret='<redacted>')"
        )

    def __getstate__(self) -> object:
        raise TypeError("connected host-configuration keys cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected host-configuration keys cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedReleasePreviewConnectionConfiguration:
    """Sealed descriptor for one dedicated, non-customer preview connection."""

    provider: ConnectorProvider
    resource: ConnectorResource
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    oauth_completion_id: str
    oauth_completion_binding_sha256: str
    current_flow_nonce_sha256: str
    credential_handle_sha256: str
    account_kind: ConnectorAccountKind
    external_account_id_hash: str
    authorization_snapshot_sha256: str
    granted_actions: frozenset[ConnectorActionKind]
    granted_scopes: frozenset[str]
    purpose: str = "release_preview_dedicated_account_v1"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider, ConnectorProvider)
            or not isinstance(self.resource, ConnectorResource)
            or not isinstance(self.account_kind, ConnectorAccountKind)
            or not isinstance(self.granted_actions, frozenset)
            or not self.granted_actions
            or any(
                not isinstance(action, ConnectorActionKind)
                for action in self.granted_actions
            )
            or not isinstance(self.granted_scopes, frozenset)
            or not self.granted_scopes
            or any(
                not isinstance(scope, str) or _SCOPE.fullmatch(scope) is None
                for scope in self.granted_scopes
            )
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        if self.purpose != "release_preview_dedicated_account_v1":
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        for name in (
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
            "oauth_completion_id",
        ):
            value = getattr(self, name)
            try:
                canonical = str(UUID(value))
            except (TypeError, ValueError, AttributeError):
                raise ConnectedHostConfigurationError(
                    "CONNECTED_HOST_CONFIGURATION_INVALID"
                ) from None
            if canonical != value:
                raise ConnectedHostConfigurationError(
                    "CONNECTED_HOST_CONFIGURATION_INVALID"
                )
        for name in (
            "credential_handle_sha256",
            "external_account_id_hash",
            "authorization_snapshot_sha256",
            "oauth_completion_binding_sha256",
            "current_flow_nonce_sha256",
        ):
            if _SHA256.fullmatch(str(getattr(self, name) or "")) is None:
                raise ConnectedHostConfigurationError(
                    "CONNECTED_HOST_CONFIGURATION_INVALID"
                )

    def __repr__(self) -> str:
        return (
            "ConnectedReleasePreviewConnectionConfiguration("
            f"provider={self.provider.value!r}, resource={self.resource.value!r}, "
            "connection='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedEncryptedHostConfiguration:
    """A compact AES-GCM envelope safe to store as deployment ciphertext."""

    value: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not 1 <= len(self.value) <= _MAX_ENVELOPE_CHARS
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        parts = self.value.split(":")
        if (
            len(parts) != 4
            or parts[0] != "v1"
            or not _KEY_ID.fullmatch(parts[1])
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        _decode_b64url(parts[2], exact=12)
        ciphertext = _decode_b64url(parts[3])
        if not 17 <= len(ciphertext) <= _MAX_PLAINTEXT_BYTES + 16:
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )

    def __repr__(self) -> str:
        return "ConnectedEncryptedHostConfiguration(ciphertext='<redacted>')"

    def __str__(self) -> str:
        return "<connected-host-configuration:redacted>"

    def __getstate__(self) -> object:
        raise TypeError("encrypted connected host configuration cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("encrypted connected host configuration cannot be serialized")

    def open(
        self,
        *,
        key: ConnectedHostConfigurationKey,
        composition_manifest_sha256: str,
    ) -> ConnectedHostConfiguration:
        if (
            type(key) is not ConnectedHostConfigurationKey
            or not isinstance(composition_manifest_sha256, str)
            or not _SHA256.fullmatch(composition_manifest_sha256)
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        version, key_id, nonce_value, ciphertext_value = self.value.split(":")
        del version
        if key_id != key.key_id:
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_DECRYPT_FAILED"
            )
        nonce = _decode_b64url(nonce_value, exact=12)
        ciphertext = _decode_b64url(ciphertext_value)
        aad = (
            _AAD_PREFIX
            + bytes.fromhex(composition_manifest_sha256)
            + b"\0"
            + key.key_id.encode("ascii")
        )
        try:
            plaintext = AESGCM(key.secret).decrypt(nonce, ciphertext, aad)
        except (InvalidTag, ValueError, TypeError):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_DECRYPT_FAILED"
            ) from None
        if not plaintext or len(plaintext) > _MAX_PLAINTEXT_BYTES:
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_DECRYPT_FAILED"
            )
        try:
            parsed = json.loads(
                plaintext.decode("utf-8"),
                object_pairs_hook=_json_no_duplicates,
                parse_constant=lambda _item: (_ for _ in ()).throw(ValueError()),
            )
        except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_DECRYPT_FAILED"
            ) from None
        return ConnectedHostConfiguration.from_json(
            parsed,
            expected_manifest_sha256=composition_manifest_sha256,
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedHostConfiguration:
    """The only accepted plaintext shape after authenticated decryption."""

    registrations: Mapping[ConnectorProvider, ProviderOAuthRegistration]
    composition_manifest_sha256: str
    release_preview_connections: Mapping[
        ConnectorProvider,
        Mapping[
            ConnectorAccountKind,
            Mapping[
                ConnectorResource,
                ConnectedReleasePreviewConnectionConfiguration,
            ],
        ],
    ] = field(default_factory=dict, repr=False, compare=False)
    release_preview_dedicated_account_attestation_sha256: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.composition_manifest_sha256):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        if not isinstance(self.registrations, Mapping):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        try:
            registrations = {
                provider: self.registrations[provider]
                for provider in ConnectorProvider
            }
        except (KeyError, TypeError):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            ) from None
        if set(self.registrations) != set(ConnectorProvider) or any(
            type(registration) is not ProviderOAuthRegistration
            or registration.provider is not provider
            for provider, registration in registrations.items()
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        if len({item.client_id_sha256 for item in registrations.values()}) != 2:
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        object.__setattr__(
            self,
            "registrations",
            MappingProxyType(registrations),
        )
        if not isinstance(self.release_preview_connections, Mapping):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        if not self.release_preview_connections:
            if self.release_preview_dedicated_account_attestation_sha256 is not None:
                raise ConnectedHostConfigurationError(
                    "CONNECTED_HOST_CONFIGURATION_INVALID"
                )
            object.__setattr__(
                self,
                "release_preview_connections",
                MappingProxyType({}),
            )
            return
        if (
            not isinstance(
                self.release_preview_dedicated_account_attestation_sha256,
                str,
            )
            or _SHA256.fullmatch(
                self.release_preview_dedicated_account_attestation_sha256
            )
            is None
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        try:
            preview = {
                provider: {
                    account_kind: {
                        resource: self.release_preview_connections[provider][
                            account_kind
                        ][resource]
                        for resource in (
                            ConnectorResource.MAIL,
                            ConnectorResource.CALENDAR,
                        )
                    }
                    for account_kind in self.release_preview_connections[provider]
                }
                for provider in ConnectorProvider
            }
        except (KeyError, TypeError):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            ) from None
        if set(self.release_preview_connections) != set(ConnectorProvider):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        if len(preview[ConnectorProvider.GOOGLE]) != 1 or set(
            preview[ConnectorProvider.MICROSOFT]
        ) != set(ConnectorAccountKind):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        owners: set[str] = set()
        for provider, account_groups in preview.items():
            for account_kind, connections in account_groups.items():
                if (
                    not isinstance(account_kind, ConnectorAccountKind)
                    or set(connections)
                    != {
                        ConnectorResource.MAIL,
                        ConnectorResource.CALENDAR,
                    }
                ):
                    raise ConnectedHostConfigurationError(
                        "CONNECTED_HOST_CONFIGURATION_INVALID"
                    )
                for resource, connection in connections.items():
                    if (
                        type(connection)
                        is not ConnectedReleasePreviewConnectionConfiguration
                        or connection.provider is not provider
                        or connection.resource is not resource
                        or connection.account_kind is not account_kind
                    ):
                        raise ConnectedHostConfigurationError(
                            "CONNECTED_HOST_CONFIGURATION_INVALID"
                        )
                mail = connections[ConnectorResource.MAIL]
                calendar = connections[ConnectorResource.CALENDAR]
                if (
                    mail.owner_id != calendar.owner_id
                    or mail.external_account_id_hash
                    != calendar.external_account_id_hash
                ):
                    raise ConnectedHostConfigurationError(
                        "CONNECTED_HOST_CONFIGURATION_INVALID"
                    )
                owners.add(mail.owner_id)
        if len(owners) != 1:
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        microsoft_hashes = {
            connections[ConnectorResource.MAIL].external_account_id_hash
            for connections in preview[ConnectorProvider.MICROSOFT].values()
        }
        if len(microsoft_hashes) != 2:
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        object.__setattr__(
            self,
            "release_preview_connections",
            MappingProxyType(
                {
                    provider: MappingProxyType(
                        {
                            account_kind: MappingProxyType(connections)
                            for account_kind, connections in account_groups.items()
                        }
                    )
                    for provider, account_groups in preview.items()
                }
            ),
        )

    @classmethod
    def from_json(
        cls,
        value: object,
        *,
        expected_manifest_sha256: str,
    ) -> ConnectedHostConfiguration:
        if not isinstance(value, dict) or set(value) not in (
            {
                "version",
                "composition_manifest_sha256",
                "google",
                "microsoft",
            },
            {
                "version",
                "composition_manifest_sha256",
                "google",
                "microsoft",
                "release_preview",
                "release_preview_dedicated_account_attestation_sha256",
            },
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        if (
            value.get("version") != _VERSION
            or value.get("composition_manifest_sha256")
            != expected_manifest_sha256
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        registrations: dict[ConnectorProvider, ProviderOAuthRegistration] = {}
        client_secrets: set[str] = set()
        for provider in ConnectorProvider:
            item = value.get(provider.value)
            if not isinstance(item, dict) or set(item) != {
                "client_id",
                "client_secret",
            }:
                raise ConnectedHostConfigurationError(
                    "CONNECTED_HOST_CONFIGURATION_INVALID"
                )
            try:
                client_id = _exact_provider_client_id(provider, item["client_id"])
                client_secret = item["client_secret"]
                if not isinstance(client_secret, str) or client_secret in client_secrets:
                    raise ConnectedHostConfigurationError(
                        "CONNECTED_HOST_CONFIGURATION_INVALID"
                    )
                client_secrets.add(client_secret)
                registrations[provider] = ProviderOAuthRegistration(
                    provider=provider,
                    client_id=client_id,
                    client_secret=ProviderOAuthClientSecret(client_secret),
                )
            except ConnectedHostConfigurationError:
                raise
            except (KeyError, TypeError, ValueError):
                raise ConnectedHostConfigurationError(
                    "CONNECTED_HOST_CONFIGURATION_INVALID"
                ) from None
        preview_connections: dict[
            ConnectorProvider,
            dict[
                ConnectorAccountKind,
                dict[
                    ConnectorResource,
                    ConnectedReleasePreviewConnectionConfiguration,
                ],
            ],
        ] = {}
        preview_attestation = value.get(
            "release_preview_dedicated_account_attestation_sha256"
        )
        preview_value = value.get("release_preview")
        if preview_value is not None:
            if not isinstance(preview_value, dict) or set(preview_value) != {
                provider.value for provider in ConnectorProvider
            }:
                raise ConnectedHostConfigurationError(
                    "CONNECTED_HOST_CONFIGURATION_INVALID"
                )
            for provider in ConnectorProvider:
                provider_value = preview_value.get(provider.value)
                if not isinstance(provider_value, dict):
                    raise ConnectedHostConfigurationError(
                        "CONNECTED_HOST_CONFIGURATION_INVALID"
                    )
                preview_connections[provider] = {}
                expected_account_kinds = (
                    set(ConnectorAccountKind)
                    if provider is ConnectorProvider.MICROSOFT
                    else None
                )
                try:
                    account_kinds = {
                        ConnectorAccountKind(key) for key in provider_value
                    }
                except (TypeError, ValueError):
                    raise ConnectedHostConfigurationError(
                        "CONNECTED_HOST_CONFIGURATION_INVALID"
                    ) from None
                if (
                    expected_account_kinds is not None
                    and account_kinds != expected_account_kinds
                ) or (
                    provider is ConnectorProvider.GOOGLE
                    and len(account_kinds) != 1
                ):
                    raise ConnectedHostConfigurationError(
                        "CONNECTED_HOST_CONFIGURATION_INVALID"
                    )
                for account_kind in account_kinds:
                    account_value = provider_value.get(account_kind.value)
                    if not isinstance(account_value, dict) or set(account_value) != {
                        ConnectorResource.MAIL.value,
                        ConnectorResource.CALENDAR.value,
                    }:
                        raise ConnectedHostConfigurationError(
                            "CONNECTED_HOST_CONFIGURATION_INVALID"
                        )
                    preview_connections[provider][account_kind] = {}
                    for resource in (
                        ConnectorResource.MAIL,
                        ConnectorResource.CALENDAR,
                    ):
                        item = account_value.get(resource.value)
                        expected = {
                            "owner_id",
                            "connection_id",
                            "connection_incarnation_id",
                            "oauth_completion_id",
                            "oauth_completion_binding_sha256",
                            "current_flow_nonce_sha256",
                            "credential_handle_sha256",
                            "account_kind",
                            "external_account_id_hash",
                            "authorization_snapshot_sha256",
                            "granted_actions",
                            "granted_scopes",
                            "purpose",
                        }
                        if not isinstance(item, dict) or set(item) != expected:
                            raise ConnectedHostConfigurationError(
                                "CONNECTED_HOST_CONFIGURATION_INVALID"
                            )
                        try:
                            raw_actions = item["granted_actions"]
                            raw_scopes = item["granted_scopes"]
                            if (
                                type(raw_actions) is not list
                                or raw_actions != sorted(set(raw_actions))
                                or type(raw_scopes) is not list
                                or raw_scopes != sorted(set(raw_scopes))
                                or item["account_kind"] != account_kind.value
                            ):
                                raise ValueError
                            preview_connections[provider][account_kind][resource] = (
                                ConnectedReleasePreviewConnectionConfiguration(
                                    provider=provider,
                                    resource=resource,
                                    owner_id=item["owner_id"],
                                    connection_id=item["connection_id"],
                                    connection_incarnation_id=item[
                                        "connection_incarnation_id"
                                    ],
                                    oauth_completion_id=item["oauth_completion_id"],
                                    oauth_completion_binding_sha256=item[
                                        "oauth_completion_binding_sha256"
                                    ],
                                    current_flow_nonce_sha256=item[
                                        "current_flow_nonce_sha256"
                                    ],
                                    credential_handle_sha256=item[
                                        "credential_handle_sha256"
                                    ],
                                    account_kind=account_kind,
                                    external_account_id_hash=item[
                                        "external_account_id_hash"
                                    ],
                                    authorization_snapshot_sha256=item[
                                        "authorization_snapshot_sha256"
                                    ],
                                    granted_actions=frozenset(
                                        ConnectorActionKind(action)
                                        for action in raw_actions
                                    ),
                                    granted_scopes=frozenset(raw_scopes),
                                    purpose=item["purpose"],
                                )
                            )
                        except (KeyError, TypeError, ValueError):
                            raise ConnectedHostConfigurationError(
                                "CONNECTED_HOST_CONFIGURATION_INVALID"
                            ) from None
        return cls(
            registrations=registrations,
            composition_manifest_sha256=expected_manifest_sha256,
            release_preview_connections=preview_connections,
            release_preview_dedicated_account_attestation_sha256=(
                preview_attestation
            ),
        )

    def __repr__(self) -> str:
        return "ConnectedHostConfiguration(registrations='<redacted>')"

    @property
    def release_preview_descriptor_matrix_sha256(self) -> str | None:
        """Hash the exact six sealed bindings without exposing their IDs."""

        if not self.release_preview_connections:
            return None
        descriptors: list[dict[str, str]] = []
        external_accounts: set[str] = set()
        for provider in sorted(
            self.release_preview_connections,
            key=lambda item: item.value,
        ):
            for account_kind in sorted(
                self.release_preview_connections[provider],
                key=lambda item: item.value,
            ):
                for resource in (
                    ConnectorResource.MAIL,
                    ConnectorResource.CALENDAR,
                ):
                    descriptor = self.release_preview_connections[provider][
                        account_kind
                    ][resource]
                    canonical = {
                        "version": "askcrump-release-preview-descriptor-v1",
                        "provider": provider.value,
                        "account_kind": account_kind.value,
                        "resource": resource.value,
                        "owner_id": descriptor.owner_id,
                        "connection_id": descriptor.connection_id,
                        "connection_incarnation_id": (
                            descriptor.connection_incarnation_id
                        ),
                        "oauth_completion_id": descriptor.oauth_completion_id,
                        "oauth_completion_binding_sha256": (
                            descriptor.oauth_completion_binding_sha256
                        ),
                        "current_flow_nonce_sha256": (
                            descriptor.current_flow_nonce_sha256
                        ),
                        "credential_handle_sha256": (
                            descriptor.credential_handle_sha256
                        ),
                        "external_account_id_hash": (
                            descriptor.external_account_id_hash
                        ),
                        "authorization_snapshot_sha256": (
                            descriptor.authorization_snapshot_sha256
                        ),
                        "granted_actions": sorted(
                            action.value for action in descriptor.granted_actions
                        ),
                        "granted_scopes": sorted(descriptor.granted_scopes),
                        "purpose": descriptor.purpose,
                    }
                    descriptor_sha256 = hashlib.sha256(
                        json.dumps(
                            canonical,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("ascii")
                    ).hexdigest()
                    descriptors.append(
                        {
                            "provider": provider.value,
                            "account_kind": account_kind.value,
                            "resource": resource.value,
                            "descriptor_sha256": descriptor_sha256,
                            "external_account_id_hash": (
                                descriptor.external_account_id_hash
                            ),
                        }
                    )
                    external_accounts.add(descriptor.external_account_id_hash)
        if len(descriptors) != 6 or len(external_accounts) != 3:
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        return hashlib.sha256(
            json.dumps(
                {
                    "version": "askcrump-release-preview-descriptor-matrix-v1",
                    "descriptors": descriptors,
                    "external_account_id_hashes": sorted(external_accounts),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()

    def seal(
        self,
        *,
        key: ConnectedHostConfigurationKey,
    ) -> ConnectedEncryptedHostConfiguration:
        """Seal registrations and exact preview bindings without exposing JSON."""

        if (
            type(key) is not ConnectedHostConfigurationKey
            or key.key_id.split(".host_configuration.", 1)[0] == key.key_id
        ):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        value: dict[str, object] = {
            "version": _VERSION,
            "composition_manifest_sha256": self.composition_manifest_sha256,
        }
        for provider, registration in self.registrations.items():
            value[provider.value] = {
                "client_id": registration.client_id,
                "client_secret": registration.client_secret._reveal(),
            }
        if self.release_preview_connections:
            value["release_preview_dedicated_account_attestation_sha256"] = (
                self.release_preview_dedicated_account_attestation_sha256
            )
            value["release_preview"] = {
                provider.value: {
                    account_kind.value: {
                        resource.value: {
                            "owner_id": descriptor.owner_id,
                            "connection_id": descriptor.connection_id,
                            "connection_incarnation_id": (
                                descriptor.connection_incarnation_id
                            ),
                            "oauth_completion_id": descriptor.oauth_completion_id,
                            "oauth_completion_binding_sha256": (
                                descriptor.oauth_completion_binding_sha256
                            ),
                            "current_flow_nonce_sha256": (
                                descriptor.current_flow_nonce_sha256
                            ),
                            "credential_handle_sha256": (
                                descriptor.credential_handle_sha256
                            ),
                            "account_kind": descriptor.account_kind.value,
                            "external_account_id_hash": (
                                descriptor.external_account_id_hash
                            ),
                            "authorization_snapshot_sha256": (
                                descriptor.authorization_snapshot_sha256
                            ),
                            "granted_actions": sorted(
                                action.value for action in descriptor.granted_actions
                            ),
                            "granted_scopes": sorted(descriptor.granted_scopes),
                            "purpose": descriptor.purpose,
                        }
                        for resource, descriptor in connections.items()
                    }
                    for account_kind, connections in account_groups.items()
                }
                for provider, account_groups in self.release_preview_connections.items()
            }
        try:
            plaintext = json.dumps(
                value,
                sort_keys=True,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("ascii")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            ) from None
        if not plaintext or len(plaintext) > _MAX_PLAINTEXT_BYTES:
            raise ConnectedHostConfigurationError(
                "CONNECTED_HOST_CONFIGURATION_INVALID"
            )
        nonce = secrets.token_bytes(12)
        aad = (
            _AAD_PREFIX
            + bytes.fromhex(self.composition_manifest_sha256)
            + b"\0"
            + key.key_id.encode("ascii")
        )
        ciphertext = AESGCM(key.secret).encrypt(nonce, plaintext, aad)
        return ConnectedEncryptedHostConfiguration(
            ":".join(
                (
                    "v1",
                    key.key_id,
                    base64.urlsafe_b64encode(nonce)
                    .decode("ascii")
                    .rstrip("="),
                    base64.urlsafe_b64encode(ciphertext)
                    .decode("ascii")
                    .rstrip("="),
                )
            )
        )

    def __getstate__(self) -> object:
        raise TypeError("connected host configuration cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected host configuration cannot be serialized")


__all__ = [
    "ConnectedEncryptedHostConfiguration",
    "ConnectedHostConfiguration",
    "ConnectedHostConfigurationError",
    "ConnectedHostConfigurationKey",
    "ConnectedReleasePreviewConnectionConfiguration",
]
