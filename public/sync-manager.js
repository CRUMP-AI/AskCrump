(() => {
  'use strict';
  const PENDING_KEY = 'crump_sync_queue_v4';
  const SYNC_KEY = 'crump_last_sync_v4';
  const SYNC_REQUEST_TIMEOUT_MS = 12_000;
  const SYNC_OWNER_HEADER = 'X-Ask-Crump-Sync-Owner';
  const MAX_CHATS_PER_PUSH = 20;
  const MAX_TOMBSTONES_PER_PUSH = 20;
  let flushPromise = null;
  let flushPromiseKey = null;

  const read = (key, fallback) => {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_) { return fallback; }
  };
  const write = (key, value) => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (_) {
      return false;
    }
  };
  function captureAuthBoundary() {
    const boundary = window.CrumpAuthBoundary;
    const userId = String(
      typeof boundary?.authenticatedUserId === 'function'
        ? boundary.authenticatedUserId()
        : window.currentUser?.id || '',
    ).trim();
    const rawRevision = typeof boundary?.revision === 'function' ? boundary.revision() : 0;
    const revision = Number(rawRevision);
    return Object.freeze({
      userId,
      revision: Number.isFinite(revision) ? revision : 0,
    });
  }

  function authBoundaryIsCurrent(snapshot) {
    if (!snapshot?.userId) return false;
    const current = captureAuthBoundary();
    return current.userId === snapshot.userId && current.revision === snapshot.revision;
  }

  function authBoundaryChanged(flushed = false) {
    return {
      success: false,
      code: 'SYNC_AUTH_BOUNDARY_CHANGED',
      staleAuth: true,
      queued: true,
      retryable: true,
      flushed,
      error: 'The signed-in account changed before synchronization completed.',
    };
  }

  const userKey = (key, userId = captureAuthBoundary().userId) => `${key}:${userId || 'anonymous'}`;

  async function requestJson(url, options, invalidResponseError) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), SYNC_REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      const data = await response.json().catch(() => ({
        success: false,
        error: invalidResponseError,
      }));
      return {response, data};
    } catch (error) {
      if (error?.name === 'AbortError') {
        throw new Error('Synchronization timed out. Your work is still queued.');
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  async function pull(_legacyDeviceId, options = {}) {
    const authBoundary = options.authBoundary || captureAuthBoundary();
    if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(false);
    const full = options.full !== false;
    const peek = options.peek === true;
    const syncKey = userKey(SYNC_KEY, authBoundary.userId);
    const since = full ? null : read(syncKey, null);
    const url = since ? `/api/sync/pull?since=${encodeURIComponent(since)}` : '/api/sync/pull';
    const {response, data} = await requestJson(
      url,
      {
        method: 'GET',
        headers: {[SYNC_OWNER_HEADER]: authBoundary.userId},
      },
      'Invalid sync response.',
    );
    if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(false);
    // A peek is a non-mutating verification read: it must never advance the
    // incremental-pull watermark, or rows it observed but did not apply would
    // be skipped by the next incremental pull. Never save/restore the cursor
    // around a peek either — that could clobber a concurrent advancement.
    if (!peek && response.ok && data.success) write(syncKey, data.serverTime || new Date().toISOString());
    return data;
  }

  const isRecord = value => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
  const parsedTime = value => {
    const parsed = Date.parse(String(value || ''));
    return Number.isFinite(parsed) ? parsed : null;
  };
  const stableValue = value => {
    if (Array.isArray(value)) return value.map(stableValue);
    if (!isRecord(value)) return value;
    return Object.fromEntries(
      Object.keys(value).sort().map(key => [key, stableValue(value[key])]),
    );
  };
  const stableSignature = value => JSON.stringify(stableValue(value));

  function mergeRecord(older, newer) {
    const merged = {...(isRecord(older) ? older : {})};
    for (const [key, value] of Object.entries(isRecord(newer) ? newer : {})) {
      if (isRecord(merged[key]) && isRecord(value)) {
        merged[key] = mergeRecord(merged[key], value);
      } else if (value !== undefined) {
        merged[key] = value;
      }
    }
    return merged;
  }

  function versionOrder(left, right, timeFields) {
    const leftTime = timeFields.map(field => parsedTime(left?.[field])).find(value => value !== null) ?? 0;
    const rightTime = timeFields.map(field => parsedTime(right?.[field])).find(value => value !== null) ?? 0;
    if (leftTime !== rightTime) return leftTime - rightTime;
    const leftRevision = Number(left?.revision || 0);
    const rightRevision = Number(right?.revision || 0);
    if (leftRevision !== rightRevision) return leftRevision - rightRevision;
    return stableSignature(left).localeCompare(stableSignature(right));
  }

  function messageKey(message) {
    const inReplyTo = message?.inReplyTo || message?.in_reply_to;
    if (message?.role === 'assistant' && inReplyTo) return `reply:${inReplyTo}`;
    if (message?.id) return `id:${message.id}`;
    return `legacy:${stableSignature({
      role: message?.role || '',
      timestamp: message?.timestamp || '',
      content: message?.content || '',
      imageUrl: message?.imageUrl || message?.image_url || '',
      files: message?.files || [],
    })}`;
  }

  const deliveryRank = status => ({sending: 1, queued: 2, failed: 2, delivered: 3, seen: 4}[status] || 0);
  const replyRank = status => ({pending: 1, failed: 2, processing: 3, replied: 4}[status] || 0);

  function mergeMessage(older, newer) {
    const merged = mergeRecord(older, newer);
    const olderDelivery = older?.deliveryStatus || older?.delivery_status;
    const newerDelivery = newer?.deliveryStatus || newer?.delivery_status;
    const olderReply = older?.replyStatus || older?.reply_status;
    const newerReply = newer?.replyStatus || newer?.reply_status;
    if (deliveryRank(olderDelivery) > deliveryRank(newerDelivery)) {
      merged.deliveryStatus = olderDelivery;
    }
    if (replyRank(olderReply) > replyRank(newerReply)) merged.replyStatus = olderReply;
    return merged;
  }

  function mergeMessages(leftMessages, rightMessages, rightIsNewer) {
    const olderMessages = rightIsNewer ? leftMessages : rightMessages;
    const newerMessages = rightIsNewer ? rightMessages : leftMessages;
    const messages = new Map();
    for (const message of Array.isArray(olderMessages) ? olderMessages : []) {
      if (!isRecord(message)) continue;
      messages.set(messageKey(message), {...message});
    }
    for (const message of Array.isArray(newerMessages) ? newerMessages : []) {
      if (!isRecord(message)) continue;
      const key = messageKey(message);
      messages.set(key, mergeMessage(messages.get(key), message));
    }
    return [...messages.entries()]
      .sort(([leftKey, left], [rightKey, right]) => {
        const leftTime = parsedTime(left?.timestamp);
        const rightTime = parsedTime(right?.timestamp);
        if (leftTime !== null && rightTime !== null && leftTime !== rightTime) {
          return leftTime - rightTime;
        }
        if (leftTime !== null && rightTime === null) return -1;
        if (leftTime === null && rightTime !== null) return 1;
        return leftKey.localeCompare(rightKey);
      })
      .map(([, message]) => message);
  }

  function mergeChat(left, right) {
    if (!isRecord(left)) return isRecord(right) ? {...right} : {};
    if (!isRecord(right)) return {...left};
    const rightIsNewer = versionOrder(
      left,
      right,
      ['updated_at', 'updatedAt', 'created_at', 'createdAt'],
    ) <= 0;
    const older = rightIsNewer ? left : right;
    const newer = rightIsNewer ? right : left;
    const merged = mergeRecord(older, newer);
    merged.messages = mergeMessages(left.messages, right.messages, rightIsNewer);
    merged.revision = Math.max(Number(left.revision || 0), Number(right.revision || 0), 1);

    const id = newer.chat_id || newer.id || older.chat_id || older.id;
    if (id) merged.chat_id = id;
    const created = [left.created_at, left.createdAt, right.created_at, right.createdAt]
      .map(value => ({value, time: parsedTime(value)}))
      .filter(item => item.time !== null)
      .sort((a, b) => a.time - b.time)[0]?.value;
    const updated = [left.updated_at, left.updatedAt, right.updated_at, right.updatedAt]
      .map(value => ({value, time: parsedTime(value)}))
      .filter(item => item.time !== null)
      .sort((a, b) => b.time - a.time)[0]?.value;
    if (created) merged.created_at = created;
    if (updated) merged.updated_at = updated;
    return merged;
  }

  function mergeQueue(queue) {
    const chats = new Map();
    const deleted = new Map();
    let settings = null;
    for (const entry of queue) {
      const payload = entry?.payload || {};
      for (const chat of payload.chats || []) {
        const id = chat?.chat_id || chat?.id;
        if (!id) continue;
        chats.set(id, mergeChat(chats.get(id), chat));
      }
      for (const tombstone of payload.deletedChats || []) {
        const value = typeof tombstone === 'string' ? { id: tombstone } : tombstone;
        const id = value?.chat_id || value?.id;
        if (!id) continue;
        const previous = deleted.get(id);
        const valueIsNewer = !previous || versionOrder(
          previous,
          value,
          ['deleted_at', 'deletedAt', 'updated_at', 'updatedAt'],
        ) <= 0;
        deleted.set(id, mergeRecord(valueIsNewer ? previous : value, valueIsNewer ? value : previous));
        chats.delete(id);
      }
      if (payload.settings && typeof payload.settings === 'object') {
        settings = mergeRecord(settings, payload.settings);
      }
    }
    // A queued deletion always wins over a stale snapshot from another tab.
    // Re-creating a conversation uses a new ID, so retaining the tombstone is
    // the only lossless and non-resurrecting choice for this queue.
    for (const id of deleted.keys()) chats.delete(id);
    return { chats: [...chats.values()], deletedChats: [...deleted.values()], settings };
  }

  const queueEntryId = (entry, index) => entry?.id || `legacy:${entry?.at || ''}:${index}`;

  function splitPayload(payload) {
    const chats = Array.isArray(payload?.chats) ? payload.chats : [];
    const deletedChats = Array.isArray(payload?.deletedChats)
      ? payload.deletedChats
      : Array.isArray(payload?.deleted_chats) ? payload.deleted_chats : [];
    const settings = payload?.settings && typeof payload.settings === 'object'
      ? payload.settings
      : null;
    const batchCount = Math.max(
      1,
      Math.ceil(chats.length / MAX_CHATS_PER_PUSH),
      Math.ceil(deletedChats.length / MAX_TOMBSTONES_PER_PUSH),
    );
    return Array.from({length: batchCount}, (_, index) => ({
      chats: chats.slice(index * MAX_CHATS_PER_PUSH, (index + 1) * MAX_CHATS_PER_PUSH),
      deletedChats: deletedChats.slice(
        index * MAX_TOMBSTONES_PER_PUSH,
        (index + 1) * MAX_TOMBSTONES_PER_PUSH,
      ),
      settings: index === 0 ? settings : null,
    }));
  }

  function boundedQueueEntries(payload, baseId, at) {
    const batches = splitPayload(payload);
    return batches.map((batch, index) => ({
      id: batches.length === 1 ? baseId : `${baseId}:batch:${index}`,
      at,
      payload: batch,
    }));
  }

  function normalizeQueuedEntries(queue) {
    const entries = Array.isArray(queue) ? queue : [];
    return entries.flatMap((entry, index) => boundedQueueEntries(
      entry?.payload || {},
      queueEntryId(entry, index),
      entry?.at || new Date().toISOString(),
    ));
  }

  function queueStorageFailure(flushed = false) {
    return {
      success: false,
      code: 'SYNC_QUEUE_STORAGE_FAILED',
      queued: true,
      retryable: true,
      flushed,
      error: 'Synchronization could not update its local queue. Your work remains on this device.',
    };
  }

  async function flushQueued(authBoundary = captureAuthBoundary()) {
    if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(false);
    const key = userKey(PENDING_KEY, authBoundary.userId);
    let flushed = false;
    let lastResult = { success: true, flushed: false };

    while (true) {
      if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(flushed);
      const storedQueue = read(key, []);
      const queue = normalizeQueuedEntries(Array.isArray(storedQueue) ? storedQueue : []);
      if (!queue.length) return {...lastResult, flushed};
      if (!navigator.onLine) return { success: false, queued: true, flushed };
      if (!write(key, queue)) return queueStorageFailure(flushed);

      const batch = queue[0];
      const batchId = queueEntryId(batch, 0);
      let response;
      let data;
      try {
        ({response, data} = await requestJson(
          '/api/sync/push',
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              [SYNC_OWNER_HEADER]: authBoundary.userId,
            },
            body: JSON.stringify(batch.payload),
          },
          'Invalid sync response.',
        ));
      } catch (error) {
        if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(flushed);
        return {
          success: false,
          queued: true,
          retryable: true,
          flushed,
          error: error?.message || 'Synchronization is temporarily unavailable. Your work is still queued.',
        };
      }
      if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(flushed);
      if (!response.ok || !data.success) return {...data, queued: true, flushed};

      const remaining = normalizeQueuedEntries(read(key, []))
        .filter((entry, index) => queueEntryId(entry, index) !== batchId);
      if (!write(key, remaining)) return queueStorageFailure(true);
      // A push confirms only that our write was accepted. It does not prove
      // that this device read concurrent changes, so it must never advance the
      // incremental-pull watermark.
      flushed = true;
      lastResult = data;
    }
  }

  async function flush(options = {}) {
    const authBoundary = options.authBoundary || captureAuthBoundary();
    if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(false);
    const queueKey = userKey(PENDING_KEY, authBoundary.userId);
    const key = `${queueKey}@${authBoundary.revision}`;
    if (flushPromise && flushPromiseKey === key) return flushPromise;
    if (flushPromise) {
      try { await flushPromise; } catch (_) {}
      if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(false);
      if (flushPromise && flushPromiseKey === key) return flushPromise;
    }
    const activePromise = flushQueued(authBoundary);
    flushPromise = activePromise;
    flushPromiseKey = key;
    try {
      return await activePromise;
    } finally {
      if (flushPromise === activePromise) {
        flushPromise = null;
        flushPromiseKey = null;
      }
    }
  }

  async function push(_legacyDeviceId, payload, options = {}) {
    const authBoundary = options.authBoundary || captureAuthBoundary();
    if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(false);
    const key = userKey(PENDING_KEY, authBoundary.userId);
    const queue = read(key, []);
    const at = new Date().toISOString();
    const baseId = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const merged = mergeQueue([
      ...(Array.isArray(queue) ? queue : []),
      {id: baseId, at, payload},
    ]);
    const bounded = boundedQueueEntries(merged, baseId, at);
    if (!authBoundaryIsCurrent(authBoundary)) return authBoundaryChanged(false);
    if (!write(key, bounded)) return queueStorageFailure(false);
    return flush({authBoundary});
  }

  window.addEventListener('online', () => flush().catch(console.warn));
  window.SyncManager = { pull, push, flush };
})();
