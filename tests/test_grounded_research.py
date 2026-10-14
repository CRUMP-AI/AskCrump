from types import SimpleNamespace
from unittest.mock import AsyncMock
from pathlib import Path

import httpx
import pytest

from backend.ai_service import AIService, AIServiceError
from backend.intelligence_service import IntelligenceService, PreparedRequest
from backend.product53_hooks import feature_for_request


EVIDENCE = (
    "[1] Primary source\n"
    "URL: https://example.com/primary\n"
    "Summary: The verified release happened on October 14."
)
ROOT = Path(__file__).resolve().parents[1]


def settings(**overrides):
    values = {
        "ai_gateway_enabled": False,
        "anthropic_api_key": "anthropic-test-token",
        "anthropic_model": "claude-test",
        "max_history_chars": 50_000,
        "max_history_messages": 50,
        "brave_api_key": "brave-test-token",
        "openweather_api_key": "weather-test-token",
        "web_search_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ProviderClient:
    calls = []

    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, *, headers, json):
        type(self).calls.append({"url": url, "headers": headers, "json": json})
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "model": "claude-test",
                "content": [{"type": "text", "text": "Grounded answer [1]"}],
                "usage": {"input_tokens": 10, "output_tokens": 4},
                "stop_reason": "end_turn",
            },
        )


class SearchClient:
    calls = []

    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url, *, params, headers):
        type(self).calls.append({"url": url, "params": params, "headers": headers})
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "web": {
                    "results": [
                        {
                            "title": "Unsafe script",
                            "url": "javascript:alert(1)",
                            "description": "Must never enter model context.",
                        },
                        {
                            "title": "Credential URL",
                            "url": "https://user:password@example.com/private",
                            "description": "Must never enter model context.",
                        },
                        {
                            "title": "Primary [source](https://evil.example) <script> `code`",
                            "url": "https://example.com/primary#tracking-fragment",
                            "description": "Verified source summary.",
                        },
                    ]
                }
            },
        )


@pytest.fixture(autouse=True)
def reset_clients():
    ProviderClient.calls = []
    SearchClient.calls = []


@pytest.mark.asyncio
async def test_research_fails_closed_when_live_evidence_is_unavailable():
    service = AIService(settings())
    service.search_web = AsyncMock(return_value=None)

    with pytest.raises(AIServiceError) as captured:
        await service.chat({
            "message": "What is the latest verified release? Cite sources.",
            "_userTier": "professional",
            "_externalLookupPolicy": {"search": True, "weather": False},
        })

    assert captured.value.code == "RESEARCH_EVIDENCE_UNAVAILABLE"
    assert captured.value.status_code == 503
    assert captured.value.retryable is True
    service.search_web.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_research_carries_bounded_request_scoped_evidence(monkeypatch):
    from backend import ai_service as ai_module

    monkeypatch.setattr(ai_module.httpx, "AsyncClient", ProviderClient)
    service = AIService(settings())
    service.search_web = AsyncMock(return_value=EVIDENCE)

    result = await service.chat({
        "message": "What is the latest verified release? Cite sources.",
        "_userTier": "professional",
        "_externalLookupPolicy": {"search": True, "weather": False},
    })

    assert result[AIService.GROUNDING_EVIDENCE_KEY] == EVIDENCE
    assert len(result[AIService.GROUNDING_EVIDENCE_KEY]) <= AIService.MAX_GROUNDING_EVIDENCE_CHARS
    assert EVIDENCE in ProviderClient.calls[0]["json"]["system"]
    assert "Sources\n- [1] Primary source — https://example.com/primary" in result["response"]


