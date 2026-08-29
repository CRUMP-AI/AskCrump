from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []
        self.inline_handlers = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        element_id = values.get('id')
        if element_id:
            self.ids.append(element_id)
        for name in values:
            if name.lower().startswith('on'):
                self.inline_handlers.append((tag, name))
        for name in ('src', 'href'):
            value = values.get(name)
            if value:
                self.assets.append(value)


def local_asset(value):
    if (
        not value.startswith('/')
        or value.startswith('/api/')
        or value.startswith('/_vercel/')
    ):
        return None
    path = value.split('#', 1)[0].split('?', 1)[0]
    if path in {'/', '/app'}:
        return None
    candidate = PUBLIC / path.lstrip('/')
    if not candidate.suffix and not candidate.exists():
        clean_url_source = candidate.with_suffix('.html')
        if clean_url_source.exists():
            return clean_url_source
    return candidate


def test_html_local_assets_exist_and_no_inline_handlers():
    for filename in ('ask-crump.html', 'app.html', 'legal.html', 'delete-account.html'):
        parser = AssetParser()
        parser.feed((PUBLIC / filename).read_text())
        assert not parser.inline_handlers, f'{filename}: {parser.inline_handlers}'
        missing = [str(path) for asset in parser.assets if (path := local_asset(asset)) and not path.exists()]
        assert not missing, f'{filename} references missing assets: {missing}'


def test_manifest_icons_are_real_files_with_declared_sizes():
    manifest = json.loads((PUBLIC / 'manifest.json').read_text())
    for icon in manifest['icons']:
        path = PUBLIC / icon['src'].lstrip('/')
        assert path.exists()
        width, height = map(int, icon['sizes'].split('x'))
        assert width == height
        assert path.name == f'ask-crump-app-icon-v2-{width}.png'


def test_apple_install_icon_is_versioned_and_uses_the_locked_mark():
    app_html = (PUBLIC / 'app.html').read_text()
    assert 'apple-touch-icon" sizes="180x180"' in app_html
    assert 'ask-crump-app-icon-v2-180.png' in app_html
    assert 'apple-touch-icon-precomposed' in app_html
    assert (PUBLIC / 'assets' / 'ask-crump-app-icon-v2-180.png').exists()

    generator = (ROOT / 'scripts' / 'generate_locked_brand_icons.py').read_text()
    assert 'LOCKED_SHA256' in generator
    assert "resources' / 'icon.png'" in generator
    assert "resources' / 'splash.png'" in generator

    from PIL import Image
    with Image.open(ROOT / 'resources' / 'icon.png') as icon:
        assert icon.size == (1024, 1024)
    with Image.open(ROOT / 'resources' / 'splash.png') as splash:
        assert splash.size == (2732, 2732)


def test_signed_out_entry_eagerly_loads_only_visible_brand_images():
    class ImageParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.images = []

        def handle_starttag(self, tag, attrs):
            if tag == 'img':
                self.images.append(dict(attrs))

    parser = ImageParser()
    parser.feed((PUBLIC / 'app.html').read_text())

    brand_images = [
        image for image in parser.images
        if image.get('src') in {
            '/assets/brand/crump-horizontal-light.png',
            '/assets/brand/crump-mark.png',
        }
    ]
    eager_images = [image for image in brand_images if image.get('loading') != 'lazy']
    deferred_images = [image for image in brand_images if image.get('loading') == 'lazy']

    assert len(eager_images) == 3
    assert sum(image['src'] == '/assets/brand/crump-horizontal-light.png' for image in eager_images) == 2
    startup_mark = next(image for image in eager_images if image['src'] == '/assets/brand/crump-mark.png')
    assert startup_mark.get('loading') == 'eager'
    assert startup_mark.get('decoding') == 'sync'
    assert startup_mark.get('fetchpriority') == 'high'
    assert len(deferred_images) == len(brand_images) - 3
    assert all(image.get('decoding') == 'async' for image in deferred_images)
    assert all(image.get('width') and image.get('height') for image in brand_images)

    navigation = (PUBLIC / 'crump-navigation-5.9.30.js').read_text()
    assert (
        '<img src="/assets/brand/crump-mark.png" width="640" height="714" '
        'loading="lazy" decoding="async" alt="">'
    ) in navigation

    worker = (PUBLIC / 'sw.js').read_text()
    core = worker[worker.index('const CORE = ['):worker.index('];')]
    on_demand_images = {
        '/assets/brand/crump-mark.png',
        '/assets/brand/crump-horizontal-dark.png',
        '/assets/ask-crump-app-icon-v2-180.png',
        '/assets/ask-crump-app-icon-v2-192.png',
        '/assets/ask-crump-app-icon-v2-512.png',
        '/assets/ask-crump-app-icon-v2-1024.png',
    }
    assert all(f"'{asset}'" not in core for asset in on_demand_images)


