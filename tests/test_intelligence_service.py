from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.intelligence_service import IntelligenceService, PreparedRequest
from backend.ai_service import AIService
from backend.db import DatabaseError


def test_complex_requests_score_above_simple_chat():
    simple = IntelligenceService._complexity_score("Hey, how are you?")
    complex_request = IntelligenceService._complexity_score(
        "Think hard and design an architecture. Compare the tradeoffs, implement "
        "the approach in Python, and explain a comprehensive verification plan."
    )
    assert complex_request > simple
    assert complex_request >= 6


def test_explicit_memory_extraction_is_conservative():
    memories = IntelligenceService._extract_explicit_memories(
        "Remember that Ask Crump is my flagship project. I prefer clean interfaces."
    )
    contents = [item["content"] for item in memories]
    assert any("Ask Crump" in content for content in contents)
    assert any("clean interfaces" in content for content in contents)


def test_sensitive_details_are_not_auto_memorized():
    memories = IntelligenceService._extract_explicit_memories(
        "Remember that my password is swordfish123."
    )
    assert memories == []


def test_forget_language_disables_auto_learning_for_turn():
    memories = IntelligenceService._extract_explicit_memories(
        "Forget what I said earlier. I prefer blue."
    )
    assert memories == []


def test_relevant_memories_use_query_overlap_and_importance():
    memories = [
        {
            "kind": "project",
            "content": "Ask Crump is a Python AI assistant project.",
            "importance": 5,
            "confidence": 0.95,
        },
        {
            "kind": "preference",
            "content": "The user prefers heavyweight cotton shirts.",
            "importance": 3,
            "confidence": 0.9,
        },
    ]
    selected = IntelligenceService._select_relevant_memories(
        "How should I improve the Ask Crump Python architecture?",
        memories,
        limit=1,
    )
    assert len(selected) == 1
    assert "Ask Crump" in selected[0]["content"]


def test_route_detection_for_current_and_code_requests():
    assert IntelligenceService._route_for("What is the latest OpenAI news?", {}) == "web"
    assert IntelligenceService._route_for("Debug this Python API error", {}) == "code"


def test_source_heavy_academic_requests_route_to_grounded_research():
    assert IntelligenceService._route_for(
        "Write a research paper with peer-reviewed citations and a bibliography.",
        {},
    ) == "web"


def test_constrained_rewrite_contract_preserves_modality_and_explicit_audience():
    request = """Reorganize this into a concise planning update that two volunteers can scan.
Preserve every supplied fact and do not add details.
The working budget is $1,200 and the workshop should happen within six weeks.
This update needs to become easier for two volunteers to scan."""

    contract = IntelligenceService._rewrite_fidelity_contract(request)

    assert contract is not None
    assert "should is not must" in contract
    assert "workshop should happen within six weeks" in contract
    assert "two volunteers" in contract
    assert "Retain every explicit audience" in contract


def test_unconstrained_conversation_does_not_create_a_rewrite_contract():
    assert IntelligenceService._rewrite_fidelity_contract(
        "Should we invite two volunteers to the workshop?"
    ) is None


def test_primary_model_prompt_receives_the_rewrite_fidelity_contract():
    contract = IntelligenceService._rewrite_fidelity_contract(
        "Reorganize this update for two volunteers. Preserve every fact. "
        "The workshop should happen within six weeks."
    )

    prompt = AIService(SimpleNamespace())._system_prompt({
        "assistantName": "Crump",
        "currentDateTime": {},
        "_rewriteFidelityContract": contract,
    })

    assert "CURRENT-TURN TRANSFORMATION FIDELITY — REQUIRED" in prompt
    assert "should happen within six weeks" in prompt
    assert "two volunteers" in prompt


@pytest.mark.asyncio
async def test_auto_verifier_repairs_strengthened_modality_and_missing_audience():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    contract = IntelligenceService._rewrite_fidelity_contract(
        "Reorganize this update for two volunteers. Preserve every fact. "
        "The workshop should happen within six weeks."
    )
    assert contract is not None
    service._model_text = AsyncMock(return_value=(
        "Audience: two volunteers.\n\n"
        "The workshop should happen within six weeks."
    ))
    prepared = PreparedRequest(
        payload={
            "_rewriteFidelityContract": contract,
            "user": {"id": "00000000-0000-0000-0000-000000000001"},
        },
        requested_mode="auto",
        effective_mode="balanced",
        verification_level="auto",
        route="conversation",
    )

    updated, verifier_used = await service.verify_answer(
        prepared=prepared,
        question=(
            "Reorganize this update for two volunteers. Preserve every fact. "
            "The workshop should happen within six weeks."
        ),
        result={"response": "The workshop must happen within six weeks."},
    )

    assert verifier_used is True
    assert updated["verified"] is True
    assert "should happen within six weeks" in updated["response"]
    assert "must happen within six weeks" not in updated["response"]
    assert "two volunteers" in updated["response"]
    call = service._model_text.await_args.kwargs
    assert "should must remain\nshould" in call["system"]
    assert "two volunteers" in call["prompt"]


