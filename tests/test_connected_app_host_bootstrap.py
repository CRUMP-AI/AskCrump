from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import itertools
import json
from pathlib import Path
import pickle

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pytest

from backend import config
from backend import connected_app_request_activation as request_activation
from backend.connected_app_host_bootstrap import (
    CONNECTED_DATABASE_CONTRACT_SHA256,
    CONNECTED_PROVIDER_CONTRACT_SHA256,
    ConnectedHostBootstrapError,
    ConnectedProductionGraphInputsBuilder,
    SupabaseConnectedProductionReadinessProbe,
    configure_connected_production_host,
)
from backend.connected_app_host_configuration import (
    ConnectedEncryptedHostConfiguration,
    ConnectedHostConfigurationError,
)
from backend.connected_app_key_derivation import (
    ConnectedDerivedKeyset,
    ConnectedKeyCustodyKind,
    ConnectedRootKeyMaterial,
)
from backend.connected_app_kms import ConnectedVercelOIDCAssertion
from backend.connected_app_policy import ConnectorProvider
from backend.connected_app_production import ConnectedProductionGraphInputs
from backend.connected_app_production_keys import ConnectedProductionKeys
from backend.connected_app_readiness_attestation import (
    ConnectedProviderSmokeAttestor,
    ConnectedProviderSmokeChallenge,
    ConnectedProviderSmokeDeployment,
)
from backend.connected_app_release_contract import (
    CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256,
)


NOW = datetime(2026, 11, 8, 18, 0, tzinfo=UTC)
MANIFEST = hashlib.sha256(b"secure-connected-host").hexdigest()
ATTESTATION = hashlib.sha256(b"kms-policy-version").hexdigest()
TOKEN = "a" * 80 + "." + "b" * 80 + "." + "c" * 80
DATABASE_TARGET = "1" * 32
DEPLOYMENT_ID = "dpl_12345678abcd"
COMMIT_SHA = "a" * 40
CHALLENGE_ID = "11111111-1111-4111-8111-111111111111"
CHALLENGE_ISSUED_AT = NOW - timedelta(days=30, minutes=1)
SMOKE_CHECKED_AT = NOW - timedelta(days=30)
DESCRIPTOR_MATRIX = hashlib.sha256(b"descriptor-matrix").hexdigest()
DEDICATED_ACCOUNT_ATTESTATION = hashlib.sha256(
    b"dedicated-account-attestation"
).hexdigest()
EFFECT_MANIFEST = hashlib.sha256(b"effect-manifest").hexdigest()
INVOCATION_ID = "22222222-2222-4222-8222-222222222222"


def production_keys(*, secret: bytes = b"k" * 32) -> ConnectedProductionKeys:
    root = ConnectedRootKeyMaterial(
        key_id="gkms1",
        custody=ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS,
        attestation_sha256=ATTESTATION,
        loaded_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(minutes=10),
        secret=secret,
    )
    return ConnectedProductionKeys.build(
        ConnectedDerivedKeyset(
            root=root,
            composition_manifest_sha256=MANIFEST,
            now=lambda: NOW,
        ),
        now=lambda: NOW,
    )


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def encrypted_configuration(
    keys: ConnectedProductionKeys,
    *,
    manifest: str = MANIFEST,
    payload_changes: dict[str, object] | None = None,
) -> ConnectedEncryptedHostConfiguration:
    payload: dict[str, object] = {
        "version": "askcrump-connected-host-v1",
        "composition_manifest_sha256": manifest,
        "google": {
            "client_id": "ask-crump-google-client.apps.googleusercontent.com",
            "client_secret": "google-client-secret-material-000001",
        },
        "microsoft": {
            "client_id": "00000000-0000-4000-8000-000000000099",
            "client_secret": "microsoft-client-secret-material-0001",
        },
    }
    if payload_changes:
        payload.update(payload_changes)
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    nonce = bytes(range(12))
    key = keys.host_configuration
    aad = (
        b"askcrump.connected-host-configuration/v1\0"
        + bytes.fromhex(manifest)
        + b"\0"
        + key.key_id.encode("ascii")
    )
    ciphertext = AESGCM(key.secret).encrypt(nonce, plaintext, aad)
    return ConnectedEncryptedHostConfiguration(
        ":".join(("v1", key.key_id, _b64url(nonce), _b64url(ciphertext)))
    )


