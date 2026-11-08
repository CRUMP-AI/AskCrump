"""One-shot, memory-only connected-operator secret provisioning ceremony.

This script is deliberately never imported by the application.  It prompts
for both provider registrations with hidden terminal input, generates the
32-byte root in memory, seals the provider configuration with the derived
host-configuration domain, sends the root directly to Google Cloud KMS over
HTTPS for encryption, and streams both resulting ciphertexts directly to the
exact linked Vercel project's protected production-secret entries.  Standard
output contains a nonsecret, hash-only installation receipt; no secret or
ciphertext value is written to disk or printed to a terminal.

Running this is a user-controlled external security action.  Merely checking
the script into the repository does not create a key, credential, connection,
or billable resource.
"""

from __future__ import annotations

import argparse
import base64
from datetime import UTC, datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from typing import NoReturn
from uuid import UUID

import certifi
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import httpx


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$")
_KMS_RESOURCE = re.compile(
    r"^projects/[a-z][a-z0-9-]{4,62}/locations/[a-z0-9-]{1,63}/"
    r"keyRings/[A-Za-z0-9_-]{1,63}/cryptoKeys/[A-Za-z0-9_-]{1,63}$"
)
_CLIENT_ID = re.compile(r"[A-Za-z0-9._:@/-]{8,512}")
_VERCEL_ORG_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{5,128}")
_VERCEL_PROJECT_ID = re.compile(r"prj_[A-Za-z0-9]{6,128}")
# Keep the ceremony's acceptance boundary identical to the runtime
# ProviderOAuthClientSecret contract.  Otherwise a short value could be sealed
# successfully and only fail later, after the plaintext has already been
# destroyed and the ciphertext handed to the deployment operator.
_SECRET = re.compile(r"[^\x00-\x20\x7f]{16,4096}")
_INFO_PREFIX = b"askcrump.connected-operator.key/v1/"
_HOST_AAD_PREFIX = b"askcrump.connected-host-configuration/v1\0"
_MIN_VERCEL_CLI = (59, 6, 0)
_VERCEL_SECRET_NAMES = (
    "CRUMP_CONNECTED_KMS_ENCRYPTED_ROOT_B64",
    "CRUMP_CONNECTED_HOST_CONFIGURATION_CIPHERTEXT",
)


def _fail() -> NoReturn:
    raise SystemExit("Provisioning failed without emitting secret material.")