def test_service_worker_never_cache_firsts_api_requests():
    source = (PUBLIC / 'sw.js').read_text()
    assert "url.pathname.startsWith('/api/')" in source
    assert "fetch(request)" in source

def test_no_decorative_startup_video_or_in_app_splash():
    assert not list(PUBLIC.rglob('*.mp4'))
    assert not list(PUBLIC.rglob('*.webm'))
    app_html = (PUBLIC / 'app.html').read_text()
    auth_source = (PUBLIC / 'auth-controller.js').read_text()
    assert 'id="splashScreen"' not in app_html
    assert 'fadeSplash' not in auth_source



def test_presence_is_inline_and_accessible():
    app_html = (PUBLIC / 'app.html').read_text()
    runtime = (PUBLIC / 'runtime-body-v1.js').read_text()
    polish = (PUBLIC / 'conversation.css').read_text()
    presence = (PUBLIC / 'presence-manager.js').read_text()
    assert '/presence-manager.js' not in app_html
    assert '/presence-manager.js?v=5.9.75' in runtime
    assert 'id="thinkingIndicator"' not in app_html
    assert 'id="conversationStatus"' in app_html
    assert 'aria-live="polite"' in app_html
    assert 'prefers-reduced-motion: reduce' in polish
    assert 'window.CrumpPresence' in presence
    assert "activityTimer = setTimeout" in presence


def test_native_push_and_network_bridges_are_wired():
    native = (PUBLIC / 'native-entry.js').read_text()
    package = json.loads((ROOT / 'package.json').read_text())
    assert '@capacitor/push-notifications' in package['dependencies']
    assert 'PushNotifications' in native
    assert 'POST_NOTIFICATIONS' not in native  # Android permission belongs in the manifest/configurator.
    assert 'networkStatusChange' in native



def test_html_ids_are_unique():
    for filename in ('ask-crump.html', 'app.html', 'legal.html', 'delete-account.html'):
        parser = AssetParser()
        parser.feed((PUBLIC / filename).read_text())
        duplicates = [name for name, count in Counter(parser.ids).items() if count > 1]
        assert not duplicates, f'{filename} contains duplicate IDs: {duplicates}'


def test_css_custom_properties_are_defined():
    sources = '\n'.join(path.read_text() for path in PUBLIC.glob('*.css'))
    used = set(re.findall(r'var\((--[a-zA-Z0-9-]+)', sources))
    defined = set(re.findall(r'(--[a-zA-Z0-9-]+)\s*:', sources))
    assert not (used - defined), f'Undefined CSS variables: {sorted(used - defined)}'



class StructureParser(HTMLParser):
    void_elements = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.ancestors_by_id = {}
        self.buttons_without_type = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        element_id = values.get('id')
        if element_id:
            self.ancestors_by_id[element_id] = tuple(item for item in self.stack if item)
        if tag == 'button' and not values.get('type'):
            self.buttons_without_type.append(element_id or values.get('class') or '<anonymous>')
        if tag not in self.void_elements:
            self.stack.append(element_id)

    def handle_endtag(self, tag):
        if tag not in self.void_elements and self.stack:
            self.stack.pop()


def test_authentication_forms_share_the_authentication_container():
    parser = StructureParser()
    parser.feed((PUBLIC / 'app.html').read_text())
    for form_id in ('loginForm', 'registerForm', 'forgotPasswordForm', 'resetPasswordForm'):
        assert 'authContainer' in parser.ancestors_by_id[form_id]


