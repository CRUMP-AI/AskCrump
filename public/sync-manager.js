(function () {
  const LAST_SYNC_KEY = 'crump_last_sync_at';
  const PENDING_PUSH_KEY = 'crump_pending_push';

  function nowIso() { return new Date().toISOString(); }

  function safeGet(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  }
  function safeSet(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
  }

  async function pull(deviceId) {
    const since = safeGet(LAST_SYNC_KEY, null);
    const url = since ? `/api/sync/pull?since=${encodeURIComponent(since)}` : `/api/sync/pull`;

    const res = await fetch(url, {
      method: 'GET',
      credentials: 'include',
      headers: deviceId ? { 'x-device-id': deviceId } : {}
    });
    const data = await res.json();
    if (!data.success) return data;

    // update local cache
    safeSet(LAST_SYNC_KEY, data.serverTime || nowIso());
    return data;
  }

  async function push(deviceId, payload) {
    // queue payload (offline safe)
    const queue = safeGet(PENDING_PUSH_KEY, []);
    queue.push({ at: nowIso(), payload });
    safeSet(PENDING_PUSH_KEY, queue);

    // flush queue
    const current = safeGet(PENDING_PUSH_KEY, []);
    if (!current.length) return { success: true };

    const merged = mergeQueue(current);

    const res = await fetch('/api/sync/push', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(deviceId ? { 'x-device-id': deviceId } : {})
      },
      body: JSON.stringify(merged)
    });

    const data = await res.json();
    if (data.success) {
      safeSet(PENDING_PUSH_KEY, []);
      safeSet(LAST_SYNC_KEY, data.serverTime || nowIso());
    }
    return data;
  }

  // Merge queued payloads into 1 push (simple last-write wins)
  function mergeQueue(queue) {
    const out = { chats: [], settings: null };

    // chats: keep last version per chat_id
    const chatMap = new Map();

    for (const item of queue) {
      const p = item.payload || {};
      const chats = p.chats || [];
      for (const c of chats) {
        if (!c) continue;
        const key = c.chat_id || c.id;
        if (!key) continue;
        chatMap.set(key, c);
      }
      if (p.settings) out.settings = p.settings;
    }

    out.chats = Array.from(chatMap.values());
    return out;
  }

  window.SyncManager = {
    pull,
    push
  };
})();
