(() => {
  'use strict';

  if (window.__crumpLibrary57Loaded) return;
  window.__crumpLibrary57Loaded = true;

  const SOURCE_ACCEPT = '.docx,.pdf,.epub,.txt,.md,application/pdf,application/epub+zip,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  const COVER_ACCEPT = 'image/jpeg,image/png,image/webp,image/heic,image/heif,image/*';
  const PREF_KEY = 'askcrump.library57.preferences';
  const LAYOUTS = new Set(['grid', 'list', 'book']);
  const SORTS = new Set(['updated', 'title', 'author', 'status', 'words', 'project']);
  const COVER_FILTERS = new Set(['all', 'imported', 'created', 'front', 'complete', 'needs-cover']);

  function readPreferences() {
    try {
      const raw = JSON.parse(localStorage.getItem(PREF_KEY) || '{}');
      return {
        layout: LAYOUTS.has(raw.layout) ? raw.layout : 'grid',
        sort: SORTS.has(raw.sort) ? raw.sort : 'updated',
        coverFilter: COVER_FILTERS.has(raw.coverFilter) ? raw.coverFilter : 'all',
      };
    } catch (_) {
      return {layout: 'grid', sort: 'updated', coverFilter: 'all'};
    }
  }

  const preferences = readPreferences();
  const state = {
    books: [],
    deletedBooks: [],
    projects: [],
    projectLimit: -1,
    search: '',
    status: 'all',
    coverFilter: preferences.coverFilter,
    sort: preferences.sort,
    layout: preferences.layout,
    installed: false,
    modal: null,
    coverUrls: new Map(),
  };

  const byId = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);

  function show(message, type = 'success') {
    if (window.showToast) window.showToast(message, type);
    else console[type === 'error' ? 'error' : 'log'](message);
  }

  function savePreferences() {
    try {
      localStorage.setItem(PREF_KEY, JSON.stringify({
        layout: state.layout,
        sort: state.sort,
        coverFilter: state.coverFilter,
      }));
    } catch (_) {}
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

  function fileStem(name) {
    return String(name || 'Ask-Crump').replace(/\.[^.]+$/, '').replace(/[^\w\- ()]+/g, '_').slice(0, 100) || 'Ask-Crump';
  }

  function isMedia(file) {
    const type = String(file?.type || '').toLowerCase();
    return type.startsWith('image/') || type.startsWith('video/');
  }

  async function signedFile(file) {
    if (!file?.id) throw new Error('That saved media item is missing its Library ID.');
    const data = await api(`/api/files/${encodeURIComponent(file.id)}/signed`);
    if (!data.url) throw new Error('Crump could not prepare that media file.');
    return data;
  }

  async function androidAlbum(Media) {
    const response = await Media.getAlbums();
    let album = (response?.albums || []).find(item => String(item?.name || '').toLowerCase() === 'ask crump');
    if (album?.identifier) return album.identifier;

    await Media.createAlbum({name: 'Ask Crump'});
    const refreshed = await Media.getAlbums();
    album = (refreshed?.albums || []).find(item => String(item?.name || '').toLowerCase() === 'ask crump');
    if (!album?.identifier) throw new Error('Ask Crump could not prepare a Photos album.');
    return album.identifier;
  }

  async function saveNativeMedia(file) {
    const Media = window.CrumpNative?.Media;
    const Capacitor = window.CrumpNative?.Capacitor;
    if (!window.CrumpAPI?.isNative || !Media || !Capacitor) return false;

    const signed = await signedFile(file);
    const type = String(file.type || signed.mimeType || '').toLowerCase();
    const platform = Capacitor.getPlatform?.() || '';
    const options = {
      path: signed.url,
      fileName: fileStem(file.name || signed.name),
    };

    if (platform === 'android') options.albumIdentifier = await androidAlbum(Media);

    if (type.startsWith('video/')) {
      await Media.saveVideo(options);
      show('Video saved to Photos.', 'success');
    } else if (type.startsWith('image/')) {
      await Media.savePhoto(options);
      show('Image saved to Photos.', 'success');
    } else {
      return false;
    }
    return true;
  }

  async function shareMediaFile(file) {
    if (!navigator.share || !window.File) return false;
    try {
      const signed = await signedFile(file);
      const response = await fetch(signed.url, {cache: 'no-store'});
      if (!response.ok) throw new Error('Could not read that media file.');
      const blob = await response.blob();
      const name = file.name || signed.name || (String(blob.type).startsWith('video/') ? 'Ask-Crump-video.mp4' : 'Ask-Crump-image.png');
      const shareFile = new File([blob], name, {type: blob.type || file.type || 'application/octet-stream'});
      if (navigator.canShare && !navigator.canShare({files: [shareFile]})) return false;
      await navigator.share({files: [shareFile], title: name});
      return true;
    } catch (error) {
      if (error?.name === 'AbortError') return true;
      console.warn('Ask Crump media share fallback failed:', error);
      return false;
    }
  }

  function mobileLike() {
    return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '') ||
      Boolean(window.matchMedia?.('(pointer: coarse)').matches);
  }

  async function saveMedia(file) {
    if (!isMedia(file)) return false;
    try {
      if (await saveNativeMedia(file)) return true;
    } catch (error) {
      console.warn('Native Photos save failed; falling back:', error);
      show(error.message || 'Could not save directly to Photos. Opening another save option.', 'warning');
    }
    if (!mobileLike()) return false;
    return shareMediaFile(file);
  }

  async function coverUrl(file) {
    if (!file?.id) return '';
    if (state.coverUrls.has(file.id)) return state.coverUrls.get(file.id);
    try {
      const signed = await signedFile(file);
      state.coverUrls.set(file.id, signed.url || '');
      return signed.url || '';
    } catch (_) {
      return '';
    }
  }

  function formatCount(value) {
    const number = Number(value || 0);
    if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}m`;
    if (number >= 1_000) return `${Math.round(number / 1_000)}k`;
    return String(number);
  }

  function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'});
  }

  function coverState(book) {
    if (book.frontCover?.id && book.backCover?.id) return 'complete';
    if (book.frontCover?.id) return 'front';
    return 'draft';
  }

  function bookMatches(book) {
    const needle = state.search.trim().toLowerCase();
    if (state.status !== 'all' && String(book.status || 'draft') !== state.status) return false;

    const covers = coverState(book);
    if (state.coverFilter === 'imported' && book.origin !== 'imported') return false;
    if (state.coverFilter === 'created' && book.origin === 'imported') return false;
    if (state.coverFilter === 'front' && covers === 'draft') return false;
    if (state.coverFilter === 'complete' && covers !== 'complete') return false;
    if (state.coverFilter === 'needs-cover' && covers !== 'draft') return false;

    if (!needle) return true;
    return [
      book.title, book.subtitle, book.authorName, book.projectName,
      book.sourceFile?.name, book.origin,
    ].some(value => String(value || '').toLowerCase().includes(needle));
  }

  function compareText(a, b) {
    return String(a || '').localeCompare(String(b || ''), undefined, {sensitivity: 'base'});
  }

  function sortBooks(books) {
    return [...books].sort((a, b) => {
      if (state.sort === 'title') return compareText(a.title, b.title);
      if (state.sort === 'author') return compareText(a.authorName, b.authorName) || compareText(a.title, b.title);
      if (state.sort === 'status') return compareText(a.status, b.status) || compareText(a.title, b.title);
      if (state.sort === 'words') return Number(b.wordCount || 0) - Number(a.wordCount || 0);
      if (state.sort === 'project') return compareText(a.projectName, b.projectName) || compareText(a.title, b.title);
      return new Date(b.updatedAt || 0).getTime() - new Date(a.updatedAt || 0).getTime();
    });
  }

  function coverMarkup(book, suffix = '') {
    const title = escapeHtml(book.title || 'Untitled manuscript');
    const author = escapeHtml(book.authorName || 'Ask Crump Library');
    const maturity = coverState(book);
    return `
      <div class="crump57-cover is-${maturity}" data-cover-book="${escapeHtml(book.id)}${escapeHtml(suffix)}">
        <div class="crump57-cover-placeholder">
          <span></span>
          <div><strong>${title}</strong><small>${author}</small></div>
        </div>
      </div>`;
  }

  async function hydrateCovers(container, books, suffix = '') {
    for (const book of books) {
      if (!book.frontCover?.id) continue;
      const selector = `[data-cover-book="${CSS.escape(String(book.id) + suffix)}"]`;
      const node = container.querySelector(selector);
      if (!node || node.querySelector('img')) continue;
      const url = await coverUrl(book.frontCover);
      if (!url || !node.isConnected) continue;
      const image = document.createElement('img');
      image.src = url;
      image.alt = `${book.title || 'Book'} front cover`;
      image.loading = 'lazy';
      node.appendChild(image);
    }
  }

  function layoutButtonMarkup(layout, label) {
    const disabled = layout === 'book' && !state.books.some(book => book.frontCover?.id);
    return `<button type="button" class="crump57-layout-button ${state.layout === layout ? 'is-active' : ''}" data-crump57-layout="${layout}" ${disabled ? 'disabled title="Add a front cover to unlock Book View"' : ''}>${label}</button>`;
  }

  function updateLayoutControls() {
    const controls = byId('crump57LayoutControls');
    if (!controls) return;
    if (state.layout === 'book' && !state.books.some(book => book.frontCover?.id)) state.layout = 'grid';
    controls.innerHTML = [
      layoutButtonMarkup('grid', 'Grid'),
      layoutButtonMarkup('list', 'List'),
      layoutButtonMarkup('book', 'Book'),
    ].join('');
    controls.querySelectorAll('[data-crump57-layout]').forEach(button => {
      button.addEventListener('click', () => {
        if (button.disabled) return;
        state.layout = button.dataset.crump57Layout || 'grid';
        savePreferences();
        renderBooks();
      });
    });
  }

  function bookCardMarkup(book) {
    const id = escapeHtml(book.id);
    const origin = book.origin === 'imported' ? 'Imported' : 'Created in Crump';
    const words = `${formatCount(book.wordCount)} words`;
    const sections = `${Number(book.sectionCount || 0)} section${Number(book.sectionCount || 0) === 1 ? '' : 's'}`;
    const maturity = coverState(book);
    const coverLabel = maturity === 'complete' ? 'Front + back covers' : maturity === 'front' ? 'Front cover added' : 'Cover not added';
    const project = book.projectName ? `<span class="crump57-project-chip" title="${escapeHtml(book.projectName)}">${escapeHtml(book.projectName)}</span>` : '';
    const updated = formatDate(book.updatedAt);
    const previewAction = book.frontCover?.id
      ? `<button type="button" data-crump57-preview="${id}">Preview book</button>`
      : '';
    const sourceAction = book.sourceFile?.id
      ? `<button type="button" data-crump57-original="${id}">Open original source</button>`
      : '';

    return `
      <article class="crump57-book is-${maturity}" data-crump57-book="${id}">
        <div class="crump57-book-visual">
          ${coverMarkup(book)}
          <span class="crump57-spine" aria-hidden="true"></span>
        </div>
        <div class="crump57-book-body">
          <div class="crump57-book-kicker"><span>${escapeHtml(origin)}</span><span>${escapeHtml(book.status || 'draft')}</span></div>
          <h4 class="crump57-book-title" title="${escapeHtml(book.title)}">${escapeHtml(book.title || 'Untitled manuscript')}</h4>
          <span class="crump57-book-author">${escapeHtml(book.authorName || 'No author set')}</span>
          <div class="crump57-book-meta"><span>${words}</span><span>${sections}</span>${updated ? `<span>Updated ${escapeHtml(updated)}</span>` : ''}</div>
          <div class="crump57-book-footnote"><span>${escapeHtml(coverLabel)}</span>${project}</div>
          <div class="crump57-book-actions">
            <button type="button" class="crump53-button is-primary" data-crump57-open="${id}">Open</button>
            <button type="button" class="crump53-button" data-crump57-edit="${id}">Covers</button>
            <details class="crump57-more">
              <summary aria-label="More actions for ${escapeHtml(book.title || 'book')}">•••</summary>
              <div class="crump57-menu" role="menu">
                <button type="button" data-crump57-details="${id}">Edit details</button>
                ${previewAction}
                ${sourceAction}
                <span class="crump57-menu-divider"></span>
                <button type="button" class="is-danger" data-crump57-trash="${id}">Move to Recently Deleted</button>
              </div>
            </details>
          </div>
        </div>
      </article>`;
  }

  function closeOtherMenus(active) {
    document.querySelectorAll('.crump57-more[open]').forEach(details => {
      if (details !== active) details.removeAttribute('open');
    });
  }

  function bindBookActions(grid) {
    const map = new Map(state.books.map(book => [String(book.id), book]));
    grid.querySelectorAll('[data-crump57-open]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Open));
        if (!book) return;
        window.CrumpProduct53?.openManuscript?.({projectId: book.projectId, manuscriptId: book.id, title: book.title});
      });
    });
    grid.querySelectorAll('[data-crump57-edit], [data-crump57-details]').forEach(button => {
      button.addEventListener('click', () => {
        const id = button.dataset.crump57Edit || button.dataset.crump57Details;
        const book = map.get(String(id));
        if (book) openBookEditor(book);
      });
    });
    grid.querySelectorAll('[data-crump57-preview]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Preview));
        if (book) void openBookPreview(book);
      });
    });
    grid.querySelectorAll('[data-crump57-original]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Original));
        if (!book?.sourceFile) return;
        window.CrumpFileTools?.open?.(book.sourceFile, false);
      });
    });
    grid.querySelectorAll('[data-crump57-trash]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Trash));
        if (book) openTrashModal(book);
      });
    });
    grid.querySelectorAll('.crump57-more').forEach(details => {
      details.addEventListener('toggle', () => { if (details.open) closeOtherMenus(details); });
    });
  }

  function renderBooks() {
    const grid = byId('crump57Bookshelf');
    if (!grid) return;

    updateLayoutControls();
    const books = sortBooks(state.books.filter(bookMatches));
    grid.className = `crump57-bookshelf is-layout-${state.layout}`;
    if (!books.length) {
      const hasAny = state.books.length > 0;
      grid.innerHTML = `
        <div class="crump57-empty">
          <strong>${hasAny ? 'No books match that view.' : 'Your shelf is ready.'}</strong>
          ${hasAny
            ? 'Try another search, status, or cover filter.'
            : 'Create a manuscript with Crump or import a book you already started somewhere else.'}
        </div>`;
      return;
    }

    grid.innerHTML = books.map(bookCardMarkup).join('');
    bindBookActions(grid);
    void hydrateCovers(grid, books);
  }

  async function refreshDeletedBooks() {
    try {
      const data = await api('/api/library/books/deleted');
      state.deletedBooks = Array.isArray(data.books) ? data.books : [];
    } catch (_) {
      state.deletedBooks = [];
    }
    const button = byId('crump57Deleted');
    if (button) {
      const count = state.deletedBooks.length;
      button.textContent = count ? `Recently Deleted · ${count}` : 'Recently Deleted';
    }
  }

  async function refreshBooks() {
    const grid = byId('crump57Bookshelf');
    if (grid) grid.innerHTML = '<div class="crump57-empty"><strong>Loading Library…</strong>Crump is collecting your books.</div>';
    try {
      const data = await api('/api/library/books');
      state.books = Array.isArray(data.books) ? data.books : [];
      await refreshDeletedBooks();
      renderBooks();
    } catch (error) {
      if (grid) grid.innerHTML = `<div class="crump57-empty"><strong>Library could not load.</strong>${escapeHtml(error.message || 'Try again in a moment.')}</div>`;
    }
  }

  async function refreshProjects() {
    try {
      const data = await api('/api/projects');
      state.projects = Array.isArray(data.projects) ? data.projects : [];
      state.projectLimit = Number(data.limit ?? 0);
    } catch (_) {
      state.projects = [];
      state.projectLimit = -1;
    }
  }

  function projectOptions(selected = '') {
    const limitReached = state.projectLimit >= 0 && state.projects.length >= state.projectLimit;
    const createLabel = limitReached
      ? 'Project limit reached — choose an existing Project'
      : 'Create a dedicated Project for this book';
    return [
      `<option value="" ${limitReached ? 'disabled' : ''}>${escapeHtml(createLabel)}</option>`,
      ...state.projects.map(project => `<option value="${escapeHtml(project.id)}" ${String(project.id) === String(selected) ? 'selected' : ''}>Add to: ${escapeHtml(project.name)}</option>`),
    ].join('');
  }

  function closeModal() {
    state.modal?.remove();
    state.modal = null;
  }

  function bindModalClose(overlay) {
    const close = () => closeModal();
    overlay.querySelector('.crump57-close')?.addEventListener('click', close);
    overlay.querySelectorAll('[data-crump57-cancel]').forEach(button => button.addEventListener('click', close));
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
    return close;
  }

  function mountModal(markup) {
    closeModal();
    const wrapper = document.createElement('div');
    wrapper.innerHTML = markup;
    const overlay = wrapper.firstElementChild;
    document.body.appendChild(overlay);
    state.modal = overlay;
    bindModalClose(overlay);
    return overlay;
  }

  function bindCoverPreview(input, image, box) {
    input?.addEventListener('change', () => {
      const file = input.files?.[0];
      if (!file) {
        image.removeAttribute('src');
        box.classList.remove('has-image');
        return;
      }
      const url = URL.createObjectURL(file);
      image.src = url;
      box.classList.add('has-image');
      image.onload = () => URL.revokeObjectURL(url);
    });
  }

  async function uploadOptional(input, label) {
    const file = input?.files?.[0];
    if (!file) return null;
    if (!window.CrumpFileTools?.upload) throw new Error('Ask Crump file upload tools are still loading.');
    if (label === 'cover' && !String(file.type || '').startsWith('image/')) throw new Error('Cover files must be images.');
    return window.CrumpFileTools.upload(file);
  }

  function importModalMarkup() {
    return `
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet" role="dialog" aria-modal="true" aria-label="Import manuscript">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">ASK CRUMP LIBRARY</div><h3>Import a manuscript</h3><p>Bring an existing book into Crump without rewriting the original.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <form class="crump57-sheet-body" id="crump57ImportForm">
            <div class="crump57-form-grid">
              <label class="crump57-field is-wide">
                <span>Manuscript file</span>
                <div class="crump57-upload">
                  <div class="crump57-upload-copy"><strong id="crump57SourceName">Choose DOCX, PDF, EPUB, TXT, or Markdown</strong><small>The original file stays in your private Ask Crump storage.</small></div>
                  <input id="crump57SourceFile" type="file" accept="${SOURCE_ACCEPT}" required>
                </div>
              </label>
              <label class="crump57-field"><span>Title <small>Optional</small></span><input id="crump57Title" maxlength="180" placeholder="Crump can infer it from the file"></label>
              <label class="crump57-field"><span>Author</span><input id="crump57Author" maxlength="160" placeholder="Author name"></label>
              <label class="crump57-field is-wide"><span>Subtitle <small>Optional</small></span><input id="crump57Subtitle" maxlength="240" placeholder="Subtitle"></label>
              <label class="crump57-field is-wide"><span>Organization</span><select id="crump57Project">${projectOptions()}</select><small>By default, Crump creates a dedicated Project so the book's files, canon, and future chats stay together.</small></label>
              <label class="crump57-field">
                <span>Front cover <small>Optional</small></span>
                <div class="crump57-upload crump57-cover-pick" id="crump57FrontBox">
                  <img id="crump57FrontPreview" alt="">
                  <div class="crump57-upload-copy"><strong>Add front cover</strong><small>JPG, PNG, WebP, HEIC</small></div>
                  <input id="crump57FrontCover" type="file" accept="${COVER_ACCEPT}">
                </div>
              </label>
              <label class="crump57-field">
                <span>Back cover <small>Optional</small></span>
                <div class="crump57-upload crump57-cover-pick" id="crump57BackBox">
                  <img id="crump57BackPreview" alt="">
                  <div class="crump57-upload-copy"><strong>Add back cover</strong><small>JPG, PNG, WebP, HEIC</small></div>
                  <input id="crump57BackCover" type="file" accept="${COVER_ACCEPT}">
                </div>
              </label>
            </div>
            <div class="crump57-import-status" id="crump57ImportStatus" aria-live="polite"></div>
            <div class="crump57-sheet-actions">
              <button type="button" class="crump53-button" data-crump57-cancel>Cancel</button>
              <button type="submit" class="crump53-button is-primary" id="crump57ImportSubmit">Import to Library</button>
            </div>
          </form>
        </section>
      </div>`;
  }

  async function openImportModal() {
    await refreshProjects();
    const overlay = mountModal(importModalMarkup());
    const source = byId('crump57SourceFile');
    const front = byId('crump57FrontCover');
    const back = byId('crump57BackCover');
    const status = byId('crump57ImportStatus');
    const submit = byId('crump57ImportSubmit');

    source?.addEventListener('change', () => {
      byId('crump57SourceName').textContent = source.files?.[0]?.name || 'Choose DOCX, PDF, EPUB, TXT, or Markdown';
    });
    bindCoverPreview(front, byId('crump57FrontPreview'), byId('crump57FrontBox'));
    bindCoverPreview(back, byId('crump57BackPreview'), byId('crump57BackBox'));

    byId('crump57ImportForm')?.addEventListener('submit', async event => {
      event.preventDefault();
      const sourceFile = source?.files?.[0];
      if (!sourceFile) {
        status.textContent = 'Choose a manuscript file first.';
        status.classList.add('is-error');
        return;
      }

      submit.disabled = true;
      status.classList.remove('is-error');
      try {
        status.textContent = 'Uploading original manuscript…';
        const sourceAsset = await window.CrumpFileTools.upload(sourceFile);
        status.textContent = 'Uploading covers…';
        const frontAsset = await uploadOptional(front, 'cover');
        const backAsset = await uploadOptional(back, 'cover');
        status.textContent = 'Reading chapters and building your Library entry…';
        const data = await api('/api/library/books/import', {
          method: 'POST',
          body: {
            sourceFileId: sourceAsset.id,
            frontCoverFileId: frontAsset?.id || '',
            backCoverFileId: backAsset?.id || '',
            title: byId('crump57Title')?.value || '',
            subtitle: byId('crump57Subtitle')?.value || '',
            authorName: byId('crump57Author')?.value || '',
            projectId: byId('crump57Project')?.value || '',
          },
        });

        closeModal();
        state.coverUrls.clear();
        show(`${data.book?.title || 'Manuscript'} added to your Library.`, 'success');
        await refreshBooks();
        if (data.book?.projectId && data.book?.id) {
          window.CrumpProduct53?.openManuscript?.({projectId: data.book.projectId, manuscriptId: data.book.id, title: data.book.title});
        }
      } catch (error) {
        status.textContent = error.message || 'The manuscript could not be imported.';
        status.classList.add('is-error');
      } finally {
        submit.disabled = false;
      }
    });
  }

  function bookEditorMarkup(book) {
    return `
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet" role="dialog" aria-modal="true" aria-label="Book details">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">BOOK DETAILS</div><h3>${escapeHtml(book.title)}</h3><p>Update shelf details or replace either cover.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <form class="crump57-sheet-body" id="crump57BookForm">
            <div class="crump57-form-grid">
              <label class="crump57-field"><span>Title</span><input id="crump57EditTitle" maxlength="180" value="${escapeHtml(book.title || '')}" required></label>
              <label class="crump57-field"><span>Author</span><input id="crump57EditAuthor" maxlength="160" value="${escapeHtml(book.authorName || '')}"></label>
              <label class="crump57-field is-wide"><span>Subtitle</span><input id="crump57EditSubtitle" maxlength="240" value="${escapeHtml(book.subtitle || '')}"></label>
              <label class="crump57-field is-wide"><span>Status</span><select id="crump57EditStatus">
                <option value="draft" ${book.status === 'draft' ? 'selected' : ''}>Draft</option>
                <option value="revising" ${book.status === 'revising' ? 'selected' : ''}>Revising</option>
                <option value="final" ${book.status === 'final' ? 'selected' : ''}>Final</option>
              </select></label>
              <label class="crump57-field">
                <span>Front cover</span>
                <div class="crump57-upload crump57-cover-pick" id="crump57EditFrontBox">
                  <img id="crump57EditFrontPreview" alt="">
                  <div class="crump57-upload-copy"><strong>${book.frontCover ? 'Replace front cover' : 'Add front cover'}</strong><small>Leave untouched to keep the current image</small></div>
                  <input id="crump57EditFront" type="file" accept="${COVER_ACCEPT}">
                </div>
              </label>
              <label class="crump57-field">
                <span>Back cover</span>
                <div class="crump57-upload crump57-cover-pick" id="crump57EditBackBox">
                  <img id="crump57EditBackPreview" alt="">
                  <div class="crump57-upload-copy"><strong>${book.backCover ? 'Replace back cover' : 'Add back cover'}</strong><small>Leave untouched to keep the current image</small></div>
                  <input id="crump57EditBack" type="file" accept="${COVER_ACCEPT}">
                </div>
              </label>
            </div>
            <div class="crump57-import-status" id="crump57EditStatusText" aria-live="polite"></div>
            <div class="crump57-sheet-actions">
              <button type="button" class="crump53-button" data-crump57-cancel>Cancel</button>
              <button type="submit" class="crump53-button is-primary" id="crump57BookSubmit">Save book</button>
            </div>
          </form>
        </section>
      </div>`;
  }

  async function setExistingCover(book, side) {
    const file = side === 'front' ? book.frontCover : book.backCover;
    const image = byId(side === 'front' ? 'crump57EditFrontPreview' : 'crump57EditBackPreview');
    const box = byId(side === 'front' ? 'crump57EditFrontBox' : 'crump57EditBackBox');
    if (!file?.id || !image || !box) return;
    const url = await coverUrl(file);
    if (url && image.isConnected) {
      image.src = url;
      box.classList.add('has-image');
    }
  }

  function openBookEditor(book) {
    mountModal(bookEditorMarkup(book));
    const front = byId('crump57EditFront');
    const back = byId('crump57EditBack');
    bindCoverPreview(front, byId('crump57EditFrontPreview'), byId('crump57EditFrontBox'));
    bindCoverPreview(back, byId('crump57EditBackPreview'), byId('crump57EditBackBox'));
    void setExistingCover(book, 'front');
    void setExistingCover(book, 'back');

    byId('crump57BookForm')?.addEventListener('submit', async event => {
      event.preventDefault();
      const status = byId('crump57EditStatusText');
      const submit = byId('crump57BookSubmit');
      submit.disabled = true;
      status.classList.remove('is-error');
      try {
        const changes = {
          title: byId('crump57EditTitle')?.value || '',
          subtitle: byId('crump57EditSubtitle')?.value || '',
          authorName: byId('crump57EditAuthor')?.value || '',
          status: byId('crump57EditStatus')?.value || 'draft',
        };
        if (front?.files?.[0]) {
          status.textContent = 'Uploading new front cover…';
          changes.frontCoverFileId = (await window.CrumpFileTools.upload(front.files[0])).id;
        }
        if (back?.files?.[0]) {
          status.textContent = 'Uploading new back cover…';
          changes.backCoverFileId = (await window.CrumpFileTools.upload(back.files[0])).id;
        }
        status.textContent = 'Saving Library details…';
        await api(`/api/library/books/${encodeURIComponent(book.id)}`, {method: 'PATCH', body: changes});
        closeModal();
        state.coverUrls.clear();
        await refreshBooks();
        show('Book updated.', 'success');
      } catch (error) {
        status.textContent = error.message || 'The book could not be updated.';
        status.classList.add('is-error');
      } finally {
        submit.disabled = false;
      }
    });
  }

  async function openBookPreview(book) {
    const overlay = mountModal(`
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet crump57-preview-sheet" role="dialog" aria-modal="true" aria-label="Book preview">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">BOOK PREVIEW</div><h3>${escapeHtml(book.title)}</h3><p>${escapeHtml(book.authorName || 'No author set')}</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <div class="crump57-sheet-body">
            <div class="crump57-preview-stage">
              <figure class="crump57-preview-cover"><div id="crump57PreviewFront" class="crump57-preview-image"><span>Front cover</span></div><figcaption>Front</figcaption></figure>
              <div class="crump57-preview-spine" aria-hidden="true"><span>${escapeHtml(book.title || '')}</span></div>
              <figure class="crump57-preview-cover"><div id="crump57PreviewBack" class="crump57-preview-image"><span>${book.backCover?.id ? 'Back cover' : 'Add a back cover to complete the book view'}</span></div><figcaption>Back</figcaption></figure>
            </div>
            <div class="crump57-preview-meta"><span>${formatCount(book.wordCount)} words</span><span>${Number(book.sectionCount || 0)} sections</span><span>${escapeHtml(book.status || 'draft')}</span></div>
            <div class="crump57-sheet-actions"><button type="button" class="crump53-button" data-crump57-cancel>Close</button><button type="button" class="crump53-button is-primary" id="crump57PreviewOpen">Open manuscript</button></div>
          </div>
        </section>
      </div>`);

    const frontNode = byId('crump57PreviewFront');
    const backNode = byId('crump57PreviewBack');
    if (book.frontCover?.id) {
      const url = await coverUrl(book.frontCover);
      if (url && overlay.isConnected) frontNode.innerHTML = `<img src="${escapeHtml(url)}" alt="${escapeHtml(book.title)} front cover">`;
    }
    if (book.backCover?.id) {
      const url = await coverUrl(book.backCover);
      if (url && overlay.isConnected) backNode.innerHTML = `<img src="${escapeHtml(url)}" alt="${escapeHtml(book.title)} back cover">`;
    }
    byId('crump57PreviewOpen')?.addEventListener('click', () => {
      closeModal();
      window.CrumpProduct53?.openManuscript?.({projectId: book.projectId, manuscriptId: book.id, title: book.title});
    });
  }

  function openTrashModal(book) {
    const sourceChoice = book.sourceFile?.id ? `
      <label class="crump57-check-row">
        <input type="checkbox" id="crump57DeleteSource">
        <span><strong>Also remove the original imported source from Files</strong><small>If another manuscript uses the same source, Crump will keep it.</small></span>
      </label>` : '';
    mountModal(`
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet crump57-confirm-sheet" role="dialog" aria-modal="true" aria-label="Move book to Recently Deleted">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">RECENTLY DELETED</div><h3>Move “${escapeHtml(book.title)}”?</h3><p>The book leaves your active Library but can be restored later.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <div class="crump57-sheet-body">
            <div class="crump57-confirm-note"><strong>Protected by default</strong><span>Your Project and cover files stay intact. Chapters and manuscript history stay recoverable until permanent deletion.</span></div>
            ${sourceChoice}
            <div class="crump57-import-status" id="crump57TrashStatus" aria-live="polite"></div>
            <div class="crump57-sheet-actions"><button type="button" class="crump53-button" data-crump57-cancel>Cancel</button><button type="button" class="crump53-button is-danger" id="crump57TrashConfirm">Move to Recently Deleted</button></div>
          </div>
        </section>
      </div>`);
    byId('crump57TrashConfirm')?.addEventListener('click', async () => {
      const button = byId('crump57TrashConfirm');
      const status = byId('crump57TrashStatus');
      button.disabled = true;
      try {
        const data = await api(`/api/library/books/${encodeURIComponent(book.id)}/trash`, {
          method: 'POST',
          body: {deleteSource: Boolean(byId('crump57DeleteSource')?.checked)},
        });
        closeModal();
        await refreshBooks();
        show(data.sourceFileKept ? 'Book moved to Recently Deleted. Shared source file was kept.' : 'Book moved to Recently Deleted.', 'success');
      } catch (error) {
        status.textContent = error.message || 'The book could not be moved.';
        status.classList.add('is-error');
        button.disabled = false;
      }
    });
  }

  function renderDeletedBooks(container) {
    if (!state.deletedBooks.length) {
      container.innerHTML = '<div class="crump57-empty"><strong>Recently Deleted is empty.</strong>Books you remove from the shelf will stay recoverable here until you permanently delete them.</div>';
      return;
    }
    container.innerHTML = state.deletedBooks.map(book => `
      <article class="crump57-deleted-book" data-deleted-book="${escapeHtml(book.id)}">
        <div class="crump57-deleted-cover">${coverMarkup(book, '-deleted')}</div>
        <div class="crump57-deleted-copy">
          <span class="crump53-kicker">REMOVED ${escapeHtml(formatDate(book.trashedAt) || '')}</span>
          <strong>${escapeHtml(book.title || 'Untitled manuscript')}</strong>
          <small>${escapeHtml(book.authorName || 'No author set')} · ${formatCount(book.wordCount)} words · ${Number(book.sectionCount || 0)} sections</small>
          <div class="crump57-deleted-actions"><button type="button" class="crump53-button is-primary" data-crump57-restore="${escapeHtml(book.id)}">Restore</button><button type="button" class="crump53-button is-danger" data-crump57-permanent="${escapeHtml(book.id)}">Delete permanently</button></div>
        </div>
      </article>`).join('');

    const map = new Map(state.deletedBooks.map(book => [String(book.id), book]));
    container.querySelectorAll('[data-crump57-restore]').forEach(button => {
      button.addEventListener('click', async () => {
        const book = map.get(String(button.dataset.crump57Restore));
        if (!book) return;
        button.disabled = true;
        try {
          await api(`/api/library/books/${encodeURIComponent(book.id)}/restore`, {method: 'POST', body: {}});
          await refreshBooks();
          renderDeletedBooks(container);
          show(`${book.title || 'Book'} restored.`, 'success');
        } catch (error) {
          show(error.message || 'The book could not be restored.', 'error');
          button.disabled = false;
        }
      });
    });
    container.querySelectorAll('[data-crump57-permanent]').forEach(button => {
      button.addEventListener('click', () => {
        const book = map.get(String(button.dataset.crump57Permanent));
        if (book) openPermanentDeleteModal(book);
      });
    });
    void hydrateCovers(container, state.deletedBooks, '-deleted');
  }

  async function openRecentlyDeleted() {
    await refreshDeletedBooks();
    mountModal(`
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet" role="dialog" aria-modal="true" aria-label="Recently Deleted books">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">LIBRARY SAFETY</div><h3>Recently Deleted</h3><p>Restore a manuscript or permanently remove it when you are certain.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <div class="crump57-sheet-body"><div id="crump57DeletedList" class="crump57-deleted-list"></div></div>
        </section>
      </div>`);
    renderDeletedBooks(byId('crump57DeletedList'));
  }

  function openPermanentDeleteModal(book) {
    mountModal(`
      <div class="crump57-overlay" role="presentation">
        <section class="crump57-sheet crump57-confirm-sheet" role="dialog" aria-modal="true" aria-label="Permanently delete book">
          <header class="crump57-sheet-head">
            <div><div class="crump53-kicker">PERMANENT DELETE</div><h3>Delete “${escapeHtml(book.title)}” forever?</h3><p>This cannot be undone.</p></div>
            <button type="button" class="crump57-close" aria-label="Close">×</button>
          </header>
          <div class="crump57-sheet-body">
            <div class="crump57-danger-note"><strong>Permanent means permanent.</strong><span>The manuscript, chapters, and manuscript-run history will be deleted. The Project and covers stay unless you remove them separately. If you chose to remove the original source when trashing the book, that source will also be permanently removed.</span></div>
            <label class="crump57-field"><span>Type DELETE to confirm</span><input id="crump57PermanentPhrase" autocomplete="off" placeholder="DELETE"></label>
            <div class="crump57-import-status" id="crump57PermanentStatus" aria-live="polite"></div>
            <div class="crump57-sheet-actions"><button type="button" class="crump53-button" data-crump57-cancel>Cancel</button><button type="button" class="crump53-button is-danger" id="crump57PermanentConfirm" disabled>Delete permanently</button></div>
          </div>
        </section>
      </div>`);
    const phrase = byId('crump57PermanentPhrase');
    const confirm = byId('crump57PermanentConfirm');
    phrase?.addEventListener('input', () => { confirm.disabled = phrase.value.trim() !== 'DELETE'; });
    confirm?.addEventListener('click', async () => {
      confirm.disabled = true;
      const status = byId('crump57PermanentStatus');
      try {
        const data = await api(`/api/library/books/${encodeURIComponent(book.id)}`, {method: 'DELETE'});
        closeModal();
        await refreshBooks();
        show(data.sourceCleanupPending
          ? `${book.title || 'Book'} deleted. Original source cleanup is still pending.`
          : `${book.title || 'Book'} permanently deleted.`,
        data.sourceCleanupPending ? 'warning' : 'success');
      } catch (error) {
        status.textContent = error.message || 'The book could not be permanently deleted.';
        status.classList.add('is-error');
        confirm.disabled = false;
      }
    });
  }

  function installLibraryPanel() {
    const manuscriptList = byId('crump53ManuscriptList');
    if (!manuscriptList) return false;
    const panel = manuscriptList.closest('[data-crump53-panel="manuscripts"]');
    const originalCard = manuscriptList.closest('.crump53-card');
    if (!panel || !originalCard) return false;

    const shell = panel.closest('.crump53-sheet');
    if (shell) shell.classList.add('crump57-library-shell');

    const manuscriptTab = document.querySelector('[data-crump53-tab="manuscripts"]');
    const filesTab = document.querySelector('[data-crump53-tab="library"]');
    if (manuscriptTab) manuscriptTab.textContent = 'Library';
    if (filesTab) filesTab.textContent = 'Files';

    const heading = originalCard.querySelector('h3');
    if (heading) heading.textContent = 'Current Project manuscript';
    const intro = heading?.nextElementSibling;
    if (intro?.tagName === 'P') intro.textContent = 'Open or continue the manuscript attached to the active Project. Your full bookshelf stays above.';

    if (!byId('crump57LibraryCard')) {
      const card = document.createElement('div');
      card.id = 'crump57LibraryCard';
      card.className = 'crump53-card crump57-library-card';
      card.innerHTML = `
        <div class="crump57-library-head">
          <div><div class="crump53-kicker">BOOKSHELF</div><h3>Your Library</h3><p>A calm home for books created with Crump and manuscripts you bring with you.</p></div>
          <div class="crump57-library-actions">
            <button type="button" class="crump53-button" id="crump57Deleted">Recently Deleted</button>
            <button type="button" class="crump53-button" id="crump57Import">Import manuscript</button>
            <button type="button" class="crump53-button is-primary" id="crump57New">New in Crump</button>
          </div>
        </div>
        <div class="crump57-library-toolbar">
          <label class="crump57-search"><span class="sr-only">Search Library</span><input type="search" id="crump57Search" placeholder="Search title, author, Project…" aria-label="Search Library"></label>
          <select id="crump57Filter" aria-label="Filter books by status">
            <option value="all">All statuses</option>
            <option value="draft">Draft</option>
            <option value="revising">Revising</option>
            <option value="final">Final</option>
          </select>
          <select id="crump57CoverFilter" aria-label="Filter books by source or cover">
            <option value="all">All books</option>
            <option value="imported">Imported</option>
            <option value="created">Created in Crump</option>
            <option value="front">Has front cover</option>
            <option value="complete">Front + back covers</option>
            <option value="needs-cover">Needs cover</option>
          </select>
          <select id="crump57Sort" aria-label="Sort Library">
            <option value="updated">Recently updated</option>
            <option value="title">Title</option>
            <option value="author">Author</option>
            <option value="status">Status</option>
            <option value="words">Word count</option>
            <option value="project">Project</option>
          </select>
          <div id="crump57LayoutControls" class="crump57-layout-controls" aria-label="Library layout"></div>
        </div>
        <div id="crump57Bookshelf" class="crump57-bookshelf"></div>`;
      panel.insertBefore(card, panel.firstElementChild);

      const coverFilter = byId('crump57CoverFilter');
      const sort = byId('crump57Sort');
      if (coverFilter) coverFilter.value = state.coverFilter;
      if (sort) sort.value = state.sort;

      byId('crump57Import')?.addEventListener('click', () => void openImportModal());
      byId('crump57New')?.addEventListener('click', () => byId('crump53NewManuscript')?.click());
      byId('crump57Deleted')?.addEventListener('click', () => void openRecentlyDeleted());
      byId('crump57Search')?.addEventListener('input', event => { state.search = event.target.value || ''; renderBooks(); });
      byId('crump57Filter')?.addEventListener('change', event => { state.status = event.target.value || 'all'; renderBooks(); });
      coverFilter?.addEventListener('change', event => {
        state.coverFilter = COVER_FILTERS.has(event.target.value) ? event.target.value : 'all';
        savePreferences();
        renderBooks();
      });
      sort?.addEventListener('change', event => {
        state.sort = SORTS.has(event.target.value) ? event.target.value : 'updated';
        savePreferences();
        renderBooks();
      });
    }

    state.installed = true;
    void refreshBooks();
    return true;
  }

  function relabelMediaActions(root = document) {
    const imageLabel = window.CrumpAPI?.isNative ? 'Save to Photos' : 'Save';
    const videoLabel = window.CrumpAPI?.isNative ? 'Save to Photos' : 'Save video';
    root.querySelectorAll?.('.crump50-image-actions button').forEach(button => {
      if (['Download', 'Save'].includes(button.textContent?.trim())) button.textContent = imageLabel;
    });
    root.querySelectorAll?.('.crump50-lightbox-bar button').forEach(button => {
      if (['Download', 'Save'].includes(button.textContent?.trim())) button.textContent = imageLabel;
    });
    root.querySelectorAll?.('.crump53-video-result-actions a[download]').forEach(link => { link.textContent = videoLabel; });
  }

  function mediaFileFromHref(href, fallbackName = 'Ask-Crump-video.mp4') {
    try {
      const url = new URL(href, location.href);
      const match = url.pathname.match(/\/api\/files\/([0-9a-f-]{36})\/content$/i);
      if (!match) return null;
      return {id: match[1], name: fallbackName, type: 'video/mp4', url: url.pathname};
    } catch (_) {
      return null;
    }
  }

  function installMediaInterception() {
    document.addEventListener('click', event => {
      if (!event.target.closest?.('.crump57-more')) closeOtherMenus(null);
      const link = event.target.closest?.('.crump53-video-result-actions a[download]');
      if (!link) return;
      const file = mediaFileFromHref(link.href, 'Ask-Crump-video.mp4');
      if (!file) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      void (async () => {
        const handled = await saveMedia(file);
        if (!handled) window.location.assign(`${file.url}?download=1`);
      })();
    }, true);

    const observer = new MutationObserver(records => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) relabelMediaActions(node);
        }
      }
      if (!state.installed) installLibraryPanel();
    });
    observer.observe(document.documentElement, {subtree: true, childList: true});
    relabelMediaActions();
  }

  function installWhenReady() {
    if (installLibraryPanel()) return;
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (installLibraryPanel() || attempts > 100) clearInterval(timer);
    }, 100);
  }

  window.CrumpLibrary57 = Object.freeze({
    refresh: refreshBooks,
    importManuscript: openImportModal,
    recentlyDeleted: openRecentlyDeleted,
    saveMedia,
  });

  installMediaInterception();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installWhenReady, {once: true});
  else installWhenReady();
})();
