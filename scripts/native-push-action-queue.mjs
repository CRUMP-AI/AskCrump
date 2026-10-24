export const NATIVE_PUSH_ACTION_STORAGE_KEY = 'crump_native_push_actions_v2';

const STATE_VERSION = 2;
const DEFAULT_LIMIT = 16;
const ACKNOWLEDGED_LIMIT = 64;
const DEFAULT_FALLBACK_DEDUP_WINDOW_MS = 10_000;
const OWNER_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function safeString(value) {
  if (value === null || value === undefined) return '';
  return String(value).trim();
}

function safeOwnerId(value) {
  const normalized = safeString(value);
  return OWNER_ID_PATTERN.test(normalized) ? normalized.toLowerCase() : '';
}

function canonicalValue(value, seen = new WeakSet()) {
  if (value === null || ['boolean', 'number', 'string'].includes(typeof value)) return value;
  if (Array.isArray(value)) return value.map(item => canonicalValue(item, seen));
  if (!value || typeof value !== 'object' || seen.has(value)) return null;
  seen.add(value);
  const result = {};
  for (const key of Object.keys(value).sort()) {
    const normalized = canonicalValue(value[key], seen);
    if (normalized !== undefined) result[key] = normalized;
  }
  seen.delete(value);
  return result;
}

function stableHash(value) {
  const source = JSON.stringify(canonicalValue(value));
  let hash = 0x811c9dc5;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36);
}

function safeNavigationData(value) {
  if (!value || typeof value !== 'object') return {};
  const result = {};
  for (const key of ['ownerId', 'chatId', 'chat_id', 'checkInId', 'check_in_id']) {
    const normalized = key === 'ownerId' ? safeOwnerId(value[key]) : safeString(value[key]);
    if (normalized) result[key] = normalized;
  }
  return result;
}

export function nativePushActionOwnerId(action) {
  const source = action && typeof action === 'object' ? action : {};
  const notificationOwner = safeOwnerId(source.notification?.data?.ownerId);
  const actionOwner = safeOwnerId(source.data?.ownerId);
  if (notificationOwner && actionOwner && notificationOwner !== actionOwner) return '';
  return notificationOwner || actionOwner;
}

function retainedAction(action) {
  const source = action && typeof action === 'object' ? action : {};
  const notification = source.notification && typeof source.notification === 'object'
    ? source.notification
    : {};
  const result = {
    actionId: safeString(source.actionId),
    notification: {
      id: safeString(notification.id),
      data: safeNavigationData(notification.data),
    },
    data: safeNavigationData(source.data),
  };
  return Object.freeze({
    ...result,
    notification: Object.freeze(result.notification),
    data: Object.freeze(result.data),
  });
}

export function nativePushActionDedupKey(action) {
  const source = action && typeof action === 'object' ? action : {};
  const ownerId = nativePushActionOwnerId(source);
  if (!ownerId) return '';
  const notificationId = safeString(source.notification?.id);
  const actionId = safeString(source.actionId) || 'tap';
  if (notificationId) return `owner:${ownerId}|notification:${notificationId}|action:${actionId}`;
  const notificationData = safeNavigationData(source.notification?.data);
  const actionData = safeNavigationData(source.data);
  const checkInId = notificationData.checkInId || notificationData.check_in_id
    || actionData.checkInId || actionData.check_in_id;
  if (checkInId) return `owner:${ownerId}|check-in:${checkInId}|action:${actionId}`;
  const navigationIdentity = {
    actionId,
    notification: notificationData,
    data: actionData,
  };
  return `owner:${ownerId}|navigation:${stableHash(navigationIdentity)}|action:${actionId}`;
}

function isFallbackDedupKey(value) {
  return safeString(value).includes('|navigation:');
}

function defaultStorage() {
  try {
    return globalThis.sessionStorage || null;
  } catch (_) {
    return null;
  }
}

function readState(storage, storageKey) {
  if (!storage?.getItem) return { pending: [], acknowledged: [], recentNavigation: [] };
  try {
    const parsed = JSON.parse(storage.getItem(storageKey) || 'null');
    if (parsed?.version !== STATE_VERSION) {
      return { pending: [], acknowledged: [], recentNavigation: [] };
    }
    const pending = Array.isArray(parsed.pending)
      ? parsed.pending.flatMap(entry => {
        if (!entry?.action) return [];
        const action = retainedAction(entry.action);
        const ownerId = nativePushActionOwnerId(action);
        const dedupKey = nativePushActionDedupKey(action);
        const queueId = dedupKey ? `crump-native-push-${stableHash(dedupKey)}` : '';
        if (!ownerId || safeOwnerId(entry.ownerId) !== ownerId) return [];
        if (safeString(entry.dedupKey) !== dedupKey || safeString(entry.queueId) !== queueId) return [];
        return [{ ownerId, queueId, dedupKey, action }];
      })
      : [];
    const acknowledged = Array.isArray(parsed.acknowledged)
      ? parsed.acknowledged.filter(value => (
        typeof value === 'string' && value.startsWith('owner:')
      ))
      : [];
    const recentNavigation = Array.isArray(parsed.recentNavigation)
      ? parsed.recentNavigation.filter(entry => (
        typeof entry?.dedupKey === 'string'
        && entry.dedupKey.startsWith('owner:')
        && isFallbackDedupKey(entry.dedupKey)
        && Number.isFinite(Number(entry.expiresAt))
      ))
      : [];
    return { pending, acknowledged, recentNavigation };
  } catch (_) {
    return { pending: [], acknowledged: [], recentNavigation: [] };
  }
}