@pytest.mark.asyncio
async def test_external_search_query_is_minimized_and_attachment_cue_is_removed(monkeypatch):
    from backend import ai_service as ai_module

    monkeypatch.setattr(ai_module.httpx, "AsyncClient", SearchClient)
    service = AIService(settings())
    query = (
        "Compare Ask Crump with current competitors. "
        + ("a" * 450)
        + " PRIVATE_MIDDLE_MATERIAL "
        + ("b" * 4_000)
        + " Cite current primary sources. "
        + "[Current attachment received: confidential-plan.pdf. Do not send this cue.]"
    )

    result = await service.search_web(query)

    sent = SearchClient.calls[0]["params"]["q"]
    assert result and "Primary source script code" in result
    assert "evil.example" not in result
    assert "javascript:" not in result
    assert "password" not in result
    assert "#tracking-fragment" not in result
    assert result.startswith("[1] Primary source")
    assert len(sent) <= AIService.MAX_SEARCH_QUERY_CHARS
    assert sent.startswith("Compare Ask Crump")
    assert sent.endswith("Cite current primary sources.")
    assert "PRIVATE_MIDDLE_MATERIAL" not in sent
    assert "Current attachment received" not in sent


def test_sources_tail_is_canonical_safe_and_idempotent():
    model_answer = (
        "The verified release happened on October 14 [01], not later [9] or [999], "
        "not according to [made-up], while [2026] remains ordinary bracketed text.\n\n"
        "### Sources\n"
        "- [1] Invented mirror — https://invented.example/release\n"
        "- [9] Unsafe — javascript:alert(1)"
    )

    canonical = AIService.ensure_verifiable_sources(model_answer, EVIDENCE)

    assert "[9]" not in canonical
    assert "[999]" not in canonical
    assert "[01]" not in canonical
    assert "[1]" in canonical
    assert "[made-up]" not in canonical
    assert "[2026]" in canonical
    assert "invented.example" not in canonical
    assert "javascript:" not in canonical
    assert canonical.count("Sources\n") == 1
    assert canonical.endswith(
        "Sources\n- [1] Primary source — https://example.com/primary"
    )
    assert AIService.ensure_verifiable_sources(canonical, EVIDENCE) == canonical


def test_canonical_source_title_cannot_inject_markdown_html_or_a_second_url():
    hostile_evidence = (
        "[1] Trusted [label](https://evil.example) <img> `code`\n"
        "URL: https://example.com/actual\n"
        "Summary: Verified."
    )

    canonical = AIService.ensure_verifiable_sources("Verified [1].", hostile_evidence)

    assert "evil.example" not in canonical
    assert "<img>" not in canonical
    assert "`" not in canonical
    assert canonical.endswith(
        "Sources\n- [1] Trusted label img code — https://example.com/actual"
    )


def test_grounding_bundle_contains_only_complete_source_records():
    records = []
    for number in range(1, 9):
        records.append(
            f"[{number}] {'T' * 250}\n"
            f"URL: https://example.com/{number}/{'u' * 1750}\n"
            f"Summary: {'S' * 700}"
        )

    bundle = AIService._grounding_evidence_bundle("\n\n".join(records))

    assert bundle
    assert len(bundle) <= AIService.MAX_GROUNDING_EVIDENCE_CHARS
    assert bundle.count("Summary: ") == len(AIService._evidence_sources(bundle))
    assert bundle.endswith("S" * 700)
    assert "[8]" not in bundle


async def prepared_request(*, auto_tools: bool, payload: dict) -> PreparedRequest:
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service.get_preferences = AsyncMock(return_value={
        "intelligence_mode": "auto",
        "memory_enabled": False,
        "auto_learn": False,
        "auto_tools": auto_tools,
        "verification_level": "auto",
    })
    service.infer_creation_intent = AsyncMock(return_value=None)
    return await service.prepare("user-1", payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("auto_tools", "payload", "expected"),
    [
        (
            False,
            {"message": "What is the latest release?", "needsSearch": True, "toolMode": "auto"},
            False,
        ),
        (
            False,
            {"message": "Compare the products.", "requestedTool": "web", "toolMode": "manual"},
            True,
        ),
        (
            True,
            {"message": "What is the latest release?", "toolMode": "manual"},
            False,
        ),
        (
            True,
            {"message": "What is the latest release?", "toolMode": "auto"},
            True,
        ),
    ],
)
async def test_prepare_makes_external_lookup_policy_server_authoritative(
    auto_tools, payload, expected
):
    payload = {
        **payload,
        "_externalLookupPolicy": {"search": True, "weather": True},
        "needsWeather": True,
    }

    prepared = await prepared_request(auto_tools=auto_tools, payload=payload)

    assert prepared.payload["_externalLookupPolicy"]["search"] is expected
    assert (prepared.payload.get("needsSearch") is True) is expected
    assert prepared.payload["_externalLookupPolicy"]["weather"] is False
    assert "needsWeather" not in prepared.payload


