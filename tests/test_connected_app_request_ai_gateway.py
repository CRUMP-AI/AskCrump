from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pickle

import httpx
import pytest

from backend.connected_app_chat_operator import ConnectedOperatorChatRequest
from backend.connected_app_delegated_responder import ConnectedOperatorDelegatedTextResponder
from backend.connected_app_kms import ConnectedVercelOIDCAssertion
from backend.connected_app_request_ai_gateway import (
    ConnectedRequestAIGatewayError,
    ConnectedRequestScopedAIGateway,
    ConnectedRequestScopedAIGatewayFactory,
)


TOKEN = "a" * 80 + "." + "b" * 80 + "." + "c" * 80
OWNER = "11111111-1111-4111-8111-111111111111"


class Database:
    def __init__(self, *, settle: bool = True) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.settle = settle

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        return self.settle if name == "settle_ai_gateway_cost_receipt" else True


def gateway(database: Database, transport: httpx.AsyncBaseTransport):
    return ConnectedRequestScopedAIGateway(
        assertion=ConnectedVercelOIDCAssertion(TOKEN),
        database=database,
        model="openai/gpt-oss-20b",
        provider="groq",
        deployment_id="dpl_12345678abcd",
        commit_sha="a" * 40,
        transport=transport,
    )


@pytest.mark.asyncio
async def test_request_oidc_gateway_is_fixed_bounded_zdr_and_cost_receipted() -> None:
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "model": "openai/gpt-oss-20b",
                "choices": [{"message": {"content": '{"disposition":"none"}'}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "prompt_tokens_details": {"cached_tokens": 3},
                },
                "providerMetadata": {
                    "gateway": {
                        "cost": "0.00012",
                        "routing": {
                            "finalProvider": "groq",
                            "planningReasoning": (
                                "groq satisfied the requested provider, no-training, "
                                "and zero-retention filters"
                            ),
                        },
                    }
                },
            },
        )

    database = Database()
    value = gateway(database, httpx.MockTransport(handler))
    result = await value.gateway_text(
        system="Return an exact connected plan.",
        prompt="Read my calendar.",
        max_tokens=512,
        timeout_seconds=10,
        user_id=OWNER,
        purpose="connected_app_plan",
    )
    assert result == '{"disposition":"none"}'
    assert len(observed) == 1
    request = observed[0]
    assert str(request.url) == "https://ai-gateway.vercel.sh/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    body = json.loads(request.content)
    assert body["providerOptions"] == {
        "gateway": {
            "only": ["groq"],
            "disallowPromptTraining": True,
            "zeroDataRetention": True,
        }
    }
    assert body["user"] == hashlib.sha256(
        b"askcrump.connected-ai-owner/v1\0" + OWNER.encode("ascii")
    ).hexdigest()
    assert OWNER not in request.content.decode("utf-8")
    assert [call[0] for call in database.calls] == [
        "claim_ai_gateway_cost_receipt",
        "settle_ai_gateway_cost_receipt",
    ]
    assert database.calls[0][1]["p_purpose"] == "planner"
    settled = database.calls[1][1]
    assert settled["p_input_tokens"] == 11
    assert settled["p_output_tokens"] == 7
    assert settled["p_cached_input_tokens"] == 3
    assert settled["p_gross_cost_usd"] == "0.00012"
    assert isinstance(settled["p_latency_ms"], int)
    assert 0 <= settled["p_latency_ms"] <= 600_000
    assert repr(value) == (
        "ConnectedRequestScopedAIGateway(authentication='request-oidc')"
    )
    assert TOKEN not in repr(value)
    with pytest.raises(TypeError):
        pickle.dumps(value)


@pytest.mark.asyncio
async def test_real_request_gateway_executes_delegated_response_on_chat_receipt_lane() -> None:
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "model": "openai/gpt-oss-20b",
                "choices": [{"message": {"content": "Email is digital mail."}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 5},
                "providerMetadata": {
                    "gateway": {
                        "cost": "0.00009",
                        "routing": {
                            "finalProvider": "groq",
                            "planningReasoning": "privacy filters satisfied",
                        },
                    }
                },
            },
        )

    database = Database()
    responder = ConnectedOperatorDelegatedTextResponder(
        gateway(database, httpx.MockTransport(handler))
    )
    result = await responder.respond(
        request=ConnectedOperatorChatRequest(
            owner_id=OWNER,
            session_id="22222222-2222-4222-8222-222222222222",
            chat_id="33333333-3333-4333-8333-333333333333",
            message_id="44444444-4444-4444-8444-444444444444",
            message="What does email mean?",
            time_zone="UTC",
        )
    )

    assert result == "Email is digital mail."
    assert len(observed) == 1
    body = json.loads(observed[0].content)
    assert body["tags"] == [
        "feature:connected-app-delegated-response",
        "tier:connected",
    ]
    assert database.calls[0][1]["p_purpose"] == "chat"
    assert database.calls[1][1]["p_status"] == "completed"


