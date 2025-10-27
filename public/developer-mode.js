// ==========================================
// CRUMP AI - DEVELOPER LOGIN v3.1
// Professional admin access system
// ==========================================

class DeveloperMode {
    constructor() {
        this.enabled = this.loadDevMode();
        // Credentials stored as base64 (still visible in source, but less obvious)
        this.credentials = {
            username: atob('Z3JlZ0BjcnVtcGFpLmNvbQ=='),  // greg@crumpai.com
            password: atob('TjItRW5naW5lLTIwMjU=')        // N2-Engine-2025
        };
        
        if (this.enabled) {
            this.activate();
        }
        
        // FIXED: Delay button setup until DOM is ready
        this.initWhenReady();
        
        console.log('🔧 Developer Login ready');
    }
    
    // ==========================================
    // INITIALIZATION FIX
    // ==========================================
    
    initWhenReady() {
        // Wait for sidebar to be rendered
        const checkSidebar = () => {
            const sidebarFooter = document.querySelector('.sidebar-footer');
            if (sidebarFooter) {
                this.setupDevLoginButton();
                if (this.enabled) {
                    this.updateUI();
                }
            } else {
                // Retry after a short delay
                setTimeout(checkSidebar, 100);
            }
        };
        
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', checkSidebar);
        } else {
            checkSidebar();
        }
    }
    
    // ==========================================
    // LOGIN UI
    // ==========================================
    
    setupDevLoginButton() {
        // Remove existing button if any
        const existing = document.querySelector('.dev-login-trigger');
        if (existing) existing.remove();
        
        // Add hidden developer login button to sidebar footer
        const sidebarFooter = document.querySelector('.sidebar-footer');
        if (!sidebarFooter) {
            console.warn('⚠️ Sidebar footer not found, retrying...');
            setTimeout(() => this.setupDevLoginButton(), 500);
            return;
        }
        
        const devLoginBtn = document.createElement('button');
        devLoginBtn.className = 'sidebar-footer-btn dev-login-trigger';
        devLoginBtn.style.cssText = 'opacity: 0.3; transition: opacity 0.2s;';
        devLoginBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
            </svg>
            <span>Developer Access</span>
        `;
        devLoginBtn.onmouseover = () => devLoginBtn.style.opacity = '1';
        devLoginBtn.onmouseout = () => devLoginBtn.style.opacity = '0.3';
        devLoginBtn.onclick = () => this.showLoginModal();
        
        // Insert before the branding footer (at the end)
        sidebarFooter.appendChild(devLoginBtn);
        
        console.log('✅ Developer login button added');
    }
    
    showLoginModal() {
        // Remove existing modal if any
        const existing = document.getElementById('devLoginModal');
        if (existing) existing.remove();
        
        const modal = document.createElement('div');
        modal.id = 'devLoginModal';
        modal.className = 'modal';
        modal.style.display = 'flex';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 400px;">
                <div class="modal-header">
                    <h2>🔐 Developer Access</h2>
                    <button class="btn-icon" onclick="document.getElementById('devLoginModal').remove()" aria-label="Close">
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                            <path d="M15 5L5 15M5 5l10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                    </button>
                </div>
                
                <div class="modal-body">
                    <p style="color: var(--color-text-secondary); margin-bottom: 1.5rem; font-size: 0.875rem;">
                        Enter your developer credentials to unlock all features
                    </p>
                    
                    <div class="form-group">
                        <label for="devUsername">Username</label>
                        <input type="text" id="devUsername" class="form-input" placeholder="developer@crumpai.com" autocomplete="username">
                    </div>
                    
                    <div class="form-group">
                        <label for="devPassword">Password</label>
                        <input type="password" id="devPassword" class="form-input" placeholder="Enter password" autocomplete="current-password">
                    </div>
                    
                    <div id="devLoginError" style="display: none; color: var(--color-error); font-size: 0.875rem; margin-bottom: 1rem; padding: 0.5rem; background: rgba(220, 38, 38, 0.1); border-radius: 6px;">
                    </div>
                    
                    <button id="devLoginBtn" class="btn btn-primary btn-block btn-large" onclick="window.developerMode.attemptLogin()">
                        Sign In
                    </button>
                    
                    ${this.enabled ? `
                        <button class="btn btn-secondary btn-block" style="margin-top: 0.5rem;" onclick="window.developerMode.logout()">
                            Logout
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Focus username field
        setTimeout(() => document.getElementById('devUsername')?.focus(), 100);
        
        // Enable Enter key
        const form = modal.querySelector('.modal-body');
        form.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.attemptLogin();
            }
        });
    }
    
    attemptLogin() {
        const username = document.getElementById('devUsername')?.value.trim();
        const password = document.getElementById('devPassword')?.value;
        const errorDiv = document.getElementById('devLoginError');
        const loginBtn = document.getElementById('devLoginBtn');
        
        if (!username || !password) {
            this.showError('Please enter both username and password');
            return;
        }
        
        // Disable button during check
        if (loginBtn) {
            loginBtn.disabled = true;
            loginBtn.textContent = 'Signing in...';
        }
        
        // Simulate checking (you could add a small delay for realism)
        setTimeout(() => {
            if (username === this.credentials.username && password === this.credentials.password) {
                // Success!
                this.activate();
                document.getElementById('devLoginModal')?.remove();
                
                if (window.showToast) {
                    window.showToast('👨‍💻 Developer Access Granted', 'success');
                }
                
                // Reload to apply unlimited features
                setTimeout(() => window.location.reload(), 1000);
            } else {
                // Failed
                this.showError('Invalid credentials. Please try again.');
                
                if (loginBtn) {
                    loginBtn.disabled = false;
                    loginBtn.textContent = 'Sign In';
                }
                
                // Clear password field
                const passwordInput = document.getElementById('devPassword');
                if (passwordInput) {
                    passwordInput.value = '';
                    passwordInput.focus();
                }
            }
        }, 500);
    }
    
    showError(message) {
        const errorDiv = document.getElementById('devLoginError');
        if (errorDiv) {
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
            
            setTimeout(() => {
                errorDiv.style.display = 'none';
            }, 5000);
        }
    }
    
    logout() {
        this.deactivate();
        document.getElementById('devLoginModal')?.remove();
        
        if (window.showToast) {
            window.showToast('👋 Logged out (Reload to apply)', 'info');
        }
        
        setTimeout(() => window.location.reload(), 1500);
    }
    
    // ==========================================
    // ACTIVATION
    // ==========================================
    
    activate() {
        console.log('👨‍💻 DEVELOPER MODE ACTIVATED');
        
        // Override profile manager to give unlimited access
        if (window.profileManager || window.currentProfile) {
            const pm = window.profileManager || window.currentProfile;
            
            pm.getTier = function() {
                return 'developer';
            };
            
            pm.getTierInfo = function() {
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
            pm.canSendMessage = () => ({ allowed: true });
            pm.canGenerateImage = () => ({ allowed: true });
            pm.canSearchWeb = () => ({ allowed: true });
            pm.canUseSportsAPI = () => ({ allowed: true });
            pm.canUseWeatherAPI = () => ({ allowed: true });
            pm.canUseStocksAPI = () => ({ allowed: true });
            pm.canUseNewsAPI = () => ({ allowed: true });
        }
        
        this.enabled = true;
        this.saveDevMode();
        
        // Update UI if DOM is ready
        if (document.querySelector('.sidebar-footer')) {
            this.updateUI();
        }
    }
    
    deactivate() {
        console.log('👨‍💻 DEVELOPER MODE DEACTIVATED');
        this.enabled = false;
        this.saveDevMode();
    }
    
    // ==========================================
    // UI UPDATES
    // ==========================================
    
    updateUI() {
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

console.log('✅ Developer Login v3.1 loaded');
