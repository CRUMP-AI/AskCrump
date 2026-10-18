(() => {
  'use strict';

  if (window.__crumpCodeLoaderLoaded) return;
  window.__crumpCodeLoaderLoaded = true;

  const STYLE_URL = '/crump-code-5.9.35.css?v=5.9.76-autonomous-integration-2';
  const SCRIPT_URL = '/crump-code-5.9.35.js?v=5.9.76-autonomous-integration-2';
  const DESTINATION_SELECTOR = '[data-crump-code-destination], [data-cv-destination="autonomous"]';
  let featureStatus = null;
  let availabilityPromise = null;
  let availabilityOwnerId = '';
  let availabilityGeneration = 0;
  let workspacePromise = null;

  function currentOwnerId() {
    return String(window.currentUser?.id || '').trim();
  }

  function invalidateOwner(ownerId = currentOwnerId()) {
    const nextOwnerId = String(ownerId || '').trim();
    if (nextOwnerId === availabilityOwnerId) return nextOwnerId;
    availabilityGeneration += 1;
    availabilityOwnerId = nextOwnerId;
    availabilityPromise = null;
    featureStatus = null;
    hideDestinations();
    return nextOwnerId;
  }

  function availabilityIsCurrent(context) {
    return Boolean(
      context
      && context.ownerId
      && context.ownerId === availabilityOwnerId
      && context.ownerId === currentOwnerId()
      && context.generation === availabilityGeneration,
    );
  }

  function syncDestinations(data = null) {
    const feature = data?.features?.code_workspace;
    const provider = data?.providers?.code;
    const isConfigured = Boolean(feature?.configured && provider?.configured);
    const isLocked = isConfigured && feature?.entitled !== true;
    document.querySelectorAll(DESTINATION_SELECTOR).forEach(destination => {
      destination.hidden = !isConfigured;
      destination.disabled = !isConfigured;
      destination.classList.toggle('is-locked', isLocked);
      destination.toggleAttribute('aria-hidden', !isConfigured);
      destination.setAttribute(
        'aria-label',
        isLocked ? 'Autonomous Crump — Professional plan' : 'Autonomous Crump',
      );
    });
    document.body?.classList.toggle('crump-code-configured', isConfigured);
  }

  function hideDestinations() {
    syncDestinations(null);
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
      node.addEventListener('error', () => reject(new Error('Autonomous Crump styles are unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function loadScript() {
    if (window.CrumpCodeWorkspace) return Promise.resolve();
    const existing = document.querySelector('script[data-crump-code-lazy-script]');
    if (existing) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('load', resolve, {once: true});
        existing.addEventListener('error', () => reject(new Error('Autonomous Crump is unavailable')), {once: true});
      });
    }
    return new Promise((resolve, reject) => {
      const node = document.createElement('script');
      node.src = SCRIPT_URL;
      node.async = false;
      node.dataset.crumpCodeLazyScript = 'true';
      node.addEventListener('load', resolve, {once: true});
      node.addEventListener('error', () => reject(new Error('Autonomous Crump is unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function loadWorkspace(data = featureStatus, context = null) {
    if (window.CrumpCodeWorkspace) {
      if (!context || availabilityIsCurrent(context)) {
        window.CrumpCodeWorkspace.hydrateAvailability?.(data);
      }
      return Promise.resolve(window.CrumpCodeWorkspace);
    }
    if (!workspacePromise) {
      window.__crumpCodeBootstrapStatus = data || null;
      workspacePromise = Promise.all([loadStyle(), loadScript()])
        .then(() => {
          if (!window.CrumpCodeWorkspace) throw new Error('Autonomous Crump is unavailable');
          return window.CrumpCodeWorkspace;
        })
        .catch(error => {
          delete window.__crumpCodeBootstrapStatus;
          document.querySelector('link[data-crump-code-lazy-style]')?.remove();
          document.querySelector('script[data-crump-code-lazy-script]')?.remove();
          workspacePromise = null;
          throw error;
        });
    }
    return workspacePromise.then(workspace => {
      if (!context || availabilityIsCurrent(context)) {
        workspace.hydrateAvailability?.(data);
        syncDestinations(data);
      }
      return workspace;
    });
  }

  function configured(data) {
    const feature = data?.features?.code_workspace;
    const provider = data?.providers?.code;
    return Boolean(feature?.configured && provider?.configured);
  }

  async function refreshAvailability() {
    const ownerId = invalidateOwner();
    if (!ownerId) {
      featureStatus = null;
      hideDestinations();
      return false;
    }
    if (availabilityPromise) return availabilityPromise;
    const context = {ownerId, generation: availabilityGeneration};
    let requestPromise;
    requestPromise = (async () => {
      try {
        const response = await fetch('/api/features', {
          credentials: 'same-origin',
          headers: {Accept: 'application/json'},
        });
        const data = response.ok ? await response.json() : null;
        if (!availabilityIsCurrent(context)) return false;
        featureStatus = data;
        if (!configured(data)) {
          hideDestinations();
          return false;
        }
        syncDestinations(data);
        await loadWorkspace(data, context);
        if (!availabilityIsCurrent(context)) return false;
        return true;
      } catch (_) {
        if (availabilityIsCurrent(context)) {
          featureStatus = null;
          hideDestinations();
        }
        return false;
      } finally {
        if (availabilityPromise === requestPromise) availabilityPromise = null;
      }
    })();
    availabilityPromise = requestPromise;
    return availabilityPromise;
  }

  async function open(options = {}) {
    if (!window.CrumpCodeWorkspace && !(await refreshAvailability())) {
      window.showToast?.('Autonomous Crump is not available for this account.', 'info');
      return false;
    }
    return window.CrumpCodeWorkspace?.open?.(options) || false;
  }

  window.CrumpCodeLoader = Object.freeze({load: loadWorkspace, open, refreshAvailability});
  hideDestinations();
  window.addEventListener('crumpvision:ready', () => {
    if (configured(featureStatus)) syncDestinations(featureStatus);
    else hideDestinations();
  });
  window.addEventListener('crump:authenticated-ready', () => {
    invalidateOwner();
    void refreshAvailability();
  });
  window.addEventListener('crump:authentication-required', () => {
    availabilityGeneration += 1;
    availabilityOwnerId = '';
    availabilityPromise = null;
    featureStatus = null;
    hideDestinations();
  });
  if (window.currentUser) void refreshAvailability();
})();
