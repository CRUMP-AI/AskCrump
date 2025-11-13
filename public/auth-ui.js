// =====================================================
// AUTHENTICATION UI
// Location: /public/auth-ui.js
// =====================================================

class AuthUI {
    constructor() {
        this.currentUser = null;
        this.authToken = null;
        this.init();
    }

    init() {
        this.createAuthHTML();
        this.attachEventListeners();
        this.checkSession();
    }

    createAuthHTML() {
        const authHTML = `
            <!-- Authentication Modal Overlay -->
            <div id="auth-overlay" class="auth-overlay">
                <!-- Login Modal -->
                <div id="login-modal" class="auth-modal">
                    <div class="auth-modal-header">
                        <h2>Welcome Back</h2>
                        <button class="auth-close-btn" onclick="authUI.closeModals()">&times;</button>
                    </div>
                    <div class="auth-modal-body">
                        <form id="login-form" class="auth-form">
                            <div class="auth-form-group">
                                <label for="login-email">Email</label>
                                <input type="email" id="login-email" required placeholder="your@email.com" autocomplete="email">
                            </div>
                            <div class="auth-form-group">
                                <label for="login-password">Password</label>
                                <input type="password" id="login-password" required placeholder="••••••••" autocomplete="current-password">
                            </div>
                            <div class="auth-form-options">
                                <label class="auth-checkbox">
                                    <input type="checkbox" id="remember-me">
                                    <span>Remember me</span>
                                </label>
                                <a href="#" class="auth-link" onclick="authUI.showForgotPassword(); return false;">Forgot password?</a>
                            </div>
                            <div id="login-error" class="auth-error"></div>
                            <button type="submit" class="auth-btn auth-btn-primary" id="login-submit-btn">
                                <span class="btn-text">Sign In</span>
                                <span class="btn-loader"></span>
                            </button>
                        </form>
                        <div class="auth-divider">
                            <span>Don't have an account?</span>
                        </div>
                        <button class="auth-btn auth-btn-secondary" onclick="authUI.showSignup()">Create Account</button>
                    </div>
                </div>

                <!-- Signup Modal -->
                <div id="signup-modal" class="auth-modal" style="display: none;">
                    <div class="auth-modal-header">
                        <h2>Create Account</h2>
                        <button class="auth-close-btn" onclick="authUI.closeModals()">&times;</button>
                    </div>
                    <div class="auth-modal-body">
                        <form id="signup-form" class="auth-form">
                            <div class="auth-form-group">
                                <label for="signup-name">Full Name (Optional)</label>
                                <input type="text" id="signup-name" placeholder="John Doe" autocomplete="name">
                            </div>
                            <div class="auth-form-group">
                                <label for="signup-email">Email</label>
                                <input type="email" id="signup-email" required placeholder="your@email.com" autocomplete="email">
                            </div>
                            <div class="auth-form-group">
                                <label for="signup-password">Password</label>
                                <input type="password" id="signup-password" required placeholder="••••••••" autocomplete="new-password">
                                <small class="auth-hint">At least 8 characters</small>
                            </div>
                            <div class="auth-form-group">
                                <label for="signup-confirm-password">Confirm Password</label>
                                <input type="password" id="signup-confirm-password" required placeholder="••••••••" autocomplete="new-password">
                            </div>
                            <div id="signup-error" class="auth-error"></div>
                            <button type="submit" class="auth-btn auth-btn-primary" id="signup-submit-btn">
                                <span class="btn-text">Sign Up</span>
                                <span class="btn-loader"></span>
                            </button>
                        </form>
                        <div class="auth-divider">
                            <span>Already have an account?</span>
                        </div>
                        <button class="auth-btn auth-btn-secondary" onclick="authUI.showLogin()">Sign In</button>
                    </div>
                </div>

                <!-- Verification Needed Modal -->
                <div id="verification-modal" class="auth-modal" style="display: none;">
                    <div class="auth-modal-header">
                        <h2>Verify Your Email</h2>
                        <button class="auth-close-btn" onclick="authUI.closeModals()">&times;</button>
                    </div>
                    <div class="auth-modal-body">
                        <div class="auth-message-box">
                            <div class="auth-icon-success">✉️</div>
                            <h3>Check Your Inbox</h3>
                            <p id="verification-message">We've sent a verification link to your email address. Please click the link to verify your account.</p>
                            <div class="auth-resend-section">
                                <p>Didn't receive the email?</p>
                                <button class="auth-btn auth-btn-secondary" onclick="authUI.resendVerification()" id="resend-btn">
                                    <span class="btn-text">Resend Verification Email</span>
                                    <span class="btn-loader"></span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Success Modal -->
                <div id="success-modal" class="auth-modal" style="display: none;">
                    <div class="auth-modal-header">
                        <h2>Success!</h2>
                        <button class="auth-close-btn" onclick="authUI.closeModals()">&times;</button>
                    </div>
                    <div class="auth-modal-body">
                        <div class="auth-message-box">
                            <div class="auth-icon-success">✓</div>
                            <h3 id="success-title">Email Verified!</h3>
                            <p id="success-message">Your email has been verified successfully. You can now sign in.</p>
                            <button class="auth-btn auth-btn-primary" onclick="authUI.showLogin()">Sign In Now</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- User Profile Button -->
            <div id="user-profile-container" style="display: none;">
                <button class="user-profile-btn" onclick="authUI.toggleProfileMenu()">
                    <img id="user-avatar" src="" alt="Profile" class="user-avatar">
                    <span id="user-name-display"></span>
                </button>
                <div id="profile-menu" class="profile-menu" style="display: none;">
                    <div class="profile-menu-header">
                        <img id="profile-menu-avatar" src="" alt="Profile" class="profile-menu-avatar">
                        <div class="profile-menu-info">
                            <div id="profile-menu-name"></div>
                            <div id="profile-menu-email"></div>
                        </div>
                    </div>
                    <div class="profile-menu-items">
                        <button onclick="authUI.showSettings()">
                            <span>⚙️</span> Settings
                        </button>
                        <button onclick="authUI.showDevices()">
                            <span>📱</span> Devices
                        </button>
                        <button onclick="authUI.logout()">
                            <span>🚪</span> Sign Out
                        </button>
                    </div>
                </div>
            </div>

            <!-- Login/Signup Trigger Button -->
            <!-- TEMPORARILY DISABLED
            <button id="auth-trigger-btn" class="auth-trigger-btn">
                Sign In
            </button>
            -->
        `;
        document.body.insertAdjacentHTML('beforeend', authHTML);
    }