def readiness_row(**changes: object) -> list[dict[str, object]]:
    keys = production_keys()
    envelope = encrypted_configuration(keys)
    host_sha256 = hashlib.sha256(envelope.value.encode("utf-8")).hexdigest()
    deployment = ConnectedProviderSmokeDeployment(
        composition_manifest_sha256=MANIFEST,
        database_contract_sha256=CONNECTED_DATABASE_CONTRACT_SHA256,
        database_target_fingerprint=DATABASE_TARGET,
        provider_contract_sha256=CONNECTED_PROVIDER_CONTRACT_SHA256,
        deployment_id=DEPLOYMENT_ID,
        commit_sha=COMMIT_SHA,
        host_configuration_ciphertext_sha256=host_sha256,
        root_key_id=keys.root_key_id,
        release_preview_contract_sha256=(
            CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
        ),
        release_preview_descriptor_matrix_sha256=DESCRIPTOR_MATRIX,
        release_preview_dedicated_account_attestation_sha256=(
            DEDICATED_ACCOUNT_ATTESTATION
        ),
        release_preview_invocation_id=INVOCATION_ID,
        release_preview_effect_manifest_sha256=EFFECT_MANIFEST,
    )
    challenge = ConnectedProviderSmokeChallenge(
        deployment=deployment,
        challenge_id=CHALLENGE_ID,
        issued_at=CHALLENGE_ISSUED_AT,
    )
    row: dict[str, object] = {
        "composition_manifest_sha256": MANIFEST,
        "database_contract_sha256": CONNECTED_DATABASE_CONTRACT_SHA256,
        "database_target_fingerprint": DATABASE_TARGET,
        "provider_contract_sha256": CONNECTED_PROVIDER_CONTRACT_SHA256,
        "deployment_id": DEPLOYMENT_ID,
        "commit_sha": COMMIT_SHA,
        "host_configuration_ciphertext_sha256": host_sha256,
        "root_key_id": keys.root_key_id,
        "release_preview_contract_sha256": (
            CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
        ),
        "release_preview_descriptor_matrix_sha256": DESCRIPTOR_MATRIX,
        "release_preview_dedicated_account_attestation_sha256": (
            DEDICATED_ACCOUNT_ATTESTATION
        ),
        "release_preview_invocation_id": INVOCATION_ID,
        "release_preview_effect_manifest_sha256": EFFECT_MANIFEST,
        "checked_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
        "provider_smoke_checked_at": SMOKE_CHECKED_AT.isoformat(),
        "provider_smoke_challenge_id": CHALLENGE_ID,
        "provider_smoke_challenge_issued_at": CHALLENGE_ISSUED_AT.isoformat(),
        "provider_smoke_attestation_sha256": ConnectedProviderSmokeAttestor(
            keys.readiness_attestation
        ).sign(challenge),
    }
    row.update(changes)
    return [row]


class Database:
    def __init__(self, result: object | None = None) -> None:
        self.result = result if result is not None else readiness_row()
        self.calls: list[tuple[object, ...]] = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        return self.result


def readiness_probe(database: Database) -> SupabaseConnectedProductionReadinessProbe:
    envelope = encrypted_configuration(production_keys())
    return SupabaseConnectedProductionReadinessProbe(
        database,
        database_target_fingerprint=DATABASE_TARGET,
        deployment_id=DEPLOYMENT_ID,
        commit_sha=COMMIT_SHA,
        host_configuration_ciphertext_sha256=hashlib.sha256(
            envelope.value.encode("utf-8")
        ).hexdigest(),
        now=lambda: NOW,
    )


class AI:
    async def gateway_text(self, **_kwargs) -> str:
        raise AssertionError("graph-input construction must not call the model")


class AIFactory:
    def __init__(self) -> None:
        self.assertions: list[object] = []

    def build(self, *, assertion):
        self.assertions.append(assertion)
        return AI()


