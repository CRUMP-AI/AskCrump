/*
 * Ask Crump activity center
 *
 * A deliberately small, content-free view of durable video, Autonomous Crump,
 * and creative work already represented in the signed-in account. The module
 * does not create jobs, change billing, or introduce a second job runner.
 */
(() => {
  'use strict';

  if (window.__crumpActivityCenterLoaded) return;
  window.__crumpActivityCenterLoaded = true;

  const VERSION = 1;
  const STORAGE_PREFIX = 'askcrump.activityCenter.v1';
  const VIDEO_JOB_PREFIX = 'askcrump.videoJob53';
  const VIDEO_REQUEST_PREFIX = 'askcrump.videoRequest53';
  const ACTIVE_REFRESH_MS = 30 * 1000;
  const IDLE_REFRESH_MS = 5 * 60 * 1000;
  const LOCAL_RECONCILE_MS = 5 * 1000;
  const REQUEST_TIMEOUT_MS = 12 * 1000;
  const MAX_FAILURE_BACKOFF_MS = 10 * 60 * 1000;
  const MAX_FAILURE_BACKOFF_STEP = 4;
  const FINISHED_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  const ACTIVE_TTL_MS = 3 * 24 * 60 * 60 * 1000;
  const MAX_STORED_ITEMS = 18;
  const MAX_VISIBLE_ITEMS = 12;
  const NETWORK_FEEDS = Object.freeze(['video', 'code']);
  const KINDS = new Set(['video', 'image', 'document', 'presentation', 'code']);
  const STATUSES = new Set(['queued', 'running', 'ready', 'failed']);
  const CODE_STATUSES = new Set([
    'queued', 'provisioning', 'running', 'awaiting_approval', 'verifying',
    'completed', 'failed', 'cancelled',
  ]);
  const ACTIVE_STATUSES = new Set(['queued', 'running']);
  const OPAQUE_ID = /^[A-Za-z0-9._:-]{1,220}$/;
  const NETWORK_ABORT_REASONS = new WeakMap();

  const state = {
    userId: '',
    items: new Map(),
    opened: false,
    lastNetworkAt: 0,
    feedLastNetworkAt: {video: 0, code: 0},
    networkInFlight: null,
    networkController: null,
    loopTimer: null,
    networkUnavailable: false,
    networkIssue: '',
    networkFailureCount: 0,
    feedFailureCount: {video: 0, code: 0},
    feedIssue: {video: '', code: ''},
    trigger: null,
    panel: null,
    list: null,
    summary: null,
    refreshButton: null,
    headerStatusObserver: null,
    lastFocus: null,
    lastRenderSignature: '',
    lastCountSignature: '',
  };

  const now = () => Date.now();
  const byId = id => document.getElementById(id);

  function currentUserId() {
    const current = String(window.currentUser?.id || '').trim();
    if (!current) return '';
    const ownerResolver = window.CrumpProductLoader?.authenticatedUserId;
    if (typeof ownerResolver !== 'function') return current;
    return String(ownerResolver() || '').trim() === current ? current : '';
  }

  function storageKey(userId = state.userId) {
    const owner = String(userId || '').trim();
    return owner ? `${STORAGE_PREFIX}:${encodeURIComponent(owner)}` : '';
  }

  function accountVideoKey(prefix, userId = state.userId) {
    const owner = String(userId || '').trim();
    return owner ? `${prefix}:${encodeURIComponent(owner)}` : '';
  }

  function safeStorage() {
    try { return window.localStorage; }
    catch (_) { return null; }
  }

  function safeOpaque(value) {
    const normalized = String(value || '').trim().slice(0, 220);
    return OPAQUE_ID.test(normalized) ? normalized : '';
  }

  function safeTime(value, fallback = now()) {
    const numeric = typeof value === 'number' ? value : Date.parse(String(value || ''));
    if (!Number.isFinite(numeric) || numeric <= 0) return fallback;
    return Math.min(numeric, now() + 60 * 1000);
  }

  function safeItem(candidate) {
    if (!candidate || typeof candidate !== 'object') return null;
    const id = safeOpaque(candidate.id);
    const kind = String(candidate.kind || '').toLowerCase();
    const status = String(candidate.status || '').toLowerCase();
    const source = candidate.source === 'conversation'
      ? 'conversation'
      : candidate.source === 'code'
        ? 'code'
        : 'video';
    if (!id || !KINDS.has(kind) || !STATUSES.has(status)) return null;

    const item = {
      id,
      kind,
      status,
      source,
      createdAt: safeTime(candidate.createdAt),
      updatedAt: safeTime(candidate.updatedAt),
    };
    if (source === 'video') {
      const jobId = safeOpaque(candidate.jobId);
      if (jobId) item.jobId = jobId;
    } else if (source === 'code') {
      const taskId = safeOpaque(candidate.taskId);
      const projectId = safeOpaque(candidate.projectId);
      const codeStatus = String(candidate.codeStatus || '').trim().toLowerCase();
      if (!taskId || !projectId || !CODE_STATUSES.has(codeStatus)) return null;
      item.taskId = taskId;
      item.projectId = projectId;
      item.codeStatus = codeStatus;
    } else {
      const chatId = safeOpaque(candidate.chatId);
      const requestMessageId = safeOpaque(candidate.requestMessageId);
      if (!chatId || !requestMessageId) return null;
      item.chatId = chatId;
      item.requestMessageId = requestMessageId;
    }
    return item;
  }

  function itemExpired(item, at = now()) {
    const age = at - Number(item.updatedAt || item.createdAt || 0);
    return age > (ACTIVE_STATUSES.has(item.status) ? ACTIVE_TTL_MS : FINISHED_TTL_MS);
  }

  function sortedItems() {
    const statusOrder = {failed: 0, running: 1, queued: 2, ready: 3};
    return Array.from(state.items.values())
      .filter(item => !itemExpired(item))
      .sort((left, right) => (
        (statusOrder[left.status] ?? 9) - (statusOrder[right.status] ?? 9)
        || Number(right.updatedAt || 0) - Number(left.updatedAt || 0)
      ));
  }

  function readPersisted(userId) {
    const storage = safeStorage();
    const key = storageKey(userId);
    if (!storage || !key) return [];
    try {
      const payload = JSON.parse(storage.getItem(key) || 'null');
      if (payload?.version !== VERSION || String(payload?.userId || '') !== userId) {
        storage.removeItem(key);
        return [];
      }
      return (Array.isArray(payload.items) ? payload.items : [])
        .map(safeItem)
        .filter(item => item && !itemExpired(item))
        .slice(0, MAX_STORED_ITEMS);
    } catch (_) {
      try { storage.removeItem(key); } catch (_) { /* storage is optional */ }
      return [];
    }
  }

  function persist() {
    const storage = safeStorage();
    const key = storageKey();
    if (!storage || !key || !state.userId) return;
    const items = sortedItems().slice(0, MAX_STORED_ITEMS);
    state.items = new Map(items.map(item => [item.id, item]));
    try {
      storage.setItem(key, JSON.stringify({
        version: VERSION,
        userId: state.userId,
        savedAt: now(),
        items,
      }));
    } catch (_) { /* storage is optional */ }
  }

  function upsert(candidate, {render = false, persistNow = false} = {}) {
    const item = safeItem(candidate);
    if (!item || !state.userId) return false;
    const previous = state.items.get(item.id);
    const approvalResumed = Boolean(
      previous?.source === 'code'
      && previous?.codeStatus === 'awaiting_approval'
      && item.source === 'code'
      && ACTIVE_STATUSES.has(item.status),
    );
    const preserveTerminal = Boolean(
      previous
      && !ACTIVE_STATUSES.has(previous.status)
      && ACTIVE_STATUSES.has(item.status)
      && !approvalResumed,
    );
    state.items.set(item.id, {
      ...(previous || {}),
      ...item,
      status: preserveTerminal ? previous.status : item.status,
      createdAt: previous?.createdAt || item.createdAt,
      updatedAt: preserveTerminal
        ? previous.updatedAt
        : Math.max(Number(previous?.updatedAt || 0), Number(item.updatedAt || 0)),
    });
    if (persistNow) persist();
    if (render) renderAll();
    return true;
  }

  function removeItem(id) {
    const normalized = safeOpaque(id);
    if (normalized) state.items.delete(normalized);
  }

  function readScopedRecord(prefix) {
    const storage = safeStorage();
    const key = accountVideoKey(prefix);
    if (!storage || !key || !state.userId) return null;
    try {
      const record = JSON.parse(storage.getItem(key) || 'null');
      if (record?.version !== 1 || String(record?.userId || '') !== state.userId) return null;
      return record;
    } catch (_) {
      return null;
    }
  }

  function reconcileStoredVideo() {
    const job = readScopedRecord(VIDEO_JOB_PREFIX);
    const jobId = safeOpaque(job?.jobId);
    if (jobId) {
      upsert({
        id: `video:${jobId}`,
        jobId,
        source: 'video',
        kind: 'video',
        status: 'running',
        createdAt: Number(job?.updatedAt || now()),
        updatedAt: Number(job?.updatedAt || now()),
      });
    }

    const request = readScopedRecord(VIDEO_REQUEST_PREFIX);
    const hasPendingRequest = Boolean(request?.idempotencyKey && request?.requestDigest);
    if (hasPendingRequest && !jobId) {
      upsert({
        id: 'video-request:pending',
        source: 'video',
        kind: 'video',
        status: 'queued',
        createdAt: Number(request.createdAt || now()),
        updatedAt: Number(request.createdAt || now()),
      });
    } else {
      removeItem('video-request:pending');
    }
  }

  function artifactKind(format) {
    const normalized = String(format || '').trim().toLowerCase().replace(/^\./, '');
    if (normalized === 'pptx' || normalized === 'ppt') return 'presentation';
    if (['docx', 'pdf', 'xlsx', 'csv', 'txt', 'md', 'html', 'rtf'].includes(normalized)) return 'document';
    return '';
  }

  function conversationWorkKind(message, assistant) {
    const meta = message?.requestMeta && typeof message.requestMeta === 'object'
      ? message.requestMeta
      : {};
    if (meta.creativeTool === 'image') return 'image';
    const requestedArtifact = artifactKind(meta.artifactFormat);
    if (requestedArtifact) return requestedArtifact;
    if (assistant?.imageFile || assistant?.imageUrl) return 'image';
    const artifact = assistant?.artifact;
    if (artifact && typeof artifact === 'object') {
      return artifactKind(artifact.format || artifact.extension || artifact.type);
    }
    return '';
  }

  function conversationWorkStatus(message, assistant) {
    if (message?.replyStatus === 'failed' || message?.deliveryStatus === 'failed') return 'failed';
    if (message?.replyStatus === 'replied') return assistant ? 'ready' : '';
    if (message?.replyStatus === 'processing') return 'running';
    if (message?.replyStatus === 'pending' || message?.deliveryStatus === 'queued') return 'queued';
    if (message?.deliveryStatus === 'sending' || message?.deliveryStatus === 'delivered') return 'queued';
    return '';
  }

  function reconcileConversationWork() {
    const chats = Array.isArray(window.chats) ? window.chats.slice(0, 50) : [];
    chats.forEach(chat => {
      const chatId = safeOpaque(chat?.id || chat?.chat_id);
      if (!chatId) return;
      const messages = Array.isArray(chat?.messages) ? chat.messages.slice(-24) : [];
      const assistantByRequest = new Map(
        messages
          .filter(message => message?.role === 'assistant' && safeOpaque(message?.inReplyTo))
          .map(message => [String(message.inReplyTo), message]),
      );
      messages.forEach(message => {
        if (message?.role !== 'user') return;
        const requestMessageId = safeOpaque(message.id);
        if (!requestMessageId) return;
        const assistant = assistantByRequest.get(requestMessageId) || null;
        const kind = conversationWorkKind(message, assistant);
        if (!kind) return;
        const status = conversationWorkStatus(message, assistant);
        if (!status) return;
        const timestamp = safeTime(message.timestamp || message.createdAt);
        const recordId = `conversation:${chatId}:${requestMessageId}`;
        const terminalTimestamp = status === 'ready'
          ? safeTime(assistant?.timestamp || assistant?.createdAt, timestamp)
          : status === 'failed'
            ? safeTime(message?.updatedAt || message?.failedAt, timestamp)
            : timestamp;
        upsert({
          id: recordId,
          source: 'conversation',
          kind,
          status,
          chatId,
          requestMessageId,
          createdAt: timestamp,
          updatedAt: terminalTimestamp,
        });
      });
    });
  }

  function normalizeVideoStatus(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'queued') return 'queued';
    if (normalized === 'processing' || normalized === 'running') return 'running';
    if (normalized === 'ready' || normalized === 'completed' || normalized === 'succeeded') return 'ready';
    if (normalized === 'failed' || normalized === 'error' || normalized === 'cancelled') return 'failed';
    return '';
  }

  function normalizeCodeStatus(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'queued') return 'queued';
    if (normalized === 'provisioning' || normalized === 'running' || normalized === 'verifying') return 'running';
    if (normalized === 'completed') return 'ready';
    if (normalized === 'awaiting_approval' || normalized === 'failed' || normalized === 'cancelled') return 'failed';
    return '';
  }

  function reconcileVideoResponse(data, ownerUserId) {
    if (!ownerUserId || ownerUserId !== state.userId || currentUserId() !== ownerUserId) return;
    const jobs = Array.isArray(data?.jobs) ? data.jobs.slice(0, 12) : [];
    jobs.forEach(job => {
      const jobId = safeOpaque(job?.id);
      const status = normalizeVideoStatus(job?.status);
      if (!jobId || !status) return;
      upsert({
        id: `video:${jobId}`,
        jobId,
        source: 'video',
        kind: 'video',
        status,
        createdAt: safeTime(job?.createdAt),
        updatedAt: safeTime(job?.updatedAt || job?.createdAt),
      });
    });
  }

  function reconcileCodeResponse(data, ownerUserId) {
    if (!ownerUserId || ownerUserId !== state.userId || currentUserId() !== ownerUserId) return;
    const activity = Array.isArray(data?.activity) ? data.activity.slice(0, MAX_STORED_ITEMS) : [];
    activity.forEach(task => {
      const taskId = safeOpaque(task?.id);
      const projectId = safeOpaque(task?.projectId);
      const codeStatus = String(task?.status || '').trim().toLowerCase();
      const status = normalizeCodeStatus(codeStatus);
      if (!taskId || !projectId || !status || !CODE_STATUSES.has(codeStatus)) return;
      upsert({
        id: `code:${taskId}`,
        taskId,
        projectId,
        codeStatus,
        source: 'code',
        kind: 'code',
        status,
        createdAt: safeTime(task?.createdAt),
        updatedAt: safeTime(task?.completedAt || task?.updatedAt || task?.createdAt),
      });
    });
  }

  function counts() {
    return sortedItems().reduce((result, item) => {
      result[item.status] += 1;
      return result;
    }, {queued: 0, running: 0, ready: 0, failed: 0});
  }

  function hasActiveFeed(feed) {
    return sortedItems().some(item => item.kind === feed && ACTIVE_STATUSES.has(item.status));
  }

  function feedNextNetworkDelay(feed) {
    const baseDelay = hasActiveFeed(feed) ? ACTIVE_REFRESH_MS : IDLE_REFRESH_MS;
    const failures = Number(state.feedFailureCount[feed] || 0);
    const backoffMultiplier = 2 ** Math.min(failures, MAX_FAILURE_BACKOFF_STEP);
    return Math.min(MAX_FAILURE_BACKOFF_MS, baseDelay * backoffMultiplier);
  }

  function dueNetworkFeeds(force) {
    return NETWORK_FEEDS.filter(feed => (
      force
      || now() - Number(state.feedLastNetworkAt[feed] || 0) >= feedNextNetworkDelay(feed)
    ));
  }

  function nextNetworkDelay() {
    return Math.min(...NETWORK_FEEDS.map(feedNextNetworkDelay));
  }

  function syncNetworkState() {
    state.lastNetworkAt = Math.max(...Object.values(state.feedLastNetworkAt));
    state.networkFailureCount = Math.max(...Object.values(state.feedFailureCount));
    state.networkUnavailable = state.networkFailureCount > 0;
    state.networkIssue = Object.values(state.feedIssue).includes('timeout')
      ? 'timeout'
      : state.networkUnavailable
        ? 'unavailable'
        : '';
  }

  function resetNetworkState() {
    state.feedLastNetworkAt = {video: 0, code: 0};
    state.feedFailureCount = {video: 0, code: 0};
    state.feedIssue = {video: '', code: ''};
    syncNetworkState();
  }

  function abortNetwork(reason) {
    const controller = state.networkController;
    if (!controller) return false;
    NETWORK_ABORT_REASONS.set(controller, String(reason || 'intentional'));
    controller.abort();
    return true;
  }

  function requestTimeoutMs() {
    if (window.__ASKCRUMP_ACTIVITY_TEST__ !== true) return REQUEST_TIMEOUT_MS;
    const configured = Number(window.__ASKCRUMP_ACTIVITY_TEST_CONFIG__?.requestTimeoutMs);
    return Number.isFinite(configured) && configured >= 10
      ? configured
      : REQUEST_TIMEOUT_MS;
  }

  async function refreshVideos({force = false} = {}) {
    const ownerUserId = currentUserId();
    if (!ownerUserId || ownerUserId !== state.userId || document.hidden) return false;
    if (state.networkInFlight) return state.networkInFlight;
    const dueFeeds = dueNetworkFeeds(force);
    if (!dueFeeds.length) return false;

    const controller = new AbortController();
    state.networkController = controller;
    const timeout = window.setTimeout(() => {
      NETWORK_ABORT_REASONS.set(controller, 'timeout');
      controller.abort();
    }, requestTimeoutMs());
    if (state.refreshButton) state.refreshButton.disabled = true;
    let requestPromise;
    requestPromise = (async () => {
      try {
        const fetchActivity = async path => {
          const response = await fetch(path, {
            method: 'GET',
            credentials: 'same-origin',
            cache: 'no-store',
            headers: {
              'Accept': 'application/json',
              'X-Ask-Crump-Expected-Owner': ownerUserId,
            },
            signal: controller.signal,
          });
          const data = await response.json().catch(() => ({}));
          if (state.userId !== ownerUserId || currentUserId() !== ownerUserId) {
            throw new Error('AUTH_OWNER_MISMATCH');
          }
          if (!response.ok) throw new Error('ACCOUNT_ACTIVITY_UNAVAILABLE');
          return data;
        };
        const paths = {video: '/api/media/video', code: '/api/code/activity'};
        const results = await Promise.allSettled(
          dueFeeds.map(feed => fetchActivity(paths[feed])),
        );
        const abortReason = NETWORK_ABORT_REASONS.get(controller) || '';
        const intentionalAbort = abortReason === 'visibility' || abortReason === 'signout';
        if (intentionalAbort) return false;

        let anySuccess = false;
        results.forEach((result, index) => {
          const feed = dueFeeds[index];
          state.feedLastNetworkAt[feed] = now();
          if (result.status === 'fulfilled') {
            if (feed === 'video') reconcileVideoResponse(result.value, ownerUserId);
            else reconcileCodeResponse(result.value, ownerUserId);
            state.feedFailureCount[feed] = 0;
            state.feedIssue[feed] = '';
            anySuccess = true;
          } else {
            state.feedFailureCount[feed] = Math.min(
              Number(state.feedFailureCount[feed] || 0) + 1,
              MAX_FAILURE_BACKOFF_STEP,
            );
            state.feedIssue[feed] = abortReason === 'timeout' ? 'timeout' : 'unavailable';
          }
        });
        syncNetworkState();
        if (anySuccess) {
          persist();
        }
        renderAll();
        return anySuccess;
      } catch (error) {
        const abortReason = NETWORK_ABORT_REASONS.get(controller) || '';
        const intentionalAbort = abortReason === 'visibility' || abortReason === 'signout';
        const stillCurrentOwner = state.userId === ownerUserId && currentUserId() === ownerUserId;
        if (!intentionalAbort && stillCurrentOwner) {
          dueFeeds.forEach(feed => {
            state.feedLastNetworkAt[feed] = now();
            state.feedFailureCount[feed] = Math.min(
              Number(state.feedFailureCount[feed] || 0) + 1,
              MAX_FAILURE_BACKOFF_STEP,
            );
            state.feedIssue[feed] = abortReason === 'timeout' ? 'timeout' : 'unavailable';
          });
          syncNetworkState();
          renderAll();
        }
        return false;
      } finally {
        window.clearTimeout(timeout);
        const abortReason = NETWORK_ABORT_REASONS.get(controller) || '';
        const intentionalAbort = abortReason === 'visibility' || abortReason === 'signout';
        NETWORK_ABORT_REASONS.delete(controller);
        if (state.networkController === controller) state.networkController = null;
        if (state.networkInFlight === requestPromise) state.networkInFlight = null;
        if (state.refreshButton) state.refreshButton.disabled = false;
      }
    })();
    state.networkInFlight = requestPromise;
    return state.networkInFlight;
  }

  function kindLabel(kind) {
    return {
      video: 'Video',
      image: 'Image',
      document: 'Document',
      presentation: 'Presentation',
      code: 'Autonomous task',
    }[kind] || 'Creation';
  }

  function statusLabel(status) {
    return {
      queued: 'Queued',
      running: 'In progress',
      ready: 'Ready',
      failed: 'Needs attention',
    }[status] || 'Activity';
  }

  function statusDetail(item) {
    if (item.kind === 'code') {
      if (item.codeStatus === 'awaiting_approval') return 'Approval required before it can continue';
      if (item.status === 'queued') return 'Waiting for its isolated worker';
      if (item.status === 'running') return 'Continues safely outside Autonomous Crump';
      if (item.status === 'ready') return 'Patch and verification are ready';
      if (item.codeStatus === 'cancelled') return 'Open Autonomous Crump to review the cancellation';
      return 'Open Autonomous Crump to review';
    }
    if (item.status === 'queued') return item.kind === 'video'
      ? 'Waiting for a generation slot'
      : 'Waiting to begin';
    if (item.status === 'running') return item.kind === 'video'
      ? 'Continues securely outside Video Studio'
      : 'Working in this signed-in session';
    if (item.status === 'ready') return item.kind === 'video'
      ? 'Saved to your private Files'
      : 'Available in its conversation';
    return item.kind === 'video'
      ? 'Open Video Studio to review'
      : 'Open the conversation to review';
  }

  function relativeTime(value) {
    const elapsed = Math.max(0, now() - Number(value || now()));
    if (elapsed < 60 * 1000) return 'Just now';
    const minutes = Math.floor(elapsed / (60 * 1000));
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  function createActivityItem(item) {
    const article = document.createElement('article');
    article.className = `crump-activity-item is-${item.status}`;
    article.dataset.activityId = item.id;
    article.dataset.activityKind = item.kind;
    article.dataset.activityStatus = item.status;

    const icon = document.createElement('span');
    icon.className = 'crump-activity-item-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = item.kind === 'code'
      ? '<svg viewBox="0 0 24 24"><path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"></path></svg>'
      : item.kind === 'video'
      ? '<svg viewBox="0 0 24 24"><rect x="3.8" y="5.25" width="16.4" height="13.5" rx="2.4"></rect><path d="m10.25 9.15 5 2.85-5 2.85v-5.7Z"></path></svg>'
      : item.kind === 'image'
        ? '<svg viewBox="0 0 24 24"><rect x="3.5" y="4" width="17" height="16" rx="2.5"></rect><circle cx="9" cy="9" r="1.5"></circle><path d="m5.5 17 4.3-4.4 3.1 3.1 2.1-2.2 3.5 3.5"></path></svg>'
        : item.kind === 'presentation'
          ? '<svg viewBox="0 0 24 24"><rect x="3.5" y="4" width="17" height="13" rx="2"></rect><path d="M8 21h8M12 17v4M7 8h10M7 11h6"></path></svg>'
          : '<svg viewBox="0 0 24 24"><path d="M6 3.5h8l4 4v13H6z"></path><path d="M14 3.5v4h4M9 12h6M9 15h6"></path></svg>';

    const copy = document.createElement('div');
    copy.className = 'crump-activity-item-copy';
    const title = document.createElement('strong');
    title.textContent = `${kindLabel(item.kind)} ${statusLabel(item.status).toLowerCase()}`;
    const detail = document.createElement('span');
    detail.textContent = statusDetail(item);
    const time = document.createElement('small');
    time.dataset.activityTimestamp = String(item.updatedAt);
    time.textContent = relativeTime(item.updatedAt);
    const exactTime = new Date(item.updatedAt);
    if (!Number.isNaN(exactTime.getTime())) time.title = exactTime.toLocaleString();
    copy.append(title, detail, time);

    const status = document.createElement('span');
    status.className = `crump-activity-status is-${item.status}`;
    status.textContent = statusLabel(item.status);

    const action = document.createElement('button');
    action.type = 'button';
    action.className = 'crump-activity-action';
    action.textContent = item.status === 'ready' ? 'View' : item.status === 'failed' ? 'Review' : 'Open';
    action.setAttribute('aria-label', `${action.textContent} ${kindLabel(item.kind).toLowerCase()} ${statusLabel(item.status).toLowerCase()}`);
    action.addEventListener('click', () => openItem(item));

    article.append(icon, copy, status, action);
    return article;
  }

  function refreshRelativeTimes() {
    state.list?.querySelectorAll('[data-activity-timestamp]').forEach(element => {
      const timestamp = Number(element.dataset.activityTimestamp || 0);
      const nextText = relativeTime(timestamp);
      if (element.textContent !== nextText) element.textContent = nextText;
    });
  }

  function renderAll({force = false} = {}) {
    if (!state.trigger || !state.panel || !state.list || !state.summary) return;
    const items = sortedItems();
    const tally = counts();
    const signature = JSON.stringify({
      owner: state.userId,
      unavailable: state.networkUnavailable,
      networkIssue: state.networkIssue,
      items: items.slice(0, MAX_VISIBLE_ITEMS).map(item => [item.id, item.status, item.updatedAt]),
    });
    if (!force && signature === state.lastRenderSignature) {
      refreshRelativeTimes();
      return;
    }
    state.lastRenderSignature = signature;
    const active = tally.running + tally.queued;
    const needsAttention = tally.failed;
    const badgeCount = active || needsAttention;
    const badge = state.trigger.querySelector('.crump-activity-badge');
    if (badge) {
      badge.hidden = badgeCount === 0;
      badge.textContent = badgeCount > 9 ? '9+' : String(badgeCount);
    }
    state.trigger.classList.toggle('has-active', active > 0);
    state.trigger.classList.toggle('has-attention', needsAttention > 0);
    state.trigger.classList.toggle('has-ready', tally.ready > 0 && active === 0 && needsAttention === 0);
    const triggerLabels = [];
    if (needsAttention) triggerLabels.push(`${needsAttention} needs attention`);
    if (active) triggerLabels.push(`${active} in progress`);
    if (tally.ready) triggerLabels.push(`${tally.ready} ready`);
    state.trigger.setAttribute('aria-label', triggerLabels.length
      ? `Activity, ${triggerLabels.join(', ')}`
      : 'Activity');

    const parts = [];
    if (active) parts.push(`${active} in progress`);
    if (tally.ready) parts.push(`${tally.ready} ready`);
    if (tally.failed) parts.push(`${tally.failed} needs attention`);
    state.summary.textContent = parts.length ? parts.join(' · ') : 'No current activity';
    state.summary.dataset.networkState = state.networkUnavailable ? 'delayed' : 'current';

    const focusedItemId = state.list.contains(document.activeElement)
      ? document.activeElement?.closest?.('[data-activity-id]')?.dataset?.activityId || ''
      : '';
    state.list.replaceChildren();
    const visible = items.slice(0, MAX_VISIBLE_ITEMS);
    if (!visible.length) {
      const empty = document.createElement('div');
      empty.className = 'crump-activity-empty';
      empty.innerHTML = '<span aria-hidden="true">✓</span><strong>You’re all caught up.</strong><p>New video, Autonomous Crump, and creative work will appear here.</p>';
      state.list.appendChild(empty);
    } else {
      visible.forEach(item => state.list.appendChild(createActivityItem(item)));
      if (focusedItemId) {
        const focusedItem = Array.from(state.list.querySelectorAll('[data-activity-id]'))
          .find(element => element.dataset.activityId === focusedItemId);
        focusedItem?.querySelector('.crump-activity-action')?.focus({preventScroll: true});
      }
    }
    const note = byId('crumpActivityNetworkNote');
    if (note) {
      note.hidden = !state.networkUnavailable;
      note.textContent = state.networkIssue === 'timeout'
        ? 'Activity status took too long to refresh. Your work continues safely; retry when ready.'
        : state.networkUnavailable
          ? 'Account activity will refresh when the connection is available.'
          : '';
    }
    dispatchCounts(tally);
  }

  function dispatchCounts(tally = counts()) {
    const signature = `${state.userId}:${tally.queued}:${tally.running}:${tally.ready}:${tally.failed}`;
    if (signature === state.lastCountSignature) return;
    state.lastCountSignature = signature;
    try {
      window.dispatchEvent(new CustomEvent('crump:activity-changed', {
        detail: {
          queued: tally.queued,
          running: tally.running,
          ready: tally.ready,
          failed: tally.failed,
        },
      }));
    } catch (_) { /* custom events are progressive enhancement */ }
  }

  function openItem(item) {
    closePanel();
    if (item.kind === 'code') {
      if (typeof window.CrumpCodeLoader?.open === 'function') {
        void window.CrumpCodeLoader.open({projectId: item.projectId, taskId: item.taskId});
      } else {
        window.showToast?.('Autonomous Crump is still loading. Try again in a moment.', 'info');
      }
      return;
    }
    if (item.kind === 'video') {
      if (typeof window.CrumpVision?.navigate === 'function') {
        window.CrumpVision.navigate('video');
      } else if (typeof window.CrumpProduct53?.open === 'function') {
        void window.CrumpProduct53.open('video');
      } else {
        window.showToast?.('Video Studio is still loading. Try again in a moment.', 'info');
      }
      return;
    }

    if (typeof window.CrumpVision?.navigate === 'function') window.CrumpVision.navigate('ask');
    const chatId = safeOpaque(item.chatId);
    if (!chatId || typeof window.loadChat !== 'function') {
      window.showToast?.('That conversation is still loading. Try again in a moment.', 'info');
      return;
    }
    window.setTimeout(() => window.loadChat?.(chatId), 0);
  }

  function openPanel() {
    if (!state.panel || !state.trigger || !state.userId) return;
    state.lastFocus = document.activeElement;
    state.opened = true;
    state.panel.hidden = false;
    state.trigger.setAttribute('aria-expanded', 'true');
    document.body.classList.add('crump-activity-open');
    renderAll({force: true});
    state.panel.querySelector('.crump-activity-close')?.focus({preventScroll: true});
    void refreshVideos({force: true});
  }

  function closePanel(restoreFocus = true) {
    if (!state.panel || !state.trigger) return;
    state.opened = false;
    state.panel.hidden = true;
    state.trigger.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('crump-activity-open');
    if (restoreFocus) {
      const target = state.lastFocus?.isConnected ? state.lastFocus : state.trigger;
      target?.focus?.({preventScroll: true});
    }
    state.lastFocus = null;
  }

  function togglePanel() {
    if (state.opened) closePanel();
    else openPanel();
  }

  function mount() {
    if (state.trigger?.isConnected && state.panel?.isConnected) return;
    const host = document.querySelector('.v1-workspace') || byId('appContainer') || document.body;

    const trigger = document.createElement('button');
    trigger.id = 'crumpActivityTrigger';
    trigger.type = 'button';
    trigger.className = 'crump-activity-trigger';
    trigger.hidden = true;
    trigger.setAttribute('aria-label', 'Activity');
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.setAttribute('aria-controls', 'crumpActivityPanel');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.25a7.75 7.75 0 1 0 7.75 7.75"></path><path d="M12 7.2V12l3.2 1.9"></path><path d="M17.6 4.4h2.05v2.05"></path></svg>
      <span class="crump-activity-trigger-label">Activity</span>
      <span class="crump-activity-badge" aria-hidden="true" hidden>0</span>`;

    const panel = document.createElement('section');
    panel.id = 'crumpActivityPanel';
    panel.className = 'crump-activity-panel';
    panel.hidden = true;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'false');
    panel.setAttribute('aria-labelledby', 'crumpActivityTitle');
    panel.innerHTML = `
      <header class="crump-activity-head">
        <div>
          <span>WORKSPACE</span>
          <h2 id="crumpActivityTitle">Activity</h2>
          <p id="crumpActivitySummary" role="status" aria-live="polite">No current activity</p>
        </div>
        <button type="button" class="crump-activity-close" aria-label="Close activity">×</button>
      </header>
      <div id="crumpActivityList" class="crump-activity-list"></div>
      <footer class="crump-activity-foot">
        <p id="crumpActivityNetworkNote" hidden></p>
        <span>Video and Autonomous Crump status sync from your account. Current chat creations appear with their conversation.</span>
        <button type="button" class="crump-activity-refresh">Refresh status</button>
      </footer>`;

    host.append(trigger, panel);
    state.trigger = trigger;
    state.panel = panel;
    state.list = byId('crumpActivityList');
    state.summary = byId('crumpActivitySummary');
    state.refreshButton = panel.querySelector('.crump-activity-refresh');

    trigger.addEventListener('click', togglePanel);
    panel.querySelector('.crump-activity-close')?.addEventListener('click', () => closePanel());
    state.refreshButton?.addEventListener('click', () => void refreshVideos({force: true}));
    observeHeaderStatus();
    renderAll({force: true});
  }

  function syncHeaderStatus() {
    const status = byId('connectionStatus') || document.querySelector('.connection-status');
    const visible = Boolean(status && !status.hidden && status.getAttribute('aria-hidden') !== 'true');
    document.body.classList.toggle('crump-activity-has-connection-status', visible);
  }

  function observeHeaderStatus() {
    state.headerStatusObserver?.disconnect?.();
    state.headerStatusObserver = null;
    const status = byId('connectionStatus') || document.querySelector('.connection-status');
    if (!status) {
      document.body.classList.remove('crump-activity-has-connection-status');
      return;
    }
    state.headerStatusObserver = new MutationObserver(syncHeaderStatus);
    state.headerStatusObserver.observe(status, {
      attributes: true,
      attributeFilter: ['hidden', 'aria-hidden', 'class', 'style'],
    });
    syncHeaderStatus();
  }

  function stopLoop() {
    if (state.loopTimer) window.clearTimeout(state.loopTimer);
    state.loopTimer = null;
  }

  function scheduleLoop(delay = LOCAL_RECONCILE_MS) {
    stopLoop();
    if (!state.userId || document.hidden) return;
    state.loopTimer = window.setTimeout(runLoop, delay);
  }

  function runLoop() {
    state.loopTimer = null;
    if (!state.userId || document.hidden || currentUserId() !== state.userId) return;
    reconcileStoredVideo();
    reconcileConversationWork();
    persist();
    renderAll();
    void refreshVideos();
    scheduleLoop();
  }

  function activate() {
    mount();
    const ownerUserId = currentUserId();
    if (!ownerUserId) return;
    if (state.userId !== ownerUserId) {
      state.userId = ownerUserId;
      state.items = new Map(readPersisted(ownerUserId).map(item => [item.id, item]));
      resetNetworkState();
      state.lastRenderSignature = '';
      state.lastCountSignature = '';
    }
    state.trigger.hidden = false;
    reconcileStoredVideo();
    reconcileConversationWork();
    persist();
    renderAll();
    void refreshVideos({force: true});
    scheduleLoop();
  }

  function deactivate() {
    stopLoop();
    abortNetwork('signout');
    state.networkController = null;
    state.networkInFlight = null;
    closePanel(false);
    if (state.trigger) state.trigger.hidden = true;
    state.userId = '';
    state.items.clear();
    resetNetworkState();
    state.lastRenderSignature = '';
    state.lastCountSignature = '';
    renderAll({force: true});
  }

  function report(candidate) {
    if (!state.userId || currentUserId() !== state.userId) return false;
    const accepted = upsert(candidate, {persistNow: true, render: true});
    if (accepted) scheduleLoop();
    return accepted;
  }

  function handleReportedActivity(event) {
    report(event?.detail);
  }

  function handleStorage(event) {
    if (!state.userId) return;
    if (event.key === storageKey()) {
      state.items = new Map(readPersisted(state.userId).map(item => [item.id, item]));
      reconcileStoredVideo();
      reconcileConversationWork();
      renderAll();
      return;
    }
    if (event.key === accountVideoKey(VIDEO_JOB_PREFIX) || event.key === accountVideoKey(VIDEO_REQUEST_PREFIX)) {
      reconcileStoredVideo();
      persist();
      renderAll();
      void refreshVideos({force: true});
    }
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && state.opened) {
      event.preventDefault();
      closePanel();
    }
  });
  document.addEventListener('pointerdown', event => {
    if (!state.opened || state.panel?.contains(event.target) || state.trigger?.contains(event.target)) return;
    closePanel();
  }, true);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopLoop();
      abortNetwork('visibility');
      return;
    }
    if (currentUserId()) {
      activate();
      void refreshVideos({force: true});
    }
  });
  window.addEventListener('online', () => {
    if (!state.userId) return;
    resetNetworkState();
    void refreshVideos({force: true});
  });
  window.addEventListener('storage', handleStorage);
  window.addEventListener('crump:activity', handleReportedActivity);
  window.addEventListener('crump:authenticated-ready', activate);
  window.addEventListener('crump:authentication-required', deactivate);

  window.CrumpActivityCenter = Object.freeze({
    open: openPanel,
    close: closePanel,
    refresh: () => refreshVideos({force: true}),
    report,
    counts: () => ({...counts()}),
  });

  if (window.__ASKCRUMP_ACTIVITY_TEST__ === true) {
    window.__CrumpActivityCenterTestHooks = Object.freeze({
      abortNetwork,
      reconcileStoredVideo,
      refreshVideos,
      snapshot: () => ({
        userId: state.userId,
        items: sortedItems().map(item => ({...item})),
        lastNetworkAt: state.lastNetworkAt,
        networkUnavailable: state.networkUnavailable,
        networkIssue: state.networkIssue,
        networkFailureCount: state.networkFailureCount,
        feedFailureCount: {...state.feedFailureCount},
        feedLastNetworkAt: {...state.feedLastNetworkAt},
        nextNetworkDelay: nextNetworkDelay(),
      }),
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      mount();
      if (currentUserId()) activate();
    }, {once: true});
  } else {
    mount();
    if (currentUserId()) activate();
  }
})();