@pytest.mark.asyncio
async def test_gateway_rejects_redirect_or_unsettled_cost_without_returning_text() -> None:
    redirect_db = Database()
    redirect = gateway(
        redirect_db,
        httpx.MockTransport(
            lambda _request: httpx.Response(
                302,
                headers={"location": "https://evil.example/"},
            )
        ),
    )
    with pytest.raises(ConnectedRequestAIGatewayError):
        await redirect.gateway_text(
            system="system",
            prompt="prompt",
            max_tokens=128,
            timeout_seconds=5,
            user_id=OWNER,
            purpose="connected_app_plan",
        )
    assert [call[0] for call in redirect_db.calls] == [
        "claim_ai_gateway_cost_receipt",
        "settle_ai_gateway_cost_receipt",
    ]

    unsettled_db = Database(settle=False)
    unsettled = gateway(
        unsettled_db,
        httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={
                    "choices": [{"message": {"content": "must not escape"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "providerMetadata": {"gateway": {"cost": "0.01"}},
                },
            )
        ),
    )
    with pytest.raises(ConnectedRequestAIGatewayError):
        await unsettled.gateway_text(
            system="system",
            prompt="prompt",
            max_tokens=128,
            timeout_seconds=5,
            user_id=OWNER,
            purpose="connected_app_plan",
        )


@pytest.mark.asyncio
async def test_gateway_refuses_invalid_owner_purpose_or_oversized_prompt_before_rpc() -> None:
    database = Database()
    value = gateway(database, httpx.MockTransport(lambda _request: httpx.Response(500)))
    for changes in (
        {"user_id": "not-a-uuid"},
        {"purpose": "chat"},
        {"prompt": "x" * (64 * 1024 + 1)},
    ):
        arguments = {
            "system": "system",
            "prompt": "prompt",
            "max_tokens": 128,
            "timeout_seconds": 5,
            "user_id": OWNER,
            "purpose": "connected_app_plan",
        }
        arguments.update(changes)
        with pytest.raises(ConnectedRequestAIGatewayError):
            await value.gateway_text(**arguments)
    assert database.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    (
        httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "model": "openai/gpt-oss-20b",
                "choices": [{"message": {"content": "missing receipts"}}],
            },
        ),
        httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=(
                b'{"model":"openai/gpt-oss-20b",'
                b'"model":"openai/gpt-oss-20b",'
                b'"choices":[]}'
            ),
        ),
        httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b"x" * (64 * 1024 + 1),
        ),
    ),
)
async def test_gateway_fails_closed_on_incomplete_duplicate_or_oversized_response(
    response: httpx.Response,
) -> None:
    database = Database()
    value = gateway(database, httpx.MockTransport(lambda _request: response))
    with pytest.raises(ConnectedRequestAIGatewayError):
        await value.gateway_text(
            system="system",
            prompt="prompt",
            max_tokens=128,
            timeout_seconds=5,
            user_id=OWNER,
            purpose="connected_app_plan",
        )
    assert [call[0] for call in database.calls] == [
        "claim_ai_gateway_cost_receipt",
        "settle_ai_gateway_cost_receipt",
    ]
    assert database.calls[1][1]["p_status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "routing",
    (
        None,
        {},
        {"finalProvider": "other", "planningReasoning": "filters satisfied"},
        {"finalProvider": "groq", "planningReasoning": ""},
    ),
)
async def test_gateway_rejects_output_without_exact_privacy_routing_audit(
    routing: object,
) -> None:
    metadata: dict[str, object] = {"cost": "0.00001"}
    if routing is not None:
        metadata["routing"] = routing
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={
            "model": "openai/gpt-oss-20b",
            "choices": [{"message": {"content": "must not escape"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2},
            "providerMetadata": {"gateway": metadata},
        },
    )
    database = Database()
    value = gateway(database, httpx.MockTransport(lambda _request: response))
    with pytest.raises(ConnectedRequestAIGatewayError):
        await value.gateway_text(
            system="system",
            prompt="prompt",
            max_tokens=128,
            timeout_seconds=5,
            user_id=OWNER,
            purpose="connected_app_plan",
        )
    assert database.calls[-1][1]["p_status"] == "failed"
    assert database.calls[-1][1]["p_error_code"] == (
        "CONNECTED_REQUEST_AI_GATEWAY_INVALID_RESPONSE"
    )


def test_factory_and_source_refuse_serialization_and_ambient_authentication() -> None:
    database = Database()
    factory = ConnectedRequestScopedAIGatewayFactory(
        database=database,
        model="openai/gpt-oss-20b",
        provider="groq",
        deployment_id="dpl_12345678abcd",
        commit_sha="a" * 40,
    )
    assert "request-oidc" in repr(factory)
    assert TOKEN not in repr(factory)
    with pytest.raises(TypeError):
        pickle.dumps(factory)
    source = Path(
        ConnectedRequestScopedAIGateway.__module__.replace(".", "/") + ".py"
    )
    repository_source = Path(__file__).resolve().parents[1] / source
    text = repository_source.read_text(encoding="utf-8")
    assert "os.environ" not in text
    assert "os.getenv" not in text
    assert "AI_GATEWAY_API_KEY" not in text
