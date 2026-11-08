"""Supervise the fixed, short-lived release-preview child process."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
from uuid import UUID, uuid4

from . import config
from .connected_app_kms import ConnectedVercelOIDCAssertion
from .connected_app_release_database import (
    ConnectedReleasePreviewProductionDatabase,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{32}$")
_DEPLOYMENT = re.compile(r"^dpl_[A-Za-z0-9]{8,}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_MAX_OUTPUT = 4096
_MAX_RUNTIME_SECONDS = 240
_CONFIRMATION = "RUN_CONNECTED_RELEASE_PREVIEW_WITH_DEDICATED_NON_CUSTOMER_ACCOUNTS"
_FUTURE_SKEW = timedelta(seconds=5)
_CHILD_ENV = frozenset(
    {
        "APP_ENV",
        "VERCEL",
        "VERCEL_ENV",
        "VERCEL_DEPLOYMENT_ID",
        "VERCEL_GIT_COMMIT_SHA",
        "VERCEL_PROJECT_ID",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "CRUMP_CONNECTED_KMS_ENCRYPTED_ROOT_B64",
        "CRUMP_CONNECTED_HOST_CONFIGURATION_CIPHERTEXT",
    }
)


class ConnectedReleasePreviewSupervisorError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("CONNECTED_RELEASE_PREVIEW_SUPERVISOR_FAILED")
        self.code = "CONNECTED_RELEASE_PREVIEW_SUPERVISOR_FAILED"


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedReleasePreviewSupervisorError()
    return value.astimezone(UTC)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedReleasePreviewSupervisorError()
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedReleasePreviewSupervisorError() from None
    if value != canonical:
        raise ConnectedReleasePreviewSupervisorError()
    return value


@dataclass(frozen=True, slots=True)
class ConnectedReleasePreviewChildResult:
    invocation_id: str
    composition_manifest_sha256: str
    database_target_fingerprint: str
    release_preview_contract_sha256: str
    deployment_id: str
    commit_sha: str
    host_configuration_ciphertext_sha256: str
    provider_smoke_attestation_sha256: str
    checked_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        checked = _aware(self.checked_at)
        expires = _aware(self.expires_at)
        if (
            _uuid(self.invocation_id) != self.invocation_id
            or any(
                _SHA256.fullmatch(value) is None
                for value in (
                    self.composition_manifest_sha256,
                    self.release_preview_contract_sha256,
                    self.host_configuration_ciphertext_sha256,
                    self.provider_smoke_attestation_sha256,
                )
            )
            or _FINGERPRINT.fullmatch(self.database_target_fingerprint) is None
            or _DEPLOYMENT.fullmatch(self.deployment_id) is None
            or _COMMIT.fullmatch(self.commit_sha) is None
            or expires <= checked
        ):
            raise ConnectedReleasePreviewSupervisorError()
        object.__setattr__(self, "checked_at", checked)
        object.__setattr__(self, "expires_at", expires)


@dataclass(frozen=True, slots=True)
class ConnectedReleasePreviewCeremonyClaim:
    invocation_id: str
    issued_at: datetime
    expires_at: datetime
    recovery: bool

    def __post_init__(self) -> None:
        issued = _aware(self.issued_at)
        expires = _aware(self.expires_at)
        if (
            _uuid(self.invocation_id) != self.invocation_id
            or type(self.recovery) is not bool
            or expires <= issued
            or expires - issued > timedelta(minutes=15)
        ):
            raise ConnectedReleasePreviewSupervisorError()
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)


def _child_environment() -> dict[str, str]:
    if config.connected_apps_release_candidate_source_released() is not True:
        raise ConnectedReleasePreviewSupervisorError()
    values = {key: os.environ[key] for key in _CHILD_ENV if key in os.environ}
    if set(values) != _CHILD_ENV or "VERCEL_OIDC_TOKEN" in values:
        raise ConnectedReleasePreviewSupervisorError()
    values["PYTHONIOENCODING"] = "utf-8"
    values["PYTHONUNBUFFERED"] = "1"
    return values


def _release_owner_sha256(owner_id: str) -> str:
    return hashlib.sha256(
        b"askcrump.connected-release-operator/v1\0" + _uuid(owner_id).encode("ascii")
    ).hexdigest()


def _confirmation_sha256(confirmation: str) -> str:
    if confirmation != _CONFIRMATION:
        raise ConnectedReleasePreviewSupervisorError()
    return hashlib.sha256(
        b"askcrump.connected-release-confirmation/v1\0"
        + confirmation.encode("ascii")
    ).hexdigest()


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ConnectedReleasePreviewSupervisorError()
    return value


def _runtime_tuple() -> tuple[str, str, str]:
    if config.connected_apps_release_candidate_source_released() is not True:
        raise ConnectedReleasePreviewSupervisorError()
    deployment_id = os.environ.get("VERCEL_DEPLOYMENT_ID", "")
    commit_sha = os.environ.get("VERCEL_GIT_COMMIT_SHA", "")
    ciphertext = os.environ.get("CRUMP_CONNECTED_HOST_CONFIGURATION_CIPHERTEXT", "")
    if (
        _DEPLOYMENT.fullmatch(deployment_id) is None
        or _COMMIT.fullmatch(commit_sha) is None
        or not isinstance(ciphertext, str)
        or not ciphertext
        or len(ciphertext) > 32_768
    ):
        raise ConnectedReleasePreviewSupervisorError()
    return (
        deployment_id,
        commit_sha,
        hashlib.sha256(ciphertext.encode("utf-8")).hexdigest(),
    )


def _claim_result(
    value: object,
    *,
    deployment_id: str,
    commit_sha: str,
    host_ciphertext_sha256: str,
) -> ConnectedReleasePreviewCeremonyClaim:
    if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        raise ConnectedReleasePreviewSupervisorError()
    row = value[0]
    if set(row) != {
        "invocation_id",
        "issued_at",
        "expires_at",
        "recovery",
        "deployment_id",
        "commit_sha",
        "host_configuration_ciphertext_sha256",
    }:
        raise ConnectedReleasePreviewSupervisorError()
    claim = ConnectedReleasePreviewCeremonyClaim(
        invocation_id=row["invocation_id"],
        issued_at=_parse_timestamp(row["issued_at"]),
        expires_at=_parse_timestamp(row["expires_at"]),
        recovery=row["recovery"],
    )
    reference = datetime.now(UTC)
    if (
        row["deployment_id"] != deployment_id
        or row["commit_sha"] != commit_sha
        or row["host_configuration_ciphertext_sha256"]
        != host_ciphertext_sha256
        or claim.issued_at > reference + _FUTURE_SKEW
        or claim.expires_at <= reference
    ):
        raise ConnectedReleasePreviewSupervisorError()
    return claim


async def claim_connected_release_preview_ceremony(
    *,
    owner_id: str,
    session_binding_sha256: str,
    confirmation: str,
) -> ConnectedReleasePreviewCeremonyClaim:
    """Claim one DB-fenced ceremony from authenticated route state only."""

    if (
        config.connected_apps_release_candidate_source_released() is not True
        or not hmac.compare_digest(
            _release_owner_sha256(owner_id),
            config.CONNECTED_APPS_RELEASE_OPERATOR_OWNER_SHA256,
        )
    ):
        raise ConnectedReleasePreviewSupervisorError()
    session_binding = _sha(session_binding_sha256)
    confirmation_sha256 = _confirmation_sha256(confirmation)
    deployment_id, commit_sha, host_sha256 = _runtime_tuple()
    claim_id = str(uuid4())
    payload = {
        "p_claim_id": claim_id,
        "p_owner_id": owner_id,
        "p_session_binding_sha256": session_binding,
        "p_confirmation_sha256": confirmation_sha256,
        "p_deployment_id": deployment_id,
        "p_commit_sha": commit_sha,
        "p_host_configuration_ciphertext_sha256": host_sha256,
    }
    database = ConnectedReleasePreviewProductionDatabase()
    try:
        await database.rpc(
            "connected_app_claim_release_preview_ceremony_v1",
            payload,
            retry_transient=False,
        )
    except Exception:
        # Claim response loss is ambiguous; never dispatch it again. The
        # service-role readback accepts only this authenticated session and
        # immutable deployment tuple.
        pass
    try:
        observed = await database.rpc(
            "connected_app_read_release_preview_ceremony_v1",
            payload,
            retry_transient=True,
        )
    except Exception:
        raise ConnectedReleasePreviewSupervisorError() from None
    return _claim_result(
        observed,
        deployment_id=deployment_id,
        commit_sha=commit_sha,
        host_ciphertext_sha256=host_sha256,
    )


async def _read_bounded(stream: asyncio.StreamReader) -> bytes:
    collected = bytearray()
    while True:
        chunk = await stream.read(min(1024, _MAX_OUTPUT + 1 - len(collected)))
        if not chunk:
            break
        collected.extend(chunk)
        if len(collected) > _MAX_OUTPUT:
            raise ConnectedReleasePreviewSupervisorError()
    return bytes(collected)


async def _stop(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=2)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise ConnectedReleasePreviewSupervisorError()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedReleasePreviewSupervisorError() from None
    return _aware(parsed)


def _result(raw: bytes, *, invocation_id: str) -> ConnectedReleasePreviewChildResult:
    try:
        value = json.loads(raw.decode("ascii"))
    except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
        raise ConnectedReleasePreviewSupervisorError() from None
    expected = {
        "version",
        "ok",
        "invocation_id",
        "composition_manifest_sha256",
        "database_target_fingerprint",
        "release_preview_contract_sha256",
        "deployment_id",
        "commit_sha",
        "host_configuration_ciphertext_sha256",
        "provider_smoke_attestation_sha256",
        "checked_at",
        "expires_at",
        "process_exit_required",
    }
    if (
        type(value) is not dict
        or set(value) != expected
        or value.get("version") != "askcrump-release-preview-child-result-v1"
        or value.get("ok") is not True
        or value.get("process_exit_required") is not True
        or value.get("invocation_id") != invocation_id
    ):
        raise ConnectedReleasePreviewSupervisorError()
    return ConnectedReleasePreviewChildResult(
        invocation_id=value["invocation_id"],
        composition_manifest_sha256=value["composition_manifest_sha256"],
        database_target_fingerprint=value["database_target_fingerprint"],
        release_preview_contract_sha256=value[
            "release_preview_contract_sha256"
        ],
        deployment_id=value["deployment_id"],
        commit_sha=value["commit_sha"],
        host_configuration_ciphertext_sha256=value[
            "host_configuration_ciphertext_sha256"
        ],
        provider_smoke_attestation_sha256=value[
            "provider_smoke_attestation_sha256"
        ],
        checked_at=_parse_timestamp(value["checked_at"]),
        expires_at=_parse_timestamp(value["expires_at"]),
    )


async def run_connected_release_preview_child(
    *,
    assertion: ConnectedVercelOIDCAssertion,
    invocation_id: str,
    issued_at: datetime,
    expires_at: datetime,
    confirmation: str,
    recovery: bool = False,
) -> ConnectedReleasePreviewChildResult:
    """Run exactly one child and return only its content-free receipt."""

    if (
        config.connected_apps_release_candidate_source_released() is not True
        or type(assertion) is not ConnectedVercelOIDCAssertion
        or confirmation != _CONFIRMATION
        or type(recovery) is not bool
    ):
        raise ConnectedReleasePreviewSupervisorError()
    invocation = _uuid(invocation_id)
    issued = _aware(issued_at)
    expires = _aware(expires_at)
    if expires <= issued or expires - issued > timedelta(minutes=15):
        raise ConnectedReleasePreviewSupervisorError()
    payload = json.dumps(
        {
            "version": "askcrump-release-preview-child-v1",
            "request_oidc_assertion": assertion.reveal_for_exchange(),
            "invocation_id": invocation,
            "issued_at": issued.isoformat().replace("+00:00", "Z"),
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "confirmation": confirmation,
            "recovery": recovery,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    child = Path(__file__).with_name("connected_app_release_preview_child.py")
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(child),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=_child_environment(),
            start_new_session=True,
        )
        if process.stdin is None or process.stdout is None:
            raise ConnectedReleasePreviewSupervisorError()
        process.stdin.write(payload)
        await process.stdin.drain()
        process.stdin.close()
        output, returncode = await asyncio.wait_for(
            asyncio.gather(_read_bounded(process.stdout), process.wait()),
            timeout=_MAX_RUNTIME_SECONDS,
        )
        if returncode != 0:
            raise ConnectedReleasePreviewSupervisorError()
        result = _result(output, invocation_id=invocation)
        # The child must already be gone before its receipt is usable.
        if process.returncode != 0:
            raise ConnectedReleasePreviewSupervisorError()
        return result
    except BaseException as exc:
        if process is not None:
            await _stop(process)
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise ConnectedReleasePreviewSupervisorError() from None


__all__ = [
    "ConnectedReleasePreviewCeremonyClaim",
    "ConnectedReleasePreviewChildResult",
    "ConnectedReleasePreviewSupervisorError",
    "claim_connected_release_preview_ceremony",
    "run_connected_release_preview_child",
]
