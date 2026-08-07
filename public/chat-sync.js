(() => {
  'use strict';

  const DELETED_KEY = 'crump_deleted_chats_v4';
  const deletedKey = () => `${DELETED_KEY}:${window.currentUser?.id || 'anonymous'}`;
  let intervalId = null;
  let syncing = false;

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

  // Match the database's compare-and-apply rule exactly:
  // 1) newer updatedAt wins;
  // 2) revision only breaks an exact timestamp tie.
  //
  // The previous client used:
  //   server.updatedAt > local.updatedAt || server.revision > local.revision
  // which allowed an OLDER server snapshot with a higher server-side revision
  // to erase a newer local assistant reply during the next pull.
  function serverWins(server, local) {
    if (!local) return true;
    const serverTime = toTime(server.updatedAt);
    const localTime = toTime(local.updatedAt);
    if (serverTime > localTime) return true;
    if (serverTime < localTime) return false;
    return Number(server.revision || 1) > Number(local.revision || 1);
  }

  // Extra guard for an in-flight local turn. If the local browser has a newer
  // message that has not yet appeared in the server copy, never discard it.
  function hasNewerLocalTurn(local, server) {
    const localMessages = Array.isArray(local?.messages) ? local.messages : [];
    const serverMessages = Array.isArray(server?.messages) ? server.messages : [];
    if (!localMessages.length || localMessages.length <= serverMessages.length) return false;

    const serverIds = new Set(serverMessages.map(message => message?.id).filter(Boolean));
    return localMessages.some(message => {
      if (!message?.id || serverIds.has(message.id)) return false;
      return toTime(message.timestamp) >= toTime(server.updatedAt);
    });
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
      const chat = normalizedChat(local);
      if (chat.id) map.set(chat.id, chat);
    }

    const deleted = readDeleted();
    const localTombstones = new Map(deleted.map(item => [item.id || item.chat_id, item]));

    for (const row of serverRows || []) {
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
      if (hasNewerLocalTurn(local, server)) continue;
      if (serverWins(server, local)) map.set(id, server);
    }

    const merged = [...map.values()].sort((a, b) => toTime(b.updatedAt) - toTime(a.updatedAt));
    writeDeleted([...localTombstones.values()]);
    return merged;
  }

  async function pullAndMerge(prefetched = null) {
    if (!window.currentUser || !navigator.onLine) return;
    const result = prefetched
      ? { success: true, data: prefetched }
      : await window.SyncManager.pull(null, { full: true });

    if (!result?.success || !Array.isArray(result.data?.chats)) return;

    let local = [];
    try { local = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]'); } catch (_) {}

    const merged = mergeServerState(result.data.chats, local);
    window.chats = merged;

    if (typeof window.replaceChats === 'function') window.replaceChats(merged);
    else SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(merged));

    if (typeof window.renderChatsList === 'function') window.renderChatsList();
  }

  async function pushLocal() {
    if (!window.currentUser) return;

    let local = [];
    try { local = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]'); } catch (_) {}

    const payload = {
      chats: local.map(chat => ({
        chat_id: chat.chat_id || chat.id,
        title: chat.title || 'New conversation',
        messages: Array.isArray(chat.messages) ? chat.messages : [],
        created_at: iso(chat.createdAt || chat.created_at),
        updated_at: iso(chat.updatedAt || chat.updated_at),
        revision: Number(chat.revision || 1),
      })),
      deletedChats: readDeleted(),
    };

    const result = await window.SyncManager.push(null, payload);
    if (result?.success) writeDeleted([]);
    return result;
  }

  async function synchronize(prefetched = null) {
    if (syncing || !window.currentUser || !navigator.onLine) return;
    syncing = true;

    try {
      // Pull first so stale local state never overwrites a genuinely newer device.
      await pullAndMerge(prefetched);
      await pushLocal();
      await pullAndMerge();
    } catch (error) {
      console.warn('[Sync] Synchronization failed:', error);
    } finally {
      syncing = false;
    }
  }

  window.syncChatsFromServer = () => synchronize(window.__crumpSyncData || null);
  window.syncChatsToServer = pushLocal;
  window.startAutoSync = () => {
    clearInterval(intervalId);
    intervalId = setInterval(() => synchronize(), 60_000);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) synchronize();
    });
  };
  window.stopAutoSync = () => clearInterval(intervalId);
  window.addEventListener('online', () => synchronize());
})();
