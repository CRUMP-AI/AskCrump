(() => {
  'use strict';
  const PENDING_KEY = 'crump_sync_queue_v4';
  const SYNC_KEY = 'crump_last_sync_v4';
  const SYNC_REQUEST_TIMEOUT_MS = 12_000;
  let flushPromise = null;
  let flushPromiseKey = null;

  const read = (key, fallback) => {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_) { return fallback; }
  };
  const write = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
  };
  const userKey = key => `${key}:${window.currentUser?.id || 'anonymous'}`;

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
    const full = options.full !== false;
    const since = full ? null : read(userKey(SYNC_KEY), null);
    const url = since ? `/api/sync/pull?since=${encodeURIComponent(since)}` : '/api/sync/pull';
    const {response, data} = await requestJson(
      url,
      {method: 'GET'},
      'Invalid sync response.',
    );
    if (response.ok && data.success) write(userKey(SYNC_KEY), data.serverTime || new Date().toISOString());
    return data;
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
        chats.set(id, chat);
      }
      for (const tombstone of payload.deletedChats || []) {
        const value = typeof tombstone === 'string' ? { id: tombstone } : tombstone;
        const id = value?.chat_id || value?.id;
        if (!id) continue;
        deleted.set(id, value);
        chats.delete(id);
      }
      if (payload.settings && typeof payload.settings === 'object') settings = payload.settings;
    }
    return { chats: [...chats.values()], deletedChats: [...deleted.values()], settings };
  }

  const queueEntryId = (entry, index) => entry?.id || `legacy:${entry?.at || ''}:${index}`;

  async function flushQueued() {
    if (!window.currentUser) return { success: false, queued: true, flushed: false };
    const key = userKey(PENDING_KEY);
    let flushed = false;
    let lastResult = { success: true, flushed: false };

    while (true) {
      const queue = read(key, []);
      if (!queue.length) return {...lastResult, flushed};
      if (!navigator.onLine) return { success: false, queued: true, flushed };

      const batchIds = new Set(queue.map(queueEntryId));
      let response;
      let data;
      try {
        ({response, data} = await requestJson(
          '/api/sync/push',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(mergeQueue(queue)),
          },
          'Invalid sync response.',
        ));
      } catch (error) {
        return {
          success: false,
          queued: true,
          retryable: true,
          flushed,
          error: error?.message || 'Synchronization is temporarily unavailable. Your work is still queued.',
        };
      }
      if (!response.ok || !data.success) return {...data, queued: true, flushed};

      const remaining = read(key, []).filter((entry, index) => !batchIds.has(queueEntryId(entry, index)));
      write(key, remaining);
      write(userKey(SYNC_KEY), data.serverTime || new Date().toISOString());
      flushed = true;
      lastResult = data;
    }
  }

  async function flush() {
    const key = userKey(PENDING_KEY);
    if (flushPromise && flushPromiseKey === key) return flushPromise;
    if (flushPromise) {
      try { await flushPromise; } catch (_) {}
      if (flushPromise && flushPromiseKey === key) return flushPromise;
    }
    const activePromise = flushQueued();
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

  async function push(_legacyDeviceId, payload) {
    const key = userKey(PENDING_KEY);
    const queue = read(key, []);
    queue.push({
      id: crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      at: new Date().toISOString(),
      payload,
    });
    write(key, queue.slice(-100));
    return flush();
  }

  window.addEventListener('online', () => flush().catch(console.warn));
  window.SyncManager = { pull, push, flush };
})();
