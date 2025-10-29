// ==========================================
// CRUMP AI - NETWORK STATUS MANAGER v1.0
// Online/Offline detection and indicators
// ==========================================

class NetworkStatusManager {
    constructor() {
        this.isOnline = navigator.onLine;
        this.indicator = null;
        
        console.log('🌐 Network Status Manager initializing...');
        this.init();
    }

    init() {
        // Listen for online/offline events
        window.addEventListener('online', () => this.handleOnline());
        window.addEventListener('offline', () => this.handleOffline());
        
        // Check initial status
        if (!this.isOnline) {
            this.showOfflineIndicator();
        }
        
        console.log('✅ Network Status Manager ready - Currently:', this.isOnline ? 'Online' : 'Offline');
    }

    handleOnline() {
        console.log('🌐 Connection restored');
        this.isOnline = true;
        
        // Show brief online notification
        this.showOnlineIndicator();
        
        // Check for app updates
        if (window.pwaManager) {
            window.pwaManager.checkForUpdates();
        }
        
        // Dispatch event for other modules
        window.dispatchEvent(new CustomEvent('networkStatusChanged', {
            detail: { online: true }
        }));
        
        // Hide offline indicator after a delay
        setTimeout(() => this.hideIndicator(), 3000);
    }

    handleOffline() {
        console.log('📡 Connection lost');
        this.isOnline = false;
        
        // Show offline indicator
        this.showOfflineIndicator();
        
        // Dispatch event for other modules
        window.dispatchEvent(new CustomEvent('networkStatusChanged', {
            detail: { online: false }
        }));
    }

    showOfflineIndicator() {
        this.hideIndicator();
        
        this.indicator = document.createElement('div');
        this.indicator.id = 'networkIndicator';
        this.indicator.className = 'offline-indicator';
        this.indicator.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display: inline-block; vertical-align: middle; margin-right: 8px;">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
            You're offline - Some features unavailable
        `;
        
        document.body.appendChild(this.indicator);
    }

    showOnlineIndicator() {
        this.hideIndicator();
        
        this.indicator = document.createElement('div');
        this.indicator.id = 'networkIndicator';
        this.indicator.className = 'online-indicator';
        this.indicator.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display: inline-block; vertical-align: middle; margin-right: 8px;">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            Back online!
        `;
        
        document.body.appendChild(this.indicator);
    }

    hideIndicator() {
        const existing = document.getElementById('networkIndicator');
        if (existing) {
            existing.remove();
        }
        this.indicator = null;
    }

    getStatus() {
        return {
            online: this.isOnline,
            effectiveType: navigator.connection?.effectiveType || 'unknown',
            downlink: navigator.connection?.downlink || null,
            rtt: navigator.connection?.rtt || null,
            saveData: navigator.connection?.saveData || false
        };
    }

    // Check if we have a good connection for heavy operations
    canPerformHeavyOperation() {
        if (!this.isOnline) return false;
        
        const connection = navigator.connection;
        if (!connection) return true;
        
        // Don't do heavy operations on slow connections
        if (connection.effectiveType === 'slow-2g' || connection.effectiveType === '2g') {
            return false;
        }
        
        // Don't do heavy operations if user has data saver on
        if (connection.saveData) {
            return false;
        }
        
        return true;
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.networkStatusManager = new NetworkStatusManager();

// Export for other modules
window.NetworkStatusManager = NetworkStatusManager;

console.log('✅ Network Status Manager v1.0 loaded');
