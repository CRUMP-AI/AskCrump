from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend.ai_service import AIService
from backend.feature_service import FeatureAccessError, FeatureService
from backend.intelligence_service import DEFAULT_PREFERENCES, IntelligenceService
from backend.routes import chat as chat_routes


ROOT = Path(__file__).resolve().parents[1]
CLIENT = TestClient(app_module.app)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_saved_assistant_name_is_an_explicit_conversational_identity():
    service = AIService(SimpleNamespace())
    prompt = service._system_prompt({"assistantName": "Echo", "currentDateTime": {}})

    assert 'Your display name is "Echo"' in prompt
    assert "recognize it naturally and respond as that" in prompt
    assert 'Do not correct the user back to "Crump"' in prompt
    assert 'Keep "Ask Crump" as the product name' in prompt


def test_think_longer_is_entitled_only_for_paid_or_internal_tiers():
    service = FeatureService(SimpleNamespace())
    free = {"id": "free", "subscription_tier": "free", "subscription_status": "inactive"}
    professional = {
        "id": "pro",
        "subscription_tier": "professional",
        "subscription_status": "active",
    }
    enterprise = {
        "id": "enterprise",
        "subscription_tier": "enterprise",
        "subscription_status": "trialing",
    }
    expired = {
        "id": "expired",
        "subscription_tier": "professional",
        "subscription_status": "inactive",
    }
    internal = {"id": "internal", "internal_tier": "professional"}

    assert service.entitled(free, "think_longer") is False
    assert service.entitled(professional, "think_longer") is True
    assert service.entitled(enterprise, "think_longer") is True
    assert service.entitled(expired, "think_longer") is False
    assert service.entitled(internal, "think_longer") is True


def test_chat_api_rejects_a_browser_attempt_to_unlock_think_longer(monkeypatch):
    class DeniedFeatures:
        def entitled(self, _user, code):
            assert code == "think_longer"
            return False

        async def require_tier(self, _user, code):
            raise FeatureAccessError(
                "Think longer requires a Professional plan.",
                "SUBSCRIPTION_REQUIRED",
                403,
                "professional",
            )

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={"id": "free-user", "subscription_tier": "free"},
            session={"id": "session"},
            token="token",
        )

    monkeypatch.setattr(chat_routes, "features", DeniedFeatures())
    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)

    response = CLIENT.post(
        "/api/chat",
        json={"message": "Analyze this carefully", "intelligenceMode": "deep"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "SUBSCRIPTION_REQUIRED"
    assert response.json()["requiredTier"] == "professional"


@pytest.mark.asyncio
async def test_auto_mode_never_silently_uses_paid_multi_pass_work_for_free_users():
    service = IntelligenceService(
        db=SimpleNamespace(),
        ai=SimpleNamespace(),
        settings=SimpleNamespace(),
    )
    service.get_preferences = AsyncMock(return_value=dict(DEFAULT_PREFERENCES))
    service.infer_creation_intent = AsyncMock(return_value=None)
    service.retrieve_memories = AsyncMock(return_value=[])
    service._make_plan = AsyncMock(return_value="- inspect\n- verify")
    message = (
        "Think hard and design a comprehensive architecture. Compare the tradeoffs, "
        "implement the approach, debug likely failures, and create a thorough verification plan. "
        * 12
    )

    free = await service.prepare(
        "free-user",
        {"message": message, "intelligenceMode": "auto"},
        allow_think_longer=False,
    )
    paid = await service.prepare(
        "paid-user",
        {"message": message, "intelligenceMode": "auto"},
        allow_think_longer=True,
    )

    assert free.effective_mode == "balanced"
    assert free.planner_used is False
    assert free.payload["responseEffort"] == "standard"
    assert paid.effective_mode == "deep"
    assert paid.planner_used is True
    assert paid.payload["responseEffort"] == "high"


def test_frontend_identity_paid_mode_and_navigation_contracts():
    app = read("public/app.js")
    intelligence = read("public/crump-4.4.js")
    legal = read("public/legal.html")

    assert "window.getAssistantName" in app
    assert "input.placeholder = `Message ${name}`" in app
    assert "crump:assistant-name-changed" in app
    assert "modeLabel(mode)" in intelligence
    assert "Think longer" in intelligence
    assert "entitlements.thinkLonger" in intelligence
    assert "showBillingCenter?.({ plan: 'professional' })" in intelligence
    assert "closeConversationMenu();" in app
    assert "menuBtn.setAttribute('aria-expanded', 'false')" in app
    assert '<a class="brand" href="/app" aria-label="Return to Ask Crump">' in legal
