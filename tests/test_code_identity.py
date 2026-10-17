from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
import time
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest

from backend.code_identity import (
    CodeIdentityError,
    CodeIdentityVerifier,
    JWKS_URL,
    MAX_JWKS_BYTES,
    code_identity_token,
    verify_code_identity,
)


@pytest.fixture(scope="module")
def signing_keys():
    keys = [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]
    return keys


def policy_settings(**overrides):
    return SimpleNamespace(
        **{
            "code_oidc_issuer": "https://oidc.vercel.com/offline-team",
            "code_oidc_audience": "https://vercel.com/offline-team",
            "code_oidc_project_id": "prj_offline",
            "code_oidc_team_id": "team_offline",
            "code_oidc_environment": "production",
            "vercel_oidc_token": None,
            "code_workspace_enabled": True,
            "anthropic_api_key": "offline-unused-fixture",
            "anthropic_model": "explicit-offline-model",
            **overrides,
        }
    )


def claims(**overrides):
    now = int(time.time())
    return {
        "iss": "https://oidc.vercel.com/offline-team",
        "aud": "https://vercel.com/offline-team",
        "sub": "owner:offline-team:project:fixture:environment:production",
        "iat": now - 10, "nbf": now - 10, "exp": now + 3600,
        "owner_id": "team_offline", "project_id": "prj_offline",
        "environment": "production", **overrides,
    }


def token(key, *, payload=None, kid="current", headers=None):
    return jwt.encode(payload or claims(), key, algorithm="RS256", headers={"kid": kid, **(headers or {})})


def public_jwk(key, kid="current", **overrides):
    return {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
            "kid": kid, "alg": "RS256", "use": "sig", **overrides}


def offline_verifier(document, *, status=200):
    requests = []
    tick = [100.0]

    async def respond(request):
        requests.append(request)
        await asyncio.sleep(0)  # A real async transport: let sibling verifications run.
        assert str(request.url) == JWKS_URL
        assert request.method == "GET"
        assert "authorization" not in request.headers
        if isinstance(document, bytes):
            return httpx.Response(status, content=document)
        return httpx.Response(status, json=document)

    verifier = CodeIdentityVerifier(transport=httpx.MockTransport(respond), clock=lambda: tick[0])
    return verifier, requests, tick


@pytest.mark.asyncio
async def test_signed_identity_is_bound_and_returns_only_verified_projection(signing_keys):
    verifier, requests, _ = offline_verifier({"keys": [public_jwk(signing_keys[0])]})
    signed = token(signing_keys[0])
    identity = await verify_code_identity(signed, policy_settings(), verifier=verifier)
    assert asdict(identity) == {
        "project_id": "prj_offline", "team_id": "team_offline",
        "issuer": "https://oidc.vercel.com/offline-team",
        "audience": "https://vercel.com/offline-team", "environment": "production",
        "expires_at": claims()["exp"],
    }
    assert signed not in repr(identity)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_global_issuer_uses_same_fixed_jwks_and_custom_audience_is_pinned(signing_keys):
    verifier, requests, _ = offline_verifier({"keys": [public_jwk(signing_keys[0])]})
    signed = token(signing_keys[0], payload=claims(iss="https://oidc.vercel.com", aud="api://offline-code"))
    identity = await verify_code_identity(
        signed, policy_settings(code_oidc_issuer="https://oidc.vercel.com", code_oidc_audience="api://offline-code"),
        verifier=verifier,
    )
    assert identity.issuer == "https://oidc.vercel.com"
    assert str(requests[0].url) == JWKS_URL


INVALID_CLAIMS = [
    {"iss": "https://oidc.vercel.com/other"},
    {"iss": "https://attacker.invalid"},
    {"aud": "https://vercel.com/other"},
    {"aud": ["https://vercel.com/offline-team", "attacker"]},
    {"project_id": "prj_other"}, {"owner_id": "team_other"},
    {"environment": "preview"}, {"sub": ""},
    {"exp": 1}, {"nbf": 4_000_000_000}, {"iat": 4_000_000_000},
    {"exp": "not-a-time"}, {"iat": True},
    {"nbf": None}, {"project_id": None},
]


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", INVALID_CLAIMS)
async def test_signed_but_invalid_claims_fail_closed(signing_keys, overrides):
    verifier, _, _ = offline_verifier({"keys": [public_jwk(signing_keys[0])]})
    signed = token(signing_keys[0], payload=claims(**overrides))
    with pytest.raises(CodeIdentityError) as caught:
        await verify_code_identity(signed, policy_settings(), verifier=verifier)
    assert caught.value.code == "CODE_IDENTITY_INVALID"
    assert signed not in str(caught.value)


