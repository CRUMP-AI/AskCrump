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

  const originalFetch = window.fetch.bind(window);
  let state = { ...DEFAULTS };
  let hydratedUserId = null;
  let panel = null;
  let memoryViewOpen = false;
  let statusData = null;

  const $ = (selector, root = document) => root.querySelector(selector);

  function cleanUserId() {
    return String(window.currentUser?.id || 'guest').replace(/[^a-zA-Z0-9_-]/g, '');
  }

  function preferenceKey() {
    return `crump_intelligence_v44:${cleanUserId() || 'guest'}`;
  }

  function privateKey() {
    return `crump_private_chats_v44:${cleanUserId() || 'guest'}`;
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

  function loadLocalState() {
    const saved = readJSON(preferenceKey(), {});
    state = {
      ...DEFAULTS,
      ...(saved && typeof saved === 'object' ? saved : {}),
    };
    if (!['auto', 'fast', 'deep'].includes(state.intelligenceMode)) state.intelligenceMode = 'auto';
    if (!['off', 'auto', 'strict'].includes(state.verificationLevel)) state.verificationLevel = 'auto';
    state.memoryEnabled = state.memoryEnabled !== false;
    state.autoLearn = state.autoLearn !== false;
    state.autoTools = state.autoTools !== false;
  }

  function privateChats() {
    const value = readJSON(privateKey(), []);
    return new Set(Array.isArray(value) ? value : []);
  }

  function isCurrentChatPrivate() {
    const id = window.currentChatId;
    return !!id && privateChats().has(id);
  }

  function setCurrentChatPrivate(enabled) {
    const id = window.currentChatId;
    if (!id) return;
    const chats = privateChats();
    if (enabled) chats.add(id);
    else chats.delete(id);
    try {
      localStorage.setItem(privateKey(), JSON.stringify([...chats].slice(-500)));
    } catch (_) {}
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
      throw error;
    }
    return data;
  }

  async function hydratePreferences({ force = false } = {}) {
    const userId = cleanUserId();
    if (!window.currentUser?.id) return;
    if (!force && hydratedUserId === userId) return;

    loadLocalState();
    try {
      const data = await api('/api/intelligence/preferences');
      if (data.preferences) {
        state = { ...state, ...data.preferences };
        saveLocalState();
      }
      hydratedUserId = userId;
    } catch (_) {
      hydratedUserId = userId;
    }
    refreshPanel();
  }

  let preferenceTimer = null;
  function persistPreferences() {
    saveLocalState();
    clearTimeout(preferenceTimer);
    preferenceTimer = setTimeout(async () => {
      if (!window.currentUser?.id) return;
      try {
        const data = await api('/api/intelligence/preferences', {
          method: 'PATCH',
          body: JSON.stringify(state),
        });
        if (data.preferences) {
          state = { ...state, ...data.preferences };
          saveLocalState();
          refreshPanel();
        }
      } catch (_) {
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

  function makeToggle({ label, description, checked, onChange, id }) {
    const row = document.createElement('div');
    row.className = 'crump44-toggle-row';

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
    if (id) toggle.id = id;
    const knob = document.createElement('span');
    toggle.appendChild(knob);
    toggle.addEventListener('click', () => onChange(!checked));

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
    return { auto: 'Auto', fast: 'Fast', deep: 'Deep' }[mode] || 'Auto';
  }

  function verificationLabel(level) {
    return { off: 'Off', auto: 'Auto', strict: 'Strict' }[level] || 'Auto';
  }

  function makeModeSelector() {
    const wrap = document.createElement('div');
    wrap.className = 'crump44-segmented';
    for (const mode of ['auto', 'fast', 'deep']) {
      const option = button(modeLabel(mode), `crump44-segment${state.intelligenceMode === mode ? ' active' : ''}`, () => {
        state.intelligenceMode = mode;
        persistPreferences();
        refreshPanel();
      });
      option.setAttribute('aria-pressed', String(state.intelligenceMode === mode));
      wrap.appendChild(option);
    }
    return wrap;
  }

  function makeVerificationSelector() {
    const wrap = document.createElement('div');
    wrap.className = 'crump44-segmented crump44-segmented-small';
    for (const level of ['off', 'auto', 'strict']) {
      const option = button(
        verificationLabel(level),
        `crump44-segment${state.verificationLevel === level ? ' active' : ''}`,
        () => {
          state.verificationLevel = level;
          persistPreferences();
          refreshPanel();
        },
      );
      option.setAttribute('aria-pressed', String(state.verificationLevel === level));
      wrap.appendChild(option);
    }
    return wrap;
  }

  function makeToolButtons() {
    const tools = document.createElement('div');
    tools.className = 'crump44-tools';
    const definitions = [
      ['Web', 'searchQuickAction'],
      ['Image', 'imageQuickAction'],
      ['Code', 'codeQuickAction'],
    ];
    for (const [label, targetId] of definitions) {
      const tool = button(label, 'crump44-tool', () => {
        document.getElementById(targetId)?.click();
        closePanel();
        document.getElementById('userInput')?.focus({ preventScroll: true });
      });
      tools.appendChild(tool);
    }
    return tools;
  }

  function buildPanel() {
    const shell = document.createElement('section');
    shell.id = 'crumpIntelligencePanel';
    shell.className = 'crump44-panel';
    shell.setAttribute('role', 'dialog');
    shell.setAttribute('aria-label', 'Crump controls');
    shell.hidden = true;

    const grabber = document.createElement('div');
    grabber.className = 'crump44-grabber';
    grabber.setAttribute('aria-hidden', 'true');

    const header = document.createElement('div');
    header.className = 'crump44-panel-header';
    const titleWrap = document.createElement('div');
    const eyebrow = document.createElement('span');
    eyebrow.className = 'crump44-eyebrow';
    eyebrow.textContent = 'CRUMP';
    const title = document.createElement('strong');
    title.textContent = 'Intelligence';
    const subtitle = document.createElement('small');
    subtitle.textContent = 'Power underneath the conversation.';
    titleWrap.append(eyebrow, title, subtitle);
    const close = button('×', 'crump44-close', closePanel);
    close.setAttribute('aria-label', 'Close Crump controls');
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

    const modeSection = document.createElement('div');
    modeSection.className = 'crump44-section';
    modeSection.append(
      makeSectionTitle('Response mode', 'Auto is the recommended everyday setting.'),
      makeModeSelector(),
    );

    const modeCopy = document.createElement('p');
    modeCopy.className = 'crump44-mode-copy';
    if (state.intelligenceMode === 'fast') {
      modeCopy.textContent = 'Prioritizes speed and skips extra planning unless a tool is required.';
    } else if (state.intelligenceMode === 'deep') {
      modeCopy.textContent = 'Adds a planning pass and stronger final-answer review for difficult work.';
    } else {
      modeCopy.textContent = 'Crump chooses how much orchestration the request actually needs.';
    }
    modeSection.appendChild(modeCopy);

    const memorySection = document.createElement('div');
    memorySection.className = 'crump44-section';
    memorySection.append(
      makeSectionTitle('Memory', 'Durable context stays separate from ordinary chat history.'),
      makeToggle({
        label: 'Use memory',
        description: 'Let Crump retrieve useful preferences, projects, goals, and explicit memories.',
        checked: state.memoryEnabled,
        onChange: enabled => {
          state.memoryEnabled = enabled;
          persistPreferences();
          refreshPanel();
        },
      }),
      makeToggle({
        label: 'Learn explicit details',
        description: 'Save durable facts when you clearly say things like “remember that” or “I prefer”.',
        checked: state.autoLearn && state.memoryEnabled,
        onChange: enabled => {
          state.autoLearn = enabled;
          if (enabled) state.memoryEnabled = true;
          persistPreferences();
          refreshPanel();
        },
      }),
      makeToggle({
        label: 'Private this conversation',
        description: 'Use the conversation normally, but do not learn new long-term memories from it.',
        checked: isCurrentChatPrivate(),
        onChange: enabled => setCurrentChatPrivate(enabled),
      }),
    );

    const memoryButton = button(
      `What Crump remembers${statusData?.memoryCount ? ` · ${statusData.memoryCount}` : ''}`,
      'crump44-row-button',
      async () => {
        memoryViewOpen = true;
        refreshPanel();
      },
    );
    memorySection.appendChild(memoryButton);

    const toolsSection = document.createElement('div');
    toolsSection.className = 'crump44-section';
    toolsSection.append(
      makeSectionTitle('Tools', 'Keep the chat clean; open what you need from here.'),
      makeToggle({
        label: 'Automatic tools',
        description: 'Let Crump decide when current web or weather information is necessary.',
        checked: state.autoTools,
        onChange: enabled => {
          state.autoTools = enabled;
          persistPreferences();
          refreshPanel();
        },
      }),
      makeToolButtons(),
    );

    const verifySection = document.createElement('div');
    verifySection.className = 'crump44-section';
    verifySection.append(
      makeSectionTitle('Answer check', 'A second pass is reserved for requests where it adds value.'),
      makeVerificationSelector(),
    );

    const keyboard = document.createElement('div');
    keyboard.className = 'crump44-keyboard-note';
    const keyboardTitle = document.createElement('strong');
    keyboardTitle.textContent = 'Keyboard';
    const keyboardCopy = document.createElement('span');
    keyboardCopy.textContent = 'Enter starts a new line. Ctrl+Enter or ⌘+Enter sends.';
    keyboard.append(keyboardTitle, keyboardCopy);

    const advanced = document.createElement('div');
    advanced.className = 'crump44-section crump44-system';
    advanced.appendChild(makeSectionTitle('System'));
    const capabilities = statusData?.capabilities || {};
    const items = [
      ['Memory', capabilities.memory !== false],
      ['Planner', capabilities.planner !== false],
      ['Verification', capabilities.verification !== false],
      ['Tool routing', capabilities.toolRouting !== false],
      ['Cross-device authority', capabilities.crossDeviceAuthority !== false],
    ];
    const statusGrid = document.createElement('div');
    statusGrid.className = 'crump44-status-grid';
    for (const [label, enabled] of items) {
      const item = document.createElement('div');
      const dot = document.createElement('i');
      dot.className = enabled ? 'is-on' : '';
      const text = document.createElement('span');
      text.textContent = label;
      item.append(dot, text);
      statusGrid.appendChild(item);
    }
    advanced.appendChild(statusGrid);

    const tutorialButton = button('Replay product tour', 'crump44-row-button crump44-subtle', () => {
      closePanel();
      window.tutorial?.restart?.();
    });
    advanced.appendChild(tutorialButton);

    content.append(modeSection, memorySection, toolsSection, verifySection, keyboard, advanced);
  }

  async function renderMemoryView(content) {
    const header = document.createElement('div');
    header.className = 'crump44-memory-header';
    const back = button('←', 'crump44-back', () => {
      memoryViewOpen = false;
      refreshPanel();
    });
    back.setAttribute('aria-label', 'Back to intelligence controls');
    const copy = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = 'What Crump remembers';
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
      empty.textContent = 'Nothing saved yet. Crump can learn durable details when you state them clearly.';
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
    } catch (_) {
      statusData = null;
    }
    refreshPanel();
  }

  async function openPanel() {
    if (!panel) panel = buildPanel();
    await hydratePreferences();
    panel.hidden = false;
    document.body.classList.add('crump44-panel-open');
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
    control.setAttribute('aria-label', 'Crump intelligence controls');
    control.setAttribute('aria-haspopup', 'dialog');
    control.setAttribute('aria-expanded', 'false');
    control.title = 'Crump controls';
    control.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M10 14v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="16" cy="7" r="2" stroke="currentColor" stroke-width="1.8"/><circle cx="8" cy="17" r="2" stroke="currentColor" stroke-width="1.8"/></svg>';
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
    setInterval(() => {
      const nextUser = cleanUserId();
      if (nextUser !== lastUser) {
        lastUser = nextUser;
        hydratedUserId = null;
        loadLocalState();
        hydratePreferences({ force: true });
      }
    }, 1500);
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
