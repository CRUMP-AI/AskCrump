(() => {
  'use strict';

  if (window.__crumpCodeLoaderLoaded) return;
  window.__crumpCodeLoaderLoaded = true;

  const STYLE_URL = '/crump-code-5.9.35.css?v=5.9.76-intelligence-architecture-1';
  const SCRIPT_URL = '/crump-code-5.9.35.js?v=5.9.76-credit-confirmation-1';
  let featureStatus = null;
  let availabilityPromise = null;
  let workspacePromise = null;

  function hideDestinations() {
    document.querySelectorAll('[data-crump-code-destination]').forEach(destination => {
      destination.hidden = true;
      destination.classList.remove('is-locked');
      destination.setAttribute('aria-label', 'Code');
    });
    document.body.classList.remove('crump-code-configured');
  }

  function loadStyle() {
    const existing = document.querySelector('link[data-crump-code-lazy-style]');
    if (existing) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const node = document.createElement('link');
      node.rel = 'stylesheet';
      node.href = STYLE_URL;
      node.dataset.crumpCodeLazyStyle = 'true';
      node.addEventListener('load', resolve, {once: true});
      node.addEventListener('error', () => reject(new Error('Code styles unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function loadScript() {
    if (window.CrumpCodeWorkspace) return Promise.resolve();
    const existing = document.querySelector('script[data-crump-code-lazy-script]');
    if (existing) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('load', resolve, {once: true});
        existing.addEventListener('error', () => reject(new Error('Code workspace unavailable')), {once: true});
      });
    }
    return new Promise((resolve, reject) => {
      const node = document.createElement('script');
      node.src = SCRIPT_URL;
      node.async = false;
      node.dataset.crumpCodeLazyScript = 'true';
      node.addEventListener('load', resolve, {once: true});
      node.addEventListener('error', () => reject(new Error('Code workspace unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function loadWorkspace(data = featureStatus) {
    if (window.CrumpCodeWorkspace) {
      window.CrumpCodeWorkspace.hydrateAvailability?.(data);
      return Promise.resolve(window.CrumpCodeWorkspace);
    }
    if (workspacePromise) return workspacePromise;
    window.__crumpCodeBootstrapStatus = data || null;
    workspacePromise = Promise.all([loadStyle(), loadScript()])
      .then(() => {
        if (!window.CrumpCodeWorkspace) throw new Error('Code workspace unavailable');
        window.CrumpCodeWorkspace.hydrateAvailability?.(data);
        return window.CrumpCodeWorkspace;
      })
      .catch(error => {
        delete window.__crumpCodeBootstrapStatus;
        document.querySelector('link[data-crump-code-lazy-style]')?.remove();
        document.querySelector('script[data-crump-code-lazy-script]')?.remove();
        workspacePromise = null;
        hideDestinations();
        throw error;
      });
    return workspacePromise;
  }

  function configured(data) {
    const feature = data?.features?.code_workspace;
    const provider = data?.providers?.code;
    return Boolean(feature?.configured && provider?.configured);
  }

  async function refreshAvailability() {
    if (!window.currentUser) {
      featureStatus = null;
      hideDestinations();
      return false;
    }
    if (availabilityPromise) return availabilityPromise;
    availabilityPromise = (async () => {
      try {
        const response = await fetch('/api/features', {
          credentials: 'same-origin',
          headers: {Accept: 'application/json'},
        });
        const data = response.ok ? await response.json() : null;
        featureStatus = data;
        if (!configured(data)) {
          hideDestinations();
          return false;
        }
        await loadWorkspace(data);
        return true;
      } catch (_) {
        featureStatus = null;
        hideDestinations();
        return false;
      } finally {
        availabilityPromise = null;
      }
    })();
    return availabilityPromise;
  }

  async function open() {
    if (!window.CrumpCodeWorkspace && !(await refreshAvailability())) return false;
    return window.CrumpCodeWorkspace?.open?.() || false;
  }

  window.CrumpCodeLoader = Object.freeze({load: loadWorkspace, open, refreshAvailability});
  window.addEventListener('crump:authenticated-ready', () => { void refreshAvailability(); });
  if (window.currentUser) void refreshAvailability();
})();
