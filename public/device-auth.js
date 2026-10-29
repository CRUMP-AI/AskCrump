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

  async confirmIssuedSession(expectedOwnerId = null, expectedEmail = null) {
    try {
      const {response, data} = await window.CrumpAuthTransport.request('/api/auth/check-session', {
        method: 'GET',
        cache: 'no-store',
      }, {
        timeoutMs: window.CrumpAuthTransport.SESSION_TIMEOUT_MS,
        timeoutMessage: 'Session verification took too long.',
      });
      if (!response.ok) {
        return { status: 'unavailable', data };
      }
      if (data.success === true && data.authenticated === true && typeof data.data?.user?.id === 'string' && data.data.user.id.trim()) {
        if ((expectedOwnerId && data.data.user.id !== expectedOwnerId) ||
            (expectedEmail && String(data.data.user.email || '').trim().toLowerCase() !== String(expectedEmail).trim().toLowerCase())) {
          return {status: 'owner_mismatch'};
        }
        return { status: 'valid', data: data.data };
      }
      if (data.success === true && data.authenticated === false) return { status: 'invalid', data };
      return {status: 'unavailable', data};
    } catch (error) {
      return { status: 'unavailable', error };
    }
  }

  async performLogin(email, password) {
    let response;
    let data;
    try {
      ({response, data} = await window.CrumpAuthTransport.request('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password,
          platform: window.CrumpNative?.Capacitor?.getPlatform?.() || window.Capacitor?.getPlatform?.() || 'web',
          deviceName: navigator.userAgent.slice(0, 150),
        }),
      }, {
        timeoutMs: window.CrumpAuthTransport.LOGIN_TIMEOUT_MS,
        timeoutMessage: 'Signing in took too long to confirm. Check your connection and try again.',
      }));
      if (response.ok && data.success === true &&
          (typeof data.data?.user?.id !== 'string' || !data.data.user.id.trim())) {
        const error = new Error('Ask Crump could not confirm the signed-in account. Your saved session has been kept. Please retry.');
        error.code = 'AUTH_INVALID_RESPONSE';
        throw error;
      }
    } catch (error) {
      const ambiguousResponse = error?.code === 'AUTH_REQUEST_TIMEOUT' || error?.code === 'AUTH_INVALID_RESPONSE';
      if (!ambiguousResponse || window.CrumpAPI?.isNative) throw error;

      // A web login can set its HttpOnly cookie before a stalled body finishes.
      // Reconcile that issued session before reporting failure or rotating it again.
      // One bounded readback reconciles an already issued cookie; never repeat
      // the credential POST or leave the form waiting through five timeouts.
      const confirmation = await this.confirmIssuedSession(null, email);
      if (confirmation.status === 'valid') {
        this.acceptSession(confirmation.data);
        return {success: true, data: confirmation.data, recovered: true};
      }
      throw error;
    }

    if (!response.ok || data.success !== true) return {...data, success: false};

    const issuedNativeToken = data.data.sessionToken || null;
    if (issuedNativeToken && window.CrumpAPI?.isNative) {
      await window.CrumpAPI.setSessionToken(issuedNativeToken);
    }

    // A successful login rotates the installation session exactly once. Give the
    // browser a bounded mobile-safe window to expose its new HttpOnly cookie instead
    // of rotating the token again while the first response is still being committed.
    for (const delay of [0, 100, 300, 750, 1500]) {
      if (delay) await new Promise(resolve => setTimeout(resolve, delay));
      const confirmation = await this.confirmIssuedSession(data.data.user.id);
      if (confirmation.status === 'owner_mismatch') {
        return {success: false, code: 'SESSION_OWNER_MISMATCH', error: 'Your active account changed during sign-in. Reload before trying again.'};
      }
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
      await window.CrumpAPI.clearSessionToken?.(issuedNativeToken);
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

  sessionUnavailable(error = null, {commit = true} = {}) {
    const cached = this.cachedUser();
    if (cached && !navigator.onLine) {
      if (commit) this.session = { user: cached, offline: true };
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

  async checkSession({commit = true} = {}) {
    const expectedOwnerId = String(
      this.session?.user?.id || this.cachedUser()?.id || window.currentUser?.id || '',
    ).trim();
    try {
      const {response, data} = await window.CrumpAuthTransport.request('/api/auth/check-session', {
        method: 'GET',
        cache: 'no-store',
      }, {
        timeoutMs: window.CrumpAuthTransport.SESSION_TIMEOUT_MS,
        timeoutMessage: 'Session verification took too long.',
      });

      if (!response.ok) {
        return this.sessionUnavailable(
          new Error(data.error || `Session check failed (${response.status}).`),
          {commit},
        );
      }

      if (data.success === true && data.authenticated === true && typeof data.data?.user?.id === 'string' && data.data.user.id.trim()) {
        if (commit) this.acceptSession(data.data);
        return data;
      }

      if (data.success !== true || data.authenticated !== false) {
        return this.sessionUnavailable(new Error('Session verification returned an incomplete response. Please retry.'), {commit});
      }

      // A definitive successful response saying "not authenticated" is the only
      // bootstrap outcome that clears local identity state.
      if (commit && this.clearLocalState(expectedOwnerId || null) === false) {
        return {success: false, authenticated: false, stale: true};
      }
      return { ...data, success: true, authenticated: false };
    } catch (error) {
      console.warn('[Auth] Session check unavailable:', error);
      return this.sessionUnavailable(error, {commit});
    }
  }

  async logout(allDevices = false) {
    const boundary = window.CrumpAuthBoundary;
    const ownerId = String(
      boundary?.authenticatedUserId?.() || this.session?.user?.id || window.currentUser?.id || '',
    ).trim();
    const revision = Number(boundary?.revision?.() || 0);
    const nativeToken = window.CrumpAPI?.isNative
      ? window.CrumpAPI?.getSessionToken?.() || null
      : null;
    const stillCurrent = () => {
      const knownOwners = [
        boundary?.authenticatedUserId?.(),
        this.session?.user?.id,
        window.currentUser?.id,
      ].map(value => String(value || '').trim()).filter(Boolean);
      const currentRevision = Number(boundary?.revision?.() || 0);
      const unboundNativeSession = !ownerId && Boolean(window.CrumpAPI?.isNative);
      return (Boolean(ownerId) || unboundNativeSession)
        && knownOwners.every(currentOwnerId => currentOwnerId === ownerId)
        && currentRevision === revision;
    };
    if (!stillCurrent()) return {stale: true};
    const ownerHeaders = ownerId ? {'X-Ask-Crump-Expected-Owner': ownerId} : {};
    const isOwnerMismatch = ({response, data} = {}) => response?.status === 409 && (
      data?.code === 'AUTH_OWNER_MISMATCH'
      || data?.staleAuth === true
      || data?.details?.staleAuth === true
    );
    let staleOwnerResponse = false;
    try {
      if (!allDevices && window.CrumpAPI?.isNative) {
        try {
          const unregisterResult = await window.CrumpAuthTransport.request('/api/notifications/register', {
            method: 'DELETE',
            headers: ownerHeaders,
          }, {
            timeoutMs: window.CrumpAuthTransport.SESSION_TIMEOUT_MS,
            timeoutMessage: 'Push-registration cleanup took too long.',
          });
          if (isOwnerMismatch(unregisterResult)) {
            staleOwnerResponse = true;
            return {stale: true};
          }
        } catch (_) {}
      }
      const logoutResult = await window.CrumpAuthTransport.request(allDevices ? '/api/auth/logout-all' : '/api/auth/logout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...ownerHeaders,
        },
      }, {
        timeoutMessage: 'Signing out took too long to confirm.',
      });
      if (isOwnerMismatch(logoutResult)) {
        staleOwnerResponse = true;
        return {stale: true};
      }
    } finally {
      if (staleOwnerResponse || !stillCurrent()) return {stale: true};
      const cleared = await window.CrumpAPI?.clearSessionToken?.(nativeToken);
      if (window.CrumpAPI?.isNative && cleared === false) return {stale: true};
      if (!stillCurrent()) return {stale: true};
      if (this.clearLocalState(ownerId || null) === false) return {stale: true};
      await window.BillingManager?.disconnect?.().catch(() => {});
    }
    return {success: true};
  }

  clearLocalState(expectedOwnerId = null) {
    const expected = String(expectedOwnerId || '').trim();
    const cachedOwnerId = String(this.cachedUser()?.id || '').trim();
    const knownOwners = [
      this.session?.user?.id,
      window.currentUser?.id,
      cachedOwnerId,
    ].map(value => String(value || '').trim()).filter(Boolean);
    if (expected && knownOwners.some(ownerId => ownerId !== expected)) return false;
    const userId = this.session?.user?.id || window.currentUser?.id || cachedOwnerId;
    if (userId) this.clearAccountCache(userId);
    this.session = null;
    window.currentUser = null;
    try { localStorage.removeItem(this.userCacheKey); } catch (_) {}
    return true;
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
