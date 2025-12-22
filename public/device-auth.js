// =====================================================
// DEVICE ID AUTH SYSTEM - Mobile PWA Solution
// =====================================================

class DeviceAuth {
    constructor() {
        this.DEVICE_ID_KEY = 'crump_device_id';
        this.SESSION_KEY = 'crump_session';
        this.deviceId = null;
        this.session = null;
    }

    getDeviceId() {
        if (this.deviceId) return this.deviceId;
        let deviceId = localStorage.getItem(this.DEVICE_ID_KEY);
        if (!deviceId) {
            deviceId = this.generateDeviceId();
            localStorage.setItem(this.DEVICE_ID_KEY, deviceId);
        }
        this.deviceId = deviceId;
        return deviceId;
    }

    generateDeviceId() {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substring(2, 15);
        const userAgent = navigator.userAgent.substring(0, 50).replace(/[^a-zA-Z0-9]/g, '');
        return `${timestamp}-${random}-${userAgent}`;
    }

    async login(email, password) {
        const deviceId = this.getDeviceId();
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, deviceId })
        });
        const data = await response.json();
        if (data.success && data.data) {
            this.session = {
                user: data.data.user,
                token: data.data.token,
                deviceId: deviceId,
                expiresAt: data.data.expiresAt
            };
            localStorage.setItem(this.SESSION_KEY, JSON.stringify(this.session));
        }
        return data;
    }

    async checkSession() {
        const deviceId = this.getDeviceId();
        const localSession = localStorage.getItem(this.SESSION_KEY);
        if (!localSession) return { authenticated: false };
        
        this.session = JSON.parse(localSession);
        const response = await fetch('/api/auth/check-session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ deviceId })
        });
        const data = await response.json();
        if (data.success && data.authenticated) {
            this.session = { ...this.session, user: data.data.user, token: data.data.token };
            localStorage.setItem(this.SESSION_KEY, JSON.stringify(this.session));
            return data;
        }
        this.clearSession();
        return { authenticated: false };
    }

    async logout() {
        const deviceId = this.getDeviceId();
        await fetch('/api/auth/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ deviceId })
        });
        this.clearSession();
    }

    clearSession() {
        this.session = null;
        localStorage.removeItem(this.SESSION_KEY);
    }
}

window.deviceAuth = new DeviceAuth();
console.log('✅ Device Auth System loaded');