    attachEventListeners() {
        // Login form
        document.getElementById('login-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleLogin();
        });

        // Signup form
        document.getElementById('signup-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleSignup();
        });

        // Auth trigger button (if enabled)
        const authTriggerBtn = document.getElementById('auth-trigger-btn');
        if (authTriggerBtn) {
            authTriggerBtn.addEventListener('click', () => {
                this.showLogin();
            });
        }
        
        // Close overlay on click outside
        document.getElementById('auth-overlay').addEventListener('click', (e) => {
            if (e.target.id === 'auth-overlay') {
                this.closeModals();
            }
        });

        // ESC key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModals();
            }
        });
    }

    async checkSession() {
        try {
            const response = await fetch('/api/auth/check-session', {
                method: 'GET',
                credentials: 'include'
            });

            const data = await response.json();

            if (data.success && data.authenticated) {
                this.handleAuthSuccess(data.data);
                this.allowAppAccess();
            } else {
                // NOT authenticated - FORCE login
                this.forceLogin();
            }
        } catch (error) {
            console.error('Session check failed:', error);
            // On error, also force login
            this.forceLogin();
        }
    }

    forceLogin() {
        // Show login modal (can't be closed)
        document.getElementById('auth-overlay').style.display = 'flex';
        document.getElementById('login-modal').style.display = 'block';
        
        // Remove close buttons (make login REQUIRED)
        const closeButtons = document.querySelectorAll('.auth-close-btn');
        closeButtons.forEach(btn => btn.style.display = 'none');
        
        // Prevent closing by clicking overlay
        const overlay = document.getElementById('auth-overlay');
        overlay.style.pointerEvents = 'none';
        overlay.querySelector('.auth-modal').style.pointerEvents = 'all';
        
        // Hide main app until authenticated
        const chatContainer = document.getElementById('chat-container');
        const sidebar = document.querySelector('.sidebar');
        if (chatContainer) chatContainer.style.display = 'none';
        if (sidebar) sidebar.style.display = 'none';
        
        console.log('🔒 Authentication required - please log in or sign up');
    }

    allowAppAccess() {
        // Show main app
        const chatContainer = document.getElementById('chat-container');
        const sidebar = document.querySelector('.sidebar');
        if (chatContainer) chatContainer.style.display = 'flex';
        if (sidebar) sidebar.style.display = 'flex';
        
        // Re-enable close buttons
        const closeButtons = document.querySelectorAll('.auth-close-btn');
        closeButtons.forEach(btn => btn.style.display = 'block');
        
        // Re-enable overlay closing
        const overlay = document.getElementById('auth-overlay');
        overlay.style.pointerEvents = 'all';
        
        console.log('✅ User authenticated - app access granted');
    }

    async handleLogin() {
        const email = document.getElementById('login-email').value;
        const password = document.getElementById('login-password').value;
        const rememberMe = document.getElementById('remember-me').checked;
        const submitBtn = document.getElementById('login-submit-btn');
        const errorDiv = document.getElementById('login-error');

        this.setLoading(submitBtn, true);
        errorDiv.textContent = '';

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ email, password, rememberMe })
            });

            const data = await response.json();

            if (data.success) {
                this.handleAuthSuccess(data.data);
                this.closeModals();
            } else {
                if (data.code === 'EMAIL_NOT_VERIFIED') {
                    this.pendingVerificationEmail = email;
                    this.showVerification('Please verify your email before signing in.');
                } else {
                    errorDiv.textContent = data.error || 'Login failed';
                }
            }
        } catch (error) {
            errorDiv.textContent = 'Network error. Please try again.';
            console.error('Login error:', error);
        } finally {
            this.setLoading(submitBtn, false);
        }
    }

    async handleSignup() {
        const fullName = document.getElementById('signup-name').value;
        const email = document.getElementById('signup-email').value;
        const password = document.getElementById('signup-password').value;
        const confirmPassword = document.getElementById('signup-confirm-password').value;
        const submitBtn = document.getElementById('signup-submit-btn');
        const errorDiv = document.getElementById('signup-error');

        errorDiv.textContent = '';

        if (password !== confirmPassword) {
            errorDiv.textContent = 'Passwords do not match';
            return;
        }

        if (password.length < 8) {
            errorDiv.textContent = 'Password must be at least 8 characters';
            return;
        }

        this.setLoading(submitBtn, true);

        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, fullName })
            });

            const data = await response.json();

            if (data.success) {
                this.pendingVerificationEmail = email;
                this.showVerification(data.message);
            } else {
                errorDiv.textContent = data.error || 'Signup failed';
            }
        } catch (error) {
            errorDiv.textContent = 'Network error. Please try again.';
            console.error('Signup error:', error);
        } finally {
            this.setLoading(submitBtn, false);
        }
    }

    async resendVerification() {
        if (!this.pendingVerificationEmail) return;

        const resendBtn = document.getElementById('resend-btn');
        this.setLoading(resendBtn, true);

        try {
            const response = await fetch('/api/auth/resend-verification', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: this.pendingVerificationEmail })
            });

            const data = await response.json();

            if (data.success) {
                this.showSuccess('Verification Email Sent', data.message);
            }
        } catch (error) {
            console.error('Resend verification error:', error);
        } finally {
            this.setLoading(resendBtn, false);
        }
    }

    async logout() {
        try {
            await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'include'
            });

            this.currentUser = null;
            this.authToken = null;
            this.updateUIForLoggedOut();
            
            // Reload page to clear any cached data
            window.location.reload();
        } catch (error) {
            console.error('Logout error:', error);
        }
    }

    handleAuthSuccess(data) {
        this.currentUser = data.user;
        this.authToken = data.token;
        this.updateUIForLoggedIn();
        
        // Allow app access
        this.allowAppAccess();
        
        // Store user data globally for Crump and app to use
        window.currentUser = this.currentUser;
        window.authToken = this.authToken;
        
        // Trigger custom event for other parts of the app
        window.dispatchEvent(new CustomEvent('user-authenticated', { 
            detail: { user: this.currentUser, token: this.authToken } 
        }));
        
        console.log('👤 User logged in:', this.currentUser.email);
        
        // Initialize app if function exists
        if (typeof window.initializeAuthenticatedApp === 'function') {
            window.initializeAuthenticatedApp(this.currentUser);
        }
    }

    updateUIForLoggedIn() {
        const authTriggerBtn = document.getElementById('auth-trigger-btn');
        const profileContainer = document.getElementById('user-profile-container');
        
        if (authTriggerBtn) authTriggerBtn.style.display = 'none';
        if (profileContainer) profileContainer.style.display = 'block';
        
        const avatar = this.currentUser.profilePicture || this.generateAvatar(this.currentUser.email);
        document.getElementById('user-avatar').src = avatar;
        document.getElementById('profile-menu-avatar').src = avatar;
        document.getElementById('user-name-display').textContent = this.currentUser.fullName || this.currentUser.email.split('@')[0];
        document.getElementById('profile-menu-name').textContent = this.currentUser.fullName || 'User';
        document.getElementById('profile-menu-email').textContent = this.currentUser.email;
    }

    updateUIForLoggedOut() {
        const authTriggerBtn = document.getElementById('auth-trigger-btn');
        const profileContainer = document.getElementById('user-profile-container');
        
        if (authTriggerBtn) authTriggerBtn.style.display = 'block';
        if (profileContainer) profileContainer.style.display = 'none';
    }
    
    generateAvatar(email) {
        // Generate a simple avatar using UI Avatars
        const name = email.split('@')[0];
        return `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=667eea&color=fff&size=128`;
    }

    showLogin() {
        document.getElementById('auth-overlay').style.display = 'flex';
        document.getElementById('login-modal').style.display = 'block';
        document.getElementById('signup-modal').style.display = 'none';
        document.getElementById('verification-modal').style.display = 'none';
        document.getElementById('success-modal').style.display = 'none';
    }

    showSignup() {
        document.getElementById('signup-modal').style.display = 'block';
        document.getElementById('login-modal').style.display = 'none';
    }

    showVerification(message) {
        document.getElementById('verification-message').textContent = message;
        document.getElementById('verification-modal').style.display = 'block';
        document.getElementById('login-modal').style.display = 'none';
        document.getElementById('signup-modal').style.display = 'none';
    }

    showSuccess(title, message) {
        document.getElementById('success-title').textContent = title;
        document.getElementById('success-message').textContent = message;
        document.getElementById('success-modal').style.display = 'block';
        document.getElementById('verification-modal').style.display = 'none';
    }

    showForgotPassword() {
        alert('Password reset functionality coming soon!');
    }

    showSettings() {
        alert('Settings functionality coming soon!');
    }

    showDevices() {
        alert('Device management functionality coming soon!');
    }

    toggleProfileMenu() {
        const menu = document.getElementById('profile-menu');
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }

    closeModals() {
        document.getElementById('auth-overlay').style.display = 'none';
        document.getElementById('profile-menu').style.display = 'none';
    }

    setLoading(button, loading) {
        const text = button.querySelector('.btn-text');
        const loader = button.querySelector('.btn-loader');
        
        if (loading) {
            button.disabled = true;
            text.style.opacity = '0';
            loader.style.display = 'block';
        } else {
            button.disabled = false;
            text.style.opacity = '1';
            loader.style.display = 'none';
        }
    }

    // Get current user (for use by other parts of the app)
    getCurrentUser() {
        return this.currentUser;
    }

    // Get auth token (for authenticated API requests)
    getAuthToken() {
        return this.authToken;
    }
}

// Initialize auth UI when DOM is ready
let authUI;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        authUI = new AuthUI();
    });
} else {
    authUI = new AuthUI();
}

// Check for verification token in URL
window.addEventListener('load', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const verificationToken = urlParams.get('token');
    
    if (verificationToken) {
        try {
            const response = await fetch('/api/auth/verify-email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: verificationToken })
            });

            const data = await response.json();

            if (data.success) {
                authUI.showSuccess('Email Verified!', data.message);
                // Remove token from URL
                window.history.replaceState({}, document.title, window.location.pathname);
            } else {
                alert(data.error || 'Verification failed');
            }
        } catch (error) {
            console.error('Verification error:', error);
        }
    }
});
