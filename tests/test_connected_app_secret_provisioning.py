from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "provision-connected-operator-secrets.py"
MANIFEST = "a" * 64
ATTESTATION = "b" * 64
KMS_RESOURCE = (
    "projects/askcrump-prod/locations/us-east1/keyRings/connected/"
    "cryptoKeys/operator-root"
)
ORG_ID = "team_askcrumpproduction"
PROJECT_ID = "prj_askcrumpproduction"


def _module():
    spec = importlib.util.spec_from_file_location("connected_secret_provisioner", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _argv(project_dir: Path | str, cli: Path | str) -> list[str]:
    return [
        str(SCRIPT),
        "--manifest-sha256",
        MANIFEST,
        "--root-key-id",
        "gkms1",
        "--crypto-key-resource",
        KMS_RESOURCE,
        "--custody-attestation-sha256",
        ATTESTATION,
        "--vercel-project-dir",
        str(project_dir),
        "--expected-vercel-org-id",
        ORG_ID,
        "--expected-vercel-project-id",
        PROJECT_ID,
        "--vercel-operation",
        "add",
        "--vercel-cli",
        str(cli),
    ]


def _bypass_vercel_preflight(monkeypatch, module) -> None:
    monkeypatch.setattr(module, "_require_interactive", lambda: None)
    monkeypatch.setattr(
        module,
        "_resolve_vercel_target",
        lambda *_args, **_kwargs: Path("C:/reviewed-vercel-project"),
    )
    monkeypatch.setattr(module, "_resolve_vercel_cli", lambda _value: "vercel.exe")
    monkeypatch.setattr(module, "_run_vercel_version", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_verify_vercel_access", lambda *_args, **_kwargs: None)


def test_memory_only_ceremony_streams_ciphertexts_to_exact_vercel_stdin_only(
    monkeypatch,
    capsys,
    tmp_path,
) -> None:
    module = _module()
    google_id = "ask-crump-google.apps.googleusercontent.com"
    google_secret = "google-secret-material-00001"
    microsoft_id = "00000000-0000-4000-8000-000000000099"
    microsoft_secret = "microsoft-secret-material-00001"
    hidden = iter((google_id, google_secret, microsoft_id, microsoft_secret))
    monkeypatch.setattr(module.getpass, "getpass", lambda _prompt: next(hidden))
    random_values = iter((b"r" * 32, b"n" * 12))
    monkeypatch.setattr(module.secrets, "token_bytes", lambda _size: next(random_values))
    observed: dict[str, object] = {}

    def kms_encrypt(*, crypto_key_resource, root, manifest):
        observed.update(
            crypto_key_resource=crypto_key_resource,
            root=root,
            manifest=manifest,
        )
        return "ZW5jcnlwdGVkLXJvb3Q=", KMS_RESOURCE + "/cryptoKeyVersions/7"

    monkeypatch.setattr(module, "_kms_encrypt", kms_encrypt)
    project_dir = tmp_path / "project"
    (project_dir / ".vercel").mkdir(parents=True)
    (project_dir / ".vercel" / "project.json").write_text(
        json.dumps({"orgId": ORG_ID, "projectId": PROJECT_ID}),
        encoding="utf-8",
    )
    cli = tmp_path / "vercel.exe"
    cli.write_bytes(b"reviewed fake executable")
    monkeypatch.setattr(module, "_require_interactive", lambda: None)
    monkeypatch.setattr(module.shutil, "which", lambda _value: str(cli))
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        command = list(command)
        calls.append((command, dict(kwargs)))
        assert kwargs["shell"] is False
        assert kwargs["cwd"] == str(project_dir.resolve())
        if command[1:] == ["--version"]:
            return subprocess.CompletedProcess(
                command, 0, stdout=b"Vercel CLI 59.6.0\n", stderr=b""
            )
        if command[1:] == ["project", "inspect", "--non-interactive"]:
            assert kwargs["stdin"] is subprocess.DEVNULL
            assert kwargs["stdout"] is subprocess.DEVNULL
            assert kwargs["stderr"] is subprocess.DEVNULL
            return subprocess.CompletedProcess(command, 0)
        assert command[1:3] in (["env", "add"], ["env", "update"])
        assert command[4:] == [
            "production",
            "--type",
            "secret",
            "--non-interactive",
        ]
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert "env" not in kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", _argv(project_dir, cli))

    module.main()

    output = capsys.readouterr()
    assert output.err == ""
    value = json.loads(output.out)
    assert set(value) == {
        "generated_at",
        "crypto_key_version",
        "custody_attestation_sha256",
        "environment",
        "installed_secret_names",
        "installed_value_sha256",
        "root_key_id",
        "vercel_operation",
        "vercel_org_id",
        "vercel_project_id",
    }
    assert value["vercel_org_id"] == ORG_ID
    assert value["vercel_project_id"] == PROJECT_ID
    assert value["environment"] == "production"
    assert value["vercel_operation"] == "add"
    assert value["installed_secret_names"] == list(module._VERCEL_SECRET_NAMES)
    env_calls = [call for call in calls if call[0][1:3] == ["env", "add"]]
    assert [call[0][3] for call in env_calls] == list(module._VERCEL_SECRET_NAMES)
    installed_values = [call[1]["input"].decode("utf-8").rstrip("\n") for call in env_calls]
    assert installed_values[0] == "ZW5jcnlwdGVkLXJvb3Q="
    assert installed_values[1].startswith(
        "v1:gkms1.host_configuration.aaaaaaaaaa:"
    )
    assert value["installed_value_sha256"] == {
        name: hashlib.sha256(secret.encode("ascii")).hexdigest()
        for name, secret in zip(module._VERCEL_SECRET_NAMES, installed_values, strict=True)
    }
    for command, kwargs in env_calls:
        serialized = "\0".join(command)
        assert installed_values[0] not in serialized
        assert installed_values[1] not in serialized
        assert "env" not in kwargs
    for secret in (
        google_id,
        google_secret,
        microsoft_id,
        microsoft_secret,
        (b"r" * 32).hex(),
        *installed_values,
    ):
        assert secret not in output.out
    assert observed == {
        "crypto_key_resource": KMS_RESOURCE,
        "root": b"r" * 32,
        "manifest": bytes.fromhex(MANIFEST),
    }


def test_invalid_ceremony_input_fails_with_one_content_free_message(
    monkeypatch,
    capsys,
) -> None:
    module = _module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--manifest-sha256",
            "invalid",
            "--root-key-id",
            "gkms1",
            "--crypto-key-resource",
            KMS_RESOURCE,
            "--custody-attestation-sha256",
            ATTESTATION,
            "--vercel-project-dir",
            "C:\\reviewed-vercel-project",
            "--expected-vercel-org-id",
            ORG_ID,
            "--expected-vercel-project-id",
            PROJECT_ID,
            "--vercel-operation",
            "add",
        ],
    )
    monkeypatch.setattr(
        module.getpass,
        "getpass",
        lambda _prompt: pytest.fail("invalid input reached a secret prompt"),
    )

    with pytest.raises(SystemExit) as failure:
        module.main()

    assert str(failure.value) == (
        "Provisioning failed without emitting secret material."
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""


def test_short_provider_secret_is_rejected_before_root_or_kms_use(
    monkeypatch,
    capsys,
) -> None:
    module = _module()
    _bypass_vercel_preflight(monkeypatch, module)
    hidden = iter(
        (
            "ask-crump-google.apps.googleusercontent.com",
            "too-short",
        )
    )
    monkeypatch.setattr(module.getpass, "getpass", lambda _prompt: next(hidden))
    monkeypatch.setattr(
        module.secrets,
        "token_bytes",
        lambda _size: pytest.fail("invalid registration generated key material"),
    )
    monkeypatch.setattr(
        module,
        "_kms_encrypt",
        lambda **_kwargs: pytest.fail("invalid registration reached Cloud KMS"),
    )
    monkeypatch.setattr(sys, "argv", _argv("C:\\reviewed-vercel-project", "vercel"))

    with pytest.raises(SystemExit) as failure:
        module.main()

    assert str(failure.value) == (
        "Provisioning failed without emitting secret material."
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""


@pytest.mark.parametrize(
    "registrations",
    (
        (
            "not-a-google-production-client",
            "google-secret-material-00001",
            "00000000-0000-4000-8000-000000000099",
            "microsoft-secret-material-00001",
        ),
        (
            "ask-crump-google.apps.googleusercontent.com",
            "google-secret-material-00001",
            "not-a-microsoft-application-uuid",
            "microsoft-secret-material-00001",
        ),
        (
            "ask-crump-google.apps.googleusercontent.com",
            "shared-provider-secret-material",
            "00000000-0000-4000-8000-000000000099",
            "shared-provider-secret-material",
        ),
    ),
)
def test_provider_specific_registration_drift_is_rejected_before_key_generation(
    registrations,
    monkeypatch,
    capsys,
) -> None:
    module = _module()
    _bypass_vercel_preflight(monkeypatch, module)
    hidden = iter(registrations)
    monkeypatch.setattr(module.getpass, "getpass", lambda _prompt: next(hidden))
    monkeypatch.setattr(
        module.secrets,
        "token_bytes",
        lambda _size: pytest.fail("invalid registration generated key material"),
    )
    monkeypatch.setattr(
        module,
        "_kms_encrypt",
        lambda **_kwargs: pytest.fail("invalid registration reached Cloud KMS"),
    )
    monkeypatch.setattr(sys, "argv", _argv("C:\\reviewed-vercel-project", "vercel"))

    with pytest.raises(SystemExit, match="Provisioning failed without emitting"):
        module.main()
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""


def test_project_link_mismatch_fails_before_any_secret_prompt(
    monkeypatch, capsys, tmp_path
) -> None:
    module = _module()
    project_dir = tmp_path / "project"
    (project_dir / ".vercel").mkdir(parents=True)
    (project_dir / ".vercel" / "project.json").write_text(
        json.dumps({"orgId": "team_wrongtarget", "projectId": PROJECT_ID}),
        encoding="utf-8",
    )
    cli = tmp_path / "vercel.exe"
    cli.write_bytes(b"fake")
    monkeypatch.setattr(module, "_require_interactive", lambda: None)
    monkeypatch.setattr(
        module.getpass,
        "getpass",
        lambda _prompt: pytest.fail("target mismatch reached a secret prompt"),
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("target mismatch invoked Vercel"),
    )
    monkeypatch.setattr(sys, "argv", _argv(project_dir, cli))

    with pytest.raises(SystemExit, match="Provisioning failed without emitting"):
        module.main()
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""


def test_vercel_install_failure_emits_no_ciphertext_or_partial_receipt(
    monkeypatch, capsys
) -> None:
    module = _module()
    _bypass_vercel_preflight(monkeypatch, module)
    hidden = iter(
        (
            "ask-crump-google.apps.googleusercontent.com",
            "google-secret-material-00001",
            "00000000-0000-4000-8000-000000000099",
            "microsoft-secret-material-00001",
        )
    )
    monkeypatch.setattr(module.getpass, "getpass", lambda _prompt: next(hidden))
    random_values = iter((b"r" * 32, b"n" * 12))
    monkeypatch.setattr(module.secrets, "token_bytes", lambda _size: next(random_values))
    monkeypatch.setattr(
        module,
        "_kms_encrypt",
        lambda **_kwargs: (
            "ZW5jcnlwdGVkLXJvb3Q=",
            KMS_RESOURCE + "/cryptoKeyVersions/7",
        ),
    )
    observed: list[str] = []

    def fail_second(_cli, *, name, value, **_kwargs):
        observed.append(value)
        if name == module._VERCEL_SECRET_NAMES[1]:
            module._fail()

    monkeypatch.setattr(module, "_install_vercel_secret", fail_second)
    monkeypatch.setattr(sys, "argv", _argv("C:\\reviewed-vercel-project", "vercel"))

    with pytest.raises(SystemExit, match="Provisioning failed without emitting"):
        module.main()
    output = capsys.readouterr()
    assert len(observed) == 2
    assert output.out == ""
    assert output.err == ""
    assert all(value not in str(capsys.readouterr()) for value in observed)


def test_noninteractive_or_ci_invocation_is_refused(monkeypatch) -> None:
    module = _module()
    monkeypatch.setenv("CI", "1")
    with pytest.raises(SystemExit, match="Provisioning failed without emitting"):
        module._require_interactive()
