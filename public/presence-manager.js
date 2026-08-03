(() => {
  'use strict';

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
  let preferences = { ...DEFAULTS };
  let notificationToken = null;
  let online = navigator.onLine;

  const currentChat = () => (window.chats || []).find(chat => chat.id === window.currentChatId || chat.chat_id === window.currentChatId);
  const rerender = () => window.renderMessages?.(currentChat()?.messages || []);
  const announce = text => {
    const region = document.getElementById('conversationStatus');
    if (region) region.textContent = text || '';
  };

  function labelFor(value) {
    const name = SafeStorage.getItem(window.STORAGE_KEYS?.ASSISTANT_NAME || 'crump_assistant_name') || 'Crump';
    const labels = {
      reading: `${name} is reading…`,
      searching: `${name} is searching…`,
      creating: `${name} is creating…`,
      thinking: `${name} is thinking…`,
    };
    return labels[value] || labels.thinking;
  }

  function start(nextActivity = 'thinking') {
    clearTimeout(activityTimer);
    activity = nextActivity;
    expanded = false;
    announce(labelFor(activity));
    rerender();
    activityTimer = setTimeout(() => {
      expanded = true;
      rerender();
    }, 2800);
  }

  function update(nextActivity) {
    if (!activity || nextActivity === activity) return;
    activity = nextActivity;
    announce(labelFor(activity));
    rerender();
  }

  function stop() {
    clearTimeout(activityTimer);
    activityTimer = null;
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
      window.syncChatsFromServer?.();
    }
  }

  async function loadPreferences() {
    if (!window.currentUser) return preferences;
    try {
      const response = await fetch('/api/presence/preferences');
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.preferences) preferences = { ...DEFAULTS, ...data.preferences };
    } catch (_) {}
    applyPreferencesToForm();
    return preferences;
  }

  function applyPreferencesToForm() {
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
      if (element) element.checked = Boolean(preferences[key]);
    }
    const frequency = document.getElementById('checkInFrequency');
    const quietStart = document.getElementById('quietStart');
    const quietEnd = document.getElementById('quietEnd');
    if (frequency) frequency.value = preferences.frequency;
    if (quietStart) quietStart.value = String(preferences.quiet_start);
    if (quietEnd) quietEnd.value = String(preferences.quiet_end);
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

  async function savePreferences() {
    const next = readPreferencesFromForm();
    if (next.notifications_enabled && !window.CrumpAPI?.isNative) {
      next.notifications_enabled = false;
      const checkbox = document.getElementById('crumpNotifications');
      if (checkbox) checkbox.checked = false;
      window.showToast?.('Push notifications are available in the iPhone and Android apps.', 'info');
    }
    if (next.notifications_enabled) {
      const granted = await enableNotifications();
      if (!granted) {
        next.notifications_enabled = false;
        const checkbox = document.getElementById('crumpNotifications');
        if (checkbox) checkbox.checked = false;
      }
    }
    const response = await fetch('/api/presence/preferences', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(next),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Could not save conversation-presence settings.');
    preferences = { ...DEFAULTS, ...(data.preferences || next) };
    return preferences;
  }

  function updateCheckInVisibility() {
    const enabled = Boolean(document.getElementById('crumpCheckIns')?.checked);
    const details = document.getElementById('checkInDetails');
    if (details) details.hidden = !enabled;
  }

  async function enableNotifications() {
    const plugin = window.CrumpNative?.PushNotifications;
    if (!window.CrumpAPI?.isNative || !plugin) return false;
    try {
      let permission = await plugin.checkPermissions();
      if (permission.receive === 'prompt') permission = await plugin.requestPermissions();
      if (permission.receive !== 'granted') {
        window.showToast?.('Notifications remain off. You can enable them later in device settings.', 'warning');
        return false;
      }
      await plugin.register();
      return true;
    } catch (error) {
      console.warn('[Push]', error);
      window.showToast?.('Push notifications could not be enabled on this device.', 'warning');
      return false;
    }
  }

  async function registerToken(token) {
    notificationToken = token || notificationToken;
    if (!notificationToken || !window.currentUser) return;
    const platform = window.CrumpNative?.Capacitor?.getPlatform?.() || window.Capacitor?.getPlatform?.();
    if (!['ios', 'android'].includes(platform)) return;
    try {
      await fetch('/api/notifications/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: notificationToken,
          platform,
          installationId: window.CrumpAPI.installationId(),
        }),
      });
    } catch (error) {
      console.warn('[Push] Token registration failed:', error);
    }
  }

  async function openNotification(detail) {
    const data = detail?.notification?.data || detail?.data || {};
    const chatId = data.chatId || data.chat_id;
    if (!chatId) return;
    try { sessionStorage.setItem('crump_pending_chat', chatId); } catch (_) {}
    await window.syncChatsFromServer?.();
    setTimeout(() => window.loadChat?.(chatId), 450);
  }

  window.addEventListener('online', () => setOnline(true));
  window.addEventListener('offline', () => setOnline(false));
  window.addEventListener('crump:network-status', event => setOnline(event.detail?.connected));
  window.addEventListener('crump:push-registration', event => registerToken(event.detail?.value));
  window.addEventListener('crump:push-action', event => openNotification(event.detail));
  document.addEventListener('change', event => {
    if (event.target?.id === 'crumpCheckIns') updateCheckInVisibility();
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      loadPreferences();
      const pending = sessionStorage.getItem('crump_pending_chat');
      if (pending) {
        sessionStorage.removeItem('crump_pending_chat');
        setTimeout(() => window.loadChat?.(pending), 300);
      }
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
    get preferences() { return { ...preferences }; },
    get online() { return online; },
  };

  renderConnectionState();
})();
