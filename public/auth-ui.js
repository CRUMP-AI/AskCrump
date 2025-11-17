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
        // Try to recover token from localStorage
        const storedToken = localStorage.getItem('crump_auth_token');
        const headers = {};

        if (storedToken) {
            headers['Authorization'] = `Bearer ${storedToken}`;
        }

        const response = await fetch('/api/auth/check-session', {
            method: 'GET',
            headers,
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

        // Clear in-memory auth
        this.currentUser = null;
        this.authToken = null;

        // Clear any persisted auth token
        localStorage.removeItem('crump_auth_token');

        this.updateUIForLoggedOut();
        
        // Reload page to clear any cached data
        window.location.reload();
    } catch (error) {
        console.error('Logout error:', error);
    }
}


    handleAuthSuccess(data) {
    // Core user object
    this.currentUser = data.user;

    // Try to keep an auth token around:
    // - Use token from /api/auth/login when available
    // - Fall back to any previously stored token
    const storedToken = localStorage.getItem('crump_auth_token');
    this.authToken = data.token || storedToken || null;

    // If this login came from /api/auth/login, persist the new token
    if (data.token) {
        localStorage.setItem('crump_auth_token', data.token);
    }

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
    // Hide all modals
    document.getElementById('login-modal').style.display = 'none';
    document.getElementById('signup-modal').style.display = 'none';
    document.getElementById('verification-modal').style.display = 'none';
    document.getElementById('success-modal').style.display = 'none';
    
    // Create forgot password modal if it doesn't exist
    let forgotModal = document.getElementById('forgot-password-modal');
    if (!forgotModal) {
        const modalHTML = `
            <div id="forgot-password-modal" class="auth-modal" style="display: none;">
                <div class="auth-modal-header">
                    <h2>Reset Password</h2>
                    <button class="auth-close-btn" onclick="authUI.closeModals()">&times;</button>
                </div>
                <div class="auth-modal-body">
                    <p style="color: rgba(255, 255, 255, 0.7); margin-bottom: 1.5rem;">
                        Enter your email address and we'll send you a link to reset your password.
                    </p>
                    <form id="forgot-password-form" class="auth-form">
                        <div class="auth-form-group">
                            <label for="forgot-email">Email Address</label>
                            <input type="email" id="forgot-email" required placeholder="your@email.com" autocomplete="email">
                        </div>
                        <div id="forgot-error" class="auth-error"></div>
                        <div id="forgot-success" class="auth-success" style="display: none;"></div>
                        <button type="submit" class="auth-btn auth-btn-primary" id="forgot-submit-btn">
                            <span class="btn-text">Send Reset Link</span>
                            <span class="btn-loader"></span>
                        </button>
                    </form>
                    <div class="auth-divider">
                        <span>Remember your password?</span>
                    </div>
                    <button class="auth-btn auth-btn-secondary" onclick="authUI.showLogin()">Back to Sign In</button>
                </div>
            </div>
        `;
        
        // Insert modal into overlay
        const overlay = document.getElementById('auth-overlay');
        overlay.insertAdjacentHTML('beforeend', modalHTML);
        
        // Attach form handler
        document.getElementById('forgot-password-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleForgotPassword();
        });
    }
    
    // Show the modal
    document.getElementById('auth-overlay').style.display = 'flex';
    document.getElementById('forgot-password-modal').style.display = 'block';
}

