// ==========================================
// CRUMP AI - PWA MANAGER v2.0
// Auto-updates + Install Button + Update Notifications
// ==========================================

class PWAManager {
    constructor() {
        this.deferredPrompt = null;
        this.registration = null;
        this.updateAvailable = false;
        this.updateReady = false;
        
        console.log('📱 PWA Manager v2.0 initializing...');
        this.init();
    }

    async init() {
        // Register service worker
        await this.registerServiceWorker();
        
        // Setup install prompt listener
        this.setupInstallPrompt();
        
        // Setup update checker
        this.setupUpdateChecker();
        
        // Create install button
        this.createInstallButton();
        
        // Show install prompt if not installed
        this.checkInstallStatus();
        
        console.log('✅ PWA Manager ready');
    }

    // ==========================================
    // SERVICE WORKER REGISTRATION
    // ==========================================
    async registerServiceWorker() {
        if (!('serviceWorker' in navigator)) {
            console.warn('⚠️ Service Worker not supported');
            return;
        }

        try {
            this.registration = await navigator.serviceWorker.register('/sw.js', {
                scope: '/'
            });

            console.log('✅ Service Worker registered:', this.registration.scope);

            // Check for updates on load
            this.registration.update();

            // Listen for updates
            this.registration.addEventListener('updatefound', () => {
                console.log('🔄 Update found - installing...');
                this.handleUpdateFound();
            });

            // Listen for controller change (new service worker activated)
            navigator.serviceWorker.addEventListener('controllerchange', () => {
                console.log('🔄 New service worker activated');
                this.handleControllerChange();
            });

        } catch (error) {
            console.error('❌ Service Worker registration failed:', error);
        }
    }

