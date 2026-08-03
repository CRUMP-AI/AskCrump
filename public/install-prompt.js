(function initializeInstallPrompt() {
    'use strict';

    const storage = window.safeStorage || window.localStorage;
    const installedKey = 'crump_pwa_installed';
    let deferredPrompt = null;
    let installButton = null;

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
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js').catch(error => {
                console.error('[Service worker] Registration failed:', error);
            });
        }, { once: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize, { once: true });
    } else {
        initialize();
    }
}());