@pytest.mark.asyncio
async def test_ai_service_does_not_recompute_lookup_when_server_policy_denies_it(monkeypatch):
    from backend import ai_service as ai_module

    monkeypatch.setattr(ai_module.httpx, "AsyncClient", ProviderClient)
    service = AIService(settings())
    service.search_web = AsyncMock(side_effect=AssertionError("lookup must stay off"))

    result = await service.chat({
        "message": "What is the latest verified release?",
        "_userTier": "professional",
        "_externalLookupPolicy": {"search": False, "weather": False},
    })

    assert result["response"] == "Grounded answer [1]"
    assert AIService.GROUNDING_EVIDENCE_KEY not in result
    service.search_web.assert_not_awaited()


@pytest.mark.asyncio
async def test_weather_fails_closed_when_current_observation_is_unavailable():
    service = AIService(settings())
    service.weather = AsyncMock(return_value=None)

    with pytest.raises(AIServiceError) as captured:
        await service.chat({
            "message": "What is the weather in Savannah today?",
            "_userTier": "professional",
            "_externalLookupPolicy": {"search": False, "weather": True},
        })

    assert captured.value.code == "WEATHER_EVIDENCE_UNAVAILABLE"
    assert captured.value.status_code == 503
    assert captured.value.retryable is True
    service.weather.assert_awaited_once()


def test_research_charge_uses_the_same_authoritative_policy_as_execution():
    media = SimpleNamespace(
        is_image_request=lambda *_args: False,
        is_edit_request=lambda *_args: False,
        has_visual_files=lambda *_args: False,
    )
    ai = AIService(settings())
    denied, _ = feature_for_request(
        payload={
            "message": "What is the latest release?",
            "_externalLookupPolicy": {"search": False, "weather": False},
        },
        file_rows=[],
        media=media,
        ai=ai,
    )
    allowed, _ = feature_for_request(
        payload={
            "message": "Compare the products.",
            "requestedTool": "web",
            "_externalLookupPolicy": {"search": True, "weather": False},
        },
        file_rows=[],
        media=media,
        ai=ai,
    )

    assert denied is None
    assert allowed == "research"


def test_web_tool_selection_and_launchpad_use_the_explicit_retry_safe_marker():
    composer = (ROOT / "public" / "crump-5.0.js").read_text(encoding="utf-8")
    launchpad = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    route = (ROOT / "backend" / "routes" / "chat.py").read_text(encoding="utf-8")
    sanitizer = (ROOT / "backend" / "crump52_patches.py").read_text(encoding="utf-8")

    assert "body.requestedTool = 'web'" in composer
    assert "{requestedTool:'web'}" in composer
    assert "body.needsSearch = true" not in composer
    assert "{needsSearch:true}" not in composer
    assert "crump:requested-tool" in launchpad
    assert "state.tool = 'web'" in composer
    assert "'requestedTool'" in route
    assert '"requestedTool"' in sanitizer


