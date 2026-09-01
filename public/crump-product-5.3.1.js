(() => {
  'use strict';

  if (window.__crump531Loaded) return;
  window.__crump531Loaded = true;

  const ACCEPT = [
    'image/*', 'application/pdf', '.docx', '.xlsx', '.pptx',
    '.txt', '.md', '.csv', '.tsv', '.json', '.html', '.rtf',
  ].join(',');
  const MAX_FILE_BYTES = 50 * 1024 * 1024;
  const MAX_QUEUE = 10;

  const state = {
    queue: [],
    menu: null,
    renameSheet: null,
    uploading: false,
  };

  const byId = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (bytes >= 1024 ** 2) return `${(bytes / (1024 ** 2)).toFixed(bytes >= 10 * 1024 ** 2 ? 0 : 1)} MB`;
    if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${bytes} B`;
  }

  async function api(path, options = {}) {
    const init = {...options};
    const headers = {...(init.headers || {})};
    if (init.body && typeof init.body !== 'string') {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(init.body);
    }
    const response = await fetch(path, {credentials: 'include', ...init, headers});
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok || data.success === false) {
      const error = new Error(data.error || data.message || `Request failed (${response.status})`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  function activeProjectId() {
    try { return localStorage.getItem('askcrump.activeProject53') || ''; }
    catch (_) { return ''; }
  }

  function projectStatus(message, isError = false) {
    const node = byId('crump531ReferenceStatus');
    if (!node) return;
    node.textContent = message || '';
    node.classList.toggle('is-error', Boolean(isError));
  }

  function validateReference(file) {
    if (!file?.name) return 'That file could not be read.';
    if (file.size <= 0) return `${file.name} is empty.`;
    if (file.size > MAX_FILE_BYTES) return `${file.name} is larger than 50 MB.`;
    return null;
  }

  function addReferenceFiles(fileList) {
    const incoming = [...(fileList || [])];
    if (!incoming.length) return;
    const available = Math.max(0, MAX_QUEUE - state.queue.length);
    if (!available) {
      projectStatus(`Add up to ${MAX_QUEUE} reference files at a time.`, true);
      return;
    }
    for (const file of incoming.slice(0, available)) {
      const issue = validateReference(file);
      if (issue) {
        projectStatus(issue, true);
        continue;
      }
      state.queue.push({
        id: crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`,
        file,
      });
    }
    renderReferenceQueue();
  }

  function renderReferenceQueue() {
    const list = byId('crump531ReferenceQueue');
    if (!list) return;
    if (!state.queue.length) {
      list.innerHTML = '<div class="crump531-empty">No reference files selected.</div>';
      return;
    }
    list.innerHTML = state.queue.map(item => `
      <div class="crump531-file-row" data-queued-id="${escapeHtml(item.id)}">
        <div class="crump531-file-copy">
          <strong>${escapeHtml(item.file.name)}</strong>
          <small>${escapeHtml(item.file.type || 'File')} · ${formatBytes(item.file.size)}</small>
        </div>
        <button type="button" class="crump531-icon-button" data-remove-queued="${escapeHtml(item.id)}" aria-label="Remove ${escapeHtml(item.file.name)}">×</button>
      </div>
    `).join('');
    list.querySelectorAll('[data-remove-queued]').forEach(button => {
      button.addEventListener('click', () => {
        state.queue = state.queue.filter(item => item.id !== button.dataset.removeQueued);
        renderReferenceQueue();
      });
    });
  }

  async function uploadProjectReference(file, projectId) {
    if (!window.CrumpFileTools?.upload) {
      throw new Error('Ask Crump file tools are not ready yet. Try again in a moment.');
    }
    const completedFile = await window.CrumpFileTools.upload(file);
    await api(`/api/projects/${encodeURIComponent(projectId)}/files`, {
      method: 'POST',
      body: {fileId: completedFile.id, role: 'reference'},
    });
    return completedFile;
  }

  async function waitForProjectId(previousId, editing) {
    for (let attempt = 0; attempt < 80; attempt += 1) {
      const projectId = activeProjectId();
      const status = byId('crump53ProjectStatus')?.textContent || '';
      if (projectId && (editing || projectId !== previousId || /project saved/i.test(status))) {
        return projectId;
      }
      if (/invalid|failed|error|required|limit/i.test(status)) return '';
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    return '';
  }

  async function attachQueuedAfterSave(previousId, editing) {
    if (state.uploading || !state.queue.length) return;
    const projectId = await waitForProjectId(previousId, editing);
    if (!projectId) {
      projectStatus('Save the Project successfully before reference files can be attached.', true);
      return;
    }

    state.uploading = true;
    const pending = [...state.queue];
    let completed = 0;
    try {
      for (const item of pending) {
        projectStatus(`Adding ${item.file.name}… ${completed + 1} of ${pending.length}`);
        await uploadProjectReference(item.file, projectId);
        completed += 1;
        state.queue = state.queue.filter(candidate => candidate.id !== item.id);
        renderReferenceQueue();
      }
      projectStatus(`${completed} reference file${completed === 1 ? '' : 's'} added to this Project.`);
      await refreshProjectFiles();
    } catch (error) {
      projectStatus(error.message || 'A reference file could not be added.', true);
    } finally {
      state.uploading = false;
    }
  }

  function projectFileGroup(file) {
    const role = String(file.projectRole || file.project_role || 'reference').toLowerCase();
    return /generated|manuscript|export|video|document/.test(role) ? 'created' : 'reference';
  }

  function renderProjectFileGroup(title, items) {
    if (!items.length) return '';
    return `
      <div class="crump531-project-file-group">
        <div class="crump531-project-file-heading">${escapeHtml(title)}</div>
        ${items.map(file => `
          <div class="crump531-file-row" data-project-file="${escapeHtml(file.id)}">
            <button type="button" class="crump531-file-open" data-open-project-file="${escapeHtml(file.id)}">
              <strong>${escapeHtml(file.name || 'File')}</strong>
              <small>${escapeHtml(file.projectRole || 'reference')} · ${formatBytes(file.size)}</small>
            </button>
            <button type="button" class="crump531-use-file" data-download-project-file="${escapeHtml(file.id)}">Download</button>
            <button type="button" class="crump531-use-file" data-use-project-file="${escapeHtml(file.id)}">Use in chat</button>
          </div>
        `).join('')}
      </div>
    `;
  }

  async function refreshProjectFiles() {
    const card = byId('crump531ProjectFilesCard');
    const list = byId('crump531ProjectFilesList');
    if (!card || !list) return;
    const projectId = activeProjectId();
    if (!projectId) {
      card.hidden = true;
      list.innerHTML = '';
      return;
    }
    card.hidden = false;
    list.innerHTML = '<div class="crump531-empty">Loading Project files…</div>';
    try {
      const data = await api(`/api/projects/${encodeURIComponent(projectId)}/files`);
      if (activeProjectId() !== projectId) return;
      const files = Array.isArray(data.files) ? data.files : [];
      if (!files.length) {
        list.innerHTML = '<div class="crump531-empty">No Project files yet.</div>';
        return;
      }
      const references = files.filter(file => projectFileGroup(file) === 'reference');
      const created = files.filter(file => projectFileGroup(file) === 'created');
      list.innerHTML =
        renderProjectFileGroup('References', references) +
        renderProjectFileGroup('Created here', created);

      const byFileId = new Map(files.map(file => [String(file.id), file]));
      list.querySelectorAll('[data-open-project-file]').forEach(button => {
        button.addEventListener('click', () => {
          const file = byFileId.get(String(button.dataset.openProjectFile));
          if (!file?.id) return;
          window.CrumpFileTools?.open?.(file, false);
        });
      });
      list.querySelectorAll('[data-download-project-file]').forEach(button => {
        button.addEventListener('click', () => {
          const file = byFileId.get(String(button.dataset.downloadProjectFile));
          if (!file?.id) return;
          window.CrumpFileTools?.open?.(file, true);
        });
      });
      list.querySelectorAll('[data-use-project-file]').forEach(button => {
        button.addEventListener('click', () => {
          const file = byFileId.get(String(button.dataset.useProjectFile));
          if (!file) return;
          if (!window.CrumpFileTools?.addReference) {
            projectStatus('Open a conversation first, then try again.', true);
            return;
          }
          window.CrumpFileTools.addReference(file);
          byId('crump53Close')?.click();
          window.showToast?.(`${file.name || 'File'} added to the conversation.`, 'success');
        });
      });
    } catch (error) {
      if (activeProjectId() !== projectId) return;
      list.innerHTML = `<div class="crump531-empty is-error"><span>${escapeHtml(error.message || 'Could not load Project files.')}</span> <button type="button" class="crump531-use-file" data-retry-project-files>Retry</button></div>`;
      list.querySelector('[data-retry-project-files]')?.addEventListener(
        'click',
        () => void refreshProjectFiles(),
      );
    }
  }

  let projectFilesRefreshTimer = 0;

  function hideProjectFiles() {
    const card = byId('crump531ProjectFilesCard');
    const list = byId('crump531ProjectFilesList');
    if (card) card.hidden = true;
    if (list) list.innerHTML = '';
  }

  function hydrateVisibleProjectFiles() {
    if (projectFilesRefreshTimer) window.clearTimeout(projectFilesRefreshTimer);
    projectFilesRefreshTimer = window.setTimeout(() => {
      projectFilesRefreshTimer = 0;
      const studio = byId('crump53Studio');
      const sheet = byId('crump53Sheet');
      if (studio?.hidden || sheet?.dataset.crump53Section !== 'projects' || sheet?.dataset.projectView !== 'detail') {
        hideProjectFiles();
        return;
      }
      void refreshProjectFiles();
    }, 0);
  }

  function installProjectReferences() {
    const form = byId('crump53ProjectForm');
    if (!form || form.dataset.crump531References === 'true') return;
    form.dataset.crump531References = 'true';

    const description = byId('crump53ProjectDescription')?.closest('.crump53-label');
    const instructions = byId('crump53ProjectInstructions')?.closest('.crump53-label');
    const referenceBox = document.createElement('div');
    referenceBox.className = 'crump531-reference-box';
    referenceBox.innerHTML = `
      <div class="crump531-reference-head">
        <div>
          <strong>Reference files</strong>
          <span>Optional · images, PDFs, documents, spreadsheets, and notes that belong with this Project.</span>
        </div>
        <button type="button" class="crump53-button" id="crump531AddReferences">Add files</button>
      </div>
      <input id="crump531ReferenceInput" type="file" multiple accept="${ACCEPT}" hidden>
      <div id="crump531ReferenceQueue" class="crump531-reference-list"></div>
      <div id="crump531ReferenceStatus" class="crump53-status" aria-live="polite"></div>
    `;
    if (instructions) form.insertBefore(referenceBox, instructions);
    else if (description?.nextSibling) form.insertBefore(referenceBox, description.nextSibling);
    else form.appendChild(referenceBox);

    byId('crump531AddReferences')?.addEventListener('click', () => byId('crump531ReferenceInput')?.click());
    byId('crump531ReferenceInput')?.addEventListener('change', event => {
      addReferenceFiles(event.target.files);
      event.target.value = '';
    });
    renderReferenceQueue();

    const projectPanel = form.closest('[data-crump53-panel="projects"]');
    const grid = projectPanel?.querySelector('.crump53-grid');
    const conversationsCard = byId('crump53ProjectConversationsCard');
    if (projectPanel && grid && !byId('crump531ProjectFilesCard')) {
      const card = document.createElement('div');
      card.id = 'crump531ProjectFilesCard';
      card.className = 'crump53-card crump531-project-files-card';
      card.hidden = true;
      card.innerHTML = `
        <div class="crump531-reference-head">
          <div>
            <h3>Project files</h3>
            <p>References stay with the Project. Things Crump creates here show up here too.</p>
          </div>
        </div>
        <div id="crump531ProjectFilesList"></div>
      `;
      if (conversationsCard) conversationsCard.insertAdjacentElement('afterend', card);
      else grid.insertAdjacentElement('afterend', card);
    }

    form.addEventListener('submit', () => {
      if (!state.queue.length) return;
      const previousId = activeProjectId();
      const editing = /edit project/i.test(byId('crump53ProjectFormTitle')?.textContent || '');
      void attachQueuedAfterSave(previousId, editing);
    }, true);

    byId('crump53NewProject')?.addEventListener('click', () => {
      state.queue = [];
      renderReferenceQueue();
      hideProjectFiles();
    });
    byId('crump53ProjectBack')?.addEventListener('click', hideProjectFiles);
    window.addEventListener('crump:project-target-changed', hydrateVisibleProjectFiles);
    hydrateVisibleProjectFiles();
  }

  function closeChatMenu() {
    state.menu?.remove();
    state.menu = null;
  }

  function renameChat(chatId) {
    closeChatMenu();
    const chat = (window.chats || []).find(item => String(item.id || item.chat_id) === String(chatId));
    if (!chat) return;

    state.renameSheet?.remove();
    const overlay = document.createElement('div');
    overlay.className = 'crump531-rename-overlay';
    overlay.innerHTML = `
      <section class="crump531-rename-sheet" role="dialog" aria-modal="true" aria-label="Rename conversation">
        <div class="crump531-rename-kicker">CONVERSATION</div>
        <h3>Rename chat</h3>
        <input class="crump531-rename-input" maxlength="120" value="${escapeHtml(chat.title || 'New conversation')}" aria-label="Conversation name">
        <div class="crump531-rename-actions">
          <button type="button" class="crump531-secondary">Cancel</button>
          <button type="button" class="crump531-primary">Save name</button>
        </div>
      </section>
    `;
    document.body.appendChild(overlay);
    state.renameSheet = overlay;
    const input = overlay.querySelector('input');
    const cancel = overlay.querySelector('.crump531-secondary');
    const save = overlay.querySelector('.crump531-primary');
    const close = () => { overlay.remove(); if (state.renameSheet === overlay) state.renameSheet = null; };
    cancel.addEventListener('click', close);
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
    save.addEventListener('click', () => {
      const title = String(input.value || '').replace(/\s+/g, ' ').trim().slice(0, 120);
      if (!title) {
        input.focus();
        return;
      }
      chat.title = title;
      chat.updatedAt = new Date().toISOString();
      chat.revision = Math.max(1, Number(chat.revision || 0) + 1);
      window.saveChats?.();
      window.renderChatsList?.();
      void window.syncChatsToServer?.();
      close();
      window.showToast?.('Conversation renamed.', 'success');
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        save.click();
      } else if (event.key === 'Escape') {
        close();
      }
    });
    setTimeout(() => { input.focus(); input.select(); }, 20);
  }

  function openChatMenu(button, chatId) {
    closeChatMenu();
    const menu = document.createElement('div');
    menu.className = 'crump531-chat-menu-popover';
    menu.innerHTML = `
      <button type="button" data-crump531-action="rename">Rename</button>
      <button type="button" data-crump531-action="delete" class="is-danger">Delete</button>
    `;
    document.body.appendChild(menu);
    state.menu = menu;
    const rect = button.getBoundingClientRect();
    menu.style.top = `${Math.min(window.innerHeight - 120, rect.bottom + 6)}px`;
    menu.style.left = `${Math.max(12, Math.min(window.innerWidth - 170, rect.right - 160))}px`;
    menu.querySelector('[data-crump531-action="rename"]').addEventListener('click', () => renameChat(chatId));
    menu.querySelector('[data-crump531-action="delete"]').addEventListener('click', () => {
      closeChatMenu();
      window.deleteChat?.(chatId);
    });
    setTimeout(() => {
      document.addEventListener('pointerdown', event => {
        if (menu.contains(event.target) || event.target === button) return;
        closeChatMenu();
      }, {once: true});
    }, 0);
  }

  function wireChatMenuDelegation() {
    if (document.documentElement.dataset.crump531ChatMenuDelegated === 'true') return;
    document.documentElement.dataset.crump531ChatMenuDelegated = 'true';

    // Capture the exact action before the clickable conversation row can handle
    // it. A single delegated listener also survives chat-list hydration and the
    // touch hit-testing differences between Safari, installed PWAs, and Chromium.
    document.addEventListener('click', event => {
      const button = event.target.closest?.('.crump531-chat-menu-button');
      const item = button?.closest?.('.chat-item[data-chat-id]');
      if (!button || !item) return;
      event.preventDefault();
      event.stopPropagation();
      openChatMenu(button, item.dataset.chatId);
    }, true);
  }

  function enhanceChatList() {
    document.querySelectorAll('#chatsList .chat-item[data-chat-id]').forEach(item => {
      if (item.dataset.crump531Actions === 'true') return;
      item.dataset.crump531Actions = 'true';
      item.classList.add('crump531-chat-actions-ready');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'crump531-chat-menu-button';
      button.setAttribute('aria-label', 'Conversation options');
      button.textContent = '•••';
      item.appendChild(button);
    });
  }

  function installObservers() {
    wireChatMenuDelegation();
    const observer = new MutationObserver(() => {
      installProjectReferences();
      enhanceChatList();
    });
    observer.observe(document.documentElement, {childList: true, subtree: true});
    installProjectReferences();
    enhanceChatList();
  }

  if (document.readyState === 'complete') setTimeout(installObservers, 60);
  else window.addEventListener('load', () => setTimeout(installObservers, 60), {once: true});
})();