@pytest.mark.asyncio
async def test_server_conversation_opt_out_overrides_client_omission():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service.get_preferences = AsyncMock(return_value={
        "intelligence_mode": "auto",
        "memory_enabled": True,
        "auto_learn": True,
        "auto_tools": True,
        "verification_level": "auto",
    })
    service.get_conversation_memory_opt_out = AsyncMock(return_value=True)
    service.infer_creation_intent = AsyncMock(return_value=None)
    service.retrieve_memories = AsyncMock(return_value=[{"content": "must not load"}])

    prepared = await service.prepare(
        "user-1",
        {
            "chatId": "00000000-0000-0000-0000-000000000111",
            "message": "Continue our work.",
            "memoryOptOut": False,
        },
    )

    assert prepared.private_chat is True
    assert prepared.auto_learn is False
    assert prepared.memory_count == 0
    service.retrieve_memories.assert_not_awaited()


@pytest.mark.asyncio
async def test_conversation_privacy_fails_closed_when_database_is_unavailable():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service.get_preferences = AsyncMock(return_value={
        "intelligence_mode": "auto",
        "memory_enabled": True,
        "auto_learn": True,
        "auto_tools": True,
        "verification_level": "auto",
    })
    service.get_conversation_memory_opt_out = AsyncMock(
        side_effect=DatabaseError("temporary outage")
    )
    service.infer_creation_intent = AsyncMock(return_value=None)
    service.retrieve_memories = AsyncMock(return_value=[])

    prepared = await service.prepare(
        "user-1",
        {
            "chatId": "00000000-0000-0000-0000-000000000111",
            "message": "Continue our work.",
        },
    )

    assert prepared.private_chat is True
    assert prepared.auto_learn is False
    service.retrieve_memories.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_can_disable_auto_learning_before_preference_sync_finishes():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service.get_preferences = AsyncMock(return_value={
        "intelligence_mode": "auto",
        "memory_enabled": True,
        "auto_learn": True,
        "auto_tools": True,
        "verification_level": "auto",
    })
    service.infer_creation_intent = AsyncMock(return_value=None)
    service.retrieve_memories = AsyncMock(return_value=[])

    prepared = await service.prepare(
        "user-1",
        {"message": "Remember that I prefer blue.", "autoLearn": False},
    )

    assert prepared.memory_enabled is True
    assert prepared.auto_learn is False


@pytest.mark.asyncio
async def test_request_memory_flags_fail_closed_and_cannot_expand_durable_permission():
    service = IntelligenceService(
        db=SimpleNamespace(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )
    service.get_preferences = AsyncMock(return_value={
        "intelligence_mode": "auto",
        "memory_enabled": True,
        "auto_learn": False,
        "auto_tools": True,
        "verification_level": "auto",
    })
    service.infer_creation_intent = AsyncMock(return_value=None)
    service.retrieve_memories = AsyncMock(return_value=[{"content": "must not load"}])

    expanded = await service.prepare(
        "user-1",
        {"message": "Remember this.", "memoryEnabled": True, "autoLearn": True},
    )
    malformed = await service.prepare(
        "user-1",
        {"message": "Continue.", "memoryEnabled": "false", "autoLearn": "true"},
    )

    assert expanded.auto_learn is False
    assert malformed.memory_enabled is False
    assert malformed.auto_learn is False
    service.retrieve_memories.assert_awaited_once()


@pytest.mark.asyncio
async def test_preference_write_failure_is_reported_instead_of_claiming_success():
    class FailingPreferenceDB:
        async def select_one(self, *_args, **_kwargs):
            return None

        async def upsert(self, *_args, **_kwargs):
            raise DatabaseError("temporary outage")

    service = IntelligenceService(
        db=FailingPreferenceDB(), ai=SimpleNamespace(), settings=SimpleNamespace()
    )

    with pytest.raises(DatabaseError):
        await service.update_preferences("user-1", {"autoLearn": False})


@pytest.mark.asyncio
async def test_preference_update_never_overwrites_defaults_after_a_failed_read():
    class FailingPreferenceReadDB:
        def __init__(self):
            self.upsert_called = False

        async def select_one(self, *_args, **_kwargs):
            raise DatabaseError("temporary read outage")

        async def upsert(self, *_args, **_kwargs):
            self.upsert_called = True

    db = FailingPreferenceReadDB()
    service = IntelligenceService(
        db=db, ai=SimpleNamespace(), settings=SimpleNamespace()
    )

    with pytest.raises(DatabaseError):
        await service.update_preferences("user-1", {"autoLearn": False})

    assert db.upsert_called is False


@pytest.mark.asyncio
async def test_image_trace_records_only_allowlisted_generation_controls():
    class TraceDB:
        def __init__(self):
            self.rows = []

        async def insert(self, table, payload):
            self.rows.append((table, payload))

    db = TraceDB()
    service = IntelligenceService(db=db, ai=SimpleNamespace(), settings=SimpleNamespace())
    prepared = PreparedRequest(
        payload={
            "imageQuality": "high",
            "imageAspect": "portrait",
            "message": "private prompt must not enter trace flags",
        },
        requested_mode="auto",
        effective_mode="auto",
        verification_level="auto",
        route="image",
    )

    await service.record_trace(
        user_id="00000000-0000-0000-0000-000000000001",
        request_id="trace-test",
        chat_id=None,
        message_id=None,
        prepared=prepared,
        model="gpt-image-2",
        latency_ms=123,
        status="success",
    )

    flags = db.rows[0][1]["tool_flags"]
    assert flags["imageQuality"] == "high"
    assert flags["imageAspect"] == "portrait"
    assert "message" not in flags
