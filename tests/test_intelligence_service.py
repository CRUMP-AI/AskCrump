from backend.intelligence_service import IntelligenceService


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
