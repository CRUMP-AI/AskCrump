(() => {
  'use strict';

  if (window.__crumpLibraryLoaderLoaded) return;
  window.__crumpLibraryLoaderLoaded = true;

  const STYLE_URL = '/crump-library-5.7.css?v=5.9.76-library-new-routing-1';
  const SCRIPT_URL = '/crump-library-5.7.js?v=5.9.76-library-new-routing-1';
  const DESTINATION_SELECTOR = '[data-crump5930-destination="library"]';
  let loadPromise = null;

  function loadStyle() {
    const existing = document.querySelector('link[data-crump-library-lazy-style]');
    if (existing?.dataset.crumpLibraryLoaded === 'true') return Promise.resolve();
    if (existing) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('load', resolve, {once: true});
        existing.addEventListener('error', () => reject(new Error('Library styles unavailable')), {once: true});
      });
    }
    return new Promise((resolve, reject) => {
      const node = document.createElement('link');
      node.rel = 'stylesheet';
      node.href = STYLE_URL;
      node.dataset.crumpLibraryLazyStyle = 'true';
      node.addEventListener('load', () => {
        node.dataset.crumpLibraryLoaded = 'true';
        resolve();
      }, {once: true});
      node.addEventListener('error', () => reject(new Error('Library styles unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function loadScript() {
    if (window.__crumpLibrary57Loaded && window.CrumpLibrary57?.refresh) return Promise.resolve();
    const existing = document.querySelector('script[data-crump-library-lazy-script]');
    if (existing?.dataset.crumpLibraryLoaded === 'true') return Promise.resolve();
    if (existing) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('load', resolve, {once: true});
        existing.addEventListener('error', () => reject(new Error('Library unavailable')), {once: true});
      });
    }
    return new Promise((resolve, reject) => {
      const node = document.createElement('script');
      node.src = SCRIPT_URL;
      node.async = false;
      node.dataset.crumpLibraryLazyScript = 'true';
      node.addEventListener('load', () => {
        node.dataset.crumpLibraryLoaded = 'true';
        resolve();
      }, {once: true});
      node.addEventListener('error', () => reject(new Error('Library unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function removeIncompleteAssets() {
    document.querySelectorAll('[data-crump-library-lazy-style], [data-crump-library-lazy-script]')
      .forEach(node => {
        if (node.dataset.crumpLibraryLoaded !== 'true') node.remove();
      });
  }

  function ready() {
    const styleReady = document.querySelector('link[data-crump-library-lazy-style]')
      ?.dataset.crumpLibraryLoaded === 'true';
    return Boolean(window.__crumpLibrary57Loaded && window.CrumpLibrary57?.refresh && styleReady);
  }

  function load() {
    if (ready()) {
      return Promise.resolve(window.CrumpLibrary57);
    }
    if (loadPromise) return loadPromise;
    loadPromise = Promise.all([loadStyle(), loadScript()])
      .then(() => {
        if (!window.__crumpLibrary57Loaded || !window.CrumpLibrary57?.refresh) {
          throw new Error('Library unavailable');
        }
        return window.CrumpLibrary57;
      })
      .catch(error => {
        removeIncompleteAssets();
        loadPromise = null;
        throw error;
      });
    return loadPromise;
  }

  function setBusy(busy) {
    document.querySelectorAll(DESTINATION_SELECTOR).forEach(button => {
      button.disabled = busy;
      if (busy) button.setAttribute('aria-busy', 'true');
      else button.removeAttribute('aria-busy');
    });
  }

  document.addEventListener('click', event => {
    const button = event.target.closest?.(DESTINATION_SELECTOR);
    if (!button || ready()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    setBusy(true);
    window.showToast?.('Opening Library…', 'info');
    void load()
      .then(() => {
        setBusy(false);
        if (button.isConnected) button.click();
      })
      .catch(error => {
        setBusy(false);
        window.showToast?.(error?.message || 'Library could not open. Try again.', 'error');
      });
  }, true);

  window.CrumpLibraryLoader = Object.freeze({load});
})();