@pytest.mark.asyncio
async def test_auto_reviewer_receives_evidence_and_strips_it_from_user_result():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service._model_text = AsyncMock(return_value="OK")
    prepared = PreparedRequest(
        payload={"user": {"id": "user-1"}},
        requested_mode="auto",
        effective_mode="balanced",
        verification_level="auto",
        route="web",
    )

    updated, verifier_used = await service.verify_answer(
        prepared=prepared,
        question="What is the latest verified release?",
        result={
            "response": "The release happened on October 14 [1].",
            AIService.GROUNDING_EVIDENCE_KEY: EVIDENCE,
        },
    )

    assert verifier_used is True
    assert AIService.GROUNDING_EVIDENCE_KEY not in updated
    call = service._model_text.await_args.kwargs
    assert EVIDENCE in call["prompt"]
    assert "only\nbasis for current" in call["system"]
    assert call["purpose"] == "answer-verifier"


@pytest.mark.asyncio
async def test_verification_off_does_not_add_research_review_and_never_leaks_evidence():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service._model_text = AsyncMock(return_value="should not run")
    prepared = PreparedRequest(
        payload={},
        requested_mode="fast",
        effective_mode="fast",
        verification_level="off",
        route="web",
    )

    updated, verifier_used = await service.verify_answer(
        prepared=prepared,
        question="Current facts with sources",
        result={"response": "Draft [1]", AIService.GROUNDING_EVIDENCE_KEY: EVIDENCE},
    )

    assert verifier_used is False
    assert updated == {
        "response": (
            "Draft [1]\n\n"
            f"{AIService.GROUNDING_REVIEW_NOTICE}\n\nSources\n"
            "- [1] Primary source — https://example.com/primary"
        )
    }
    service._model_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_reviewer_preserves_long_draft_instead_of_reviewing_only_a_prefix():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service._model_text = AsyncMock(return_value="truncated replacement")
    prepared = PreparedRequest(
        payload={},
        requested_mode="deep",
        effective_mode="deep",
        verification_level="strict",
        route="web",
    )
    draft = "A" * (IntelligenceService.MAX_REVIEW_DRAFT_CHARS + 1)

    updated, verifier_used = await service.verify_answer(
        prepared=prepared,
        question="Review this complete report.",
        result={"response": draft},
    )

    assert verifier_used is False
    assert updated == {"response": draft}
    service._model_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_grounded_long_draft_is_preserved_with_unreviewed_notice():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service._model_text = AsyncMock(return_value="must not run")
    prepared = PreparedRequest(
        payload={},
        requested_mode="deep",
        effective_mode="deep",
        verification_level="strict",
        route="web",
    )
    draft = "A" * (IntelligenceService.MAX_REVIEW_DRAFT_CHARS + 1)

    updated, verifier_used = await service.verify_answer(
        prepared=prepared,
        question="Review this grounded report.",
        result={"response": draft, AIService.GROUNDING_EVIDENCE_KEY: EVIDENCE},
    )

    assert verifier_used is False
    assert updated["response"].startswith(draft)
    assert AIService.GROUNDING_REVIEW_NOTICE in updated["response"]
    assert updated["response"].endswith(
        "Sources\n- [1] Primary source — https://example.com/primary"
    )
    service._model_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_grounded_reviewer_adds_notice_without_second_call():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service._model_text = AsyncMock(return_value=None)
    prepared = PreparedRequest(
        payload={},
        requested_mode="auto",
        effective_mode="balanced",
        verification_level="auto",
        route="web",
    )

    updated, verifier_used = await service.verify_answer(
        prepared=prepared,
        question="What is the current release?",
        result={"response": "Draft [1]", AIService.GROUNDING_EVIDENCE_KEY: EVIDENCE},
    )

    assert verifier_used is False
    assert AIService.GROUNDING_REVIEW_NOTICE in updated["response"]
    assert service._model_text.await_count == 1


def test_unreviewed_grounding_notice_is_idempotent_and_keeps_canonical_sources():
    first = AIService.qualify_unreviewed_grounding("Draft [1]", EVIDENCE)
    second = AIService.qualify_unreviewed_grounding(first, EVIDENCE)

    assert second == first
    assert second.count(AIService.GROUNDING_REVIEW_NOTICE) == 1
    assert second.endswith(
        "Sources\n- [1] Primary source — https://example.com/primary"
    )
