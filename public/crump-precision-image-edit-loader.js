(() => {
  'use strict';

  if (window.__crumpPrecisionImageEditLoaderLoaded) return;
  window.__crumpPrecisionImageEditLoaderLoaded = true;

  const STYLE_URL = '/crump-precision-image-edit.css?v=5.9.76-precision-studio-1';
  const SCRIPT_URL = '/crump-precision-image-edit.js?v=5.9.76-precision-studio-1';
  let loadPromise = null;

  function loadStyle() {
    const existing = document.querySelector('link[data-crump-precision-lazy-style]');
    if (existing?.dataset.crumpPrecisionLoaded === 'true') return Promise.resolve();
    if (existing) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('load', resolve, {once: true});
        existing.addEventListener('error', () => reject(new Error('Precision Edit styles unavailable')), {once: true});
      });
    }
    return new Promise((resolve, reject) => {
      const node = document.createElement('link');
      node.rel = 'stylesheet';
      node.href = STYLE_URL;
      node.dataset.crumpPrecisionLazyStyle = 'true';
      node.addEventListener('load', () => {
        node.dataset.crumpPrecisionLoaded = 'true';
        resolve();
      }, {once: true});
      node.addEventListener('error', () => reject(new Error('Precision Edit styles unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function loadScript() {
    if (window.CrumpPrecisionImageEditor) return Promise.resolve();
    const existing = document.querySelector('script[data-crump-precision-lazy-script]');
    if (existing?.dataset.crumpPrecisionLoaded === 'true') return Promise.resolve();
    if (existing) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('load', resolve, {once: true});
        existing.addEventListener('error', () => reject(new Error('Precision Edit unavailable')), {once: true});
      });
    }
    return new Promise((resolve, reject) => {
      const node = document.createElement('script');
      node.src = SCRIPT_URL;
      node.async = false;
      node.dataset.crumpPrecisionLazyScript = 'true';
      node.addEventListener('load', () => {
        node.dataset.crumpPrecisionLoaded = 'true';
        resolve();
      }, {once: true});
      node.addEventListener('error', () => reject(new Error('Precision Edit unavailable')), {once: true});
      document.head.appendChild(node);
    });
  }

  function removeIncompleteAssets() {
    document.querySelectorAll('[data-crump-precision-lazy-style], [data-crump-precision-lazy-script]')
      .forEach(node => {
        if (node.dataset.crumpPrecisionLoaded !== 'true') node.remove();
      });
  }

  function load() {
    const styleReady = document.querySelector('link[data-crump-precision-lazy-style]')
      ?.dataset.crumpPrecisionLoaded === 'true';
    if (window.CrumpPrecisionImageEditor && styleReady) {
      return Promise.resolve(window.CrumpPrecisionImageEditor);
    }
    if (loadPromise) return loadPromise;
    loadPromise = Promise.all([loadStyle(), loadScript()])
      .then(() => {
        if (!window.CrumpPrecisionImageEditor) throw new Error('Precision Edit unavailable');
        return window.CrumpPrecisionImageEditor;
      })
      .catch(error => {
        removeIncompleteAssets();
        loadPromise = null;
        throw error;
      });
    return loadPromise;
  }

  window.CrumpPrecisionImageEditLoader = Object.freeze({load});
})();
