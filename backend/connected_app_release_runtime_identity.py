"""Platform-authored identity for the one-shot connected release ceremony.

The Vercel OIDC assertion is first accepted by the source-pinned Google WIF
provider during KMS unwrap.  Only after that exchange succeeds does this
boundary inspect the same signed assertion and compare its owner/project/
environment claims with Vercel's production system variables and source pins.
Deployment ID and Git SHA therefore never come from release-script arguments.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
import re

from . import config
from .connected_app_key_derivation import (
    ConnectedKeyCustodyKind,
    ConnectedRootKeyMaterial,
)
from .connected_app_kms import ConnectedVercelOIDCAssertion


_DEPLOYMENT = re.compile(r"^dpl_[A-Za-z0-9]{8,}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_VERCEL_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_MAX_ASSERTION_BYTES = 12_288


class ConnectedReleaseRuntimeIdentityError(RuntimeError):
    def __init__(self) -> None:
        self.code = "CONNECTED_RELEASE_RUNTIME_IDENTITY_FAILED"
        super().__init__(self.code)


def _json_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _claim_text(claims: dict[str, object], name: str) -> str:
    value = claims.get(name)
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or value != value.strip()
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
    ):
        raise ConnectedReleaseRuntimeIdentityError()
    return value


def _assertion_claims(assertion: ConnectedVercelOIDCAssertion) -> dict[str, object]:
    token = assertion.reveal_for_exchange()
    if len(token.encode("utf-8")) > _MAX_ASSERTION_BYTES:
        raise ConnectedReleaseRuntimeIdentityError()
    parts = token.split(".")
    if len(parts) != 3:
        raise ConnectedReleaseRuntimeIdentityError()
    try:
        payload = parts[1]
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        claims = json.loads(
            decoded.decode("utf-8"),
            object_pairs_hook=_json_no_duplicates,
            parse_constant=lambda _item: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
        raise ConnectedReleaseRuntimeIdentityError() from None
    if not isinstance(claims, dict):
        raise ConnectedReleaseRuntimeIdentityError()
    return claims


def _system_value(name: str) -> str:
    value = os.environ.get(name)
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or value != value.strip()
        or "\x00" in value
    ):
        raise ConnectedReleaseRuntimeIdentityError()
    return value


@dataclass(frozen=True, slots=True)
class ConnectedVercelProductionIdentity:
    deployment_id: str
    commit_sha: str
    project_id: str
    team_id: str
    environment: str

    def __post_init__(self) -> None:
        if (
            _DEPLOYMENT.fullmatch(self.deployment_id) is None
            or _COMMIT.fullmatch(self.commit_sha) is None
            or _VERCEL_ID.fullmatch(self.project_id) is None
            or _VERCEL_ID.fullmatch(self.team_id) is None
            or self.environment != "production"
        ):
            raise ConnectedReleaseRuntimeIdentityError()


class ConnectedVercelProductionRuntimeIdentity:
    """Read only platform-owned process identity; no injectable environment."""

    __slots__ = ()

    def attest(
        self,
        *,
        assertion: ConnectedVercelOIDCAssertion,
        kms_root: ConnectedRootKeyMaterial,
    ) -> ConnectedVercelProductionIdentity:
        if (
            type(self) is not ConnectedVercelProductionRuntimeIdentity
            or type(assertion) is not ConnectedVercelOIDCAssertion
            or type(kms_root) is not ConnectedRootKeyMaterial
            or kms_root.custody is not ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS
            or os.environ.get("VERCEL") != "1"
        ):
            raise ConnectedReleaseRuntimeIdentityError()
        deployment_id = _system_value("VERCEL_DEPLOYMENT_ID")
        commit_sha = _system_value("VERCEL_GIT_COMMIT_SHA")
        project_id = _system_value("VERCEL_PROJECT_ID")
        environment = _system_value("VERCEL_ENV")
        claims = _assertion_claims(assertion)
        team_id = _claim_text(claims, "owner_id")
        if (
            project_id != config.CONNECTED_APPS_VERCEL_PROJECT_ID
            or team_id != config.CONNECTED_APPS_VERCEL_TEAM_ID
            or environment != config.CONNECTED_APPS_VERCEL_ENVIRONMENT
            or environment != "production"
            or _claim_text(claims, "project_id") != project_id
            or _claim_text(claims, "environment") != environment
        ):
            raise ConnectedReleaseRuntimeIdentityError()
        return ConnectedVercelProductionIdentity(
            deployment_id=deployment_id,
            commit_sha=commit_sha,
            project_id=project_id,
            team_id=team_id,
            environment=environment,
        )

    def __repr__(self) -> str:
        return "ConnectedVercelProductionRuntimeIdentity(source='vercel')"


__all__ = [
    "ConnectedReleaseRuntimeIdentityError",
    "ConnectedVercelProductionIdentity",
    "ConnectedVercelProductionRuntimeIdentity",
]