@pytest.mark.asyncio
async def test_forged_signature_and_missing_required_claims_fail(signing_keys):
    verifier, _, _ = offline_verifier({"keys": [public_jwk(signing_keys[0])]})
    with pytest.raises(CodeIdentityError):
        await verify_code_identity(token(signing_keys[1]), policy_settings(), verifier=verifier)
    for name in ("iss", "aud", "sub", "exp", "nbf", "iat", "project_id", "owner_id", "environment"):
        payload = claims(); del payload[name]
        with pytest.raises(CodeIdentityError):
            await verify_code_identity(token(signing_keys[0], payload=payload), policy_settings(), verifier=verifier)


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [
    {"kid": None}, {"kid": "x" * 129}, {"typ": "other"},
    {"jku": "https://attacker.invalid/keys"}, {"jwk": {"kty": "RSA"}},
    {"x5u": "https://attacker.invalid/cert"}, {"x5c": ["attacker"]},
    {"crit": ["custom"]}, {"b64": False},
])
async def test_attacker_key_headers_are_rejected_without_network(signing_keys, header):
    verifier, requests, _ = offline_verifier({"keys": [public_jwk(signing_keys[0])]})
    # PyJWT refuses non-string kid at encoding, so serialize that protected header ourselves.
    signed = token(signing_keys[0], headers={k: v for k, v in header.items() if k != "kid"})
    if "kid" in header:
        pieces = signed.split(".")
        pieces[0] = jwt.utils.base64url_encode(json.dumps({"alg": "RS256", "typ": "JWT", **header}).encode()).decode()
        signed = ".".join(pieces)
    with pytest.raises(CodeIdentityError):
        await verify_code_identity(signed, policy_settings(), verifier=verifier)
    assert requests == []


@pytest.mark.asyncio
async def test_none_hmac_and_oversized_tokens_never_fetch_keys(signing_keys):
    verifier, requests, _ = offline_verifier({"keys": [public_jwk(signing_keys[0])]})
    attempts = [
        jwt.encode(claims(), "", algorithm="none", headers={"kid": "current"}),
        jwt.encode(claims(), b"offline-attacker-not-a-provider-key", algorithm="HS256", headers={"kid": "current"}),
        "a" * 16_385, "not-a-jwt", "", None,
    ]
    for signed in attempts:
        with pytest.raises(CodeIdentityError):
            await verify_code_identity(signed, policy_settings(), verifier=verifier)
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name,value", [
    ("code_oidc_issuer", "https://oidc.vercel.com.attacker.invalid"),
    ("code_oidc_issuer", "https://oidc.vercel.com/team/../keys"),
    ("code_oidc_issuer", "https://oidc.vercel.com/team?x=1"),
    ("code_oidc_issuer", "http://oidc.vercel.com/team"),
    ("code_oidc_audience", "*"), ("code_oidc_project_id", "*"),
    ("code_oidc_team_id", ""), ("code_oidc_environment", "*"),
])
async def test_incomplete_or_unsafe_server_policy_cannot_fetch_keys(signing_keys, name, value):
    verifier, requests, _ = offline_verifier({"keys": [public_jwk(signing_keys[0])]})
    with pytest.raises(CodeIdentityError):
        await verify_code_identity(token(signing_keys[0]), policy_settings(**{name: value}), verifier=verifier)
    assert requests == []