@pytest.fixture(autouse=True)
def clean_activation(monkeypatch):
    request_activation.connected_request_activation_coordinator = None
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", False)
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        False,
    )
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", False)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", "")
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_DATABASE_TARGET_FINGERPRINT",
        DATABASE_TARGET,
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_PROJECT_NUMBER", "123456789012")
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_WIF_POOL_ID", "askcrump-pool")
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_KMS_WIF_PROVIDER_ID",
        "vercel-provider",
    )
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_KMS_SERVICE_ACCOUNT_EMAIL",
        "askcrump-kms@askcrump-prod.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_KMS_CRYPTO_KEY_RESOURCE",
        (
            "projects/askcrump-prod/locations/us-east1/keyRings/connected/"
            "cryptoKeys/operator-root"
        ),
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_ROOT_KEY_ID", "gkms1")
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_KMS_CUSTODY_ATTESTATION_SHA256",
        ATTESTATION,
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_PROTECTION_LEVEL", "HSM")
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_ROOT_TTL_SECONDS", 600)
    yield
    request_activation.connected_request_activation_coordinator = None


def set_source_locks(
    monkeypatch,
    *,
    preview: bool,
    public: bool,
    multi: bool,
) -> None:
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        preview,
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", public)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", multi)


def release_candidate(monkeypatch) -> None:
    set_source_locks(
        monkeypatch,
        preview=True,
        public=True,
        multi=True,
    )


def test_envelope_opens_exact_registrations_and_never_discloses_secrets() -> None:
    keys = production_keys()
    envelope = encrypted_configuration(keys)
    value = envelope.open(
        key=keys.host_configuration,
        composition_manifest_sha256=MANIFEST,
    )
    assert set(value.registrations) == set(ConnectorProvider)
    assert value.registrations[ConnectorProvider.GOOGLE].client_id.endswith(
        ".apps.googleusercontent.com"
    )
    rendered = " ".join((repr(keys.host_configuration), repr(envelope), repr(value)))
    assert "google-client-secret-material" not in rendered
    assert "microsoft-client-secret-material" not in rendered
    assert "<redacted>" in rendered
    for item in (keys.host_configuration, envelope, value):
        with pytest.raises(TypeError):
            pickle.dumps(item)


def test_envelope_rejects_wrong_root_manifest_tamper_and_shape() -> None:
    keys = production_keys()
    envelope = encrypted_configuration(keys)
    for wrong in (
        production_keys(secret=b"z" * 32).host_configuration,
        keys.host_configuration,
    ):
        with pytest.raises(
            ConnectedHostConfigurationError,
            match="CONNECTED_HOST_CONFIGURATION_DECRYPT_FAILED",
        ):
            envelope.open(
                key=wrong,
                composition_manifest_sha256=(
                    MANIFEST
                    if wrong is not keys.host_configuration
                    else hashlib.sha256(b"other manifest").hexdigest()
                ),
            )

    malformed = encrypted_configuration(
        keys,
        payload_changes={"unexpected": True},
    )
    with pytest.raises(
        ConnectedHostConfigurationError,
        match="CONNECTED_HOST_CONFIGURATION_INVALID",
    ):
        malformed.open(
            key=keys.host_configuration,
            composition_manifest_sha256=MANIFEST,
        )

    for provider_changes in (
        {
            "google": {
                "client_id": "not-a-google-production-client",
                "client_secret": "google-client-secret-material-000001",
            }
        },
        {
            "microsoft": {
                "client_id": "not-a-microsoft-application-uuid",
                "client_secret": "microsoft-client-secret-material-0001",
            }
        },
        {
            "microsoft": {
                "client_id": "00000000-0000-4000-8000-000000000099",
                "client_secret": "google-client-secret-material-000001",
            }
        },
    ):
        malformed_registration = encrypted_configuration(
            keys,
            payload_changes=provider_changes,
        )
        with pytest.raises(
            ConnectedHostConfigurationError,
            match="CONNECTED_HOST_CONFIGURATION_INVALID",
        ):
            malformed_registration.open(
                key=keys.host_configuration,
                composition_manifest_sha256=MANIFEST,
            )


