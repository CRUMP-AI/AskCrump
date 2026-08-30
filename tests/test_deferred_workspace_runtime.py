from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def read(name: str) -> str:
    return (PUBLIC / name).read_text(encoding='utf-8')


def test_signed_out_shell_loads_only_authentication_critical_assets():
    shell = read('app.html')
    styles = re.findall(r'<link rel="stylesheet" href="([^"]+)"', shell)
    scripts = re.findall(r'<script defer src="([^"]+)"', shell)

    assert styles == [
        '/styles.css',
        '/install-prompt.css?v=5.9.76',
        '/auth-styles.css',
        '/crump-v1-body.css?v=5.9.76-registration-consent-1',
    ]
    assert scripts == [
        '/telemetry-config.js?v=5.9.76',
        '/runtime-body-v1.js?v=5.9.76-parallel-fetch-1',
        '/native-runtime.js',
        '/mobile-bridge.js',
        '/safe-storage.js',
        '/install-prompt.js?v=5.9.76',
        '/auth-resilience.js?v=5.9.76',
        '/device-auth.js?v=5.9.76',
        '/auth-controller.js?v=5.9.76-registration-consent-projects-1',
        '/_vercel/insights/script.js',
        '/_vercel/speed-insights/script.js',
    ]


def test_workspace_runtime_is_complete_idempotent_and_authentication_gated():
    shell = read('app.html')
    runtime = read('runtime-body-v1.js')
    controller = read('auth-controller.js')

    deferred_assets = [
        '/billing.css',
        '/onboarding.css?v=5.9.76-actionable-tour-1',
        '/conversation.css?v=5.9.76',
        '/onboarding.js?v=5.9.76-books-library-2',
        '/scroll-manager.js',
        '/profile-manager.js',
        '/billing-manager.js',
        '/subscription-ui.js',
        '/chat-resilience.js?v=5.9.76',
        '/ui-functions.js?v=5.9.76-project-continuity-1',
        '/presence-manager.js?v=5.9.76',
        '/sync-manager.js?v=5.9.76',
        '/chat-sync.js?v=5.9.76-sync-cadence-1',
        '/account-manager.js',
        '/app.js?v=5.9.76',
        '/product-analytics.js?v=5.9.76',
    ]
    for asset in deferred_assets:
        assert asset not in shell
        assert asset in runtime

    assert 'let runtimePromise = null;' in runtime
    assert 'if (runtimePromise) return runtimePromise;' in runtime
    assert 'window.CrumpWorkspaceRuntime = Object.freeze({load});' in runtime
    assert "document.addEventListener('DOMContentLoaded', () => { void boot();" not in runtime

    assert 'async function prepareAuthenticatedWorkspace()' in controller
    assert controller.count('await prepareAuthenticatedWorkspace();') == 2
    bootstrap = controller[controller.index('  async function bootstrap()'):controller.index('  function wireNavigation()')]
    assert bootstrap.index('await prepareAuthenticatedWorkspace();') < bootstrap.index('activeUser = session.data.user;')
    login = controller[controller.index('  function wireLogin()'):controller.index('  function wireRegistration()')]
    assert login.index('await prepareAuthenticatedWorkspace();') < login.index('activeUser = result.data.user;')


def test_new_visitors_wait_for_authentication_before_service_worker_registration():
    install = read('install-prompt.js')
    native_builder = (ROOT / 'scripts' / 'build-native.mjs').read_text(encoding='utf-8')

    assert 'navigator.serviceWorker.getRegistration()' in install
    assert "window.addEventListener('crump:authenticated-ready'" in install
    assert 'if (existing || window.currentUser)' in install
    assert "serviceWorkerRegistration = await navigator.serviceWorker.register('/sw.js');" in install
    load_handler = install[install.index("window.addEventListener('load'"):]
    assert 'void registerExistingOrWaitForAuthentication();' in load_handler
    assert "navigator.serviceWorker.register('/sw.js')" not in load_handler

    assert 'window.CrumpWorkspaceRuntime = Object.freeze({load});' in native_builder
    assert "window.addEventListener('load', () => { void boot();" not in native_builder


def test_authenticated_entry_fixture_counts_exactly_one_runtime_load():
    fixture = (ROOT / 'tests' / 'fixtures' / 'auth-entry-sync-stall.html').read_text(encoding='utf-8')

    assert 'id="runtimeLoads"' in fixture
    assert 'window.__fixture.runtimeLoads += 1;' in fixture
    assert "document.getElementById('runtimeLoads').textContent" in fixture
