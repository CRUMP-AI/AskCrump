(() => {
  'use strict';

  if (window.__crumpLibrary57Loaded) return;
  window.__crumpLibrary57Loaded = true;

  const SOURCE_ACCEPT = '.docx,.pdf,.epub,.txt,.md,application/pdf,application/epub+zip,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  const COVER_ACCEPT = 'image/jpeg,image/png,image/webp,image/heic,image/heif,image/*';
  const PREF_KEY = 'askcrump.library57.preferences';
  const COVER_URL_DEFAULT_TTL_SECONDS = 1200;
  const COVER_URL_SAFETY_MS = 30 * 1000;
  const LAYOUTS = new Set(['grid', 'list', 'book']);
  const SORTS = new Set(['updated', 'title', 'author', 'status', 'words', 'project']);
  const COVER_FILTERS = new Set(['all', 'imported', 'created', 'front', 'complete', 'needs-cover']);

  function readPreferences() {
    try {
      const raw = JSON.parse(localStorage.getItem(PREF_KEY) || '{}');
      return {
        layout: LAYOUTS.has(raw.layout) ? raw.layout : 'grid',
        sort: SORTS.has(raw.sort) ? raw.sort : 'updated',
        coverFilter: COVER_FILTERS.has(raw.coverFilter) ? raw.coverFilter : 'all',
      };
    } catch (_) {
      return {layout: 'grid', sort: 'updated', coverFilter: 'all'};
    }
  }

  const preferences = readPreferences();
  const state = {
    books: [],
    deletedBooks: [],
    projects: [],
    projectLimit: -1,
    search: '',
    status: 'all',
    coverFilter: preferences.coverFilter,
    sort: preferences.sort,
    layout: preferences.layout,
    installed: false,
    modal: null,
    modalReturnFocus: null,
    coverUrls: new Map(),
    coverSignControllers: new Map(),
  };

  const byId = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);

  function manuscriptExportDeliveryRuntime() {
    if (window.CrumpManuscriptExportDelivery?.version === 1) {
      return window.CrumpManuscriptExportDelivery;
    }
    const runKey = '__crumpManuscriptExportRun';
    const sequenceKey = '__crumpManuscriptExportRunSequence';
    const cleanupByRun = new WeakMap();
    const abortError = () => {
      const error = new Error('The manuscript export was cancelled after the account changed.');
      error.name = 'AbortError';
      return error;
    };
    const runtime = Object.freeze({
      version: 1,
      begin(surface, userId) {
        const normalizedUserId = String(userId || '').trim();
        const normalizedSurface = String(surface || '').trim();
        if (!normalizedUserId || !normalizedSurface) return null;
        const active = window[runKey];
        if (active && !active.controller?.signal?.aborted) return null;
        const token = Math.max(0, Number(window[sequenceKey]) || 0) + 1;
        window[sequenceKey] = token;
        const run = {
          token,
          controller: new AbortController(),
          userId: normalizedUserId,
          surface: normalizedSurface,
        };
        window[runKey] = run;
        return run;
      },
      isCurrent(run, userId) {
        return Boolean(
          run
          && window[runKey] === run
          && !run.controller?.signal?.aborted
          && run.userId === String(userId || '').trim()
        );
      },
      finish(run) {
        cleanupByRun.get(run)?.();
        cleanupByRun.delete(run);
        if (window[runKey] === run) window[runKey] = null;
      },
      attachCleanup(run, cleanup) {
        if (!run || typeof cleanup !== 'function') return;
        let complete = false;
        cleanupByRun.set(run, () => {
          if (complete) return;
          complete = true;
          cleanup();
        });
      },
      abort() {
        const run = window[runKey];
        if (run?.controller && !run.controller.signal.aborted) run.controller.abort();
        cleanupByRun.get(run)?.();
        cleanupByRun.delete(run);
        if (window[runKey] === run) window[runKey] = null;
      },
      async deliver(file, run, shouldProceed = () => true) {
        const canProceed = () => this.isCurrent(run, run?.userId) && shouldProceed() !== false;
        if (!canProceed()) throw abortError();
        const fileId = String(file?.id || '').trim();
        if (!fileId) {
          throw new Error('Delivery could not be verified. Check Files before trying again.');
        }
        const canonicalFile = {...file, id: fileId, url: ''};
        const canonicalOpen = window.CrumpFileTools?.open;
        if (typeof canonicalOpen === 'function') {
          try {
            const opened = await Promise.resolve(canonicalOpen(canonicalFile, true, {
              signal: run.controller.signal,
              shouldProceed: canProceed,
            }));
            if (!canProceed()) throw abortError();
            if (opened === true) return true;
          } catch (error) {
            if (!canProceed()) throw abortError();
            // Web/PWA can recover through the authenticated owner-checked endpoint below.
          }
        }
        if (!canProceed()) throw abortError();
        if (window.CrumpAPI?.isNative) {
          throw new Error('The manuscript is saved in Files, but private delivery could not start here. Retry from Files.');
        }
        const link = document.createElement('a');
        link.href = `/api/files/${encodeURIComponent(fileId)}/content?download=1`;
        link.download = String(file?.name || 'manuscript');
        link.hidden = true;
        document.body.appendChild(link);
        if (!canProceed()) {
          link.remove();
          throw abortError();
        }
        link.click();
        link.remove();
        return true;
      },
    });
    window.CrumpManuscriptExportDelivery = runtime;
    return runtime;
  }

  const manuscriptExportDelivery = manuscriptExportDeliveryRuntime();
  let libraryAuthSequence = 0;
  let libraryStateUserId = '';
  let libraryOperationSequence = 0;
  let libraryModalSequence = 0;
  const libraryFileDeliveryControllers = new Set();
  const libraryOperations = new Set();
  const libraryOverlayOperations = new WeakMap();
  const libraryModalIdentity = new WeakMap();
  const libraryRefreshes = new Map();
  const libraryRefreshGenerations = new Map();
  const LIBRARY_MUTATION_RECONCILIATION_DELAY_MS = 1600;
  let libraryMutationReconciliationTimer = null;
  let libraryMutationReconciliationContext = null;
  let libraryMutationReconciliationSequence = 0;

  function libraryAbortError(message = 'This Library action is no longer current.') {
    return Object.assign(new Error(message), {name: 'AbortError'});
  }

  function currentLibraryUserId() {
    const currentUserId = String(window.currentUser?.id || '').trim();
    if (!currentUserId) return '';
    const authenticatedUserId = window.CrumpProductLoader?.authenticatedUserId;
    if (typeof authenticatedUserId !== 'function') return currentUserId;
    return String(authenticatedUserId() || '').trim() === currentUserId ? currentUserId : '';
  }

  function libraryOperationContext() {
    const userId = currentLibraryUserId();
    if (libraryStateUserId && libraryStateUserId !== userId) resetLibraryAuthMemory();
    libraryStateUserId = userId;
    return {userId, sequence: libraryAuthSequence};
  }

  function libraryOperationIsCurrent(context) {
    return Boolean(
      context?.userId
      && context.sequence === libraryAuthSequence
      && context.userId === libraryStateUserId
      && context.userId === currentLibraryUserId()
    );
  }

  function beginLibraryOperation(surface, {
    overlay = null,
    modalSensitive = Boolean(overlay),
    resourceType = '',
    resourceId = '',
    resourceCurrent = null,
  } = {}) {
    const auth = libraryOperationContext();
    if (!auth.userId) return null;
    const operation = {
      id: ++libraryOperationSequence,
      surface: String(surface || 'library'),
      userId: auth.userId,
      authSequence: auth.sequence,
      controller: new AbortController(),
      overlay,
      modalSensitive: Boolean(modalSensitive),
      modalSequence: libraryModalSequence,
      expectedModal: overlay || state.modal || null,
      modalIdentity: overlay ? libraryModalIdentity.get(overlay) || null : null,
      resourceType: String(resourceType || ''),
      resourceId: String(resourceId || ''),
      resourceCurrent: typeof resourceCurrent === 'function' ? resourceCurrent : null,
      finished: false,
    };
    libraryOperations.add(operation);
    if (overlay) {
      const overlayOperations = libraryOverlayOperations.get(overlay) || new Set();
      overlayOperations.add(operation);
      libraryOverlayOperations.set(overlay, overlayOperations);
    }
    return operation;
  }

  function attachLibraryOperationOverlay(operation, overlay, {
    resourceType = operation?.resourceType || '',
    resourceId = operation?.resourceId || '',
  } = {}) {
    if (!operation || !overlay) return false;
    const previous = operation.overlay;
    if (previous && previous !== overlay) {
      libraryOverlayOperations.get(previous)?.delete(operation);
    }
    operation.overlay = overlay;
    operation.modalSensitive = true;
    operation.expectedModal = overlay;
    operation.modalSequence = libraryModalSequence;
    operation.modalIdentity = libraryModalIdentity.get(overlay) || null;
    operation.resourceType = String(resourceType || '');
    operation.resourceId = String(resourceId || '');
    const overlayOperations = libraryOverlayOperations.get(overlay) || new Set();
    overlayOperations.add(operation);
    libraryOverlayOperations.set(overlay, overlayOperations);
    return true;
  }

  function libraryOperationAccountIsCurrent(operation) {
    return Boolean(
      operation?.userId
      && operation.authSequence === libraryAuthSequence
      && operation.userId === libraryStateUserId
      && operation.userId === currentLibraryUserId()
    );
  }

  function activeLibraryOperation(operation) {
    if (!operation || operation.finished || operation.controller?.signal?.aborted || !libraryOperationAccountIsCurrent(operation)) return false;
    if (operation.modalSensitive) {
      if (operation.overlay) {
        if (
          state.modal !== operation.overlay
          || !operation.overlay.isConnected
          || libraryModalIdentity.get(operation.overlay) !== operation.modalIdentity
          || (operation.resourceType && operation.overlay.dataset.crump57ResourceType !== operation.resourceType)
          || (operation.resourceId && operation.overlay.dataset.crump57ResourceId !== operation.resourceId)
        ) return false;
      } else if (
        libraryModalSequence !== operation.modalSequence
        || state.modal !== operation.expectedModal
      ) return false;
    }
    if (operation.resourceCurrent) {
      try {
        if (operation.resourceCurrent() === false) return false;
      } catch (_) {
        return false;
      }
    }
    return true;
  }

  function assertLibraryOperationCurrent(operation) {
    if (!activeLibraryOperation(operation)) throw libraryAbortError();
  }

  function finishLibraryOperation(operation) {
    if (!operation) return;
    operation.finished = true;
    libraryOperations.delete(operation);
    if (operation.overlay) libraryOverlayOperations.get(operation.overlay)?.delete(operation);
  }

  function abortLibraryOverlayOperations(overlay) {
    const operations = libraryOverlayOperations.get(overlay);
    operations?.forEach(operation => {
      if (!operation.controller.signal.aborted) operation.controller.abort();
      finishLibraryOperation(operation);
    });
    if (overlay) libraryOverlayOperations.delete(overlay);
  }

  function abortAllLibraryOperations() {
    libraryOperations.forEach(operation => {
      if (!operation.controller.signal.aborted) operation.controller.abort();
    });
    libraryOperations.clear();
  }

  function beginLibraryRefresh(key, parentOperation = null, {replaceExisting = true} = {}) {
    if (parentOperation && !activeLibraryOperation(parentOperation)) return null;
    const auth = libraryOperationContext();
    if (!auth.userId) return null;
    const previous = libraryRefreshes.get(key);
    if (previous && !previous.controller.signal.aborted) {
      if (!replaceExisting) return null;
      previous.controller.abort();
    }
    previous?.detachParent?.();
    const generation = Math.max(0, Number(libraryRefreshGenerations.get(key)) || 0) + 1;
    libraryRefreshGenerations.set(key, generation);
    const controller = new AbortController();
    let resolveCompletion = null;
    const completion = new Promise(resolve => { resolveCompletion = resolve; });
    let detachParent = null;
    if (parentOperation?.controller?.signal) {
      const abortFromParent = () => controller.abort();
      parentOperation.controller.signal.addEventListener('abort', abortFromParent, {once: true});
      detachParent = () => parentOperation.controller.signal.removeEventListener('abort', abortFromParent);
    }
    const refresh = {
      key,
      generation,
      controller,
      userId: auth.userId,
      authSequence: auth.sequence,
      parentOperation,
      detachParent,
      completion,
      resolveCompletion,
      completed: false,
    };
    libraryRefreshes.set(key, refresh);
    return refresh;
  }

  function libraryRefreshIsCurrent(refresh) {
    return Boolean(
      refresh
      && libraryRefreshes.get(refresh.key) === refresh
      && !refresh.controller.signal.aborted
      && refresh.userId === currentLibraryUserId()
      && refresh.userId === libraryStateUserId
      && refresh.authSequence === libraryAuthSequence
      && (!refresh.parentOperation || activeLibraryOperation(refresh.parentOperation))
    );
  }

  function finishLibraryRefresh(refresh) {
    if (!refresh) return;
    refresh.detachParent?.();
    if (!refresh.completed) {
      refresh.completed = true;
      refresh.resolveCompletion?.();
    }
    if (libraryRefreshes.get(refresh.key) === refresh) libraryRefreshes.delete(refresh.key);
  }

  function abortAllLibraryRefreshes() {
    libraryRefreshes.forEach(refresh => {
      if (!refresh.controller.signal.aborted) refresh.controller.abort();
      refresh.detachParent?.();
      if (!refresh.completed) {
        refresh.completed = true;
        refresh.resolveCompletion?.();
      }
    });
    libraryRefreshes.clear();
    libraryRefreshGenerations.clear();
  }

  function clearLibraryMutationReconciliation() {
    if (libraryMutationReconciliationTimer !== null) {
      window.clearTimeout(libraryMutationReconciliationTimer);
      libraryMutationReconciliationTimer = null;
    }
    libraryMutationReconciliationContext = null;
    libraryMutationReconciliationSequence += 1;
  }

  function libraryOverlayHasActiveOperations(overlay) {
    const operations = overlay ? libraryOverlayOperations.get(overlay) : null;
    if (!operations) return false;
    return [...operations].some(operation => activeLibraryOperation(operation));
  }

  function currentLibraryRefresh(key) {
    const refresh = libraryRefreshes.get(key);
    return libraryRefreshIsCurrent(refresh) ? refresh : null;
  }

  function libraryMutationReconciliationIsCurrent(context) {
    return Boolean(
      libraryOperationIsCurrent(context)
      && (
        !Number.isFinite(context?.reconciliationSequence)
        || context.reconciliationSequence === libraryMutationReconciliationSequence
      )
    );
  }

  async function reconcileLibraryViews(context, {retryAfterBusyBooks = false} = {}) {
    if (!libraryMutationReconciliationIsCurrent(context)) return false;
    const busyBooksRefresh = currentLibraryRefresh('books');
    if (busyBooksRefresh) {
      if (!retryAfterBusyBooks) return false;
      await busyBooksRefresh.completion;
      if (!libraryMutationReconciliationIsCurrent(context)) return false;
      return reconcileLibraryViews(context, {retryAfterBusyBooks: false});
    }
    const refreshed = await refreshBooks({
      showSkeleton: false,
      includeDeleted: false,
      replaceExisting: false,
    });
    if (!refreshed) {
      const racedBooksRefresh = currentLibraryRefresh('books');
      if (!retryAfterBusyBooks || !racedBooksRefresh) return false;
      await racedBooksRefresh.completion;
      if (!libraryMutationReconciliationIsCurrent(context)) return false;
      return reconcileLibraryViews(context, {retryAfterBusyBooks: false});
    }
    if (!libraryMutationReconciliationIsCurrent(context)) return false;
    const overlay = state.modal;
    if (
      !overlay?.isConnected
      || overlay.dataset.crump57ResourceType !== 'deleted-books'
      || libraryOverlayHasActiveOperations(overlay)
    ) return true;
    const modalIdentity = libraryModalIdentity.get(overlay) || null;
    const deletedRefreshed = await refreshDeletedBooks(null, {replaceExisting: false});
    if (
      !deletedRefreshed
      || !libraryMutationReconciliationIsCurrent(context)
      || state.modal !== overlay
      || !overlay.isConnected
      || libraryModalIdentity.get(overlay) !== modalIdentity
      || libraryOverlayHasActiveOperations(overlay)
    ) return true;
    const deletedList = overlay.querySelector('#crump57DeletedList');
    if (deletedList) renderDeletedBooks(deletedList);
    return true;
  }

  function scheduleLibraryMutationReconciliation(operation) {
    if (!libraryOperationAccountIsCurrent(operation)) return false;
    clearLibraryMutationReconciliation();
    const context = Object.freeze({
      userId: operation.userId,
      sequence: operation.authSequence,
      reconciliationSequence: libraryMutationReconciliationSequence,
    });
    libraryMutationReconciliationContext = context;
    const timer = window.setTimeout(() => {
      if (libraryMutationReconciliationTimer === timer) {
        libraryMutationReconciliationTimer = null;
        libraryMutationReconciliationContext = null;
      }
      if (!libraryMutationReconciliationIsCurrent(context)) return;
      void reconcileLibraryViews(context, {retryAfterBusyBooks: true});
    }, LIBRARY_MUTATION_RECONCILIATION_DELAY_MS);
    libraryMutationReconciliationTimer = timer;
    return true;
  }

  async function refreshAfterPossibleMutation(operation) {
    if (!libraryOperationAccountIsCurrent(operation)) return false;
    const context = Object.freeze({
      userId: operation.userId,
      sequence: operation.authSequence,
    });
    scheduleLibraryMutationReconciliation(operation);
    return reconcileLibraryViews(context);
  }

  function show(message, type = 'success') {
    if (window.showToast) window.showToast(message, type);
    else console[type === 'error' ? 'error' : 'log'](message);
  }

  function savePreferences() {
    try {
      localStorage.setItem(PREF_KEY, JSON.stringify({
        layout: state.layout,
        sort: state.sort,
        coverFilter: state.coverFilter,
      }));
    } catch (_) {}
  }

  async function api(path, options = {}) {
    const init = {...options};
    const headers = {...(init.headers || {})};
    const expectedOwnerId = currentLibraryUserId();
    if (expectedOwnerId) headers['X-Ask-Crump-Expected-Owner'] = expectedOwnerId;
    if (init.body && typeof init.body !== 'string') {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(init.body);
    }
    const response = await fetch(path, {credentials: 'include', ...init, headers});
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok || data.success === false) {
      const error = new Error(data.error || data.message || `Request failed (${response.status})`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  async function signedLibraryFile(file, {signal = null} = {}) {
    if (!file?.id) throw new Error('That saved media item is missing its file ID.');
    const data = await api(`/api/files/${encodeURIComponent(file.id)}/signed`, {signal: signal || undefined});
    if (!data.url) throw new Error('Crump could not prepare that media file.');
    return data;
  }

  async function saveMedia(file, deliveryOptions = {}) {
    const deliver = window.CrumpMediaSave?.saveMedia;
    if (typeof deliver !== 'function') throw new Error('Private media delivery is still loading. Try again.');
    return deliver(file, deliveryOptions);
  }

  async function coverUrl(file, {force = false, libraryRun = null} = {}) {
    if (!file?.id) return '';
    const operation = libraryOperationContext();
    if (!operation.userId || (libraryRun && !activeLibraryOperation(libraryRun))) return '';
    const cached = state.coverUrls.get(file.id);
    if (!force && cached?.url && cached.expiresAt > Date.now()) return cached.url;
    state.coverUrls.delete(file.id);
    const previous = state.coverSignControllers.get(file.id);
    if (previous && !previous.signal.aborted) previous.abort();
    const controller = new AbortController();
    const abortFromRun = () => controller.abort();
    libraryRun?.controller?.signal?.addEventListener('abort', abortFromRun, {once: true});
    state.coverSignControllers.set(file.id, controller);
    try {
      const signed = await signedLibraryFile(file, {signal: controller.signal});
      if (
        controller.signal.aborted
        || state.coverSignControllers.get(file.id) !== controller
        || !libraryOperationIsCurrent(operation)
        || (libraryRun && !activeLibraryOperation(libraryRun))
      ) return '';
      const url = signed.url || '';
      if (!url) return '';
      const providedTtl = Number(signed.expiresIn);
      const ttlSeconds = Number.isFinite(providedTtl)
        ? Math.max(30, providedTtl)
        : COVER_URL_DEFAULT_TTL_SECONDS;
      const safetyMs = Math.min(COVER_URL_SAFETY_MS, ttlSeconds * 500);
      state.coverUrls.set(file.id, {
        url,
        expiresAt: Date.now() + (ttlSeconds * 1000) - safetyMs,
      });
      return url;
    } catch (_) {
      return '';
    } finally {
      libraryRun?.controller?.signal?.removeEventListener('abort', abortFromRun);
      if (state.coverSignControllers.get(file.id) === controller) {
        state.coverSignControllers.delete(file.id);
      }
    }
  }

  async function loadCoverImage(image, file, {force = false, libraryRun = null} = {}) {
    if (!image || !file?.id) return false;
    const url = await coverUrl(file, {force, libraryRun});
    if (!url || !image.isConnected || (libraryRun && !activeLibraryOperation(libraryRun))) return false;

    image.hidden = false;
    image.dataset.crump57CoverRetry = force ? '1' : '0';
    image.onerror = async () => {
      if (!image.isConnected) return;
      if (image.dataset.crump57CoverRetry === '1') {
        image.hidden = true;
        image.removeAttribute('src');
        return;
      }
      image.dataset.crump57CoverRetry = '1';
      state.coverUrls.delete(file.id);
      const replacement = libraryRun
        ? await coverUrl(file, {force: true, libraryRun})
        : await coverUrl(file, {force: true});
      if (!replacement || !image.isConnected || (libraryRun && !activeLibraryOperation(libraryRun))) {
        image.hidden = true;
        image.removeAttribute('src');
        return;
      }
      image.src = replacement;
    };
    image.src = url;
    return true;
  }

  function formatCount(value) {
    const number = Number(value || 0);
    if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}m`;
    if (number >= 1_000) return `${Math.round(number / 1_000)}k`;
    return String(number);
  }

  function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'});
  }

  function coverState(book) {
    if (book.frontCover?.id && book.backCover?.id) return 'complete';
    if (book.frontCover?.id) return 'front';
    return 'draft';
  }

  function bookMatches(book) {
    const needle = state.search.trim().toLowerCase();
    if (state.status !== 'all' && String(book.status || 'draft') !== state.status) return false;

    const covers = coverState(book);
    if (state.coverFilter === 'imported' && book.origin !== 'imported') return false;
    if (state.coverFilter === 'created' && book.origin === 'imported') return false;
    if (state.coverFilter === 'front' && covers === 'draft') return false;
    if (state.coverFilter === 'complete' && covers !== 'complete') return false;
    if (state.coverFilter === 'needs-cover' && covers !== 'draft') return false;

    if (!needle) return true;
    return [
      book.title, book.subtitle, book.authorName, book.projectName,
      book.sourceFile?.name, book.origin,
    ].some(value => String(value || '').toLowerCase().includes(needle));
  }

  function compareText(a, b) {
    return String(a || '').localeCompare(String(b || ''), undefined, {sensitivity: 'base'});
  }

  function sortBooks(books) {
    return [...books].sort((a, b) => {
      if (state.sort === 'title') return compareText(a.title, b.title);
      if (state.sort === 'author') return compareText(a.authorName, b.authorName) || compareText(a.title, b.title);
      if (state.sort === 'status') return compareText(a.status, b.status) || compareText(a.title, b.title);
      if (state.sort === 'words') return Number(b.wordCount || 0) - Number(a.wordCount || 0);
      if (state.sort === 'project') return compareText(a.projectName, b.projectName) || compareText(a.title, b.title);
      return new Date(b.updatedAt || 0).getTime() - new Date(a.updatedAt || 0).getTime();
    });
  }

  function coverMarkup(book, suffix = '') {
    const title = escapeHtml(book.title || 'Untitled manuscript');
    const author = escapeHtml(book.authorName || 'Ask Crump Library');
    const maturity = coverState(book);
    return `
      <div class="crump57-cover is-${maturity}" data-cover-book="${escapeHtml(book.id)}${escapeHtml(suffix)}">
        <div class="crump57-cover-placeholder">
          <span></span>
          <div><strong>${title}</strong><small>${author}</small></div>
        </div>
      </div>`;
  }

  async function hydrateCovers(container, books, suffix = '') {
    for (const book of books) {
      if (!book.frontCover?.id) continue;
      const selector = `[data-cover-book="${CSS.escape(String(book.id) + suffix)}"]`;
      const node = container.querySelector(selector);
      if (!node || node.querySelector('img')) continue;
      const image = document.createElement('img');
      image.alt = `${book.title || 'Book'} front cover`;
      image.loading = 'lazy';
      image.hidden = true;
      node.appendChild(image);
      if (!await loadCoverImage(image, book.frontCover)) image.remove();
    }
  }

  function layoutButtonMarkup(layout, label) {
    const disabled = layout === 'book' && !state.books.some(book => book.frontCover?.id);
    return `<button type="button" class="crump57-layout-button ${state.layout === layout ? 'is-active' : ''}" data-crump57-layout="${layout}" aria-pressed="${state.layout === layout ? 'true' : 'false'}" ${disabled ? 'disabled title="Add a front cover to unlock Book View"' : ''}>${label}</button>`;
  }

  function updateLayoutControls() {
    const controls = byId('crump57LayoutControls');
    if (!controls) return;
    if (state.layout === 'book' && !state.books.some(book => book.frontCover?.id)) state.layout = 'grid';
    controls.innerHTML = [
      layoutButtonMarkup('grid', 'Grid'),
      layoutButtonMarkup('list', 'List'),
      layoutButtonMarkup('book', 'Book'),
    ].join('');
    controls.querySelectorAll('[data-crump57-layout]').forEach(button => {
      button.addEventListener('click', () => {
        if (button.disabled) return;
        state.layout = button.dataset.crump57Layout || 'grid';
        savePreferences();
        renderBooks();
      });
    });
  }

  function bookCardMarkup(book) {
    const id = escapeHtml(book.id);
    const origin = book.origin === 'imported' ? 'Imported' : 'Created in Crump';
    const words = `${formatCount(book.wordCount)} words`;
    const sections = `${Number(book.sectionCount || 0)} section${Number(book.sectionCount || 0) === 1 ? '' : 's'}`;
    const maturity = coverState(book);
    const coverLabel = maturity === 'complete' ? 'Front + back covers' : maturity === 'front' ? 'Front cover added' : 'Cover not added';
    const project = book.projectName ? `<span class="crump57-project-chip" title="${escapeHtml(book.projectName)}">${escapeHtml(book.projectName)}</span>` : '';
    const updated = formatDate(book.updatedAt);
    const previewAction = book.frontCover?.id
      ? `<button type="button" data-crump57-preview="${id}">Preview book</button>`
      : '';
    const sourceAction = book.sourceFile?.id
      ? `<button type="button" data-crump57-original="${id}">Open original source</button>`
      : '';
    const workspaceAction = book.projectId
      ? `<button type="button" data-crump57-workspace="${id}">Edit manuscript</button>`
      : '';
    const downloadAction = `<button type="button" data-crump57-download="${id}">Download manuscript</button>`;

    return `
      <article class="crump57-book is-${maturity}" data-crump57-book="${id}">
        <div class="crump57-book-visual">
          ${coverMarkup(book)}
          <span class="crump57-spine" aria-hidden="true"></span>
        </div>
        <div class="crump57-book-body">
          <div class="crump57-book-kicker"><span>${escapeHtml(origin)}</span><span>${escapeHtml(book.status || 'draft')}</span></div>
          <h4 class="crump57-book-title" title="${escapeHtml(book.title)}">${escapeHtml(book.title || 'Untitled manuscript')}</h4>
          <span class="crump57-book-author">${escapeHtml(book.authorName || 'No author set')}</span>
          <div class="crump57-book-meta"><span>${words}</span><span>${sections}</span>${updated ? `<span>Updated ${escapeHtml(updated)}</span>` : ''}</div>
          <div class="crump57-book-footnote"><span>${escapeHtml(coverLabel)}</span>${project}</div>
          <div class="crump57-book-actions">
            <button type="button" class="crump53-button is-primary" data-crump57-open="${id}">Open</button>
            <button type="button" class="crump53-button" data-crump57-edit="${id}">Covers</button>
            <details class="crump57-more">
              <summary aria-label="More actions for ${escapeHtml(book.title || 'book')}">•••</summary>
              <div class="crump57-menu" role="menu">
                ${workspaceAction}
                ${downloadAction}
                <button type="button" data-crump57-details="${id}">Edit details</button>
                ${previewAction}
                ${sourceAction}
                <span class="crump57-menu-divider"></span>
                <button type="button" class="is-danger" data-crump57-trash="${id}">Move to Recently Deleted</button>
              </div>
            </details>
          </div>
        </div>
      </article>`;
  }

  function closeOtherMenus(active) {
    document.querySelectorAll('.crump57-more[open]').forEach(details => {
      if (details !== active) details.removeAttribute('open');
    });
  }

  const MANUSCRIPT_EXPORT_FORMATS = new Set(['docx', 'pdf', 'epub']);

  function captureManuscriptExportControls() {
    const controls = Array.from(document.querySelectorAll('[data-crump53-export], [data-crump53-run-output], [data-crump57-export-format]'));
    return controls.map(button => ({
      button,
      disabled: button.disabled,
      label: button.innerHTML,
      ariaBusy: button.getAttribute('aria-busy'),
    }));
  }

  function restoreManuscriptExportControls(controlState) {
    controlState.forEach(({button, disabled, label, ariaBusy}) => {
      button.disabled = disabled;
      button.innerHTML = label;
      if (ariaBusy == null) button.removeAttribute('aria-busy');
      else button.setAttribute('aria-busy', ariaBusy);
    });
  }

  function setLibraryExportStatus(message, isError = false, status = byId('crump57ExportStatus')) {
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('is-error', Boolean(isError));
  }

  async function exportCurrentManuscript(book, format, button = null, originRoot = null) {
    const normalized = String(format || '').toLowerCase().trim();
    const bookId = String(book?.id || '').trim();
    if (!MANUSCRIPT_EXPORT_FORMATS.has(normalized)) {
      show('Choose DOCX, PDF, or EPUB.', 'error');
      return false;
    }
    const operation = libraryOperationContext();
    const exportRoot = originRoot || button?.closest?.('.crump57-overlay') || null;
    const statusNode = exportRoot?.querySelector?.('#crump57ExportStatus') || null;
    const resourceIsCurrent = () => libraryOperationIsCurrent(operation)
      && Boolean(bookId)
      && (!exportRoot || exportRoot.isConnected);
    if (!operation.userId) {
      show('Sign in again before exporting this manuscript.', 'error');
      setLibraryExportStatus('Sign in again before exporting this manuscript.', true, statusNode);
      return false;
    }
    const run = manuscriptExportDelivery.begin('library', operation.userId);
    if (!run) {
      const message = 'Another manuscript export is already in progress.';
      setLibraryExportStatus(message, false, statusNode);
      show(message, 'info');
      return false;
    }
    const controlState = captureManuscriptExportControls();
    manuscriptExportDelivery.attachCleanup(run, () => restoreManuscriptExportControls(controlState));
    controlState.forEach(({button: control}) => {
      control.disabled = true;
      if (control === button) {
        control.textContent = `Building ${normalized.toUpperCase()}…`;
        control.setAttribute('aria-busy', 'true');
      }
    });

    try {
      setLibraryExportStatus(`Building ${normalized.toUpperCase()}…`, false, statusNode);
      const data = await api(`/api/manuscripts/${encodeURIComponent(bookId)}/export`, {
        method: 'POST',
        body: {format: normalized},
        signal: run.controller.signal,
      });
      if (!manuscriptExportDelivery.isCurrent(run, operation.userId) || !resourceIsCurrent()) return false;
      await manuscriptExportDelivery.deliver(data.file, run, resourceIsCurrent);
      if (!manuscriptExportDelivery.isCurrent(run, operation.userId) || !resourceIsCurrent()) return false;

      const message = `${normalized.toUpperCase()} ready · current manuscript exported and saved to Files.`;
      setLibraryExportStatus(message, false, statusNode);
      show(message, 'success');
      return true;
    } catch (error) {
      if (error?.name === 'AbortError' || !resourceIsCurrent()) return false;
      console.warn('Ask Crump manuscript export failed:', error);
      const message = error?.message || 'Crump could not export that manuscript.';
      setLibraryExportStatus(message, true, statusNode);
      show(message, 'error');
      return false;
    } finally {
      manuscriptExportDelivery.finish(run);
    }
  }

  function bindManuscriptExportButtons(root, book, closeAfter = false) {
    root?.querySelectorAll?.('[data-crump57-export-format]').forEach(button => {
      button.addEventListener('click', async () => {
        const format = button.dataset.crump57ExportFormat || '';
        const exported = await exportCurrentManuscript(book, format, button, root);
        const details = button.closest('details');
        if (exported && details) {
          const summary = details.querySelector('summary');
          details.removeAttribute('open');
          summary?.focus({preventScroll: true});
        } else if (!exported && button.isConnected && !button.disabled) {
          button.focus({preventScroll: true});
        }
        if (exported && closeAfter && state.modal === root) closeModal({overlay: root});
      });
    });
  }

  function openBookDownload(book, returnFocus = null) {
    const overlay = mountModal(`
      <div class="crump57-overlay crump57-download-overlay" role="presentation">
        <section class="crump57-sheet crump57-download-sheet" role="dialog" aria-modal="true" aria-label="Download ${escapeHtml(book.title || 'manuscript')}">
          <header class="crump57-sheet-head">
            <div>
              <div class="crump53-kicker">CURRENT MANUSCRIPT</div>
              <h3>Download ${escapeHtml(book.title || 'manuscript')}</h3>
              <p>Export the version that exists in Crump right now.</p>
            </div>
            <button type="button" class="crump57-close" aria-label="Close download options">×</button>
          </header>
          <div class="crump57-sheet-body">
            <div class="crump57-download-note">
              <strong>Your current version stays yours.</strong>
              <span>This export includes the manuscript as it exists in Crump now, including saved edits. If you originally uploaded a file, the untouched source remains separately available through “Open original source.”</span>
            </div>
            <div class="crump57-download-options">
              <button type="button" class="crump57-download-option" data-crump57-export-format="docx">
                <strong>Word</strong><span>DOCX</span><small>Best for continuing to edit.</small>
              </button>
              <button type="button" class="crump57-download-option" data-crump57-export-format="pdf">
                <strong>Print PDF</strong><span>PDF</span><small>KDP-aware formatted manuscript.</small>
              </button>
              <button type="button" class="crump57-download-option" data-crump57-export-format="epub">
                <strong>eBook</strong><span>EPUB</span><small>Portable e-reader format.</small>
              </button>
            </div>
            <p id="crump57ExportStatus" class="crump53-status" role="status" aria-live="polite"></p>
          </div>
        </section>
      </div>`, {returnFocus});
    bindManuscriptExportButtons(overlay, book, true);
  }

  function readerParagraphs(content) {
    const value = String(content || '').replace(/\r\n?/g, '\n').trim();
    if (!value) return '<p class="crump57-reader-empty-copy">This section does not have readable text yet.</p>';
    return value
      .split(/\n{2,}/)
      .map(paragraph => `<p>${escapeHtml(paragraph).replace(/\n/g, '<br>')}</p>`)
      .join('');
  }

  async function openBookReader(book) {
    const bookId = String(book?.id || '');
    const overlay = mountModal(`
      <div class="crump57-overlay crump57-reader-overlay" role="presentation">
        <section class="crump57-sheet crump57-reader-sheet" role="dialog" aria-modal="true" aria-label="Read ${escapeHtml(book.title || 'manuscript')}">
          <header class="crump57-sheet-head crump57-reader-head">
            <div>
              <div class="crump53-kicker">READING</div>
              <h3>${escapeHtml(book.title || 'Untitled manuscript')}</h3>
              <p>${escapeHtml(book.authorName || 'Ask Crump Library')}</p>
            </div>
            <div class="crump57-reader-head-actions">
              <details class="crump57-reader-download">
                <summary class="crump53-button">Download</summary>
                <div class="crump57-reader-download-menu">
                  <button type="button" data-crump57-export-format="docx">Word (.docx)</button>
                  <button type="button" data-crump57-export-format="pdf">Print PDF</button>
                  <button type="button" data-crump57-export-format="epub">eBook (.epub)</button>
                </div>
              </details>
              <button type="button" class="crump57-close" aria-label="Close reader">×</button>
            </div>
          </header>
          <div class="crump57-reader-loading" id="crump57ReaderLoading">
            <strong>Opening book…</strong>
            <span>Crump is preparing the manuscript for reading.</span>
          </div>
        </section>
      </div>`, {resourceType: 'active-book', resourceId: bookId});
    const operation = beginLibraryOperation('reader', {
      overlay,
      resourceType: 'active-book',
      resourceId: bookId,
    });
    if (!operation) {
      closeModal({overlay, restoreFocus: false});
      return false;
    }
    bindManuscriptExportButtons(overlay, book, false);

    try {
      const data = await api(`/api/manuscripts/${encodeURIComponent(bookId)}`, {
        signal: operation.controller.signal,
      });
      if (!activeLibraryOperation(operation)) return false;
      const manuscript = data.manuscript || {};
      const sections = Array.isArray(data.sections) ? data.sections : [];
      const sheet = overlay.querySelector('.crump57-reader-sheet');
      const loading = overlay.querySelector('#crump57ReaderLoading');
      if (!sheet || !loading || !activeLibraryOperation(operation)) return false;

      if (!sections.length) {
        loading.innerHTML = `
          <strong>No readable sections yet.</strong>
          <span>This manuscript exists in your Library, but it does not have any sections to read yet.</span>`;
        return true;
      }

      loading.remove();

      const reader = document.createElement('div');
      reader.className = 'crump57-reader';
      reader.innerHTML = `
        <aside class="crump57-reader-nav" aria-label="Book sections">
          <div class="crump57-reader-nav-head">
            <small>CONTENTS</small>
            <strong>${sections.length} section${sections.length === 1 ? '' : 's'}</strong>
          </div>
          <div class="crump57-reader-section-list">
            ${sections.map((section, index) => `
              <button type="button" data-crump57-reader-index="${index}">
                <small>${String(index + 1).padStart(2, '0')}</small>
                <span>${escapeHtml(section.title || `Section ${index + 1}`)}</span>
              </button>`).join('')}
          </div>
        </aside>
        <main class="crump57-reader-main">
          <div class="crump57-reader-mobile-nav">
            <label>
              <span>Section</span>
              <select id="crump57ReaderSelect">
                ${sections.map((section, index) => `
                  <option value="${index}">${escapeHtml(section.title || `Section ${index + 1}`)}</option>`).join('')}
              </select>
            </label>
          </div>
          <article class="crump57-reader-page" id="crump57ReaderPage" tabindex="-1">
            <div class="crump57-reader-page-meta" id="crump57ReaderMeta"></div>
            <h2 id="crump57ReaderTitle"></h2>
            <div class="crump57-reader-copy" id="crump57ReaderCopy"></div>
          </article>
          <footer class="crump57-reader-controls">
            <button type="button" class="crump53-button" id="crump57ReaderPrev">← Previous</button>
            <span id="crump57ReaderPosition"></span>
            <button type="button" class="crump53-button" id="crump57ReaderNext">Next →</button>
          </footer>
        </main>`;
      sheet.appendChild(reader);

      const page = overlay.querySelector('#crump57ReaderPage');
      const title = overlay.querySelector('#crump57ReaderTitle');
      const copy = overlay.querySelector('#crump57ReaderCopy');
      const meta = overlay.querySelector('#crump57ReaderMeta');
      const position = overlay.querySelector('#crump57ReaderPosition');
      const previous = overlay.querySelector('#crump57ReaderPrev');
      const next = overlay.querySelector('#crump57ReaderNext');
      const select = overlay.querySelector('#crump57ReaderSelect');
      const navButtons = Array.from(reader.querySelectorAll('[data-crump57-reader-index]'));
      let activeIndex = 0;

      const showSection = (index, focusPage = false) => {
        const bounded = Math.max(0, Math.min(sections.length - 1, Number(index) || 0));
        const section = sections[bounded] || {};
        activeIndex = bounded;
        title.textContent = section.title || `Section ${bounded + 1}`;
        copy.innerHTML = readerParagraphs(section.content);
        meta.textContent = [String(section.section_type || '').replace(/_/g, ' '), section.word_count ? `${Number(section.word_count).toLocaleString()} words` : '']
          .filter(Boolean)
          .join(' · ');
        position.textContent = `${bounded + 1} of ${sections.length}`;
        previous.disabled = bounded === 0;
        next.disabled = bounded === sections.length - 1;
        if (select) select.value = String(bounded);
        navButtons.forEach((button, buttonIndex) => {
          button.classList.toggle('is-active', buttonIndex === bounded);
          button.setAttribute('aria-current', buttonIndex === bounded ? 'true' : 'false');
        });
        if (focusPage) {
          const reducedMotion = Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
          page.scrollIntoView({behavior: reducedMotion ? 'auto' : 'smooth', block: 'start'});
          page.focus({preventScroll: true});
        } else {
          page.scrollTop = 0;
        }
      };

      navButtons.forEach(button => {
        button.addEventListener('click', () => showSection(Number(button.dataset.crump57ReaderIndex), true));
      });
      select?.addEventListener('change', () => showSection(Number(select.value), true));
      previous?.addEventListener('click', () => showSection(activeIndex - 1, true));
      next?.addEventListener('click', () => showSection(activeIndex + 1, true));

      const subtitle = String(manuscript.subtitle || book.subtitle || '').trim();
      const head = overlay.querySelector('.crump57-reader-head p');
      if (head) {
        head.textContent = [manuscript.author_name || manuscript.authorName || book.authorName, subtitle].filter(Boolean).join(' · ') || 'Ask Crump Library';
      }
      showSection(0, false);
      return true;
    } catch (error) {
      if (error?.name === 'AbortError' || !activeLibraryOperation(operation)) return false;
      const loading = overlay.querySelector('#crump57ReaderLoading');
      if (loading) {
        loading.innerHTML = `
          <strong>Book could not open.</strong>
          <span>${escapeHtml(error?.message || 'Try again in a moment.')}</span>`;
      } else {
        show(error?.message || 'Crump could not open that book for reading.', 'error');
      }
      return false;
    } finally {
      finishLibraryOperation(operation);
    }
  }

  async function openBookWorkspace(book) {
    const bookId = String(book?.id || '');
    const originOverlay = state.modal;
    const operation = beginLibraryOperation('open-workspace', {
      overlay: originOverlay,
      modalSensitive: true,
      resourceType: 'active-book',
      resourceId: bookId,
      resourceCurrent: () => originOverlay
        ? originOverlay.dataset.crump57ResourceId === bookId
        : state.books.some(item => String(item?.id || '') === bookId),
    });
    const opener = window.CrumpProduct53?.openManuscript;
    if (!operation) return false;
    if (typeof opener !== 'function' && activeLibraryOperation(operation)) {
      show('The manuscript workspace is not ready yet. Refresh Ask Crump and try again.', 'error');
      finishLibraryOperation(operation);
      return false;
    }
    try {
      assertLibraryOperationCurrent(operation);
      const opened = await opener({
        projectId: book.projectId,
        manuscriptId: bookId,
        title: book.title,
        signal: operation.controller.signal,
        shouldProceed: () => activeLibraryOperation(operation),
      });
      if (!activeLibraryOperation(operation)) return false;
      if (opened === false) {
        show('Crump could not open ' + (book.title || 'that manuscript') + ' for editing.', 'error');
        if (originOverlay) closeModal({overlay: originOverlay});
        return false;
      }
      if (originOverlay) closeModal({overlay: originOverlay});
      return true;
    } catch (error) {
      if (error?.name === 'AbortError' || !activeLibraryOperation(operation)) return false;
      show(error?.message || 'Crump could not open that manuscript for editing.', 'error');
      return false;
    } finally {
      finishLibraryOperation(operation);
    }
  }

  async function openOriginalSource(book) {
    const operation = libraryOperationContext();
    const bookId = String(book?.id || '').trim();
    const sourceFileId = String(book?.sourceFile?.id || '').trim();
    const openFile = window.CrumpFileTools?.open;
    if (!operation.userId || !bookId || !sourceFileId || typeof openFile !== 'function') return false;

    const controller = new AbortController();
    libraryFileDeliveryControllers.add(controller);
    const shouldProceed = () => {
      if (controller.signal.aborted || !libraryOperationIsCurrent(operation)) return false;
      const currentBook = state.books.find(item => String(item?.id || '') === bookId);
      return String(currentBook?.sourceFile?.id || '') === sourceFileId;
    };
    try {
      if (!shouldProceed()) return false;
      const opened = await Promise.resolve(openFile(
        {...book.sourceFile, id: sourceFileId, url: ''},
        false,
        {signal: controller.signal, shouldProceed},
      ));
      return shouldProceed() && opened === true;
    } catch (error) {
      if (error?.name === 'AbortError' || !shouldProceed()) return false;
      show(error?.message || 'Crump could not open that original source.', 'error');
      return false;
    } finally {
      libraryFileDeliveryControllers.delete(controller);
    }
  }

  function bindBookActions(grid) {
    const map = new Map(state.books.map(book => [String(book.id), book]));
    grid.querySelectorAll('[data-crump57-open]').forEach(button => {
      button.addEventListener('click', async () => {
        const book = map.get(String(button.dataset.crump57Open));
        if (!book) return;
        const originalLabel = button.textContent;
        button.disabled = true;
        button.textContent = 'Opening…';
        try {
          await openBookReader(book);
        } finally {
          button.disabled = false;
          button.textContent = originalLabel || 'Open';
        }
      });
    });
    grid.querySelectorAll('[data-crump57-download]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Download));
        if (!book) return;
        const returnFocus = button.closest('details')?.querySelector('summary')
          || button.closest('[data-crump57-book]')?.querySelector('[data-crump57-open]')
          || button;
        closeOtherMenus(null);
        openBookDownload(book, returnFocus);
      });
    });
    grid.querySelectorAll('[data-crump57-workspace]').forEach(button => {
      button.addEventListener('click', async () => {
        const book = map.get(String(button.dataset.crump57Workspace));
        if (!book) return;
        closeOtherMenus(null);
        try {
          await openBookWorkspace(book);
        } catch (error) {
          console.error('Ask Crump manuscript workspace open failed:', error);
          show(error?.message || 'Crump could not open that manuscript for editing.', 'error');
        }
      });
    });
    grid.querySelectorAll('[data-crump57-edit], [data-crump57-details]').forEach(button => {
      button.addEventListener('click', () => {
        const id = button.dataset.crump57Edit || button.dataset.crump57Details;
        const book = map.get(String(id));
        if (book) openBookEditor(book);
      });
    });
    grid.querySelectorAll('[data-crump57-preview]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Preview));
        if (book) void openBookPreview(book);
      });
    });
    grid.querySelectorAll('[data-crump57-original]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Original));
        if (!book?.sourceFile) return;
        void openOriginalSource(book);
      });
    });
    grid.querySelectorAll('[data-crump57-trash]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Trash));
        if (book) openTrashModal(book);
      });
    });
    grid.querySelectorAll('.crump57-more').forEach(details => {
      details.addEventListener('toggle', () => { if (details.open) closeOtherMenus(details); });
    });
  }

  function renderBooks() {
    const grid = byId('crump57Bookshelf');
    if (!grid) return;

    updateLayoutControls();
    const books = sortBooks(state.books.filter(bookMatches));
    grid.className = `crump57-bookshelf is-layout-${state.layout}`;
    grid.removeAttribute('aria-busy');
    if (!books.length) {
      const hasAny = state.books.length > 0;
      if (!hasAny) {
        // First-run: the empty shelf teaches the two ways in and offers
        // both, wired to the existing header actions.
        grid.innerHTML = `
          <div class="crump57-first-run">
            <div class="crump53-kicker">LIBRARY</div>
            <strong>Your shelf is ready.</strong>
            <p>Write something new with Crump, or bring a book you started somewhere else.</p>
            <div class="crump57-first-run-actions">
              <button type="button" class="crump53-button is-primary" data-crump57-first-run-new>New in Crump</button>
              <button type="button" class="crump53-button" data-crump57-first-run-import>Import a manuscript</button>
            </div>
          </div>`;
        grid.querySelector('[data-crump57-first-run-new]')?.addEventListener('click', () => byId('crump57New')?.click());
        grid.querySelector('[data-crump57-first-run-import]')?.addEventListener('click', () => byId('crump57Import')?.click());
        return;
      }
      grid.innerHTML = `
        <div class="crump57-empty">
          <strong>No books match that view.</strong>
          Try another search, status, or cover filter.
        </div>`;
      return;
    }

    grid.innerHTML = books.map(bookCardMarkup).join('');
    bindBookActions(grid);
    void hydrateCovers(grid, books);
  }

  async function refreshDeletedBooks(parentOperation = null, {replaceExisting = true} = {}) {
    const refresh = beginLibraryRefresh('deleted-books', parentOperation, {replaceExisting});
    if (!refresh) return false;
    try {
      const data = await api('/api/library/books/deleted', {signal: refresh.controller.signal});
      if (!libraryRefreshIsCurrent(refresh)) return false;
      state.deletedBooks = Array.isArray(data.books) ? data.books : [];
    } catch (error) {
      if (error?.name === 'AbortError' || !libraryRefreshIsCurrent(refresh)) return false;
      state.deletedBooks = [];
    } finally {
      finishLibraryRefresh(refresh);
    }
    const button = byId('crump57Deleted');
    if (button) {
      const count = state.deletedBooks.length;
      button.textContent = count ? `Recently Deleted · ${count}` : 'Recently Deleted';
    }
    return true;
  }

  async function refreshBooks({
    parentOperation = null,
    showSkeleton = true,
    includeDeleted = true,
    replaceExisting = true,
  } = {}) {
    const refresh = beginLibraryRefresh('books', parentOperation, {replaceExisting});
    if (!refresh) return false;
    const grid = byId('crump57Bookshelf');
    if (grid && showSkeleton) {
      // Skeleton covers keep the bookshelf's shape while it loads, in the
      // same calm gold language as the rest of the surface.
      grid.className = 'crump57-bookshelf is-loading';
      grid.setAttribute('aria-busy', 'true');
      grid.innerHTML = '<div class="crump57-skeleton" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></div>';
    }
    try {
      const data = await api('/api/library/books', {signal: refresh.controller.signal});
      if (!libraryRefreshIsCurrent(refresh)) return false;
      state.books = Array.isArray(data.books) ? data.books : [];
      if (includeDeleted) {
        await refreshDeletedBooks(parentOperation, {replaceExisting});
        if (!libraryRefreshIsCurrent(refresh)) return false;
      }
      renderBooks();
      return true;
    } catch (error) {
      if (error?.name === 'AbortError' || !libraryRefreshIsCurrent(refresh)) return false;
      if (grid) {
        grid.className = 'crump57-bookshelf';
        grid.removeAttribute('aria-busy');
        grid.innerHTML = `<div class="crump57-empty"><strong>Library could not load.</strong>${escapeHtml(error.message || 'Try again in a moment.')}</div>`;
      }
      return false;
    } finally {
      finishLibraryRefresh(refresh);
    }
  }

  async function refreshProjects(parentOperation = null) {
    const refresh = beginLibraryRefresh('projects', parentOperation);
    if (!refresh) return false;
    try {
      const data = await api('/api/projects', {signal: refresh.controller.signal});
      if (!libraryRefreshIsCurrent(refresh)) return false;
      state.projects = Array.isArray(data.projects) ? data.projects : [];
      state.projectLimit = Number(data.limit ?? 0);
    } catch (error) {
      if (error?.name === 'AbortError' || !libraryRefreshIsCurrent(refresh)) return false;
      state.projects = [];
      state.projectLimit = -1;
    } finally {
      finishLibraryRefresh(refresh);
    }
    return true;
  }

  function projectOptions(selected = '') {
    const limitReached = state.projectLimit >= 0 && state.projects.length >= state.projectLimit;
    const createLabel = limitReached
      ? 'Project limit reached — choose an existing Project'
      : 'Create a dedicated Project for this book';
    return [
      `<option value="" ${limitReached ? 'disabled' : ''}>${escapeHtml(createLabel)}</option>`,
      ...state.projects.map(project => `<option value="${escapeHtml(project.id)}" ${String(project.id) === String(selected) ? 'selected' : ''}>Add to: ${escapeHtml(project.name)}</option>`),
    ].join('');
  }

  function closeModal({restoreFocus = true, overlay = state.modal} = {}) {
    if (!overlay) return false;
    const isCurrentModal = state.modal === overlay;
    abortLibraryOverlayOperations(overlay);
    overlay.querySelectorAll?.('[data-crump57-object-url]').forEach(image => {
      const url = image.dataset.crump57ObjectUrl || '';
      if (url.startsWith('blob:')) URL.revokeObjectURL(url);
      delete image.dataset.crump57ObjectUrl;
    });
    overlay.remove();
    if (!isCurrentModal) return false;
    const returnFocus = state.modalReturnFocus;
    state.modal = null;
    state.modalReturnFocus = null;
    libraryModalSequence += 1;
    const closedSequence = libraryModalSequence;
    if (restoreFocus && returnFocus?.isConnected) {
      window.requestAnimationFrame(() => {
        if (libraryModalSequence !== closedSequence || state.modal) return;
        if (returnFocus.isConnected) returnFocus.focus({preventScroll: true});
      });
    }
    return true;
  }

  function resetLibraryAuthMemory() {
    clearLibraryMutationReconciliation();
    libraryAuthSequence += 1;
    abortAllLibraryOperations();
    abortAllLibraryRefreshes();
    manuscriptExportDelivery.abort();
    window.CrumpMediaSave?.abort?.();
    libraryFileDeliveryControllers.forEach(controller => controller.abort());
    libraryFileDeliveryControllers.clear();
    libraryStateUserId = '';
    state.books = [];
    state.deletedBooks = [];
    state.projects = [];
    state.projectLimit = -1;
    state.search = '';
    state.status = 'all';
    state.coverSignControllers.forEach(controller => controller.abort());
    state.coverSignControllers.clear();
    state.coverUrls.clear();
    closeModal({restoreFocus: false, overlay: state.modal});
    const grid = byId('crump57Bookshelf');
    if (grid) {
      grid.className = 'crump57-bookshelf';
      grid.removeAttribute('aria-busy');
      grid.replaceChildren();
    }
    const search = byId('crump57Search');
    if (search) search.value = '';
    const status = byId('crump57Filter');
    if (status) status.value = 'all';
    const deleted = byId('crump57Deleted');
    if (deleted) deleted.textContent = 'Recently Deleted';
  }

  function bindModalClose(overlay) {
    const close = () => closeModal({overlay});
    overlay.querySelector('.crump57-close')?.addEventListener('click', close);
    overlay.querySelectorAll('[data-crump57-cancel]').forEach(button => button.addEventListener('click', close));
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
    return close;
  }

  function mountModal(markup, {
    returnFocus = null,
    operation = null,
    resourceType = '',
    resourceId = '',
  } = {}) {
    const opener = returnFocus || (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    if (state.modal) closeModal({restoreFocus: false, overlay: state.modal});
    const wrapper = document.createElement('div');
    wrapper.innerHTML = markup;
    const overlay = wrapper.firstElementChild;
    libraryModalSequence += 1;
    const identity = Object.freeze({sequence: libraryModalSequence});
    libraryModalIdentity.set(overlay, identity);
    overlay.dataset.crump57ModalSequence = String(identity.sequence);
    overlay.dataset.crump57ResourceType = String(resourceType || '');
    overlay.dataset.crump57ResourceId = String(resourceId || '');
    document.body.appendChild(overlay);
    state.modal = overlay;
    state.modalReturnFocus = opener?.isConnected ? opener : null;
    if (operation) attachLibraryOperationOverlay(operation, overlay, {resourceType, resourceId});
    bindModalClose(overlay);
    window.requestAnimationFrame(() => {
      if (
        state.modal !== overlay
        || !overlay.isConnected
        || libraryModalIdentity.get(overlay) !== identity
      ) return;
      const focusTarget = overlay.classList.contains('crump57-download-overlay')
        ? overlay.querySelector('[data-crump57-export-format]')
        : overlay.querySelector('.crump57-close, button, input, select, textarea, [tabindex]');
      focusTarget?.focus({preventScroll: true});
    });
    return overlay;
  }

  function bindCoverPreview(input, image, box) {
    input?.addEventListener('change', () => {
      const previousUrl = image.dataset.crump57ObjectUrl || '';
      if (previousUrl.startsWith('blob:')) URL.revokeObjectURL(previousUrl);
      delete image.dataset.crump57ObjectUrl;
      const file = input.files?.[0];
      if (!file) {
        image.removeAttribute('src');
        box.classList.remove('has-image');
        return;
      }
      const url = URL.createObjectURL(file);
      image.dataset.crump57ObjectUrl = url;
      image.src = url;
      box.classList.add('has-image');
      const release = () => {
        if (image.dataset.crump57ObjectUrl !== url) return;
        URL.revokeObjectURL(url);
        delete image.dataset.crump57ObjectUrl;
      };
      image.onload = release;
      image.onerror = release;
    });
  }

  function libraryUploadOptions(operation) {
    return {
      signal: operation?.controller?.signal,
      shouldProceed: () => activeLibraryOperation(operation),
    };
  }

  async function uploadLibraryFile(file, operation) {
    assertLibraryOperationCurrent(operation);
    if (!window.CrumpFileTools?.upload) throw new Error('Ask Crump file upload tools are still loading.');
    const uploaded = await window.CrumpFileTools.upload(file, libraryUploadOptions(operation));
    assertLibraryOperationCurrent(operation);
    return uploaded;
  }

  async function uploadOptional(file, label, operation) {
    if (!file) return null;
    if (label === 'cover' && !String(file.type || '').startsWith('image/')) throw new Error('Cover files must be images.');
    return uploadLibraryFile(file, operation);
  }

  function importModalMarkup() {
    return `
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet" role="dialog" aria-modal="true" aria-label="Import manuscript">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">ASK CRUMP LIBRARY</div><h3>Import a manuscript</h3><p>Bring an existing book into Crump without rewriting the original.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <form class="crump57-sheet-body" id="crump57ImportForm">
            <div class="crump57-form-grid">
              <label class="crump57-field is-wide">
                <span>Manuscript file</span>
                <div class="crump57-upload">
                  <div class="crump57-upload-copy"><strong id="crump57SourceName">Choose DOCX, PDF, EPUB, TXT, or Markdown</strong><small>The original file stays in your private Ask Crump storage.</small></div>
                  <input id="crump57SourceFile" type="file" accept="${SOURCE_ACCEPT}" required>
                </div>
              </label>
              <label class="crump57-field"><span>Title <small>Optional</small></span><input id="crump57Title" maxlength="180" placeholder="Crump can infer it from the file"></label>
              <label class="crump57-field"><span>Author</span><input id="crump57Author" maxlength="160" placeholder="Author name"></label>
              <label class="crump57-field is-wide"><span>Subtitle <small>Optional</small></span><input id="crump57Subtitle" maxlength="240" placeholder="Subtitle"></label>
              <label class="crump57-field is-wide"><span>Organization</span><select id="crump57Project">${projectOptions()}</select><small>By default, Crump creates a dedicated Project so the book's files, canon, and future chats stay together.</small></label>
              <label class="crump57-field">
                <span>Front cover <small>Optional</small></span>
                <div class="crump57-upload crump57-cover-pick" id="crump57FrontBox">
                  <img id="crump57FrontPreview" alt="">
                  <div class="crump57-upload-copy"><strong>Add front cover</strong><small>JPG, PNG, WebP, HEIC</small></div>
                  <input id="crump57FrontCover" type="file" accept="${COVER_ACCEPT}">
                </div>
              </label>
              <label class="crump57-field">
                <span>Back cover <small>Optional</small></span>
                <div class="crump57-upload crump57-cover-pick" id="crump57BackBox">
                  <img id="crump57BackPreview" alt="">
                  <div class="crump57-upload-copy"><strong>Add back cover</strong><small>JPG, PNG, WebP, HEIC</small></div>
                  <input id="crump57BackCover" type="file" accept="${COVER_ACCEPT}">
                </div>
              </label>
            </div>
            <div class="crump57-import-status" id="crump57ImportStatus" aria-live="polite"></div>
            <div class="crump57-sheet-actions">
              <button type="button" class="crump53-button" data-crump57-cancel>Cancel</button>
              <button type="submit" class="crump53-button is-primary" id="crump57ImportSubmit">Import to Library</button>
            </div>
          </form>
        </section>
      </div>`;
  }

  async function openImportModal() {
    const openerOperation = beginLibraryOperation('open-import', {modalSensitive: true});
    if (!openerOperation) return false;
    try {
      const projectsReady = await refreshProjects(openerOperation);
      if (!projectsReady || !activeLibraryOperation(openerOperation)) return false;
      const overlay = mountModal(importModalMarkup(), {
        operation: openerOperation,
        resourceType: 'import',
        resourceId: 'new',
      });
      if (!activeLibraryOperation(openerOperation)) return false;
      const source = overlay.querySelector('#crump57SourceFile');
      const front = overlay.querySelector('#crump57FrontCover');
      const back = overlay.querySelector('#crump57BackCover');
      const status = overlay.querySelector('#crump57ImportStatus');
      const submit = overlay.querySelector('#crump57ImportSubmit');

      source?.addEventListener('change', () => {
        const sourceName = overlay.querySelector('#crump57SourceName');
        if (sourceName) sourceName.textContent = source.files?.[0]?.name || 'Choose DOCX, PDF, EPUB, TXT, or Markdown';
      });
      bindCoverPreview(front, overlay.querySelector('#crump57FrontPreview'), overlay.querySelector('#crump57FrontBox'));
      bindCoverPreview(back, overlay.querySelector('#crump57BackPreview'), overlay.querySelector('#crump57BackBox'));

      overlay.querySelector('#crump57ImportForm')?.addEventListener('submit', async event => {
        event.preventDefault();
        const sourceFile = source?.files?.[0] || null;
        const frontFile = front?.files?.[0] || null;
        const backFile = back?.files?.[0] || null;
        const formValues = {
          title: overlay.querySelector('#crump57Title')?.value || '',
          subtitle: overlay.querySelector('#crump57Subtitle')?.value || '',
          authorName: overlay.querySelector('#crump57Author')?.value || '',
          projectId: overlay.querySelector('#crump57Project')?.value || '',
        };
        if (!sourceFile) {
          status.textContent = 'Choose a manuscript file first.';
          status.classList.add('is-error');
          return;
        }
        const operation = beginLibraryOperation('import', {
          overlay,
          resourceType: 'import',
          resourceId: 'new',
        });
        if (!operation) return;
        let mutationStarted = false;
        submit.disabled = true;
        status.classList.remove('is-error');
        try {
          status.textContent = 'Uploading original manuscript…';
          const sourceAsset = await uploadLibraryFile(sourceFile, operation);
          assertLibraryOperationCurrent(operation);
          status.textContent = 'Uploading covers…';
          const frontAsset = await uploadOptional(frontFile, 'cover', operation);
          const backAsset = await uploadOptional(backFile, 'cover', operation);
          assertLibraryOperationCurrent(operation);
          status.textContent = 'Reading chapters and building your Library entry…';
          mutationStarted = true;
          const data = await api('/api/library/books/import', {
            method: 'POST',
            signal: operation.controller.signal,
            body: {
              sourceFileId: sourceAsset.id,
              frontCoverFileId: frontAsset?.id || '',
              backCoverFileId: backAsset?.id || '',
              ...formValues,
            },
          });
          if (!activeLibraryOperation(operation)) {
            void refreshAfterPossibleMutation(operation);
            return;
          }

          finishLibraryOperation(operation);
          closeModal({overlay});
          state.coverUrls.clear();
          const continuation = beginLibraryOperation('import-committed', {modalSensitive: true});
          if (!continuation) return;
          try {
            await refreshBooks({parentOperation: continuation, showSkeleton: false});
            if (!activeLibraryOperation(continuation)) return;
            show(`${data.book?.title || 'Manuscript'} added to your Library.`, 'success');
          } finally {
            finishLibraryOperation(continuation);
          }
          if (data.book?.projectId && data.book?.id) await openBookWorkspace(data.book);
        } catch (error) {
          if (mutationStarted && !activeLibraryOperation(operation)) {
            void refreshAfterPossibleMutation(operation);
            return;
          }
          if (error?.name === 'AbortError' || !activeLibraryOperation(operation)) return;
          status.textContent = error.message || 'The manuscript could not be imported.';
          status.classList.add('is-error');
        } finally {
          if (activeLibraryOperation(operation)) submit.disabled = false;
          finishLibraryOperation(operation);
        }
      });
      return true;
    } finally {
      finishLibraryOperation(openerOperation);
    }
  }

  function bookEditorMarkup(book) {
    return `
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet" role="dialog" aria-modal="true" aria-label="Book details">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">BOOK DETAILS</div><h3>${escapeHtml(book.title)}</h3><p>Update shelf details or replace either cover.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <form class="crump57-sheet-body" id="crump57BookForm">
            <div class="crump57-form-grid">
              <label class="crump57-field"><span>Title</span><input id="crump57EditTitle" maxlength="180" value="${escapeHtml(book.title || '')}" required></label>
              <label class="crump57-field"><span>Author</span><input id="crump57EditAuthor" maxlength="160" value="${escapeHtml(book.authorName || '')}"></label>
              <label class="crump57-field is-wide"><span>Subtitle</span><input id="crump57EditSubtitle" maxlength="240" value="${escapeHtml(book.subtitle || '')}"></label>
              <label class="crump57-field is-wide"><span>Status</span><select id="crump57EditStatus">
                <option value="draft" ${book.status === 'draft' ? 'selected' : ''}>Draft</option>
                <option value="revising" ${book.status === 'revising' ? 'selected' : ''}>Revising</option>
                <option value="final" ${book.status === 'final' ? 'selected' : ''}>Final</option>
              </select></label>
              <label class="crump57-field">
                <span>Front cover</span>
                <div class="crump57-upload crump57-cover-pick" id="crump57EditFrontBox">
                  <img id="crump57EditFrontPreview" alt="">
                  <div class="crump57-upload-copy"><strong>${book.frontCover ? 'Replace front cover' : 'Add front cover'}</strong><small>Leave untouched to keep the current image</small></div>
                  <input id="crump57EditFront" type="file" accept="${COVER_ACCEPT}">
                </div>
              </label>
              <label class="crump57-field">
                <span>Back cover</span>
                <div class="crump57-upload crump57-cover-pick" id="crump57EditBackBox">
                  <img id="crump57EditBackPreview" alt="">
                  <div class="crump57-upload-copy"><strong>${book.backCover ? 'Replace back cover' : 'Add back cover'}</strong><small>Leave untouched to keep the current image</small></div>
                  <input id="crump57EditBack" type="file" accept="${COVER_ACCEPT}">
                </div>
              </label>
            </div>
            <div class="crump57-import-status" id="crump57EditStatusText" aria-live="polite"></div>
            <div class="crump57-sheet-actions">
              <button type="button" class="crump53-button" data-crump57-cancel>Cancel</button>
              <button type="submit" class="crump53-button is-primary" id="crump57BookSubmit">Save book</button>
            </div>
          </form>
        </section>
      </div>`;
  }

  async function setExistingCover(book, side, overlay, operation) {
    const file = side === 'front' ? book.frontCover : book.backCover;
    const image = overlay?.querySelector(side === 'front' ? '#crump57EditFrontPreview' : '#crump57EditBackPreview');
    const box = overlay?.querySelector(side === 'front' ? '#crump57EditFrontBox' : '#crump57EditBackBox');
    if (!file?.id || !image || !box) return;
    if (await loadCoverImage(image, file, {libraryRun: operation}) && activeLibraryOperation(operation)) {
      box.classList.add('has-image');
    }
  }

  function openBookEditor(book) {
    const bookId = String(book?.id || '');
    const overlay = mountModal(bookEditorMarkup(book), {
      resourceType: 'active-book',
      resourceId: bookId,
    });
    const front = overlay.querySelector('#crump57EditFront');
    const back = overlay.querySelector('#crump57EditBack');
    bindCoverPreview(front, overlay.querySelector('#crump57EditFrontPreview'), overlay.querySelector('#crump57EditFrontBox'));
    bindCoverPreview(back, overlay.querySelector('#crump57EditBackPreview'), overlay.querySelector('#crump57EditBackBox'));
    const coverOperation = beginLibraryOperation('editor-covers', {
      overlay,
      resourceType: 'active-book',
      resourceId: bookId,
    });
    if (coverOperation) {
      void Promise.all([
        setExistingCover(book, 'front', overlay, coverOperation),
        setExistingCover(book, 'back', overlay, coverOperation),
      ]).finally(() => finishLibraryOperation(coverOperation));
    }

    overlay.querySelector('#crump57BookForm')?.addEventListener('submit', async event => {
      event.preventDefault();
      const status = overlay.querySelector('#crump57EditStatusText');
      const submit = overlay.querySelector('#crump57BookSubmit');
      const frontFile = front?.files?.[0] || null;
      const backFile = back?.files?.[0] || null;
      const changes = {
        title: overlay.querySelector('#crump57EditTitle')?.value || '',
        subtitle: overlay.querySelector('#crump57EditSubtitle')?.value || '',
        authorName: overlay.querySelector('#crump57EditAuthor')?.value || '',
        status: overlay.querySelector('#crump57EditStatus')?.value || 'draft',
      };
      const operation = beginLibraryOperation('editor-save', {
        overlay,
        resourceType: 'active-book',
        resourceId: bookId,
      });
      if (!operation) return;
      let mutationStarted = false;
      submit.disabled = true;
      status.classList.remove('is-error');
      try {
        if (frontFile) {
          status.textContent = 'Uploading new front cover…';
          changes.frontCoverFileId = (await uploadLibraryFile(frontFile, operation)).id;
        }
        if (backFile) {
          status.textContent = 'Uploading new back cover…';
          changes.backCoverFileId = (await uploadLibraryFile(backFile, operation)).id;
        }
        assertLibraryOperationCurrent(operation);
        status.textContent = 'Saving Library details…';
        mutationStarted = true;
        await api(`/api/library/books/${encodeURIComponent(bookId)}`, {
          method: 'PATCH',
          signal: operation.controller.signal,
          body: changes,
        });
        if (!activeLibraryOperation(operation)) {
          void refreshAfterPossibleMutation(operation);
          return;
        }
        finishLibraryOperation(operation);
        closeModal({overlay});
        state.coverUrls.clear();
        const continuation = beginLibraryOperation('editor-committed', {modalSensitive: true});
        if (!continuation) return;
        try {
          await refreshBooks({parentOperation: continuation, showSkeleton: false});
          if (activeLibraryOperation(continuation)) show('Book updated.', 'success');
        } finally {
          finishLibraryOperation(continuation);
        }
      } catch (error) {
        if (mutationStarted && !activeLibraryOperation(operation)) {
          void refreshAfterPossibleMutation(operation);
          return;
        }
        if (error?.name === 'AbortError' || !activeLibraryOperation(operation)) return;
        status.textContent = error.message || 'The book could not be updated.';
        status.classList.add('is-error');
      } finally {
        if (activeLibraryOperation(operation)) submit.disabled = false;
        finishLibraryOperation(operation);
      }
    });
  }

  async function openBookPreview(book) {
    const bookId = String(book?.id || '');
    const overlay = mountModal(`
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet crump57-preview-sheet" role="dialog" aria-modal="true" aria-label="Book preview">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">BOOK PREVIEW</div><h3>${escapeHtml(book.title)}</h3><p>${escapeHtml(book.authorName || 'No author set')}</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <div class="crump57-sheet-body">
            <div class="crump57-preview-stage">
              <figure class="crump57-preview-cover"><div id="crump57PreviewFront" class="crump57-preview-image"><span>Front cover</span></div><figcaption>Front</figcaption></figure>
              <div class="crump57-preview-spine" aria-hidden="true"><span>${escapeHtml(book.title || '')}</span></div>
              <figure class="crump57-preview-cover"><div id="crump57PreviewBack" class="crump57-preview-image"><span>${book.backCover?.id ? 'Back cover' : 'Add a back cover to complete the book view'}</span></div><figcaption>Back</figcaption></figure>
            </div>
            <div class="crump57-preview-meta"><span>${formatCount(book.wordCount)} words</span><span>${Number(book.sectionCount || 0)} sections</span><span>${escapeHtml(book.status || 'draft')}</span></div>
            <div class="crump57-sheet-actions"><button type="button" class="crump53-button" data-crump57-cancel>Close</button><button type="button" class="crump53-button is-primary" id="crump57PreviewOpen">Open manuscript</button></div>
          </div>
        </section>
      </div>`, {resourceType: 'active-book', resourceId: bookId});
    const operation = beginLibraryOperation('preview', {
      overlay,
      resourceType: 'active-book',
      resourceId: bookId,
    });
    if (!operation) {
      closeModal({overlay, restoreFocus: false});
      return false;
    }

    const frontNode = overlay.querySelector('#crump57PreviewFront');
    const backNode = overlay.querySelector('#crump57PreviewBack');
    overlay.querySelector('#crump57PreviewOpen')?.addEventListener('click', () => {
      if (state.modal !== overlay || !overlay.isConnected) return;
      void openBookWorkspace(book);
    });
    const coverLoads = [];
    if (book.frontCover?.id) {
      const image = document.createElement('img');
      image.alt = `${book.title || 'Book'} front cover`;
      image.hidden = true;
      frontNode.replaceChildren(image);
      coverLoads.push(loadCoverImage(image, book.frontCover, {libraryRun: operation}).then(loaded => {
        if (!loaded && activeLibraryOperation(operation)) image.remove();
      }));
    }
    if (book.backCover?.id) {
      const image = document.createElement('img');
      image.alt = `${book.title || 'Book'} back cover`;
      image.hidden = true;
      backNode.replaceChildren(image);
      coverLoads.push(loadCoverImage(image, book.backCover, {libraryRun: operation}).then(loaded => {
        if (!loaded && activeLibraryOperation(operation)) image.remove();
      }));
    }
    try {
      await Promise.all(coverLoads);
      return activeLibraryOperation(operation);
    } finally {
      finishLibraryOperation(operation);
    }
  }

  function openTrashModal(book) {
    const bookId = String(book?.id || '');
    const sourceChoice = book.sourceFile?.id ? `
      <label class="crump57-check-row">
        <input type="checkbox" id="crump57DeleteSource">
        <span><strong>Also remove the original imported source from Files</strong><small>If another manuscript uses the same source, Crump will keep it.</small></span>
      </label>` : '';
    const overlay = mountModal(`
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet crump57-confirm-sheet" role="dialog" aria-modal="true" aria-label="Move book to Recently Deleted">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">RECENTLY DELETED</div><h3>Move “${escapeHtml(book.title)}”?</h3><p>The book leaves your active Library but can be restored later.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <div class="crump57-sheet-body">
            <div class="crump57-confirm-note"><strong>Protected by default</strong><span>Your Project and cover files stay intact. Chapters and manuscript history stay recoverable until permanent deletion.</span></div>
            ${sourceChoice}
            <div class="crump57-import-status" id="crump57TrashStatus" aria-live="polite"></div>
            <div class="crump57-sheet-actions"><button type="button" class="crump53-button" data-crump57-cancel>Cancel</button><button type="button" class="crump53-button is-danger" id="crump57TrashConfirm">Move to Recently Deleted</button></div>
          </div>
        </section>
      </div>`, {resourceType: 'active-book', resourceId: bookId});
    overlay.querySelector('#crump57TrashConfirm')?.addEventListener('click', async () => {
      const button = overlay.querySelector('#crump57TrashConfirm');
      const status = overlay.querySelector('#crump57TrashStatus');
      const deleteSource = Boolean(overlay.querySelector('#crump57DeleteSource')?.checked);
      const operation = beginLibraryOperation('trash', {
        overlay,
        resourceType: 'active-book',
        resourceId: bookId,
      });
      if (!operation) return;
      let mutationStarted = false;
      button.disabled = true;
      try {
        mutationStarted = true;
        const data = await api(`/api/library/books/${encodeURIComponent(bookId)}/trash`, {
          method: 'POST',
          signal: operation.controller.signal,
          body: {deleteSource},
        });
        if (!activeLibraryOperation(operation)) {
          void refreshAfterPossibleMutation(operation);
          return;
        }
        finishLibraryOperation(operation);
        closeModal({overlay});
        const continuation = beginLibraryOperation('trash-committed', {modalSensitive: true});
        if (!continuation) return;
        try {
          await refreshBooks({parentOperation: continuation, showSkeleton: false});
          if (activeLibraryOperation(continuation)) {
            show(data.sourceFileKept ? 'Book moved to Recently Deleted. Shared source file was kept.' : 'Book moved to Recently Deleted.', 'success');
          }
        } finally {
          finishLibraryOperation(continuation);
        }
      } catch (error) {
        if (mutationStarted && !activeLibraryOperation(operation)) {
          void refreshAfterPossibleMutation(operation);
          return;
        }
        if (error?.name === 'AbortError' || !activeLibraryOperation(operation)) return;
        status.textContent = error.message || 'The book could not be moved.';
        status.classList.add('is-error');
      } finally {
        if (activeLibraryOperation(operation)) button.disabled = false;
        finishLibraryOperation(operation);
      }
    });
  }

  function renderDeletedBooks(container) {
    if (!state.deletedBooks.length) {
      container.innerHTML = '<div class="crump57-empty"><strong>Recently Deleted is empty.</strong>Books you remove from the shelf will stay recoverable here until you permanently delete them.</div>';
      return;
    }
    container.innerHTML = state.deletedBooks.map(book => `
      <article class="crump57-deleted-book" data-deleted-book="${escapeHtml(book.id)}">
        <div class="crump57-deleted-cover">${coverMarkup(book, '-deleted')}</div>
        <div class="crump57-deleted-copy">
          <span class="crump53-kicker">REMOVED ${escapeHtml(formatDate(book.trashedAt) || '')}</span>
          <strong>${escapeHtml(book.title || 'Untitled manuscript')}</strong>
          <small>${escapeHtml(book.authorName || 'No author set')} · ${formatCount(book.wordCount)} words · ${Number(book.sectionCount || 0)} sections</small>
          <div class="crump57-deleted-actions"><button type="button" class="crump53-button is-primary" data-crump57-restore="${escapeHtml(book.id)}">Restore</button><button type="button" class="crump53-button is-danger" data-crump57-permanent="${escapeHtml(book.id)}">Delete permanently</button></div>
        </div>
      </article>`).join('');

    const map = new Map(state.deletedBooks.map(book => [String(book.id), book]));
    container.querySelectorAll('[data-crump57-restore]').forEach(button => {
      button.addEventListener('click', async () => {
        const book = map.get(String(button.dataset.crump57Restore));
        if (!book) return;
        const bookId = String(book.id || '');
        const overlay = container.closest('.crump57-overlay');
        const operation = beginLibraryOperation('restore', {
          overlay,
          resourceType: 'deleted-books',
          resourceId: 'collection',
          resourceCurrent: () => button.isConnected
            && button.dataset.crump57Restore === bookId
            && container.isConnected,
        });
        if (!operation) return;
        let mutationStarted = false;
        button.disabled = true;
        try {
          mutationStarted = true;
          await api(`/api/library/books/${encodeURIComponent(bookId)}/restore`, {
            method: 'POST',
            signal: operation.controller.signal,
            body: {},
          });
          if (!activeLibraryOperation(operation)) {
            void refreshAfterPossibleMutation(operation);
            return;
          }
          await refreshBooks({parentOperation: operation, showSkeleton: false});
          if (!activeLibraryOperation(operation)) return;
          show(`${book.title || 'Book'} restored.`, 'success');
          renderDeletedBooks(container);
        } catch (error) {
          if (mutationStarted && !activeLibraryOperation(operation)) {
            void refreshAfterPossibleMutation(operation);
            return;
          }
          if (error?.name === 'AbortError' || !activeLibraryOperation(operation)) return;
          show(error.message || 'The book could not be restored.', 'error');
        } finally {
          if (activeLibraryOperation(operation)) button.disabled = false;
          finishLibraryOperation(operation);
        }
      });
    });
    container.querySelectorAll('[data-crump57-permanent]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Permanent));
        if (book) openPermanentDeleteModal(book);
      });
    });
    void hydrateCovers(container, state.deletedBooks, '-deleted');
  }

  async function openRecentlyDeleted() {
    const openerOperation = beginLibraryOperation('open-deleted', {modalSensitive: true});
    if (!openerOperation) return false;
    try {
      const refreshed = await refreshDeletedBooks(openerOperation);
      if (!refreshed || !activeLibraryOperation(openerOperation)) return false;
      const overlay = mountModal(`
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet" role="dialog" aria-modal="true" aria-label="Recently Deleted books">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">LIBRARY SAFETY</div><h3>Recently Deleted</h3><p>Restore a manuscript or permanently remove it when you are certain.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <div class="crump57-sheet-body"><div id="crump57DeletedList" class="crump57-deleted-list"></div></div>
        </section>
      </div>`, {
        operation: openerOperation,
        resourceType: 'deleted-books',
        resourceId: 'collection',
      });
      if (!activeLibraryOperation(openerOperation)) return false;
      renderDeletedBooks(overlay.querySelector('#crump57DeletedList'));
      return true;
    } finally {
      finishLibraryOperation(openerOperation);
    }
  }

  function openPermanentDeleteModal(book) {
    const bookId = String(book?.id || '');
    const overlay = mountModal(`
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet crump57-confirm-sheet" role="dialog" aria-modal="true" aria-label="Permanently delete book">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">PERMANENT DELETE</div><h3>Delete “${escapeHtml(book.title)}” forever?</h3><p>This cannot be undone.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <div class="crump57-sheet-body">
            <div class="crump57-danger-note"><strong>Permanent means permanent.</strong><span>The manuscript, chapters, and manuscript-run history will be deleted. The Project and covers stay unless you remove them separately. If you chose to remove the original source when trashing the book, that source will also be permanently removed.</span></div>
            <label class="crump57-field"><span>Type DELETE to confirm</span><input id="crump57PermanentPhrase" autocomplete="off" placeholder="DELETE"></label>
            <div class="crump57-import-status" id="crump57PermanentStatus" aria-live="polite"></div>
            <div class="crump57-sheet-actions"><button type="button" class="crump53-button" data-crump57-cancel>Cancel</button><button type="button" class="crump53-button is-danger" id="crump57PermanentConfirm" disabled>Delete permanently</button></div>
          </div>
        </section>
      </div>`, {resourceType: 'deleted-book', resourceId: bookId});
    const phrase = overlay.querySelector('#crump57PermanentPhrase');
    const confirm = overlay.querySelector('#crump57PermanentConfirm');
    phrase?.addEventListener('input', () => { confirm.disabled = phrase.value.trim() !== 'DELETE'; });
    confirm?.addEventListener('click', async () => {
      const confirmation = phrase?.value?.trim() || '';
      if (confirmation !== 'DELETE') return;
      const operation = beginLibraryOperation('permanent-delete', {
        overlay,
        resourceType: 'deleted-book',
        resourceId: bookId,
      });
      if (!operation) return;
      let mutationStarted = false;
      confirm.disabled = true;
      const status = overlay.querySelector('#crump57PermanentStatus');
      try {
        mutationStarted = true;
        const data = await api(`/api/library/books/${encodeURIComponent(bookId)}`, {
          method: 'DELETE',
          signal: operation.controller.signal,
        });
        if (!activeLibraryOperation(operation)) {
          void refreshAfterPossibleMutation(operation);
          return;
        }
        finishLibraryOperation(operation);
        closeModal({overlay});
        const continuation = beginLibraryOperation('permanent-delete-committed', {modalSensitive: true});
        if (!continuation) return;
        try {
          await refreshBooks({parentOperation: continuation, showSkeleton: false});
          if (activeLibraryOperation(continuation)) {
            show(data.sourceCleanupPending
              ? `${book.title || 'Book'} deleted. Original source cleanup is still pending.`
              : `${book.title || 'Book'} permanently deleted.`,
            data.sourceCleanupPending ? 'warning' : 'success');
          }
        } finally {
          finishLibraryOperation(continuation);
        }
      } catch (error) {
        if (mutationStarted && !activeLibraryOperation(operation)) {
          void refreshAfterPossibleMutation(operation);
          return;
        }
        if (error?.name === 'AbortError' || !activeLibraryOperation(operation)) return;
        status.textContent = error.message || 'The book could not be permanently deleted.';
        status.classList.add('is-error');
      } finally {
        if (activeLibraryOperation(operation)) confirm.disabled = false;
        finishLibraryOperation(operation);
      }
    });
  }

  function installLibraryPanel() {
    const manuscriptList = byId('crump53ManuscriptList');
    if (!manuscriptList) return false;
    const manuscriptPanel = manuscriptList.closest('[data-crump53-panel="manuscripts"]');
    const libraryPanel = document.querySelector('[data-crump53-panel="library"]');
    const originalCard = manuscriptList.closest('.crump53-card');
    if (!manuscriptPanel || !libraryPanel || !originalCard) return false;

    const shell = libraryPanel.closest('.crump53-sheet');
    if (shell) shell.classList.add('crump57-library-shell');

    const heading = originalCard.querySelector('h3');
    if (heading) heading.textContent = 'Current Project manuscript';
    const intro = heading?.nextElementSibling;
    if (intro?.tagName === 'P') intro.textContent = 'Open or continue the manuscript attached to the active Project. Your full bookshelf stays above.';

    if (!byId('crump57LibraryCard')) {
      const card = document.createElement('div');
      card.id = 'crump57LibraryCard';
      card.className = 'crump53-card crump57-library-card';
      card.innerHTML = `
        <div class="crump57-library-head">
          <div><div class="crump53-kicker">BOOKSHELF</div><h3>Your Library</h3><p>A calm home for books created with Crump and manuscripts you bring with you.</p></div>
          <div class="crump57-library-actions">
            <button type="button" class="crump53-button" id="crump57Deleted">Recently Deleted</button>
            <button type="button" class="crump53-button" id="crump57Import">Import manuscript</button>
            <button type="button" class="crump53-button is-primary" id="crump57New">New in Crump</button>
          </div>
        </div>
        <div class="crump57-library-toolbar">
          <label class="crump57-search"><span class="sr-only">Search Library</span><input type="search" id="crump57Search" placeholder="Search title, author, Project…" aria-label="Search Library"></label>
          <select id="crump57Filter" aria-label="Filter books by status">
            <option value="all">All statuses</option>
            <option value="draft">Draft</option>
            <option value="revising">Revising</option>
            <option value="final">Final</option>
          </select>
          <select id="crump57CoverFilter" aria-label="Filter books by source or cover">
            <option value="all">All books</option>
            <option value="imported">Imported</option>
            <option value="created">Created in Crump</option>
            <option value="front">Has front cover</option>
            <option value="complete">Front + back covers</option>
            <option value="needs-cover">Needs cover</option>
          </select>
          <select id="crump57Sort" aria-label="Sort Library">
            <option value="updated">Recently updated</option>
            <option value="title">Title</option>
            <option value="author">Author</option>
            <option value="status">Status</option>
            <option value="words">Word count</option>
            <option value="project">Project</option>
          </select>
          <div id="crump57LayoutControls" class="crump57-layout-controls" aria-label="Library layout"></div>
        </div>
        <div id="crump57Bookshelf" class="crump57-bookshelf"></div>`;
      libraryPanel.insertBefore(card, libraryPanel.firstElementChild);

      const coverFilter = byId('crump57CoverFilter');
      const sort = byId('crump57Sort');
      if (coverFilter) coverFilter.value = state.coverFilter;
      if (sort) sort.value = state.sort;

      byId('crump57Import')?.addEventListener('click', () => void openImportModal());
      byId('crump57New')?.addEventListener('click', () => {
        const openProduct = window.CrumpProduct53?.open;
        if (typeof openProduct !== 'function') {
          show('The manuscript workspace is still loading. Try again in a moment.', 'error');
          return;
        }
        openProduct('manuscripts');
        window.requestAnimationFrame(() => byId('crump53NewManuscript')?.click());
      });
      byId('crump57Deleted')?.addEventListener('click', () => void openRecentlyDeleted());
      byId('crump57Search')?.addEventListener('input', event => { state.search = event.target.value || ''; renderBooks(); });
      byId('crump57Filter')?.addEventListener('change', event => { state.status = event.target.value || 'all'; renderBooks(); });
      coverFilter?.addEventListener('change', event => {
        state.coverFilter = COVER_FILTERS.has(event.target.value) ? event.target.value : 'all';
        savePreferences();
        renderBooks();
      });
      sort?.addEventListener('change', event => {
        state.sort = SORTS.has(event.target.value) ? event.target.value : 'updated';
        savePreferences();
        renderBooks();
      });
    }

    state.installed = true;
    return true;
  }

  function installWhenReady() {
    if (installLibraryPanel()) return;
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (installLibraryPanel() || attempts > 100) clearInterval(timer);
    }, 100);
  }

  window.CrumpLibrary57 = Object.freeze({
    refresh: refreshBooks,
    importManuscript: openImportModal,
    recentlyDeleted: openRecentlyDeleted,
    saveMedia,
  });

  if (window.CrumpAuthBoundary?.register) {
    window.CrumpAuthBoundary.register('library57', resetLibraryAuthMemory);
  } else {
    window.addEventListener('crump:authentication-required', resetLibraryAuthMemory);
  }
  window.addEventListener('crump:authenticated-ready', () => {
    libraryOperationContext();
    if (!state.installed) installWhenReady();
  });
  document.addEventListener('click', event => {
    if (!event.target.closest?.('.crump57-more')) closeOtherMenus(null);
  }, true);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installWhenReady, {once: true});
  else installWhenReady();
})();
