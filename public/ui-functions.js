(() => {
  'use strict';

  const escapeHtml = value => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

  function safeExternalUrl(value) {
    if (!value || typeof value !== 'string') return null;
    if (/^data:image\/(png|jpe?g|gif|webp);base64,[a-z0-9+/=\s]+$/i.test(value)) return value;
    if (/^blob:/i.test(value)) return value;
    try {
      const parsed = new URL(value, window.location.origin);
      if (['https:', 'http:'].includes(parsed.protocol)) return parsed.href;
    } catch (_) {}
    return null;
  }

  function inlineMarkdown(value) {
    let html = value;
    html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label, url) => {
      const safe = safeExternalUrl(url.replace(/&amp;/g, '&'));
      return safe ? `<a href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">${label}</a>` : label;
    });
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    return html;
  }

  function renderSafeMarkdown(raw) {
    const source = String(raw ?? '').replace(/\r\n/g, '\n');
    const protectedBlocks = [];
    const tokenSeed = window.crypto?.randomUUID?.()
      || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const token = html => {
      const id = `CRUMP_BLOCK_${tokenSeed}_${protectedBlocks.length}`;
      protectedBlocks.push({ id, html });
      return id;
    };

    let text = source.replace(/```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g, (_match, language, code) => {
      const lang = String(language || 'text').replace(/[^a-zA-Z0-9_+-]/g, '').slice(0, 30) || 'text';
      return `\n${token(`<pre class="code-block"><code class="language-${lang}">${escapeHtml(code.trim())}</code></pre>`)}\n`;
    });
    text = text.replace(/`([^`\n]+)`/g, (_match, code) => token(`<code class="inline-code">${escapeHtml(code)}</code>`));
    text = escapeHtml(text);

    const lines = text.split('\n');
    const output = [];
    let paragraph = [];
    let list = [];
    const restore = value => {
      let restored = value;
      for (const block of protectedBlocks) restored = restored.replaceAll(block.id, block.html);
      return restored;
    };
    const flushParagraph = () => {
      if (!paragraph.length) return;
      output.push(`<p>${inlineMarkdown(paragraph.join('<br>'))}</p>`);
      paragraph = [];
    };
    const flushList = () => {
      if (!list.length) return;
      output.push(`<ul>${list.map(item => `<li>${inlineMarkdown(item)}</li>`).join('')}</ul>`);
      list = [];
    };

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        flushParagraph();
        flushList();
        continue;
      }
      if (protectedBlocks.some(block => block.id === trimmed)) {
        flushParagraph();
        flushList();
        output.push(trimmed);
        continue;
      }
      const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        flushList();
        output.push(`<h${heading[1].length}>${inlineMarkdown(heading[2])}</h${heading[1].length}>`);
        continue;
      }
      const bullet = trimmed.match(/^[-*]\s+(.+)$/);
      if (bullet) {
        flushParagraph();
        list.push(bullet[1]);
        continue;
      }
      flushList();
      paragraph.push(trimmed);
    }
    flushParagraph();
    flushList();
    return restore(output.join(''));
  }

  const activeToasts = new Set();

  function showToast(message, tone = 'info', options = {}) {
    const container = document.getElementById('toastContainer');
    if (!container) return null;

    const allowedTones = new Set(['success', 'error', 'warning', 'info']);
    const toastTone = allowedTones.has(tone) ? tone : 'info';
    const toast = document.createElement('div');
    toast.className = `toast ${toastTone}`;
    toast.setAttribute('role', toastTone === 'error' ? 'alert' : 'status');
    toast.setAttribute('aria-live', toastTone === 'error' ? 'assertive' : 'polite');

    const text = document.createElement('span');
    text.className = 'toast__message';
    text.textContent = String(message || '');
    toast.appendChild(text);

    const dismiss = document.createElement('button');
    dismiss.type = 'button';
    dismiss.className = 'toast__dismiss';
    dismiss.setAttribute('aria-label', 'Dismiss notification');
    dismiss.textContent = 'Dismiss';
    toast.appendChild(dismiss);

    let timer = null;
    const remove = () => {
      if (!activeToasts.has(toast)) return;
      activeToasts.delete(toast);
      if (timer) window.clearTimeout(timer);
      toast.classList.add('toast--leaving');
      toast.addEventListener('animationend', () => toast.remove(), { once: true });
      window.setTimeout(() => toast.remove(), 250);
    };

    dismiss.addEventListener('click', remove);
    container.appendChild(toast);
    activeToasts.add(toast);

    while (activeToasts.size > 4) {
      const oldest = activeToasts.values().next().value;
      if (oldest) {
        activeToasts.delete(oldest);
        oldest.remove();
      }
    }

    const duration = Number(options.duration ?? (toastTone === 'error' ? 7000 : 4500));
    if (Number.isFinite(duration) && duration > 0) timer = window.setTimeout(remove, duration);
    return toast;
  }

  window.showToast = showToast;

  function confirmAction({ title, message, confirmLabel = 'Continue', cancelLabel = 'Cancel', destructive = false }) {
    return new Promise(resolve => {
      const dialog = document.createElement('dialog');
      dialog.className = 'confirm-dialog';
      dialog.setAttribute('aria-labelledby', 'confirm-dialog-title');
      dialog.setAttribute('aria-describedby', 'confirm-dialog-message');

      const card = document.createElement('form');
      card.className = 'confirm-dialog__card';
      card.method = 'dialog';

      const heading = document.createElement('h2');
      heading.id = 'confirm-dialog-title';
      heading.textContent = title;

      const body = document.createElement('p');
      body.id = 'confirm-dialog-message';
      body.textContent = message;

      const actions = document.createElement('div');
      actions.className = 'confirm-dialog__actions';

      const cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.className = 'btn btn-secondary';
      cancel.textContent = cancelLabel;

      const confirm = document.createElement('button');
      confirm.type = 'button';
      confirm.className = destructive ? 'btn confirm-dialog__danger' : 'btn btn-primary';
      confirm.textContent = confirmLabel;

      actions.append(cancel, confirm);
      card.append(heading, body, actions);
      dialog.appendChild(card);
      document.body.appendChild(dialog);

      let settled = false;
      const finish = value => {
        if (settled) return;
        settled = true;
        dialog.close?.();
        dialog.remove();
        resolve(value);
      };

      cancel.addEventListener('click', () => finish(false));
      confirm.addEventListener('click', () => finish(true));
      dialog.addEventListener('cancel', event => {
        event.preventDefault();
        finish(false);
      });
      dialog.addEventListener('click', event => {
        if (event.target === dialog) finish(false);
      });

      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
      requestAnimationFrame(() => cancel.focus());
    });
  }

  window.confirmAction = confirmAction;

  function currentMessages() {
    const chat = (window.chats || []).find(item => item.id === window.currentChatId || item.chat_id === window.currentChatId);
    return chat?.messages || [];
  }

  async function copyMessage(index) {
    const content = currentMessages()[index]?.content || '';
    try {
      await navigator.clipboard.writeText(content);
      window.showToast?.('Copied', 'success');
    } catch (_) {
      const area = document.createElement('textarea');
      area.value = content;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      area.remove();
      window.showToast?.('Copied', 'success');
    }
  }

  function openImage(url) {
    const safe = safeExternalUrl(url);
    if (safe) window.open(safe, '_blank', 'noopener,noreferrer');
  }

  function downloadImage(url) {
    const safe = safeExternalUrl(url);
    if (!safe) return;
    const link = document.createElement('a');
    link.href = safe;
    link.download = `ask-crump-image-${Date.now()}.png`;
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function createImageBlock(url, alt = 'Generated image') {
    const safe = safeExternalUrl(url);
    if (!safe) return null;
    const wrapper = document.createElement('div');
    wrapper.className = 'generated-image-wrapper';
    const image = document.createElement('img');
    image.src = safe;
    image.className = 'message-image';
    image.alt = alt;
    image.loading = 'lazy';
    image.addEventListener('error', () => {
      wrapper.replaceChildren(Object.assign(document.createElement('div'), { className: 'image-error', textContent: 'Image failed to load.' }));
    });
    wrapper.appendChild(image);
    const actions = document.createElement('div');
    actions.className = 'image-actions';
    for (const [label, handler] of [['Download', () => downloadImage(safe)], ['Open', () => openImage(safe)]]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'image-action-btn';
      button.textContent = label;
      button.addEventListener('click', handler);
      actions.appendChild(button);
    }
    wrapper.appendChild(actions);
    return wrapper;
  }

  function deliveryLabel(message) {
    if (message?.replyStatus === 'failed') return { label: 'Seen · Reply failed — Tap to retry', tone: 'failed', retry: true };
    const status = message?.deliveryStatus || 'seen';
    const labels = {
      sending: { label: 'Sending…', tone: 'pending' },
      queued: { label: 'Waiting for connection', tone: 'pending', retry: true },
      delivered: { label: 'Delivered', tone: 'delivered' },
      seen: { label: 'Seen', tone: 'seen' },
      failed: { label: 'Not delivered — Tap to retry', tone: 'failed', retry: true },
    };
    return labels[status] || labels.seen;
  }

  function createDeliveryStatus(message) {
    const state = deliveryLabel(message);
    const element = state.retry ? document.createElement('button') : document.createElement('div');
    if (state.retry) element.type = 'button';
    element.className = `message-status ${state.tone}`;
    element.textContent = state.label;
    element.setAttribute('aria-label', state.label);
    if (state.retry) element.addEventListener('click', () => window.retryMessage?.(message.id));
    return element;
  }

  function createPresenceRow(state) {
    const row = document.createElement('div');
    row.className = 'message assistant-message presence-message';
    row.setAttribute('aria-hidden', 'true');
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper';
    const bubble = document.createElement('div');
    bubble.className = 'message-content presence-bubble';
    const dots = document.createElement('span');
    dots.className = 'typing-dots';
    dots.innerHTML = '<i></i><i></i><i></i>';
    bubble.appendChild(dots);
    if (state.expanded) {
      const label = document.createElement('span');
      label.className = 'presence-label';
      label.textContent = state.label;
      bubble.appendChild(label);
    }
    wrapper.appendChild(bubble);
    row.appendChild(wrapper);
    return row;
  }

  function renderMessages(messages) {
    const container = document.getElementById('chatContainer');
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    const shouldStick = distanceFromBottom < 180 || container.childElementCount === 0;
    const fragment = document.createDocumentFragment();
    const safeMessages = Array.isArray(messages) ? messages : [];
    let lastUserIndex = -1;
    safeMessages.forEach((message, index) => { if (message?.role === 'user') lastUserIndex = index; });

    safeMessages.forEach((message, index) => {
      const isUser = message?.role === 'user';
      const row = document.createElement('article');
      row.className = `message ${isUser ? 'user-message user' : 'assistant-message'}`;
      row.dataset.messageId = message?.id || '';
      row.setAttribute('aria-label', isUser ? 'Your message' : 'Crump response');

      const wrapper = document.createElement('div');
      wrapper.className = 'message-wrapper';
      const content = document.createElement('div');
      content.className = 'message-content';
      if (isUser) content.textContent = String(message?.content || '');
      else content.innerHTML = renderSafeMarkdown(message?.content || '');
      wrapper.appendChild(content);

      for (const file of Array.isArray(message?.files) ? message.files : []) {
        const attachment = document.createElement('div');
        attachment.className = 'message-attachment';
        const info = document.createElement('div');
        info.className = 'file-info';
        const name = document.createElement('div');
        name.className = 'file-name';
        name.textContent = file?.name || 'Attachment';
        const type = document.createElement('div');
        type.className = 'file-meta';
        type.textContent = file?.type || 'File';
        info.append(name, type);
        attachment.appendChild(info);
        wrapper.appendChild(attachment);
      }

      if (message?.imageUrl) {
        const imageBlock = createImageBlock(message.imageUrl);
        if (imageBlock) wrapper.appendChild(imageBlock);
      }

      if (isUser && index === lastUserIndex) wrapper.appendChild(createDeliveryStatus(message));

      if (!isUser) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'message-action-btn';
        copy.textContent = 'Copy';
        copy.addEventListener('click', () => copyMessage(index));
        const speak = document.createElement('button');
        speak.type = 'button';
        speak.className = 'message-action-btn';
        speak.textContent = 'Read aloud';
        speak.addEventListener('click', () => window.speakText?.(String(message?.content || '')));
        actions.append(copy, speak);
        wrapper.appendChild(actions);
      }

      row.appendChild(wrapper);
      fragment.appendChild(row);
    });

    const presence = window.CrumpPresence?.indicator?.();
    if (presence) fragment.appendChild(createPresenceRow(presence));
    container.replaceChildren(fragment);
    if (shouldStick || presence) requestAnimationFrame(() => { container.scrollTop = container.scrollHeight; });
  }

  window.renderMessages = renderMessages;
  window.renderMarkdown = renderSafeMarkdown;
  window.copyMessage = copyMessage;
  window.downloadImage = downloadImage;
  window.openImageInNewTab = openImage;
})();
