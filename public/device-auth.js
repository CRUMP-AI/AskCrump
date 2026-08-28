class DeviceAuth {
  constructor() {
    this.session = null;
    this.userCacheKey = 'crump_user_cache_v4';
    this.loginPromise = null;
  }

  // Retained for compatibility only. This ID is telemetry, never authentication.
  getDeviceId() {
    return window.CrumpAPI?.installationId?.() || 'web';
  }

  acceptSession(data) {
    if (!data?.user) return;
    this.session = { user: data.user, expiresAt: data.expiresAt };
    try { localStorage.setItem(this.userCacheKey, JSON.stringify(data.user)); } catch (_) {}
  }

  async confirmIssuedSession() {
    try {
      const response = await fetch('/api/auth/check-session', {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
      });
      const data = await response.json().catch(() => ({ success: false, authenticated: false }));
      if (!response.ok) {
        return { status: 'unavailable', data };
      }
      if (data.authenticated && data.data?.user) {
        return { status: 'valid', data: data.data };
      }
      return { status: 'invalid', data };
    } catch (error) {
      return { status: 'unavailable', error };
    }
  }

  async performLogin(email, password) {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        email,
        password,
        platform: window.CrumpNative?.Capacitor?.getPlatform?.() || window.Capacitor?.getPlatform?.() || 'web',
        deviceName: navigator.userAgent.slice(0, 150),
      }),
    });
    const data = await response.json().catch(() => ({ success: false, error: 'Invalid server response.' }));

    if (!(response.ok && data.success && data.data?.user)) {
      return data;
    }

    if (data.data.sessionToken && window.CrumpAPI?.isNative) {
      await window.CrumpAPI.setSessionToken(data.data.sessionToken);
    }

    // A successful login rotates the installation session exactly once. Give the
    // browser a short bounded window to expose its new HttpOnly cookie instead of
    // rotating the token again while the first response is still being committed.
    for (const delay of [0, 75, 200]) {
      if (delay) await new Promise(resolve => setTimeout(resolve, delay));
      const confirmation = await this.confirmIssuedSession();
      if (confirmation.status === 'valid') {
        const confirmedData = {
          ...data.data,
          ...confirmation.data,
          sessionToken: data.data.sessionToken,
        };
        this.acceptSession(confirmedData);
        return { ...data, data: confirmedData };
      }

      if (confirmation.status === 'unavailable') {
        // Do not turn a successful login into a logout because the confirmation probe
        // hit a transient network/server failure. The issued credential remains stored.
        this.acceptSession(data.data);
        return data;
      }

    }

    if (window.CrumpAPI?.isNative) {
      await window.CrumpAPI.clearSessionToken?.();
    }

    return {
      success: false,
      error: data.error || 'Your session could not be established. Please try again.',
      code: 'SESSION_ESTABLISHMENT_FAILED',
    };
  }

  async login(email, password) {
    if (this.loginPromise) return this.loginPromise;
    this.loginPromise = this.performLogin(email, password)
      .finally(() => { this.loginPromise = null; });
    return this.loginPromise;
  }

  cachedUser() {
    try {
      return JSON.parse(localStorage.getItem(this.userCacheKey) || 'null');
    } catch (_) {
      return null;
    }
  }

  sessionUnavailable(error = null) {
    const cached = this.cachedUser();
    if (cached && !navigator.onLine) {
      this.session = { user: cached, offline: true };
      return { success: true, authenticated: true, offline: true, data: { user: cached } };
    }

    // Preserve the browser cookie/native token and local cache. A temporary 5xx,
    // rate-limit, or network interruption must not destroy a valid persisted session.
    return {
      success: false,
      authenticated: false,
      unavailable: true,
      error: error?.message || 'Session verification is temporarily unavailable.',
    };
  }

  async checkSession() {
    try {
      await window.CrumpAPI?.ready;
      const response = await fetch('/api/auth/check-session', { method: 'GET' });
      const data = await response.json().catch(() => ({ success: false, authenticated: false }));

      if (!response.ok) {
        return this.sessionUnavailable(new Error(data.error || `Session check failed (${response.status}).`));
      }

      if (data.authenticated && data.data?.user) {
        this.acceptSession(data.data);
        return data;
      }

      // A definitive successful response saying "not authenticated" is the only
      // bootstrap outcome that clears local identity state.
      this.clearLocalState();
      return { ...data, success: true, authenticated: false };
    } catch (error) {
      console.warn('[Auth] Session check unavailable:', error);
      return this.sessionUnavailable(error);
    }
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
