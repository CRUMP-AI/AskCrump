// ==========================================
// CRUMP AI - FRONTEND AUTH MANAGER
// Handles authentication state and API calls
// ==========================================

class AuthManager {
    constructor() {
        this.token = localStorage.getItem('crump_auth_token');
        this.user = null;
        this.loadUser();
    }

    async loadUser() {
        if (!this.token) return null;

        try {
            const response = await fetch('/api/auth/me', {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (response.ok) {
                this.user = await response.json();
                return this.user;
            } else {
                // Token invalid
                this.logout();
                return null;
            }
        } catch (error) {
            console.error('Load user error:', error);
            return null;
        }
    }

    async signup(email, password, name) {
        try {
            const response = await fetch('/api/auth/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, name })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Signup failed');
            }

            return data;
        } catch (error) {
            throw error;
        }
    }

    async verifyEmail(email, code) {
        try {
            const response = await fetch('/api/auth/verify-email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, code })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Verification failed');
            }

            // Store token and user
            this.token = data.token;
            this.user = data.user;
            localStorage.setItem('crump_auth_token', data.token);

            return data;
        } catch (error) {
            throw error;
        }
    }

    async login(email, password, rememberMe = false) {
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, rememberMe })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Login failed');
            }

            // Store token and user
            this.token = data.token;
            this.user = data.user;
            localStorage.setItem('crump_auth_token', data.token);

            return data;
        } catch (error) {
            throw error;
        }
    }

    async logout() {
        try {
            if (this.token) {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.token}`
                    }
                });
            }
        } catch (error) {
            console.error('Logout error:', error);
        } finally {
            this.token = null;
            this.user = null;
            localStorage.removeItem('crump_auth_token');
        }
    }

    isAuthenticated() {
        return !!this.token && !!this.user;
    }

    getUser() {
        return this.user;
    }

    getToken() {
        return this.token;
    }
}

// Global instance
window.authManager = new AuthManager();

console.log('✅ Auth Manager loaded');
