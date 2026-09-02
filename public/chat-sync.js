(() => {
  'use strict';

  const DELETED_KEY = 'crump_deleted_chats_v4';
  const AUTO_SYNC_INTERVAL_MS = 60_000;
  const deletedKey = () => `${DELETED_KEY}:${window.currentUser?.id || 'anonymous'}`;
  let intervalId = null;
  let syncing = false;
  let syncRequested = false;
  let fullSyncRequested = false;
  let visibilityBound = false;
  let initialReconciliationPending = true;

  const toTime = value => {
    if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
    const parsed = new Date(value || 0).getTime();
    return Number.isFinite(parsed) ? parsed : 0;
  };

  const iso = value => new Date(toTime(value) || Date.now()).toISOString();

  const readDeleted = () => {
    try { return JSON.parse(localStorage.getItem(deletedKey()) || '[]'); } catch (_) { return []; }
  };

  const writeDeleted = value => {
    try { localStorage.setItem(deletedKey(), JSON.stringify(value)); } catch (_) {}
  };

  const normalizedChat = chat => ({
    id: chat.chat_id || chat.id,
    chat_id: chat.chat_id || chat.id,
    title: chat.title || 'New conversation',
    messages: Array.isArray(chat.messages) ? chat.messages : [],
    createdAt: chat.created_at || chat.createdAt || new Date().toISOString(),
    updatedAt: chat.updated_at || chat.updatedAt || chat.created_at || chat.createdAt || new Date().toISOString(),
    revision: Number(chat.revision || 1),
  });

  const isPristineChat = chat => {
    const title = String(chat?.title || 'New conversation').trim().toLowerCase();
    return (!Array.isArray(chat?.messages) || chat.messages.length === 0) &&
      (!title || title === 'new conversation');
  };

  const messageKey = (message, index = 0) => {
    const inReplyTo = message?.inReplyTo || message?.in_reply_to;
    if (message?.role === 'assistant' && inReplyTo) return `reply:${inReplyTo}`;
    if (message?.id) return `id:${message.id}`;
    return `legacy:${message?.role || ''}:${message?.timestamp || ''}:${String(message?.content || '').slice(0, 160)}:${index}`;
  };

  const deliveryRank = status => ({ sending: 1, queued: 2, failed: 2, delivered: 3, seen: 4 }[status] || 0);
  const replyRank = status => ({ pending: 1, failed: 2, processing: 3, replied: 4 }[status] || 0);

  function mergeMessage(local, server) {
    if (!local) return { ...server };
    if (!server) return { ...local };

    const localDelivery = local.deliveryStatus || local.delivery_status;
    const serverDelivery = server.deliveryStatus || server.delivery_status;
    const localReply = local.replyStatus || local.reply_status;
    const serverReply = server.replyStatus || server.reply_status;

    const merged = { ...local, ...server };
    if (deliveryRank(localDelivery) > deliveryRank(serverDelivery)) merged.deliveryStatus = localDelivery;
    if (replyRank(localReply) > replyRank(serverReply)) merged.replyStatus = localReply;

    const localDeliveryTime = toTime(local.deliveryUpdatedAt || local.delivery_updated_at);
    const serverDeliveryTime = toTime(server.deliveryUpdatedAt || server.delivery_updated_at);
    if (localDeliveryTime > serverDeliveryTime) {
      for (const field of ['deliveryUpdatedAt', 'deliveredAt', 'seenAt', 'replyError']) {
        if (local[field] !== undefined) merged[field] = local[field];
      }
    }
    return merged;
  }

  function mergeMessages(localMessages = [], serverMessages = []) {
    const byKey = new Map();
    const order = [];

    serverMessages.forEach((message, index) => {
      const key = messageKey(message, index);
      if (!byKey.has(key)) order.push(key);
      byKey.set(key, { server: message, local: null, first: index });
    });

    localMessages.forEach((message, index) => {
      const key = messageKey(message, index);
      if (!byKey.has(key)) {
        order.push(key);
        byKey.set(key, { server: null, local: message, first: serverMessages.length + index });
      } else {
        byKey.get(key).local = message;
      }
    });

    return order
      .map(key => {
        const entry = byKey.get(key);
        return { message: mergeMessage(entry.local, entry.server), first: entry.first };
      })
      .sort((a, b) => {
        const at = toTime(a.message?.timestamp);
        const bt = toTime(b.message?.timestamp);
        if (at && bt && at !== bt) return at - bt;
        return a.first - b.first;
      })
      .map(entry => entry.message);
  }

  function stableValue(value) {
    if (Array.isArray(value)) return value.map(stableValue);
    if (!value || typeof value !== 'object') return value;
    return Object.fromEntries(
      Object.keys(value).sort().map(key => [key, stableValue(value[key])]),
    );
  }

  function stableMessageSignature(messages = []) {
    return JSON.stringify(stableValue(messages));
  }

  function serverWins(server, local) {
    if (!local) return true;
    const serverTime = toTime(server.updatedAt);
    const localTime = toTime(local.updatedAt);
    if (serverTime > localTime) return true;
    if (serverTime < localTime) return false;
    return Number(server.revision || 1) > Number(local.revision || 1);
  }

  window.recordChatDeletion = chatId => {
    if (!chatId) return;
    const deleted = readDeleted().filter(item => (item.id || item.chat_id) !== chatId);
    deleted.push({ id: chatId, deletedAt: new Date().toISOString(), revision: Date.now() });
    writeDeleted(deleted.slice(-500));
  };

  function mergeServerState(serverRows, localRows) {
    const map = new Map();

    for (const local of localRows || []) {
      if (isPristineChat(local)) continue;
      const chat = normalizedChat(local);
      if (chat.id) map.set(chat.id, chat);
    }

    const deleted = readDeleted();
    const localTombstones = new Map(deleted.map(item => [item.id || item.chat_id, item]));

    for (const row of serverRows || []) {
      if (isPristineChat(row)) continue;
      const id = row.chat_id || row.id;
      if (!id) continue;

      const serverDeletedAt = row.deleted_at || row.deletedAt;
      if (serverDeletedAt) {
        const local = map.get(id);
        if (!local || toTime(serverDeletedAt) >= toTime(local.updatedAt)) map.delete(id);
        localTombstones.delete(id);
        continue;
      }

      const server = normalizedChat(row);
      const tombstone = localTombstones.get(id);
      if (tombstone && toTime(tombstone.deletedAt) >= toTime(server.updatedAt)) continue;

      const local = map.get(id);
      if (!local) {
        map.set(id, server);
        continue;
      }

      const mergedMessages = mergeMessages(local.messages, server.messages);
      const mergedDiffersFromServer = stableMessageSignature(mergedMessages) !== stableMessageSignature(server.messages);
      const winner = serverWins(server, local) ? server : local;
      const merged = {
        ...winner,
        id,
        chat_id: id,
        createdAt: toTime(local.createdAt) && toTime(local.createdAt) < toTime(server.createdAt) ? local.createdAt : server.createdAt,
        messages: mergedMessages,
        revision: Math.max(Number(local.revision || 1), Number(server.revision || 1)),
      };

      // If one device owns a message the server does not yet have (most notably
      // an assistant reply), make the merged chat a fresh revision so the next
      // push cannot be rejected as stale merely because metadata came from an
      // older in-memory chat object.
      if (mergedDiffersFromServer) {
        merged.updatedAt = new Date().toISOString();
        merged.revision += 1;
      }

      map.set(id, merged);
    }

    const merged = [...map.values()].sort((a, b) => toTime(b.updatedAt) - toTime(a.updatedAt));
    writeDeleted([...localTombstones.values()]);
    return merged;
  }

  async function pullAndMerge(prefetched = null, { full = true } = {}) {
    if (!window.currentUser || !navigator.onLine) return null;
    const result = prefetched
      ? { success: true, data: prefetched }
      : await window.SyncManager.pull(null, { full });

    if (!result?.success || !Array.isArray(result.data?.chats)) return result;

    let local = [];
    try { local = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]'); } catch (_) {}

    const previous = Array.isArray(window.chats) ? window.chats : local;
    const activeId = String(window.currentChatId || '');
    const previousActive = previous.find(chat => String(chat?.id || chat?.chat_id || '') === activeId);
    const merged = mergeServerState(result.data.chats, local);
    const nextActive = merged.find(chat => String(chat?.id || chat?.chat_id || '') === activeId);
    const preserveActiveRender = Boolean(
      activeId
      && previousActive
      && nextActive
      && String(previousActive.title || '') === String(nextActive.title || '')
      && stableMessageSignature(previousActive.messages) === stableMessageSignature(nextActive.messages)
    );
    window.chats = merged;

    if (typeof window.replaceChats === 'function') {
      window.replaceChats(merged, {preserveActiveRender});
    }
    else SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(merged));

    if (typeof window.renderChatsList === 'function') window.renderChatsList();
    return result;
  }

  async function pushLocal() {
    if (!window.currentUser) return { success: false, offline: true };

    let local = [];
    try { local = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]'); } catch (_) {}

    const payload = {
      chats: local.filter(chat => !isPristineChat(chat)).map(chat => ({
        chat_id: chat.chat_id || chat.id,
        title: chat.title || 'New conversation',
        messages: Array.isArray(chat.messages) ? chat.messages : [],
        created_at: iso(chat.createdAt || chat.created_at),
        updated_at: iso(chat.updatedAt || chat.updated_at),
        revision: Number(chat.revision || 1),
      })),
      deletedChats: readDeleted(),
    };

    if (!payload.chats.length && !payload.deletedChats.length) return { success: true, skipped: true };
    const result = await window.SyncManager.push(null, payload);
    if (result?.success) writeDeleted([]);
    return result;
  }

  async function synchronize(prefetched = null, { full = true, reconcileLocal = false } = {}) {
    if (!window.currentUser || !navigator.onLine) return { success: false, offline: true };
    if (syncing) {
      syncRequested = true;
      fullSyncRequested = fullSyncRequested || full;
      return { success: true, deferred: true };
    }

    syncing = true;
    let firstPrefetch = prefetched;
    let nextFull = full;
    let lastResult = { success: true };

    try {
      do {
        syncRequested = false;
        fullSyncRequested = false;
        const snapshot = firstPrefetch;
        if (snapshot) await pullAndMerge(snapshot, { full: true });
        firstPrefetch = null;
        const flushResult = await window.SyncManager.flush?.() || { success: true, flushed: false };
        if (flushResult.success === false) return flushResult;
        if (!snapshot || flushResult.flushed) {
          lastResult = await pullAndMerge(null, { full: nextFull || flushResult.flushed }) || flushResult;
        } else {
          lastResult = flushResult;
        }
        if (reconcileLocal) {
          const reconciliation = await pushLocal();
          if (reconciliation?.success === false) return reconciliation;
          lastResult = reconciliation || lastResult;
          if (Array.isArray(reconciliation?.ignored) && reconciliation.ignored.length) {
            lastResult = await pullAndMerge(null, { full: true }) || lastResult;
          }
          reconcileLocal = false;
        }
        nextFull = fullSyncRequested;
      } while (syncRequested);
      return lastResult;
    } catch (error) {
      console.warn('[Sync] Synchronization failed:', error);
      return { success: false, error: error?.message || 'Synchronization failed.' };
    } finally {
      syncing = false;
    }
  }

  window.syncChatsFromServer = () => {
    const prefetched = window.__crumpSyncData || null;
    window.__crumpSyncData = null;
    const reconcileLocal = initialReconciliationPending;
    initialReconciliationPending = false;
    return synchronize(prefetched, { full: true, reconcileLocal }).then(result => {
      if (result?.success === false) initialReconciliationPending = true;
      return result;
    });
  };

  // Explicit saves are push-only. Pulling here can replace app.js's live chat
  // object while an AI reply is in flight, leaving the reply attached to a
  // stale object. The database merge function is authoritative and lossless,
  // while the visible-tab synchronizer flushes only queued writes and then
  // performs one incremental pull.
  window.syncChatsToServer = () => pushLocal();

  window.startAutoSync = () => {
    clearInterval(intervalId);
    intervalId = setInterval(() => {
      if (!document.hidden) synchronize(null, { full: false });
    }, AUTO_SYNC_INTERVAL_MS);
    if (!visibilityBound) {
      visibilityBound = true;
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) synchronize(null, { full: false });
      });
    }
  };
  window.stopAutoSync = () => {
    clearInterval(intervalId);
    intervalId = null;
  };
  window.addEventListener('online', () => synchronize(null, { full: false }));
})();