def _crc32c(value: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in value:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _hidden(label: str, pattern: re.Pattern[str]) -> str:
    value = getpass.getpass(f"{label} (hidden): ")
    if not pattern.fullmatch(value):
        _fail()
    return value


def _require_interactive() -> None:
    """Refuse CI, pipes, and log-oriented/noninteractive invocation."""

    if os.environ.get("CI") or not sys.stdin.isatty():
        _fail()


def _resolve_vercel_target(
    project_dir: str,
    *,
    expected_org_id: str,
    expected_project_id: str,
) -> Path:
    if (
        not _VERCEL_ORG_ID.fullmatch(expected_org_id)
        or not _VERCEL_PROJECT_ID.fullmatch(expected_project_id)
    ):
        _fail()
    candidate = Path(project_dir)
    if not candidate.is_absolute():
        _fail()
    try:
        if candidate.is_symlink():
            _fail()
        root = candidate.resolve(strict=True)
        vercel_dir = root / ".vercel"
        project_file = vercel_dir / "project.json"
        if vercel_dir.is_symlink() or project_file.is_symlink():
            _fail()
        raw = project_file.read_bytes()
    except (OSError, RuntimeError):
        _fail()
    if not root.is_dir() or len(raw) > 32 * 1024:
        _fail()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail()
    if (
        type(value) is not dict
        or value.get("orgId") != expected_org_id
        or value.get("projectId") != expected_project_id
    ):
        _fail()
    return root


def _resolve_vercel_cli(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 1024:
        _fail()
    found = shutil.which(value)
    if found is None:
        candidate = Path(value)
        if candidate.is_absolute() and candidate.is_file():
            found = str(candidate)
    if found is None:
        _fail()
    try:
        resolved = Path(found).resolve(strict=True)
    except (OSError, RuntimeError):
        _fail()
    if not resolved.is_file():
        _fail()
    return str(resolved)


def _run_vercel_version(cli: str, *, project_dir: Path) -> None:
    try:
        completed = subprocess.run(
            [cli, "--version"],
            cwd=str(project_dir),
            check=False,
            capture_output=True,
            timeout=15,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        _fail()
    output = bytes(completed.stdout or b"") + bytes(completed.stderr or b"")
    if completed.returncode != 0 or len(output) > 512:
        _fail()
    try:
        decoded = output.decode("ascii")
    except UnicodeDecodeError:
        _fail()
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?(?!\d)", decoded)
    if match is None:
        _fail()
    version = tuple(int(part or "0") for part in match.groups())
    if version < _MIN_VERCEL_CLI:
        _fail()


def _verify_vercel_access(cli: str, *, project_dir: Path) -> None:
    try:
        completed = subprocess.run(
            [cli, "project", "inspect", "--non-interactive"],
            cwd=str(project_dir),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        _fail()
    if completed.returncode != 0:
        _fail()


def _install_vercel_secret(
    cli: str,
    *,
    project_dir: Path,
    operation: str,
    name: str,
    value: str,
) -> None:
    if operation not in {"add", "update"} or name not in _VERCEL_SECRET_NAMES:
        _fail()
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        _fail()
    command = [
        cli,
        "env",
        operation,
        name,
        "production",
        "--type",
        "secret",
        "--non-interactive",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(project_dir),
            check=False,
            input=(value + "\n").encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        _fail()
    if completed.returncode != 0:
        _fail()


def _access_token() -> str:
    try:
        completed = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        _fail()
    token = completed.stdout.strip()
    if (
        not 32 <= len(token) <= 12_288
        or any(ord(character) <= 32 or ord(character) == 127 for character in token)
    ):
        _fail()
    return token


def _kms_encrypt(
    *,
    crypto_key_resource: str,
    root: bytes,
    manifest: bytes,
) -> tuple[str, str]:
    token = _access_token()
    try:
        with httpx.Client(
            http2=True,
            verify=certifi.where(),
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(20.0, connect=5.0, write=10.0, pool=5.0),
        ) as client:
            response = client.post(
                f"https://cloudkms.googleapis.com/v1/{crypto_key_resource}:encrypt",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "AskCrump-Connected-Provisioner/1",
                },
                json={
                    "plaintext": base64.b64encode(root).decode("ascii"),
                    "additionalAuthenticatedData": base64.b64encode(manifest).decode(
                        "ascii"
                    ),
                    "plaintextCrc32c": str(_crc32c(root)),
                    "additionalAuthenticatedDataCrc32c": str(_crc32c(manifest)),
                },
            )
    except httpx.HTTPError:
        _fail()
    if response.status_code != 200 or len(response.content) > 64 * 1024:
        _fail()
    try:
        value = response.json()
        ciphertext = base64.b64decode(value["ciphertext"], validate=True)
        returned_crc = int(value["ciphertextCrc32c"])
        key_version = value["name"]
    except (KeyError, TypeError, ValueError, OverflowError, json.JSONDecodeError):
        _fail()
    if (
        value.get("verifiedPlaintextCrc32c") is not True
        or value.get("verifiedAdditionalAuthenticatedDataCrc32c") is not True
        or not ciphertext
        or len(ciphertext) > 64 * 1024
        or _crc32c(ciphertext) != returned_crc
        or not isinstance(key_version, str)
        or not key_version.startswith(crypto_key_resource + "/cryptoKeyVersions/")
    ):
        _fail()
    return base64.b64encode(ciphertext).decode("ascii"), key_version


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seal Ask Crump connected-operator deployment secrets."
    )
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--root-key-id", required=True)
    parser.add_argument("--crypto-key-resource", required=True)
    parser.add_argument("--custody-attestation-sha256", required=True)
    parser.add_argument("--vercel-project-dir", required=True)
    parser.add_argument("--expected-vercel-org-id", required=True)
    parser.add_argument("--expected-vercel-project-id", required=True)
    parser.add_argument(
        "--vercel-operation", required=True, choices=("add", "update")
    )
    parser.add_argument("--vercel-cli", default="vercel")
    arguments = parser.parse_args()
    if (
        not _SHA256.fullmatch(arguments.manifest_sha256)
        or not _KEY_ID.fullmatch(arguments.root_key_id)
        or not _KMS_RESOURCE.fullmatch(arguments.crypto_key_resource)
        or not _SHA256.fullmatch(arguments.custody_attestation_sha256)
    ):
        _fail()

    _require_interactive()
    project_dir = _resolve_vercel_target(
        arguments.vercel_project_dir,
        expected_org_id=arguments.expected_vercel_org_id,
        expected_project_id=arguments.expected_vercel_project_id,
    )
    vercel_cli = _resolve_vercel_cli(arguments.vercel_cli)
    _run_vercel_version(vercel_cli, project_dir=project_dir)
    _verify_vercel_access(vercel_cli, project_dir=project_dir)

    google_client_id = _hidden("Google OAuth client ID", _CLIENT_ID)
    google_client_secret = _hidden("Google OAuth client secret", _SECRET)
    microsoft_client_id = _hidden("Microsoft OAuth client ID", _CLIENT_ID)
    microsoft_client_secret = _hidden("Microsoft OAuth client secret", _SECRET)
    try:
        microsoft_client_id_canonical = str(UUID(microsoft_client_id))
    except (ValueError, TypeError, AttributeError):
        _fail()
    if (
        not google_client_id.endswith(".apps.googleusercontent.com")
        or microsoft_client_id != microsoft_client_id_canonical
        or google_client_secret == microsoft_client_secret
    ):
        _fail()

    root = secrets.token_bytes(32)
    manifest = bytes.fromhex(arguments.manifest_sha256)
    host_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=manifest,
        info=_INFO_PREFIX + b"host_configuration",
    ).derive(root)
    host_key_id = (
        f"{arguments.root_key_id}.host_configuration."
        f"{arguments.manifest_sha256[:10]}"
    )
    if len(host_key_id) > 64:
        _fail()
    host_plaintext = json.dumps(
        {
            "version": "askcrump-connected-host-v1",
            "composition_manifest_sha256": arguments.manifest_sha256,
            "google": {
                "client_id": google_client_id,
                "client_secret": google_client_secret,
            },
            "microsoft": {
                "client_id": microsoft_client_id,
                "client_secret": microsoft_client_secret,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    nonce = secrets.token_bytes(12)
    host_aad = _HOST_AAD_PREFIX + manifest + b"\0" + host_key_id.encode("ascii")
    host_ciphertext = AESGCM(host_key).encrypt(nonce, host_plaintext, host_aad)
    host_envelope = ":".join(
        ("v1", host_key_id, _b64url(nonce), _b64url(host_ciphertext))
    )

    encrypted_root, crypto_key_version = _kms_encrypt(
        crypto_key_resource=arguments.crypto_key_resource,
        root=root,
        manifest=manifest,
    )
    encrypted_root_sha256 = hashlib.sha256(encrypted_root.encode("ascii")).hexdigest()
    host_envelope_sha256 = hashlib.sha256(host_envelope.encode("ascii")).hexdigest()
    _install_vercel_secret(
        vercel_cli,
        project_dir=project_dir,
        operation=arguments.vercel_operation,
        name=_VERCEL_SECRET_NAMES[0],
        value=encrypted_root,
    )
    _install_vercel_secret(
        vercel_cli,
        project_dir=project_dir,
        operation=arguments.vercel_operation,
        name=_VERCEL_SECRET_NAMES[1],
        value=host_envelope,
    )

    # The ciphertexts were streamed over child stdin and are never echoed.
    # Only nonsecret target identity and one-way evidence reach stdout.
    json.dump(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "crypto_key_version": crypto_key_version,
            "custody_attestation_sha256": arguments.custody_attestation_sha256,
            "environment": "production",
            "installed_secret_names": list(_VERCEL_SECRET_NAMES),
            "installed_value_sha256": {
                _VERCEL_SECRET_NAMES[0]: encrypted_root_sha256,
                _VERCEL_SECRET_NAMES[1]: host_envelope_sha256,
            },
            "root_key_id": arguments.root_key_id,
            "vercel_operation": arguments.vercel_operation,
            "vercel_org_id": arguments.expected_vercel_org_id,
            "vercel_project_id": arguments.expected_vercel_project_id,
        },
        sys.stdout,
        sort_keys=True,
        separators=(",", ":"),
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, Exception):
        _fail()
