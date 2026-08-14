(() => {
  'use strict';

  const state = {
    features: null,
    projects: [],
    activeProject: null,
    editingProject: null,
    manuscripts: [],
    activeManuscript: null,
    activeSection: null,
    videoPollTimer: null,
  };

  const nativeFetch = window.fetch.bind(window);
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
    const headers = {...(options.headers || {})};
    if (options.body && typeof options.body !== 'string') {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }
    const response = await nativeFetch(path, {credentials: 'include', ...options, headers});
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok || data.success === false) {
      const error = new Error(data.error || `Request failed (${response.status})`);
      error.data = data;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function setStatus(id, message, isError = false) {
    const node = byId(id);
    if (!node) return;
    node.textContent = message || '';
    node.classList.toggle('is-error', Boolean(isError));
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

  function injectNavigation() {
    const primaryStack = document.querySelector('.v1-rail .v1-rail-stack');
    if (primaryStack && !document.querySelector('.crump53-projects-button')) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'v1-rail-button crump53-projects-button';
      button.setAttribute('aria-label', 'Projects');
      button.title = 'Projects';
      button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h6l2 2h8v10H4z"/><path d="M4 7V5h7l2 2"/></svg>';
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
    if (strip && !byId('crump53VideoMode')) {
      const imagePill = strip.querySelector('[data-v1-command="image"]');
      const button = document.createElement('button');
      button.id = 'crump53VideoMode';
      button.type = 'button';
      button.className = 'v1-mode-pill';
      button.innerHTML = '<span>Video</span>';
      button.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        openStudio('video');
      });
      if (imagePill?.nextSibling) strip.insertBefore(button, imagePill.nextSibling);
      else strip.appendChild(button);
    }
  }

  function injectStudio() {
    if (byId('crump53Studio')) return;
    const overlay = document.createElement('div');
    overlay.id = 'crump53Studio';
    overlay.className = 'crump53-overlay';
    overlay.hidden = true;
    overlay.innerHTML = `
      <section class="crump53-sheet" role="dialog" aria-modal="true" aria-label="Ask Crump Projects and creation studio">
        <header class="crump53-sheet-head">
          <div><div class="crump53-kicker">ASK CRUMP</div><strong>Projects & Creation</strong></div>
          <button type="button" class="crump53-close" id="crump53Close" aria-label="Close">×</button>
        </header>
        <div class="crump53-sheet-body">
          <div class="crump53-tabs" role="tablist">
            <button type="button" class="crump53-tab is-active" data-crump53-tab="projects">Projects</button>
            <button type="button" class="crump53-tab" data-crump53-tab="manuscripts">Manuscripts</button>
            <button type="button" class="crump53-tab" data-crump53-tab="video">Video</button>
          </div>

          <section class="crump53-panel" data-crump53-panel="projects">
            <div class="crump53-grid">
              <div class="crump53-card">
                <h3>Your projects</h3>
                <p>Each project keeps its own instructions, canon, files, manuscripts, and conversations.</p>
                <div id="crump53ProjectList" class="crump53-list"></div>
              </div>
              <div class="crump53-card">
                <h3 id="crump53ProjectFormTitle">New project</h3>
                <form id="crump53ProjectForm" class="crump53-form">
                  <label class="crump53-label">Name<input id="crump53ProjectName" class="crump53-input" maxlength="100" required></label>
                  <label class="crump53-label">Description<textarea id="crump53ProjectDescription" class="crump53-textarea" maxlength="1200"></textarea></label>
                  <label class="crump53-label">Project instructions<textarea id="crump53ProjectInstructions" class="crump53-textarea" maxlength="12000" placeholder="Canon, tone, goals, rules, constraints..."></textarea></label>
                  <div class="crump53-actions">
                    <button class="crump53-button is-primary" type="submit">Save project</button>
                    <button class="crump53-button" type="button" id="crump53UseProject">Use in conversation</button>
                    <button class="crump53-button" type="button" id="crump53NewProject">New</button>
                  </div>
                  <div id="crump53ProjectStatus" class="crump53-status" aria-live="polite"></div>
                </form>
              </div>
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
            <div id="crump53ManuscriptNoProject" class="crump53-note">Choose an active Project first. Manuscripts stay isolated inside their Project.</div>
            <div id="crump53ManuscriptWorkspace" hidden>
              <div class="crump53-grid">
                <div class="crump53-card">
                  <h3>Manuscripts</h3>
                  <p>Build chapter by chapter, then export KDP-aware DOCX/PDF or Kindle EPUB.</p>
                  <div class="crump53-note">Professional+: 2 AI drafts/day on Professional, 4/day on Enterprise. Additional AI drafts use 8 credits. KDP-aware exports are included.</div>
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
                    <label class="crump53-label">Trim size<select id="crump53Trim" class="crump53-select"><option value="6x9">6 × 9 in</option><option value="5x8">5 × 8 in</option><option value="5.25x8">5.25 × 8 in</option><option value="5.5x8.5">5.5 × 8.5 in</option><option value="6.14x9.21">6.14 × 9.21 in</option><option value="7x10">7 × 10 in</option><option value="8x10">8 × 10 in</option><option value="8.5x11">8.5 × 11 in</option></select></label>
                    <button type="button" class="crump53-button is-primary" id="crump53CreateManuscript">Create</button>
                  </div>
                  <div id="crump53ManuscriptEditor" hidden>
                    <h3 id="crump53EditorTitle">Manuscript</h3>
                    <div class="crump53-actions" style="margin-bottom:10px">
                      <button type="button" class="crump53-button" id="crump53AddChapter">Add chapter</button>
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

          <section class="crump53-panel" data-crump53-panel="video" hidden>
            <div class="crump53-card">
              <div class="crump53-kicker">VIDEO STUDIO</div>
              <h3>Generate a short video</h3>
              <p>Generation runs asynchronously, so you can close this sheet and come back while the provider works.</p>
              <form id="crump53VideoForm" class="crump53-form">
                <label class="crump53-label">Prompt<textarea id="crump53VideoPrompt" class="crump53-textarea" maxlength="4000" placeholder="Describe the scene, subject, camera movement, atmosphere, and sound..."></textarea></label>
                <div class="crump53-grid">
                  <label class="crump53-label">Aspect ratio<select id="crump53VideoAspect" class="crump53-select"><option value="16:9">Landscape 16:9</option><option value="9:16">Portrait 9:16</option></select></label>
                  <label class="crump53-label">Resolution<select id="crump53VideoResolution" class="crump53-select"><option value="720p">720p · 60 credits</option><option value="1080p">1080p · 90 credits</option></select></label>
                </div>
                <div class="crump53-note">Video is Professional+ only and every generation spends Crump Credits. There are no unlimited or included video generations, which protects the account from runaway provider cost. Ask Crump never exposes the provider key to the browser.</div>
                <div class="crump53-actions"><button class="crump53-button is-primary" type="submit">Generate video</button><span id="crump53VideoEntitlement" class="crump53-lock">Checking access…</span></div>
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
    overlay.querySelectorAll('[data-crump53-tab]').forEach(button => {
      button.addEventListener('click', () => selectTab(button.dataset.crump53Tab));
    });
    byId('crump53ProjectForm')?.addEventListener('submit', saveProject);
    byId('crump53UseProject')?.addEventListener('click', activateSelectedProject);
    byId('crump53NewProject')?.addEventListener('click', resetProjectForm);
    byId('crump53AddContext')?.addEventListener('click', addProjectContext);
    byId('crump53NewManuscript')?.addEventListener('click', showManuscriptCreate);
    byId('crump53CreateManuscript')?.addEventListener('click', createManuscript);
    byId('crump53AddChapter')?.addEventListener('click', addChapter);
    byId('crump53SaveSection')?.addEventListener('click', saveSection);
    byId('crump53DraftSection')?.addEventListener('click', draftSection);
    overlay.querySelectorAll('[data-crump53-export]').forEach(button => {
      button.addEventListener('click', () => exportManuscript(button.dataset.crump53Export));
    });
    byId('crump53VideoForm')?.addEventListener('submit', startVideo);
  }

  function openStudio(tab = 'projects') {
    const studio = byId('crump53Studio');
    if (!studio) return;
    studio.hidden = false;
    document.body.style.overflow = 'hidden';
    selectTab(tab);
    void refreshFeatures();
    void refreshProjects();
  }

  function closeStudio() {
    const studio = byId('crump53Studio');
    if (studio) studio.hidden = true;
    document.body.style.overflow = '';
  }

  function selectTab(tab) {
    document.querySelectorAll('[data-crump53-tab]').forEach(node => {
      node.classList.toggle('is-active', node.dataset.crump53Tab === tab);
    });
    document.querySelectorAll('[data-crump53-panel]').forEach(node => {
      node.hidden = node.dataset.crump53Panel !== tab;
    });
    if (tab === 'manuscripts') void refreshManuscripts();
    if (tab === 'video') {
      const pendingJob = readStoredVideoJob();
      if (pendingJob) pollVideo(pendingJob);
    }
  }

  async function refreshFeatures() {
    try {
      const data = await api('/api/features');
      state.features = data;
      const video = data.features?.video;
      const label = byId('crump53VideoEntitlement');
      if (label) {
        if (!video?.configured) label.textContent = 'Provider key not configured';
        else if (!video?.entitled) label.textContent = 'Professional plan required';
        else label.textContent = `Ready · ${data.creditBalance ?? 0} credits`;
      }
    } catch (_) {
      state.features = null;
    }
  }

  async function refreshProjects() {
    try {
      const data = await api('/api/projects');
      state.projects = Array.isArray(data.projects) ? data.projects : [];
      const stored = state.activeProject?.id || readStoredProject();
      state.activeProject = state.projects.find(item => item.id === stored) || null;
      if (!state.activeProject && stored) storeProject('');
      renderProjectList(data.limit);
      renderProjectIndicator();
      renderManuscriptProjectState();
    } catch (error) {
      setStatus('crump53ProjectStatus', error.message, true);
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
      <button type="button" class="crump53-list-button ${state.activeProject?.id === item.id ? 'is-active' : ''}" data-project-id="${escapeHtml(item.id)}">
        <span>${escapeHtml(item.name)}</span><small>${escapeHtml(item.updated_at ? 'Saved' : '')}</small>
      </button>`).join('') + (limit ? `<div class="crump53-status">${state.projects.length} / ${limit} active projects</div>` : '');
    list.querySelectorAll('[data-project-id]').forEach(button => {
      button.addEventListener('click', () => selectProject(button.dataset.projectId));
    });
  }

  function selectProject(projectId) {
    const project = state.projects.find(item => item.id === projectId);
    if (!project) return;
    state.activeProject = project;
    state.editingProject = project;
    storeProject(project.id);
    renderProjectIndicator();
    byId('crump53ProjectName').value = project.name || '';
    byId('crump53ProjectDescription').value = project.description || '';
    byId('crump53ProjectInstructions').value = project.instructions || '';
    byId('crump53ProjectFormTitle').textContent = 'Edit project';
    renderProjectList(state.features?.projectLimit);
    renderManuscriptProjectState();
    void refreshProjectContext();
  }

  function resetProjectForm() {
    byId('crump53ProjectName').value = '';
    byId('crump53ProjectDescription').value = '';
    byId('crump53ProjectInstructions').value = '';
    byId('crump53ProjectFormTitle').textContent = 'New project';
    state.editingProject = null;
    const contextCard = byId('crump53ProjectContextCard');
    if (contextCard) contextCard.hidden = true;
    renderProjectList(state.features?.projectLimit);
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
      setStatus('crump53ProjectStatus', 'Project saved and selected.');
      await refreshProjects();
    } catch (error) {
      setStatus('crump53ProjectStatus', error.message, true);
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
    try {
      const data = await api(`/api/projects/${state.activeProject.id}`);
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
      list.innerHTML = `<div class="crump53-note">${escapeHtml(error.message || 'Could not load Project context.')}</div>`;
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

  function renderProjectIndicator() {
    document.querySelector('.crump53-active-project')?.remove();
    document.querySelectorAll('.crump53-projects-button').forEach(node => {
      node.classList.toggle('is-active', Boolean(state.activeProject));
    });
    if (!state.activeProject) return;
    const header = document.querySelector('.v1-header-branding');
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
      setStatus('crump53ManuscriptStatus', error.message, true);
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
    renderManuscriptList();
  }

  async function createManuscript() {
    if (!state.activeProject?.id) return;
    try {
      setStatus('crump53ManuscriptStatus', 'Creating…');
      const data = await api(`/api/projects/${state.activeProject.id}/manuscripts`, {
        method: 'POST',
        body: {
          title: byId('crump53ManuscriptTitle')?.value || '',
          authorName: byId('crump53ManuscriptAuthor')?.value || '',
          trimCode: byId('crump53Trim')?.value || '6x9',
        },
      });
      await refreshManuscripts();
      await loadManuscript(data.manuscript.id);
    } catch (error) {
      setStatus('crump53ManuscriptStatus', error.message, true);
    }
  }

  async function loadManuscript(manuscriptId) {
    try {
      const data = await api(`/api/manuscripts/${manuscriptId}`);
      state.activeManuscript = data.manuscript;
      state.activeManuscript.sections = Array.isArray(data.sections) ? data.sections : [];
      state.activeSection = null;
      byId('crump53ManuscriptCreate').hidden = true;
      byId('crump53ManuscriptEditor').hidden = false;
      byId('crump53SectionEditor').hidden = true;
      byId('crump53EditorTitle').textContent = data.manuscript.title || 'Manuscript';
      renderManuscriptList();
      renderSections();
    } catch (error) {
      setStatus('crump53ManuscriptStatus', error.message, true);
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
      selectSection(data.section.id);
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
      byId('crump53SectionContent').value = data.section.content || '';
      if (byId('crump53DraftInstruction')) byId('crump53DraftInstruction').value = '';
      setStatus('crump53ManuscriptStatus', 'Draft ready. Review and revise before publishing.');
    } catch (error) {
      const message = error.data?.creditsRequired
        ? `${error.message} Current balance: ${error.data.creditBalance ?? 0}.`
        : error.message;
      setStatus('crump53ManuscriptStatus', message, true);
    }
  }

  function replaceSection(section) {
    if (!state.activeManuscript) return;
    state.activeManuscript.sections = (state.activeManuscript.sections || []).map(item => item.id === section.id ? section : item);
    state.activeSection = section;
    renderSections();
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
      setStatus('crump53ManuscriptStatus', error.message, true);
    }
  }

  async function startVideo(event) {
    event.preventDefault();
    const prompt = byId('crump53VideoPrompt')?.value || '';
    const resolution = byId('crump53VideoResolution')?.value || '720p';
    const aspectRatio = byId('crump53VideoAspect')?.value || '16:9';
    const idempotencyKey = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    try {
      setStatus('crump53VideoStatus', 'Starting video generation…');
      byId('crump53VideoResult').innerHTML = '';
      const data = await api('/api/media/video', {
        method: 'POST',
        headers: {'X-Idempotency-Key': idempotencyKey},
        body: {prompt, resolution, aspectRatio, projectId: state.activeProject?.id || null},
      });
      storeVideoJob(data.job.id);
      setStatus('crump53VideoStatus', 'Generating… this can take a few minutes. You can close this panel and return.');
      pollVideo(data.job.id);
    } catch (error) {
      const suffix = error.data?.creditsRequired
        ? ` Needs ${error.data.creditsRequired} credits; balance ${error.data.creditBalance ?? 0}.`
        : '';
      setStatus('crump53VideoStatus', `${error.message}${suffix}`, true);
    }
  }

  function pollVideo(jobId) {
    if (state.videoPollTimer) window.clearTimeout(state.videoPollTimer);
    const check = async () => {
      try {
        const data = await api(`/api/media/video/${jobId}`);
        const job = data.job || {};
        if (job.status === 'ready' && job.file?.url) {
          storeVideoJob('');
          setStatus('crump53VideoStatus', 'Video ready.');
          byId('crump53VideoResult').innerHTML = `
            <video class="crump53-video-preview" controls playsinline src="${escapeHtml(job.file.url)}"></video>
            <div class="crump53-actions" style="margin-top:10px"><a class="crump53-button" href="${escapeHtml(job.file.url)}?download=1">Download video</a></div>`;
          return;
        }
        if (job.status === 'failed') {
          storeVideoJob('');
          setStatus('crump53VideoStatus', job.error || 'Video generation failed. Your generation charge was returned.', true);
          return;
        }
        setStatus('crump53VideoStatus', 'Generating… Crump is checking the provider status.');
        state.videoPollTimer = window.setTimeout(check, 8000);
      } catch (error) {
        setStatus('crump53VideoStatus', error.message, true);
      }
    };
    void check();
  }

  function init() {
    injectNavigation();
    injectStudio();
    injectProjectIntoChatRequests();
    const scrollButton = byId('scrollToEndBtn');
    if (scrollButton) scrollButton.title = 'Jump to newest message';
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !byId('crump53Studio')?.hidden) closeStudio();
    });
    void refreshProjects();
    void refreshFeatures();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
