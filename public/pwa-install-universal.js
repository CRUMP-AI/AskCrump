// ==========================================
// ONE-CLICK PWA INSTALL - SIMPLIFIED
// No modals, no instructions - just works
// ==========================================

(function() {
    'use strict';
    
    let deferredPrompt = null;
    let installButton = null;
    
    // Check if already installed
    function isPWAInstalled() {
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true ||
               localStorage.getItem('crump_pwa_installed') === 'true' ||
               localStorage.getItem('crump_pwa_install_prompted') === 'true';
    }
    
    // Check if main app is visible (not onboarding/splash) and no modals/sidebars are open
    function isMainAppVisible() {
        const appContainer = document.getElementById('appContainer');
        const sidebar = document.getElementById('sidebar');
        const settingsModal = document.getElementById('settingsModal');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        
        // Check if app container is visible
        const appVisible = appContainer && appContainer.style.display !== 'none';
        
        // Check if sidebar is open
        const sidebarOpen = sidebar && sidebar.classList.contains('active');
        
        // Check if any modal is open (settings or others)
        const modalOpen = settingsModal && settingsModal.style.display !== 'none';
        
        // Check if sidebar overlay is visible
        const overlayVisible = sidebarOverlay && 
                               window.getComputedStyle(sidebarOverlay).display !== 'none';
        
        // Only show if app is visible AND no sidebar/modal is open
        return appVisible && !sidebarOpen && !modalOpen && !overlayVisible;
    }
    
    // Create floating install button
    function createInstallButton() {
        // Remove old banner if it exists
        const oldBanner = document.getElementById('pwaInstallBanner');
        if (oldBanner) {
            oldBanner.remove();
        }
        
        // Create new floating button
        installButton = document.createElement('button');
        installButton.className = 'pwa-install-floating';
        installButton.setAttribute('aria-label', 'Install App');
        installButton.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Install App
        `;
        
        installButton.addEventListener('click', handleInstallClick);
        document.body.appendChild(installButton);
        
        console.log('[PWA] Install button created');
    }
    
    // Show the install button
    function showInstallButton() {
        // Only show if main app is visible and no modals/sidebars open
        if (!isMainAppVisible()) {
            console.log('[PWA] Main app not visible or modal/sidebar open, skipping install button');
            return;
        }
        
        if (!installButton) {
            createInstallButton();
        }
        
        // Small delay for smooth animation
        setTimeout(() => {
            if (installButton && isMainAppVisible()) {
                installButton.classList.add('visible');
                console.log('[PWA] Install button shown');
            }
        }, 100);
    }
    
    // Hide the install button
    function hideInstallButton() {
        if (installButton) {
            installButton.classList.remove('visible');
            setTimeout(() => {
                if (installButton && installButton.parentNode) {
                    installButton.remove();
                    installButton = null;
                }
            }, 300);
        }
    }
    
    // Handle install button click
    async function handleInstallClick() {
        if (!deferredPrompt) {
            // For browsers/platforms without native install prompt (iOS Safari, etc.)
            showFallbackInstructions();
            return;
        }
        
        // Hide button immediately
        hideInstallButton();
        
        try {
            // Show native install prompt
            deferredPrompt.prompt();
            
            // Wait for user response
            const { outcome } = await deferredPrompt.userChoice;
            
            console.log('[PWA] Install outcome:', outcome);
            
            if (outcome === 'accepted') {
                localStorage.setItem('crump_pwa_installed', 'true');
                showSuccessToast();
            }
            
            deferredPrompt = null;
            
        } catch (error) {
            console.error('[PWA] Install error:', error);
            showFallbackInstructions();
        }
    }
    
    // Fallback instructions for unsupported browsers
    function showFallbackInstructions() {
        const platform = detectPlatform();
        let message = '';
        
        if (platform === 'ios') {
            message = 'To install:\n\n1. Tap the Share button (square with arrow)\n2. Select "Add to Home Screen"\n3. Tap "Add"';
        } else if (platform === 'android') {
            message = 'To install:\n\n1. Tap the menu (⋮)\n2. Select "Add to Home screen"\n3. Tap "Add"';
        } else {
            message = 'To install:\n\nLook for the install icon in your browser\'s address bar or menu.';
        }
        
        alert(message);
        
        // Mark as shown so we don't keep prompting the user
        localStorage.setItem('crump_pwa_install_prompted', 'true');
        hideInstallButton();
    }
    
    // Detect platform
    function detectPlatform() {
        const ua = navigator.userAgent;
        if (/iPad|iPhone|iPod/.test(ua) && !window.MSStream) return 'ios';
        if (/Android/.test(ua)) return 'android';
        return 'desktop';
    }
    
    // Show success toast
    function showSuccessToast() {
        const toast = document.createElement('div');
        toast.className = 'pwa-toast';
        toast.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <span>App installed successfully!</span>
        `;
        
        document.body.appendChild(toast);
        
        // Show toast
        setTimeout(() => toast.classList.add('visible'), 10);
        
        // Hide and remove after 3 seconds
        setTimeout(() => {
            toast.classList.remove('visible');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
    
    // Check visibility and toggle button
    function checkVisibilityAndToggle() {
        if (isMainAppVisible() && deferredPrompt && !installButton) {
            showInstallButton();
        } else if (!isMainAppVisible() && installButton) {
            hideInstallButton();
        }
    }
    
    // Initialize
    function init() {
        console.log('[PWA] One-click installer initializing...');
        
        // Don't show if already installed
        if (isPWAInstalled()) {
            console.log('[PWA] App already installed');
            return;
        }
        
        // Listen for the install prompt event
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            console.log('[PWA] Install prompt available');
            showInstallButton();
        });
        
        // Listen for successful installation
        window.addEventListener('appinstalled', () => {
            console.log('[PWA] App installed');
            localStorage.setItem('crump_pwa_installed', 'true');
            hideInstallButton();
            showSuccessToast();
        });
        
        // For browsers that don't fire beforeinstallprompt (Safari, etc.)
        // Show button after 3 seconds if no native prompt appeared
        setTimeout(() => {
            if (!deferredPrompt && !isPWAInstalled()) {
                const platform = detectPlatform();
                // Only show for iOS/Android where manual install is possible
                if (platform === 'ios' || platform === 'android') {
                    console.log('[PWA] Showing manual install button for', platform);
                    showInstallButton();
                }
            }
        }, 3000);
        
        // Watch for various UI changes that might affect visibility
        const observer = new MutationObserver(checkVisibilityAndToggle);
        
        // Observe multiple elements
        const appContainer = document.getElementById('appContainer');
        const sidebar = document.getElementById('sidebar');
        const settingsModal = document.getElementById('settingsModal');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        
        if (appContainer) {
            observer.observe(appContainer, { 
                attributes: true, 
                attributeFilter: ['style'] 
            });
        }
        
        if (sidebar) {
            observer.observe(sidebar, { 
                attributes: true, 
                attributeFilter: ['class'] 
            });
        }
        
        if (settingsModal) {
            observer.observe(settingsModal, { 
                attributes: true, 
                attributeFilter: ['style'] 
            });
        }
        
        if (sidebarOverlay) {
            observer.observe(sidebarOverlay, { 
                attributes: true, 
                attributeFilter: ['style'] 
            });
        }
        
        // Also listen for click events on sidebar/modal controls
        document.addEventListener('click', (e) => {
            // Small delay to let animations complete
            setTimeout(checkVisibilityAndToggle, 100);
        });
    }
    
    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
    console.log('[PWA] One-click installer loaded');
    
})();