@pytest.mark.asyncio
async def test_live_probe_is_exact_fresh_and_covers_key_lifetime() -> None:
    database = Database()
    keys = production_keys()
    probe = readiness_probe(database)
    value = await probe.attest(
        keys=keys,
        expected_manifest_sha256=MANIFEST,
        minimum_expires_at=NOW + timedelta(minutes=9),
    )
    assert value.is_ready(expected_manifest_sha256=MANIFEST, now=NOW)
    assert database.calls == [
        (
            "connected_app_runtime_readiness_v1",
            {
                "p_expected_manifest_sha256": MANIFEST,
                "p_expected_database_contract_sha256": (
                    CONNECTED_DATABASE_CONTRACT_SHA256
                ),
                "p_expected_database_target_fingerprint": DATABASE_TARGET,
                "p_expected_provider_contract_sha256": (
                    CONNECTED_PROVIDER_CONTRACT_SHA256
                ),
                "p_expected_deployment_id": DEPLOYMENT_ID,
                "p_expected_commit_sha": COMMIT_SHA,
                "p_expected_host_configuration_ciphertext_sha256": (
                    hashlib.sha256(
                        encrypted_configuration(keys).value.encode("utf-8")
                    ).hexdigest()
                ),
                "p_expected_root_key_id": keys.root_key_id,
                "p_expected_release_preview_contract_sha256": (
                    CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256
                ),
            },
            False,
        )
    ]


@pytest.mark.asyncio
async def test_live_probe_can_require_one_exact_release_preview_receipt() -> None:
    database = Database()
    keys = production_keys()
    expected_receipt = readiness_row()[0]["provider_smoke_attestation_sha256"]
    value = await readiness_probe(database).attest(
        keys=keys,
        expected_manifest_sha256=MANIFEST,
        minimum_expires_at=NOW + timedelta(minutes=9),
        expected_provider_smoke_attestation_sha256=expected_receipt,
    )
    assert value.is_ready(expected_manifest_sha256=MANIFEST, now=NOW)

    with pytest.raises(
        ConnectedHostBootstrapError,
        match="CONNECTED_HOST_BOOTSTRAP_NOT_READY",
    ):
        await readiness_probe(Database()).attest(
            keys=keys,
            expected_manifest_sha256=MANIFEST,
            minimum_expires_at=NOW + timedelta(minutes=9),
            expected_provider_smoke_attestation_sha256="0" * 64,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    (
        [],
        readiness_row(database_contract_sha256="0" * 64),
        readiness_row(provider_contract_sha256="0" * 64),
        readiness_row(database_target_fingerprint="0" * 32),
        readiness_row(deployment_id="dpl_wrongvalue"),
        readiness_row(provider_smoke_attestation_sha256="0" * 64),
        readiness_row(checked_at=(NOW - timedelta(minutes=2)).isoformat()),
        readiness_row(expires_at=(NOW + timedelta(minutes=8)).isoformat()),
        readiness_row(
            checked_at=(NOW + timedelta(seconds=4)).isoformat(),
            expires_at=(NOW + timedelta(seconds=2)).isoformat(),
        ),
        readiness_row(
            provider_smoke_checked_at=(NOW + timedelta(seconds=9)).isoformat()
        ),
        readiness_row(unexpected=True),
    ),
)
async def test_live_probe_rejects_shape_tuple_hmac_and_lease_drift(result) -> None:
    probe = readiness_probe(Database(result))
    with pytest.raises(
        ConnectedHostBootstrapError,
        match="CONNECTED_HOST_BOOTSTRAP_NOT_READY",
    ):
        await probe.attest(
            keys=production_keys(),
            expected_manifest_sha256=MANIFEST,
            minimum_expires_at=NOW + timedelta(minutes=9),
        )


@pytest.mark.asyncio
async def test_builder_attests_then_decrypts_without_provider_or_model_call() -> None:
    keys = production_keys()
    database = Database()
    readiness = readiness_probe(database)
    ai_factory = AIFactory()
    builder = ConnectedProductionGraphInputsBuilder(
        ciphertext=encrypted_configuration(keys),
        database=database,
        ai_gateway_factory=ai_factory,
        readiness=readiness,
        now=lambda: NOW,
    )
    assertion = ConnectedVercelOIDCAssertion(TOKEN)
    value = await builder.build(
        keys=keys,
        expected_manifest_sha256=MANIFEST,
        assertion=assertion,
    )
    assert type(value) is ConnectedProductionGraphInputs
    assert value.keys is keys
    assert value.key_custody is ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS
    assert value.redirect_uris == {
        ConnectorProvider.GOOGLE: (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
        ),
        ConnectorProvider.MICROSOFT: (
            "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
        ),
    }
    assert all(item is None for item in value.oauth_transports.values())
    assert all(item is None for item in value.provider_transports.values())
    assert ai_factory.assertions == [assertion]
    assert repr(builder) == "ConnectedProductionGraphInputsBuilder(config='<encrypted>')"


