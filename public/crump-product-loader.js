(() => {
  'use strict';

  if (window.__crumpProductLoaderLoaded) return;
  window.__crumpProductLoaderLoaded = true;

  const STYLE_URL = '/crump-product-5.3.css?v=5.9.76-file-library-window-1';
  const SCRIPT_URL = '/crump-product-5.3.js?v=5.9.76-studio-action-labels-1';
  const ACTIVE_PROJECT_KEY = 'askcrump.activeProject53';
  const VIDEO_JOB_KEY = 'askcrump.videoJob53';
  const VIDEO_REQUEST_KEY = 'askcrump.videoRequest53';
  const DESTINATIONS = new Set(['projects', 'manuscripts', 'video', 'library']);
  let loadPromise = null;
  let facade = null;
  let loadedApi = null;

  function stored(key) {
    try { return localStorage.getItem(key) || ''; }
    catch (_) { return ''; }
  }

  function realApi() {
    if (loadedApi) return loadedApi;
    const candidate = window.CrumpProduct53;
    return candidate && candidate !== facade && typeof candidate.open === 'function'
      ? candidate
      : null;
  }

  function styleReady() {
    return document.querySelector('link[data-crump-product-lazy-style]')
      ?.dataset.crumpProductLoaded === 'true';
  }

  function loadStyle() {
    const existing = document.querySelector('link[data-crump-product-lazy-style]');
    if (existing?.dataset.crumpProductLoaded === 'true') return Promise.resolve();
    if (existing) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('load', resolve, {once: true});
        existing.addEventListener('error', () => reject(new Error('Workspace styles unavailable')), {once: true});
      });
    }
    return new Promise((resolve, reject) => {
      const node = document.createElement('link');
      node.rel = 'stylesheet';
      node.href = STYLE_URL;
      node.dataset.crumpProductLazyStyle = 'true';
      node.addEventListener('load', () => {
        node.dataset.crumpProductLoaded = 'true';
        resolve();
      }, {once: true});
      node.addEventListener('error', () => reject(new Error('Workspace styles unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function loadScript() {
    if (realApi()) return Promise.resolve();
    const existing = document.querySelector('script[data-crump-product-lazy-script]');
    if (existing?.dataset.crumpProductLoaded === 'true') return Promise.resolve();
    if (existing) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('load', resolve, {once: true});
        existing.addEventListener('error', () => reject(new Error('Workspace unavailable')), {once: true});
      });
    }
    return new Promise((resolve, reject) => {
      const node = document.createElement('script');
      node.src = SCRIPT_URL;
      node.async = false;
      node.dataset.crumpProductLazyScript = 'true';
      node.addEventListener('load', () => {
        const candidate = window.CrumpProduct53;
        if (candidate && candidate !== facade && typeof candidate.open === 'function') {
          loadedApi = candidate;
          window.CrumpProduct53 = facade;
        }
        node.dataset.crumpProductLoaded = 'true';
        resolve();
      }, {once: true});
      node.addEventListener('error', () => reject(new Error('Workspace unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function removeIncompleteAssets() {
    document.querySelectorAll('[data-crump-product-lazy-style], [data-crump-product-lazy-script]')
      .forEach(node => {
        if (node.dataset.crumpProductLoaded !== 'true') node.remove();
      });
  }

  function load() {
    const api = realApi();
    if (api && styleReady()) return Promise.resolve(api);
    if (loadPromise) return loadPromise;
    loadPromise = Promise.all([loadStyle(), loadScript()])
      .then(() => {
        const loaded = realApi();
        if (!loaded || !styleReady()) throw new Error('Workspace unavailable');
        loadedApi = loaded;
        window.CrumpProduct53 = facade;
        return loadedApi;
      })
      .catch(error => {
        removeIncompleteAssets();
        loadPromise = null;
        throw error;
      });
    return loadPromise;
  }

  function destinationControls(destination) {
    const normalized = String(destination || '').trim();
    if (!DESTINATIONS.has(normalized)) return [];
    return Array.from(document.querySelectorAll(
      `[data-v1-command="${normalized}"], [data-crump5930-destination="${normalized}"]`,
    ));
  }

  function setBusy(destination, busy) {
    destinationControls(destination).forEach(button => {
      button.disabled = busy;
      if (busy) button.setAttribute('aria-busy', 'true');
      else button.removeAttribute('aria-busy');
    });
  }

  function invoke(method, args = [], {destination = '', announce = false} = {}) {
    setBusy(destination, true);
    if (announce) window.showToast?.(`Opening ${destination === 'video' ? 'Video Studio' : destination || 'workspace'}…`, 'info');
    return load()
      .catch(error => {
        window.showToast?.(error?.message || 'That workspace could not open. Try again.', 'error');
        return null;
      })
      .then(api => {
        if (!api) return false;
        const action = api?.[method];
        if (typeof action !== 'function') throw new Error('That workspace action is unavailable');
        return action(...args);
      })
      .finally(() => setBusy(destination, false));
  }

  function cachedProjectTarget() {
    const id = String(stored(ACTIVE_PROJECT_KEY) || '').trim();
    return id ? {id, name: 'Project'} : null;
  }

  facade = Object.freeze({
    open: destination => invoke('open', [destination], {destination, announce: true}),
    openProject: projectId => invoke('openProject', [projectId], {destination: 'projects', announce: true}),
    openFiles: () => invoke('openFiles', [], {destination: 'projects', announce: true}),
    projectTarget: () => realApi()?.projectTarget?.() || cachedProjectTarget(),
    projectForConversation: chatId => invoke('projectForConversation', [chatId]),
    resolveOutcomeProject: chatId => invoke('resolveOutcomeProject', [chatId]),
    keepConversation: options => invoke('keepConversation', [options]),
    keepArtifact: (file, options) => invoke('keepArtifact', [file, options]),
    openManuscript: workspace => invoke('openManuscript', [workspace], {destination: 'manuscripts', announce: true}),
    handleCreationHandoff: handoff => invoke('handleCreationHandoff', [handoff]),
  });

  window.CrumpProduct53 = facade;
  window.CrumpProductLoader = Object.freeze({load});

  function shouldResumeAfterAuthentication() {
    if (stored(VIDEO_JOB_KEY) || stored(VIDEO_REQUEST_KEY) || stored(ACTIVE_PROJECT_KEY)) return true;
    const chatId = String(window.currentChatId || '').trim();
    if (!chatId) return false;
    const chat = (Array.isArray(window.chats) ? window.chats : []).find(
      item => String(item?.id || item?.chat_id || '') === chatId,
    );
    return Boolean(Array.isArray(chat?.messages) && chat.messages.length);
  }

  function loadForPersistedWork() {
    if (!window.currentUser || !shouldResumeAfterAuthentication()) return;
    void load().catch(error => {
      window.showToast?.(error?.message || 'Saved workspace state could not resume yet.', 'error');
    });
  }

  window.addEventListener('crump:authenticated-ready', loadForPersistedWork);
  window.addEventListener('crump:conversation-opened', event => {
    if (realApi() || event?.detail?.fresh !== false) return;
    loadForPersistedWork();
  });

  try {
    if (new URL(window.location.href).searchParams.has('project')) {
      void load().catch(error => {
        window.showToast?.(error?.message || 'That Project could not resume yet.', 'error');
      });
    }
    else loadForPersistedWork();
  } catch (_) {
    loadForPersistedWork();
  }
})();
