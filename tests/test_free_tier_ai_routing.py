import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.ai_service import AIService, AIServiceError
from backend.feature_service import FeatureService
from backend.intelligence_service import IntelligenceService


def _settings(**overrides):
    values = {
        "ai_gateway_enabled": True,
        "ai_gateway_api_key": "gateway-test-token",
        "vercel_oidc_token": None,
        "ai_gateway_free_model": "openai/gpt-oss-20b",
        "ai_gateway_free_provider": "groq",
        "ai_gateway_free_max_history_chars": 40_000,
        "ai_gateway_free_max_input_chars": 80_000,
        "anthropic_api_key": "anthropic-test-token",
        "anthropic_model": "claude-test",
        "max_history_chars": 50_000,
        "max_history_messages": 50,
        "brave_api_key": None,
        "openweather_api_key": None,
        "web_search_enabled": False,
        "environment": "development",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeAsyncClient:
    calls = []
    response = httpx.Response(200, json={})

    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, *, headers, json):
        type(self).calls.append({"url": url, "headers": headers, "json": json})
        return type(self).response


@pytest.fixture(autouse=True)
def _reset_fake_client():
    FakeAsyncClient.calls = []
    FakeAsyncClient.response = httpx.Response(200, json={})


@pytest.mark.asyncio
async def test_free_chat_uses_hard_allowlisted_gateway_without_anthropic_fallback(monkeypatch):
    from backend import ai_service as ai_module

    FakeAsyncClient.response = httpx.Response(
        200,
        json={
            "model": "openai/gpt-oss-20b",
            "choices": [{"message": {"content": "Low-cost answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 3},
        },
    )
    monkeypatch.setattr(ai_module.httpx, "AsyncClient", FakeAsyncClient)
    service = AIService(_settings())

    result = await service.chat({
        "message": "Help me organize this project.",
        "history": [],
        "assistantName": "Crump",
        "user": {"id": "free-user", "name": "Tester"},
        "_userTier": "free",
    })

    assert result["response"] == "Low-cost answer"
    assert result["provider"] == "vercel-ai-gateway"
    assert len(FakeAsyncClient.calls) == 1
    call = FakeAsyncClient.calls[0]
    assert call["url"] == AIService.AI_GATEWAY_URL
    assert call["json"]["model"] == "openai/gpt-oss-20b"
    assert call["json"]["providerOptions"]["gateway"] == {
        "only": ["groq"],
        "disallowPromptTraining": True,
        "zeroDataRetention": True,
    }
    assert "user" not in call["json"]
    assert "tier:free" in call["json"]["tags"]
    assert call["json"]["messages"][0]["role"] == "system"
    assert "free-user" not in json.dumps(call["json"])
    assert "Tester" not in json.dumps(call["json"])


@pytest.mark.asyncio
async def test_paid_chat_keeps_the_premium_anthropic_route(monkeypatch):
    from backend import ai_service as ai_module

    FakeAsyncClient.response = httpx.Response(
        200,
        json={
            "model": "claude-test",
            "content": [{"type": "text", "text": "Premium answer"}],
            "usage": {"input_tokens": 8, "output_tokens": 3},
            "stop_reason": "end_turn",
        },
    )
    monkeypatch.setattr(ai_module.httpx, "AsyncClient", FakeAsyncClient)
    service = AIService(_settings())

    result = await service.chat({
        "message": "Analyze the strategy.",
        "history": [],
        "assistantName": "Crump",
        "user": {"id": "paid-user", "name": "Tester"},
        "_userTier": "professional",
    })

    assert result["response"] == "Premium answer"
    assert len(FakeAsyncClient.calls) == 1
    assert FakeAsyncClient.calls[0]["url"] == "https://api.anthropic.com/v1/messages"
    assert FakeAsyncClient.calls[0]["headers"]["x-api-key"] == "anthropic-test-token"
    assert "paid-user" not in json.dumps(FakeAsyncClient.calls[0]["json"])
    assert "Tester" not in json.dumps(FakeAsyncClient.calls[0]["json"])


@pytest.mark.asyncio
async def test_gateway_rejects_provider_outside_current_consent_registry_before_network():
    service = AIService(_settings(ai_gateway_free_provider="together"))

    with pytest.raises(AIServiceError) as captured:
        await service.gateway_text(
            system="Route safely.",
            prompt="Do not send this.",
            max_tokens=512,
            timeout_seconds=30,
            user_id="must-not-be-forwarded",
            purpose="consent-registry-test",
        )

    assert captured.value.code == "AI_GATEWAY_PROVIDER_NOT_CONSENTED"
    assert FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_free_gateway_budget_error_never_retries_on_anthropic(monkeypatch):
    from backend import ai_service as ai_module

    FakeAsyncClient.response = httpx.Response(
        402,
        json={"error": {"message": "credits exhausted"}},
    )
    monkeypatch.setattr(ai_module.httpx, "AsyncClient", FakeAsyncClient)
    service = AIService(_settings())

    with pytest.raises(AIServiceError) as captured:
        await service.chat({
            "message": "Hello",
            "user": {"id": "free-user"},
            "_userTier": "free",
        })

    assert captured.value.code == "FREE_AI_BUDGET"
    assert len(FakeAsyncClient.calls) == 1
    assert FakeAsyncClient.calls[0]["url"] == AIService.AI_GATEWAY_URL


@pytest.mark.asyncio
async def test_free_chat_trims_old_history_before_it_reaches_the_gateway(monkeypatch):
    from backend import ai_service as ai_module

    FakeAsyncClient.response = httpx.Response(
        200,
        json={
            "model": "openai/gpt-oss-20b",
            "choices": [{"message": {"content": "Bounded answer"}, "finish_reason": "stop"}],
        },
    )
    monkeypatch.setattr(ai_module.httpx, "AsyncClient", FakeAsyncClient)
    service = AIService(_settings())

    await service.chat({
        "message": "Current request",
        "history": [
            {"role": "user", "content": "a" * 30_000},
            {"role": "assistant", "content": "b" * 30_000},
        ],
        "user": {"id": "free-user"},
        "_userTier": "free",
    })

    messages = FakeAsyncClient.calls[0]["json"]["messages"]
    assert not any(item.get("content") == "a" * 30_000 for item in messages)
    assert any(item.get("content") == "b" * 30_000 for item in messages)


@pytest.mark.asyncio
async def test_free_creation_router_uses_gateway_and_never_anthropic():
    ai = AIService(_settings())
    ai.gateway_text = AsyncMock(return_value=json.dumps({
        "kind": "document",
        "stage": "execute",
        "confidence": 0.9,
        "brief": "Create a project report for leadership.",
        "question": "",
        "title": "",
        "format": "docx",
    }))
    service = IntelligenceService(db=SimpleNamespace(), ai=ai, settings=_settings())
    service._anthropic_text = AsyncMock(return_value=None)

    intent = await service.infer_creation_intent(
        "Create a project report for leadership as a Word document.",
        [],
        user_tier="free",
        user_id="free-user",
    )

    assert intent and intent["kind"] == "document"
    ai.gateway_text.assert_awaited_once()
    service._anthropic_text.assert_not_awaited()


def test_visual_analysis_requires_a_paid_plan():
    service = FeatureService(SimpleNamespace())

    assert not service.entitled({"id": "free", "subscription_tier": "free"}, "visual_analysis")
    assert service.entitled({
        "id": "paid",
        "subscription_tier": "professional",
        "subscription_status": "active",
    }, "visual_analysis")


class ReceiptDB:
    def __init__(self, *, claim=True, settle=True):
        self.claim = claim
        self.settle = settle
        self.calls = []

    async def rpc(self, name, payload):
        self.calls.append((name, payload))
        return self.claim if name == "claim_ai_gateway_cost_receipt" else self.settle


def _production_env(monkeypatch):
    monkeypatch.setenv("VERCEL_DEPLOYMENT_ID", "dpl_1234567890abcdef")
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "a" * 40)


@pytest.mark.asyncio
async def test_gateway_cost_receipt_captures_helper_usage_and_actual_cost(monkeypatch):
    from backend import ai_service as ai_module

    _production_env(monkeypatch)
    FakeAsyncClient.response = httpx.Response(
        200,
        json={
            "model": "openai/gpt-oss-20b",
            "choices": [{"message": {"content": "Route it"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 21,
                "completion_tokens": 7,
                "prompt_tokens_details": {"cached_tokens": 3},
            },
            "providerMetadata": {"gateway": {"cost": "0.0000042"}},
        },
    )
    monkeypatch.setattr(ai_module.httpx, "AsyncClient", FakeAsyncClient)
    db = ReceiptDB()
    service = AIService(_settings(environment="production"), db)

    result = await service.gateway_text(
        system="Route safely.",
        prompt="Create a document.",
        max_tokens=512,
        timeout_seconds=30,
        user_id="must-not-be-stored",
        purpose="creation-router",
    )

    assert result == "Route it"
    assert [name for name, _ in db.calls] == [
        "claim_ai_gateway_cost_receipt",
        "settle_ai_gateway_cost_receipt",
    ]
    claim = db.calls[0][1]
    settled = db.calls[1][1]
    assert claim["p_purpose"] == "creation-intent"
    assert claim["p_authentication_lane"] == "api-key-attributed"
    assert claim["p_deployment_id"] == "dpl_1234567890abcdef"
    assert claim["p_commit_sha"] == "a" * 40
    assert "user" not in " ".join(claim).lower()
    assert settled["p_status"] == "completed"
    assert settled["p_input_tokens"] == 21
    assert settled["p_output_tokens"] == 7
    assert settled["p_cached_input_tokens"] == 3
    assert settled["p_gross_cost_usd"] == "0.0000042"
    assert settled["p_usage_receipt_complete"] is True
    assert settled["p_cost_receipt_complete"] is True
    assert "feature:creation-intent" in FakeAsyncClient.calls[0]["json"]["tags"]
    assert "user" not in FakeAsyncClient.calls[0]["json"]
    assert "must-not-be-stored" not in json.dumps(FakeAsyncClient.calls[0]["json"])


@pytest.mark.asyncio
async def test_production_claim_failure_prevents_unobserved_gateway_spend(monkeypatch):
    from backend import ai_service as ai_module

    _production_env(monkeypatch)
    monkeypatch.setattr(ai_module.httpx, "AsyncClient", FakeAsyncClient)
    service = AIService(_settings(environment="production"), ReceiptDB(claim=False))

    with pytest.raises(AIServiceError) as captured:
        await service.chat({
            "message": "Hello",
            "user": {"id": "free-user"},
            "_userTier": "free",
        })

    assert captured.value.code == "FREE_AI_OBSERVABILITY_UNAVAILABLE"
    assert FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_missing_gateway_cost_is_visible_and_fails_closed(monkeypatch):
    from backend import ai_service as ai_module

    _production_env(monkeypatch)
    FakeAsyncClient.response = httpx.Response(
        200,
        json={
            "model": "openai/gpt-oss-20b",
            "choices": [{"message": {"content": "Answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        },
    )
    monkeypatch.setattr(ai_module.httpx, "AsyncClient", FakeAsyncClient)
    db = ReceiptDB()
    service = AIService(_settings(environment="production"), db)

    assert (await service.chat({
        "message": "Hello",
        "user": {"id": "free-user"},
        "_userTier": "free",
    }))["response"] == "Answer"

    settled = db.calls[1][1]
    assert settled["p_usage_receipt_complete"] is True
    assert settled["p_cost_receipt_complete"] is False
    assert settled["p_gross_cost_usd"] is None


@pytest.mark.asyncio
async def test_rate_limit_is_settled_as_failed_subset(monkeypatch):
    from backend import ai_service as ai_module

    _production_env(monkeypatch)
    FakeAsyncClient.response = httpx.Response(
        429,
        json={"error": {"message": "rate limited"}},
    )
    monkeypatch.setattr(ai_module.httpx, "AsyncClient", FakeAsyncClient)
    db = ReceiptDB()
    service = AIService(_settings(environment="production"), db)

    with pytest.raises(AIServiceError) as captured:
        await service.chat({
            "message": "Hello",
            "user": {"id": "free-user"},
            "_userTier": "free",
        })

    assert captured.value.code == "FREE_AI_RATE_LIMIT"
    assert db.calls[1][1]["p_status"] == "rate_limited"
    assert db.calls[1][1]["p_error_code"] == "FREE_AI_RATE_LIMIT"
