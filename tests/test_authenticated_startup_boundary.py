from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def read(name: str) -> str:
    return (PUBLIC / name).read_text(encoding='utf-8')


def test_auth_controller_announces_server_confirmed_workspace_readiness():
    source = read('auth-controller.js')

    initialize = 'window.initializeAuthenticatedApp?.(activeUser);'
    announce = "window.dispatchEvent(new Event('crump:authenticated-ready'));"
    assert initialize in source
    assert announce in source
    assert source.index(initialize) < source.index(announce)


def test_protected_product_modules_hydrate_only_after_an_intentional_open():
    product = read('crump-product-5.3.js')
    code = read('crump-code-5.9.35.js')
    library = read('crump-library-5.7.js')
    billing = read('crump-billing-5.1.js')

    assert 'if (authenticatedHydrationStarted || !window.currentUser) return;' in product
    assert 'if (!readProjectRoute()) return;' in product
    assert "openStudio('projects', {preserveProjectRoute: true});" in product
    assert "window.addEventListener('crump:authenticated-ready', () => {" in product
    assert "hydrateAuthenticatedState();" in product
    assert "resumePendingVideoJob();" in product
    assert "if (section === 'projects')" in product
    assert "else if (section === 'video')" in product
    assert 'void refreshFeatures();' in product
    assert 'if (projectRefreshPromise) return projectRefreshPromise;' in product
    assert 'if (window.currentUser) void refreshBooks();' not in library
    assert "window.addEventListener('crump:authenticated-ready'" in library
    assert 'if (!state.installed) installWhenReady();' in library
    assert "window.addEventListener('crump:authenticated-ready', () => void refreshAvailability())" in code
    auth_listener = code.index("window.addEventListener('crump:authenticated-ready'")
    assert "loadProjects()" not in code[auth_listener:]
    assert 'if (!(await refreshAvailability()))' in code
    assert 'if (window.currentUser) refreshBalance();' in billing
    assert "window.addEventListener('crump:authenticated-ready', () => refreshBalance())" in billing


def test_signed_out_initializers_do_not_directly_hydrate_protected_data():
    product = read('crump-product-5.3.js')
    billing = read('crump-billing-5.1.js')

    product_init = product[product.index('  function init()'):]
    assert '    hydrateAuthenticatedState();' in product_init
    assert '    void refreshProjects();\n    void refreshFeatures();' not in product_init

    billing_boot = billing[billing.index('  function boot()'):]
    assert '    if (window.currentUser) refreshBalance();' in billing_boot
