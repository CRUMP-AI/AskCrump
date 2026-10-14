from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_autonomous_vision_controls_are_fail_closed_and_follow_feature_availability():
    loader = read("public/crump-code-loader.js")
    shell = read("public/crump-vision-shell-1.0.js")
    browser_proof = read("scripts/verify-code-lazy-load.cjs")

    assert 'data-crump-code-destination hidden disabled aria-hidden="true"' in shell
    assert '[data-cv-destination="autonomous"]' in loader
    assert "destination.hidden = !isConfigured" in loader
    assert "destination.disabled = !isConfigured" in loader
    assert "destination.toggleAttribute('aria-hidden', !isConfigured)" in loader
    assert "Autonomous Crump is not available for this account." in loader
    assert "window.addEventListener('crumpvision:ready'" in loader

    assert 'data-cv-destination="autonomous" data-crump-code-destination hidden disabled' in browser_proof
    assert "visionDisabled: [true, true, true]" in browser_proof
    assert "results.locked.visionDisabled, [false, false, false]" in browser_proof
    assert "results.entitled.visionDisabled, [false, false, false]" in browser_proof


def test_files_cold_start_owns_busy_feedback_and_visible_vision_controls():
    loader = read("public/crump-product-loader.js")
    browser_proof = read("scripts/verify-product-studio-lazy-load.cjs")

    assert "new Set(['projects', 'files', 'manuscripts', 'video', 'library'])" in loader
    assert "files: 'Files'" in loader
    assert '[data-cv-destination="${normalized}"]' in loader
    assert "openFiles: () => invoke('openFiles', [], {destination: 'files', announce: true})" in loader
    assert "openFiles: facade.openFiles" in loader

    assert "Opening Files…" in browser_proof
    assert "coldFilesBusy.filesBusy.every(value => value === 'true')" in browser_proof
    assert "coldFilesBusy.filesDisabled.every(Boolean)" in browser_proof
    assert "opened.filesActive, true" in browser_proof
    assert "afterLegacyProjectSync.filesActive, true" in browser_proof
    assert "afterLegacyProjectSync.projectsActive, false" in browser_proof


def test_files_is_a_first_class_surface_with_lazy_active_state_recovery():
    product = read("public/crump-product-5.3.js")
    shell = read("public/crump-vision-shell-1.0.js")
    browser_proof = read("scripts/verify-studio-section-isolation.cjs")

    assert "back.hidden = !isOpen || normalized === 'files'" in product
    assert "kicker.textContent = 'PRIVATE FILES'" in product
    assert "title.textContent = 'Files'" in product
    assert "close?.setAttribute('aria-label', 'Close Files')" in product
    assert "new CustomEvent('crump:product-view-changed'" in product
    assert "destination: normalized === 'files' ? 'files' : 'projects'" in product

    assert "function filesNavigationIsPending()" in shell
    assert "function filesSurfaceIsOpen()" in shell
    assert "function bindProductSurfaceObservers()" in shell
    assert "attributeFilter: ['data-project-view', 'data-crump53-section']" in shell
    assert "insertionObserver.observe(document.body, {childList: true, subtree: true})" in shell
    assert "document.addEventListener('crump:product-view-changed'" in shell
    navigation = read("public/crump-navigation-5.9.30.js")
    assert "function destinationControlIsVisible(button)" in navigation
    assert "restoreDestinationFocus(previous)" in navigation
    assert "visibleDestinationButton('more')" in navigation

    assert "'PRIVATE FILES'" in browser_proof
    assert "'#crump53ProjectBack').isHidden(), true" in browser_proof
    assert "'Ask Crump Files'" in browser_proof