    // ==========================================
    // UPDATE HANDLING
    // ==========================================
    handleUpdateFound() {
        const newWorker = this.registration.installing;
        
        newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                // Update available
                console.log('✅ Update installed and ready');
                this.updateReady = true;
                this.showUpdateNotification();
            }
        });
    }

    handleControllerChange() {
        // Only reload if we explicitly asked for an update
        if (this.updateReady) {
            console.log('🔄 Reloading to activate update...');
            window.location.reload();
        }
    }

    showUpdateNotification() {
        const notification = document.createElement('div');
        notification.className = 'pwa-update-notification';
        notification.innerHTML = `
            <div class="update-content">
                <div class="update-icon">🔄</div>
                <div class="update-text">
                    <strong>Update Available</strong>
                    <p>A new version of Crump AI is ready</p>
                </div>
                <button class="update-btn" id="updateBtn">Update Now</button>
                <button class="update-close" id="updateLaterBtn">×</button>
            </div>
        `;

        notification.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: var(--bg-secondary);
            border: 2px solid var(--accent-primary);
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
            z-index: 10000;
            max-width: 400px;
            width: 90%;
            animation: slideUp 0.4s ease;
        `;

        document.body.appendChild(notification);

        // Update button
        document.getElementById('updateBtn').addEventListener('click', () => {
            this.applyUpdate();
            notification.remove();
        });

        // Later button
        document.getElementById('updateLaterBtn').addEventListener('click', () => {
            notification.remove();
        });
    }

    async applyUpdate() {
        if (!this.registration || !this.registration.waiting) {
            console.warn('⚠️ No update waiting');
            return;
        }

        console.log('🔄 Applying update...');

        // Tell service worker to skip waiting
        this.registration.waiting.postMessage({ type: 'SKIP_WAITING' });
        
        // Show loading indicator
        if (window.showToast) {
            window.showToast('Updating Crump AI...', 'info');
        }
    }

    // ==========================================
    // AUTO UPDATE CHECKER
    // ==========================================
    setupUpdateChecker() {
        // Check for updates every 30 minutes
        setInterval(() => {
            if (this.registration) {
                console.log('🔍 Checking for updates...');
                this.registration.update();
            }
        }, 30 * 60 * 1000);

        // Check for updates when page becomes visible
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.registration) {
                console.log('🔍 Page visible - checking for updates...');
                this.registration.update();
            }
        });

        // Check for updates on network reconnection
        window.addEventListener('online', () => {
            if (this.registration) {
                console.log('🔍 Back online - checking for updates...');
                this.registration.update();
            }
        });
    }

    // ==========================================
    // INSTALL PROMPT
    // ==========================================
    setupInstallPrompt() {
        window.addEventListener('beforeinstallprompt', (e) => {
            console.log('📱 Install prompt available');
            
            // Prevent default prompt
            e.preventDefault();
            
            // Store event for later
            this.deferredPrompt = e;
            
            // Show install button
            this.showInstallButton();
        });

        // Listen for successful install
        window.addEventListener('appinstalled', () => {
            console.log('✅ PWA installed successfully');
            this.deferredPrompt = null;
            this.hideInstallButton();
            
            if (window.showToast) {
                window.showToast('🎉 Crump AI installed successfully!', 'success');
            }
        });
    }

    // ==========================================
    // INSTALL BUTTON
    // ==========================================
    createInstallButton() {
        // Create button but keep it hidden initially
        const button = document.createElement('button');
        button.id = 'pwaInstallBtn';
        button.className = 'pwa-install-btn hidden';
        button.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            <span>Install App</span>
        `;

        button.style.cssText = `
            position: fixed;
            bottom: 80px;
            right: 20px;
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 12px 20px;
            background: var(--accent-primary);
            color: var(--bg-primary);
            border: none;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(212, 175, 55, 0.4);
            z-index: 1000;
            transition: all 0.3s ease;
        `;

        button.addEventListener('click', () => this.promptInstall());

        // Add hover effect
        button.addEventListener('mouseenter', () => {
            button.style.transform = 'translateY(-2px)';
            button.style.boxShadow = '0 6px 16px rgba(212, 175, 55, 0.6)';
        });

        button.addEventListener('mouseleave', () => {
            button.style.transform = 'translateY(0)';
            button.style.boxShadow = '0 4px 12px rgba(212, 175, 55, 0.4)';
        });

        document.body.appendChild(button);
    }

    showInstallButton() {
        const button = document.getElementById('pwaInstallBtn');
        if (button) {
            button.classList.remove('hidden');
            button.style.display = 'flex';
            button.style.animation = 'slideInRight 0.4s ease';
        }
    }

    hideInstallButton() {
        const button = document.getElementById('pwaInstallBtn');
        if (button) {
            button.style.animation = 'slideOutRight 0.4s ease';
            setTimeout(() => {
                button.classList.add('hidden');
                button.style.display = 'none';
            }, 400);
        }
    }

    async promptInstall() {
        if (!this.deferredPrompt) {
            console.warn('⚠️ Install prompt not available');
            
            // Show manual install instructions
            this.showManualInstallInstructions();
            return;
        }

        console.log('📱 Showing install prompt...');

        // Show the install prompt
        this.deferredPrompt.prompt();

        // Wait for user response
        const { outcome } = await this.deferredPrompt.userChoice;

        console.log(`📱 User ${outcome} the install`);

        if (outcome === 'accepted') {
            this.hideInstallButton();
        }

        // Clear the prompt
        this.deferredPrompt = null;
    }

    // ==========================================
    // MANUAL INSTALL INSTRUCTIONS
    // ==========================================
    showManualInstallInstructions() {
        const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
        const isSafari = /Safari/.test(navigator.userAgent) && !/Chrome/.test(navigator.userAgent);

        let instructions = '';

        if (isIOS && isSafari) {
            instructions = `
                <h3>Install on iOS</h3>
                <ol>
                    <li>Tap the <strong>Share</strong> button (square with arrow)</li>
                    <li>Scroll down and tap <strong>"Add to Home Screen"</strong></li>
                    <li>Tap <strong>"Add"</strong> in the top right</li>
                </ol>
            `;
        } else {
            instructions = `
                <h3>Install Crump AI</h3>
                <p>To install this app:</p>
                <ol>
                    <li>Open your browser menu</li>
                    <li>Look for <strong>"Install app"</strong> or <strong>"Add to Home Screen"</strong></li>
                    <li>Follow the prompts</li>
                </ol>
            `;
        }

        const modal = document.createElement('div');
        modal.className = 'modal active';
        modal.innerHTML = `
            <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
            <div class="modal-content" style="max-width: 500px;">
                <div class="modal-header">
                    <h2>Install App</h2>
                    <button class="btn-icon" onclick="this.closest('.modal').remove()">
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                            <path d="M15 5L5 15M5 5l10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                    </button>
                </div>
                <div class="modal-body">
                    ${instructions}
                    <button class="btn btn-primary btn-block" onclick="this.closest('.modal').remove()">
                        Got it
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
    }

    // ==========================================
    // CHECK INSTALL STATUS
    // ==========================================
    checkInstallStatus() {
        // Check if already installed
        if (window.matchMedia('(display-mode: standalone)').matches || 
            window.navigator.standalone === true) {
            console.log('📱 App is installed');
            this.hideInstallButton();
            return;
        }

        // Check if install prompt is available
        if (this.deferredPrompt) {
            this.showInstallButton();
        } else {
            // Wait a bit for the prompt to fire
            setTimeout(() => {
                if (this.deferredPrompt) {
                    this.showInstallButton();
                }
            }, 3000);
        }
    }

    // ==========================================
    // PUBLIC API
    // ==========================================
    isInstalled() {
        return window.matchMedia('(display-mode: standalone)').matches || 
               window.navigator.standalone === true;
    }

    async checkForUpdates() {
        if (this.registration) {
            await this.registration.update();
        }
    }

    getInstallStatus() {
        return {
            installed: this.isInstalled(),
            installable: this.deferredPrompt !== null,
            updateAvailable: this.updateReady
        };
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.pwaManager = new PWAManager();

// Export for other modules
window.PWAManager = PWAManager;

console.log('✅ PWA Manager v2.0 loaded - Auto-updates enabled');
