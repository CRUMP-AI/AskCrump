(() => {
  'use strict';

  const SESSION_KEY = 'ask_crump_session_v4';
  const INSTALLATION_KEY = 'ask_crump_installation_id';
  let native = Boolean(window.Capacitor?.isNativePlatform?.() || window.CrumpNative?.isNative);
  const isNative = () => Boolean(native || window.Capacitor?.isNativePlatform?.() || window.CrumpNative?.isNative);
  const apiBase = () => isNative() ? (window.CRUMP_CONFIG?.apiBase || 'https://www.askcrump.com') : '';
  const originalFetch = window.fetch.bind(window);
  let sessionToken = null;
  let tokenMutation = Promise.resolve();
  let readyResolve;
  const ready = new Promise(resolve => { readyResolve = resolve; });

  function secureStorage() {
    return window.CrumpNative?.SecureStorage || window.Capacitor?.Plugins?.SecureStorage;
  }

  async function secureGet(key) {
    if (!isNative()) return null;
    const store = secureStorage();
    if (!store) return null;
    try {
      const result = await store.get(key);
      return typeof result === 'object' && result !== null && 'value' in result ? result.value : result;
    } catch (_) {
      try {
        const result = await store.get({ key });
        return result?.value ?? result ?? null;
      } catch (_) {
        return null;
      }
    }
  }

  async function secureSet(key, value) {
    if (!isNative()) return;
    const store = secureStorage();
    if (!store) throw new Error('Native secure storage is unavailable. Run npm install and npx cap sync.');
    try {
      await store.set(key, value);
    } catch (_) {
      await store.set({ key, value });
    }
  }

  async function secureRemove(key) {
    if (!isNative()) return;
    const store = secureStorage();
    if (!store) return;
    try {
      await store.remove(key);
    } catch (_) {
      try { await store.remove({ key }); } catch (_) {}
    }
  }

  async function initialize() {
    native = isNative();
    if (native) {
      sessionToken = await secureGet(SESSION_KEY);
    }
    readyResolve();
  }

  if (window.CrumpNative || !isNative()) {
    initialize();
  } else {
    window.addEventListener('crump:native-ready', initialize, { once: true });
    setTimeout(initialize, 2500);
  }

  function mutateSessionToken(token, expectedToken, compareExpected) {
    const nextToken = token || null;
    const operation = tokenMutation.catch(() => {}).then(async () => {
      if (compareExpected && sessionToken !== expectedToken) return false;
      const previousToken = sessionToken;
      sessionToken = nextToken;
      try {
        if (isNative()) {
          if (nextToken) await secureSet(SESSION_KEY, nextToken);
          else await secureRemove(SESSION_KEY);
        }
      } catch (error) {
        if (sessionToken === nextToken) sessionToken = previousToken;
        throw error;
      }
      return true;
    });
    tokenMutation = operation.catch(() => {});
    return operation;
  }

  function setSessionToken(token) {
    return mutateSessionToken(token, undefined, false);
  }

  function clearSessionToken(expectedToken) {
    return mutateSessionToken(null, expectedToken, arguments.length > 0);
  }

  function installationId() {
    let id = null;
    try { id = localStorage.getItem(INSTALLATION_KEY); } catch (_) {}
    if (!id) {
      id = crypto.randomUUID?.() || `${Date.now()}-${crypto.getRandomValues(new Uint32Array(2)).join('-')}`;
      try { localStorage.setItem(INSTALLATION_KEY, id); } catch (_) {}
    }
    return id;
  }

  async function apiFetch(input, init = {}) {
    await ready;
    const originalUrl = typeof input === 'string' ? input : input.url;
    const base = apiBase();
    const isApi = originalUrl.startsWith('/api/') || (base && originalUrl.startsWith(`${base}/api/`));
    if (!isApi) return originalFetch(input, init);

    const url = originalUrl.startsWith('/api/') ? `${base}${originalUrl}` : originalUrl;
    const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined));
    native = isNative();
    headers.set('X-Crump-Client', native ? 'native' : 'web');
    headers.set('X-Crump-Platform', window.CrumpNative?.Capacitor?.getPlatform?.() || window.Capacitor?.getPlatform?.() || (native ? 'native' : 'web'));
    headers.set('X-Device-Name', navigator.userAgent.slice(0, 150));
    headers.set('X-Installation-ID', installationId());
    const requestToken = native ? sessionToken : null;
    if (native && requestToken) headers.set('Authorization', `Bearer ${requestToken}`);

    const response = await originalFetch(url, {
      ...init,
      headers,
      credentials: 'include',
    });
    if (response.status === 401 && native) {
      await clearSessionToken(requestToken);
    }
    return response;
  }

  window.fetch = apiFetch;
  window.CrumpAPI = {
    fetch: apiFetch,
    ready,
    get isNative() { return isNative(); },
    get apiBase() { return apiBase(); },
    installationId,
    setSessionToken,
    clearSessionToken,
    getSessionToken: () => sessionToken,
  };
})();
