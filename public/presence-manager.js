(() => {
  'use strict';

  const EXPECTED_OWNER_HEADER = 'X-Ask-Crump-Expected-Owner';
  const LEGACY_PENDING_CHAT_KEY = 'crump_pending_chat';
  const PUSH_ACTION_CONSUMED = 'consumed';
  const PUSH_ACTION_DROP = 'drop';
  const PUSH_ACTION_DEFER = 'defer';
  const PUSH_ACTION_RETRY = 'retry';
  const DEFAULTS = Object.freeze({
    enabled: false,
    frequency: 'balanced',
    quiet_start: 21,
    quiet_end: 8,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York',
    notifications_enabled: false,
    haptics_enabled: true,
    allow_followups: true,
    allow_reminders: true,
    allow_goals: true,
    allow_encouragement: false,
  });

  let activity = null;
  let expanded = false;
  let activityTimer = null;
  let warmVerbIndex = 0;
  let warmVerbTimer = null;
  let preferences = { ...DEFAULTS };
  let preferencesOwnerId = '';
  let presenceBoundaryGeneration = 0;
  let unregisterAuthBoundary = null;
  const preferenceRequests = new Set();
  let pushRegistrationController = null;
  let pushRegistrationGeneration = 0;
  let pendingNotificationBoundary = null;
  let notificationToken = null;
  let online = navigator.onLine;
  const handledPushActionIds = new Set();
  const inFlightPushActionIds = new Set();
  let pushConsumerReady = document.documentElement?.dataset?.crumpBodyRuntime === 'ready';
  let pushRetryTimer = null;
  let pushRetryDelay = 750;
  let pushDrainPromise = null;

  const currentChat = () => (window.chats || []).find(chat => chat.id === window.currentChatId || chat.chat_id === window.currentChatId);
  const rerender = () => window.renderMessages?.(currentChat()?.messages || []);
  const announce = text => {
    const region = document.getElementById('conversationStatus');
    if (region) region.textContent = text || '';
  };

  function captureAuthBoundary(expected = null) {
    const boundary = window.CrumpAuthBoundary;
    const ownerId = String(
      expected?.ownerId
      || (typeof boundary?.authenticatedUserId === 'function'
        ? boundary.authenticatedUserId()
        : window.currentUser?.id || ''),
    ).trim();
    const rawRevision = expected?.revision
      ?? (typeof boundary?.revision === 'function' ? boundary.revision() : 0);
    const revision = Number(rawRevision);
    return Object.freeze({
      ownerId,
      revision: Number.isFinite(revision) ? revision : 0,
      generation: presenceBoundaryGeneration,
    });
  }

  function authBoundaryIsCurrent(snapshot) {
    if (!snapshot?.ownerId || snapshot.generation !== presenceBoundaryGeneration) return false;
    const current = captureAuthBoundary();
    return current.ownerId === snapshot.ownerId && current.revision === snapshot.revision;
  }

  function pushActionOwnerId(detail) {
    const action = detail?.action || detail || {};
    const values = [
      detail?.ownerId,
      action?.notification?.data?.ownerId,
      action?.data?.ownerId,
    ].map(value => String(value || '').trim().toLowerCase()).filter(Boolean);
    if (!values.length || values.some(value => value !== values[0])) return '';
    return values[0];
  }

  function authBoundaryDisposition(snapshot) {
    const current = captureAuthBoundary();
    if (!current.ownerId) return PUSH_ACTION_DEFER;
    if (current.ownerId !== snapshot?.ownerId) return PUSH_ACTION_DROP;
    return authBoundaryIsCurrent(snapshot) ? '' : PUSH_ACTION_RETRY;
  }

  function clearLegacyPendingChat() {
    try { sessionStorage.removeItem(LEGACY_PENDING_CHAT_KEY); } catch (_) {}
  }

  function newPreferenceRequest() {
    const controller = new AbortController();
    preferenceRequests.add(controller);
    return controller;
  }

  function releasePreferenceRequest(controller) {
    preferenceRequests.delete(controller);
  }

  function scrubAuthBoundary() {
    presenceBoundaryGeneration += 1;
    pushRegistrationGeneration += 1;
    pushRegistrationController?.abort?.();
    pushRegistrationController = null;
    pendingNotificationBoundary = null;
    preferenceRequests.forEach(controller => controller.abort());
    preferenceRequests.clear();
    if (pushRetryTimer) clearTimeout(pushRetryTimer);
    pushRetryTimer = null;
    pushRetryDelay = 750;
    // Let the next owner start a fresh drain. Any earlier async drain retains
    // its captured boundary and can only retry/drop after it resumes.
    pushDrainPromise = null;
    handledPushActionIds.clear();
    inFlightPushActionIds.clear();
    clearLegacyPendingChat();
    preferencesOwnerId = '';
    preferences = { ...DEFAULTS };
  }

  function ensureAuthBoundaryRegistration() {
    if (unregisterAuthBoundary || typeof window.CrumpAuthBoundary?.register !== 'function') return;
    unregisterAuthBoundary = window.CrumpAuthBoundary.register(
      'presence-preferences',
      scrubAuthBoundary,
    );
  }

  function refreshVisiblePresence({ensureLabel = false} = {}) {
    const label = labelFor(activity);
    const bubble = document.querySelector('.presence-message .presence-bubble');
    let visibleLabel = bubble?.querySelector('.presence-label') || null;
    if (!visibleLabel && ensureLabel && bubble) {
      visibleLabel = document.createElement('span');
      visibleLabel.className = 'presence-label';
      bubble.appendChild(visibleLabel);
    }
    if (visibleLabel) visibleLabel.textContent = label;
    announce(label);
  }

  function assistantName() {
    return SafeStorage.getItem(window.STORAGE_KEYS?.ASSISTANT_NAME || 'crump_assistant_name') || 'Crump';
  }

  function warmThinkingVerbs() {
    const name = assistantName();
    return [
      `${name} is thinking…`,
      `${name} is connecting the thread…`,
      `${name} is putting it together…`,
      `${name} is checking the details…`,
      `${name} is lining it up…`,
    ];
  }

  function labelFor(value) {
    const name = assistantName();
    if (value === 'thinking') {
      // Rotate warm verbs on long generations so the wait feels alive.
      const verbs = warmThinkingVerbs();
      return verbs[warmVerbIndex % verbs.length];
    }
    const labels = {
      reading: `${name} is reading…`,
      searching: `${name} is searching…`,
      creating: `${name} is creating…`,
    };
    return labels[value] || warmThinkingVerbs()[warmVerbIndex % warmThinkingVerbs().length];
  }

  function start(nextActivity = 'thinking') {
    clearTimeout(activityTimer);
    clearInterval(warmVerbTimer);
    activity = nextActivity;
    expanded = false;
    warmVerbIndex = 0;
    announce(labelFor(activity));
    rerender();
    activityTimer = setTimeout(() => {
      expanded = true;
      refreshVisiblePresence({ensureLabel: true});
    }, 2800);
    // Rotate the visible verb every few seconds while Crump works.
    warmVerbTimer = setInterval(() => {
      if (!activity) {
        clearInterval(warmVerbTimer);
        warmVerbTimer = null;
        return;
      }
      warmVerbIndex += 1;
      // The status copy can change without rebuilding every message node.
      // Keeping those nodes stable prevents image flicker and preserves the
      // viewport while a long-running response is still in progress.
      refreshVisiblePresence();
    }, 4200);
  }

  function update(nextActivity) {
    if (!activity || nextActivity === activity) return;
    activity = nextActivity;
    refreshVisiblePresence({ensureLabel: expanded});
  }

  function stop() {
    clearTimeout(activityTimer);
    activityTimer = null;
    clearInterval(warmVerbTimer);
    warmVerbTimer = null;
    warmVerbIndex = 0;
    activity = null;
    expanded = false;
    announce('');
    rerender();
  }

  function indicator() {
    if (!activity) return null;
    return { activity, expanded, label: labelFor(activity) };
  }

  function hapticsEnabled() {
    return preferences.haptics_enabled !== false;
  }

  async function haptic(kind = 'light') {
    if (!hapticsEnabled() || !window.CrumpAPI?.isNative) return;
    const native = window.CrumpNative;
    if (!native?.Haptics) return;
    try {
      if (kind === 'success' && native.NotificationType) {
        await native.Haptics.notification({ type: native.NotificationType.Success });
      } else if (kind === 'error' && native.NotificationType) {
        await native.Haptics.notification({ type: native.NotificationType.Error });
      } else {
        const style = kind === 'medium' ? native.ImpactStyle.Medium : native.ImpactStyle.Light;
        await native.Haptics.impact({ style });
      }
    } catch (_) {}
  }

  function renderConnectionState() {
    const pill = document.getElementById('connectionStatus');
    if (!pill) return;
    pill.hidden = online;
    pill.textContent = online ? '' : 'Offline — messages will wait';
    pill.setAttribute('aria-hidden', online ? 'true' : 'false');
  }

  function setOnline(value) {
    const wasOnline = online;
    online = Boolean(value);
    renderConnectionState();
    if (!wasOnline && online) {
      announce('Back online. Syncing conversations.');
    }
  }

  async function loadPreferences() {
    ensureAuthBoundaryRegistration();
    const authBoundary = captureAuthBoundary();
    if (!authBoundary.ownerId || !authBoundaryIsCurrent(authBoundary)) return { ...DEFAULTS };
    const controller = newPreferenceRequest();
    try {
      const response = await fetch('/api/presence/preferences', {
        headers: {[EXPECTED_OWNER_HEADER]: authBoundary.ownerId},
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!authBoundaryIsCurrent(authBoundary)) return { ...DEFAULTS };
      if (response.ok && data.preferences) {
        preferencesOwnerId = authBoundary.ownerId;
        preferences = { ...DEFAULTS, ...data.preferences };
      }
    } catch (_) {
      if (!authBoundaryIsCurrent(authBoundary)) return { ...DEFAULTS };
    } finally {
      releasePreferenceRequest(controller);
    }
    if (!authBoundaryIsCurrent(authBoundary)) return { ...DEFAULTS };
    applyPreferencesToForm();
    return { ...preferences };
  }

  function applyPreferencesToForm() {
    const activeOwnerId = String(window.currentUser?.id || '').trim();
    const visiblePreferences = activeOwnerId && preferencesOwnerId === activeOwnerId
      ? preferences
      : DEFAULTS;
    const map = {
      crumpCheckIns: 'enabled',
      crumpNotifications: 'notifications_enabled',
      crumpHaptics: 'haptics_enabled',
      checkInFollowups: 'allow_followups',
      checkInReminders: 'allow_reminders',
      checkInGoals: 'allow_goals',
      checkInEncouragement: 'allow_encouragement',
    };
    for (const [id, key] of Object.entries(map)) {
      const element = document.getElementById(id);
      if (element) element.checked = Boolean(visiblePreferences[key]);
    }
    const frequency = document.getElementById('checkInFrequency');
    const quietStart = document.getElementById('quietStart');
    const quietEnd = document.getElementById('quietEnd');
    if (frequency) frequency.value = visiblePreferences.frequency;
    if (quietStart) quietStart.value = String(visiblePreferences.quiet_start);
    if (quietEnd) quietEnd.value = String(visiblePreferences.quiet_end);
    updateCheckInVisibility();
  }

  function readPreferencesFromForm() {
    return {
      enabled: Boolean(document.getElementById('crumpCheckIns')?.checked),
      frequency: document.getElementById('checkInFrequency')?.value || 'balanced',
      quiet_start: Number(document.getElementById('quietStart')?.value || 21),
      quiet_end: Number(document.getElementById('quietEnd')?.value || 8),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || preferences.timezone,
      notifications_enabled: Boolean(document.getElementById('crumpNotifications')?.checked),
      haptics_enabled: Boolean(document.getElementById('crumpHaptics')?.checked),
      allow_followups: Boolean(document.getElementById('checkInFollowups')?.checked),
      allow_reminders: Boolean(document.getElementById('checkInReminders')?.checked),
      allow_goals: Boolean(document.getElementById('checkInGoals')?.checked),
      allow_encouragement: Boolean(document.getElementById('checkInEncouragement')?.checked),
    };
  }

  async function savePreferences(expectedBoundary = null) {
    ensureAuthBoundaryRegistration();
    const authBoundary = captureAuthBoundary(expectedBoundary);
    if (!authBoundary.ownerId || !authBoundaryIsCurrent(authBoundary)) {
      throw new Error('Account changed before preferences could be saved.');
    }
    const next = readPreferencesFromForm();
    if (next.notifications_enabled && !window.CrumpAPI?.isNative) {
      next.notifications_enabled = false;
      const checkbox = document.getElementById('crumpNotifications');
      if (checkbox) checkbox.checked = false;
      window.showToast?.('Push notifications are available in the iPhone and Android apps.', 'info');
    }
    if (next.notifications_enabled) {
      const granted = await enableNotifications(authBoundary);
      if (!authBoundaryIsCurrent(authBoundary)) {
        throw new Error('Account changed before preferences could be saved.');
      }
      if (!granted) {
        next.notifications_enabled = false;
        const checkbox = document.getElementById('crumpNotifications');
        if (checkbox) checkbox.checked = false;
      }
    }
    const controller = newPreferenceRequest();
    try {
      const response = await fetch('/api/presence/preferences', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          [EXPECTED_OWNER_HEADER]: authBoundary.ownerId,
        },
        body: JSON.stringify(next),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!authBoundaryIsCurrent(authBoundary)) {
        throw new Error('Account changed before preferences could be saved.');
      }
      if (!response.ok) throw new Error(data.error || 'Could not save conversation-presence settings.');
      preferencesOwnerId = authBoundary.ownerId;
      preferences = { ...DEFAULTS, ...(data.preferences || next) };
      return { ...preferences };
    } finally {
      releasePreferenceRequest(controller);
    }
  }

  function updateCheckInVisibility() {
    const enabled = Boolean(document.getElementById('crumpCheckIns')?.checked);
    const details = document.getElementById('checkInDetails');
    if (details) details.hidden = !enabled;
  }

  async function enableNotifications(expectedBoundary = null) {
    const authBoundary = captureAuthBoundary(expectedBoundary);
    if (!authBoundary.ownerId || !authBoundaryIsCurrent(authBoundary)) return false;
    const plugin = window.CrumpNative?.PushNotifications;
    if (!window.CrumpAPI?.isNative || !plugin) return false;
    try {
      let permission = await plugin.checkPermissions();
      if (!authBoundaryIsCurrent(authBoundary)) return false;
      if (permission.receive === 'prompt') permission = await plugin.requestPermissions();
      if (!authBoundaryIsCurrent(authBoundary)) return false;
      if (permission.receive !== 'granted') {
        window.showToast?.('Notifications remain off. You can enable them later in device settings.', 'warning');
        return false;
      }
      pendingNotificationBoundary = authBoundary;
      await plugin.register();
      return authBoundaryIsCurrent(authBoundary);
    } catch (error) {
      if (!authBoundaryIsCurrent(authBoundary)) return false;
      console.warn('[Push]', error);
      window.showToast?.('Push notifications could not be enabled on this device.', 'warning');
      return false;
    }
  }

  async function registerToken(token, expectedBoundary = null) {
    notificationToken = token || notificationToken;
    if (!notificationToken || !window.currentUser) return;
    const platform = window.CrumpNative?.Capacitor?.getPlatform?.() || window.Capacitor?.getPlatform?.();
    if (!['ios', 'android'].includes(platform)) return;
    const authBoundary = captureAuthBoundary(expectedBoundary);
    if (!authBoundaryIsCurrent(authBoundary)) return;
    pushRegistrationController?.abort?.();
    const controller = new AbortController();
    pushRegistrationController = controller;
    const registrationGeneration = ++pushRegistrationGeneration;
    try {
      const response = await fetch('/api/notifications/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          [EXPECTED_OWNER_HEADER]: authBoundary.ownerId,
        },
        body: JSON.stringify({
          token: notificationToken,
          platform,
          installationId: window.CrumpAPI.installationId(),
        }),
        signal: controller.signal,
      });
      if (
        registrationGeneration !== pushRegistrationGeneration
        || !authBoundaryIsCurrent(authBoundary)
      ) return;
      if (!response.ok) throw new Error('Push token registration failed.');
    } catch (error) {
      if (
        controller.signal.aborted
        || registrationGeneration !== pushRegistrationGeneration
        || !authBoundaryIsCurrent(authBoundary)
      ) return;
      console.warn('[Push] Token registration failed:', error);
    } finally {
      if (pushRegistrationController === controller) pushRegistrationController = null;
      if (
        pendingNotificationBoundary?.ownerId === authBoundary.ownerId
        && pendingNotificationBoundary?.revision === authBoundary.revision
      ) pendingNotificationBoundary = null;
    }
  }

  async function refreshAuthenticatedPresence() {
    ensureAuthBoundaryRegistration();
    const authBoundary = captureAuthBoundary();
    if (!authBoundary.ownerId || !authBoundaryIsCurrent(authBoundary)) return;
    const loaded = await loadPreferences();
    if (!authBoundaryIsCurrent(authBoundary)) return;
    if (loaded.notifications_enabled && window.CrumpAPI?.isNative) {
      await enableNotifications(authBoundary);
    }
  }

  async function openNotification(detail, authBoundary) {
    const action = detail?.action || detail || {};
    if (!authBoundary?.ownerId || pushActionOwnerId(detail) !== authBoundary.ownerId) {
      return PUSH_ACTION_DROP;
    }
    const initialDisposition = authBoundaryDisposition(authBoundary);
    if (initialDisposition) return initialDisposition;
    const notificationData = action?.notification?.data || {};
    const actionData = action?.data || {};
    const chatId = String(
      notificationData.chatId || notificationData.chat_id
      || actionData.chatId || actionData.chat_id
      || '',
    ).trim();
    if (!chatId) return PUSH_ACTION_CONSUMED;
    const findChat = () => (window.chats || []).find(chat =>
      String(chat?.id || chat?.chat_id || '') === chatId
    );
    let target = findChat();
    if (!target) {
      if (typeof window.syncChatsFromServer !== 'function') return PUSH_ACTION_RETRY;
      const result = await window.syncChatsFromServer();
      const postSyncDisposition = authBoundaryDisposition(authBoundary);
      if (postSyncDisposition) return postSyncDisposition;
      if (result?.success !== true || result?.deferred) return PUSH_ACTION_RETRY;
      target = findChat();
    }
    if (!target) {
      const missingDisposition = authBoundaryDisposition(authBoundary);
      if (missingDisposition) return missingDisposition;
      window.showToast?.('This conversation is no longer available.', 'info');
      return PUSH_ACTION_CONSUMED;
    }
    if (typeof window.loadChat !== 'function') return PUSH_ACTION_RETRY;
    const preLoadDisposition = authBoundaryDisposition(authBoundary);
    if (preLoadDisposition) return preLoadDisposition;
    const targetId = String(target.id || target.chat_id || chatId);
    const loaded = await Promise.resolve(window.loadChat(targetId, {
      ownerId: authBoundary.ownerId,
      revision: authBoundary.revision,
    }));
    const postLoadDisposition = authBoundaryDisposition(authBoundary);
    if (postLoadDisposition) return postLoadDisposition;
    if (loaded === false || String(window.currentChatId || '') !== targetId) {
      return PUSH_ACTION_RETRY;
    }
    return PUSH_ACTION_CONSUMED;
  }

  function pendingPushActions() {
    const pending = window.CrumpNative?.peekPendingPushActions?.();
    return Array.isArray(pending) ? pending : [];
  }

  function schedulePushActionRetry() {
    if (pushRetryTimer || !pendingPushActions().length || !captureAuthBoundary().ownerId) return;
    const delay = pushRetryDelay;
    const retryGeneration = presenceBoundaryGeneration;
    pushRetryDelay = Math.min(pushRetryDelay * 2, 30000);
    pushRetryTimer = setTimeout(() => {
      pushRetryTimer = null;
      if (retryGeneration !== presenceBoundaryGeneration) return;
      void consumeAllPushActions();
    }, delay);
  }

  async function consumePushAction(detail) {
    if (!pushConsumerReady) return false;
    const queueId = String(detail?.queueId || '');
    const durableIdentity = queueId && !String(detail?.dedupKey || '').includes('|navigation:');
    const actionOwnerId = pushActionOwnerId(detail);
    if (!actionOwnerId) {
      if (queueId) window.CrumpNative?.acknowledgePushAction?.(queueId);
      return true;
    }
    const authBoundary = captureAuthBoundary();
    if (!authBoundary.ownerId) return false;
    if (actionOwnerId !== authBoundary.ownerId) {
      if (queueId) window.CrumpNative?.acknowledgePushAction?.(queueId);
      return true;
    }
    if (durableIdentity && handledPushActionIds.has(queueId)) {
      window.CrumpNative?.acknowledgePushAction?.(queueId);
      return true;
    }
    if (queueId && inFlightPushActionIds.has(queueId)) return false;
    if (queueId) inFlightPushActionIds.add(queueId);
    try {
      const outcome = await openNotification(detail, authBoundary);
      if (outcome === PUSH_ACTION_DEFER) return false;
      if (outcome === PUSH_ACTION_RETRY) {
        schedulePushActionRetry();
        return false;
      }
      const consumed = outcome === PUSH_ACTION_CONSUMED || outcome === PUSH_ACTION_DROP;
      if (!consumed) return false;
      if (queueId) {
        if (durableIdentity) {
          handledPushActionIds.add(queueId);
          if (handledPushActionIds.size > 64) {
            handledPushActionIds.delete(handledPushActionIds.values().next().value);
          }
        }
        window.CrumpNative?.acknowledgePushAction?.(queueId);
      }
      pushRetryDelay = 750;
      return true;
    } catch (error) {
      console.warn('[Push] Notification handoff will retry:', error);
      schedulePushActionRetry();
      return false;
    } finally {
      if (queueId) inFlightPushActionIds.delete(queueId);
    }
  }

  async function consumePendingPushActions() {
    while (pushConsumerReady) {
      const [detail] = pendingPushActions();
      if (!detail) return true;
      const consumed = await consumePushAction(detail);
      if (!consumed) return false;
    }
    return false;
  }

  async function consumeAllPushActions() {
    if (!pushConsumerReady) return;
    if (pushDrainPromise) return pushDrainPromise;
    const drainGeneration = presenceBoundaryGeneration;
    const activeDrain = (async () => {
      while (drainGeneration === presenceBoundaryGeneration) {
        const queueDrained = await consumePendingPushActions();
        if (!queueDrained) break;
        if (!pendingPushActions().length) break;
      }
    })();
    pushDrainPromise = activeDrain;
    try {
      return await activeDrain;
    } finally {
      if (pushDrainPromise === activeDrain) pushDrainPromise = null;
      if (
        drainGeneration !== presenceBoundaryGeneration
        && captureAuthBoundary().ownerId
      ) queueMicrotask(() => { void consumeAllPushActions(); });
    }
  }

  function startPushConsumer() {
    clearLegacyPendingChat();
    pushConsumerReady = true;
    void consumeAllPushActions();
  }

  window.addEventListener('online', () => {
    setOnline(true);
    void consumeAllPushActions();
  });
  window.addEventListener('offline', () => setOnline(false));
  window.addEventListener('crump:network-status', event => {
    setOnline(event.detail?.connected);
    if (event.detail?.connected) void consumeAllPushActions();
  });
  window.addEventListener('crump:push-registration', event => {
    const expectedBoundary = pendingNotificationBoundary;
    if (expectedBoundary) void registerToken(event.detail?.value, expectedBoundary);
  });
  window.addEventListener('crump:push-action', () => { void consumeAllPushActions(); });
  window.addEventListener('crump:body-runtime-ready', startPushConsumer, { once: true });
  if (pushConsumerReady) queueMicrotask(startPushConsumer);
  document.addEventListener('change', event => {
    if (event.target?.id === 'crumpCheckIns') updateCheckInVisibility();
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      loadPreferences();
      void consumeAllPushActions();
    }
  });

  window.CrumpPresence = {
    start,
    update,
    stop,
    indicator,
    haptic,
    loadPreferences,
    savePreferences,
    applyPreferencesToForm,
    updateCheckInVisibility,
    registerToken,
    scrubAuthBoundary,
    get preferences() {
      const activeOwnerId = String(window.currentUser?.id || '').trim();
      return activeOwnerId && preferencesOwnerId === activeOwnerId
        ? { ...preferences }
        : { ...DEFAULTS };
    },
    get online() { return online; },
  };

  window.addEventListener('crump:authenticated-ready', () => {
    void refreshAuthenticatedPresence();
    void consumeAllPushActions();
  });
  window.addEventListener('crump:authentication-required', scrubAuthBoundary);
  ensureAuthBoundaryRegistration();
  clearLegacyPendingChat();
  if (captureAuthBoundary().ownerId) queueMicrotask(() => { void refreshAuthenticatedPresence(); });
  renderConnectionState();
})();
