// ==========================================
// CRUMP AI - AUTH GUARD
// Add to index.html to protect the app
// ==========================================

(async function() {
    // Check if user is authenticated
    const token = localStorage.getItem('crump_auth_token');
    
    if (!token) {
        // No token - redirect to auth page
        window.location.href = '/auth.html';
        return;
    }

    // Verify token is still valid
    try {
        const response = await fetch('/api/auth/me', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            // Token invalid - redirect to auth
            localStorage.removeItem('crump_auth_token');
            window.location.href = '/auth.html';
            return;
        }

        const user = await response.json();
        
        // Store user info globally
        window.currentUser = user;
        
        console.log('✅ Authenticated as:', user.name);
        
        // Update profile manager with authenticated user
        if (window.currentProfile) {
            window.currentProfile.updateProfile({
                name: user.name,
                email: user.email,
                initial: user.name.charAt(0).toUpperCase()
            });
        }

        // Store user ID in chats for server-side storage later
        window.userId = user.userId;
        
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/auth.html';
    }
})();

// Add logout function
window.logout = async function() {
    if (confirm('Are you sure you want to sign out?')) {
        await window.authManager.logout();
        window.location.href = '/auth.html';
    }
};

// Update chat API calls to include auth token
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
    // Add auth token to all API requests
    if (url.startsWith('/api/')) {
        const token = localStorage.getItem('crump_auth_token');
        if (token) {
            options.headers = {
                ...options.headers,
                'Authorization': `Bearer ${token}`
            };
        }
    }
    return originalFetch(url, options);
};

console.log('✅ Auth Guard loaded - App protected');
