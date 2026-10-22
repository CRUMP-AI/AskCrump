(() => {
  'use strict';

  if (window.__askCrumpHomeDocumentEntryLoaded) return;
  window.__askCrumpHomeDocumentEntryLoaded = true;

  const ENTRY_SELECTOR = '[data-home-document-entry]';

  function openDocumentStudio(event) {
    event.preventDefault();

    if (typeof window.CrumpDocumentStudio?.open !== 'function') {
      window.showToast?.('Document Studio is still loading. Try again in a moment.', 'info');
      event.currentTarget?.focus?.({ preventScroll: true });
      return;
    }

    window.CrumpDocumentStudio.open();
  }

  function wireDocumentEntries() {
    document.querySelectorAll(ENTRY_SELECTOR).forEach((entry) => {
      if (entry.dataset.homeDocumentEntryWired === 'true') return;
      entry.dataset.homeDocumentEntryWired = 'true';
      entry.addEventListener('click', openDocumentStudio);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireDocumentEntries, { once: true });
  } else {
    wireDocumentEntries();
  }

  window.addEventListener('crump:body-runtime-ready', wireDocumentEntries);
})();