async handleForgotPassword() {
    const email = document.getElementById('forgot-email').value.trim();
    const errorDiv = document.getElementById('forgot-error');
    const successDiv = document.getElementById('forgot-success');
    const submitBtn = document.getElementById('forgot-submit-btn');
    
    // Clear previous messages
    errorDiv.textContent = '';
    successDiv.style.display = 'none';
    successDiv.textContent = '';
    
    // Validate email
    if (!email) {
        errorDiv.textContent = 'Please enter your email address';
        return;
    }
    
    // Show loading state
    this.setLoading(submitBtn, true);
    
    try {
        const response = await fetch('/api/auth/forgot-password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email })
        });
        
        const data = await response.json();
        
        this.setLoading(submitBtn, false);
        
        if (data.success) {
            // Show success message
            successDiv.textContent = data.message || 'If an account exists with that email, a password reset link has been sent.';
            successDiv.style.display = 'block';
            
            // Clear the form
            document.getElementById('forgot-email').value = '';
            
            // Auto-close after 5 seconds and go back to login
            setTimeout(() => {
                this.showLogin();
            }, 5000);
        } else {
            errorDiv.textContent = data.error || 'Failed to send reset email. Please try again.';
        }
    } catch (error) {
        console.error('Forgot password error:', error);
        this.setLoading(submitBtn, false);
        errorDiv.textContent = 'An error occurred. Please try again.';
    }
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
    
    showResetPassword(token) {
        // Hide all modals
        document.getElementById('login-modal').style.display = 'none';
        document.getElementById('signup-modal').style.display = 'none';
        
        // Create reset password modal if it doesn't exist
        let resetModal = document.getElementById('reset-password-modal');
        if (!resetModal) {
            const modalHTML = `
                <div id="reset-password-modal" class="auth-modal" style="display: none;">
                    <div class="auth-modal-header">
                        <h2>Set New Password</h2>
                        <button class="auth-close-btn" onclick="authUI.closeModals()">&times;</button>
                    </div>
                    <div class="auth-modal-body">
                        <p style="color: rgba(255, 255, 255, 0.7); margin-bottom: 1.5rem;">
                            Enter your new password below.
                        </p>
                        <form id="reset-password-form" class="auth-form">
                            <input type="hidden" id="reset-token" value="">
                            <div class="auth-form-group">
                                <label for="new-password">New Password</label>
                                <input type="password" id="new-password" required placeholder="••••••••" autocomplete="new-password">
                                <small class="auth-hint">At least 8 characters</small>
                            </div>
                            <div class="auth-form-group">
                                <label for="confirm-new-password">Confirm New Password</label>
                                <input type="password" id="confirm-new-password" required placeholder="••••••••" autocomplete="new-password">
                            </div>
                            <div id="reset-error" class="auth-error"></div>
                            <button type="submit" class="auth-btn auth-btn-primary" id="reset-submit-btn">
                                <span class="btn-text">Reset Password</span>
                                <span class="btn-loader"></span>
                            </button>
                        </form>
                    </div>
                </div>
            `;
            
            const overlay = document.getElementById('auth-overlay');
            overlay.insertAdjacentHTML('beforeend', modalHTML);
            
            // Attach form handler
            document.getElementById('reset-password-form').addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleResetPassword();
            });
        }
        
        // Set the token
        document.getElementById('reset-token').value = token;
        
        // Show the modal
        document.getElementById('auth-overlay').style.display = 'flex';
        document.getElementById('reset-password-modal').style.display = 'block';
        
        // Clean URL
        window.history.replaceState({}, document.title, window.location.pathname);
    }

    async handleResetPassword() {
        const token = document.getElementById('reset-token').value;
        const newPassword = document.getElementById('new-password').value;
        const confirmPassword = document.getElementById('confirm-new-password').value;
        const errorDiv = document.getElementById('reset-error');
        const submitBtn = document.getElementById('reset-submit-btn');
        
        // Clear previous errors
        errorDiv.textContent = '';
        
        // Validate passwords match
        if (newPassword !== confirmPassword) {
            errorDiv.textContent = 'Passwords do not match';
            return;
        }
        
        // Validate password length
        if (newPassword.length < 8) {
            errorDiv.textContent = 'Password must be at least 8 characters';
            return;
        }
        
        // Show loading state
        this.setLoading(submitBtn, true);
        
        try {
            const response = await fetch('/api/auth/reset-password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    token: token,
                    newPassword: newPassword
                })
            });
            
            const data = await response.json();
            
            this.setLoading(submitBtn, false);
            
            if (data.success) {
                // Show success and redirect to login
                this.showSuccess('Password Reset!', data.message);
            } else {
                errorDiv.textContent = data.error || 'Failed to reset password. Please try again.';
            }
        } catch (error) {
            console.error('Reset password error:', error);
            this.setLoading(submitBtn, false);
            errorDiv.textContent = 'An error occurred. Please try again.';
        }
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

// Check for verification status in URL (from API redirect)
window.addEventListener('load', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const verification = urlParams.get('verification');
    const reason = urlParams.get('reason');
    const resetToken = urlParams.get('token');
    
    // Check if this is a password reset link
    if (resetToken) {
        authUI.showResetPassword(resetToken);
        return;
    }
    
    if (verification) {
        // Remove params from URL immediately
        window.history.replaceState({}, document.title, window.location.pathname);
        
        switch(verification) {
            case 'success':
                authUI.showSuccess(
                    'Email Verified! ✅', 
                    'Your email has been verified successfully. You can now sign in to your account.'
                );
                break;
            
            case 'already_verified':
                authUI.showSuccess(
                    'Already Verified ✓', 
                    'Your email is already verified. You can sign in to your account.'
                );
                break;
            
            case 'failed':
                let errorMessage = 'Email verification failed. ';
                switch(reason) {
                    case 'invalid_token':
                        errorMessage += 'The verification link is invalid.';
                        break;
                    case 'expired':
                        errorMessage += 'The verification link has expired. Please request a new one.';
                        break;
                    case 'user_not_found':
                        errorMessage += 'User account not found.';
                        break;
                    case 'token_mismatch':
                        errorMessage += 'The verification link is invalid or has already been used.';
                        break;
                    case 'update_error':
                    case 'server_error':
                        errorMessage += 'A server error occurred. Please try again or contact support.';
                        break;
                    default:
                        errorMessage += 'Please try again or contact support.';
                }
                
                // Show error in modal
                authUI.showLogin();
                setTimeout(() => {
                    alert(errorMessage);
                }, 500);
                break;
        }
    }
});
