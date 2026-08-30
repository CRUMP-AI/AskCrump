from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_531_personality_is_conversational_without_dropping_truthfulness():
    ai = read("backend/ai_service.py")
    assert "follow the spirit of casual questions" in ai
    assert "ontology lecture" in ai
    assert "Use contractions" in ai
    assert "Do not fake emotions, memories, consciousness, or experiences" in ai


def test_project_reference_files_use_existing_private_file_system():
    routes = read("backend/routes/projects.py")
    service = read("backend/project_service.py")
    chat = read("backend/routes/chat.py")
    media = read("backend/media_service.py")
    assert '@router.post("/{project_id}/files")' in routes
    assert "async def reference_files" in service
    assert '"reference_files"' in service
    assert "project_reference_files" in chat
    assert "include_pdf=True" in chat
    assert "include_pdf: bool = False" in media
    assert "mime == PDF_TYPE and not include_pdf" in media


def test_project_reference_ui_and_chat_rename_are_final_runtime_layers():
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    js = read("public/crump-product-5.3.1.js")
    css = read("public/crump-product-5.3.1.css")
    app = read("public/app.js")
    files = read("public/crump-5.0.js")
    assert "/crump-product-5.3.1.css" in runtime
    assert "/crump-product-5.3.1.js" in runtime
    assert runtime.index("/crump-product-5.3.js") < runtime.index("/crump-product-5.3.1.js")
    assert "/crump-product-5.3.1.js?v=5.9.76-demand-hydration-1" in runtime
    assert "/crump-product-5.3.1.js?v=5.9.76-demand-hydration-1" in worker
    assert "ask-crump-new-body-v1-r141" in worker
    assert "Reference files" in js
    assert "Project files" in js
    assert "conversationsCard.insertAdjacentElement('afterend', card)" in js
    assert "Rename chat" in js
    assert "data.chatId" not in js
    assert "item.dataset.chatId = chat.id" in app
    assert "window.CrumpFileTools" in files
    assert "upload: async file =>" in files
    assert "CrumpFileTools?.upload" in js
    assert "window.addEventListener('crump:project-target-changed', hydrateVisibleProjectFiles)" in js
    assert "sheet?.dataset.projectView !== 'detail'" in js
    assert 'setTimeout(() => { void refreshProjectFiles(); }, 120);' not in js
    assert ".crump531-chat-menu-button" in css
    assert ".crump531-project-file-group" in css
    assert "grid-template-columns: minmax(0,1fr)" in css
    assert "box-sizing: border-box" in css


def test_project_canon_flags_conflicts_instead_of_silently_rewriting():
    hooks = read("backend/product53_hooks.py")
    assert "conflicts with established Project canon" in hooks
    assert "point out the conflict" in hooks


def test_clever_crump_page_uses_plain_language_positioning():
    page = read("public/ask-crump.html")
    assert 'src="/assets/brand/crump-horizontal-light.png"' in page
    assert 'aria-label="Ask Crump home"' in page
    assert '<div class="eyebrow">YOUR AI WORKSPACE</div>' in page
    assert "CLEVER CRUMP PRESENTS" not in page
    assert "AI should help you" in page
    assert "finish things." in page
    assert "WHAT ASK CRUMP HAS BECOME" in page
    assert "THE CRUMP VIDEO ENGINE" in page
    assert "HOW CLEVER CRUMP BUILDS" in page
    assert "Projects" in page
    assert "Library" in page
    assert "Saved Library" not in page
    assert "transformative intelligence ecosystem" not in page.lower()
    assert "chatgpt" not in page.lower()


def test_parent_company_uses_the_current_ask_crump_positioning():
    page = read("public/clever-crump.html")

    assert 'alt="Ask Crump — An AI workspace for work that continues"' in page
    assert 'alt="Ask Crump — AI Virtual Assistant"' not in page
