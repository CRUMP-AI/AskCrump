// ==========================================
// CRUMP AI - PWA INSTALLER v2.0
// Claude-level installation experience
// ==========================================

class PWAInstaller {
    constructor() {
        this.deferredPrompt = null;
        this.isInstalled = this.checkIfInstalled();
        this.isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
        this.isAndroid = /Android/.test(navigator.userAgent);
        this.installBannerDismissed = localStorage.getItem('crump_install_dismissed') === 'true';
        
        this.init();
        console.log('📱 PWA Installer v2.0 initialized');
    }

    init() {
        // Listen for install prompt
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            console.log('💾 Install prompt ready');
            
            // Show install UI if not dismissed and not installed
            if (!this.installBannerDismissed && !this.isInstalled) {
                this.showInstallPrompt();
            }
        });

        // Listen for successful installation
        window.addEventListener('appinstalled', () => {
            console.log('✅ PWA installed successfully');
            this.isInstalled = true;
            this.hideInstallPrompt();
            this.showSuccessNotification();
            localStorage.setItem('crump_pwa_installed', 'true');
        });

        // Check if already installed
        if (this.isInstalled) {
            console.log('✅ Running as installed PWA');
            this.hideInstallPrompt();
        }

        // iOS-specific handling
        if (this.isIOS && !this.isInstalled && !this.installBannerDismissed) {
            setTimeout(() => this.showIOSInstructions(), 3000);
        }

        // Add install button to sidebar if applicable
        this.addInstallButtonToSidebar();
    }

    checkIfInstalled() {
        // Check if running as PWA
        if (window.matchMedia('(display-mode: standalone)').matches) {
            return true;
        }
        if (window.navigator.standalone === true) {
            return true; // iOS
        }
        if (localStorage.getItem('crump_pwa_installed') === 'true') {
            return true;
        }
        return false;
    }

    showInstallPrompt() {
        // Don't show if already shown or dismissed
        if (document.getElementById('pwa-install-banner')) return;

        const banner = document.createElement('div');
        banner.id = 'pwa-install-banner';
        banner.className = 'pwa-install-banner';
        banner.innerHTML = `
            <div class="pwa-install-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
            </div>
            <div class="pwa-install-content">
                <h3>Install Crump AI</h3>
                <p>Get the full app experience with offline access</p>
            </div>
            <div class="pwa-install-actions">
                <button class="pwa-install-btn pwa-btn-dismiss" onclick="window.pwaInstaller.dismissInstallPrompt()">
                    Not Now
                </button>
                <button class="pwa-install-btn pwa-btn-install" onclick="window.pwaInstaller.installApp()">
                    Install
                </button>
            </div>
        `;

        document.body.appendChild(banner);
        
        // Animate in
        requestAnimationFrame(() => {
            banner.classList.add('visible');
        });

        console.log('📱 Install banner shown');
    }

    showIOSInstructions() {
        if (this.isInstalled || this.installBannerDismissed) return;

        const modal = document.createElement('div');
        modal.id = 'ios-install-modal';
        modal.className = 'modal active';
        modal.innerHTML = `
            <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
            <div class="modal-content" style="max-width: 400px;">
                <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
                
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent-primary)" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                </div>
                
                <h2 style="text-align: center; margin-bottom: 1rem;">Install Crump AI</h2>
                
                <p style="color: var(--color-text-secondary); margin-bottom: 1.5rem; text-align: center;">
                    To install Crump on your iPhone or iPad:
                </p>
                
                <ol style="color: var(--color-text-secondary); margin-bottom: 2rem; padding-left: 1.5rem; line-height: 1.8;">
                    <li>Tap the <strong>Share</strong> button <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" style="vertical-align: middle;"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg></li>
                    <li>Scroll down and tap <strong>"Add to Home Screen"</strong></li>
                    <li>Tap <strong>"Add"</strong> to confirm</li>
                </ol>
                
                <button class="btn-primary btn-block" onclick="this.closest('.modal').remove(); window.pwaInstaller.dismissInstallPrompt();">
                    Got It
                </button>
            </div>
        `;

        document.body.appendChild(modal);
        console.log('📱 iOS install instructions shown');
    }

    async installApp() {
        if (!this.deferredPrompt) {
            console.warn('⚠️ No install prompt available');
            
            // Show iOS instructions if on iOS
            if (this.isIOS) {
                this.showIOSInstructions();
            }
            return;
        }

        try {
            // Show the install prompt
            this.deferredPrompt.prompt();
            
            // Wait for the user's response
            const { outcome } = await this.deferredPrompt.userChoice;
            
            console.log(`📱 Install outcome: ${outcome}`);
            
            if (outcome === 'accepted') {
                console.log('✅ User accepted installation');
                this.hideInstallPrompt();
            } else {
                console.log('❌ User dismissed installation');
            }
            
            // Clear the deferred prompt
            this.deferredPrompt = null;
            
        } catch (error) {
            console.error('❌ Installation error:', error);
        }
    }

    dismissInstallPrompt() {
        this.installBannerDismissed = true;
        localStorage.setItem('crump_install_dismissed', 'true');
        this.hideInstallPrompt();
        console.log('📱 Install prompt dismissed');
    }

    hideInstallPrompt() {
        const banner = document.getElementById('pwa-install-banner');
        if (banner) {
            banner.classList.remove('visible');
            setTimeout(() => banner.remove(), 300);
        }
    }

    showSuccessNotification() {
        if (window.showNotification) {
            window.showNotification('✅ Crump AI installed successfully!', 'success');
        } else {
            console.log('✅ App installed successfully');
        }
    }

    addInstallButtonToSidebar() {
        // Only add if not installed and not iOS (iOS uses share button)
        if (this.isInstalled || this.isIOS) return;

        const checkForSidebar = () => {
            const sidebarFooter = document.querySelector('.sidebar-footer');
            if (!sidebarFooter) {
                setTimeout(checkForSidebar, 100);
                return;
            }

            // Check if button already exists
            if (document.getElementById('install-app-btn')) return;

            const installBtn = document.createElement('button');
            installBtn.id = 'install-app-btn';
            installBtn.className = 'sidebar-footer-btn';
            installBtn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                <span>Install App</span>
            `;
            installBtn.onclick = () => this.installApp();

            // Insert before the first button
            sidebarFooter.insertBefore(installBtn, sidebarFooter.firstChild);
            console.log('📱 Install button added to sidebar');
        };

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', checkForSidebar);
        } else {
            checkForSidebar();
        }
    }

    // Reset for testing
    reset() {
        localStorage.removeItem('crump_install_dismissed');
        localStorage.removeItem('crump_pwa_installed');
        this.installBannerDismissed = false;
        console.log('🔄 PWA installer reset');
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.pwaInstaller = new PWAInstaller();
window.PWAInstaller = PWAInstaller;

console.log('✅ PWA Installer v2.0 loaded');
