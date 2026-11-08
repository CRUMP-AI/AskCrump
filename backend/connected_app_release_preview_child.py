"""Short-lived child entry point for the one-shot production release preview.

The Vercel request assertion arrives only over a private stdin pipe.  It is
never accepted from argv or the process environment.  The child prints one
bounded, content-free JSON result and must then exit, which is the destruction
boundary for immutable Python root/token bytes.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import config  # noqa: E402
from backend.connected_app_host_configuration import (  # noqa: E402
    ConnectedEncryptedHostConfiguration,
)
from backend.connected_app_kms import (  # noqa: E402
    ConnectedGoogleKMSConfiguration,
    ConnectedGoogleKMSRootLoader,
    ConnectedVercelOIDCAssertion,
)
from backend.connected_app_release_database import (  # noqa: E402
    ConnectedReleasePreviewProductionDatabase,
)
from backend.connected_app_release_preview import (  # noqa: E402
    ConnectedAIGatewayReleaseProbe,
    ConnectedReleasePreviewHarness,
    ConnectedReleasePreviewPermit,
)
from backend.connected_app_release_runtime_identity import (  # noqa: E402
    ConnectedVercelProductionRuntimeIdentity,
)
from backend.connected_app_request_ai_gateway import (  # noqa: E402
    ConnectedRequestScopedAIGatewayFactory,
)


_MAX_STDIN = 20_000
_INPUT_KEYS = {
    "version",
    "request_oidc_assertion",
    "invocation_id",
    "issued_at",
    "expires_at",
    "confirmation",
    "recovery",
}


class ConnectedReleasePreviewChildError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("CONNECTED_RELEASE_PREVIEW_CHILD_FAILED")
        self.code = "CONNECTED_RELEASE_PREVIEW_CHILD_FAILED"


def _required(name: str, *, maximum: int = 32_768) -> str:
    value = os.environ.get(name)
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or value != value.strip()
        or "\x00" in value
    ):
        raise ConnectedReleasePreviewChildError()
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise ConnectedReleasePreviewChildError()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedReleasePreviewChildError() from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedReleasePreviewChildError()
    return parsed.astimezone(UTC)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _read_input() -> dict[str, object]:
    raw = sys.stdin.buffer.read(_MAX_STDIN + 1)
    if not raw or len(raw) > _MAX_STDIN:
        raise ConnectedReleasePreviewChildError()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _item: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
        raise ConnectedReleasePreviewChildError() from None
    if type(value) is not dict or set(value) != _INPUT_KEYS:
        raise ConnectedReleasePreviewChildError()
    return value


async def _run(value: dict[str, object]) -> dict[str, object]:
    if (
        config.connected_apps_release_candidate_source_released() is not True
        or value.get("version") != "askcrump-release-preview-child-v1"
    ):
        raise ConnectedReleasePreviewChildError()
    assertion = ConnectedVercelOIDCAssertion(value["request_oidc_assertion"])
    issued_at = _timestamp(value["issued_at"])
    expires_at = _timestamp(value["expires_at"])
    permit = ConnectedReleasePreviewPermit(
        invocation_id=value["invocation_id"],
        issued_at=issued_at,
        expires_at=expires_at,
        confirmation=value["confirmation"],
        recovery=value["recovery"],
    )
    expected_manifest = config.CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256
    encrypted_root_b64 = _required("CRUMP_CONNECTED_KMS_ENCRYPTED_ROOT_B64")
    host_ciphertext = _required(
        "CRUMP_CONNECTED_HOST_CONFIGURATION_CIPHERTEXT"
    )
    deployment_id = _required("VERCEL_DEPLOYMENT_ID", maximum=256)
    commit_sha = _required("VERCEL_GIT_COMMIT_SHA", maximum=64)
    database = ConnectedReleasePreviewProductionDatabase()
    harness = ConnectedReleasePreviewHarness(
        root_loader=ConnectedGoogleKMSRootLoader(
            ConnectedGoogleKMSConfiguration(
                project_number=config.CONNECTED_APPS_KMS_PROJECT_NUMBER,
                workload_identity_pool_id=(
                    config.CONNECTED_APPS_KMS_WIF_POOL_ID
                ),
                workload_identity_provider_id=(
                    config.CONNECTED_APPS_KMS_WIF_PROVIDER_ID
                ),
                service_account_email=(
                    config.CONNECTED_APPS_KMS_SERVICE_ACCOUNT_EMAIL
                ),
                crypto_key_resource=(
                    config.CONNECTED_APPS_KMS_CRYPTO_KEY_RESOURCE
                ),
                encrypted_root_b64=encrypted_root_b64,
                root_key_id=config.CONNECTED_APPS_KMS_ROOT_KEY_ID,
                composition_manifest_sha256=expected_manifest,
                custody_attestation_sha256=(
                    config.CONNECTED_APPS_KMS_CUSTODY_ATTESTATION_SHA256
                ),
                expected_protection_level=(
                    config.CONNECTED_APPS_KMS_PROTECTION_LEVEL
                ),
                root_ttl_seconds=config.CONNECTED_APPS_KMS_ROOT_TTL_SECONDS,
            )
        ),
        ciphertext=ConnectedEncryptedHostConfiguration(host_ciphertext),
        database=database,
        ai_gateway_factory=ConnectedRequestScopedAIGatewayFactory(
            database=database,
            model="openai/gpt-oss-20b",
            provider="groq",
            deployment_id=deployment_id,
            commit_sha=commit_sha,
        ),
        gateway_probe=ConnectedAIGatewayReleaseProbe(),
        runtime_identity=ConnectedVercelProductionRuntimeIdentity(),
        database_target_fingerprint=(
            config.CONNECTED_APPS_DATABASE_TARGET_FINGERPRINT
        ),
    )
    result = await harness.run(
        permit=permit,
        assertion=assertion,
        expected_manifest_sha256=expected_manifest,
    )
    return {
        "version": "askcrump-release-preview-child-result-v1",
        "ok": True,
        "invocation_id": result.invocation_id,
        "composition_manifest_sha256": result.composition_manifest_sha256,
        "database_target_fingerprint": result.database_target_fingerprint,
        "release_preview_contract_sha256": (
            result.release_preview_contract_sha256
        ),
        "deployment_id": result.deployment_id,
        "commit_sha": result.commit_sha,
        "host_configuration_ciphertext_sha256": (
            result.host_configuration_ciphertext_sha256
        ),
        "provider_smoke_attestation_sha256": (
            result.provider_smoke_attestation_sha256
        ),
        "checked_at": result.checked_at.isoformat().replace("+00:00", "Z"),
        "expires_at": result.expires_at.isoformat().replace("+00:00", "Z"),
        "process_exit_required": True,
    }


def main() -> int:
    try:
        if config.connected_apps_release_candidate_source_released() is not True:
            raise ConnectedReleasePreviewChildError()
        result = asyncio.run(_run(_read_input()))
    except BaseException:
        result = {
            "version": "askcrump-release-preview-child-result-v1",
            "ok": False,
            "error": "CONNECTED_RELEASE_PREVIEW_CHILD_FAILED",
            "process_exit_required": True,
        }
    encoded = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    if len(encoded) > 4096:
        encoded = (
            b'{"error":"CONNECTED_RELEASE_PREVIEW_CHILD_FAILED",'
            b'"ok":false,"process_exit_required":true,'
            b'"version":"askcrump-release-preview-child-result-v1"}'
        )
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
