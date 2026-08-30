(() => {
  'use strict';

  const state = {
    features: null,
    projects: [],
    activeProject: null,
    editingProject: null,
    projectView: 'index',
    projectConversations: [],
    manuscripts: [],
    activeManuscript: null,
    activeSection: null,
    manuscriptProgress: null,
    manuscriptRun: null,
    manuscriptPollTimer: null,
    videoPollTimer: null,
    activeVideoJob: null,
    libraryFiles: [],
    libraryFilter: 'all',
    libraryVideoObserver: null,
  };

  const nativeFetch = window.fetch.bind(window);
  const PROJECT_SAVE_TIMEOUT_MS = 15_000;
  const PROJECT_READ_TIMEOUT_MS = 15_000;
  const PROJECT_ROUTE_PARAM = 'project';
  const FEATURE_ACCESS_CODES = new Set([
    'SUBSCRIPTION_REQUIRED',
    'CREDITS_REQUIRED',
    'FEATURE_LIMIT_REACHED',
    'PROJECT_LIMIT_REACHED',
  ]);
  const byId = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);

  function readStoredProject() {
    try { return localStorage.getItem('askcrump.activeProject53') || ''; }
    catch (_) { return ''; }
  }

  function storeProject(value) {
    try {
      if (value) localStorage.setItem('askcrump.activeProject53', value);
      else localStorage.removeItem('askcrump.activeProject53');
    } catch (_) { /* storage is optional */ }
  }

  function readProjectRoute() {
    try { return new URL(window.location.href).searchParams.get(PROJECT_ROUTE_PARAM) || ''; }
    catch (_) { return ''; }
  }

  function projectRouteHref(projectId = '') {
    try {
      const url = new URL(window.location.pathname, window.location.origin);
      const normalized = String(projectId || '').trim();
      if (normalized) url.searchParams.set(PROJECT_ROUTE_PARAM, normalized);
      return `${url.pathname}${url.search}`;
    } catch (_) {
      return '/app';
    }
  }

  function writeProjectRoute(projectId = '', {replace = false} = {}) {
    const href = projectRouteHref(projectId);
    const current = `${window.location.pathname}${window.location.search}`;
    if (href === current) return;
    const normalized = String(projectId || '').trim();
    const nextState = {...(window.history.state || {})};
    if (normalized) nextState.askCrumpProjectRoute = normalized;
    else delete nextState.askCrumpProjectRoute;
    window.history[replace ? 'replaceState' : 'pushState'](nextState, '', href);
  }

  function currentProjectTarget() {
    const id = String(state.activeProject?.id || '').trim();
    if (!id) return null;
    return {
      id,
      name: String(state.activeProject?.name || 'Project').replace(/\s+/g, ' ').trim() || 'Project',
    };
  }

  function notifyProjectTargetChanged() {
    window.dispatchEvent(new Event('crump:project-target-changed'));
  }

  function readStoredVideoJob() {
    try { return localStorage.getItem('askcrump.videoJob53') || ''; }
    catch (_) { return ''; }
  }

  function storeVideoJob(value) {
    try {
      if (value) localStorage.setItem('askcrump.videoJob53', value);
      else localStorage.removeItem('askcrump.videoJob53');
    } catch (_) { /* storage is optional */ }
  }

  async function api(path, options = {}) {
    const {
      timeoutMs: requestedTimeout = 0,
      signal: callerSignal,
      ...requestOptions
    } = options;
    const timeoutMs = Math.max(0, Number(requestedTimeout) || 0);
    const controller = timeoutMs > 0 ? new AbortController() : null;
    let timeoutId = null;
    let relayAbort = null;
    if (controller && callerSignal) {
      relayAbort = () => controller.abort(callerSignal.reason);
      if (callerSignal.aborted) relayAbort();
      else callerSignal.addEventListener('abort', relayAbort, {once: true});
    }
    if (controller && !controller.signal.aborted) {
      timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    }
    const signal = controller?.signal || callerSignal;
    const headers = {...(requestOptions.headers || {})};
    if (requestOptions.body && typeof requestOptions.body !== 'string') {
      headers['Content-Type'] = 'application/json';
      requestOptions.body = JSON.stringify(requestOptions.body);
    }
    try {
      const response = await nativeFetch(path, {
        credentials: 'include',
        ...requestOptions,
        headers,
        ...(signal ? {signal} : {}),
      });
      let data = {};
      try {
        data = await response.json();
      } catch (error) {
        if (controller?.signal.aborted || callerSignal?.aborted) throw error;
        data = {};
      }
      if (!response.ok || data.success === false) {
        const error = new Error(data.error || `Request failed (${response.status})`);
        error.data = data;
        error.status = response.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (controller?.signal.aborted && !callerSignal?.aborted) {
        const timeoutError = new Error('This request took too long. Check your connection and try again.');
        timeoutError.code = 'REQUEST_TIMEOUT';
        throw timeoutError;
      }
      throw error;
    } finally {
      if (timeoutId !== null) clearTimeout(timeoutId);
      if (callerSignal && relayAbort) callerSignal.removeEventListener('abort', relayAbort);
    }
  }

  function setStatus(id, message, isError = false) {
    const node = byId(id);
    if (!node) return;
    node.textContent = message || '';
    node.classList.toggle('is-error', Boolean(isError));
  }

  function featureAccessCode(error) {
    return String(error?.data?.code || error?.code || '').toUpperCase();
  }

  function openFeatureAccessRecovery(error) {
    const open = window.showUpgradePrompt || window.showBillingCenter;
    if (typeof open !== 'function') {
      window.showToast?.('Plan & credits is still loading. Try again in a moment.', 'error');
      return false;
    }
    const requiredTier = error?.data?.requiredTier;
    open({
      ...(requiredTier ? {plan: requiredTier} : {}),
      source: 'feature_recovery',
    });
    return true;
  }

  function setFeatureAccessStatus(id, error, message = '') {
    setStatus(id, message || error?.message || 'This feature is not available yet.', true);
    const code = featureAccessCode(error);
    if (!FEATURE_ACCESS_CODES.has(code)) return false;
    const node = byId(id);
    if (!node) return false;
    const actions = document.createElement('span');
    actions.className = 'crump53-actions crump53-feature-recovery';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'crump53-button';
    button.textContent = code === 'CREDITS_REQUIRED'
      ? 'Add credits or compare plans'
      : (code === 'SUBSCRIPTION_REQUIRED' ? 'Compare plans' : 'Review Plan & credits');
    button.setAttribute('aria-label', `${button.textContent} for this feature`);
    button.addEventListener('click', () => openFeatureAccessRecovery(error));
    actions.appendChild(button);
    node.appendChild(actions);
    return true;
  }

  function renderRetryableListError(list, message, label, retry) {
    if (!list) return;
    const note = document.createElement('div');
    note.className = 'crump53-note';
    note.textContent = message;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'crump53-button';
    button.textContent = 'Retry';
    button.setAttribute('aria-label', label);
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await retry();
      } finally {
        if (button.isConnected) button.disabled = false;
      }
    });
    list.replaceChildren(note, button);
  }

  function injectProjectIntoChatRequests() {
    window.fetch = async (input, init = {}) => {
      let url;
      try {
        url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
      } catch (_) {
        return nativeFetch(input, init);
      }
      const method = String(init.method || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
      if (url.origin === window.location.origin && url.pathname === '/api/chat' && method === 'POST') {
        const body = init.body;
        if (typeof body === 'string' && state.activeProject?.id) {
          try {
            const parsed = JSON.parse(body);
            if (parsed && typeof parsed === 'object' && !parsed.projectId) {
              parsed.projectId = state.activeProject.id;
              init = {...init, body: JSON.stringify(parsed)};
            }
          } catch (_) { /* preserve the original request */ }
        }
      }
      return nativeFetch(input, init);
    };
  }

  const TOOL_MENU_META = Object.freeze({
    focus: {label: 'Ask', description: 'Think something through'},
    research: {label: 'Research', description: 'Search current sources'},
    image: {label: 'Image', description: 'Generate or edit visuals'},
    document: {label: 'Document', description: 'Build a polished file'},
    manuscript: {label: 'Manuscript', description: 'Plan and draft long-form work'},
    video: {label: 'Video', description: 'Create or continue a scene'},
    file: {label: 'Files', description: 'Attach a reference file'},
  });

  function toolKey(button) {
    if (button?.dataset?.v1Command) return button.dataset.v1Command;
    if (button?.id === 'crump53DocumentMode') return 'document';
    if (button?.id === 'crump53ManuscriptMode') return 'manuscript';
    if (button?.id === 'crump53VideoMode') return 'video';
    return 'focus';
  }

  function toolIcon(key) {
    const paths = {
      focus: '<path d="M5 7.5h14v9H9l-4 3v-12Z"/><path d="M9 11h6M9 14h4"/>',
      research: '<circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 4 4M10.5 8v5M8 10.5h5"/>',
      image: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="m6.5 16 4-4 3 3 2-2 2 3M15.5 9h.01"/>',
      document: '<path d="M7 3.5h7l3 3V20H7z"/><path d="M14 3.5V7h3M9.5 11h5M9.5 14h5M9.5 17h3"/>',
      manuscript: '<path d="M5 5.5A3.5 3.5 0 0 1 8.5 2H19v16H8.5A3.5 3.5 0 0 0 5 21.5z"/><path d="M5 5.5v16M9 6h6M9 9h6"/>',
      video: '<rect x="3.5" y="5" width="13" height="14" rx="2"/><path d="m16.5 10 4-2v8l-4-2zM8 9l5 3-5 3z"/>',
      file: '<path d="M4 7h6l2 2h8v10H4z"/><path d="M4 7V5h7l2 2"/>',
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[key] || paths.focus}</svg>`;
  }

  function enhanceToolMenu(strip) {
    if (!strip || strip.dataset.crump53Menu === 'true') return;
    strip.dataset.crump53Menu = 'true';

    const shell = document.createElement('div');
    shell.className = 'crump53-tool-shell';
    const trigger = document.createElement('button');
    trigger.id = 'crump53ToolTrigger';
    trigger.type = 'button';
    trigger.className = 'crump53-tool-trigger';
    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-controls', 'crump53ToolMenu');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.innerHTML = `
      <span class="crump53-tool-trigger-mark">${toolIcon('focus')}</span>
      <span class="crump53-tool-trigger-copy"><small>TOOLS</small><strong data-crump53-tool-label>Ask</strong></span>
      <span class="crump53-tool-count">7 tools</span>
      <svg class="crump53-tool-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m8 10 4 4 4-4"/></svg>`;

    const menu = document.createElement('div');
    menu.id = 'crump53ToolMenu';
    menu.className = 'crump53-tool-menu';
    menu.hidden = true;
    menu.innerHTML = `
      <div class="crump53-tool-menu-head">
        <span><small>ASK CRUMP TOOLS</small><strong>What do you want to do?</strong></span>
        <i aria-hidden="true">✦</i>
      </div>`;

    const parent = strip.parentNode;
    parent.insertBefore(shell, strip);
    shell.append(trigger, menu);
    menu.appendChild(strip);
    strip.classList.add('crump53-tool-grid');
    strip.setAttribute('role', 'menu');
    strip.setAttribute('aria-label', 'Create with Crump tools');

    const options = Array.from(strip.querySelectorAll('.v1-mode-pill'));
    options.forEach(button => {
      const key = toolKey(button);
      const meta = TOOL_MENU_META[key] || TOOL_MENU_META.focus;
      button.dataset.crump53Tool = key;
      button.classList.add('crump53-tool-option');
      button.setAttribute('role', 'menuitemradio');
      button.setAttribute('aria-label', `${meta.label}: ${meta.description}`);
      button.innerHTML = `
        <span class="crump53-tool-icon">${toolIcon(key)}</span>
        <span class="crump53-tool-option-copy"><strong>${meta.label}</strong><small>${meta.description}</small></span>`;
    });

    const choose = button => {
      if (!button) return;
      const key = toolKey(button);
      const meta = TOOL_MENU_META[key] || TOOL_MENU_META.focus;
      options.forEach(option => {
        const selected = option === button;
        option.classList.toggle('is-active', selected);
        option.setAttribute('aria-checked', selected ? 'true' : 'false');
      });
      const label = trigger.querySelector('[data-crump53-tool-label]');
      const mark = trigger.querySelector('.crump53-tool-trigger-mark');
      if (label) label.textContent = meta.label;
      if (mark) mark.innerHTML = toolIcon(key);
    };

    const setOpen = open => {
      const next = Boolean(open);
      menu.hidden = !next;
      shell.classList.toggle('is-open', next);
      trigger.setAttribute('aria-expanded', next ? 'true' : 'false');
    };

    choose(options.find(button => button.classList.contains('is-active')) || options[0]);
    trigger.addEventListener('click', () => setOpen(menu.hidden));
    menu.addEventListener('click', event => {
      const button = event.target.closest('.v1-mode-pill');
      if (!button || !strip.contains(button)) return;
      choose(button);
      setOpen(false);
    }, true);
    shell.addEventListener('keydown', event => {
      const current = event.target.closest('.v1-mode-pill');
      if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && event.target === trigger) {
        event.preventDefault();
        setOpen(true);
        (options.find(button => button.classList.contains('is-active')) || options[0])?.focus();
        return;
      }
      if (current && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
        event.preventDefault();
        const index = options.indexOf(current);
        const offset = event.key === 'ArrowDown' ? 1 : -1;
        options[(index + offset + options.length) % options.length]?.focus();
      }
      if (event.key === 'Escape' && !menu.hidden) {
        event.preventDefault();
        setOpen(false);
        trigger.focus();
      }
    });
    document.addEventListener('click', event => {
      if (!shell.contains(event.target)) setOpen(false);
    });

    new MutationObserver(() => {
      const active = options.find(button => button.classList.contains('is-active'));
      if (active) choose(active);
    }).observe(strip, {subtree: true, attributes: true, attributeFilter: ['class']});
  }

  function injectNavigation() {
    const primaryStack = document.querySelector('.v1-rail .v1-rail-stack');
    if (primaryStack && !document.querySelector('.crump53-projects-button')) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'v1-rail-button crump53-projects-button';
      button.setAttribute('aria-label', 'Projects');
      button.title = 'Projects';
      button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h6l2 2h8v10H4z"/><path d="M4 7V5h7l2 2"/></svg><span class="v1-rail-label">Projects</span>';
      button.addEventListener('click', () => openStudio('projects'));
      primaryStack.appendChild(button);
    }

    const footer = document.querySelector('.v1-library-footer');
    if (footer && !byId('crump53ProjectsSidebar')) {
      const button = document.createElement('button');
      button.id = 'crump53ProjectsSidebar';
      button.type = 'button';
      button.className = 'sidebar-footer-btn';
      button.innerHTML = '<span>Projects</span>';
      button.addEventListener('click', () => {
        byId('sidebar')?.classList.remove('active');
        byId('sidebarOverlay')?.classList.remove('active');
        openStudio('projects');
      });
      footer.insertBefore(button, footer.firstChild);
    }

    const strip = document.querySelector('.v1-mode-strip');
    if (strip && !byId('crump53DocumentMode')) {
      const createMode = (id, label, handler) => {
        const button = document.createElement('button');
        button.id = id;
        button.type = 'button';
        button.className = 'v1-mode-pill';
        button.innerHTML = `<span>${label}</span>`;
        button.addEventListener('click', event => {
          event.preventDefault();
          event.stopPropagation();
          handler();
        });
        return button;
      };
      const filesPill = strip.querySelector('[data-v1-command="file"]');
      const documentButton = createMode('crump53DocumentMode', 'Document', () => window.CrumpDocumentStudio?.open?.());
      const manuscriptButton = createMode('crump53ManuscriptMode', 'Manuscript', () => openStudio('manuscripts'));
      const videoButton = createMode('crump53VideoMode', 'Video', () => openStudio('video'));
      strip.insertBefore(documentButton, filesPill || null);
      strip.insertBefore(manuscriptButton, filesPill || null);
      strip.insertBefore(videoButton, filesPill || null);
    }
    enhanceToolMenu(strip);
  }

  function injectStudio() {
    if (byId('crump53Studio')) return;
    const overlay = document.createElement('div');
    overlay.id = 'crump53Studio';
    overlay.className = 'crump53-overlay';
    overlay.hidden = true;
    overlay.innerHTML = `
      <section class="crump53-sheet" id="crump53Sheet" role="dialog" aria-modal="false" aria-label="Ask Crump Projects" data-crump53-section="projects">
        <header class="crump53-sheet-head">
          <div class="crump53-sheet-identity">
            <button type="button" class="crump53-project-back" id="crump53ProjectBack" hidden aria-label="Back to all Projects">‹ <span>Projects</span></button>
            <div><div class="crump53-kicker" id="crump53WorkspaceKicker">WORKSPACE</div><strong id="crump53WorkspaceTitle" tabindex="-1">Projects</strong></div>
          </div>
          <button type="button" class="crump53-close" id="crump53Close" aria-label="Close">×</button>
        </header>
        <div class="crump53-sheet-body">
          <section class="crump53-panel" data-crump53-panel="projects">
            <div class="crump53-grid">
              <div class="crump53-card crump53-project-index-card" id="crump53ProjectIndexCard">
                <div class="crump53-section-head">
                  <div>
                    <h3>Your projects</h3>
                    <p>Each Project keeps its own instructions, files, conversations, and durable context.</p>
                  </div>
                  <div class="crump53-section-actions">
                    <button class="crump53-button" type="button" id="crump53OpenFiles">Files</button>
                    <button class="crump53-button" type="button" id="crump53CreateProject">New Project</button>
                  </div>
                </div>
                <div id="crump53ProjectList" class="crump53-list"></div>
              </div>
              <div class="crump53-card crump53-project-detail-card" id="crump53ProjectDetailCard">
                <div class="crump53-project-hero" id="crump53ProjectHero" hidden>
                  <div>
                    <div class="crump53-kicker">PROJECT WORKSPACE</div>
                    <h2 id="crump53ProjectWorkspaceName" tabindex="-1">Project</h2>
                    <p id="crump53ProjectWorkspaceDescription">Everything for this Project stays together.</p>
                  </div>
                  <div class="crump53-project-hero-actions">
                    <button class="crump53-button is-primary" type="button" id="crump53StartProjectChat">New chat in this Project</button>
                    <button class="crump53-button" type="button" id="crump53UseProject">Use in current conversation</button>
                  </div>
                </div>
                <details class="crump53-project-settings" id="crump53ProjectSettings" open>
                  <summary>
                    <span id="crump53ProjectFormTitle">New project</span>
                    <small id="crump53ProjectSettingsHint">Name it, describe it, and set the context Crump should keep.</small>
                  </summary>
                  <form id="crump53ProjectForm" class="crump53-form">
                    <label class="crump53-label">Name<input id="crump53ProjectName" class="crump53-input" maxlength="100" required></label>
                    <label class="crump53-label">Description<textarea id="crump53ProjectDescription" class="crump53-textarea" maxlength="1200"></textarea></label>
                    <label class="crump53-label">Project instructions<textarea id="crump53ProjectInstructions" class="crump53-textarea" maxlength="12000" placeholder="Canon, tone, goals, rules, constraints..."></textarea></label>
                    <div class="crump53-actions">
                      <button class="crump53-button is-primary" type="submit">Save project</button>
                      <button class="crump53-button" type="button" id="crump53NewProject">Create another</button>
                    </div>
                    <div id="crump53ProjectStatus" class="crump53-status" aria-live="polite"></div>
                  </form>
                </details>
              </div>
            </div>
            <div class="crump53-card crump53-saved-files-card" id="crump53SavedFilesCard">
              <div class="crump53-kicker">PRIVATE FILES</div>
              <div class="crump53-library-head">
                <div>
                  <h3>Your files</h3>
                  <p>Documents, images, video, exports, and uploads stay private and available across devices. Books and manuscripts live separately in Library.</p>
                </div>
                <button type="button" class="crump53-button" id="crump53RefreshLibrary">Refresh</button>
              </div>
              <div class="crump53-library-filters" role="group" aria-label="Filter saved files">
                <button type="button" class="crump53-library-filter is-active" data-library-filter="all">All</button>
                <button type="button" class="crump53-library-filter" data-library-filter="video">Videos</button>
                <button type="button" class="crump53-library-filter" data-library-filter="image">Images</button>
                <button type="button" class="crump53-library-filter" data-library-filter="document">Documents</button>
              </div>
              <div id="crump53LibraryStatus" class="crump53-status" aria-live="polite"></div>
              <div id="crump53LibraryGrid" class="crump53-library-grid"></div>
            </div>
            <div class="crump53-card" id="crump53ProjectConversationsCard" hidden style="margin-top:16px">
              <div class="crump53-section-head">
                <div>
                  <h3>Conversations</h3>
                  <p>Continue any conversation you kept in this Project without rebuilding the context.</p>
                </div>
                <span id="crump53ProjectConversationCount" class="crump53-count-badge"></span>
              </div>
              <div id="crump53ProjectConversationList" class="crump53-list" aria-live="polite"></div>
            </div>
            <div class="crump53-card" id="crump53ProjectContextCard" hidden style="margin-top:16px">
              <h3>Canon & project notes</h3>
              <p>Save durable facts, rules, timeline details, or decisions that Crump should keep isolated to this Project.</p>
              <div class="crump53-grid">
                <div class="crump53-form">
                  <label class="crump53-label">Type<select id="crump53ContextKind" class="crump53-select"><option value="canon">Canon</option><option value="rule">Rule / constraint</option><option value="timeline">Timeline</option><option value="note">Note</option></select></label>
                  <label class="crump53-label">Label<input id="crump53ContextLabel" class="crump53-input" maxlength="120" placeholder="Optional short label"></label>
                  <label class="crump53-label">Details<textarea id="crump53ContextContent" class="crump53-textarea" maxlength="16000" placeholder="A fact, continuity rule, decision, character detail, requirement, or other durable Project context..."></textarea></label>
                  <div class="crump53-actions"><button type="button" class="crump53-button is-primary" id="crump53AddContext">Add to Project</button></div>
                  <div id="crump53ContextStatus" class="crump53-status" aria-live="polite"></div>
                </div>
                <div><div id="crump53ContextList" class="crump53-list"></div></div>
              </div>
            </div>
          </section>

          <section class="crump53-panel" data-crump53-panel="manuscripts" hidden>
            <div id="crump53ManuscriptNoProject" class="crump53-note">Choose an active Project first. Manuscripts stay isolated inside their Project. <button type="button" class="crump53-button" id="crump53OpenProjectsFromManuscript">Open Projects</button></div>
            <div id="crump53ManuscriptWorkspace" hidden>
              <div class="crump53-grid">
                <div class="crump53-card">
                  <h3>Manuscripts</h3>
                  <p>Plan the whole work, draft chapter by chapter, and return tomorrow without rebuilding context.</p>
                  <div class="crump53-note">Everyone can create and export manuscripts. Planning costs 4 credits and drafting costs 8 on Free; Professional and Enterprise include daily planning and drafting allowances.</div>
                  <div id="crump53ManuscriptList" class="crump53-list"></div>
                  <div class="crump53-actions" style="margin-top:10px">
                    <button type="button" class="crump53-button is-primary" id="crump53NewManuscript">New manuscript</button>
                  </div>
                </div>
                <div class="crump53-card">
                  <div id="crump53ManuscriptCreate" class="crump53-form">
                    <h3>Create manuscript</h3>
                    <label class="crump53-label">Title<input id="crump53ManuscriptTitle" class="crump53-input" maxlength="180"></label>
                    <label class="crump53-label">Author<input id="crump53ManuscriptAuthor" class="crump53-input" maxlength="160"></label>
                    <label class="crump53-label">What should this manuscript become?<textarea id="crump53ManuscriptPremise" class="crump53-textarea" maxlength="12000" placeholder="Premise, genre, audience, tone, ending direction, constraints, or simply: surprise me..."></textarea></label>
                    <div class="crump53-grid crump53-compact-grid">
                      <label class="crump53-label">Target words<input id="crump53TargetWords" class="crump53-input" type="number" min="20000" max="150000" step="5000" value="80000"></label>
                      <label class="crump53-label">Planned chapters<input id="crump53ChapterCount" class="crump53-input" type="number" min="8" max="80" value="28"></label>
                    </div>
                    <label class="crump53-label">Trim size<select id="crump53Trim" class="crump53-select"><option value="6x9">6 × 9 in</option><option value="5x8">5 × 8 in</option><option value="5.25x8">5.25 × 8 in</option><option value="5.5x8.5">5.5 × 8.5 in</option><option value="6.14x9.21">6.14 × 9.21 in</option><option value="7x10">7 × 10 in</option><option value="8x10">8 × 10 in</option><option value="8.5x11">8.5 × 11 in</option></select></label>
                    <button type="button" class="crump53-button is-primary" id="crump53CreateManuscript">Create & plan</button>
                  </div>
                  <div id="crump53ManuscriptEditor" hidden>
                    <h3 id="crump53EditorTitle">Manuscript</h3>
                    <div id="crump53ManuscriptProgress" class="crump53-progress" aria-live="polite"></div>
                    <div id="crump53ManuscriptRun" class="crump53-note" hidden aria-live="polite"></div>
                    <div class="crump53-actions" style="margin-bottom:10px">
                      <select id="crump53FullDraftFormat" class="crump53-select" aria-label="Automatic export format"><option value="docx">Full draft + DOCX</option><option value="pdf">Full draft + PDF</option><option value="epub">Full draft + EPUB</option></select>
                      <button type="button" class="crump53-button is-primary" id="crump53StartFullDraft">Write full manuscript</button>
                      <button type="button" class="crump53-button" id="crump53PauseFullDraft" hidden>Pause</button>
                      <button type="button" class="crump53-button" id="crump53ResumeFullDraft" hidden>Resume</button>
                      <button type="button" class="crump53-button" id="crump53CancelFullDraft" hidden>Cancel</button>
                    </div>
                    <div id="crump53BlueprintPanel" class="crump53-blueprint-panel">
                      <label class="crump53-label">Manuscript brief<textarea id="crump53BlueprintBrief" class="crump53-textarea" maxlength="12000" placeholder="Describe the complete work Crump should plan..."></textarea></label>
                      <div class="crump53-actions">
                        <input id="crump53BlueprintTarget" class="crump53-input crump53-number-input" type="number" min="20000" max="150000" step="5000" value="80000" aria-label="Target words">
                        <input id="crump53BlueprintChapters" class="crump53-input crump53-number-input" type="number" min="8" max="80" value="28" aria-label="Chapter count">
                        <button type="button" class="crump53-button" id="crump53PlanManuscript">Plan chapters with Crump</button>
                      </div>
                    </div>
                    <div class="crump53-actions" style="margin-bottom:10px">
                      <button type="button" class="crump53-button" id="crump53AddChapter">Add chapter</button>
                      <button type="button" class="crump53-button is-primary" id="crump53DraftNext">Draft next chapter</button>
                      <button type="button" class="crump53-button" data-crump53-export="docx">KDP DOCX</button>
                      <button type="button" class="crump53-button" data-crump53-export="pdf">KDP PDF</button>
                      <button type="button" class="crump53-button" data-crump53-export="epub">Kindle EPUB</button>
                    </div>
                    <div id="crump53SectionList" class="crump53-list" style="margin-bottom:12px"></div>
                    <div id="crump53SectionEditor" hidden>
                      <label class="crump53-label">Section title<input id="crump53SectionTitle" class="crump53-input"></label>
                      <label class="crump53-label">Manuscript text<textarea id="crump53SectionContent" class="crump53-textarea crump53-editor"></textarea></label>
                      <label class="crump53-label">Direction for Crump <textarea id="crump53DraftInstruction" class="crump53-textarea" maxlength="5000" placeholder="Optional: pacing, scene goals, POV, length, continuity notes, or what should happen next..."></textarea></label>
                      <div class="crump53-actions">
                        <button type="button" class="crump53-button is-primary" id="crump53SaveSection">Save</button>
                        <button type="button" class="crump53-button" id="crump53DraftSection">Draft with Crump</button>
                      </div>
                    </div>
                    <div id="crump53ManuscriptStatus" class="crump53-status" aria-live="polite"></div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="crump53-panel" data-crump53-panel="library" hidden></section>

          <section class="crump53-panel" data-crump53-panel="video" hidden>
            <div class="crump53-card">
              <div class="crump53-kicker">VIDEO STUDIO</div>
              <h3>Create a scene. Keep directing.</h3>
              <p>Pick the experience you need. Crump handles the provider, saves the result privately, and keeps compatible scenes ready to continue.</p>
              <div class="crump53-video-engine-guide" aria-label="Video engine guide">
                <div class="crump53-video-engine-card is-active" data-video-engine-card="quick"><strong>Quick</strong><span>Fast short clips. Best when you just need a strong first take.</span></div>
                <div class="crump53-video-engine-card" data-video-engine-card="extendable"><strong>Extendable</strong><span>Built for scenes that need another shot after the first clip ends.</span></div>
                <div class="crump53-video-engine-card" data-video-engine-card="cinematic"><strong>Cinematic</strong><span>Runway Gen-4.5 for premium 5- or 10-second generations.</span></div>
              </div>
              <form id="crump53VideoForm" class="crump53-form">
                <div class="crump53-grid">
                  <label class="crump53-label">Engine<select id="crump53VideoEngine" class="crump53-select">
                    <option value="quick">Quick · Veo Lite</option>
                    <option value="extendable">Extendable · Veo Fast + Continue</option>
                    <option value="cinematic">Cinematic · Runway Gen-4.5</option>
                  </select></label>
                  <label class="crump53-label" id="crump53VideoDurationWrap" hidden>Duration<select id="crump53VideoDuration" class="crump53-select"><option value="5">5 seconds · 60 credits</option><option value="10">10 seconds · 120 credits · Enterprise</option></select></label>
                </div>
                <label class="crump53-label">Prompt<textarea id="crump53VideoPrompt" class="crump53-textarea" maxlength="4000" placeholder="Describe the scene, subject, camera movement, atmosphere, and sound..."></textarea></label>
                <div class="crump53-grid">
                  <label class="crump53-label">Aspect ratio<select id="crump53VideoAspect" class="crump53-select"><option value="16:9">Landscape 16:9</option><option value="9:16">Portrait 9:16</option></select></label>
                  <label class="crump53-label">Resolution<select id="crump53VideoResolution" class="crump53-select"><option value="720p">720p · 60 credits</option><option value="1080p">1080p · 90 credits</option></select></label>
                </div>
                <div class="crump53-note" id="crump53VideoCostNote">Quick video uses Veo Lite. 720p costs 60 credits and 1080p costs 90 credits. Every generation spends Crump Credits.</div>
                <a class="crump53-provider-attribution" id="crump53RunwayAttribution" href="https://runwayml.com" target="_blank" rel="noopener" hidden>Powered by Runway</a>
                <div class="crump53-actions"><button class="crump53-button is-primary" type="submit" id="crump53GenerateVideo">Create video</button><span id="crump53VideoEntitlement" class="crump53-lock">Checking access…</span></div>
                <div id="crump53VideoStatus" class="crump53-status" aria-live="polite"></div>
              </form>
              <div id="crump53VideoResult"></div>
            </div>
          </section>
        </div>
      </section>`;
    document.body.appendChild(overlay);

    byId('crump53Close')?.addEventListener('click', closeStudio);
    overlay.addEventListener('click', event => { if (event.target === overlay) closeStudio(); });
    byId('crump53ProjectBack')?.addEventListener('click', showProjectIndex);
    byId('crump53CreateProject')?.addEventListener('click', resetProjectForm);
    byId('crump53OpenFiles')?.addEventListener('click', openProjectFiles);
    byId('crump53StartProjectChat')?.addEventListener('click', startProjectConversation);
    byId('crump53ProjectForm')?.addEventListener('submit', saveProject);
    byId('crump53UseProject')?.addEventListener('click', activateSelectedProject);
    byId('crump53NewProject')?.addEventListener('click', resetProjectForm);
    byId('crump53AddContext')?.addEventListener('click', addProjectContext);
    byId('crump53NewManuscript')?.addEventListener('click', showManuscriptCreate);
    byId('crump53OpenProjectsFromManuscript')?.addEventListener('click', () => openStudio('projects'));
    byId('crump53CreateManuscript')?.addEventListener('click', createManuscript);
    byId('crump53PlanManuscript')?.addEventListener('click', planManuscript);
    byId('crump53AddChapter')?.addEventListener('click', addChapter);
    byId('crump53DraftNext')?.addEventListener('click', draftNextSection);
    byId('crump53StartFullDraft')?.addEventListener('click', startFullManuscript);
    byId('crump53PauseFullDraft')?.addEventListener('click', () => controlManuscriptRun('pause'));
    byId('crump53ResumeFullDraft')?.addEventListener('click', () => controlManuscriptRun('resume'));
    byId('crump53CancelFullDraft')?.addEventListener('click', () => controlManuscriptRun('cancel'));
    byId('crump53SaveSection')?.addEventListener('click', saveSection);
    byId('crump53DraftSection')?.addEventListener('click', draftSection);
    overlay.querySelectorAll('[data-crump53-export]').forEach(button => {
      button.addEventListener('click', () => exportManuscript(button.dataset.crump53Export));
    });
    byId('crump53VideoForm')?.addEventListener('submit', startVideo);
    byId('crump53VideoEngine')?.addEventListener('change', updateVideoStudio);
    byId('crump53VideoDuration')?.addEventListener('change', updateVideoStudio);
    byId('crump53VideoResolution')?.addEventListener('change', updateVideoStudio);
    byId('crump53RefreshLibrary')?.addEventListener('click', () => void refreshLibrary());
    overlay.querySelectorAll('[data-library-filter]').forEach(button => {
      button.addEventListener('click', () => {
        state.libraryFilter = button.dataset.libraryFilter || 'all';
        overlay.querySelectorAll('[data-library-filter]').forEach(item => {
          item.classList.toggle('is-active', item === button);
        });
        renderLibrary();
      });
    });
  }

  const STUDIO_SECTION_META = Object.freeze({
    projects: {kicker: 'WORKSPACE', title: 'Projects', label: 'Ask Crump Projects'},
    manuscripts: {kicker: 'LONG-FORM', title: 'Manuscripts', label: 'Ask Crump Manuscripts'},
    video: {kicker: 'MOTION', title: 'Video Studio', label: 'Ask Crump Video Studio'},
    library: {kicker: 'PRIVATE LIBRARY', title: 'Library', label: 'Ask Crump Library'},
  });

  function configureStudioSection(tab) {
    const section = Object.hasOwn(STUDIO_SECTION_META, tab) ? tab : 'projects';
    const meta = STUDIO_SECTION_META[section];
    const sheet = byId('crump53Sheet');
    const kicker = byId('crump53WorkspaceKicker');
    const title = byId('crump53WorkspaceTitle');
    if (sheet) {
      sheet.dataset.crump53Section = section;
      sheet.setAttribute('aria-label', meta.label);
    }
    if (kicker) kicker.textContent = meta.kicker;
    if (title) title.textContent = meta.title;
    return section;
  }

  function openStudio(tab = 'projects', {preserveProjectRoute = false} = {}) {
    const studio = byId('crump53Studio');
    if (!studio) return;
    const section = configureStudioSection(tab);
    studio.hidden = false;
    document.body.style.overflow = 'hidden';
    selectStudioPanel(section);
    if (section === 'projects') {
      if (!preserveProjectRoute && readProjectRoute()) writeProjectRoute('', {replace: true});
      setProjectView('index', {focus: false});
      void refreshProjects();
    } else if (section === 'manuscripts') {
      void refreshProjects().then(() => {
        const currentSection = byId('crump53Sheet')?.dataset.crump53Section;
        if (!byId('crump53Studio')?.hidden && currentSection === 'manuscripts') {
          void refreshManuscripts();
        }
      });
    } else if (section === 'video') {
      void refreshFeatures();
    }
  }

  async function openProject(projectId) {
    const normalizedProjectId = String(projectId || '').trim();
    if (!normalizedProjectId) {
      openStudio('projects');
      return false;
    }
    const studio = byId('crump53Studio');
    if (!studio) return false;
    configureStudioSection('projects');
    studio.hidden = false;
    document.body.style.overflow = 'hidden';
    selectStudioPanel('projects');

    let project = state.projects.find(item => String(item.id || '') === normalizedProjectId);
    if (!project && String(state.activeProject?.id || '') === normalizedProjectId) {
      project = state.activeProject;
      state.projects = [project, ...state.projects.filter(item => String(item.id || '') !== normalizedProjectId)];
    }
    if (!project) {
      await refreshProjects();
      project = state.projects.find(item => String(item.id || '') === normalizedProjectId);
    }
    if (!project) {
      setProjectView('index', {focus: false});
      setStatus('crump53ProjectStatus', 'That Project could not be opened. Refresh Projects and try again.', true);
      return false;
    }
    return selectProject(normalizedProjectId);
  }

  function closeStudio() {
    const studio = byId('crump53Studio');
    if (studio) studio.hidden = true;
    if (readProjectRoute()) writeProjectRoute('', {replace: true});
    document.querySelectorAll('#crump53LibraryGrid video').forEach(video => video.pause());
    document.body.style.overflow = '';
    if (state.manuscriptPollTimer) window.clearTimeout(state.manuscriptPollTimer);
    state.manuscriptPollTimer = null;
  }

  function selectStudioPanel(tab) {
    if (tab !== 'library') {
      document.querySelectorAll('#crump53LibraryGrid video').forEach(video => video.pause());
    }
    document.querySelectorAll('[data-crump53-panel]').forEach(node => {
      node.hidden = node.dataset.crump53Panel !== tab;
    });
    if (tab === 'manuscripts') {
      scheduleManuscriptPoll();
    }
    if (tab === 'video') {
      const pendingJob = readStoredVideoJob();
      if (pendingJob) pollVideo(pendingJob);
    }
    if (tab === 'library') void window.CrumpLibrary57?.refresh?.();
  }

  function selectedVideoFeature() {
    const engine = byId('crump53VideoEngine')?.value || 'quick';
    const resolution = byId('crump53VideoResolution')?.value || '720p';
    const duration = Number(byId('crump53VideoDuration')?.value || 5);
    if (engine === 'extendable') return 'video_extendable';
    if (engine === 'cinematic') return duration === 10 ? 'video_cinematic_10' : 'video_cinematic_5';
    return resolution === '1080p' ? 'video_hd' : 'video';
  }

  function updateVideoStudio() {
    const engine = byId('crump53VideoEngine')?.value || 'quick';
    const resolution = byId('crump53VideoResolution');
    const durationWrap = byId('crump53VideoDurationWrap');
    const duration = Number(byId('crump53VideoDuration')?.value || 5);
    const prompt = byId('crump53VideoPrompt');
    const attribution = byId('crump53RunwayAttribution');
    const costNote = byId('crump53VideoCostNote');
    const label = byId('crump53VideoEntitlement');

    document.querySelectorAll('[data-video-engine-card]').forEach(card => {
      card.classList.toggle('is-active', card.dataset.videoEngineCard === engine);
    });

    if (durationWrap) durationWrap.hidden = engine !== 'cinematic';
    if (attribution) attribution.hidden = engine !== 'cinematic';
    if (prompt) prompt.maxLength = engine === 'cinematic' ? 1000 : 4000;

    if (resolution) {
      const hd = resolution.querySelector('option[value="1080p"]');
      if (engine === 'quick') {
        if (hd) hd.disabled = false;
        resolution.disabled = false;
      } else {
        resolution.value = '720p';
        if (hd) hd.disabled = true;
        resolution.disabled = true;
      }
      const sd = resolution.querySelector('option[value="720p"]');
      if (sd) {
        sd.textContent = engine === 'extendable'
          ? '720p · 80 credits'
          : engine === 'cinematic'
            ? `720p · ${duration === 10 ? 120 : 60} credits`
            : '720p · 60 credits';
      }
    }

    const featureCode = selectedVideoFeature();
    const feature = state.features?.features?.[featureCode];
    if (costNote) {
      costNote.classList.toggle('crump53-founder-note', Boolean(state.features?.internalAccess));
      if (state.features?.internalAccess) {
        costNote.textContent = 'Founder Lab active · App credits are bypassed. Provider usage is still owner-funded and protected by server budget limits.';
      } else if (engine === 'extendable') {
        costNote.textContent = 'Extendable uses Veo 3.1 Fast at 720p. Starting the scene costs 80 credits; each native continuation costs 80 credits and adds about 7 seconds while the provider reference and private-storage guard remain available.';
      } else if (engine === 'cinematic') {
        costNote.textContent = duration === 10
          ? 'Cinematic uses Runway Gen-4.5. The 10-second mode costs 120 credits and requires Enterprise.'
          : 'Cinematic uses Runway Gen-4.5. The 5-second mode costs 60 credits and requires Professional or Enterprise.';
      } else {
        costNote.textContent = 'Quick uses Veo Lite. 720p costs 60 credits and 1080p costs 90 credits. Use Extendable when you know the scene needs to keep going.';
      }
    }
    if (label && state.features) {
      if (!feature?.configured) label.textContent = engine === 'cinematic' ? 'Runway is not configured yet' : 'Video provider not configured';
      else if (state.features.internalAccess) label.textContent = 'Founder Lab · metering bypassed';
      else if (!feature?.entitled) label.textContent = `${feature?.minimumTier === 'enterprise' ? 'Enterprise' : 'Professional'} plan required`;
      else label.textContent = `Ready · ${state.features.creditBalance ?? 0} credits`;
    }
  }

  async function refreshFeatures() {
    try {
      const data = await api('/api/features');
      state.features = data;
      updateVideoStudio();
    } catch (_) {
      state.features = null;
    }
  }

  let projectRefreshPromise = null;

  async function refreshProjects() {
    if (projectRefreshPromise) return projectRefreshPromise;
    projectRefreshPromise = (async () => {
      try {
        const data = await api('/api/projects', {timeoutMs: PROJECT_READ_TIMEOUT_MS});
        state.projects = Array.isArray(data.projects) ? data.projects : [];
        const stored = state.activeProject?.id || readStoredProject();
        state.activeProject = state.projects.find(item => item.id === stored) || null;
        if (!state.activeProject && stored) storeProject('');
        renderProjectList(data.limit);
        renderProjectIndicator();
        renderManuscriptProjectState();
        const requestedProjectId = readProjectRoute();
        if (requestedProjectId) {
          const requestedProject = state.projects.find(
            item => String(item.id || '') === requestedProjectId,
          );
          if (requestedProject) {
            selectProject(requestedProjectId, {updateRoute: false, focus: false});
            return;
          }
          writeProjectRoute('', {replace: true});
          setStatus('crump53ProjectStatus', 'That Project is no longer available.', true);
        }
        const projectsPanel = document.querySelector('[data-crump53-panel="projects"]');
        if (!byId('crump53Studio')?.hidden && !projectsPanel?.hidden && state.activeProject && state.projectView === 'detail') {
          renderActiveProjectWorkspace({open: false});
        }
      } catch (error) {
        const message = error.message || 'Could not load Projects.';
        setStatus('crump53ProjectStatus', message, true);
        renderRetryableListError(
          byId('crump53ProjectList'),
          message,
          'Retry loading Projects',
          () => refreshProjects(),
        );
      }
    })();
    try {
      return await projectRefreshPromise;
    } finally {
      projectRefreshPromise = null;
    }
  }

  function currentConversation() {
    return (Array.isArray(window.chats) ? window.chats : []).find(
      item => item.id === window.currentChatId || item.chat_id === window.currentChatId,
    ) || null;
  }

  function projectNameForConversation(chat) {
    const title = String(chat?.title || '').replace(/\s+/g, ' ').trim();
    if (title && title.toLowerCase() !== 'new conversation') return title.slice(0, 100);
    const firstPrompt = (Array.isArray(chat?.messages) ? chat.messages : []).find(
      message => message?.role === 'user' && String(message?.content || '').trim(),
    );
    return String(firstPrompt?.content || 'Continued work').replace(/\s+/g, ' ').trim().slice(0, 100);
  }

  async function keepConversation(options = {}) {
    const chat = currentConversation();
    const chatId = String(chat?.id || chat?.chat_id || '').trim();
    if (!chatId) throw new Error('Open a conversation before saving it to a Project.');
    const hasExplicitTarget = Object.prototype.hasOwnProperty.call(options, 'projectId');
    const targetProjectId = hasExplicitTarget
      ? String(options.projectId || '').trim()
      : String(state.activeProject?.id || '').trim();

    try {
      const sync = await window.syncChatsToServer?.();
      if (sync?.success === false) throw new Error('This conversation is still syncing. Try again in a moment.');

      const data = targetProjectId
        ? await api(`/api/projects/${targetProjectId}/chats`, {
            method: 'POST',
            body: {chatId},
            timeoutMs: PROJECT_SAVE_TIMEOUT_MS,
          })
        : await api('/api/projects', {
            method: 'POST',
            body: {
              name: projectNameForConversation(chat),
              description: 'Continued from an Ask Crump conversation.',
              chatId,
            },
            timeoutMs: PROJECT_SAVE_TIMEOUT_MS,
          });
      state.activeProject = data.project;
      state.editingProject = data.project;
      storeProject(data.project.id);
      if (options.notify !== false) {
        window.showToast?.(`Saved to ${data.project.name}.`, 'success');
      }
      if (options.refresh !== false) void refreshProjects();
      return {success: true, project: data.project};
    } catch (error) {
      if (featureAccessCode(error) === 'PROJECT_LIMIT_REACHED') {
        openFeatureAccessRecovery(error);
      }
      if (options.notify !== false) {
        window.showToast?.(error.message || 'The conversation could not be saved.', 'error');
      }
      throw error;
    }
  }

  async function keepArtifact(file, options = {}) {
    const fileId = String(file?.id || '').trim();
    if (!fileId) throw new Error('This file is not ready to add to a Project yet.');
    const hasExplicitTarget = Object.prototype.hasOwnProperty.call(options, 'projectId');
    const targetProjectId = hasExplicitTarget
      ? String(options.projectId || '').trim()
      : String(state.activeProject?.id || '').trim();

    try {
      const kept = await keepConversation({
        projectId: targetProjectId || null,
        notify: false,
        refresh: false,
      });
      const projectId = String(kept?.project?.id || '').trim();
      if (!projectId) throw new Error('Choose a Project before adding this file.');
      const data = await api(`/api/projects/${encodeURIComponent(projectId)}/files`, {
        method: 'POST',
        body: {fileId, role: 'generated_document'},
        timeoutMs: PROJECT_SAVE_TIMEOUT_MS,
      });
      window.showToast?.(`Added to ${kept.project.name}.`, 'success');
      void refreshProjects();
      return {success: true, project: kept.project, file: data.file};
    } catch (error) {
      window.showToast?.(error.message || 'The file could not be added to a Project.', 'error');
      throw error;
    }
  }

  function renderProjectList(limit) {
    const list = byId('crump53ProjectList');
    if (!list) return;
    if (!state.projects.length) {
      list.innerHTML = '<div class="crump53-note">No projects yet. Create one on the right.</div>';
      return;
    }
    list.innerHTML = state.projects.map(item => `
      <a href="${escapeHtml(projectRouteHref(item.id))}" class="crump53-list-button crump53-project-list-button ${String(state.activeProject?.id || '') === String(item.id || '') ? 'is-active' : ''}" data-project-id="${escapeHtml(item.id)}" aria-label="Open Project ${escapeHtml(item.name)}" ${String(state.activeProject?.id || '') === String(item.id || '') ? 'aria-current="page"' : ''}>
        <span>${escapeHtml(item.name)}</span><small>Open&nbsp;›</small>
      </a>`).join('') + (Number(limit) > 0
        ? `<div class="crump53-status">${state.projects.length} / ${limit} active projects</div>`
        : (Number(limit) < 0 ? '<div class="crump53-status">Founder Lab · unlimited project workspaces</div>' : ''));
    wireProjectLinks(list);
  }

  function wireProjectLinks(list) {
    list.querySelectorAll('[data-project-id]').forEach(link => {
      link.addEventListener('click', event => {
        // Preserve normal browser behavior for new-tab/window modifiers. A regular
        // tap or click is owned directly by its Project row so list re-renders and
        // ancestor menu handlers cannot turn the interaction into a silent no-op.
        if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        if (link.getAttribute('aria-busy') === 'true') return;
        link.setAttribute('aria-busy', 'true');
        const action = link.querySelector('small');
        if (action) action.textContent = 'Opening…';
        const opened = selectProject(link.dataset.projectId);
        if (!opened) window.location.assign(link.href);
      });
    });
  }

  function selectProject(projectId, {updateRoute = true, replaceRoute = false, focus = true, reveal = true} = {}) {
    const normalizedProjectId = String(projectId || '').trim();
    const project = state.projects.find(item => String(item.id || '') === normalizedProjectId);
    if (!project) {
      setStatus('crump53ProjectStatus', 'That Project could not be opened. Refresh Projects and try again.', true);
      window.showToast?.('That Project could not be opened. Refresh Projects and try again.', 'error');
      return false;
    }
    state.activeProject = project;
    state.editingProject = project;
    storeProject(project.id);
    const settings = byId('crump53ProjectSettings');
    if (settings) settings.open = false;
    if (updateRoute) writeProjectRoute(project.id, {replace: replaceRoute});
    if (reveal) {
      const studio = byId('crump53Studio');
      configureStudioSection('projects');
      if (studio) studio.hidden = false;
      document.body.style.overflow = 'hidden';
      selectStudioPanel('projects');
    }
    renderProjectIndicator();
    setProjectView('detail', {focus: false});
    renderActiveProjectWorkspace({open: focus});
    return true;
  }

  function setProjectView(view, {focus = true} = {}) {
    const normalized = ['detail', 'new', 'files'].includes(view) ? view : 'index';
    state.projectView = normalized;
    const panel = document.querySelector('[data-crump53-panel="projects"]');
    const sheet = byId('crump53Sheet');
    const back = byId('crump53ProjectBack');
    const kicker = byId('crump53WorkspaceKicker');
    const title = byId('crump53WorkspaceTitle');
    const isOpen = normalized !== 'index';
    panel?.classList.toggle('is-project-open', isOpen);
    if (sheet) sheet.dataset.projectView = normalized;
    if (back) back.hidden = !isOpen;
    if (normalized === 'files') {
      if (kicker) kicker.textContent = 'PROJECTS';
      if (title) title.textContent = 'Files';
      sheet?.setAttribute('aria-label', 'Ask Crump Files');
    } else if (normalized === 'detail' && state.activeProject) {
      if (kicker) kicker.textContent = 'PROJECT';
      if (title) title.textContent = state.activeProject.name || 'Project';
      sheet?.setAttribute('aria-label', `Ask Crump Project: ${state.activeProject.name || 'Project'}`);
    } else if (normalized === 'new') {
      if (kicker) kicker.textContent = 'PROJECTS';
      if (title) title.textContent = 'New Project';
      sheet?.setAttribute('aria-label', 'Create an Ask Crump Project');
    } else {
      if (kicker) kicker.textContent = STUDIO_SECTION_META.projects.kicker;
      if (title) title.textContent = STUDIO_SECTION_META.projects.title;
      sheet?.setAttribute('aria-label', STUDIO_SECTION_META.projects.label);
    }
    const body = sheet?.querySelector('.crump53-sheet-body');
    if (body) body.scrollTop = 0;
    if (!focus) return;
    requestAnimationFrame(() => {
      if (normalized === 'files') byId('crump53RefreshLibrary')?.focus({preventScroll: true});
      else if (normalized === 'detail') byId('crump53ProjectWorkspaceName')?.focus({preventScroll: true});
      else if (normalized === 'new') byId('crump53ProjectName')?.focus({preventScroll: true});
      else byId('crump53ProjectList')?.querySelector('button')?.focus({preventScroll: true});
    });
  }

  function openProjectFiles() {
    setProjectView('files');
    void refreshLibrary();
  }

  function showProjectIndex({updateRoute = true} = {}) {
    setProjectView('index');
    if (!updateRoute || !readProjectRoute()) return;
    if (window.history.state?.askCrumpProjectRoute) window.history.back();
    else writeProjectRoute('', {replace: true});
  }

  function renderActiveProjectWorkspace({open = false} = {}) {
    const project = state.activeProject;
    if (!project) return;
    byId('crump53ProjectName').value = project.name || '';
    byId('crump53ProjectDescription').value = project.description || '';
    byId('crump53ProjectInstructions').value = project.instructions || '';
    byId('crump53ProjectFormTitle').textContent = 'Edit project';
    const hint = byId('crump53ProjectSettingsHint');
    if (hint) hint.textContent = 'Rename this Project, revise its description, or update the instructions Crump keeps with it.';
    const hero = byId('crump53ProjectHero');
    if (hero) hero.hidden = false;
    if (byId('crump53ProjectWorkspaceName')) byId('crump53ProjectWorkspaceName').textContent = project.name || 'Project';
    if (byId('crump53ProjectWorkspaceDescription')) {
      byId('crump53ProjectWorkspaceDescription').textContent =
        project.description || 'Conversations, files, instructions, and durable context for this Project.';
    }
    renderProjectList(state.features?.projectLimit);
    renderManuscriptProjectState();
    if (open || state.projectView === 'detail') setProjectView('detail', {focus: open});
    void refreshProjectContext();
    void refreshProjectConversations();
  }

  function resetProjectForm() {
    byId('crump53ProjectName').value = '';
    byId('crump53ProjectDescription').value = '';
    byId('crump53ProjectInstructions').value = '';
    byId('crump53ProjectFormTitle').textContent = 'New project';
    const hint = byId('crump53ProjectSettingsHint');
    if (hint) hint.textContent = 'Name it, describe it, and set the context Crump should keep.';
    const settings = byId('crump53ProjectSettings');
    if (settings) settings.open = true;
    const hero = byId('crump53ProjectHero');
    if (hero) hero.hidden = true;
    state.editingProject = null;
    const contextCard = byId('crump53ProjectContextCard');
    if (contextCard) contextCard.hidden = true;
    const conversationsCard = byId('crump53ProjectConversationsCard');
    if (conversationsCard) conversationsCard.hidden = true;
    renderProjectList(state.features?.projectLimit);
    setProjectView('new');
  }

  async function refreshProjectConversations() {
    const card = byId('crump53ProjectConversationsCard');
    const list = byId('crump53ProjectConversationList');
    const count = byId('crump53ProjectConversationCount');
    if (!card || !list) return;
    if (!state.activeProject?.id) {
      state.projectConversations = [];
      card.hidden = true;
      list.innerHTML = '';
      if (count) count.textContent = '';
      return;
    }
    card.hidden = false;
    list.innerHTML = '<div class="crump53-note">Loading saved conversations…</div>';
    const projectId = state.activeProject.id;
    try {
      const data = await api(`/api/projects/${projectId}/chats`, {
        timeoutMs: PROJECT_READ_TIMEOUT_MS,
      });
      if (state.activeProject?.id !== projectId) return;
      state.projectConversations = Array.isArray(data.conversations) ? data.conversations : [];
      if (count) count.textContent = String(state.projectConversations.length);
      if (!state.projectConversations.length) {
        list.innerHTML = '<div class="crump53-note">No conversations saved here yet. After a useful result in Ask, choose “Keep in a Project.”</div>';
        return;
      }
      list.innerHTML = state.projectConversations.map(item => {
        const title = String(item.title || 'New conversation').replace(/\s+/g, ' ').trim();
        return `<button type="button" class="crump53-list-button crump53-conversation-button" data-project-chat-id="${escapeHtml(item.chatId)}" aria-label="Continue ${escapeHtml(title)}">
          <span>${escapeHtml(title)}</span><small>Continue</small>
        </button>`;
      }).join('');
      list.querySelectorAll('[data-project-chat-id]').forEach(button => {
        button.addEventListener('click', () => void resumeProjectConversation(button.dataset.projectChatId));
      });
    } catch (error) {
      if (state.activeProject?.id !== projectId) return;
      state.projectConversations = [];
      if (count) count.textContent = '';
      renderRetryableListError(
        list,
        error.message || 'Could not load saved conversations.',
        'Retry loading saved conversations',
        () => refreshProjectConversations(),
      );
    }
  }

  async function resumeProjectConversation(chatId) {
    const normalized = String(chatId || '').trim();
    if (!normalized || typeof window.loadChat !== 'function') {
      window.showToast?.('That conversation is not available yet.', 'error');
      return;
    }
    if (!(Array.isArray(window.chats) && window.chats.some(item => item.id === normalized))) {
      try {
        await window.syncChatsFromServer?.();
      } catch (_) {
        window.showToast?.('Could not sync that conversation on this device yet.', 'error');
        return;
      }
    }
    if (!(Array.isArray(window.chats) && window.chats.some(item => item.id === normalized))) {
      window.showToast?.('That conversation could not be restored on this device yet.', 'error');
      return;
    }
    void window.CrumpAnalytics?.track?.('RecentWorkResumed', {
      eventKey: 'recent-work-resumed',
      source: 'project',
    });
    closeStudio();
    window.loadChat(normalized);
  }

  async function saveProject(event) {
    event.preventDefault();
    const payload = {
      name: byId('crump53ProjectName')?.value || '',
      description: byId('crump53ProjectDescription')?.value || '',
      instructions: byId('crump53ProjectInstructions')?.value || '',
    };
    try {
      setStatus('crump53ProjectStatus', 'Saving…');
      const data = state.editingProject?.id
        ? await api(`/api/projects/${state.editingProject.id}`, {method: 'PATCH', body: payload})
        : await api('/api/projects', {method: 'POST', body: payload});
      state.activeProject = data.project;
      state.editingProject = data.project;
      storeProject(data.project.id);
      state.projectView = 'detail';
      setStatus('crump53ProjectStatus', 'Project saved and selected.');
      await refreshProjects();
      const settings = byId('crump53ProjectSettings');
      if (settings) settings.open = false;
    } catch (error) {
      setFeatureAccessStatus('crump53ProjectStatus', error);
    }
  }

  async function refreshProjectContext() {
    const card = byId('crump53ProjectContextCard');
    const list = byId('crump53ContextList');
    if (!card || !list) return;
    if (!state.activeProject?.id) {
      card.hidden = true;
      list.innerHTML = '';
      return;
    }
    card.hidden = false;
    const projectId = state.activeProject.id;
    try {
      const data = await api(`/api/projects/${projectId}`, {
        timeoutMs: PROJECT_READ_TIMEOUT_MS,
      });
      if (state.activeProject?.id !== projectId) return;
      const rows = Array.isArray(data.context?.canon) ? data.context.canon : [];
      if (!rows.length) {
        list.innerHTML = '<div class="crump53-note">No canon or durable Project notes yet.</div>';
        return;
      }
      list.innerHTML = rows.slice(0, 40).map(item => {
        const kind = escapeHtml(String(item.kind || 'note').toUpperCase());
        const label = escapeHtml(item.label || 'Project context');
        const content = escapeHtml(String(item.content || '').slice(0, 900));
        return `<div class="crump53-context-item"><small>${kind}</small><strong>${label}</strong><p>${content}</p></div>`;
      }).join('');
    } catch (error) {
      if (state.activeProject?.id !== projectId) return;
      renderRetryableListError(
        list,
        error.message || 'Could not load Project context.',
        'Retry loading Project notes',
        () => refreshProjectContext(),
      );
    }
  }

  async function addProjectContext() {
    if (!state.activeProject?.id) {
      setStatus('crump53ContextStatus', 'Choose or save a Project first.', true);
      return;
    }
    const content = byId('crump53ContextContent')?.value?.trim() || '';
    if (!content) {
      setStatus('crump53ContextStatus', 'Add a canon fact, rule, timeline detail, or note first.', true);
      return;
    }
    try {
      setStatus('crump53ContextStatus', 'Saving…');
      await api(`/api/projects/${state.activeProject.id}/context`, {
        method: 'POST',
        body: {
          kind: byId('crump53ContextKind')?.value || 'note',
          label: byId('crump53ContextLabel')?.value || '',
          content,
        },
      });
      if (byId('crump53ContextLabel')) byId('crump53ContextLabel').value = '';
      if (byId('crump53ContextContent')) byId('crump53ContextContent').value = '';
      setStatus('crump53ContextStatus', 'Saved to this Project only.');
      await refreshProjectContext();
    } catch (error) {
      setStatus('crump53ContextStatus', error.message, true);
    }
  }

  function activateSelectedProject() {
    if (!state.activeProject?.id) {
      setStatus('crump53ProjectStatus', 'Choose or save a project first.', true);
      return;
    }
    storeProject(state.activeProject.id);
    renderProjectIndicator();
    setStatus('crump53ProjectStatus', 'New messages will use this project context.');
  }

  function startProjectConversation() {
    if (!state.activeProject?.id) {
      setStatus('crump53ProjectStatus', 'Choose or save a Project first.', true);
      return;
    }
    const name = String(state.activeProject.name || 'Project').replace(/\s+/g, ' ').trim() || 'Project';
    storeProject(state.activeProject.id);
    renderProjectIndicator();
    closeStudio();
    if (window.CrumpBodyV1?.command) window.CrumpBodyV1.command('new');
    else byId('newChatBtn')?.click();
    requestAnimationFrame(() => {
      const input = byId('userInput');
      if (!input) return;
      input.placeholder = `Message Crump in ${name}…`;
      input.focus({preventScroll: true});
    });
    window.showToast?.(`${name} is open. Your next message starts a Project conversation.`, 'success');
  }

  function renderProjectIndicator() {
    document.querySelector('.crump53-active-project')?.remove();
    document.querySelectorAll('.crump53-projects-button').forEach(node => {
      node.classList.toggle('is-active', Boolean(state.activeProject));
    });
    notifyProjectTargetChanged();
    if (!state.activeProject) return;
    const header = document.querySelector('.v1-workspace-context');
    if (!header) return;
    const chip = document.createElement('span');
    chip.className = 'crump53-active-project';
    chip.innerHTML = `<span>${escapeHtml(state.activeProject.name)}</span><button type="button" aria-label="Leave project">×</button>`;
    chip.querySelector('button')?.addEventListener('click', event => {
      event.stopPropagation();
      state.activeProject = null;
      storeProject('');
      renderProjectIndicator();
      renderProjectList(state.features?.projectLimit);
      renderManuscriptProjectState();
      const contextCard = byId('crump53ProjectContextCard');
      if (contextCard) contextCard.hidden = true;
      const conversationsCard = byId('crump53ProjectConversationsCard');
      if (conversationsCard) conversationsCard.hidden = true;
    });
    header.appendChild(chip);
  }

  function renderManuscriptProjectState() {
    const empty = byId('crump53ManuscriptNoProject');
    const workspace = byId('crump53ManuscriptWorkspace');
    if (empty) empty.hidden = Boolean(state.activeProject);
    if (workspace) workspace.hidden = !state.activeProject;
  }

  async function refreshManuscripts() {
    renderManuscriptProjectState();
    if (!state.activeProject?.id) return;
    try {
      const data = await api(`/api/projects/${state.activeProject.id}/manuscripts`);
      state.manuscripts = Array.isArray(data.manuscripts) ? data.manuscripts : [];
      renderManuscriptList();
    } catch (error) {
      setFeatureAccessStatus('crump53ManuscriptStatus', error);
    }
  }

  function renderManuscriptList() {
    const list = byId('crump53ManuscriptList');
    if (!list) return;
    if (!state.manuscripts.length) {
      list.innerHTML = '<div class="crump53-note">No manuscripts in this project yet.</div>';
      return;
    }
    list.innerHTML = state.manuscripts.map(item => `
      <button type="button" class="crump53-list-button ${state.activeManuscript?.id === item.id ? 'is-active' : ''}" data-manuscript-id="${escapeHtml(item.id)}">
        <span>${escapeHtml(item.title)}</span><small>${escapeHtml(item.status || 'draft')}</small>
      </button>`).join('');
    list.querySelectorAll('[data-manuscript-id]').forEach(button => {
      button.addEventListener('click', () => void loadManuscript(button.dataset.manuscriptId));
    });
  }

  function showManuscriptCreate() {
    byId('crump53ManuscriptCreate').hidden = false;
    byId('crump53ManuscriptEditor').hidden = true;
    state.activeManuscript = null;
    state.activeSection = null;
    state.manuscriptRun = null;
    if (state.manuscriptPollTimer) window.clearTimeout(state.manuscriptPollTimer);
    state.manuscriptPollTimer = null;
    renderManuscriptList();
  }

  async function createManuscript() {
    if (!state.activeProject?.id) return;
    const brief = byId('crump53ManuscriptPremise')?.value?.trim() || '';
    if (!brief) {
      setStatus('crump53ManuscriptStatus', 'Describe what the manuscript should become—or tell Crump to surprise you.', true);
      return;
    }
    let manuscriptId = '';
    try {
      setStatus('crump53ManuscriptStatus', 'Creating…');
      const data = await api(`/api/projects/${state.activeProject.id}/manuscripts`, {
        method: 'POST',
        body: {
          title: byId('crump53ManuscriptTitle')?.value || '',
          authorName: byId('crump53ManuscriptAuthor')?.value || '',
          trimCode: byId('crump53Trim')?.value || '6x9',
          premise: brief,
          targetWords: Number(byId('crump53TargetWords')?.value || 80000),
        },
      });
      manuscriptId = data.manuscript.id;
      setStatus('crump53ManuscriptStatus', 'Queueing the complete manuscript plan…');
      await api(`/api/manuscripts/${manuscriptId}/runs`, {
        method: 'POST',
        body: {
          brief,
          targetWords: Number(byId('crump53TargetWords')?.value || 80000),
          chapterCount: Number(byId('crump53ChapterCount')?.value || 28),
          mode: 'outline',
          format: 'docx',
        },
      });
      await refreshManuscripts();
      await loadManuscript(manuscriptId);
      setStatus('crump53ManuscriptStatus', 'Blueprint queued. You can leave this screen and return when it is ready.');
    } catch (error) {
      if (manuscriptId) {
        await refreshManuscripts();
        await loadManuscript(manuscriptId);
      }
      const message = error.data?.creditsRequired
        ? `${error.message} Current balance: ${error.data.creditBalance ?? 0}. The empty manuscript was saved.`
        : error.message;
      setFeatureAccessStatus('crump53ManuscriptStatus', error, message);
    }
  }

  async function loadManuscript(manuscriptId) {
    if (state.manuscriptPollTimer) window.clearTimeout(state.manuscriptPollTimer);
    state.manuscriptPollTimer = null;
    try {
      const data = await api(`/api/manuscripts/${manuscriptId}`);
      state.activeManuscript = data.manuscript;
      state.activeManuscript.sections = Array.isArray(data.sections) ? data.sections : [];
      state.manuscriptProgress = data.progress || null;
      state.manuscriptRun = data.run || null;
      state.activeSection = null;
      byId('crump53ManuscriptCreate').hidden = true;
      byId('crump53ManuscriptEditor').hidden = false;
      byId('crump53SectionEditor').hidden = true;
      byId('crump53EditorTitle').textContent = data.manuscript.title || 'Manuscript';
      const metadata = data.manuscript.metadata && typeof data.manuscript.metadata === 'object' ? data.manuscript.metadata : {};
      if (byId('crump53BlueprintBrief')) byId('crump53BlueprintBrief').value = metadata.premise || '';
      if (byId('crump53BlueprintTarget')) byId('crump53BlueprintTarget').value = String(metadata.targetWords || 80000);
      if (byId('crump53BlueprintChapters')) byId('crump53BlueprintChapters').value = String(metadata.plannedChapterCount || data.sections?.length || 28);
      renderManuscriptList();
      renderSections();
      renderManuscriptProgress();
      renderManuscriptRun();
      scheduleManuscriptPoll();
      return true;
    } catch (error) {
      setStatus('crump53ManuscriptStatus', error.message, true);
      return false;
    }
  }

  function renderManuscriptRun() {
    const node = byId('crump53ManuscriptRun');
    const run = state.manuscriptRun;
    const start = byId('crump53StartFullDraft');
    const pause = byId('crump53PauseFullDraft');
    const resume = byId('crump53ResumeFullDraft');
    const cancel = byId('crump53CancelFullDraft');
    const active = Boolean(run && ['queued', 'running', 'paused', 'awaiting_credits'].includes(run.status));
    if (start) start.hidden = active;
    if (pause) pause.hidden = !run || !['queued', 'running'].includes(run.status);
    if (resume) resume.hidden = !run || !['paused', 'awaiting_credits'].includes(run.status);
    if (cancel) cancel.hidden = !active;
    if (!node) return;
    if (!run) {
      node.hidden = true;
      node.innerHTML = '';
      return;
    }
    const stageLabels = {blueprint: 'Planning chapters', drafting: 'Writing full draft', export: 'Packaging export', complete: 'Complete'};
    const total = Number(run.totalSections || run.chapterCount || 0);
    const completed = Number(run.completedSections || 0);
    const output = run.outputFile?.url
      ? `<a class="crump53-button" href="${escapeHtml(run.outputFile.url)}?download=1">Download ${escapeHtml(String(run.preferredExportFormat || 'file').toUpperCase())}</a>`
      : '';
    const error = run.error ? `<div class="crump53-status is-error">${escapeHtml(run.error)}</div>` : '';
    const creditRecovery = run.status === 'awaiting_credits'
      ? '<button type="button" class="crump53-button" id="crump53ManuscriptCredits">Add credits or compare plans</button>'
      : '';
    node.hidden = false;
    node.innerHTML = `<strong>${escapeHtml(stageLabels[run.stage] || 'Manuscript run')} · ${escapeHtml(run.status || '')}</strong><br><span>${completed} of ${total} chapters drafted. This job is saved and can resume after a timeout or browser close.</span>${error}${output || creditRecovery ? `<div class="crump53-actions" style="margin-top:8px">${creditRecovery}${output}</div>` : ''}`;
    byId('crump53ManuscriptCredits')?.addEventListener('click', () => openFeatureAccessRecovery({
      data: {code: 'CREDITS_REQUIRED'},
    }));
  }

  function scheduleManuscriptPoll() {
    if (state.manuscriptPollTimer) window.clearTimeout(state.manuscriptPollTimer);
    state.manuscriptPollTimer = null;
    if (!state.activeManuscript?.id || !state.manuscriptRun || !['queued', 'running'].includes(state.manuscriptRun.status)) return;
    state.manuscriptPollTimer = window.setTimeout(pollManuscriptRun, 10000);
  }

  async function pollManuscriptRun() {
    const manuscriptId = state.activeManuscript?.id;
    if (!manuscriptId) return;
    try {
      const data = await api(`/api/manuscripts/${manuscriptId}/run`);
      state.manuscriptRun = data.run || null;
      renderManuscriptRun();
      if (state.manuscriptRun && ['completed', 'failed', 'awaiting_credits'].includes(state.manuscriptRun.status)) {
        await loadManuscript(manuscriptId);
        return;
      }
    } catch (error) {
      setStatus('crump53ManuscriptStatus', error.message, true);
    }
    scheduleManuscriptPoll();
  }

  async function startFullManuscript() {
    if (!state.activeManuscript?.id) return;
    const metadata = state.activeManuscript.metadata && typeof state.activeManuscript.metadata === 'object' ? state.activeManuscript.metadata : {};
    const brief = byId('crump53BlueprintBrief')?.value?.trim() || metadata.premise || '';
    try {
      setStatus('crump53ManuscriptStatus', 'Queueing the complete manuscript…');
      const data = await api(`/api/manuscripts/${state.activeManuscript.id}/runs`, {
        method: 'POST',
        body: {
          brief,
          targetWords: Number(byId('crump53BlueprintTarget')?.value || metadata.targetWords || 80000),
          chapterCount: Number(byId('crump53BlueprintChapters')?.value || metadata.plannedChapterCount || 28),
          format: byId('crump53FullDraftFormat')?.value || 'docx',
          mode: 'autopilot',
        },
      });
      state.manuscriptRun = data.run;
      renderManuscriptRun();
      scheduleManuscriptPoll();
      setStatus('crump53ManuscriptStatus', 'Full manuscript queued. It is safe to close this screen.');
    } catch (error) {
      const message = error.data?.creditsRequired
        ? `${error.message} Current balance: ${error.data.creditBalance ?? 0}.`
        : error.message;
      setFeatureAccessStatus('crump53ManuscriptStatus', error, message);
    }
  }

  async function controlManuscriptRun(action) {
    const runId = state.manuscriptRun?.id;
    if (!runId || !['pause', 'resume', 'cancel'].includes(action)) return;
    try {
      const data = await api(`/api/manuscript-runs/${runId}/${action}`, {method: 'POST'});
      state.manuscriptRun = data.run;
      renderManuscriptRun();
      scheduleManuscriptPoll();
      setStatus('crump53ManuscriptStatus', `Manuscript run ${action === 'cancel' ? 'cancelled' : `${action}d`}.`);
    } catch (error) {
      setFeatureAccessStatus('crump53ManuscriptStatus', error);
    }
  }

  function renderSections() {
    const list = byId('crump53SectionList');
    if (!list || !state.activeManuscript) return;
    const sections = state.activeManuscript.sections || [];
    list.innerHTML = sections.length ? sections.map(item => `
      <button type="button" class="crump53-list-button ${state.activeSection?.id === item.id ? 'is-active' : ''}" data-section-id="${escapeHtml(item.id)}">
        <span>${escapeHtml(item.title)}</span><small>${Number(item.word_count || 0).toLocaleString()} words</small>
      </button>`).join('') : '<div class="crump53-note">Add a chapter to start writing.</div>';
    list.querySelectorAll('[data-section-id]').forEach(button => {
      button.addEventListener('click', () => selectSection(button.dataset.sectionId));
    });
    const drafted = sections.some(item => String(item.content || '').trim());
    const blueprint = byId('crump53BlueprintPanel');
    if (blueprint) blueprint.hidden = drafted;
  }

  function localProgress() {
    const sections = state.activeManuscript?.sections || [];
    const metadata = state.activeManuscript?.metadata && typeof state.activeManuscript.metadata === 'object'
      ? state.activeManuscript.metadata : {};
    const wordCount = sections.reduce((total, item) => total + Number(item.word_count || 0), 0);
    const targetWords = Number(metadata.targetWords || state.manuscriptProgress?.targetWords || 80000);
    const draftedSections = sections.filter(item => String(item.content || '').trim()).length;
    return {
      wordCount,
      targetWords,
      wordProgress: Math.min(100, Math.round((wordCount / Math.max(1, targetWords)) * 1000) / 10),
      draftedSections,
      plannedSections: sections.length,
      complete: Boolean(sections.length) && draftedSections === sections.length,
    };
  }

  function renderManuscriptProgress() {
    const node = byId('crump53ManuscriptProgress');
    if (!node) return;
    const progress = {...localProgress(), ...(state.manuscriptProgress || {})};
    const percent = Number(progress.wordProgress || 0);
    node.innerHTML = `
      <div class="crump53-progress-head"><strong>${Number(progress.wordCount || 0).toLocaleString()} / ${Number(progress.targetWords || 0).toLocaleString()} words</strong><span>${percent}%</span></div>
      <div class="crump53-progress-track"><i style="width:${Math.max(0, Math.min(100, percent))}%"></i></div>
      <small>${Number(progress.draftedSections || 0)} of ${Number(progress.plannedSections || 0)} sections drafted${progress.complete ? ' · full draft complete' : ''}</small>`;
  }

  async function planManuscript() {
    if (!state.activeManuscript?.id) return;
    const brief = byId('crump53BlueprintBrief')?.value?.trim() || '';
    if (!brief) {
      setStatus('crump53ManuscriptStatus', 'Add the premise, audience, genre, or direction Crump should plan.', true);
      return;
    }
    try {
      setStatus('crump53ManuscriptStatus', 'Crump is building the complete chapter blueprint…');
      const hasOutlines = Boolean(state.activeManuscript.sections?.length);
      const data = await api(`/api/manuscripts/${state.activeManuscript.id}/blueprint`, {
        method: 'POST',
        body: {
          brief,
          targetWords: Number(byId('crump53BlueprintTarget')?.value || 80000),
          chapterCount: Number(byId('crump53BlueprintChapters')?.value || 28),
          replaceOutlines: hasOutlines,
        },
      });
      state.activeManuscript = data.manuscript || state.activeManuscript;
      state.activeManuscript.sections = Array.isArray(data.sections) ? data.sections : [];
      state.manuscriptProgress = data.progress || null;
      state.activeSection = null;
      byId('crump53SectionEditor').hidden = true;
      renderSections();
      renderManuscriptProgress();
      setStatus('crump53ManuscriptStatus', 'Blueprint ready. Every chapter now has a purpose and continuity burden.');
    } catch (error) {
      const message = error.data?.creditsRequired
        ? `${error.message} Current balance: ${error.data.creditBalance ?? 0}.`
        : error.message;
      setFeatureAccessStatus('crump53ManuscriptStatus', error, message);
    }
  }

  function selectSection(sectionId) {
    const section = state.activeManuscript?.sections?.find(item => item.id === sectionId);
    if (!section) return;
    state.activeSection = section;
    byId('crump53SectionEditor').hidden = false;
    byId('crump53SectionTitle').value = section.title || '';
    byId('crump53SectionContent').value = section.content || '';
    renderSections();
  }

  async function addChapter() {
    if (!state.activeManuscript?.id) return;
    const number = (state.activeManuscript.sections?.length || 0) + 1;
    try {
      const data = await api(`/api/manuscripts/${state.activeManuscript.id}/sections`, {
        method: 'POST', body: {title: `Chapter ${number}`, sectionType: 'chapter'},
      });
      state.activeManuscript.sections = [...(state.activeManuscript.sections || []), data.section];
      state.manuscriptProgress = null;
      selectSection(data.section.id);
      renderManuscriptProgress();
    } catch (error) {
      setStatus('crump53ManuscriptStatus', error.message, true);
    }
  }

  async function saveSection() {
    if (!state.activeManuscript?.id || !state.activeSection?.id) return;
    try {
      setStatus('crump53ManuscriptStatus', 'Saving chapter…');
      const data = await api(`/api/manuscripts/${state.activeManuscript.id}/sections/${state.activeSection.id}`, {
        method: 'PATCH',
        body: {
          title: byId('crump53SectionTitle')?.value || '',
          content: byId('crump53SectionContent')?.value || '',
        },
      });
      replaceSection(data.section);
      state.manuscriptProgress = null;
      renderManuscriptProgress();
      setStatus('crump53ManuscriptStatus', 'Saved.');
    } catch (error) {
      setStatus('crump53ManuscriptStatus', error.message, true);
    }
  }

  async function draftSection() {
    if (!state.activeManuscript?.id || !state.activeSection?.id) return;
    const instruction = byId('crump53DraftInstruction')?.value || '';
    try {
      setStatus('crump53ManuscriptStatus', 'Crump is drafting this section…');
      const data = await api(`/api/manuscripts/${state.activeManuscript.id}/sections/${state.activeSection.id}/draft`, {
        method: 'POST', body: {instruction},
      });
      replaceSection(data.section);
      state.manuscriptProgress = data.progress || null;
      byId('crump53SectionContent').value = data.section.content || '';
      if (byId('crump53DraftInstruction')) byId('crump53DraftInstruction').value = '';
      setStatus('crump53ManuscriptStatus', 'Draft ready. Review and revise before publishing.');
      renderManuscriptProgress();
    } catch (error) {
      const message = error.data?.creditsRequired
        ? `${error.message} Current balance: ${error.data.creditBalance ?? 0}.`
        : error.message;
      setFeatureAccessStatus('crump53ManuscriptStatus', error, message);
    }
  }

  async function draftNextSection() {
    if (!state.activeManuscript?.id) return;
    try {
      setStatus('crump53ManuscriptStatus', 'Crump is drafting the next unfinished chapter…');
      const data = await api(`/api/manuscripts/${state.activeManuscript.id}/draft-next`, {
        method: 'POST',
        body: {instruction: ''},
      });
      replaceSection(data.section);
      state.manuscriptProgress = data.progress || null;
      selectSection(data.section.id);
      byId('crump53SectionContent').value = data.section.content || '';
      renderManuscriptProgress();
      setStatus('crump53ManuscriptStatus', `${data.section.title || 'Next chapter'} drafted. Review it before continuing.`);
    } catch (error) {
      const message = error.data?.creditsRequired
        ? `${error.message} Current balance: ${error.data.creditBalance ?? 0}.`
        : error.message;
      setFeatureAccessStatus('crump53ManuscriptStatus', error, message);
    }
  }

  function replaceSection(section) {
    if (!state.activeManuscript) return;
    state.activeManuscript.sections = (state.activeManuscript.sections || []).map(item => item.id === section.id ? section : item);
    state.activeSection = section;
    renderSections();
    renderManuscriptProgress();
  }

  async function exportManuscript(format) {
    if (!state.activeManuscript?.id) return;
    try {
      setStatus('crump53ManuscriptStatus', `Building ${String(format).toUpperCase()}…`);
      const data = await api(`/api/manuscripts/${state.activeManuscript.id}/export`, {
        method: 'POST', body: {format},
      });
      setStatus('crump53ManuscriptStatus', `Export ready · ${data.kdp?.wordCount?.toLocaleString?.() || 0} words.`);
      if (data.file?.url) window.open(`${data.file.url}?download=1`, '_blank', 'noopener');
    } catch (error) {
      setFeatureAccessStatus('crump53ManuscriptStatus', error);
    }
  }

  function libraryCategory(file) {
    const kind = String(file?.kind || '').toLowerCase();
    const type = String(file?.type || '').toLowerCase();
    if (kind === 'generated_video' || type.startsWith('video/')) return 'video';
    if (kind === 'generated_image' || type.startsWith('image/')) return 'image';
    return 'document';
  }

  function formatLibraryBytes(value) {
    const bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) return '';
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
  }

  function formatLibraryDate(value) {
    const date = new Date(value || '');
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'});
  }

  function libraryTitle(file) {
    const metadata = file?.metadata && typeof file.metadata === 'object' ? file.metadata : {};
    const title = String(metadata.title || metadata.documentTitle || '').trim();
    if (title) return title.slice(0, 120);
    const prompt = String(metadata.prompt || '').trim();
    if (prompt) return prompt.slice(0, 96);
    return String(file?.name || 'Saved file');
  }

  function showPlaybackError(preview, message) {
    if (!preview?.isConnected) return;
    preview.dataset.playbackState = 'error';
    preview.classList.remove('is-ready', 'is-loading');
    preview.classList.add('is-error');
    const status = preview.querySelector('[data-playback-status]');
    const detail = preview.querySelector('[data-playback-detail]');
    const retry = preview.querySelector('[data-playback-retry]');
    if (status) status.textContent = 'Preview unavailable';
    if (detail) detail.textContent = message || 'Tap to try loading it again.';
    if (retry) retry.hidden = false;
  }

  async function loadLibraryVideo(preview, force = false) {
    if (!preview?.isConnected) return;
    const current = preview.dataset.playbackState || '';
    if (!force && (current === 'loading' || current === 'ready')) return;
    const fileId = String(preview.dataset.playbackFile || '');
    const video = preview.querySelector('video');
    if (!fileId || !video) return;

    preview.dataset.playbackState = 'loading';
    preview.classList.remove('is-ready', 'is-error');
    preview.classList.add('is-loading');
    const status = preview.querySelector('[data-playback-status]');
    const detail = preview.querySelector('[data-playback-detail]');
    const retry = preview.querySelector('[data-playback-retry]');
    if (status) status.textContent = 'Preparing preview';
    if (detail) detail.textContent = 'Securely loading from your private Files…';
    if (retry) retry.hidden = true;

    video.pause();
    video.removeAttribute('src');
    video.load();

    try {
      const data = await api(`/api/files/${encodeURIComponent(fileId)}/playback`);
      if (!preview.isConnected || preview.dataset.playbackFile !== fileId) return;
      const directUrl = new URL(String(data.url || ''), window.location.origin);
      directUrl.hash = 't=0.001';

      let settled = false;
      const markReady = () => {
        if (settled || !preview.isConnected) return;
        settled = true;
        preview.dataset.playbackState = 'ready';
        preview.classList.remove('is-loading', 'is-error');
        preview.classList.add('is-ready');
        const overlay = preview.querySelector('.crump53-playback-state');
        if (overlay) overlay.hidden = true;
      };
      const markFailed = () => {
        if (settled) return;
        settled = true;
        showPlaybackError(preview, 'The private playback link could not be opened.');
      };

      video.addEventListener('loadedmetadata', () => {
        try {
          const duration = Number(video.duration || 0);
          video.currentTime = Number.isFinite(duration) && duration > 0.12
            ? Math.min(0.08, duration / 50)
            : 0.001;
        } catch (_) { /* the URL fragment still requests the opening frame */ }
      }, {once: true});
      video.addEventListener('loadeddata', markReady, {once: true});
      video.addEventListener('canplay', markReady, {once: true});
      video.addEventListener('error', markFailed, {once: true});
      video.src = directUrl.href;
      video.load();
    } catch (error) {
      showPlaybackError(preview, error.message || 'Could not prepare private playback.');
    }
  }

  function hydrateLibraryVideos(grid) {
    state.libraryVideoObserver?.disconnect?.();
    state.libraryVideoObserver = null;
    const previews = Array.from(grid?.querySelectorAll('[data-playback-file]') || []);
    if (!previews.length) return;
    if (!('IntersectionObserver' in window)) {
      previews.forEach(preview => void loadLibraryVideo(preview));
      return;
    }
    state.libraryVideoObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        state.libraryVideoObserver?.unobserve(entry.target);
        void loadLibraryVideo(entry.target);
      });
    }, {rootMargin: '180px 0px'});
    previews.forEach(preview => state.libraryVideoObserver.observe(preview));
  }

  function renderLibrary() {
    const grid = byId('crump53LibraryGrid');
    if (!grid) return;
    const filter = state.libraryFilter || 'all';
    const visible = state.libraryFiles.filter(file => filter === 'all' || libraryCategory(file) === filter);
    if (!visible.length) {
      state.libraryVideoObserver?.disconnect?.();
      grid.innerHTML = '<div class="crump53-library-empty">No files in this category yet.</div>';
      return;
    }

    grid.innerHTML = visible.map(file => {
      const category = libraryCategory(file);
      const url = String(file.url || '');
      const metadata = file?.metadata && typeof file.metadata === 'object' ? file.metadata : {};
      const title = libraryTitle(file);
      const prompt = String(metadata.prompt || '').trim();
      const preview = category === 'video'
        ? `<video controls playsinline preload="metadata" aria-label="Play ${escapeHtml(title)}"></video>
           <div class="crump53-playback-state" aria-live="polite">
             <span class="crump53-playback-pulse">${toolIcon('video')}</span>
             <strong data-playback-status>Preparing preview</strong>
             <small data-playback-detail>Securely loading from your private Files…</small>
             <button type="button" class="crump53-button" data-playback-retry="${escapeHtml(file.id)}" hidden>Try again</button>
           </div>`
        : category === 'image'
          ? `<img loading="lazy" src="${escapeHtml(url)}" alt="${escapeHtml(title)}">`
          : `<div class="crump53-library-document"><span>${escapeHtml(String(file.name || 'FILE').split('.').pop().slice(0, 5).toUpperCase())}</span></div>`;
      const detail = [
        String(file.kind || category).replaceAll('_', ' '),
        category === 'video' && metadata.durationSeconds ? `${metadata.durationSeconds}s` : '',
        category === 'video' && metadata.engine ? String(metadata.engine) : '',
        formatLibraryBytes(file.size),
        formatLibraryDate(file.createdAt),
      ].filter(Boolean).join(' · ');
      return `
        <article class="crump53-library-item" data-library-file="${escapeHtml(file.id)}">
          <div class="crump53-library-preview"${category === 'video' ? ` data-playback-file="${escapeHtml(file.id)}" data-playback-state="idle"` : ''}>${preview}</div>
          <div class="crump53-library-copy">
            <strong>${escapeHtml(title)}</strong>
            ${prompt && prompt !== title ? `<p>${escapeHtml(prompt.slice(0, 180))}</p>` : ''}
            <small>${escapeHtml(detail)}</small>
          </div>
          <div class="crump53-actions">
            <button type="button" class="crump53-button" data-library-open="${escapeHtml(file.id)}">Open</button>
            <button type="button" class="crump53-button" data-library-download="${escapeHtml(file.id)}">Download</button>
            ${category === 'video' && metadata.engine === 'extendable' && metadata.mediaJobId ? `<button type="button" class="crump53-button" data-library-continue="${escapeHtml(metadata.mediaJobId)}">Continue scene</button>` : ''}
            ${category !== 'video' ? `<button type="button" class="crump53-button" data-library-use="${escapeHtml(file.id)}">Use in chat</button>` : ''}
          </div>
        </article>`;
    }).join('');

    const byFileId = new Map(state.libraryFiles.map(file => [String(file.id), file]));
    grid.querySelectorAll('[data-library-open]').forEach(button => {
      button.addEventListener('click', () => {
        const file = byFileId.get(String(button.dataset.libraryOpen));
        if (!file) return;
        if (window.CrumpFileTools?.open) window.CrumpFileTools.open(file);
        else window.open(file.url, '_blank', 'noopener');
      });
    });
    grid.querySelectorAll('[data-library-download]').forEach(button => {
      button.addEventListener('click', () => {
        const file = byFileId.get(String(button.dataset.libraryDownload));
        if (!file) return;
        if (window.CrumpFileTools?.open) window.CrumpFileTools.open(file, true);
        else window.location.assign(`${file.url}?download=1`);
      });
    });
    grid.querySelectorAll('[data-library-use]').forEach(button => {
      button.addEventListener('click', () => {
        const file = byFileId.get(String(button.dataset.libraryUse));
        if (!file || !window.CrumpFileTools?.addReference) return;
        window.CrumpFileTools.addReference(file);
        closeStudio();
        window.showToast?.(`${file.name || 'File'} added to the conversation.`, 'success');
      });
    });
    grid.querySelectorAll('[data-library-continue]').forEach(button => {
      button.addEventListener('click', async () => {
        const jobId = String(button.dataset.libraryContinue || '');
        if (!jobId) return;
        try {
          const data = await api(`/api/media/video/${jobId}`);
          const job = data.job || {};
          if (!job.canContinue) {
            window.showToast?.('That continuation window has closed or the next combined file would exceed the current storage guard.', 'info');
            return;
          }
          openStudio('video');
          renderReadyVideo(job, true);
        } catch (error) {
          window.showToast?.(error.message || 'Could not reopen that video scene.', 'error');
        }
      });
    });
    grid.querySelectorAll('[data-playback-retry]').forEach(button => {
      button.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        const preview = button.closest('[data-playback-file]');
        if (preview) void loadLibraryVideo(preview, true);
      });
    });
    hydrateLibraryVideos(grid);
  }

  async function refreshLibrary() {
    const grid = byId('crump53LibraryGrid');
    if (!grid) return;
    setStatus('crump53LibraryStatus', 'Loading your private files…');
    if (!state.libraryFiles.length) {
      grid.innerHTML = '<div class="crump53-library-empty">Loading saved files…</div>';
    }
    try {
      const data = await api('/api/files?limit=200');
      state.libraryFiles = Array.isArray(data.files) ? data.files : [];
      renderLibrary();
      setStatus(
        'crump53LibraryStatus',
        `${state.libraryFiles.length} saved item${state.libraryFiles.length === 1 ? '' : 's'} · private to your account.`,
      );
    } catch (error) {
      setStatus('crump53LibraryStatus', error.message || 'Could not load your saved files.', true);
      grid.innerHTML = '<div class="crump53-library-empty is-error">Your files could not be loaded.</div>';
    }
  }

  async function startVideo(event, overrides = {}) {
    event?.preventDefault?.();
    const prompt = String(overrides.prompt ?? byId('crump53VideoPrompt')?.value ?? '');
    const engine = byId('crump53VideoEngine')?.value || 'quick';
    const resolution = byId('crump53VideoResolution')?.value || '720p';
    const aspectRatio = byId('crump53VideoAspect')?.value || '16:9';
    const durationSeconds = Number(byId('crump53VideoDuration')?.value || 5);
    const idempotencyKey = String(overrides.idempotencyKey || '') || globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    try {
      setStatus('crump53VideoStatus', 'Starting video generation…');
      state.activeVideoJob = null;
      byId('crump53VideoResult').innerHTML = '';
      const data = await api('/api/media/video', {
        method: 'POST',
        headers: {'X-Idempotency-Key': idempotencyKey},
        body: {
          prompt,
          engine,
          resolution,
          aspectRatio,
          durationSeconds,
          projectId: state.activeProject?.id || null,
        },
      });
      storeVideoJob(data.job.id);
      setStatus('crump53VideoStatus', 'Generating… this can take a few minutes. You can close this panel and return.');
      pollVideo(data.job.id);
    } catch (error) {
      const suffix = error.data?.creditsRequired
        ? ` Needs ${error.data.creditsRequired} credits; balance ${error.data.creditBalance ?? 0}.`
        : '';
      setFeatureAccessStatus('crump53VideoStatus', error, `${error.message}${suffix}`);
    }
  }

  function renderReadyVideo(job, openContinuation = false) {
    if (!job?.file?.url) return;
    state.activeVideoJob = job;
    const attribution = job.attribution && job.attributionUrl
      ? `<a class="crump53-provider-attribution" href="${escapeHtml(job.attributionUrl)}" target="_blank" rel="noopener">${escapeHtml(job.attribution)}</a>`
      : '';
    const continuation = job.canContinue
      ? `<button type="button" class="crump53-button is-primary" id="crump53ContinueScene">Continue scene</button>`
      : '';
    const result = byId('crump53VideoResult');
    if (!result) return;
    result.innerHTML = `
      <div class="crump53-video-result-meta">
        <span>${escapeHtml(String(job.engine || 'quick'))} · ${escapeHtml(String(job.durationSeconds || 8))}s · ${escapeHtml(String(job.resolution || '720p'))}</span>
        ${attribution}
      </div>
      <video class="crump53-video-preview" controls playsinline src="${escapeHtml(job.file.url)}"></video>
      <div class="crump53-video-result-actions">
        ${continuation}
        <a class="crump53-button crump53-button-link" href="${escapeHtml(job.file.url)}?download=1" download>Download video</a>
        <button type="button" class="crump53-button" id="crump53OpenLibraryFromVideo">Open Files</button>
      </div>
      ${job.canContinue ? `
        <div class="crump53-video-continuation" id="crump53VideoContinuation" hidden>
          <div class="crump53-kicker">NEXT SHOT</div>
          <label class="crump53-label">What happens next?<textarea id="crump53ContinuePrompt" class="crump53-textarea" maxlength="4000" placeholder="Continue the action from the final moment. Describe the next movement, camera direction, dialogue, or sound..."></textarea></label>
          <div class="crump53-note">Native continuation uses the previous Veo scene as the reference point, adds about 7 seconds, and returns one combined video. 80 credits per continuation.</div>
          <div class="crump53-actions"><button type="button" class="crump53-button is-primary" id="crump53SubmitContinuation">Continue · 80 credits</button><button type="button" class="crump53-button" id="crump53CancelContinuation">Cancel</button></div>
        </div>` : ''}`;
    byId('crump53OpenLibraryFromVideo')?.addEventListener('click', () => {
      openStudio('projects');
      openProjectFiles();
    });
    byId('crump53ContinueScene')?.addEventListener('click', () => {
      const composer = byId('crump53VideoContinuation');
      if (composer) composer.hidden = false;
      byId('crump53ContinuePrompt')?.focus();
    });
    byId('crump53CancelContinuation')?.addEventListener('click', () => {
      const composer = byId('crump53VideoContinuation');
      if (composer) composer.hidden = true;
    });
    byId('crump53SubmitContinuation')?.addEventListener('click', () => continueVideoScene(job));
    if (openContinuation && job.canContinue) {
      byId('crump53ContinueScene')?.click();
    }
  }

  async function continueVideoScene(parentJob) {
    const prompt = byId('crump53ContinuePrompt')?.value || '';
    const button = byId('crump53SubmitContinuation');
    const idempotencyKey = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    if (button) button.disabled = true;
    try {
      setStatus('crump53VideoStatus', 'Continuing from the final moment of your scene…');
      const data = await api(`/api/media/video/${parentJob.id}/continue`, {
        method: 'POST',
        headers: {'X-Idempotency-Key': idempotencyKey},
        body: {prompt},
      });
      storeVideoJob(data.job.id);
      state.activeVideoJob = data.job;
      setStatus('crump53VideoStatus', 'Extending… Crump is preserving the previous scene and building the next seven seconds.');
      pollVideo(data.job.id);
    } catch (error) {
      const suffix = error.data?.creditsRequired
        ? ` Needs ${error.data.creditsRequired} credits; balance ${error.data.creditBalance ?? 0}.`
        : '';
      setFeatureAccessStatus('crump53VideoStatus', error, `${error.message}${suffix}`);
      if (button) button.disabled = false;
    }
  }

  function pollVideo(jobId) {
    if (state.videoPollTimer) window.clearTimeout(state.videoPollTimer);
    const check = async () => {
      try {
        const data = await api(`/api/media/video/${jobId}`);
        const job = data.job || {};
        state.activeVideoJob = job;
        if (job.status === 'ready' && job.file?.url) {
          storeVideoJob('');
          setStatus('crump53VideoStatus', `Saved to Files · ${job.durationSeconds || 8}s · ${job.resolution || '720p'}`);
          renderReadyVideo(job);
          void refreshLibrary();
          return;
        }
        if (job.status === 'failed') {
          storeVideoJob('');
          const billingMessage = job.chargeReturned
            ? ' Your generation charge was returned.'
            : ' No video was delivered; this provider failure may still have incurred provider cost.';
          setStatus('crump53VideoStatus', `${job.error || 'Video generation failed.'}${billingMessage}`, true);
          return;
        }
        setStatus('crump53VideoStatus', job.provider === 'runway' && job.providerStatus === 'THROTTLED'
          ? 'Runway queued the job because provider concurrency is busy. Crump will keep checking.'
          : 'Generating… Crump is checking the provider status.');
        state.videoPollTimer = window.setTimeout(check, 8000);
      } catch (error) {
        setStatus('crump53VideoStatus', error.message, true);
        if (error.data?.shouldRetry) {
          state.videoPollTimer = window.setTimeout(check, 10000);
        }
      }
    };
    void check();
  }

  async function openManuscriptWorkspace(workspace) {
    const projectId = String(workspace?.projectId || '');
    const manuscriptId = String(workspace?.manuscriptId || '');
    openStudio('manuscripts');
    if (!projectId || !manuscriptId) {
      setStatus('crump53ManuscriptStatus', 'This Library book is missing its manuscript workspace link.', true);
      return false;
    }
    await refreshProjects();
    const project = state.projects.find(item => String(item.id) === projectId);
    if (!project) {
      setStatus('crump53ManuscriptStatus', 'That Project is no longer available.', true);
      return false;
    }
    selectProject(projectId, {updateRoute: false, focus: false, reveal: false});
    await refreshManuscripts();
    const opened = await loadManuscript(manuscriptId);
    if (!opened) return false;

    const editor = byId('crump53ManuscriptEditor');
    const target = byId('crump53EditorTitle') || editor;
    if (editor && !editor.hidden && target) {
      const reducedMotion = Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
      window.requestAnimationFrame(() => {
        target.scrollIntoView({
          behavior: reducedMotion ? 'auto' : 'smooth',
          block: 'center',
          inline: 'nearest',
        });
      });
    }
    setStatus('crump53ManuscriptStatus', 'Opened ' + (workspace?.title || 'manuscript') + '.');
    return true;
  }

  function handoffOnceKey(kind, value) {
    return 'askcrump.creationHandoff.' + kind + '.' + String(value || 'unknown');
  }

  function claimLiveHandoff(kind, value) {
    const key = handoffOnceKey(kind, value);
    try {
      if (sessionStorage.getItem(key) === 'done') return false;
      sessionStorage.setItem(key, 'done');
    } catch (_) { /* one-time handoff guard is best effort */ }
    return true;
  }

  async function openVideoCreationHandoff(handoff, {start = false} = {}) {
    const brief = String(handoff?.brief || '').trim();
    openStudio('video');
    const prompt = byId('crump53VideoPrompt');
    if (prompt && brief) prompt.value = brief;
    if (!start) {
      prompt?.focus({preventScroll: true});
      return true;
    }
    const key = String(handoff?.idempotencyKey || '');
    if (!claimLiveHandoff('video', key || brief.slice(0, 80))) return true;
    await startVideo({preventDefault() {}}, {prompt: brief, idempotencyKey: key});
    return true;
  }

  async function handleCreationHandoff(handoff) {
    if (!handoff || typeof handoff !== 'object') return false;
    if (handoff.kind === 'manuscript') {
      const workspace = handoff.workspace || handoff;
      if (!workspace?.autoOpen) return false;
      const token = workspace.runId || workspace.manuscriptId;
      if (!claimLiveHandoff('manuscript', token)) return true;
      return await openManuscriptWorkspace(workspace);
    }
    if (handoff.kind === 'video') {
      return await openVideoCreationHandoff(handoff, {start: Boolean(handoff.autoStart)});
    }
    return false;
  }

  function enhanceManuscriptHandoffs(messages) {
    (Array.isArray(messages) ? messages : []).forEach(message => {
      if (!message?.id) return;
      const row = document.querySelector(`[data-message-id="${CSS.escape(message.id)}"]`);
      const wrapper = row?.querySelector('.message-wrapper');
      if (!wrapper) return;

      const workspace = message.manuscriptWorkspace;
      if (workspace && !wrapper.querySelector('.crump53-manuscript-handoff')) {
        const card = document.createElement('div');
        card.className = 'crump53-manuscript-handoff';
        card.innerHTML = `
          <div class="crump53-handoff-mark">M</div>
          <div><small>YOUR MANUSCRIPT · ${escapeHtml(workspace.runStatus || 'saved')}</small><strong>${escapeHtml(workspace.title || 'Untitled manuscript')}</strong><span>${Number(workspace.chapterCount || 0)} planned chapters · ${Number(workspace.targetWords || 0).toLocaleString()}-word target · built from this conversation</span></div>
          <button type="button">Open Workshop</button>`;
        card.querySelector('button')?.addEventListener('click', () => void openManuscriptWorkspace(workspace));
        wrapper.appendChild(card);
      }

      const creation = message.creationHandoff;
      if (creation?.kind === 'video' && !wrapper.querySelector('.crump53-video-handoff')) {
        const card = document.createElement('div');
        card.className = 'crump53-manuscript-handoff crump53-video-handoff';
        card.innerHTML = `
          <div class="crump53-handoff-mark">V</div>
          <div><small>VIDEO STUDIO</small><strong>Scene ready to create</strong><span>${escapeHtml(String(creation.brief || 'Your video direction').slice(0, 180))}</span></div>
          <button type="button">Open Video Studio</button>`;
        card.querySelector('button')?.addEventListener('click', () => void openVideoCreationHandoff(creation));
        wrapper.appendChild(card);
      }
    });
  }

  let rendererWrapped = false;
  let authenticatedHydrationStarted = false;
  function wrapManuscriptRenderer() {
    if (rendererWrapped || typeof window.renderMessages !== 'function') return;
    const original = window.renderMessages;
    window.renderMessages = function(messages) {
      const result = original(messages);
      enhanceManuscriptHandoffs(messages);
      return result;
    };
    rendererWrapped = true;
    const chat = (Array.isArray(window.chats) ? window.chats : []).find(item => item.id === window.currentChatId);
    if (chat) enhanceManuscriptHandoffs(chat.messages);
  }

  function hydrateAuthenticatedState() {
    if (authenticatedHydrationStarted || !window.currentUser) return;
    if (!readProjectRoute()) return;
    authenticatedHydrationStarted = true;
    openStudio('projects', {preserveProjectRoute: true});
  }

  window.CrumpProduct53 = Object.freeze({
    open: openStudio,
    openProject: projectId => openProject(projectId),
    projectTarget: () => currentProjectTarget(),
    keepConversation: options => keepConversation(options),
    keepArtifact: (file, options) => keepArtifact(file, options),
    openManuscript: workspace => openManuscriptWorkspace(workspace),
    handleCreationHandoff: handoff => handleCreationHandoff(handoff),
  });

  function init() {
    injectNavigation();
    injectStudio();
    injectProjectIntoChatRequests();
    wrapManuscriptRenderer();
    const scrollButton = byId('scrollToEndBtn');
    if (scrollButton) scrollButton.title = 'Jump to newest message';
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !byId('crump53Studio')?.hidden) closeStudio();
    });
    window.addEventListener('popstate', () => {
      const requestedProjectId = readProjectRoute();
      if (!requestedProjectId) {
        if (byId('crump53Sheet')?.dataset.crump53Section === 'projects') {
          showProjectIndex({updateRoute: false});
        }
        return;
      }
      const project = state.projects.find(item => String(item.id || '') === requestedProjectId);
      if (project) selectProject(requestedProjectId, {updateRoute: false, focus: false});
      else void refreshProjects();
    });
    hydrateAuthenticatedState();
    setTimeout(() => {
      const chat = (Array.isArray(window.chats) ? window.chats : []).find(item => item.id === window.currentChatId);
      if (chat) enhanceManuscriptHandoffs(chat.messages);
    }, 900);
  }

  window.addEventListener('crump:authenticated-ready', hydrateAuthenticatedState);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
