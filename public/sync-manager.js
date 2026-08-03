(() => {
  'use strict';
  const PENDING_KEY = 'crump_sync_queue_v4';
  const SYNC_KEY = 'crump_last_sync_v4';

  const read = (key, fallback) => {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_) { return fallback; }
  };
  const write = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
  };
  const userKey = key => `${key}:${window.currentUser?.id || 'anonymous'}`;

  async function pull(_legacyDeviceId, options = {}) {
    const full = options.full !== false;
    const since = full ? null : read(userKey(SYNC_KEY), null);
    const url = since ? `/api/sync/pull?since=${encodeURIComponent(since)}` : '/api/sync/pull';
    const response = await fetch(url, { method: 'GET' });
    const data = await response.json().catch(() => ({ success: false, error: 'Invalid sync response.' }));
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

  async function flush() {
    if (!navigator.onLine || !window.currentUser) return { success: false, queued: true };
    const key = userKey(PENDING_KEY);
    const queue = read(key, []);
    if (!queue.length) return { success: true };
    const response = await fetch('/api/sync/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(mergeQueue(queue)),
    });
    const data = await response.json().catch(() => ({ success: false, error: 'Invalid sync response.' }));
    if (response.ok && data.success) {
      write(key, []);
      write(userKey(SYNC_KEY), data.serverTime || new Date().toISOString());
    }
    return data;
  }

  async function push(_legacyDeviceId, payload) {
    const key = userKey(PENDING_KEY);
    const queue = read(key, []);
    queue.push({ at: new Date().toISOString(), payload });
    write(key, queue.slice(-100));
    return flush();
  }

  window.addEventListener('online', () => flush().catch(console.warn));
  window.SyncManager = { pull, push, flush };
})();
