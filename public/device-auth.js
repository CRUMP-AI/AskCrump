class DeviceAuth {
  constructor() {
    this.session = null;
    this.userCacheKey = 'crump_user_cache_v4';
  }

  // Retained for compatibility only. This ID is telemetry, never authentication.
  getDeviceId() {
    return window.CrumpAPI?.installationId?.() || 'web';
  }

  async login(email, password) {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email,
        password,
        platform: window.CrumpNative?.Capacitor?.getPlatform?.() || window.Capacitor?.getPlatform?.() || 'web',
        deviceName: navigator.userAgent.slice(0, 150),
      }),
    });
    const data = await response.json().catch(() => ({ success: false, error: 'Invalid server response.' }));
    if (response.ok && data.success && data.data?.user) {
      if (data.data.sessionToken && window.CrumpAPI?.isNative) {
        await window.CrumpAPI.setSessionToken(data.data.sessionToken);
      }
      this.session = { user: data.data.user, expiresAt: data.data.expiresAt };
      try { localStorage.setItem(this.userCacheKey, JSON.stringify(data.data.user)); } catch (_) {}
    }
    return data;
  }

  async checkSession() {
    try {
      await window.CrumpAPI?.ready;
      const response = await fetch('/api/auth/check-session', { method: 'GET' });
      const data = await response.json().catch(() => ({ success: false, authenticated: false }));
      if (response.ok && data.authenticated && data.data?.user) {
        this.session = { user: data.data.user, expiresAt: data.data.expiresAt };
        try { localStorage.setItem(this.userCacheKey, JSON.stringify(data.data.user)); } catch (_) {}
        return data;
      }
    } catch (error) {
      console.warn('[Auth] Session check unavailable:', error);
      try {
        const cached = JSON.parse(localStorage.getItem(this.userCacheKey) || 'null');
        if (cached && !navigator.onLine) {
          this.session = { user: cached, offline: true };
          return { success: true, authenticated: true, offline: true, data: { user: cached } };
        }
      } catch (_) {}
    }
    this.clearLocalState();
    return { success: true, authenticated: false };
  }

  async logout(allDevices = false) {
    try {
      if (!allDevices && window.CrumpAPI?.isNative) {
        try { await fetch('/api/notifications/register', { method: 'DELETE' }); } catch (_) {}
      }
      await fetch(allDevices ? '/api/auth/logout-all' : '/api/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
    } finally {
      await window.CrumpAPI?.clearSessionToken?.();
      this.clearLocalState();
    }
  }

  clearLocalState() {
    const userId = this.session?.user?.id || window.currentUser?.id;
    if (userId) this.clearAccountCache(userId);
    this.session = null;
    window.currentUser = null;
    try { localStorage.removeItem(this.userCacheKey); } catch (_) {}
  }

  clearAccountCache(userId) {
    const safeUserId = String(userId || '').replace(/[^a-zA-Z0-9_-]/g, '');
    if (!safeUserId) return;
    const suffix = `:${safeUserId}`;
    const removablePrefixes = [
      'crump_chats', 'crump_current_chat', 'crump_user_profile',
      'crump_user_initial', 'crump_assistant_name', 'crump_work_mode',
      'crump_work_start', 'crump_work_end', 'crump_has_onboarded',
      'crump_deleted_chats_v4', 'crump_sync_queue_v4', 'crump_last_sync_v4',
      'crump_user_profile_v4', 'crump_tutorial_completed_v3',
    ];
    try {
      for (let index = localStorage.length - 1; index >= 0; index -= 1) {
        const key = localStorage.key(index);
        if (!key?.endsWith(suffix)) continue;
        if (removablePrefixes.some(prefix => key.startsWith(prefix))) localStorage.removeItem(key);
      }
    } catch (_) {}
  }
}

window.deviceAuth = new DeviceAuth();
