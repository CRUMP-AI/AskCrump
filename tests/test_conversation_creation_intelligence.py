from pathlib import Path

from backend.intelligence_service import IntelligenceService
from backend.routes.chat import _promote_explicit_document_delivery

ROOT = Path(__file__).resolve().parents[1]

def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")

def test_natural_creation_language_is_a_semantic_candidate():
    assert IntelligenceService._creation_candidate("I want a book", [])
    assert IntelligenceService._creation_candidate("make me a picture of a dog playing piano", [])
    assert IntelligenceService._creation_candidate("I need a resume", [])

def test_short_confirmation_keeps_recent_creation_context():
    history = [
        {"role": "user", "content": "I want to write a psychological science fiction novel."},
        {"role": "assistant", "content": "Do you want it dark or hopeful?"},
        {"role": "user", "content": "Dark. About 300 pages."},
    ]
    assert IntelligenceService._creation_candidate("go", history)

def test_fallback_does_not_instantly_execute_vague_book_desire():
    intent = IntelligenceService._fallback_creation_intent("I want a book", [])
    assert intent and intent["kind"] == "manuscript"
    assert intent["stage"] == "clarify"

def test_fallback_can_execute_a_specific_natural_image_request():
    intent = IntelligenceService._fallback_creation_intent("Make me a picture of a golden retriever playing a grand piano on stage", [])
    assert intent and intent["kind"] == "image"
    assert intent["stage"] == "execute"


def test_document_delivery_follow_up_executes_from_recent_context():
    history = [
        {"role": "user", "content": "Create a detailed sample resume for a fraud detection technology role."},
        {"role": "assistant", "content": "Jordan A. Ramirez — Fraud Detection Engineer"},
    ]
    intent = IntelligenceService._fallback_creation_intent(
        "Could you deliver this in a document format?",
        history,
    )
    assert intent and intent["kind"] == "document"
    assert intent["stage"] == "execute"
    assert intent["format"] == "docx"


def test_explicit_document_delivery_cannot_be_downgraded_to_clarification():
    intent = _promote_explicit_document_delivery(
        {
            "kind": "document",
            "stage": "clarify",
            "confidence": 0.9,
            "brief": "Package the completed resume from this conversation.",
            "question": "What should the document contain?",
            "format": "",
        },
        "docx",
    )
    assert intent["stage"] == "execute"
    assert intent["question"] == ""
    assert intent["format"] == "docx"


def test_chat_route_uses_resolved_brief_and_avoids_reasking_forms():
    route = read("backend/routes/chat.py")
    assert "history=request_payload.get('history')" in route
    assert "execution_brief = str(creation_intent.get('brief') or original_message)" in route
    assert "brief=execution_brief" in route
    assert "creation_title.casefold() not in execution_brief.casefold()" in route
    assert "request_payload['message'] = execution_brief" in route
    assert "semantic_chat_only" in route
    assert "creationHandoff" in route

def test_natural_page_targets_are_carried_into_manuscript_planning():
    manuscript = read("backend/manuscript_service.py")
    assert "pages / 1.12" in manuscript
    assert "* 275" in manuscript

def test_manuscript_handoff_opens_real_workshop_with_prefilled_metadata():
    manuscript = read("backend/manuscript_service.py")
    product = read("public/crump-product-5.3.js")
    assert '"autoOpen": True' in manuscript
    assert "I carried what we already worked out into the Workshop" in manuscript
    assert "metadata.premise || ''" in product
    assert "Open Workshop" in product
    assert "handleCreationHandoff" in product

def test_video_handoff_reuses_existing_guarded_video_engine():
    product = read("public/crump-product-5.3.js")
    composer = read("public/crump-5.0.js")
    assert "openVideoCreationHandoff" in product
    assert "startVideo(event, overrides = {})" in product
    assert "idempotencyKey: key" in product
    assert "CrumpProduct53?.handleCreationHandoff" in composer

def test_crump_voice_avoids_generic_assistant_form_language():
    service = read("backend/ai_service.py")
    assert "Never default to canned assistant language" in service
    assert "ask at most one high-value question at a time" in service
    assert "Keep internal product vocabulary invisible" in service

def test_conversation_intelligence_advances_shell_cache():
    sw = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")
    assert "ask-crump-new-body-v1-r173" in sw
    assert "ask-crump-new-body-v1-r23" not in sw
    assert "ask-crump-new-body-v1-r173" in checker


def test_reload_opens_a_clean_conversation_without_discarding_history():
    app = read("public/app.js")
    shell = read("public/app.html")
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    startup = app[app.index("window.initializeApp = function"):app.index("// Event Listeners")]
    fresh_start = app[
        app.index("function openFreshConversationAtStartup"):
        app.index("function loadChat(chatId)")
    ]

    assert "openFreshConversationAtStartup();" in startup
    assert "savedChatId" not in startup
    assert "beginFreshConversation();" in fresh_start
    assert "saveChats" not in fresh_start
    assert "syncChatsToServer" not in fresh_start
    assert "first real message materializes the draft" in fresh_start
    assert "chats = []" not in fresh_start
    assert "recordChatDeletion" not in fresh_start
    assert 'src="/app.js?v=5.9.76-intelligence-receipt-1"' not in shell
    assert "['/app.js?v=5.9.76-core-reliability-1', 'workspaceapp']" in runtime
    assert "'/app.js?v=5.9.76-core-reliability-1'" in worker

def test_runtime_document_extraction_patch_accepts_project_pdf_keyword():
    compatibility = read("backend/crump52_patches.py")
    route = read("backend/routes/chat.py")

    assert "include_pdf: bool = False" in compatibility
    assert "or include_pdf" in compatibility
    assert "MediaService.extract_nonvisual = _extract_nonvisual_v52" in compatibility
    assert "include_pdf=True" in route


def test_runtime_artifact_compatibility_patch_preserves_contextual_delivery_history():
    compatibility = read("backend/crump52_patches.py")

    assert "history: Any = None" in compatibility
    assert "_ORIGINAL_DETECT_ARTIFACT(cls, message, explicit, history)" in compatibility


def test_conversation_intelligence_remains_enabled_after_project_chat_compatibility_fix():
    route = read("backend/routes/chat.py")
    intelligence = read("backend/intelligence_service.py")

    assert "prepared = await intelligence.prepare" in route
    assert "async def infer_creation_intent" in intelligence
    assert "_promote_explicit_document_delivery(" in route
    assert "prepared.creation_intent or {}," in route
