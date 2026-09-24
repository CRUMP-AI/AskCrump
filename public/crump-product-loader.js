(() => {
  'use strict';

  if (window.__crumpProductLoaderLoaded) return;
  window.__crumpProductLoaderLoaded = true;

  const STYLE_URL = '/crump-product-5.3.css?v=5.9.76-reference-fidelity-focused-3';
  const SCRIPT_URL = '/crump-product-5.3.js?v=5.9.76-reference-fidelity-focused-3';
  const ACTIVE_PROJECT_KEY = 'askcrump.activeProject53';
  const VIDEO_JOB_KEY = 'askcrump.videoJob53';
  const VIDEO_REQUEST_KEY = 'askcrump.videoRequest53';
  const VIDEO_STORAGE_VERSION = 1;
  const VIDEO_REQUEST_TTL_MS = 30 * 60 * 1000;
  const VIDEO_JOB_ID_PATTERN = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  const VIDEO_REFERENCE_DRAFT_KEY = 'askcrump.videoReferenceDraft53';
  const DESTINATIONS = new Set(['projects', 'manuscripts', 'video', 'library']);
  const DESTINATION_LABELS = Object.freeze({
    projects: 'Projects',
    manuscripts: 'Manuscripts',
    video: 'Video Studio',
    library: 'Library',
  });
  let loadPromise = null;
  let facade = null;
  let loadedApi = null;
  let authenticatedUserId = '';

  const VIDEO_REFERENCE_ROLE_LABELS = Object.freeze({
    subject: 'Subject / product',
    mascot: 'Mascot / character',
    logo: 'Logo / wordmark',
    style: 'Style / palette',
  });

  function videoReferenceTransportCopy(mode, count) {
    if (mode === 'initial-frame') {
      return 'Provider transport: Input image 1 was sent as the starting frame. That records how the request was sent, not verified frame-by-frame fidelity.';
    }
    if (mode === 'appearance-guidance') {
      return `Provider transport: ${count} ordered input image${count === 1 ? ' was' : 's were'} sent as best-effort appearance guidance, not as pixel-locked frames or layouts.`;
    }
    return 'Provider transport: reference inputs were recorded, but their transport mode is unavailable. This receipt does not claim visual fidelity.';
  }

  function privateReferenceLabel(fileId) {
    const normalized = String(fileId || '').trim();
    return normalized ? `Private file ending ${normalized.slice(-8)}` : 'Private file';
  }

  function renderVideoReferenceReceipt(root, job) {
    if (!root?.querySelector || job?.status !== 'ready') return false;
    root.querySelector('[data-video-reference-receipt]')?.remove();
    const references = (Array.isArray(job.referencePlan) ? job.referencePlan : [])
      .filter(reference => reference && VIDEO_REFERENCE_ROLE_LABELS[reference.role])
      .slice(0, 3);
    if (!references.length) return false;

    const receipt = document.createElement('section');
    receipt.className = 'crump53-video-reference-receipt';
    receipt.dataset.videoReferenceReceipt = 'true';
    receipt.dataset.referenceMode = String(job.referenceMode || 'unavailable');
    receipt.dataset.referenceVerification = 'not-performed';
    receipt.setAttribute('aria-label', 'Video reference delivery receipt');

    const kicker = document.createElement('div');
    kicker.className = 'crump53-kicker';
    kicker.textContent = 'REFERENCE DELIVERY RECEIPT';
    receipt.appendChild(kicker);

    const heading = document.createElement('h3');
    heading.textContent = 'What was sent with this video';
    receipt.appendChild(heading);

    const transport = document.createElement('p');
    transport.dataset.videoReferenceTransport = 'true';
    transport.textContent = videoReferenceTransportCopy(job.referenceMode, references.length);
    receipt.appendChild(transport);

    const ordered = document.createElement('ol');
    ordered.className = 'crump53-video-reference-receipt-list';
    references.forEach((reference, index) => {
      const item = document.createElement('li');
      item.dataset.referenceInput = String(index + 1);
      const input = document.createElement('strong');
      input.textContent = `Input image ${index + 1}`;
      const role = document.createElement('span');
      role.textContent = VIDEO_REFERENCE_ROLE_LABELS[reference.role];
      const file = document.createElement('small');
      file.textContent = privateReferenceLabel(reference.fileId);
      item.append(input, role, file);
      ordered.appendChild(item);
    });
    receipt.appendChild(ordered);

    const verification = document.createElement('div');
    verification.className = 'crump53-video-reference-check';
    const verificationTitle = document.createElement('strong');
    verificationTitle.textContent = 'Fidelity check: not automatically performed';
    const verificationCopy = document.createElement('p');
    verificationCopy.textContent = 'Exact logos, readable text, and subject identity were not automatically verified in the rendered frames.';
    verification.append(verificationTitle, verificationCopy);
    receipt.appendChild(verification);

    const nextAction = document.createElement('div');
    nextAction.className = 'crump53-video-reference-check';
    const nextTitle = document.createElement('strong');
    nextTitle.textContent = 'Before you publish';
    const nextCopy = document.createElement('p');
    nextCopy.textContent = 'Pause on representative frames and compare them side by side with each source image. If exact branding or wording matters, add the approved logo or text as a deterministic overlay in your video editor.';
    const compare = document.createElement('button');
    compare.type = 'button';
    compare.className = 'crump53-button';
    compare.dataset.videoReferenceCompare = 'true';
    compare.textContent = 'Open Files to compare';
    compare.addEventListener('click', () => {
      const existingAction = root.querySelector('#crump53OpenLibraryFromVideo');
      if (existingAction) existingAction.click();
      else void window.CrumpProduct53?.openFiles?.();
    });
    nextAction.append(nextTitle, nextCopy, compare);
    receipt.appendChild(nextAction);

    const continuation = root.querySelector('.crump53-video-continuation');
    root.insertBefore(receipt, continuation || null);
    return true;
  }

  window.CrumpVideoReferenceReceipt = Object.freeze({render: renderVideoReferenceReceipt});

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
    const loading = !realApi() || !styleReady();
    if (loading) setBusy(destination, true);
    if (loading && announce) {
      window.showToast?.(`Opening ${DESTINATION_LABELS[destination] || 'workspace'}…`, 'info');
    }
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
      .finally(() => {
        if (loading) setBusy(destination, false);
      });
  }

  function cachedProjectTarget() {
    const userId = currentLoaderUserId();
    const key = userId ? `${ACTIVE_PROJECT_KEY}:${encodeURIComponent(userId)}` : '';
    const id = String(key ? stored(key) : '').trim();
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
  window.CrumpProductLoader = Object.freeze({
    load,
    authenticatedUserId: () => authenticatedUserId,
  });

  function currentLoaderUserId() {
    const currentUserId = String(window.currentUser?.id || '').trim();
    return currentUserId && currentUserId === authenticatedUserId ? currentUserId : '';
  }

  function videoReferenceDraftKey(userId = currentLoaderUserId()) {
    const normalized = String(userId || '').trim();
    return normalized ? `${VIDEO_REFERENCE_DRAFT_KEY}:${encodeURIComponent(normalized)}` : '';
  }

  function videoAccountStorageKey(baseKey, userId = currentLoaderUserId()) {
    const normalized = String(userId || '').trim();
    return normalized ? `${baseKey}:${encodeURIComponent(normalized)}` : '';
  }

  function hasStoredVideoRecord(baseKey, kind) {
    const userId = currentLoaderUserId();
    const accountKey = videoAccountStorageKey(baseKey, userId);
    if (!userId || !accountKey) return false;
    let sourceKey = accountKey;
    try {
      let rawValue = localStorage.getItem(accountKey) || '';
      if (!rawValue) {
        const legacyRawValue = localStorage.getItem(baseKey) || '';
        if (legacyRawValue) {
          if (kind === 'job' && VIDEO_JOB_ID_PATTERN.test(legacyRawValue.trim())) {
            return true;
          }
          sourceKey = baseKey;
          const legacyValue = JSON.parse(legacyRawValue);
          if (String(legacyValue?.userId || '') === userId) rawValue = legacyRawValue;
          else localStorage.removeItem(baseKey);
        }
      }
      if (!rawValue) return false;
      const value = JSON.parse(rawValue);
      if (value?.version !== VIDEO_STORAGE_VERSION || String(value?.userId || '') !== userId) {
        localStorage.removeItem(sourceKey);
        return false;
      }
      let sanitized = null;
      if (kind === 'job') {
        const jobId = String(value.jobId || '').trim().slice(0, 200);
        if (jobId) {
          sanitized = {
            version: VIDEO_STORAGE_VERSION,
            userId,
            jobId,
            updatedAt: Number(value.updatedAt || Date.now()),
          };
        }
      } else {
        const idempotencyKey = String(value.idempotencyKey || '').trim().slice(0, 200);
        const requestDigest = String(value.requestDigest || '').trim().slice(0, 128);
        const createdAt = Number(value.createdAt || 0);
        if (
          idempotencyKey
          && /^(?:[a-f0-9]{64}|fallback-[a-f0-9]{16})$/.test(requestDigest)
          && createdAt
          && Date.now() - createdAt <= VIDEO_REQUEST_TTL_MS
        ) {
          sanitized = {
            version: VIDEO_STORAGE_VERSION,
            userId,
            idempotencyKey,
            requestDigest,
            createdAt,
          };
        }
      }
      if (!sanitized) {
        localStorage.removeItem(sourceKey);
        return false;
      }
      localStorage.setItem(accountKey, JSON.stringify(sanitized));
      if (sourceKey !== accountKey) localStorage.removeItem(sourceKey);
      return true;
    } catch (_) {
      try { localStorage.removeItem(sourceKey); } catch (_) { /* storage is optional */ }
      return false;
    }
  }

  function hasStoredVideoReferenceDraft() {
    const userId = currentLoaderUserId();
    const accountKey = videoReferenceDraftKey(userId);
    if (!userId || !accountKey) return false;
    if (stored(accountKey)) return true;
    try {
      const legacy = JSON.parse(stored(VIDEO_REFERENCE_DRAFT_KEY) || 'null');
      return String(legacy?.userId || '') === userId;
    } catch (_) {
      return false;
    }
  }

  function shouldResumeAfterAuthentication() {
    const hasVideoJob = hasStoredVideoRecord(VIDEO_JOB_KEY, 'job');
    const hasVideoRequest = hasStoredVideoRecord(VIDEO_REQUEST_KEY, 'request');
    if (
      hasVideoJob
      || hasVideoRequest
      || hasStoredVideoReferenceDraft()
      || cachedProjectTarget()
      // A legacy unscoped value may only wake the full owner resolver. It is
      // never exposed as the facade's active target.
      || stored(ACTIVE_PROJECT_KEY)
    ) return true;
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

  window.addEventListener('crump:authenticated-ready', () => {
    authenticatedUserId = String(window.currentUser?.id || '').trim();
    loadForPersistedWork();
  });
  window.addEventListener('crump:authentication-required', () => {
    authenticatedUserId = '';
  });
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
