(() => {
  'use strict';

  if (window.__crump50Loaded) return;
  window.__crump50Loaded = true;

  const MAX_FILES = 10;
  const MAX_FILE_BYTES = 50 * 1024 * 1024;
  const ACCEPT = [
    'image/*', 'application/pdf', '.docx', '.xlsx', '.pptx', '.txt', '.md', '.csv', '.tsv', '.json', '.html', '.rtf',
  ].join(',');
  const state = {
    attachments: [],
    tool: null,
    imageAspect: 'square',
    imageQuality: 'medium',
    documentFormat: null,
    documentPurpose: null,
    sending: false,
    menu: null,
    lightbox: null,
    imageRecovery: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const uid = () => crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;

  function currentChat() {
    return (window.chats || []).find(chat => (chat.id || chat.chat_id) === window.currentChatId) || null;
  }

  function touch(chat) {
    if (!chat) return;
    chat.updatedAt = new Date().toISOString();
    chat.revision = Math.max(1, Number(chat.revision || 0) + 1);
  }

  function saveAndRender(chat) {
    touch(chat);
    window.saveChats?.();
    const fresh = currentChat() || chat;
    window.renderMessages?.(fresh.messages || []);
    window.renderChatsList?.();
  }

  function show(message, tone = 'info') {
    window.showToast?.(message, tone);
  }

  function formatBytes(bytes) {
    const value = Number(bytes || 0);
    if (value >= 1024 ** 2) return `${(value / (1024 ** 2)).toFixed(value >= 10 * 1024 ** 2 ? 0 : 1)} MB`;
    if (value >= 1024) return `${Math.round(value / 1024)} KB`;
    return `${value} B`;
  }

  function fileKind(file) {
    const type = String(file?.type || '').toLowerCase();
    const name = String(file?.name || '').toLowerCase();
    if (type.startsWith('image/')) return 'image';
    if (type === 'application/pdf' || name.endsWith('.pdf')) return 'pdf';
    if (name.endsWith('.docx')) return 'word';
    if (name.endsWith('.xlsx')) return 'sheet';
    if (name.endsWith('.pptx')) return 'slides';
    if (name.endsWith('.csv') || name.endsWith('.tsv')) return 'table';
    return 'file';
  }

  function iconFor(kind) {
    const icons = {
      image: '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5z"/><circle cx="9" cy="9" r="1.5"/><path d="m5.5 17 4.2-4.4 3.1 3 2-2.1 3.7 3.5"/>',
      pdf: '<path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4"/><path d="M9.5 15h5M9.5 12h5"/>',
      word: '<path d="M6 3.5h12v17H6z"/><path d="M9 8.5 10.5 16 12 11l1.5 5L15 8.5"/>',
      sheet: '<rect x="5" y="3.5" width="14" height="17" rx="1"/><path d="M5 9h14M5 14h14M10 9v11M14.5 9v11"/>',
      slides: '<rect x="4" y="5" width="16" height="12" rx="1.5"/><path d="M8 21h8M12 17v4M8 9h8M8 12h5"/>',
      table: '<rect x="4" y="5" width="16" height="14" rx="1"/><path d="M4 10h16M9 5v14M15 5v14"/>',
      file: '<path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4"/>',
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[kind] || icons.file}</svg>`;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: 'same-origin',
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.message || data.error || `Request failed (${response.status})`);
      error.code = data.code;
      error.shouldRetry = !!data.shouldRetry;
      error.retryAfter = data.retryAfter;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function validateFile(file) {
    if (!file || !file.name) return 'That file could not be read.';
    if (file.size <= 0) return `${file.name} is empty.`;
    if (file.size > MAX_FILE_BYTES) return `${file.name} is larger than 50 MB.`;
    return null;
  }

  function makeLocalAttachment(file) {
    return {
      localId: uid(),
      file,
      name: file.name,
      type: file.type || 'application/octet-stream',
      size: file.size,
      status: 'queued',
      progress: 0,
      server: null,
      controller: null,
      previewUrl: file.type?.startsWith('image/') ? URL.createObjectURL(file) : null,
      promise: null,
    };
  }

  function addRemoteReference(file, { imageReference = false } = {}) {
    if (!file?.id) return;
    const existing = state.attachments.find(item => item.server?.id === file.id);
    if (existing) return;
    state.attachments.push({
      localId: uid(), file: null, name: file.name || 'Image', type: file.type || 'image/png',
      size: file.size || 0, status: 'ready', progress: 100, server: file, previewUrl: file.url || null,
      imageReference,
    });
    renderAttachmentTray();
  }

  function safeImageRecovery(value) {
    if (value?.action !== 'revise_image_request' || value?.usageRestored !== true) return null;
    return {action: 'revise_image_request', usageRestored: true};
  }

  function sortedReferenceIds(files) {
    return (files || [])
      .map(item => item?.server?.id || item?.id)
      .filter(Boolean)
      .map(String)
      .sort();
  }

  function unchangedRecoveredImageRequest(prompt, readyFiles) {
    const recovery = state.imageRecovery;
    if (!recovery || state.tool !== 'image') return false;
    if (String(prompt || '').trim() !== recovery.prompt) return false;
    const currentIds = sortedReferenceIds(readyFiles);
    return currentIds.length === recovery.fileIds.length
      && currentIds.every((value, index) => value === recovery.fileIds[index]);
  }

  async function normalizeInputFile(file) {
    const type = String(file?.type || '').toLowerCase();
    const heic = type.includes('heic') || type.includes('heif') || /\.hei[cf]$/i.test(file?.name || '');
    if (!heic) return file;
    try {
      const bitmap = await createImageBitmap(file);
      const scale = Math.min(1, 4096 / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const context = canvas.getContext('2d', {alpha: false});
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close?.();
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .94));
      if (!blob) return file;
      const stem = String(file.name || 'photo').replace(/\.hei[cf]$/i, '');
      return new File([blob], `${stem}.jpg`, {type: 'image/jpeg', lastModified: file.lastModified || Date.now()});
    } catch (_) {
      try {
        const objectUrl = URL.createObjectURL(file);
        const image = new Image();
        image.src = objectUrl;
        await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; });
        const scale = Math.min(1, 4096 / Math.max(image.naturalWidth, image.naturalHeight));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
        canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
        canvas.getContext('2d', {alpha:false}).drawImage(image, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(objectUrl);
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .94));
        if (!blob) return file;
        const stem = String(file.name || 'photo').replace(/\.hei[cf]$/i, '');
        return new File([blob], `${stem}.jpg`, {type:'image/jpeg', lastModified:file.lastModified || Date.now()});
      } catch (_) {
        return file;
      }
    }
  }

  async function addFiles(fileList) {
    const incoming = [...(fileList || [])];
    if (!incoming.length) return;
    const available = Math.max(0, MAX_FILES - state.attachments.length);
    if (!available) {
      show(`You can attach up to ${MAX_FILES} files to one message.`, 'warning');
      return;
    }
    for (const original of incoming.slice(0, available)) {
      const file = await normalizeInputFile(original);
      const issue = validateFile(file);
      if (issue) {
        show(issue, 'error');
        continue;
      }
      const item = makeLocalAttachment(file);
      state.attachments.push(item);
      item.promise = uploadItem(item);
    }
    renderAttachmentTray();
  }

  async function uploadItem(item) {
    item.status = 'signing';
    renderAttachmentTray();
    try {
      const signed = await api('/api/files/sign-upload', {
        method: 'POST',
        body: JSON.stringify({
          name: item.name, type: item.type, size: item.size,
          chatId: window.currentChatId || null,
        }),
      });
      item.server = signed.file;
      item.status = 'uploading';
      item.progress = 1;
      renderAttachmentTray();
      let uploadError = null;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          if (item.size > 6 * 1024 * 1024 && signed.uploadToken && signed.resumableUrl && signed.uploadPath) {
            await uploadResumable(item, signed);
          } else {
            await uploadSigned(item, signed.uploadUrl, signed.uploadToken);
          }
          uploadError = null;
          break;
        } catch (error) {
          uploadError = error;
          if (error?.name === 'AbortError' || attempt === 1) throw error;
          await new Promise(resolve => setTimeout(resolve, 700));
        }
      }
      if (uploadError) throw uploadError;
      const completed = await api(`/api/files/${encodeURIComponent(item.server.id)}/complete`, {method: 'POST', body: '{}'});
      item.server = completed.file;
      item.status = 'ready';
      item.progress = 100;
      renderAttachmentTray();
      return item.server;
    } catch (error) {
      item.status = error?.name === 'AbortError' ? 'cancelled' : 'failed';
      item.error = error.message || 'Upload failed.';
      renderAttachmentTray();
      if (item.status === 'failed') show(`${item.name}: ${item.error}`, 'error');
      throw error;
    }
  }

  function uploadSigned(item, uploadUrl, token) {
    return new Promise((resolve, reject) => {
      let url = String(uploadUrl || '');
      if (token && !/[?&]token=/.test(url)) url += `${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`;
      const xhr = new XMLHttpRequest();
      item.controller = {abort: () => xhr.abort()};
      xhr.open('PUT', url, true);
      xhr.setRequestHeader('x-upsert', 'false');
      xhr.upload.addEventListener('progress', event => {
        if (!event.lengthComputable) return;
        item.progress = Math.max(1, Math.min(99, Math.round((event.loaded / event.total) * 100)));
        renderAttachmentTray();
      });
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(new Error(`Upload failed (${xhr.status}).`));
      });
      xhr.addEventListener('error', () => reject(new Error('Network error during upload.')));
      xhr.addEventListener('abort', () => reject(Object.assign(new Error('Upload cancelled.'), {name: 'AbortError'})));
      const form = new FormData();
      form.append('cacheControl', '3600');
      form.append('file', item.file);
      xhr.send(form);
    });
  }


  function tusMeta(value) {
    const bytes = new TextEncoder().encode(String(value || ''));
    let binary = '';
    bytes.forEach(byte => { binary += String.fromCharCode(byte); });
    return btoa(binary);
  }

  async function tusOffset(url, token) {
    const response = await fetch(url, {
      method: 'HEAD',
      headers: {'Tus-Resumable': '1.0.0', 'x-signature': token},
    });
    if (!response.ok) throw new Error(`Could not resume upload (${response.status}).`);
    return Number(response.headers.get('Upload-Offset') || 0);
  }

  async function uploadTusChunk(item, url, token, offset, chunk) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      item.controller = {abort: () => xhr.abort()};
      xhr.open('PATCH', url, true);
      xhr.setRequestHeader('Tus-Resumable', '1.0.0');
      xhr.setRequestHeader('Upload-Offset', String(offset));
      xhr.setRequestHeader('Content-Type', 'application/offset+octet-stream');
      xhr.setRequestHeader('x-signature', token);
      xhr.upload.addEventListener('progress', event => {
        if (!event.lengthComputable) return;
        const sent = offset + event.loaded;
        item.progress = Math.max(1, Math.min(99, Math.round((sent / item.size) * 100)));
        renderAttachmentTray();
      });
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(Number(xhr.getResponseHeader('Upload-Offset') || offset + chunk.size));
        else reject(new Error(`Chunk upload failed (${xhr.status}).`));
      });
      xhr.addEventListener('error', () => reject(new Error('Network error during resumable upload.')));
      xhr.addEventListener('abort', () => reject(Object.assign(new Error('Upload cancelled.'), {name:'AbortError'})));
      xhr.send(chunk);
    });
  }

  async function uploadResumable(item, signed) {
    const metadata = [
      ['bucketName', signed.uploadBucket],
      ['objectName', signed.uploadPath],
      ['contentType', item.type || 'application/octet-stream'],
      ['cacheControl', '3600'],
    ].map(([key,value]) => `${key} ${tusMeta(value)}`).join(',');
    const create = await fetch(signed.resumableUrl, {
      method: 'POST',
      headers: {
        'Tus-Resumable': '1.0.0',
        'Upload-Length': String(item.size),
        'Upload-Metadata': metadata,
        'x-signature': signed.uploadToken,
        'x-upsert': 'false',
      },
    });
    if (!create.ok) throw new Error(`Could not start resumable upload (${create.status}).`);
    let location = create.headers.get('Location');
    if (!location) throw new Error('Storage did not return a resumable upload location.');
    location = new URL(location, signed.resumableUrl).href;
    const chunkSize = 6 * 1024 * 1024;
    let offset = Number(create.headers.get('Upload-Offset') || 0);
    while (offset < item.size) {
      const chunk = item.file.slice(offset, Math.min(item.size, offset + chunkSize));
      let uploaded = false;
      for (const delay of [0, 700, 1800]) {
        if (delay) await new Promise(resolve => setTimeout(resolve, delay));
        try {
          offset = await uploadTusChunk(item, location, signed.uploadToken, offset, chunk);
          uploaded = true;
          break;
        } catch (error) {
          if (error?.name === 'AbortError') throw error;
          try { offset = await tusOffset(location, signed.uploadToken); } catch (_) {}
          if (offset >= item.size) { uploaded = true; break; }
        }
      }
      if (!uploaded) throw new Error('The resumable upload could not continue.');
    }
  }

  function removeAttachment(localId) {
    const index = state.attachments.findIndex(item => item.localId === localId);
    if (index < 0) return;
    const [item] = state.attachments.splice(index, 1);
    item.controller?.abort?.();
    if (item.previewUrl?.startsWith('blob:')) URL.revokeObjectURL(item.previewUrl);
    renderAttachmentTray();
  }

  function renderAttachmentTray() {
    const tray = $('#filePreview');
    if (!tray) return;
    tray.classList.add('crump50-attachment-tray');
    tray.hidden = !state.attachments.length;
    tray.style.display = state.attachments.length ? 'flex' : 'none';
    const liveIds = new Set(state.attachments.map(item => item.localId));
    $$('[data-crump50-attachment-id]', tray).forEach(card => {
      if (!liveIds.has(card.dataset.crump50AttachmentId)) card.remove();
    });

    state.attachments.forEach((item, index) => {
      let card = $$('[data-crump50-attachment-id]', tray)
        .find(node => node.dataset.crump50AttachmentId === item.localId);
      if (!card) {
        card = document.createElement('article');
        card.dataset.crump50AttachmentId = item.localId;
        const visual = document.createElement('div');
        visual.className = 'crump50-upload-visual';
        if (item.previewUrl && String(item.type).startsWith('image/')) {
          const img = document.createElement('img');
          img.src = item.previewUrl;
          img.alt = '';
          img.decoding = 'async';
          visual.appendChild(img);
        } else {
          visual.innerHTML = iconFor(fileKind(item));
        }
        const copy = document.createElement('div');
        copy.className = 'crump50-upload-copy';
        const name = document.createElement('strong');
        const meta = document.createElement('span');
        meta.dataset.crump50UploadMeta = 'true';
        const progress = document.createElement('i');
        progress.className = 'crump50-upload-progress';
        copy.append(name, meta, progress);
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'crump50-upload-remove';
        remove.textContent = '×';
        remove.addEventListener('click', () => removeAttachment(item.localId));
        card.append(visual, copy, remove);
      }
      card.className = `crump50-upload-card is-${item.status}`;
      $('strong', card).textContent = item.name;
      $('[data-crump50-upload-meta]', card).textContent = item.status === 'ready'
        ? formatBytes(item.size)
        : item.status === 'failed'
          ? 'Upload failed'
          : `${item.progress || 0}%`;
      $('.crump50-upload-progress', card).style.setProperty('--progress', `${item.progress || 0}%`);
      const remove = $('.crump50-upload-remove', card);
      remove.setAttribute('aria-label', `Remove ${item.name}`);
      const position = tray.children[index];
      if (position !== card) tray.insertBefore(card, position || null);
    });
  }

  function activeToolLabel() {
    if (state.tool === 'image') return `Create image · ${state.imageAspect}`;
    if (state.tool === 'document' && state.documentPurpose === 'resume') return 'Create résumé · DOCX';
    if (state.tool === 'document') return `Create ${String(state.documentFormat || 'docx').toUpperCase()}`;
    if (state.tool === 'web') return 'Web search';
    if (state.tool === 'code') return 'Code';
    return null;
  }

  function renderToolChip() {
    let host = $('#crump50ToolChipHost');
    const area = $('.input-area');
    if (!area) return;
    if (!host) {
      host = document.createElement('div');
      host.id = 'crump50ToolChipHost';
      host.className = 'crump50-tool-chip-host';
      area.insertBefore(host, $('.input-container', area));
    }
    host.replaceChildren();
    const label = activeToolLabel();
    if (!label) return;
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'crump50-tool-chip';
    chip.innerHTML = `<span>${label}</span><i aria-hidden="true">×</i>`;
    chip.addEventListener('click', () => {
      if (state.tool === 'image') state.imageRecovery = null;
      state.tool = null;
      state.documentFormat = null;
      state.documentPurpose = null;
      renderToolChip();
    });
    host.appendChild(chip);
  }

  function closeMenu() {
    state.menu?.remove();
    state.menu = null;
    document.body.classList.remove('crump50-sheet-open');
  }

  function menuButton(icon, title, subtitle, handler) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'crump50-menu-row';
    button.innerHTML = `<span class="crump50-menu-icon">${icon}</span><span><strong>${title}</strong><small>${subtitle}</small></span><b>›</b>`;
    button.addEventListener('click', handler);
    return button;
  }

  function showAttachMenu() {
    closeMenu();
    const sheet = document.createElement('section');
    sheet.className = 'crump50-sheet crump50-attach-sheet';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-label', 'Add to conversation');
    const head = document.createElement('div');
    head.className = 'crump50-sheet-head';
    head.innerHTML = '<div><span>ADD TO CRUMP</span><strong>Bring anything into the conversation.</strong></div>';
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'crump50-sheet-close'; close.textContent = '×'; close.addEventListener('click', closeMenu);
    head.appendChild(close);
    const rows = document.createElement('div');
    rows.className = 'crump50-menu-list';
    rows.append(
      menuButton(iconFor('file'), 'Photos & files', 'Images, PDF, Word, Excel, PowerPoint, text and data', () => { closeMenu(); $('#fileInput')?.click(); }),
      menuButton(iconFor('image'), 'Take a photo', 'Use your camera and ask Crump what he sees', () => { closeMenu(); openCamera(); }),
      menuButton('<svg viewBox="0 0 24 24"><path d="M12 3v18M3 12h18"/><path d="m5 5 14 14M19 5 5 19" opacity=".45"/></svg>', 'Create image', 'Generate or edit with GPT Image', () => showImageOptions()),
      menuButton('<svg viewBox="0 0 24 24"><path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4M9.5 12h5M9.5 15h5"/></svg>', 'Create document', 'Word, PDF, PowerPoint, Excel, Markdown', () => showDocumentOptions()),
      menuButton('<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c2.5 2.5 3.5 5.1 3.5 8S14.5 17.5 12 20M12 4C9.5 6.5 8.5 9.1 8.5 12S9.5 17.5 12 20"/></svg>', 'Search the web', 'Use current information when the answer depends on now', () => { state.tool = 'web'; closeMenu(); renderToolChip(); focusComposer(); }),
      menuButton('<svg viewBox="0 0 24 24"><path d="m8.5 8-4 4 4 4M15.5 8l4 4-4 4M14 5l-4 14"/></svg>', 'Code', 'Debug, explain, design, or build software', () => { state.tool = 'code'; closeMenu(); renderToolChip(); focusComposer(); }),
    );
    sheet.append(head, rows);
    document.body.appendChild(sheet);
    state.menu = sheet;
    document.body.classList.add('crump50-sheet-open');
    requestAnimationFrame(() => sheet.classList.add('is-visible'));
  }

  function segmented(options, selected, onSelect) {
    const wrap = document.createElement('div');
    wrap.className = 'crump50-segmented';
    options.forEach(([value, label]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = selected === value ? 'is-active' : '';
      button.textContent = label;
      button.addEventListener('click', () => onSelect(value));
      wrap.appendChild(button);
    });
    return wrap;
  }

  function showImageOptions() {
    closeMenu();
    const sheet = document.createElement('section');
    sheet.className = 'crump50-sheet crump50-options-sheet';
    sheet.innerHTML = '<div class="crump50-sheet-head"><div><span>IMAGE STUDIO</span><strong>Build the frame before you describe it.</strong></div></div>';
    const close = document.createElement('button'); close.type = 'button'; close.className = 'crump50-sheet-close'; close.textContent = '×'; close.addEventListener('click', closeMenu); $('.crump50-sheet-head', sheet).appendChild(close);
    const body = document.createElement('div'); body.className = 'crump50-options-body';
    const aspectLabel = document.createElement('label'); aspectLabel.textContent = 'Aspect ratio';
    let aspectControl;
    const rebuildAspect = () => {
      aspectControl?.replaceWith(aspectControl = segmented([['square','Square'],['portrait','Portrait'],['landscape','Landscape']], state.imageAspect, value => { state.imageAspect = value; rebuildAspect(); }));
    };
    aspectControl = segmented([['square','Square'],['portrait','Portrait'],['landscape','Landscape']], state.imageAspect, value => { state.imageAspect = value; rebuildAspect(); });
    const qualityLabel = document.createElement('label'); qualityLabel.textContent = 'Quality';
    let qualityControl;
    const rebuildQuality = () => {
      qualityControl?.replaceWith(qualityControl = segmented([['medium','Balanced'],['high','Highest']], state.imageQuality, value => { state.imageQuality = value; rebuildQuality(); }));
    };
    qualityControl = segmented([['medium','Balanced'],['high','Highest']], state.imageQuality, value => { state.imageQuality = value; rebuildQuality(); });
    const activate = document.createElement('button'); activate.type = 'button'; activate.className = 'crump50-primary-action'; activate.textContent = 'Use Image Studio';
    activate.addEventListener('click', () => { state.imageRecovery = null; state.tool = 'image'; closeMenu(); renderToolChip(); focusComposer('Describe the image you want…'); });
    body.append(aspectLabel, aspectControl, qualityLabel, qualityControl, activate);
    sheet.appendChild(body); document.body.appendChild(sheet); state.menu = sheet; document.body.classList.add('crump50-sheet-open'); requestAnimationFrame(() => sheet.classList.add('is-visible'));
  }

  function showDocumentOptions() {
    closeMenu();
    const sheet = document.createElement('section');
    sheet.className = 'crump50-sheet crump50-options-sheet';
    sheet.innerHTML = '<div class="crump50-sheet-head"><div><span>DOCUMENT STUDIO</span><strong>Start with the outcome. Crump will structure the file.</strong></div></div>';
    const close = document.createElement('button'); close.type = 'button'; close.className = 'crump50-sheet-close'; close.textContent = '×'; close.addEventListener('click', closeMenu); $('.crump50-sheet-head', sheet).appendChild(close);
    const outcomeLabel = document.createElement('div'); outcomeLabel.className = 'crump50-option-label'; outcomeLabel.textContent = 'What are you making?';
    const outcomes = document.createElement('div'); outcomes.className = 'crump50-outcome-grid';
    [
      ['docx','ESSAY · REPORT','Academic & professional writing','Describe the topic, audience, length, requirements, and citation style…',''],
      ['docx','RÉSUMÉ · CV','ATS-friendly and fact-grounded','Share your real experience, target role, skills, and achievements…','resume'],
      ['pptx','PRESENTATION','A clear, decision-ready narrative','Describe the audience, objective, key evidence, and desired next step…',''],
      ['xlsx','SPREADSHEET','Structured inputs, formulas, and outputs','Describe the data, assumptions, calculations, and decisions this workbook should support…',''],
      ['docx','MANUSCRIPT','Persistent, chapter-by-chapter work','Describe the book, audience, voice, target length, and what you already know…',''],
    ].forEach(([format, eyebrow, label, placeholder, purpose]) => {
      const button = document.createElement('button'); button.type = 'button';
      button.innerHTML = `<span>${eyebrow}</span><strong>${label}</strong><b>›</b>`;
      button.addEventListener('click', () => { state.tool = 'document'; state.documentFormat = format; state.documentPurpose = purpose || null; closeMenu(); renderToolChip(); focusComposer(placeholder); });
      outcomes.appendChild(button);
    });
    const formatLabel = document.createElement('div'); formatLabel.className = 'crump50-option-label'; formatLabel.textContent = 'Or choose a file format';
    const grid = document.createElement('div'); grid.className = 'crump50-format-grid';
    [['docx','Word','DOCX'],['pdf','PDF','PDF'],['pptx','PowerPoint','PPTX'],['xlsx','Excel','XLSX'],['md','Markdown','MD'],['txt','Text','TXT']].forEach(([value,label,badge]) => {
      const b = document.createElement('button'); b.type = 'button'; b.innerHTML = `<span>${badge}</span><strong>${label}</strong>`;
      b.addEventListener('click', () => { state.tool = 'document'; state.documentFormat = value; state.documentPurpose = null; closeMenu(); renderToolChip(); focusComposer(`Describe the ${label} document you want…`); });
      grid.appendChild(b);
    });
    sheet.append(outcomeLabel, outcomes, formatLabel, grid); document.body.appendChild(sheet); state.menu = sheet; document.body.classList.add('crump50-sheet-open'); requestAnimationFrame(() => sheet.classList.add('is-visible'));
  }

  function openCamera() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = 'image/*'; input.capture = 'environment';
    input.addEventListener('change', () => addFiles(input.files), {once: true});
    input.click();
  }

  function focusComposer(placeholder) {
    const input = $('#userInput');
    if (!input) return;
    if (placeholder) input.placeholder = placeholder;
    input.focus({preventScroll: true});
  }

  async function waitForUploads() {
    const pending = state.attachments.filter(item => item.promise && !['ready','failed','cancelled'].includes(item.status));
    if (pending.length) await Promise.all(pending.map(item => item.promise));
    const failed = state.attachments.filter(item => item.status === 'failed');
    if (failed.length) throw new Error('Remove or retry failed uploads before sending.');
    return state.attachments.filter(item => item.status === 'ready' && item.server?.id);
  }

  function buildRequestBody(chat, userMessage, readyFiles) {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const body = {
      chatId: chat.id || chat.chat_id,
      messageId: userMessage.id,
      message: userMessage.content || '',
      history: (chat.messages || []).map(item => ({
        role: item.role,
        content: item.content || '',
        fileRefs: [
          ...(Array.isArray(item.files) ? item.files.map(file => file?.id).filter(Boolean) : []),
          ...(item.imageFile?.id ? [item.imageFile.id] : []),
          ...(item.artifact?.id ? [item.artifact.id] : []),
        ],
      })),
      currentDateTime: {
        iso: new Date().toISOString(), timezone,
        date: new Date().toLocaleDateString('en-US', {dateStyle: 'full', timeZone: timezone}),
        time: new Date().toLocaleTimeString('en-US', {timeStyle: 'medium', timeZone: timezone}),
      },
      fileRefs: readyFiles.map(item => item.server.id),
    };
    if (state.tool === 'web') body.needsSearch = true;
    if (state.tool === 'code') body.taskType = 'code';
    if (state.tool === 'image') {
      body.creativeTool = 'image'; body.imageAspect = state.imageAspect; body.imageQuality = state.imageQuality;
      body.imageUseReference = readyFiles.some(item => String(item.server?.type || '').startsWith('image/'));
    }
    if (state.tool === 'document' && state.documentFormat) body.artifactFormat = state.documentFormat;
    if (state.tool === 'document' && state.documentPurpose) body.artifactPurpose = state.documentPurpose;
    if (userMessage.requestMeta && typeof userMessage.requestMeta === 'object') Object.assign(body, userMessage.requestMeta);
    return body;
  }

  async function ensureUsage() {
    if (!window.CrumpChatTransport) throw new Error('Message delivery is still loading. Try again.');
    return window.CrumpChatTransport.ensureUsage();
  }

  function syncCompletedReplyInBackground() {
    try {
      void Promise.resolve(window.syncChatsFromServer?.()).catch(() => {
        console.warn('Completed reply sync deferred; background sync will retry.');
      });
    } catch (_) {
      console.warn('Completed reply sync deferred; background sync will retry.');
    }
  }

  function runCompletedCreationHandoffInBackground(data) {
    try {
      let pending = null;
      if (data.manuscriptWorkspace?.autoOpen) {
        pending = window.CrumpProduct53?.handleCreationHandoff?.({kind:'manuscript', workspace:data.manuscriptWorkspace});
      } else if (data.creationHandoff) {
        pending = window.CrumpProduct53?.handleCreationHandoff?.(data.creationHandoff);
      } else {
        return;
      }
      void Promise.resolve(pending).catch(() => {
        console.warn('Completed creation handoff deferred; the saved reply remains available.');
      });
    } catch (_) {
      console.warn('Completed creation handoff deferred; the saved reply remains available.');
    }
  }

  async function completeReply(chat, userMessage, data) {
    chat = currentChat() || chat;
    const finalUser = chat.messages.find(item => item.id === userMessage.id) || userMessage;
    finalUser.deliveryStatus = 'seen'; finalUser.replyStatus = 'replied'; finalUser.replyError = null;
    delete finalUser.replyErrorCode;
    delete finalUser.replyRecovery;
    const serverAssistant = data.assistantMessage && typeof data.assistantMessage === 'object'
      ? data.assistantMessage
      : {};
    const assistant = {
      ...serverAssistant,
      id: serverAssistant.id || uid(),
      role: 'assistant',
      content: serverAssistant.content ?? data.response ?? '',
      timestamp: serverAssistant.timestamp || new Date().toISOString(),
      origin: 'reply',
      inReplyTo: userMessage.id,
    };
    for (const key of ['imageUrl', 'imagePrompt', 'imageAspect', 'imageFile', 'artifact', 'artifactRecovery', 'projectAttachments', 'manuscriptWorkspace', 'creationHandoff']) {
      if (assistant[key] == null && data[key] != null) assistant[key] = data[key];
    }
    const existingIndex = chat.messages.findIndex(item => item.role === 'assistant' && item.inReplyTo === userMessage.id);
    if (existingIndex >= 0) chat.messages[existingIndex] = {...chat.messages[existingIndex], ...assistant};
    else chat.messages.push(assistant);
    if (data.conversationRevision) {
      chat.revision = Math.max(Number(chat.revision || 1), Number(data.conversationRevision || 1));
    }
    saveAndRender(chat);
    window.CrumpPresence?.stop?.(); window.CrumpPresence?.haptic?.('success');
    runCompletedCreationHandoffInBackground(data);
    syncCompletedReplyInBackground();
    setTimeout(() => window.crumpScrollManager?.scrollToBottom?.({behavior: 'smooth'}), 80);
  }

  async function applyCompletedReplySafely(chat, userMessage, data) {
    try {
      await completeReply(chat, userMessage, data);
      return true;
    } catch (_) {
      try { window.CrumpPresence?.stop?.(); } catch (_) {}
      try {
        console.warn('Completed reply presentation deferred; the saved reply remains authoritative.');
      } catch (_) {}
      try {
        show(
          'Your reply was saved, but this screen could not finish updating. Refresh this conversation to load the saved reply.',
          'warning',
        );
      } catch (_) {}
      return false;
    }
  }

  async function studioSendMessage() {
    if (state.sending) return;
    const input = $('#userInput');
    const text = String(input?.value || '').trim();
    if (!text && !state.attachments.length) return;
    state.sending = true;
    document.body.classList.add('crump50-sending');
    let userMessage = null;
    try {
      const ready = await waitForUploads();
      if (unchangedRecoveredImageRequest(text, ready)) {
        show('Change the wording or reference image before sending this request again.', 'info');
        return;
      }
      await ensureUsage();
      let fresh = currentChat() || window.ensureCurrentChat?.();
      if (!fresh) throw new Error('Crump could not start a new conversation. Try again.');
      const now = new Date().toISOString();
      userMessage = {
        id: uid(), role: 'user', content: text, timestamp: now,
        deliveryStatus: 'sending', replyStatus: 'pending',
        files: ready.map(item => item.server),
        requestMeta: {
          ...(state.tool === 'web' ? {needsSearch:true} : {}),
          ...(state.tool === 'code' ? {taskType:'code'} : {}),
          ...(state.tool === 'image' ? {creativeTool:'image', imageAspect:state.imageAspect, imageQuality:state.imageQuality, imageUseReference:ready.some(item => String(item.server?.type || '').startsWith('image/'))} : {}),
          ...(state.tool === 'document' && state.documentFormat ? {artifactFormat:state.documentFormat} : {}),
          ...(state.tool === 'document' && state.documentPurpose ? {artifactPurpose:state.documentPurpose} : {}),
        },
      };
      state.imageRecovery = null;
      fresh.messages.push(userMessage);
      if (fresh.messages.length === 1 && text) fresh.title = text.slice(0, 50) + (text.length > 50 ? '…' : '');
      saveAndRender(fresh);
      window.crumpScrollManager?.scrollToBottom?.({force: true});
      input.value = ''; input.style.height = 'auto';
      const body = buildRequestBody(currentChat() || fresh, userMessage, ready);
      state.attachments = [];
      renderAttachmentTray();
      const sentTool = state.tool;
      state.tool = null; state.documentFormat = null; state.documentPurpose = null; renderToolChip();

      const sync = await window.syncChatsToServer?.();
      if (sync && sync.success === false) throw Object.assign(new Error('This message is waiting to sync.'), {quiet: true});
      fresh = currentChat() || fresh;
      const liveUser = fresh.messages.find(item => item.id === userMessage.id) || userMessage;
      liveUser.deliveryStatus = 'delivered';
      saveAndRender(fresh);

      const ack = await window.CrumpChatTransport.acknowledge({
        chatId: fresh.id || fresh.chat_id, messageId: userMessage.id, message: text,
        fileTypes: ready.map(item => item.server.type),
      });
      fresh = currentChat() || fresh;
      const acknowledged = fresh.messages.find(item => item.id === userMessage.id) || liveUser;
      Object.assign(acknowledged, {deliveryStatus: 'seen', deliveredAt: ack.deliveredAt, seenAt: ack.seenAt, replyStatus: 'processing', replyError: null});
      delete acknowledged.replyErrorCode;
      delete acknowledged.replyRecovery;
      saveAndRender(fresh);
      window.CrumpPresence?.start?.(sentTool === 'image' ? 'creating' : ready.length ? 'reading' : ack.activity || 'thinking');

      const data = await window.CrumpChatTransport.send(body);
      await applyCompletedReplySafely(fresh, userMessage, data);
    } catch (error) {
      window.CrumpPresence?.stop?.();
      const fresh = currentChat();
      const target = fresh?.messages?.find(item => item.id === userMessage?.id);
      if (target) {
        target.deliveryStatus = error.quiet ? 'queued' : (target.deliveryStatus === 'sending' ? 'failed' : target.deliveryStatus);
        target.replyStatus = error.quiet ? 'pending' : 'failed';
        target.replyError = error.quiet ? null : (error.message || 'Reply failed.');
        if (!error.quiet && error.code === 'IMAGE_SAFETY_REJECTED') {
          target.replyErrorCode = 'IMAGE_SAFETY_REJECTED';
          const recovery = safeImageRecovery(error.recovery || error.data?.recovery);
          if (recovery) target.replyRecovery = recovery;
          else delete target.replyRecovery;
        } else if (!error.quiet) {
          delete target.replyErrorCode;
          delete target.replyRecovery;
        }
        saveAndRender(fresh);
      }
      if (!error.quiet) show(error.message || 'Crump could not complete that request.', 'error');
      window.CrumpPresence?.haptic?.('error');
    } finally {
      state.sending = false;
      document.body.classList.remove('crump50-sending');
      focusComposer();
    }
  }

  async function retryMessage(id) {
    if (state.sending) return;
    let chat = currentChat();
    let message = chat?.messages?.find(item => item.id === id && item.role === 'user');
    if (!chat || !message) return;
    if (message.replyErrorCode === 'IMAGE_SAFETY_REJECTED') {
      reviseImageMessage(id);
      return;
    }
    state.sending = true;
    document.body.classList.add('crump50-sending');
    try {
      window.CrumpPresence?.start?.('thinking');
      const recovered = await window.CrumpChatTransport?.recover?.(id);
      if (recovered) {
        await applyCompletedReplySafely(chat, message, recovered);
        return;
      }
      window.CrumpPresence?.stop?.();
      await ensureUsage();
      const ready = (message.files || []).filter(file => file?.id).map(file => ({status:'ready', server:file, name:file.name, type:file.type, size:file.size}));
      message.deliveryStatus = 'sending'; message.replyStatus = 'pending'; message.replyError = null;
      delete message.replyErrorCode;
      delete message.replyRecovery;
      saveAndRender(chat);
      await window.syncChatsToServer?.();
      chat = currentChat() || chat;
      message = chat.messages.find(item => item.id === id) || message;
      const ack = await window.CrumpChatTransport.acknowledge({
        chatId:chat.id || chat.chat_id, messageId:id, message:message.content || '', fileTypes:ready.map(item => item.server.type),
      });
      Object.assign(message, {deliveryStatus:'seen', deliveredAt:ack.deliveredAt, seenAt:ack.seenAt, replyStatus:'processing'});
      saveAndRender(chat);
      window.CrumpPresence?.start?.(ready.length ? 'reading' : ack.activity || 'thinking');
      const body = buildRequestBody(chat, message, ready);
      const data = await window.CrumpChatTransport.send(body);
      await applyCompletedReplySafely(chat, message, data);
    } catch (error) {
      window.CrumpPresence?.stop?.();
      chat=currentChat() || chat; message=chat?.messages?.find(item => item.id===id) || message;
      if (message) {
        message.replyStatus='failed'; message.replyError=error.message || 'Reply failed.';
        if (error.code === 'IMAGE_SAFETY_REJECTED') {
          message.replyErrorCode = 'IMAGE_SAFETY_REJECTED';
          const recovery = safeImageRecovery(error.recovery || error.data?.recovery);
          if (recovery) message.replyRecovery = recovery;
        }
        saveAndRender(chat);
      }
      show(error.message || 'Retry failed.', 'error');
    } finally {
      state.sending=false; document.body.classList.remove('crump50-sending');
    }
  }

  function reviseImageMessage(id) {
    if (state.sending) return;
    const chat = currentChat();
    const message = chat?.messages?.find(item => item.id === id && item.role === 'user');
    if (!message || message.replyErrorCode !== 'IMAGE_SAFETY_REJECTED') return;
    const recovery = safeImageRecovery(message.replyRecovery);
    if (!recovery) {
      show('This request needs a changed prompt or reference image before it can be sent again.', 'warning');
      return;
    }
    const input = $('#userInput');
    if (!input) return;
    const alreadyRestoring = state.imageRecovery?.messageId === id;
    if (!alreadyRestoring && (String(input.value || '').trim() || state.attachments.length)) {
      show('Finish or clear the current draft before revising this image request.', 'warning');
      focusComposer();
      return;
    }

    const references = (message.files || []).filter(file =>
      file?.id && String(file.type || file.mime_type || '').toLowerCase().startsWith('image/')
    );
    references.forEach(file => addRemoteReference(file, {imageReference: true}));
    const meta = message.requestMeta && typeof message.requestMeta === 'object' ? message.requestMeta : {};
    state.imageAspect = ['square', 'portrait', 'landscape'].includes(meta.imageAspect) ? meta.imageAspect : 'square';
    state.imageQuality = ['medium', 'high'].includes(meta.imageQuality) ? meta.imageQuality : 'medium';
    state.tool = 'image';
    state.imageRecovery = {
      messageId: id,
      prompt: String(message.content || '').trim(),
      fileIds: references.map(file => String(file.id)).sort(),
    };
    input.value = message.content || '';
    input.dispatchEvent(new Event('input', {bubbles: true}));
    renderToolChip();
    focusComposer('Revise the prompt or reference image before sending…');
    show('The failed attempt was refunded. Change the wording or reference image before sending again.', 'info');
  }

  function replaceLegacyControls() {
    const oldAttach = $('#attachBtn');
    if (oldAttach && oldAttach.dataset.crump50 !== 'true') {
      const button = oldAttach.cloneNode(false);
      button.id = 'attachBtn'; button.dataset.crump50 = 'true'; button.className = 'crump50-plus';
      button.setAttribute('aria-label', 'Add to conversation'); button.title = 'Add'; button.innerHTML = '<span aria-hidden="true">+</span>';
      oldAttach.replaceWith(button);
      button.addEventListener('click', showAttachMenu);
    }
    const oldInput = $('#fileInput');
    if (oldInput && oldInput.dataset.crump50 !== 'true') {
      const input = oldInput.cloneNode(false);
      input.id = 'fileInput'; input.dataset.crump50 = 'true'; input.type = 'file'; input.multiple = true; input.accept = ACCEPT; input.hidden = true;
      oldInput.replaceWith(input);
      input.addEventListener('change', event => { addFiles(event.target.files); event.target.value = ''; });
    }
    const oldSend = $('#sendButton');
    if (oldSend && oldSend.dataset.crump50 !== 'true') {
      const button = oldSend.cloneNode(false);
      button.id = 'sendButton'; button.dataset.crump50 = 'true'; button.className = 'crump50-send'; button.setAttribute('aria-label', 'Send message');
      button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6.5 10.5 12 5l5.5 5.5"/></svg>';
      oldSend.replaceWith(button); button.addEventListener('click', studioSendMessage);
    }
    const input = $('#userInput');
    if (input) {
      input.placeholder = `Message ${window.getAssistantName?.() || 'Crump'}`;
      input.maxLength = 20000;
    }
    window.sendMessage = studioSendMessage;
    window.retryMessage = retryMessage;
    window.reviseImageMessage = reviseImageMessage;
  }

  function installPasteAndDrop() {
    const input = $('#userInput');
    if (input && input.dataset.crump50Paste !== 'true') {
      input.dataset.crump50Paste = 'true';
      input.addEventListener('paste', event => {
        const files = [...(event.clipboardData?.files || [])].filter(file => file.type.startsWith('image/'));
        if (files.length) addFiles(files);
      });
    }
    if (document.body.dataset.crump50Drop === 'true') return;
    document.body.dataset.crump50Drop = 'true';
    let overlay = null;
    let depth = 0;
    const remove = () => { overlay?.remove(); overlay = null; depth = 0; };
    document.addEventListener('dragenter', event => {
      if (![...(event.dataTransfer?.types || [])].includes('Files')) return;
      depth += 1; event.preventDefault();
      if (!overlay) {
        overlay = document.createElement('div'); overlay.className = 'crump50-drop-overlay';
        overlay.innerHTML = '<div><span>+</span><strong>Drop files into Crump</strong><small>They stay private to your account.</small></div>';
        document.body.appendChild(overlay);
      }
    });
    document.addEventListener('dragover', event => { if (overlay) event.preventDefault(); });
    document.addEventListener('dragleave', () => { depth -= 1; if (depth <= 0) remove(); });
    document.addEventListener('drop', event => { if (!overlay) return; event.preventDefault(); const files = event.dataTransfer?.files; remove(); addFiles(files); });
  }

  function showFileViewer(file) {
    const url = file?.id ? `/api/files/${encodeURIComponent(file.id)}/content` : String(file?.url || '');
    if (!url) return false;
    const type = String(file?.type || '').toLowerCase();
    if (type.startsWith('image/')) {
      showLightbox(file, url);
      return true;
    }

    state.lightbox?.remove();
    const box = document.createElement('section');
    box.className = 'crump50-lightbox crump50-file-viewer';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-labelledby', 'crump50FileViewerTitle');
    const top = document.createElement('div');
    top.className = 'crump50-lightbox-bar';
    const title = document.createElement('span');
    title.id = 'crump50FileViewerTitle';
    title.textContent = file?.name || 'File';
    const actions = document.createElement('div');
    const download = document.createElement('button');
    download.type = 'button';
    download.textContent = 'Download';
    download.addEventListener('click', () => { void openFile(file, true); });
    const close = document.createElement('button');
    close.type = 'button';
    close.textContent = 'Done';
    const dismiss = () => {
      box.remove();
      if (state.lightbox === box) state.lightbox = null;
    };
    close.addEventListener('click', dismiss);
    actions.append(download, close);
    top.append(title, actions);

    const body = document.createElement('div');
    body.className = 'crump50-file-viewer-body';
    if (type.startsWith('video/')) {
      const video = document.createElement('video');
      video.controls = true;
      video.playsInline = true;
      video.preload = 'metadata';
      video.src = url;
      video.setAttribute('aria-label', `Play ${file?.name || 'video'}`);
      body.appendChild(video);
    } else if (type === 'application/pdf' || String(file?.name || '').toLowerCase().endsWith('.pdf')) {
      const frame = document.createElement('iframe');
      frame.src = url;
      frame.title = `Preview ${file?.name || 'PDF'}`;
      body.appendChild(frame);
    } else {
      const kind = fileKind(file);
      const placeholder = document.createElement('div');
      placeholder.className = 'crump50-file-viewer-placeholder';
      const icon = document.createElement('span');
      icon.innerHTML = iconFor(kind);
      const heading = document.createElement('strong');
      heading.textContent = kind === 'slides' ? 'Editable PowerPoint ready' : 'File ready to download';
      const detail = document.createElement('p');
      detail.textContent = kind === 'slides'
        ? 'Download the PPTX here, then open it in PowerPoint, Keynote, or a compatible editor. Ask Crump keeps you on this screen instead of sending you to private storage.'
        : 'This file type does not have a safe built-in preview yet. Download it here to open it with a compatible app on your device.';
      const metadata = document.createElement('small');
      metadata.textContent = `${String(file?.name || 'File').split('.').pop().toUpperCase()} · ${formatBytes(file?.size)}`;
      const downloadHere = document.createElement('button');
      downloadHere.type = 'button';
      downloadHere.textContent = 'Download to this device';
      downloadHere.addEventListener('click', () => { void openFile(file, true); });
      placeholder.append(icon, heading, detail, metadata, downloadHere);
      body.appendChild(placeholder);
    }

    box.append(top, body);
    box.addEventListener('keydown', event => {
      if (event.key === 'Escape') dismiss();
    });
    document.body.appendChild(box);
    state.lightbox = box;
    requestAnimationFrame(() => close.focus({preventScroll: true}));
    return true;
  }

  async function openFile(file, download = false) {
    if (!file?.id && !file?.url) return;
    const type = String(file?.type || '').toLowerCase();
    if (download && (type.startsWith('image/') || type.startsWith('video/')) && window.CrumpLibrary57?.saveMedia) {
      try {
        const handled = await window.CrumpLibrary57.saveMedia(file);
        if (handled) return;
      } catch (error) {
        console.warn('Ask Crump media save failed; using file download fallback.', error);
      }
    }
    if (!download && showFileViewer(file)) return true;
    const url = file.id ? `/api/files/${encodeURIComponent(file.id)}/content${download ? '?download=1' : ''}` : file.url;
    const link = document.createElement('a'); link.href = url; link.target = download ? '_self' : '_blank'; link.rel = 'noopener';
    if (download) link.download = file.name || 'download';
    document.body.appendChild(link); link.click(); link.remove();
    return true;
  }

  function showLightbox(file, url) {
    state.lightbox?.remove();
    const box = document.createElement('div'); box.className = 'crump50-lightbox';
    const img = document.createElement('img'); img.src = url; img.alt = file?.name || 'Generated image';
    const top = document.createElement('div'); top.className = 'crump50-lightbox-bar';
    const title = document.createElement('span'); title.textContent = file?.name || 'Image';
    const actions = document.createElement('div');
    const download = document.createElement('button'); download.type = 'button'; download.textContent = 'Download'; download.addEventListener('click', () => openFile(file, true));
    const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Done'; close.addEventListener('click', () => { box.remove(); if (state.lightbox === box) state.lightbox = null; });
    actions.append(download, close); top.append(title, actions); box.append(top, img); document.body.appendChild(box); state.lightbox = box;
  }

  function fileCard(file) {
    const card = document.createElement('button'); card.type = 'button'; card.className = 'crump50-file-card';
    card.innerHTML = `<span class="crump50-file-icon">${iconFor(fileKind(file))}</span><span><strong></strong><small></small></span><b>↗</b>`;
    $('strong', card).textContent = file.name || 'File';
    $('small', card).textContent = `${String(file.type || 'File').split('/').pop()?.toUpperCase() || 'FILE'}${file.size ? ` · ${formatBytes(file.size)}` : ''}`;
    card.addEventListener('click', () => openFile(file)); return card;
  }

  function outputProjectReceipt(message, kind) {
    const receipt = message?.projectAttachments?.[kind];
    if (!receipt || typeof receipt !== 'object') return null;
    const status = receipt.status === 'attached' || receipt.status === 'failed' || receipt.status === 'missing'
      ? receipt.status
      : '';
    const projectId = String(receipt.projectId || '').trim();
    if (!status || !projectId) return null;
    return {status, projectId};
  }

  function wireOutputProjectAction(button, {message, file, kind, role, label, statusNode = null}) {
    if (!button || !file?.id) { button?.remove(); return; }
    const receipt = outputProjectReceipt(message, kind);
    const targetProjectId = receipt?.status === 'failed' ? receipt.projectId : '';
    if (receipt?.status === 'attached') {
      button.dataset.projectId = receipt.projectId;
      button.textContent = 'Open Project';
      button.setAttribute('aria-label', `Open the Project containing ${label}`);
      if (statusNode) statusNode.textContent = 'Created by Crump · Saved in Project';
    } else {
      button.textContent = receipt?.status === 'failed'
        ? 'Retry Project save'
        : (receipt?.status === 'missing' ? 'Add to another Project' : 'Add to Project');
      button.setAttribute(
        'aria-label',
        receipt?.status === 'failed'
          ? `Retry adding ${label} to its Project`
          : `Add ${label} and its source conversation to a Project`,
      );
      if (statusNode && receipt?.status === 'failed') {
        statusNode.textContent = 'Created by Crump · Safe in Files · Project link needs retry';
      } else if (statusNode && receipt?.status === 'missing') {
        statusNode.textContent = 'Created by Crump · Safe in Files · Original Project is no longer available · Choose another Project';
      }
    }

    button.addEventListener('click', async () => {
      const savedProjectId = String(button.dataset.projectId || '').trim();
      if (savedProjectId) {
        const opened = await window.CrumpProduct53?.openProject?.(savedProjectId);
        if (!opened) window.CrumpProduct53?.open?.('projects');
        return;
      }
      const keepArtifact = window.CrumpProduct53?.keepArtifact;
      if (typeof keepArtifact !== 'function') {
        show('Projects are still loading. Try again in a moment.', 'error');
        return;
      }
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      try {
        const options = {role};
        if (targetProjectId) options.projectId = targetProjectId;
        const result = await keepArtifact(file, options);
        const projectId = String(result?.project?.id || '').trim();
        if (!result?.success || !projectId) throw new Error('The file could not be added to a Project.');
        message.projectAttachments = {
          ...(message.projectAttachments || {}),
          [kind]: {status: 'attached', projectId, role, shouldRetry: false},
        };
        const chat = currentChat();
        if (chat) saveAndRender(chat);
      } catch (error) {
        if (targetProjectId && Number(error?.status) === 404) {
          message.projectAttachments = {
            ...(message.projectAttachments || {}),
            [kind]: {
              status: 'missing',
              projectId: targetProjectId,
              role,
              shouldRetry: false,
              message: 'The file is safe in Files, but its original Project is no longer available.',
            },
          };
          const chat = currentChat();
          if (chat) saveAndRender(chat);
          window.showToast?.('Original Project is no longer available. Choose another Project.', 'info');
          return;
        }
        button.disabled = false;
      } finally {
        button.removeAttribute('aria-busy');
      }
      button.disabled = false;
    });
  }

  function enhanceRenderedMessages(messages) {
    const safe = Array.isArray(messages) ? messages : [];
    safe.forEach(message => {
      const row = message?.id ? document.querySelector(`[data-message-id="${CSS.escape(message.id)}"]`) : null;
      const wrapper = row?.querySelector('.message-wrapper');
      if (!wrapper || wrapper.dataset.crump50Enhanced === 'true') return;
      wrapper.dataset.crump50Enhanced = 'true';
      const files = Array.isArray(message.files) ? message.files.filter(file => file?.id || file?.url) : [];
      if (files.length) {
        const list = document.createElement('div'); list.className = 'crump50-message-files'; files.forEach(file => list.appendChild(fileCard(file)));
        wrapper.appendChild(list);
      }
      if (message.artifact) {
        const artifact = document.createElement('div'); artifact.className = 'crump50-artifact';
        artifact.innerHTML = `<span>${String(message.artifact.format || 'FILE').toUpperCase()}</span><div class="crump50-artifact-copy"><strong></strong><small>Created by Crump · ${formatBytes(message.artifact.size)}</small></div><div class="crump50-artifact-actions"><button type="button" data-artifact-project>Add to Project</button><button type="button" data-artifact-download>Download</button></div>`;
        $('strong', artifact).textContent = message.artifact.title || message.artifact.name || 'Crump document';
        const projectButton = $('[data-artifact-project]', artifact);
        const downloadButton = $('[data-artifact-download]', artifact);
        const artifactName = message.artifact.title || message.artifact.name || 'this file';
        wireOutputProjectAction(projectButton, {
          message, file: message.artifact, kind: 'artifact', role: 'generated_document',
          label: artifactName, statusNode: $('small', artifact),
        });
        downloadButton?.addEventListener('click', () => openFile(message.artifact, true)); wrapper.appendChild(artifact);
      }
      const artifactRecovery = message.artifactRecovery && typeof message.artifactRecovery === 'object'
        ? message.artifactRecovery
        : null;
      if (artifactRecovery?.shouldRetry && message.inReplyTo) {
        const recovery = document.createElement('div'); recovery.className = 'crump50-artifact';
        const packaged = artifactRecovery.status === 'packaged' && !!message.artifact;
        recovery.innerHTML = '<span data-artifact-recovery-format></span><div class="crump50-artifact-copy"><strong></strong><small></small></div><div class="crump50-artifact-actions"><button type="button" data-artifact-retry></button></div>';
        $('[data-artifact-recovery-format]', recovery).textContent = String(artifactRecovery.format || 'FILE').toUpperCase();
        $('strong', recovery).textContent = packaged ? 'Saved file link needs retry' : 'Downloadable file needs packaging';
        $('small', recovery).textContent = packaged
          ? 'Safe in Files · Conversation link needs retry'
          : 'Crump’s answer is saved · No generation or credits needed';
        const retry = $('[data-artifact-retry]', recovery);
        retry.textContent = packaged ? 'Retry saved file link' : 'Retry file packaging';
        retry.addEventListener('click', async () => {
          retry.disabled = true;
          retry.setAttribute('aria-busy', 'true');
          try {
            const data = await api(`/api/chat/artifacts/${encodeURIComponent(message.inReplyTo)}/retry`, {
              method: 'POST', body: '{}', timeoutMs: 45_000,
            });
            const recovered = data.assistantMessage && typeof data.assistantMessage === 'object'
              ? data.assistantMessage
              : {};
            if (data.artifact) message.artifact = data.artifact;
            if (data.projectAttachments) {
              message.projectAttachments = {...(message.projectAttachments || {}), ...data.projectAttachments};
            }
            if (data.artifactRecovery?.shouldRetry) message.artifactRecovery = data.artifactRecovery;
            else delete message.artifactRecovery;
            Object.assign(message, recovered);
            const chat = currentChat();
            if (chat) {
              if (data.conversationRevision) {
                chat.revision = Math.max(Number(chat.revision || 1), Number(data.conversationRevision || 1));
              }
              saveAndRender(chat);
            }
            window.showToast?.(
              data.conversationSaved === false
                ? 'The file is safe in Files. Retry its saved conversation link when ready.'
                : 'Downloadable file packaged from the saved answer.',
              data.conversationSaved === false ? 'info' : 'success',
            );
          } catch (error) {
            window.showToast?.(error.message || 'The saved answer is safe, but its file still needs packaging.', 'error');
            retry.disabled = false;
          } finally {
            retry.removeAttribute('aria-busy');
          }
        });
        wrapper.appendChild(recovery);
      }
      if (message.imageFile && message.imageUrl) {
        const generated = wrapper.querySelector('.generated-image-wrapper');
        if (generated) {
          generated.classList.add('crump50-generated');
          const img = generated.querySelector('img');
          if (img) img.addEventListener('click', () => showLightbox(message.imageFile, message.imageUrl));
          let actions = generated.querySelector('.crump50-image-actions');
          if (!actions) {
            actions = document.createElement('div'); actions.className = 'crump50-image-actions';
            const view = document.createElement('button'); view.type='button'; view.textContent='View'; view.addEventListener('click', () => showLightbox(message.imageFile, message.imageUrl));
            const edit = document.createElement('button'); edit.type='button'; edit.textContent='Edit'; edit.addEventListener('click', () => { state.imageRecovery=null; addRemoteReference(message.imageFile, {imageReference:true}); state.tool='image'; renderToolChip(); focusComposer('Tell Crump what to change…'); });
            const project = document.createElement('button'); project.type='button';
            const download = document.createElement('button'); download.type='button'; download.textContent='Download'; download.addEventListener('click', () => openFile(message.imageFile, true));
            wireOutputProjectAction(project, {
              message, file: message.imageFile, kind: 'imageFile', role: 'generated_image',
              label: message.imageFile.name || 'this image',
            });
            actions.append(view, edit, project, download); generated.appendChild(actions);
          }
        }
      }
    });
  }

  function wrapRenderer() {
    if (window.renderMessages?.__crump50Wrapped) return;
    const original = window.renderMessages;
    if (typeof original !== 'function') return;
    const wrapped = function(messages) {
      const result = original(messages);
      enhanceRenderedMessages(messages);
      return result;
    };
    wrapped.__crump50Wrapped = true;
    window.renderMessages = wrapped;
    const chat = currentChat(); if (chat) enhanceRenderedMessages(chat.messages);
  }

  function premiumShell() {
    document.body.classList.add('crump-50');
    const branding = $('.header-branding');
    if (branding && !document.body.classList.contains('crump-v1-body') && !$('#crump50Brand')) {
      branding.replaceChildren();
      const brand = document.createElement('div'); brand.id='crump50Brand'; brand.className='crump50-brand';
      brand.innerHTML='<span class="crump50-mark">C</span><span><strong>Ask Crump</strong><small>AI assistant</small></span>';
      branding.appendChild(brand);
    }
    const sidebarFooter = $('.sidebar-branding-footer .branding-engine'); if (sidebarFooter) sidebarFooter.textContent = 'Crump 5';
    $$('.quick-actions').forEach(node => node.classList.add('crump50-legacy-quick-actions'));
    renderToolChip();
  }


  window.CrumpFileTools = Object.freeze({
    addReference: file => addRemoteReference(file),
    open: (file, download = false) => openFile(file, download),
    upload: async file => {
      const normalized = await normalizeInputFile(file);
      const issue = validateFile(normalized);
      if (issue) throw new Error(issue);
      const item = makeLocalAttachment(normalized);
      try {
        return await uploadItem(item);
      } finally {
        if (item.previewUrl?.startsWith('blob:')) URL.revokeObjectURL(item.previewUrl);
      }
    },
  });
  window.CrumpDocumentStudio = Object.freeze({
    open: showDocumentOptions,
    select: (format = 'docx', placeholder = '', purpose = '') => {
      state.tool = 'document';
      state.documentFormat = String(format || 'docx').toLowerCase();
      state.documentPurpose = String(purpose || '').toLowerCase() === 'resume' ? 'resume' : null;
      closeMenu();
      renderToolChip();
      focusComposer(placeholder || `Describe the ${state.documentFormat.toUpperCase()} document you want…`);
    },
  });
  window.CrumpImageStudio = Object.freeze({
    open: showImageOptions,
  });
  function boot() {
    if (document.documentElement.dataset.crump50Booted === 'true') return;
    document.documentElement.dataset.crump50Booted = 'true';
    premiumShell(); replaceLegacyControls(); installPasteAndDrop(); wrapRenderer(); renderAttachmentTray();
    setTimeout(() => { premiumShell(); replaceLegacyControls(); installPasteAndDrop(); wrapRenderer(); }, 800);
  }

  if (document.readyState === 'complete') setTimeout(boot, 80);
  else window.addEventListener('load', () => setTimeout(boot, 80), {once: true});
})();
