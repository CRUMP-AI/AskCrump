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


def test_image_scroll_contract_respects_reading_and_reserves_layout() -> None:
    scroll = (ROOT / 'public' / 'crump-5.2.2.js').read_text(encoding='utf-8')
    renderer = (ROOT / 'public' / 'ui-functions.js').read_text(encoding='utf-8')
    composer = (ROOT / 'public' / 'crump-5.0.js').read_text(encoding='utf-8')

    assert 'state.scroll.userReviewingHistory' in scroll
    assert 'if (!force && state.scroll.userReviewingHistory) return;' in scroll
    assert 'if (state.scroll.userReviewingHistory)' in scroll
    assert "window.crumpScrollManager?.scrollToBottom?.({force: true});" in composer
    assert 'function imageAspectForMessage(message, messages)' in renderer
    assert 'image.width = aspect.width;' in renderer
    assert 'image.height = aspect.height;' in renderer