@pytest.mark.asyncio
async def test_builder_does_not_open_registration_secrets_before_readiness(
    monkeypatch,
) -> None:
    keys = production_keys()
    database = Database([])
    opened: list[bool] = []
    original_open = ConnectedEncryptedHostConfiguration.open

    def tracked_open(self, **kwargs):
        opened.append(True)
        return original_open(self, **kwargs)

    monkeypatch.setattr(ConnectedEncryptedHostConfiguration, "open", tracked_open)
    builder = ConnectedProductionGraphInputsBuilder(
        ciphertext=encrypted_configuration(keys),
        database=database,
        ai_gateway_factory=AIFactory(),
        readiness=readiness_probe(database),
        now=lambda: NOW,
    )
    with pytest.raises(
        ConnectedHostBootstrapError,
        match="CONNECTED_HOST_BOOTSTRAP_NOT_READY",
    ):
        await builder.build(
            keys=keys,
            expected_manifest_sha256=MANIFEST,
            assertion=ConnectedVercelOIDCAssertion(TOKEN),
        )
    assert opened == []


class OpaqueEnvironment(dict):
    def __getitem__(self, _key):
        raise AssertionError("lock-false bootstrap read a deployment setting")

    def get(self, _key, _default=None):
        raise AssertionError("lock-false bootstrap read a deployment setting")


def test_environment_switch_source_short_circuits_and_reads_only_its_boolean(
    monkeypatch,
) -> None:
    set_source_locks(
        monkeypatch,
        preview=False,
        public=False,
        multi=False,
    )
    monkeypatch.setattr(
        config.os,
        "getenv",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("source-lock false read the process environment")
        ),
    )
    assert config.connected_apps_environment_released() is False

    reads: list[tuple[object, ...]] = []
    release_candidate(monkeypatch)

    def getenv(*args):
        reads.append(args)
        return "true"

    monkeypatch.setattr(config.os, "getenv", getenv)
    assert config.connected_apps_environment_released() is True
    assert reads == [("CRUMP_ENABLE_CONNECTED_APPS",)]


def test_host_checks_both_locks_before_runtime_or_deployment_reads() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "connected_app_host_bootstrap.py"
    ).read_text(encoding="utf-8")
    function = source[source.index("def configure_connected_production_host(") :]
    assert function.index(
        "config.connected_apps_release_candidate_source_released() is not True"
    ) < (
        function.index("config.connected_apps_environment_released() is not True")
    )
    assert function.index("config.connected_apps_environment_released() is not True") < (
        function.index("from .runtime import db")
    )
    assert function.index("from .runtime import db") < function.index("os.environ")


@pytest.mark.parametrize(
    ("preview", "public", "multi"),
    [
        combination
        for combination in itertools.product((False, True), repeat=3)
        if combination != (True, True, True)
    ],
)
def test_partial_source_locks_never_import_services_or_read_environment(
    monkeypatch,
    preview,
    public,
    multi,
) -> None:
    set_source_locks(
        monkeypatch,
        preview=preview,
        public=public,
        multi=multi,
    )
    monkeypatch.setattr(
        config,
        "connected_apps_environment_released",
        lambda: (_ for _ in ()).throw(
            AssertionError("partial source lock inspected the environment switch")
        ),
    )
    assert configure_connected_production_host(environment=OpaqueEnvironment()) is None
    assert request_activation.connected_request_activation_coordinator is None


def test_environment_lock_false_never_reads_connected_configuration(monkeypatch) -> None:
    release_candidate(monkeypatch)
    monkeypatch.setattr(config, "connected_apps_environment_released", lambda: False)
    assert configure_connected_production_host(environment=OpaqueEnvironment()) is None
    assert request_activation.connected_request_activation_coordinator is None