export function createNativePushActionQueue(options = DEFAULT_LIMIT) {
  const settings = typeof options === 'number' ? { limit: options } : (options || {});
  const maximum = Math.max(1, Math.floor(Number(settings.limit) || DEFAULT_LIMIT));
  const storage = settings.storage === undefined ? defaultStorage() : settings.storage;
  const storageKey = safeString(settings.storageKey) || NATIVE_PUSH_ACTION_STORAGE_KEY;
  const now = typeof settings.now === 'function' ? settings.now : Date.now;
  const fallbackDedupWindowMs = Math.max(
    1_000,
    Math.floor(Number(settings.fallbackDedupWindowMs) || DEFAULT_FALLBACK_DEDUP_WINDOW_MS),
  );
  const restored = readState(storage, storageKey);
  const pending = restored.pending.slice(-maximum).map(entry => ({
    ownerId: safeOwnerId(entry.ownerId),
    queueId: safeString(entry.queueId),
    dedupKey: safeString(entry.dedupKey),
    action: retainedAction(entry.action),
  }));
  const acknowledged = restored.acknowledged.slice(-ACKNOWLEDGED_LIMIT);
  const recentNavigation = restored.recentNavigation.slice(-ACKNOWLEDGED_LIMIT);

  function pruneRecentNavigation() {
    const currentTime = Number(now());
    for (let index = recentNavigation.length - 1; index >= 0; index -= 1) {
      if (Number(recentNavigation[index].expiresAt) <= currentTime) {
        recentNavigation.splice(index, 1);
      }
    }
  }

  function persist() {
    if (!storage?.setItem) return;
    try {
      storage.setItem(storageKey, JSON.stringify({
        version: STATE_VERSION,
        pending,
        acknowledged,
        recentNavigation,
      }));
    } catch (_) {}
  }

  function peek() {
    return pending.map(entry => Object.freeze({
      ownerId: entry.ownerId,
      queueId: entry.queueId,
      dedupKey: entry.dedupKey,
      action: retainedAction(entry.action),
    }));
  }

  function retain(action) {
    const ownerId = nativePushActionOwnerId(action);
    if (!ownerId) return null;
    const dedupKey = nativePushActionDedupKey(action);
    pruneRecentNavigation();
    if (acknowledged.includes(dedupKey)
        || recentNavigation.some(entry => entry.dedupKey === dedupKey)) return null;
    const existing = pending.find(entry => entry.dedupKey === dedupKey);
    if (existing) return peek().find(entry => entry.queueId === existing.queueId) || null;

    const queueId = `crump-native-push-${stableHash(dedupKey)}`;
    const entry = {
      ownerId,
      queueId,
      dedupKey,
      action: retainedAction(action),
    };
    pending.push(entry);
    if (pending.length > maximum) pending.splice(0, pending.length - maximum);
    persist();
    return peek().find(item => item.queueId === queueId) || null;
  }

  function acknowledge(queueId) {
    const normalized = safeString(queueId);
    const index = pending.findIndex(entry => entry.queueId === normalized);
    if (index < 0) return false;
    const [entry] = pending.splice(index, 1);
    if (isFallbackDedupKey(entry.dedupKey)) {
      pruneRecentNavigation();
      recentNavigation.push({
        dedupKey: entry.dedupKey,
        expiresAt: Number(now()) + fallbackDedupWindowMs,
      });
      if (recentNavigation.length > ACKNOWLEDGED_LIMIT) {
        recentNavigation.splice(0, recentNavigation.length - ACKNOWLEDGED_LIMIT);
      }
    } else if (!acknowledged.includes(entry.dedupKey)) {
      acknowledged.push(entry.dedupKey);
    }
    if (acknowledged.length > ACKNOWLEDGED_LIMIT) {
      acknowledged.splice(0, acknowledged.length - ACKNOWLEDGED_LIMIT);
    }
    persist();
    return true;
  }

  persist();
  return Object.freeze({ retain, acknowledge, peek, drain: peek });
}
