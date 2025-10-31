// ==========================================
// CRUMP AI - UNIVERSAL PWA INSTALL SYSTEM
// Works on iOS, Android, Desktop
// ==========================================

class UniversalPWAInstaller {
    constructor() {
        this.deferredPrompt = null;
        this.isStandalone = false;
        this.platform = this.detectPlatform();
        this.installMethod = null;
        
        console.log('[PWA] Detected platform:', this.platform);
        this.init();
    }
    
    detectPlatform() {
        const ua = navigator.userAgent;
        const isIOS = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
        const isAndroid = /Android/.test(ua);
        const isMacOS = /Macintosh/.test(ua);
        const isWindows = /Windows/.test(ua);
        const isSafari = /Safari/.test(ua) && !/Chrome/.test(ua);
        const isChrome = /Chrome/.test(ua);
        
        if (isIOS) return 'ios';
        if (isAndroid && isChrome) return 'android-chrome';
        if (isAndroid) return 'android-other';
        if (isMacOS && isSafari) return 'macos-safari';
        if (isMacOS && isChrome) return 'macos-chrome';
        if (isWindows && isChrome) return 'windows-chrome';
        if (isWindows) return 'windows-other';
        return 'desktop-other';
    }
    
    init() {
        // Check if already installed
        this.isStandalone = window.matchMedia('(display-mode: standalone)').matches ||
                           window.navigator.standalone === true ||
                           localStorage.getItem('crump_pwa_installed') === 'true';
        
        if (this.isStandalone) {
            console.log('[PWA] Already running as installed app');
            this.hideInstallBanner();
            return;
        }
        
        // Check if user dismissed
        const dismissed = localStorage.getItem('crump_pwa_dismissed');
        const dismissedTime = localStorage.getItem('crump_pwa_dismissed_time');
        
        if (dismissed === 'true' && dismissedTime) {
            // Re-show after 7 days
            const daysSinceDismiss = (Date.now() - parseInt(dismissedTime)) / (1000 * 60 * 60 * 24);
            if (daysSinceDismiss < 7) {
                console.log('[PWA] User dismissed recently, not showing banner');
                return;
            }
        }
        
        // Listen for Chrome/Edge install prompt
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            this.installMethod = 'native';
            console.log('[PWA] beforeinstallprompt event captured');
            this.showInstallBanner();
        });
        
        // For platforms without native prompt (iOS, Safari, etc)
        if (!this.deferredPrompt) {
            setTimeout(() => {
                if (!this.isStandalone && !this.deferredPrompt) {
                    this.installMethod = 'manual';
                    this.showInstallBanner();
                }
            }, 3000); // Show after 3 seconds
        }
        
        // Listen for successful install
        window.addEventListener('appinstalled', () => {
            console.log('[PWA] App installed successfully');
            localStorage.setItem('crump_pwa_installed', 'true');
            this.hideInstallBanner();
            this.showSuccessMessage();
        });
    }
    
    showInstallBanner() {
        const banner = document.getElementById('pwaInstallBanner');
        const installBtn = document.getElementById('pwaInstallBtn');
        const dismissBtn = document.getElementById('pwaDismissBtn');
        const installText = document.getElementById('pwaInstallText');
        
        if (!banner) {
            console.error('[PWA] Install banner element not found');
            return;
        }
        
        // Update button text based on platform and install method
        if (installBtn) {
            if (this.installMethod === 'native') {
                installBtn.textContent = 'Install';
            } else {
                installBtn.textContent = 'Show Instructions';
            }
        }
        
        // Update description text based on platform
        if (installText) {
            const descriptions = {
                'ios': 'Tap Share → Add to Home Screen',
                'android-chrome': 'Add to your home screen for quick access',
                'macos-safari': 'Click Share → Add to Dock',
                'default': 'Install for the best experience'
            };
            installText.textContent = descriptions[this.platform] || descriptions.default;
        }
        
        banner.classList.add('visible');
        console.log('[PWA] Install banner shown');
    }
    
    hideInstallBanner() {
        const banner = document.getElementById('pwaInstallBanner');
        if (banner) {
            banner.classList.remove('visible');
        }
    }
    
    async handleInstall() {
        if (this.installMethod === 'native' && this.deferredPrompt) {
            // Native Chrome/Edge install
            this.hideInstallBanner();
            
            try {
                this.deferredPrompt.prompt();
                const { outcome } = await this.deferredPrompt.userChoice;
                
                console.log('[PWA] User choice:', outcome);
                
                if (outcome === 'accepted') {
                    localStorage.setItem('crump_pwa_installed', 'true');
                    this.showSuccessMessage();
                } else {
                    this.markAsDismissed();
                }
                
                this.deferredPrompt = null;
            } catch (error) {
                console.error('[PWA] Install error:', error);
                this.showInstructionsModal();
            }
        } else {
            // Manual install (iOS, Safari, etc)
            this.hideInstallBanner();
            this.showInstructionsModal();
        }
    }
    
    showInstructionsModal() {
        const modal = document.createElement('div');
        modal.className = 'pwa-instructions-modal';
        modal.id = 'pwaInstructionsModal';
        
        const instructions = this.getInstructionsForPlatform();
        
        modal.innerHTML = `
            <div class="pwa-modal-overlay" onclick="this.parentElement.remove()"></div>
            <div class="pwa-modal-content">
                <button class="pwa-modal-close" onclick="this.closest('.pwa-instructions-modal').remove()">×</button>
                
                <div class="pwa-modal-header">
                    <h2>Install Crump AI</h2>
                    <p>Get the full app experience</p>
                </div>
                
                <div class="pwa-instructions">
                    ${instructions.html}
                </div>
                
                <div class="pwa-modal-footer">
                    <button class="pwa-btn-secondary" onclick="document.getElementById('pwaInstructionsModal').remove()">
                        Maybe Later
                    </button>
                    <button class="pwa-btn-primary" onclick="document.getElementById('pwaInstructionsModal').remove(); localStorage.setItem('crump_pwa_shown_instructions', 'true');">
                        Got It
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        setTimeout(() => modal.classList.add('active'), 10);
    }
    
    getInstructionsForPlatform() {
        const instructions = {
            'ios': {
                html: `
                    <div class="instruction-step">
                        <div class="step-number">1</div>
                        <div class="step-content">
                            <strong>Tap the Share button</strong>
                            <p>Located at the bottom of Safari (square with arrow pointing up)</p>
                        </div>
                    </div>
                    <div class="instruction-step">
                        <div class="step-number">2</div>
                        <div class="step-content">
                            <strong>Select "Add to Home Screen"</strong>
                            <p>Scroll down in the share menu to find this option</p>
                        </div>
                    </div>
                    <div class="instruction-step">
                        <div class="step-number">3</div>
                        <div class="step-content">
                            <strong>Tap "Add"</strong>
                            <p>The Crump AI icon will appear on your home screen</p>
                        </div>
                    </div>
                `
            },
            'android-chrome': {
                html: `
                    <div class="instruction-step">
                        <div class="step-number">1</div>
                        <div class="step-content">
                            <strong>Tap the menu button</strong>
                            <p>Three dots in the top-right corner</p>
                        </div>
                    </div>
                    <div class="instruction-step">
                        <div class="step-number">2</div>
                        <div class="step-content">
                            <strong>Select "Add to Home screen" or "Install app"</strong>
                            <p>You may see either option depending on your Chrome version</p>
                        </div>
                    </div>
                    <div class="instruction-step">
                        <div class="step-number">3</div>
                        <div class="step-content">
                            <strong>Tap "Add" or "Install"</strong>
                            <p>Crump AI will be added to your home screen</p>
                        </div>
                    </div>
                `
            },
            'macos-safari': {
                html: `
                    <div class="instruction-step">
                        <div class="step-number">1</div>
                        <div class="step-content">
                            <strong>Click the Share button</strong>
                            <p>Located in the Safari toolbar (square with arrow pointing up)</p>
                        </div>
                    </div>
                    <div class="instruction-step">
                        <div class="step-number">2</div>
                        <div class="step-content">
                            <strong>Select "Add to Dock"</strong>
                            <p>This will add Crump AI to your macOS Dock</p>
                        </div>
                    </div>
                `
            },
            'default': {
                html: `
                    <div class="instruction-step">
                        <div class="step-number">1</div>
                        <div class="step-content">
                            <strong>Look for the install icon</strong>
                            <p>Usually in your browser's address bar or menu</p>
                        </div>
                    </div>
                    <div class="instruction-step">
                        <div class="step-number">2</div>
                        <div class="step-content">
                            <strong>Click "Install" or "Add"</strong>
                            <p>Follow your browser's prompts to install</p>
                        </div>
                    </div>
                `
            }
        };
        
        return instructions[this.platform] || instructions.default;
    }
    
    markAsDismissed() {
        localStorage.setItem('crump_pwa_dismissed', 'true');
        localStorage.setItem('crump_pwa_dismissed_time', Date.now().toString());
        this.hideInstallBanner();
        console.log('[PWA] User dismissed install prompt');
    }
    
    showSuccessMessage() {
        const toast = document.createElement('div');
        toast.className = 'pwa-success-toast';
        toast.innerHTML = `
            <div class="toast-content">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                <span>Crump AI installed successfully!</span>
            </div>
        `;
        
        document.body.appendChild(toast);
        setTimeout(() => toast.classList.add('visible'), 10);
        setTimeout(() => {
            toast.classList.remove('visible');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
    
    // Public method to manually trigger install prompt
    triggerInstall() {
        if (this.isStandalone) {
            console.log('[PWA] Already installed');
            return;
        }
        this.handleInstall();
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.pwaInstaller = new UniversalPWAInstaller();
    });
} else {
    window.pwaInstaller = new UniversalPWAInstaller();
}

// Setup button event listeners
window.addEventListener('load', () => {
    const installBtn = document.getElementById('pwaInstallBtn');
    const dismissBtn = document.getElementById('pwaDismissBtn');
    
    if (installBtn) {
        installBtn.addEventListener('click', () => {
            if (window.pwaInstaller) {
                window.pwaInstaller.handleInstall();
            }
        });
    }
    
    if (dismissBtn) {
        dismissBtn.addEventListener('click', () => {
            if (window.pwaInstaller) {
                window.pwaInstaller.markAsDismissed();
            }
        });
    }
});

console.log('[PWA] Universal installer script loaded');