def deployment_environment(envelope: ConnectedEncryptedHostConfiguration) -> dict[str, str]:
    return {
        "CRUMP_CONNECTED_KMS_ENCRYPTED_ROOT_B64": base64.b64encode(
            b"ciphertext-only"
        ).decode(),
        "CRUMP_CONNECTED_HOST_CONFIGURATION_CIPHERTEXT": envelope.value,
        "VERCEL_DEPLOYMENT_ID": "dpl_12345678abcd",
        "VERCEL_GIT_COMMIT_SHA": "a" * 40,
    }


def test_released_bootstrap_installs_only_request_scoped_header_coordinator(monkeypatch) -> None:
    keys = production_keys()
    environment = deployment_environment(encrypted_configuration(keys))
    reads: list[str] = []

    class TrackingEnvironment(dict):
        def __getitem__(self, key):
            reads.append(key)
            return super().__getitem__(key)

        def get(self, key, default=None):
            reads.append(key)
            return super().get(key, default)

    release_candidate(monkeypatch)
    monkeypatch.setattr(config, "connected_apps_environment_released", lambda: True)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", MANIFEST)
    value = configure_connected_production_host(
        environment=TrackingEnvironment(environment),
        now=lambda: NOW,
    )
    assert value is request_activation.connected_request_activation_coordinator
    assert value is not None and value.expected_manifest_sha256 == MANIFEST
    assert "VERCEL_OIDC_TOKEN" not in reads
    assert all("CLIENT_SECRET" not in key for key in reads)
    assert set(reads) == {
        "CRUMP_CONNECTED_KMS_ENCRYPTED_ROOT_B64",
        "CRUMP_CONNECTED_HOST_CONFIGURATION_CIPHERTEXT",
        "VERCEL_DEPLOYMENT_ID",
        "VERCEL_GIT_COMMIT_SHA",
    }
    assert configure_connected_production_host(
        environment=OpaqueEnvironment(),
        now=lambda: NOW,
    ) is value


def test_released_bootstrap_failure_leaves_no_partial_activation(monkeypatch) -> None:
    release_candidate(monkeypatch)
    monkeypatch.setattr(config, "connected_apps_environment_released", lambda: True)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", MANIFEST)
    with pytest.raises(
        ConnectedHostBootstrapError,
        match="CONNECTED_HOST_BOOTSTRAP_NOT_READY",
    ) as failure:
        configure_connected_production_host(environment={}, now=lambda: NOW)
    assert repr(failure.value) == (
        "ConnectedHostBootstrapError('CONNECTED_HOST_BOOTSTRAP_NOT_READY')"
    )
    assert request_activation.connected_request_activation_coordinator is None


def test_released_bootstrap_refuses_unpinned_source_custody_without_partial_state(
    monkeypatch,
) -> None:
    keys = production_keys()
    environment = deployment_environment(encrypted_configuration(keys))
    release_candidate(monkeypatch)
    monkeypatch.setattr(config, "connected_apps_environment_released", lambda: True)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", MANIFEST)
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_PROJECT_NUMBER", "")
    with pytest.raises(
        ConnectedHostBootstrapError,
        match="CONNECTED_HOST_BOOTSTRAP_NOT_READY",
    ):
        configure_connected_production_host(environment=environment, now=lambda: NOW)
    assert request_activation.connected_request_activation_coordinator is None


def test_released_bootstrap_refuses_root_id_that_cannot_fit_every_domain(
    monkeypatch,
) -> None:
    release_candidate(monkeypatch)
    monkeypatch.setattr(config, "connected_apps_environment_released", lambda: True)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", MANIFEST)
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_ROOT_KEY_ID", "k" * 32)
    with pytest.raises(
        ConnectedHostBootstrapError,
        match="CONNECTED_HOST_BOOTSTRAP_NOT_READY",
    ):
        configure_connected_production_host(
            environment=OpaqueEnvironment(),
            now=lambda: NOW,
        )
    assert request_activation.connected_request_activation_coordinator is None


def test_source_contract_hashes_are_exact_and_distinct() -> None:
    assert re_full_sha(CONNECTED_DATABASE_CONTRACT_SHA256)
    assert re_full_sha(CONNECTED_PROVIDER_CONTRACT_SHA256)
    assert CONNECTED_DATABASE_CONTRACT_SHA256 != CONNECTED_PROVIDER_CONTRACT_SHA256


def re_full_sha(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