def test_buttons_declare_their_type():
    for filename in ('ask-crump.html', 'app.html', 'legal.html', 'delete-account.html'):
        parser = StructureParser()
        parser.feed((PUBLIC / filename).read_text())
        assert not parser.buttons_without_type, f'{filename}: {parser.buttons_without_type}'


def test_toast_notifications_have_an_implementation():
    app_html = (PUBLIC / 'app.html').read_text()
    ui = (PUBLIC / 'ui-functions.js').read_text()
    assert 'id="toastContainer"' in app_html
    assert 'window.showToast = showToast' in ui
    assert "role', toastTone === 'error' ? 'alert' : 'status'" in ui


def test_ai_responses_have_in_app_safety_reporting():
    ui = (PUBLIC / 'ui-functions.js').read_text()
    privacy = (PUBLIC / 'legal.html').read_text()
    assert "report.textContent" in ui
    assert "'/api/safety/reports'" in ui
    assert "Report this response" in ui
    assert "AI response safety reports" in privacy
    assert "Vercel AI Gateway" in privacy
    assert "zero-data-retention" in privacy
    assert "prompt-training restrictions" in privacy


def test_ai_responses_have_privacy_safe_sharing():
    ui = (PUBLIC / 'ui-functions.js').read_text()
    assert "share.textContent = 'Share'" in ui
    assert "navigator.share(payload)" in ui
    assert "Created with Ask Crump" in ui
    assert "ResponseShared" in ui
    assert "responseShareKey(message, index)" in ui
    assert (
        "https://www.askcrump.com/app?signup=1&acquisition=referral&source=response-share"
        in ui
    )
    share_url = ui[ui.index("const ASK_CRUMP_SHARE_URL"):ui.index("async function writeClipboard")]
    assert "user_id" not in share_url.lower()
    assert "message" not in share_url.lower()
    assert "chat" not in share_url.lower()


def test_failed_clipboard_fallback_never_claims_or_records_a_share():
    ui = (PUBLIC / 'ui-functions.js').read_text()
    clipboard = ui[ui.index('async function writeClipboard'):ui.index('async function copyMessage')]
    share = ui[ui.index('async function shareMessage'):ui.index('async function shareAskCrump')]
    referral = ui[ui.index('async function shareAskCrump'):ui.index('const OUTCOME_FEEDBACK_STORAGE_PREFIX')]

    assert "document.execCommand?.('copy') !== true" in clipboard
    assert 'throw clipboardError' in clipboard
    assert share.index('await writeClipboard') < share.index("recordResponseShare(message, index, 'clipboard')")
    assert referral.index('await writeClipboard') < referral.index("recordResponseShare(message, index, 'useful_prompt_clipboard')")
    assert "Sharing is unavailable in this browser." in share
    assert "Sharing is unavailable in this browser." in referral


def test_destructive_actions_use_an_accessible_dialog():
    app_js = (PUBLIC / 'app.js').read_text()
    ui = (PUBLIC / 'ui-functions.js').read_text()
    assert "confirm('" not in app_js
    assert 'window.confirmAction = confirmAction' in ui
    assert "document.createElement('dialog')" in ui


def test_account_dialog_traps_keyboard_focus():
    source = (PUBLIC / 'account-manager.js').read_text()
    assert "event.key !== 'Tab'" in source
    assert "event.shiftKey && document.activeElement === first" in source
    assert "document.activeElement === last" in source


def test_markdown_placeholders_are_not_predictable_user_tokens():
    source = (PUBLIC / 'ui-functions.js').read_text()
    assert 'window.crypto?.randomUUID?.()' in source
    assert 'CRUMPBLOCK${protectedBlocks.length}TOKEN' not in source


def test_manifest_uses_standard_product_metadata():
    manifest = json.loads((PUBLIC / 'manifest.json').read_text())
    assert manifest['name'] == 'Ask Crump'
    assert manifest['short_name'] == 'Ask Crump'
    assert 'version' not in manifest
    assert 'private' not in manifest['description'].lower()
