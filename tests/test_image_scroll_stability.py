from pathlib import Path

from backend.media_service import MediaService
from backend.sync_service import sanitize_message


ROOT = Path(__file__).resolve().parents[1]


def test_generated_image_aspect_is_content_free_and_allowlisted() -> None:
    assert MediaService.image_aspect_for_size('1024x1024') == 'square'
    assert MediaService.image_aspect_for_size('1024x1536') == 'portrait'
    assert MediaService.image_aspect_for_size('1536x1024') == 'landscape'
    assert MediaService.image_aspect_for_size('attacker-controlled') == 'square'

    allowed = sanitize_message({
        'role': 'assistant',
        'content': 'Image ready.',
        'imageUrl': 'https://www.askcrump.com/api/files/example/content',
        'imageAspect': 'PORTRAIT',
    })
    rejected = sanitize_message({
        'role': 'assistant',
        'content': 'Image ready.',
        'imageUrl': 'https://www.askcrump.com/api/files/example/content',
        'imageAspect': 'private-freeform-value',
    })

    assert allowed['imageAspect'] == 'portrait'
    assert 'imageAspect' not in rejected


def test_image_scroll_contract_is_user_controlled_and_reserves_layout() -> None:
    scroll = (ROOT / 'public' / 'crump-5.2.2.js').read_text(encoding='utf-8')
    base_scroll = (ROOT / 'public' / 'scroll-manager.js').read_text(encoding='utf-8')
    renderer = (ROOT / 'public' / 'ui-functions.js').read_text(encoding='utf-8')
    composer = (ROOT / 'public' / 'crump-5.0.js').read_text(encoding='utf-8')
    app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    assert 'function jumpToNewest()' in scroll
    assert 'scrollToBottom: () => undefined' in scroll
    assert 'autoScrollToBottom: () => undefined' in scroll
    assert 'scrollToMessageTop: () => undefined' in scroll
    assert 'anchorNewReply' not in scroll
    assert 'activeReplyShouldHold' not in scroll
    assert "state.scroll.button?.setAttribute('aria-label', 'New response available. Jump to newest message')" in scroll
    assert "status.setAttribute('aria-live', 'polite')" in scroll
    assert "status.setAttribute('aria-atomic', 'true')" in scroll
    assert "state.scroll.status.textContent = 'New response available. Use Jump to newest message when you are ready.'" in scroll
    assert "if (chatId !== state.scroll.chatId)" in scroll
    assert "clearNewResponse();" in scroll
    assert 'function jumpToNewest(event)' in base_scroll
    assert 'scrollToBottom: () => undefined' in base_scroll
    assert 'crumpScrollManager?.scrollToBottom' not in composer
    assert 'safeScrollToBottom' not in app
    assert 'const preservedScrollTop = container.scrollTop;' in renderer
    assert 'if (container.scrollTop !== preservedScrollTop) container.scrollTop = preservedScrollTop;' in renderer
    assert "window.crumpScrollManager.scrollToBottom('auto')" not in renderer
    assert 'function imageAspectForMessage(message, messages)' in renderer
    assert 'image.width = aspect.width;' in renderer
    assert 'image.height = aspect.height;' in renderer
