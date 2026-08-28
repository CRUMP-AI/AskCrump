(function initializeInstallPrompt() {
    'use strict';

    const storage = window.safeStorage || window.localStorage;
    const installedKey = 'crump_pwa_installed';
    let deferredPrompt = null;
    let installButton = null;
    let serviceWorkerRegistration = null;
    let updateNotice = null;
    let updateCheckStartedAt = 0;
    let runtimeUpdateHandled = false;
    let runtimeUpdatePending = false;
    let reloadStarted = false;

    const updateCheckIntervalMs = 60_000;
    const reloadGuardKey = 'crump_runtime_reload_started_at';

    function authFormHasWork() {
        const authContainer = document.getElementById('authContainer');
        if (!authContainer) return false;
        const hasValue = Array.from(authContainer.querySelectorAll('input')).some(input => Boolean(input.value));
        const hasBusyForm = Boolean(authContainer.querySelector('form button:disabled, form[aria-busy="true"]'));
        return hasValue || hasBusyForm;
    }

    function reloadForRuntimeUpdate() {
        if (reloadStarted) return;
        reloadStarted = true;
        try {
            const lastReload = Number(window.sessionStorage.getItem(reloadGuardKey) || 0);
            if (lastReload && Date.now() - lastReload < 15_000) {
                reloadStarted = false;
                showRuntimeUpdateNotice();
                return;
            }
            window.sessionStorage.setItem(reloadGuardKey, String(Date.now()));
        } catch (_) {}
        window.location.reload();
    }

    function showRuntimeUpdateNotice() {
        if (updateNotice) return;
        updateNotice = document.createElement('section');
        updateNotice.className = 'runtime-update-notice';
        updateNotice.setAttribute('role', 'status');
        updateNotice.setAttribute('aria-live', 'polite');
        updateNotice.innerHTML = `
            <div>
                <strong>Ask Crump is ready to update.</strong>
                <span>Reload to use the latest sign-in and reliability fixes.</span>
            </div>
            <button type="button" class="runtime-update-action">Reload now</button>
            <button type="button" class="runtime-update-later" aria-label="Dismiss update notice">Later</button>
        `;
        updateNotice.querySelector('.runtime-update-action')?.addEventListener('click', reloadForRuntimeUpdate);
        updateNotice.querySelector('.runtime-update-later')?.addEventListener('click', () => {
            updateNotice?.remove();
            updateNotice = null;
        });
        document.body.appendChild(updateNotice);
        requestAnimationFrame(() => updateNotice?.classList.add('visible'));
    }

    function handleRuntimeUpdate() {
        if (runtimeUpdateHandled) return;
        runtimeUpdateHandled = true;
        runtimeUpdatePending = true;
        window.setTimeout(() => {
            // A signed-out page with no entered credentials is safe to refresh. Keep
            // drafts and in-flight authentication input under the user's control.
            if (!window.currentUser && !authFormHasWork()) reloadForRuntimeUpdate();
            else showRuntimeUpdateNotice();
        }, 250);
    }

    async function checkForRuntimeUpdate({force = false} = {}) {
        if (!serviceWorkerRegistration) return;
        const now = Date.now();
        if (!force && now - updateCheckStartedAt < updateCheckIntervalMs) return;
        updateCheckStartedAt = now;
        try {
            await serviceWorkerRegistration.update();
        } catch (error) {
            console.warn('[Service worker] Update check unavailable:', error);
        }
    }

    function isInstalled() {
        return Boolean(window.CrumpAPI?.isNative)
            || window.matchMedia('(display-mode: standalone)').matches
            || window.navigator.standalone === true
            || storage.getItem(installedKey) === 'true';
    }

    function isAppVisible() {
        const app = document.getElementById('appContainer');
        if (!app || app.hidden || app.style.display === 'none') return false;
        return !document.querySelector('.modal.active, .account-modal, .auth-container[style*="flex"]');
    }

    function removeInstallButton() {
        installButton?.remove();
        installButton = null;
    }

    function showInstalledNotice() {
        const notice = document.createElement('div');
        notice.className = 'install-toast';
        notice.setAttribute('role', 'status');
        notice.textContent = 'Ask Crump was installed.';
        document.body.appendChild(notice);
        requestAnimationFrame(() => notice.classList.add('visible'));
        setTimeout(() => {
            notice.classList.remove('visible');
            setTimeout(() => notice.remove(), 200);
        }, 2400);
    }

    async function requestInstallation() {
        if (!deferredPrompt) return;

        installButton.disabled = true;
        try {
            deferredPrompt.prompt();
            const { outcome } = await deferredPrompt.userChoice;
            if (outcome === 'accepted') {
                storage.setItem(installedKey, 'true');
                showInstalledNotice();
            }
        } catch (error) {
            console.error('[Install] Browser install prompt failed:', error);
        } finally {
            deferredPrompt = null;
            removeInstallButton();
        }
    }

    function renderInstallButton() {
        if (installButton || !deferredPrompt || !isAppVisible() || isInstalled()) return;

        installButton = document.createElement('button');
        installButton.type = 'button';
        installButton.className = 'install-button';
        installButton.setAttribute('aria-label', 'Install Ask Crump');
        installButton.innerHTML = `
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 3v12"></path>
                <path d="m7 10 5 5 5-5"></path>
                <path d="M5 21h14"></path>
            </svg>
            <span>Install app</span>
        `;
        installButton.addEventListener('click', requestInstallation, { once: true });
        document.body.appendChild(installButton);
        requestAnimationFrame(() => installButton?.classList.add('visible'));
    }

    function observeAppVisibility() {
        const app = document.getElementById('appContainer');
        if (!app) return;
        const observer = new MutationObserver(() => {
            if (isAppVisible()) renderInstallButton();
            else removeInstallButton();
        });
        observer.observe(app, { attributes: true, attributeFilter: ['hidden', 'style', 'class'] });
    }

    function initialize() {
        if (isInstalled()) return;

        window.addEventListener('beforeinstallprompt', event => {
            event.preventDefault();
            deferredPrompt = event;
            renderInstallButton();
        });

        window.addEventListener('appinstalled', () => {
            storage.setItem(installedKey, 'true');
            deferredPrompt = null;
            removeInstallButton();
            showInstalledNotice();
        });

        observeAppVisibility();
    }

    if (!window.CrumpAPI?.isNative && 'serviceWorker' in navigator) {
        let wasControlledAtBoot = Boolean(navigator.serviceWorker.controller);
        navigator.serviceWorker.addEventListener('controllerchange', () => {
            if (!wasControlledAtBoot) {
                // The first controller owns the same fresh runtime that registered it.
                wasControlledAtBoot = true;
                return;
            }
            handleRuntimeUpdate();
        });

        window.addEventListener('load', async () => {
            try {
                serviceWorkerRegistration = await navigator.serviceWorker.register('/sw.js');
                await checkForRuntimeUpdate({force: true});
            } catch (error) {
                console.error('[Service worker] Registration failed:', error);
            }
        }, { once: true });

        document.addEventListener('visibilitychange', () => {
            if (document.hidden) return;
            if (runtimeUpdatePending && !updateNotice) showRuntimeUpdateNotice();
            void checkForRuntimeUpdate();
        });
        window.addEventListener('pageshow', () => {
            if (runtimeUpdatePending && !updateNotice) showRuntimeUpdateNotice();
            void checkForRuntimeUpdate();
        });
        window.addEventListener('online', () => { void checkForRuntimeUpdate({force: true}); });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize, { once: true });
    } else {
        initialize();
    }
}());
