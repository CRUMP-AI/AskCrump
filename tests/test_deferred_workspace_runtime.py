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
        '/auth-styles.css?v=5.9.76-guest-free-contract-2',
        '/crump-v1-body.css?v=5.9.76-owned-workspace-access-1',
        '/appearance-controls.css?v=5.9.76-appearance-choice-3',
        # The preview entry and authenticated shell share these presentation
        # assets. Retired Home/Studios/You view scripts no longer ship.
        '/crump-vision-shell-1.0.css?v=5.9.76-atelier-workspace-1',
        '/crump-vision-chats-1.0.css?v=5.9.76-atelier-workspace-1',
        '/crump-vision-projects-1.0.css?v=5.9.76-project-resume-1',
        '/crump-vision-library-1.0.css?v=5.9.76-atelier-workspace-1',
        '/crump-vision-studios-1.0.css?v=5.9.76-atelier-workspace-1',
    ]
    assert scripts == [
        '/telemetry-config.js?v=5.9.76',
        '/crump-vision-demo-1.0.js?v=5.9.76-atelier-workspace-1',
        '/runtime-body-v1.js?v=5.9.76-workspace-opened-retry-1',
        '/home-document-entry.js?v=5.9.76-home-document-entry-1',
        '/crump-vision-shell-1.0.js?v=5.9.76-atelier-workspace-1',
        '/crump-vision-chats-1.0.js?v=5.9.76-atelier-workspace-1',
        '/crump-vision-projects-1.0.js?v=5.9.76-project-resume-owner-boundary-1',
        '/crump-vision-library-1.0.js?v=5.9.76-account-owner-boundary-1',
        '/native-runtime.js',
        '/mobile-bridge.js?v=5.9.76-private-owner-boundary-1',
        '/safe-storage.js',
        '/install-prompt.js?v=5.9.76-update-work-guard-1',
        '/auth-resilience.js?v=5.9.76',
        '/device-auth.js?v=5.9.76-account-owner-boundary-1',
        '/auth-controller.js?v=5.9.76-workspace-opened-retry-1',
        '/_vercel/insights/script.js',
        '/_vercel/speed-insights/script.js',
    ]


def test_workspace_runtime_is_complete_idempotent_and_authentication_gated():
    shell = read('app.html')
    runtime = read('runtime-body-v1.js')
    controller = read('auth-controller.js')

    deferred_assets = [
        '/billing.css',
        '/onboarding.css?v=5.9.76-friendly-workspace-1',
        '/conversation.css?v=5.9.76-muse-release-repair-1',
        '/onboarding.js?v=5.9.76-friendly-workspace-1',
        '/scroll-manager.js?v=5.9.76-muse-release-repair-1',
        '/profile-manager.js?v=5.9.76-account-owner-boundary-1',
        '/billing-manager.js?v=5.9.76-private-owner-boundary-1',
        '/subscription-ui.js?v=5.9.76-private-owner-boundary-1',
        '/credit-confirmation.js?v=5.9.76-private-owner-boundary-1',
        '/chat-resilience.js?v=5.9.76-chat-owner-boundary-1',
        '/ui-functions.js?v=5.9.76-private-owner-boundary-1',
        '/presence-manager.js?v=5.9.76-native-push-owner-fence-1',
        '/crump-design-pass.css?v=5.9.76-ui-release-audit-2',
        '/crump-activity-center-1.0.css?v=5.9.76-autonomous-continuity-1',
        '/crump-ui-guardrails.css?v=5.9.76-ui-guardrails-1',
        '/crump-motion-system.css?v=5.9.76-motion-system-2',
        '/crump-activity-center-1.0.js?v=5.9.76-private-owner-boundary-1',
        '/sync-manager.js?v=5.9.76-auth-boundary-sync-1',
        '/chat-sync.js?v=5.9.76-initial-chat-owner-reconciliation-1',
        '/account-manager.js?v=5.9.76-account-owner-boundary-1',
        '/app.js?v=5.9.76-native-push-owner-fence-1',
        '/product-analytics.js?v=5.9.76-workspace-opened-retry-1',
    ]
    for asset in deferred_assets:
        assert asset not in shell
        assert asset in runtime

    assert 'let runtimePromise = null;' in runtime
    assert 'if (runtimePromise) return runtimePromise;' in runtime
    assert 'window.CrumpWorkspaceRuntime = Object.freeze({load});' in runtime
    assert "document.documentElement.dataset.crumpBodyRuntime = 'failed';" in runtime
    assert "Your sign-in is safe—check your connection and reload to try again." in runtime
    assert "void load().catch(() => {});" in runtime
    assert "document.addEventListener('DOMContentLoaded', () => { void boot();" not in runtime

    assert 'async function prepareAuthenticatedWorkspace()' in controller
    assert controller.count('await prepareAuthenticatedWorkspace();') == 3
    bootstrap = controller[controller.index('  async function bootstrap()'):controller.index('  function wireNavigation()')]
    assert bootstrap.rindex('await prepareAuthenticatedWorkspace();') < bootstrap.rindex('activeUser = session.data.user;')
    login = controller[controller.index('  function wireLogin()'):controller.index('  function wireRegistration()')]
    assert login.index('await prepareAuthenticatedWorkspace();') < login.index('activeUser = result.data.user;')
    bootstrap_catch = controller[controller.rindex("bootstrap().catch(error =>") :]
    assert "showAuth('login');" in bootstrap_catch
    assert "error?.message" in bootstrap_catch
    assert "Your sign-in is safe" in bootstrap_catch


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