@pytest.mark.asyncio
async def test_public_key_cache_is_single_flight_rotation_aware_and_never_caches_tokens(signing_keys):
    document = {"keys": [public_jwk(signing_keys[0])]}
    verifier, requests, tick = offline_verifier(document)
    signed = token(signing_keys[0])
    result = await asyncio.gather(*(verify_code_identity(signed, policy_settings(), verifier=verifier) for _ in range(20)))
    assert len(result) == 20 and len(requests) == 1
    with pytest.raises(CodeIdentityError):
        await verify_code_identity(token(signing_keys[0], payload=claims(exp=1)), policy_settings(), verifier=verifier)
    assert len(requests) == 1, "cache contains public keys, not accepted token decisions"
    for i in range(10):
        with pytest.raises(CodeIdentityError):
            await verify_code_identity(token(signing_keys[1], kid=f"unknown-{i}"), policy_settings(), verifier=verifier)
    assert len(requests) == 1, "unknown kid cannot force per-request key downloads"
    tick[0] += 31
    document["keys"] = [public_jwk(signing_keys[1], "rotated")]
    result = await verify_code_identity(token(signing_keys[1], kid="rotated"), policy_settings(), verifier=verifier)
    assert result.project_id == "prj_offline" and len(requests) == 2
    tick[0] += 301
    document["keys"] = []
    with pytest.raises(CodeIdentityError):
        await verify_code_identity(token(signing_keys[1], kid="rotated"), policy_settings(), verifier=verifier)
    assert len(requests) == 3, "expired keys cannot survive a failed refresh"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["duplicate", "private", "encryption", "operations", "many", "oversized", "redirect"])
async def test_jwks_size_key_type_and_ambiguity_limits(signing_keys, case):
    key = public_jwk(signing_keys[0]); document = {"keys": [key]}; status = 200
    if case == "duplicate": document["keys"].append(dict(key))
    if case == "private": key["d"] = "forbidden"
    if case == "encryption": key["use"] = "enc"
    if case == "operations": key["key_ops"] = ["encrypt"]
    if case == "many": document["keys"] = [{**key, "kid": f"k-{i}"} for i in range(33)]
    if case == "oversized": document = b" " * (MAX_JWKS_BYTES + 1)
    if case == "redirect": status = 302
    verifier, requests, _ = offline_verifier(document, status=status)
    with pytest.raises(CodeIdentityError):
        await verify_code_identity(token(signing_keys[0]), policy_settings(), verifier=verifier)
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [*INVALID_CLAIMS, "forged", "hmac", "none", "key-url"])
async def test_invalid_identity_cannot_create_charge_dispatch_or_provision(monkeypatch, signing_keys, overrides):
    from backend.routes import code as routes
    calls = []
    settings = policy_settings()
    verifier, _, _ = offline_verifier({"keys": [public_jwk(signing_keys[0])]})

    async def verify(signed, config):
        return await verify_code_identity(signed, config, verifier=verifier)

    async def authenticate(*_args):
        return SimpleNamespace(user={"id": "offline-user"})

    class Tripwire:
        def __getattr__(self, name):
            async def unexpected(*_args, **_kwargs):
                calls.append(name)
                raise AssertionError(f"Rejected workload reached {name}")
            return unexpected

    if overrides == "forged":
        signed = token(signing_keys[1])
    elif overrides == "hmac":
        signed = jwt.encode(claims(), b"offline-attacker-not-a-provider-key", algorithm="HS256", headers={"kid": "current"})
    elif overrides == "none":
        signed = jwt.encode(claims(), "", algorithm="none", headers={"kid": "current"})
    elif overrides == "key-url":
        signed = token(signing_keys[0], headers={"jku": "https://attacker.invalid/keys"})
    else:
        signed = token(signing_keys[0], payload=claims(**overrides))

    class Request:
        headers = {"x-vercel-oidc-token": signed}

        async def json(self):
            calls.append("body")
            return {"confirmed": True}

    monkeypatch.setattr(routes, "settings", settings)
    monkeypatch.setattr(routes, "authenticate_request", authenticate)
    monkeypatch.setattr(routes, "verify_code_identity", verify)
    monkeypatch.setattr(routes, "code_tasks", Tripwire())
    monkeypatch.setattr(routes, "features", Tripwire())
    assert (await routes.create_code_task("offline-project", Request())).status_code == 503
    assert (await routes.run_code_task("offline-task", Request())).status_code == 503
    assert calls == []


