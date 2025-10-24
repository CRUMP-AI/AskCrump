// ==========================================
// CRUMP AI - DEVELOPER MODE v3.0
// Secret bypass for development/testing
// ==========================================

class DeveloperMode {
    constructor() {
        this.enabled = this.loadDevMode();
        this.secretCode = 'CRUMP-DEV-2025';
        
        if (this.enabled) {
            this.activate();
        }
        
        this.setupKeyboardShortcut();
        console.log('🔧 Developer Mode ready (Ctrl+Shift+D to toggle)');
    }
    
    // ==========================================
    // ACTIVATION
    // ==========================================
    
    activate() {
        console.log('👨‍💻 DEVELOPER MODE ACTIVATED');
        
        // Override profile manager to give unlimited access
        if (window.profileManager) {
            const originalGetTier = window.profileManager.getTier.bind(window.profileManager);
            
            window.profileManager.getTier = function() {
                return 'developer';
            };
            
            window.profileManager.getTierInfo = function() {
                return {
                    current: 'developer',
                    name: 'Developer',
                    icon: '👨‍💻',
                    limits: {
                        messages: -1,
                        images: -1,
                        searches: -1,
                        sports: -1,
                        weather: -1,
                        stocks: -1,
                        news: -1
                    },
                    features: ['UNLIMITED EVERYTHING', 'All Premium Features', 'API Access', 'No Restrictions']
                };
            };
            
            // Override all limit checks
            window.profileManager.canSendMessage = () => ({ allowed: true });
            window.profileManager.canGenerateImage = () => ({ allowed: true });
            window.profileManager.canSearchWeb = () => ({ allowed: true });
            window.profileManager.canUseSportsAPI = () => ({ allowed: true });
            window.profileManager.canUseWeatherAPI = () => ({ allowed: true });
            window.profileManager.canUseStocksAPI = () => ({ allowed: true });
            window.profileManager.canUseNewsAPI = () => ({ allowed: true });
        }
        
        this.enabled = true;
        this.saveDevMode();
        this.updateUI();
        
        if (window.showNotification) {
            window.showNotification('👨‍💻 Developer Mode: ACTIVATED', 'success');
        }
    }
    
    deactivate() {
        console.log('👨‍💻 DEVELOPER MODE DEACTIVATED');
        
        this.enabled = false;
        this.saveDevMode();
        
        if (window.showNotification) {
            window.showNotification('👨‍💻 Developer Mode: DEACTIVATED (Reload to apply)', 'info');
        }
        
        // Reload to restore normal functions
        setTimeout(() => window.location.reload(), 1500);
    }
    
    toggle() {
        if (this.enabled) {
            this.deactivate();
        } else {
            this.activate();
        }
    }
    
    // ==========================================
    // KEYBOARD SHORTCUT
    // ==========================================
    
    setupKeyboardShortcut() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+Shift+D (or Cmd+Shift+D on Mac)
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
                e.preventDefault();
                this.showActivationPrompt();
            }
        });
    }
    
    showActivationPrompt() {
        const code = prompt('🔐 Enter Developer Access Code:');
        
        if (code === this.secretCode) {
            this.toggle();
        } else if (code !== null) {
            if (window.showNotification) {
                window.showNotification('❌ Invalid access code', 'error');
            }
        }
    }
    
    // ==========================================
    // UI UPDATES
    // ==========================================
    
    updateUI() {
        // Update tier badges
        const tierBadges = document.querySelectorAll('#tierName, #headerTierName');
        tierBadges.forEach(badge => {
            if (badge) {
                badge.textContent = '👨‍💻 DEV';
                badge.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
                badge.style.webkitBackgroundClip = 'text';
                badge.style.webkitTextFillColor = 'transparent';
            }
        });
        
        // Add dev indicator to sidebar
        const sidebar = document.getElementById('sidebar');
        if (sidebar && !document.getElementById('devIndicator')) {
            const indicator = document.createElement('div');
            indicator.id = 'devIndicator';
            indicator.style.cssText = `
                position: absolute;
                top: 10px;
                right: 10px;
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.5px;
                z-index: 1000;
            `;
            indicator.textContent = 'DEV MODE';
            sidebar.appendChild(indicator);
        }
    }
    
    // ==========================================
    // PERSISTENCE
    // ==========================================
    
    loadDevMode() {
        const saved = localStorage.getItem('crump_dev_mode');
        return saved === 'true';
    }
    
    saveDevMode() {
        localStorage.setItem('crump_dev_mode', this.enabled.toString());
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.developerMode = new DeveloperMode();

// Export
window.DeveloperMode = DeveloperMode;

console.log('✅ Developer Mode v3.0 loaded');
console.log('💡 Press Ctrl+Shift+D to toggle');
console.log('🔐 Access Code: CRUMP-DEV-2025');
