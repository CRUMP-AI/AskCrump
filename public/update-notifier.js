// ==========================================
// CRUMP AI - UPDATE NOTIFICATION v1.0
// Notify users of new versions like Claude
// ==========================================

class UpdateNotifier {
    constructor() {
        this.hasUpdate = false;
        this.registration = null;
        this.newWorker = null;
        this.init();
        
        console.log('🔔 Update Notifier initialized');
    }

    async init() {
        if (!('serviceWorker' in navigator)) {
            console.log('❌ Service Worker not supported');
            return;
        }

        // Get the service worker registration
        this.registration = await navigator.serviceWorker.getRegistration();
        
        if (!this.registration) {
            console.log('⚠️ No service worker registered');
            return;
        }

        // Check for updates on load
        this.registration.addEventListener('updatefound', () => {
            this.onUpdateFound();
        });

        // Check if there's already a waiting worker
        if (this.registration.waiting) {
            this.onWaiting(this.registration.waiting);
        }

        // Handle controller change
        navigator.serviceWorker.addEventListener('controllerchange', () => {
            if (this.hasUpdate) {
                window.location.reload();
            }
        });

        // Check for updates periodically (every 30 minutes)
        setInterval(() => {
            this.checkForUpdates();
        }, 30 * 60 * 1000);

        // Check for updates when page becomes visible
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.checkForUpdates();
            }
        });
    }

    onUpdateFound() {
        console.log('🔄 New version found, installing...');
        this.newWorker = this.registration.installing;

        this.newWorker.addEventListener('statechange', () => {
            if (this.newWorker.state === 'installed') {
                if (navigator.serviceWorker.controller) {
                    // New version available
                    this.onWaiting(this.newWorker);
                } else {
                    // First install
                    console.log('✅ App installed successfully');
                }
            }
        });
    }

    onWaiting(worker) {
        this.hasUpdate = true;
        this.newWorker = worker;
        this.showUpdateNotification();
        console.log('✨ New version ready to install');
    }

    showUpdateNotification() {
        // Remove existing notification
        const existing = document.getElementById('update-notification');
        if (existing) existing.remove();

        const notification = document.createElement('div');
        notification.id = 'update-notification';
        notification.className = 'update-notification';
        notification.innerHTML = `
            <div class="update-content">
                <div class="update-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                    </svg>
                </div>
                <div class="update-text">
                    <strong>New Version Available</strong>
                    <span>Update now to get the latest features and improvements</span>
                </div>
            </div>
            <div class="update-actions">
                <button class="update-btn update-btn-later" onclick="window.updateNotifier.dismissUpdate()">
                    Later
                </button>
                <button class="update-btn update-btn-update" onclick="window.updateNotifier.applyUpdate()">
                    Update Now
                </button>
            </div>
        `;

        document.body.appendChild(notification);

        // Animate in
        requestAnimationFrame(() => {
            notification.classList.add('visible');
        });

        console.log('🔔 Update notification shown');
    }

    applyUpdate() {
        if (!this.newWorker) {
            console.warn('⚠️ No new worker available');
            return;
        }

        // Tell the new service worker to skip waiting
        this.newWorker.postMessage({ type: 'SKIP_WAITING' });

        // Show loading state
        const notification = document.getElementById('update-notification');
        if (notification) {
            notification.innerHTML = `
                <div class="update-content">
                    <div class="update-icon">
                        <svg class="spinning" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
                        </svg>
                    </div>
                    <div class="update-text">
                        <strong>Updating...</strong>
                        <span>This will only take a moment</span>
                    </div>
                </div>
            `;
        }

        console.log('🔄 Applying update...');

        // Reload will happen automatically via controllerchange event
    }

    dismissUpdate() {
        const notification = document.getElementById('update-notification');
        if (notification) {
            notification.classList.remove('visible');
            setTimeout(() => notification.remove(), 300);
        }

        // Show again after 1 hour
        setTimeout(() => {
            if (this.hasUpdate) {
                this.showUpdateNotification();
            }
        }, 60 * 60 * 1000);

        console.log('⏰ Update dismissed, will remind in 1 hour');
    }

    async checkForUpdates() {
        if (!this.registration) return;

        try {
            await this.registration.update();
            console.log('🔍 Checked for updates');
        } catch (error) {
            console.error('❌ Update check failed:', error);
        }
    }

    // Force check for updates (exposed for debugging)
    async forceUpdate() {
        console.log('🔄 Forcing update check...');
        await this.checkForUpdates();
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.updateNotifier = new UpdateNotifier();
window.UpdateNotifier = UpdateNotifier;

console.log('✅ Update Notifier v1.0 loaded');
