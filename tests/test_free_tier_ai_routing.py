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
    }
    assert call["json"]["user"] == "free-user"
    assert "tier:free" in call["json"]["tags"]
    assert call["json"]["messages"][0]["role"] == "system"


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
