(() => {
  'use strict';

  if (window.__crump44Loaded) return;
  window.__crump44Loaded = true;

  const DEFAULTS = Object.freeze({
    intelligenceMode: 'auto',
    memoryEnabled: true,
    autoLearn: true,
    autoTools: true,
    verificationLevel: 'auto',
  });
  const PLAN_OPEN_TIMEOUT_MS = 15_000;

  const originalFetch = window.fetch.bind(window);
  let state = { ...DEFAULTS };
  let hydratedUserId = null;
  let panel = null;
  let memoryViewOpen = false;
  let advancedOpen = false;
  let statusData = null;
  let entitlements = { thinkLonger: false, minimumTier: 'professional' };
  let planOpenPending = false;
  let hydratedPrivateChatId = null;
  let privateMutationRevision = 0;
  let preferenceMutationRevision = 0;

  const $ = (selector, root = document) => root.querySelector(selector);

  function assistantName() {
    return String(window.getAssistantName?.() || 'Crump').trim() || 'Crump';
  }

  function applyEntitlements(value) {
    if (!value || typeof value !== 'object') return;
    entitlements = {
      ...entitlements,
      thinkLonger: value.thinkLonger === true,
      minimumTier: String(value.minimumTier || 'professional'),
    };
    normalizeEntitledState();
  }

  function normalizeEntitledState() {
    if (entitlements.thinkLonger) return;
    if (state.intelligenceMode === 'deep') state.intelligenceMode = 'auto';
    if (state.verificationLevel === 'strict') state.verificationLevel = 'auto';
  }

  function cleanUserId() {
    return String(window.currentUser?.id || 'guest').replace(/[^a-zA-Z0-9_-]/g, '');
  }

  function preferenceKey() {
    return `crump_intelligence_v44:${cleanUserId() || 'guest'}`;
  }

  function preferencePendingKey() {
    return `crump_intelligence_pending_v44:${cleanUserId() || 'guest'}`;
  }

  function privateKey() {
    return `crump_private_chats_v44:${cleanUserId() || 'guest'}`;
  }

  function privatePendingKey() {
    return `crump_private_chat_pending_v44:${cleanUserId() || 'guest'}`;
  }

  function readJSON(key, fallback) {
    try {
      const value = JSON.parse(localStorage.getItem(key) || 'null');
      return value ?? fallback;
    } catch (_) {
      return fallback;
    }
  }

  function saveLocalState() {
    try {
      localStorage.setItem(preferenceKey(), JSON.stringify(state));
    } catch (_) {}
  }

  function preferencePayload(value = state) {
    return {
      intelligenceMode: ['auto', 'fast', 'deep'].includes(value?.intelligenceMode)
        ? value.intelligenceMode
        : 'auto',
      memoryEnabled: value?.memoryEnabled === true,
      autoLearn: value?.autoLearn === true,
      autoTools: value?.autoTools === true,
      verificationLevel: ['off', 'auto', 'strict'].includes(value?.verificationLevel)
        ? value.verificationLevel
        : 'auto',
    };
  }

  function pendingPreferenceState() {
    const value = readJSON(preferencePendingKey(), null);
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    if (
      !['auto', 'fast', 'deep'].includes(value.intelligenceMode)
      || typeof value.memoryEnabled !== 'boolean'
      || typeof value.autoLearn !== 'boolean'
      || typeof value.autoTools !== 'boolean'
      || !['off', 'auto', 'strict'].includes(value.verificationLevel)
    ) {
      try {
        localStorage.removeItem(preferencePendingKey());
      } catch (_) {}
      return null;
    }
    return preferencePayload(value);
  }

  function writePendingPreferenceState(value) {
    try {
      localStorage.setItem(preferencePendingKey(), JSON.stringify(preferencePayload(value)));
    } catch (_) {}
  }

  function clearPendingPreferenceState(expected) {
    const current = pendingPreferenceState();
    if (!current || JSON.stringify(current) !== JSON.stringify(preferencePayload(expected))) return;
    try {
      localStorage.removeItem(preferencePendingKey());
    } catch (_) {}
  }

  function loadLocalState() {
    const saved = readJSON(preferenceKey(), {});
    state = {
      ...DEFAULTS,
      ...(saved && typeof saved === 'object' ? saved : {}),
    };
    if (!['auto', 'fast', 'deep'].includes(state.intelligenceMode)) state.intelligenceMode = 'auto';
    if (!['off', 'auto', 'strict'].includes(state.verificationLevel)) state.verificationLevel = 'auto';
    state.memoryEnabled = state.memoryEnabled === true;
    state.autoLearn = state.autoLearn === true;
    state.autoTools = state.autoTools === true;
  }

  function privateChats() {
    const value = readJSON(privateKey(), []);
    return new Set(Array.isArray(value) ? value : []);
  }

  function isCurrentChatPrivate() {
    const id = window.currentChatId;
    return !!id && privateChats().has(id);
  }

  function writeLocalPrivateState(id, enabled) {
    if (!id) return;
    const chats = privateChats();
    if (enabled) chats.add(id);
    else chats.delete(id);
    try {
      localStorage.setItem(privateKey(), JSON.stringify([...chats].slice(-500)));
    } catch (_) {}
  }

  function pendingPrivateChanges() {
    const value = readJSON(privatePendingKey(), {});
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function writePendingPrivateChange(id, enabled) {
    const pending = pendingPrivateChanges();
    pending[id] = Boolean(enabled);
    const entries = Object.entries(pending).slice(-500);
    try {
      localStorage.setItem(privatePendingKey(), JSON.stringify(Object.fromEntries(entries)));
    } catch (_) {}
  }

  function clearPendingPrivateChange(id, expected) {
    const pending = pendingPrivateChanges();
    if (!Object.prototype.hasOwnProperty.call(pending, id) || pending[id] !== expected) return;
    delete pending[id];
    try {
      localStorage.setItem(privatePendingKey(), JSON.stringify(pending));
    } catch (_) {}
  }

  async function syncConversationPrivacy(id, enabled, revision) {
    try {
      const data = await api(`/api/intelligence/conversations/${encodeURIComponent(id)}/privacy`, {
        method: 'PATCH',
        body: JSON.stringify({ memoryOptOut: Boolean(enabled) }),
      });
      clearPendingPrivateChange(id, Boolean(enabled));
      if (revision !== privateMutationRevision || String(window.currentChatId || '') !== id) return;
      writeLocalPrivateState(id, data.memoryOptOut === true);
      hydratedPrivateChatId = id;
      refreshPanel();
    } catch (_) {
      if (revision !== privateMutationRevision) return;
      window.showToast?.('This privacy choice is saved on this device and will sync when the server is available.', 'warning');
    }
  }

  function setCurrentChatPrivate(enabled) {
    const id = String(window.currentChatId || '');
    if (!id) return;
    privateMutationRevision += 1;
    const revision = privateMutationRevision;
    writeLocalPrivateState(id, enabled);
    writePendingPrivateChange(id, enabled);
    hydratedPrivateChatId = id;
    refreshPanel();
    void syncConversationPrivacy(id, enabled, revision);
  }

  async function hydrateCurrentChatPrivacy({ force = false } = {}) {
    const id = String(window.currentChatId || '');
    if (!window.currentUser?.id || !id) return;
    if (!force && hydratedPrivateChatId === id) return;
    const startedRevision = privateMutationRevision;
    hydratedPrivateChatId = id;
    const pending = pendingPrivateChanges();
    const hasPending = Object.prototype.hasOwnProperty.call(pending, id);
    try {
      const data = hasPending
        ? await api(`/api/intelligence/conversations/${encodeURIComponent(id)}/privacy`, {
            method: 'PATCH',
            body: JSON.stringify({ memoryOptOut: Boolean(pending[id]) }),
          })
        : await api(`/api/intelligence/conversations/${encodeURIComponent(id)}/privacy`);
      if (hasPending) clearPendingPrivateChange(id, Boolean(pending[id]));
      if (startedRevision !== privateMutationRevision || String(window.currentChatId || '') !== id) return;
      writeLocalPrivateState(id, data.memoryOptOut === true);
    } catch (_) {
      if (String(window.currentChatId || '') === id) hydratedPrivateChatId = null;
    }
    refreshPanel();
  }

  function urlPath(input) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      return new URL(raw, location.origin).pathname;
    } catch (_) {
      return '';
    }
  }

  // Enrich only the primary chat POST. Authentication, sync, billing, and other
  // requests remain untouched.
  window.fetch = function crump44Fetch(input, init = {}) {
    const method = String(init?.method || (typeof input !== 'string' ? input?.method : 'GET') || 'GET').toUpperCase();
    if (method === 'POST' && urlPath(input) === '/api/chat' && typeof init?.body === 'string') {
      try {
        const body = JSON.parse(init.body);
        if (body && typeof body === 'object') {
          body.intelligenceMode = state.intelligenceMode;
          body.memoryEnabled = state.memoryEnabled;
          body.autoLearn = state.autoLearn;
          body.memoryOptOut = isCurrentChatPrivate();
          body.toolMode = state.autoTools ? 'auto' : 'manual';
          body.verificationMode = state.verificationLevel;
          init = { ...init, body: JSON.stringify(body) };
        }
      } catch (_) {}
    }
    return originalFetch(input, init);
  };

  async function api(path, options = {}) {
    const response = await originalFetch(path, {
      credentials: 'same-origin',
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || data.message || `Request failed (${response.status})`);
      error.status = response.status;
      error.code = data.code;
      error.requiredTier = data.requiredTier;
      throw error;
    }
    return data;
  }

  async function hydratePreferences({ force = false } = {}) {
    const userId = cleanUserId();
    if (!window.currentUser?.id) return;
    const pending = pendingPreferenceState();
    if (!force && hydratedUserId === userId && !pending) return;

    loadLocalState();
    const startedRevision = preferenceMutationRevision;
    try {
      const data = pending
        ? await api('/api/intelligence/preferences', {
            method: 'PATCH',
            body: JSON.stringify(pending),
          })
        : await api('/api/intelligence/preferences');
      if (pending) clearPendingPreferenceState(pending);
      if (startedRevision !== preferenceMutationRevision) return;
      applyEntitlements(data.entitlements);
      if (data.preferences) {
        state = { ...state, ...data.preferences };
        normalizeEntitledState();
        saveLocalState();
      }
      hydratedUserId = userId;
    } catch (error) {
      if (pending && error?.code === 'SUBSCRIPTION_REQUIRED') {
        clearPendingPreferenceState(pending);
        if (startedRevision === preferenceMutationRevision) {
          state.intelligenceMode = 'auto';
          state.verificationLevel = 'auto';
          saveLocalState();
        }
      }
      hydratedUserId = null;
    }
    refreshPanel();
  }

  let preferenceTimer = null;
  function persistPreferences() {
    saveLocalState();
    const outgoing = preferencePayload();
    writePendingPreferenceState(outgoing);
    preferenceMutationRevision += 1;
    const revision = preferenceMutationRevision;
    clearTimeout(preferenceTimer);
    preferenceTimer = setTimeout(async () => {
      if (!window.currentUser?.id) return;
      try {
        const data = await api('/api/intelligence/preferences', {
          method: 'PATCH',
          body: JSON.stringify(outgoing),
        });
        clearPendingPreferenceState(outgoing);
        if (revision !== preferenceMutationRevision) return;
        if (data.preferences) {
          state = { ...state, ...data.preferences };
          saveLocalState();
          refreshPanel();
        }
      } catch (error) {
        if (error?.code === 'SUBSCRIPTION_REQUIRED') {
          clearPendingPreferenceState(outgoing);
          if (revision !== preferenceMutationRevision) return;
          state.intelligenceMode = 'auto';
          state.verificationLevel = 'auto';
          saveLocalState();
          refreshPanel();
          openProfessionalPlans('advanced-intelligence-sync');
          return;
        }
        if (revision !== preferenceMutationRevision) return;
        window.showToast?.('Crump saved this setting locally and will sync it when the server is available.', 'warning');
      }
    }, 250);
  }

  function button(label, className, handler) {
    const node = document.createElement('button');
    node.type = 'button';
    node.className = className;
    node.textContent = label;
    node.addEventListener('click', handler);
    return node;
  }

  function makeToggle({ label, description, checked, onChange, id, disabled = false }) {
    const row = document.createElement('div');
    row.className = `crump44-toggle-row${disabled ? ' is-disabled' : ''}`;
    if (disabled) row.setAttribute('aria-disabled', 'true');

    const text = document.createElement('div');
    text.className = 'crump44-row-copy';
    const title = document.createElement('strong');
    title.textContent = label;
    const help = document.createElement('span');
    help.textContent = description;
    text.append(title, help);

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = `crump44-toggle${checked ? ' is-on' : ''}`;
    toggle.setAttribute('role', 'switch');
    toggle.setAttribute('aria-checked', String(checked));
    toggle.setAttribute('aria-label', label);
    toggle.disabled = disabled;
    if (id) toggle.id = id;
    const knob = document.createElement('span');
    toggle.appendChild(knob);
    toggle.addEventListener('click', () => {
      if (!disabled) onChange(!checked);
    });

    row.append(text, toggle);
    return row;
  }

  function makeSectionTitle(title, description = '') {
    const header = document.createElement('div');
    header.className = 'crump44-section-heading';
    const label = document.createElement('span');
    label.textContent = title;
    header.appendChild(label);
    if (description) {
      const help = document.createElement('small');
      help.textContent = description;
      header.appendChild(help);
    }
    return header;
  }

  function modeLabel(mode) {
    return { auto: 'Balanced', fast: 'Fast', deep: 'Deep' }[mode] || 'Balanced';
  }

  function verificationLabel(level) {
    return { off: 'Standard', auto: 'Smart', strict: 'Always' }[level] || 'Smart';
  }

  function openProfessionalPlans(source) {
    closePanel();
    const detail = {
      plan: 'professional',
      source,
      location: 'intelligence',
      capturedAt: Date.now(),
    };
    const open = () => {
      planOpenPending = false;
      const modal = window.showBillingCenter?.({ plan: 'professional' });
      if (!modal) window.showUpgradePrompt?.({ plan: 'professional' });
      window.dispatchEvent(new CustomEvent('crump:plan-intent', { detail }));
    };
    if (typeof window.showBillingCenter === 'function' || typeof window.showUpgradePrompt === 'function') {
      open();
      return;
    }
    if (planOpenPending) return;
    planOpenPending = true;
    window.showToast?.('Plans are loading. Crump will open them when ready.', 'info');
    window.addEventListener('crump:body-runtime-ready', open, { once: true });
    window.setTimeout(() => {
      if (!planOpenPending) return;
      planOpenPending = false;
      window.removeEventListener('crump:body-runtime-ready', open);
      window.showToast?.('Plan & credits did not finish loading. Please try again.', 'warning');
    }, PLAN_OPEN_TIMEOUT_MS);
  }

  function makeModeSelector() {
    const wrap = document.createElement('div');
    wrap.className = 'crump44-segmented';
    for (const mode of ['fast', 'auto', 'deep']) {
      const locked = mode === 'deep' && !entitlements.thinkLonger;
      const option = button(modeLabel(mode), `crump44-segment${state.intelligenceMode === mode ? ' active' : ''}`, () => {
        if (locked) {
          openProfessionalPlans('think-longer');
          return;
        }
        state.intelligenceMode = mode;
        persistPreferences();
        refreshPanel();
      });
      option.setAttribute('aria-pressed', String(state.intelligenceMode === mode));
      if (locked) {
        option.classList.add('is-locked');
        option.setAttribute('aria-label', 'Deep response style — Professional or Enterprise');
        option.title = 'Deep is included with Professional and Enterprise';
        const badge = document.createElement('small');
        badge.textContent = 'PRO';
        option.appendChild(badge);
      }
      wrap.appendChild(option);
    }
    return wrap;
  }

  function makeVerificationSelector() {
    const wrap = document.createElement('div');
    wrap.className = 'crump44-segmented crump44-segmented-small';
    for (const level of ['off', 'auto', 'strict']) {
      const locked = level === 'strict' && !entitlements.thinkLonger;
      const option = button(
        verificationLabel(level),
        `crump44-segment${state.verificationLevel === level ? ' active' : ''}`,
        () => {
          if (locked) {
            openProfessionalPlans('always-review');
            return;
          }
          state.verificationLevel = level;
          persistPreferences();
          refreshPanel();
        },
      );
      option.setAttribute('aria-pressed', String(state.verificationLevel === level));
      if (locked) {
        option.classList.add('is-locked');
        option.setAttribute('aria-label', 'Always review — Professional or Enterprise');
        option.title = 'Always review is included with Professional and Enterprise';
        const badge = document.createElement('small');
        badge.textContent = 'PRO';
        option.appendChild(badge);
      }
      wrap.appendChild(option);
    }
    return wrap;
  }

  function buildPanel() {
    const shell = document.createElement('section');
    shell.id = 'crumpIntelligencePanel';
    shell.className = 'crump44-panel';
    shell.setAttribute('role', 'dialog');
    shell.setAttribute('aria-label', `${assistantName()} response settings`);
    shell.hidden = true;

    const grabber = document.createElement('div');
    grabber.className = 'crump44-grabber';
    grabber.setAttribute('aria-hidden', 'true');

    const header = document.createElement('div');
    header.className = 'crump44-panel-header';
    const titleWrap = document.createElement('div');
    const eyebrow = document.createElement('span');
    eyebrow.className = 'crump44-eyebrow';
    eyebrow.textContent = assistantName().toUpperCase();
    const title = document.createElement('strong');
    title.textContent = 'Intelligence';
    const subtitle = document.createElement('small');
    subtitle.textContent = `Choose how ${assistantName()} responds. More controls stay out of the way until you need them.`;
    titleWrap.append(eyebrow, title, subtitle);
    const close = button('×', 'crump44-close', closePanel);
    close.setAttribute('aria-label', `Close ${assistantName()} controls`);
    header.append(titleWrap, close);

    const content = document.createElement('div');
    content.id = 'crump44PanelContent';
    content.className = 'crump44-panel-content';

    shell.append(grabber, header, content);
    document.body.appendChild(shell);
    return shell;
  }

  function refreshPanel() {
    if (!panel) return;
    const content = $('#crump44PanelContent', panel);
    if (!content) return;
    content.replaceChildren();

    if (memoryViewOpen) {
      renderMemoryView(content);
      return;
    }

    // This progressively disclosed layout replaces the former “Response effort”,
    // “Memory & privacy”, “Live knowledge”, “Quality review”, and
    // “Advanced Intelligence · Professional” hierarchy. The existing
    // “Think longer” and “Always review” backend capabilities remain unchanged.

    const modeSection = document.createElement('div');
    modeSection.className = 'crump44-section crump44-section-primary';
    modeSection.append(
      makeSectionTitle('Response style', 'Balanced is recommended for most work.'),
      makeModeSelector(),
    );

    const modeCopy = document.createElement('p');
    modeCopy.className = 'crump44-mode-copy';
    if (state.intelligenceMode === 'fast') {
      modeCopy.textContent = 'A quicker response for simple questions, rewrites, and first drafts.';
    } else if (state.intelligenceMode === 'deep') {
      modeCopy.textContent = 'Plans first and checks the final response. Best for difficult or high-stakes work.';
    } else {
      modeCopy.textContent = `${assistantName()} adapts the effort to each request without slowing down routine work.`;
    }
    modeSection.appendChild(modeCopy);

    const memorySection = document.createElement('div');
    memorySection.className = 'crump44-section';
    memorySection.append(
      makeSectionTitle('Memory', 'Keep useful continuity under your control.'),
      makeToggle({
        label: 'Use saved memory',
        description: `Use preferences, projects, goals, and details you asked ${assistantName()} to keep.`,
        checked: state.memoryEnabled,
        onChange: enabled => {
          state.memoryEnabled = enabled;
          persistPreferences();
          refreshPanel();
        },
      }),
      makeToggle({
        label: 'Learn when I ask',
        description: 'Save a detail only when you clearly say “remember that” or “I prefer”.',
        checked: state.autoLearn && state.memoryEnabled,
        onChange: enabled => {
          state.autoLearn = enabled;
          if (enabled) state.memoryEnabled = true;
          persistPreferences();
          refreshPanel();
        },
      }),
      makeToggle({
        label: 'Keep this chat out of memory',
        description: window.currentChatId
          ? `${assistantName()} will not retrieve or add long-term memories in this conversation.`
          : 'Available after the first message creates this conversation.',
        checked: isCurrentChatPrivate(),
        disabled: !window.currentChatId,
        onChange: enabled => setCurrentChatPrivate(enabled),
      }),
    );

    const memoryButton = button(
      `What ${assistantName()} remembers${statusData?.memoryCount ? ` · ${statusData.memoryCount}` : ''}`,
      'crump44-row-button',
      async () => {
        memoryViewOpen = true;
        refreshPanel();
      },
    );
    memorySection.appendChild(memoryButton);

    const currentInformationSection = document.createElement('div');
    currentInformationSection.className = 'crump44-section';
    currentInformationSection.append(
      makeSectionTitle('Current information', `Let ${assistantName()} check supported live sources when recency matters.`),
      makeToggle({
        label: 'Check current sources when needed',
        description: `Useful for current facts, weather, and other supported live information.`,
        checked: state.autoTools,
        onChange: enabled => {
          state.autoTools = enabled;
          persistPreferences();
          refreshPanel();
        },
      }),
    );

    const verifySection = document.createElement('div');
    verifySection.className = 'crump44-section';
    verifySection.append(
      makeSectionTitle('Answer review', 'Choose when Crump adds a second checking pass.'),
      makeVerificationSelector(),
    );
    const reviewCopy = document.createElement('p');
    reviewCopy.className = 'crump44-review-copy';
    if (state.verificationLevel === 'off') {
      reviewCopy.textContent = 'One response pass for the fastest result.';
    } else if (state.verificationLevel === 'strict') {
      reviewCopy.textContent = 'Checks every eligible response for logic, requirements, and unsupported claims.';
    } else {
      reviewCopy.textContent = 'Adds a review when work is complex, higher-risk, code-based, or downloadable.';
    }
    verifySection.appendChild(reviewCopy);

    const premium = document.createElement('div');
    premium.className = `crump44-premium${entitlements.thinkLonger ? ' is-active' : ''}`;
    const premiumCopy = document.createElement('div');
    premiumCopy.className = 'crump44-premium-copy';
    const premiumTitle = document.createElement('strong');
    premiumTitle.textContent = entitlements.thinkLonger
      ? 'Professional controls are active'
      : 'Go deeper with Professional';
    const premiumDescription = document.createElement('span');
    premiumDescription.textContent = entitlements.thinkLonger
      ? 'Deep responses and Always review are unlocked on this plan.'
      : 'Professional unlocks Deep responses and Always review. Enterprise includes them too.';
    premiumCopy.append(premiumTitle, premiumDescription);
    premium.appendChild(premiumCopy);
    if (!entitlements.thinkLonger) {
      const comparePlans = button('See Professional', 'crump44-premium-button', () => {
        openProfessionalPlans('advanced-intelligence-card');
      });
      premium.appendChild(comparePlans);
    }

    const advanced = document.createElement('details');
    advanced.className = 'crump44-advanced';
    advanced.open = advancedOpen;
    advanced.addEventListener('toggle', () => {
      advancedOpen = advanced.open;
    });

    const advancedSummary = document.createElement('summary');
    const advancedCopy = document.createElement('span');
    advancedCopy.className = 'crump44-advanced-copy';
    const advancedTitle = document.createElement('strong');
    advancedTitle.textContent = 'Memory, sources & review';
    const advancedStatus = document.createElement('small');
    advancedStatus.textContent = [
      `Memory ${state.memoryEnabled ? 'on' : 'off'}`,
      `Current info ${state.autoTools ? 'on' : 'off'}`,
      `${verificationLabel(state.verificationLevel)} review`,
    ].join(' · ');
    advancedCopy.append(advancedTitle, advancedStatus);
    const advancedChevron = document.createElement('span');
    advancedChevron.className = 'crump44-advanced-chevron';
    advancedChevron.setAttribute('aria-hidden', 'true');
    advancedChevron.textContent = '⌄';
    advancedSummary.append(advancedCopy, advancedChevron);

    const advancedBody = document.createElement('div');
    advancedBody.className = 'crump44-advanced-body';
    advancedBody.append(memorySection, currentInformationSection, verifySection, premium);
    advanced.append(advancedSummary, advancedBody);

    content.append(modeSection, advanced);
  }

  async function renderMemoryView(content) {
    const header = document.createElement('div');
    header.className = 'crump44-memory-header';
    const back = button('←', 'crump44-back', () => {
      memoryViewOpen = false;
      refreshPanel();
    });
    back.setAttribute('aria-label', 'Back to response settings');
    const copy = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = `What ${assistantName()} remembers`;
    const subtitle = document.createElement('span');
    subtitle.textContent = 'Only durable memory items. Your full chat history lives separately.';
    copy.append(title, subtitle);
    header.append(back, copy);
    content.appendChild(header);

    const loading = document.createElement('div');
    loading.className = 'crump44-memory-empty';
    loading.textContent = 'Loading memory…';
    content.appendChild(loading);

    let memories = [];
    try {
      const data = await api('/api/intelligence/memories?limit=100');
      memories = Array.isArray(data.memories) ? data.memories : [];
      statusData = { ...(statusData || {}), memoryCount: memories.length };
    } catch (_) {
      loading.textContent = 'Memory is temporarily unavailable.';
      return;
    }

    loading.remove();

    if (!memories.length) {
      const empty = document.createElement('div');
      empty.className = 'crump44-memory-empty';
      empty.textContent = `Nothing saved yet. ${assistantName()} can learn durable details when you state them clearly.`;
      content.appendChild(empty);
      return;
    }

    const list = document.createElement('div');
    list.className = 'crump44-memory-list';
    for (const memory of memories) {
      const card = document.createElement('article');
      card.className = 'crump44-memory-card';
      const top = document.createElement('div');
      top.className = 'crump44-memory-card-top';
      const kind = document.createElement('span');
      kind.className = 'crump44-memory-kind';
      kind.textContent = String(memory.kind || 'note').replace(/_/g, ' ');
      const remove = button('Forget', 'crump44-forget', async () => {
        remove.disabled = true;
        try {
          await api(`/api/intelligence/memories/${encodeURIComponent(memory.id)}`, { method: 'DELETE' });
          card.remove();
          statusData = { ...(statusData || {}), memoryCount: Math.max(0, Number(statusData?.memoryCount || memories.length) - 1) };
          if (!list.children.length) {
            memoryViewOpen = false;
            refreshPanel();
          }
        } catch (_) {
          remove.disabled = false;
          window.showToast?.('Could not forget that memory yet.', 'error');
        }
      });
      top.append(kind, remove);

      const body = document.createElement('p');
      body.textContent = String(memory.content || '');
      card.append(top, body);
      list.appendChild(card);
    }
    content.appendChild(list);

    const clear = button('Forget all saved memories', 'crump44-clear-memory', async () => {
      const accepted = await window.confirmAction?.({
        title: 'Forget all saved memories?',
        message: 'Conversation history will stay intact. Only Crump’s separate long-term memory will be cleared.',
        confirmLabel: 'Forget memories',
        destructive: true,
      });
      if (!accepted) return;
      clear.disabled = true;
      try {
        await api('/api/intelligence/memories', { method: 'DELETE' });
        statusData = { ...(statusData || {}), memoryCount: 0 };
        memoryViewOpen = false;
        refreshPanel();
        window.showToast?.('Crump’s saved memories were cleared.', 'success');
      } catch (_) {
        clear.disabled = false;
        window.showToast?.('Could not clear memories yet.', 'error');
      }
    });
    content.appendChild(clear);
  }

  async function refreshStatus() {
    if (!window.currentUser?.id) return;
    try {
      statusData = await api('/api/intelligence/status');
      applyEntitlements(statusData.entitlements);
    } catch (_) {
      statusData = null;
    }
    refreshPanel();
  }

  async function openPanel() {
    if (!panel) panel = buildPanel();
    await Promise.all([hydratePreferences(), hydrateCurrentChatPrivacy()]);
    panel.hidden = false;
    document.body.classList.add('crump44-panel-open');
    void window.CrumpAnalytics?.track?.('NavigationDestinationSelected', {
      eventKey: 'navigation-destination-selected',
      source: 'intelligence',
    });
    const trigger = $('#crumpIntelligenceButton');
    trigger?.setAttribute('aria-expanded', 'true');
    refreshPanel();
    refreshStatus();
    setTimeout(() => $('.crump44-close', panel)?.focus({ preventScroll: true }), 20);
  }

  function closePanel() {
    if (!panel) return;
    panel.hidden = true;
    memoryViewOpen = false;
    document.body.classList.remove('crump44-panel-open');
    $('#crumpIntelligenceButton')?.setAttribute('aria-expanded', 'false');
  }

  function togglePanel() {
    if (!panel || panel.hidden) openPanel();
    else closePanel();
  }

  function addControlButton() {
    const header = $('.header');
    if (!header || $('#crumpIntelligenceButton')) return;

    const control = document.createElement('button');
    control.id = 'crumpIntelligenceButton';
    control.type = 'button';
    control.className = 'crump44-control-button';
    control.setAttribute('aria-label', `${assistantName()} intelligence controls`);
    control.setAttribute('aria-haspopup', 'dialog');
    control.setAttribute('aria-expanded', 'false');
    control.title = 'Intelligence';
    // A compact glasses glyph feels more distinctly Ask Crump than a
    // generic AI brain while keeping the Intelligence control subtle.
    control.innerHTML = `
      <svg class="crump44-glasses-icon" width="23" height="23" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
        <rect x="3.35" y="8.55" width="6.15" height="5.5" rx="2.2" stroke="currentColor" stroke-width="1.5"/>
        <rect x="14.5" y="8.55" width="6.15" height="5.5" rx="2.2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M9.5 11.15H14.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M3.35 10.95L2.35 10.55M20.65 10.95L21.65 10.55" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity=".82"/>
        <path d="M6.45 9.75C6.92 9.43 7.46 9.25 8.05 9.25M15.95 9.25C16.54 9.25 17.08 9.43 17.55 9.75" stroke="currentColor" stroke-width="1.05" stroke-linecap="round" opacity=".58"/>
      </svg>`;
    control.addEventListener('click', event => {
      event.stopPropagation();
      togglePanel();
    });
    header.appendChild(control);
  }

  function installKeyboardBehavior() {
    const input = $('#userInput');
    if (!input || input.dataset.crump44Keyboard === 'true') return;
    input.dataset.crump44Keyboard = 'true';

    // Capture phase runs before app.js's legacy Enter-to-send listener.
    input.addEventListener('keydown', event => {
      if (event.key !== 'Enter' || event.isComposing) return;

      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        event.stopImmediatePropagation();
        window.sendMessage?.();
        return;
      }

      // Do not preventDefault: the textarea performs its native newline action.
      // Stop the old bubble listener so plain Enter never submits the message.
      event.stopImmediatePropagation();
    }, true);
  }

  function watchAuthenticatedUser() {
    let lastUser = cleanUserId();
    let lastChatId = String(window.currentChatId || '');
    setInterval(() => {
      const nextUser = cleanUserId();
      if (nextUser !== lastUser) {
        lastUser = nextUser;
        hydratedUserId = null;
        hydratedPrivateChatId = null;
        loadLocalState();
        hydratePreferences({ force: true });
      }
      const nextChatId = String(window.currentChatId || '');
      if (nextChatId !== lastChatId) {
        lastChatId = nextChatId;
        hydratedPrivateChatId = null;
        if (panel && !panel.hidden) void hydrateCurrentChatPrivacy({ force: true });
        else refreshPanel();
      }
    }, 1500);
  }

  function syncAssistantName() {
    panel?.setAttribute('aria-label', `${assistantName()} response settings`);
    const eyebrow = panel && $('.crump44-eyebrow', panel);
    if (eyebrow) eyebrow.textContent = assistantName().toUpperCase();
    const close = panel && $('.crump44-close', panel);
    close?.setAttribute('aria-label', `Close ${assistantName()} controls`);
    $('#crumpIntelligenceButton')?.setAttribute('aria-label', `${assistantName()} intelligence controls`);
    refreshPanel();
  }

  function boot() {
    if (document.documentElement.dataset.crump44Booted === 'true') return;
    document.documentElement.dataset.crump44Booted = 'true';
    document.body.classList.add('crump-44');

    loadLocalState();
    addControlButton();
    panel = buildPanel();
    installKeyboardBehavior();
    watchAuthenticatedUser();
    window.addEventListener('crump:assistant-name-changed', syncAssistantName);

    document.addEventListener('click', event => {
      if (!panel || panel.hidden) return;
      if (panel.contains(event.target) || $('#crumpIntelligenceButton')?.contains(event.target)) return;
      closePanel();
    });

    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && panel && !panel.hidden) {
        event.preventDefault();
        closePanel();
        $('#crumpIntelligenceButton')?.focus({ preventScroll: true });
      }
    });

    // app.js and the 4.3 polish may finish after this file on some mobile loads.
    // A short follow-up pass makes the keyboard and header control self-healing.
    setTimeout(() => {
      addControlButton();
      installKeyboardBehavior();
    }, 600);

    hydratePreferences();
  }

  if (document.readyState === 'complete') {
    setTimeout(boot, 60);
  } else {
    window.addEventListener('load', () => setTimeout(boot, 60), { once: true });
  }
})();