@pytest.mark.asyncio
async def test_header_presence_is_not_configuration_and_invalid_header_cannot_use_good_env_token(monkeypatch, signing_keys):
    from backend.routes import code as routes
    signed = token(signing_keys[0]); settings = policy_settings(vercel_oidc_token=signed)
    verifier, requests, _ = offline_verifier({"keys": [public_jwk(signing_keys[0])]})

    async def verify(value, config):
        return await verify_code_identity(value, config, verifier=verifier)

    monkeypatch.setattr(routes, "settings", settings)
    monkeypatch.setattr(routes, "verify_code_identity", verify)
    for suffix, value in {
        "MODEL": settings.anthropic_model,
        "INPUT_USD_MICROS_PER_MILLION": "3000000",
        "OUTPUT_USD_MICROS_PER_MILLION": "15000000",
        "MAX_INPUT_BYTES": "100000", "MAX_OUTPUT_TOKENS": "6000",
        "CALL_USD_MICROS": "500000", "RUN_USD_MICROS": "2000000",
        "ACCOUNT_DAILY_USD_MICROS": "10000000", "GLOBAL_DAILY_USD_MICROS": "20000000",
    }.items():
        monkeypatch.setenv("CODE_PROVIDER_" + suffix, value)
    assert not await routes._configured(SimpleNamespace(headers={"x-vercel-oidc-token": "forged"}))
    assert not await routes._configured(SimpleNamespace(headers={"x-vercel-oidc-token": ""}))
    assert requests == []
    assert await routes._configured(SimpleNamespace(headers={}))
    settings.code_workspace_enabled = False
    assert not await routes._configured(SimpleNamespace(headers={"x-vercel-oidc-token": signed}))
    assert len(requests) == 1
    assert code_identity_token(settings, {"x-vercel-oidc-token": ""}) == ""


def test_trust_policy_configuration_never_opens_either_release_stop(monkeypatch):
    from backend import config
    monkeypatch.setenv("CRUMP_ENABLE_CODE_WORKSPACE", "true")
    for name, value in {
        "ISSUER": "https://oidc.vercel.com/offline-team",
        "AUDIENCE": "https://vercel.com/offline-team", "PROJECT_ID": "prj_offline",
        "TEAM_ID": "team_offline", "ENVIRONMENT": "production",
    }.items():
        monkeypatch.setenv("CODE_OIDC_" + name, value)
    config.get_settings.cache_clear()
    try:
        settings = config.get_settings()
        assert settings.code_oidc_project_id == "prj_offline"
        assert settings.code_oidc_team_id == "team_offline"
        assert settings.code_oidc_environment == "production"
        assert config.CODE_WORKSPACE_PUBLIC_RELEASED is False
        assert settings.code_workspace_enabled is False
    finally:
        config.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_jwks_fetch_yields_to_other_work_and_enforces_total_deadline(monkeypatch, signing_keys):
    from backend import code_identity
    entered = asyncio.Event()
    heartbeat = asyncio.Event()

    async def stuck_transport(_request):
        entered.set()
        await asyncio.sleep(60)
        raise AssertionError("Transport must be cancelled by the total deadline")

    async def other_work():
        await entered.wait()
        await asyncio.sleep(0)
        heartbeat.set()

    monkeypatch.setattr(code_identity, "JWKS_FETCH_TIMEOUT_SECONDS", .05)
    verifier = CodeIdentityVerifier(transport=httpx.MockTransport(stuck_transport))
    sibling = asyncio.create_task(other_work())
    with pytest.raises(CodeIdentityError) as caught:
        await verify_code_identity(token(signing_keys[0]), policy_settings(), verifier=verifier)
    await sibling
    assert heartbeat.is_set(), "key retrieval must never block unrelated async requests"
    assert caught.value.code == "CODE_IDENTITY_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["symmetric", "wrong-algorithm", "weak-rsa", "malformed"])
async def test_jwks_never_accepts_symmetric_weak_or_malformed_keys(signing_keys, kind):
    key = public_jwk(signing_keys[0])
    if kind == "symmetric": key = {"kty": "oct", "kid": "current", "k": "ignored"}
    if kind == "wrong-algorithm": key["alg"] = "HS256"
    if kind == "weak-rsa": key = public_jwk(rsa.generate_private_key(public_exponent=65537, key_size=1024))
    if kind == "malformed": key["n"] = "not-valid-rsa-material"
    verifier, _, _ = offline_verifier({"keys": [key]})
    with pytest.raises(CodeIdentityError):
        await verify_code_identity(token(signing_keys[0]), policy_settings(), verifier=verifier)
