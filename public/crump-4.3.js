(() => {
  'use strict';

  if (window.__crump43Loaded) return;
  window.__crump43Loaded = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function currentChatMessages() {
    const id = window.currentChatId;
    const chat = (window.chats || []).find(item => item?.id === id || item?.chat_id === id);
    return Array.isArray(chat?.messages) ? chat.messages : [];
  }

  function textPreview(message) {
    const content = String(message?.content || '').replace(/\s+/g, ' ').trim();
    if (!content && message?.imageUrl) return 'Generated image';
    if (!content && message?.files?.length) return 'Attachment';
    if (!content) return 'Start a conversation';
    const prefix = message?.role === 'user' ? 'You: ' : '';
    return `${prefix}${content.slice(0, 66)}${content.length > 66 ? '…' : ''}`;
  }

  function upgradeHeader() {
    const branding = $('.header-branding');
    if (!branding || branding.dataset.crump43 === 'true') return;
    branding.dataset.crump43 = 'true';
    branding.replaceChildren();

    const icon = document.createElement('img');
    icon.src = '/assets/logo-c.png';
    icon.alt = '';
    icon.className = 'crump-43-header-icon';

    const text = document.createElement('div');
    text.className = 'crump-43-header-text';
    const title = document.createElement('strong');
    title.textContent = 'Ask Crump';
    const status = document.createElement('span');
    status.innerHTML = '<i aria-hidden="true"></i> AI assistant';
    text.append(title, status);
    branding.append(icon, text);
  }

  function upgradeComposerIcons() {
    const attach = $('#attachBtn');
    if (attach && attach.dataset.crump43 !== 'true') {
      attach.dataset.crump43 = 'true';
      attach.title = 'Attach image or PDF';
      attach.setAttribute('aria-label', 'Attach image or PDF');
      attach.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M8.5 12.5L14.8 6.2a3.2 3.2 0 114.5 4.5l-8.2 8.2a5 5 0 11-7.1-7.1l8.1-8.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    }

    const send = $('#sendButton');
    if (send && send.dataset.crump43 !== 'true') {
      send.dataset.crump43 = 'true';
      send.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 19V5M6.5 10.5L12 5l5.5 5.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    }

    const input = $('#userInput');
    if (input) input.placeholder = `Message ${window.getAssistantName?.() || 'Crump'}`;
  }

  function fixPasswordCopy() {
    const registration = $('#registerPassword');
    if (registration) registration.placeholder = '10+ characters';
    const hint = registration?.closest('.form-group')?.querySelector('.form-hint');
    if (hint) hint.textContent = '10+ characters with at least one letter and one number';

    const reset = $('#newPassword');
    if (reset) reset.placeholder = '10+ characters';
    const resetHint = reset?.closest('.form-group')?.querySelector('.form-hint');
    if (resetHint) resetHint.textContent = '10+ characters with at least one letter and one number';
  }

  function updateComposerState() {
    const input = $('#userInput');
    const send = $('#sendButton');
    const filePreview = $('#filePreview');
    if (!input) return;

    const hasText = input.value.trim().length > 0;
    const hasFile = !!filePreview && !filePreview.hidden && getComputedStyle(filePreview).display !== 'none' && !!filePreview.children.length;
    document.body.classList.toggle('crump-composer-active', hasText || hasFile);
    $('.input-container')?.classList.toggle('has-content', hasText || hasFile);

    if (send) {
      send.classList.toggle('is-ready', hasText || hasFile);
      send.setAttribute('aria-disabled', String(!(hasText || hasFile)));
    }
  }

  function wireComposer() {
    const input = $('#userInput');
    if (!input || input.dataset.crump43 === 'true') return;
    input.dataset.crump43 = 'true';
    input.addEventListener('input', updateComposerState, { passive: true });
    input.addEventListener('focus', () => document.body.classList.add('crump-input-focused'));
    input.addEventListener('blur', () => document.body.classList.remove('crump-input-focused'));

    const filePreview = $('#filePreview');
    if (filePreview) {
      new MutationObserver(updateComposerState).observe(filePreview, {
        childList: true,
        attributes: true,
        attributeFilter: ['style', 'hidden'],
      });
    }
    updateComposerState();
  }

  function suggestionPrompts() {
    return [
      'Help me think through an idea',
      'Search the web for something current',
      'Explain something complicated simply',
      'Help me build or debug code',
    ];
  }

  function v1OwnsEmptyState() {
    return (
      document.body?.classList.contains('crump-v1-body') ||
      document.getElementById('v1Launchpad') !== null
    );
  }

  function makeEmptyState() {
    const section = document.createElement('section');
    section.className = 'crump-empty-state';
    section.setAttribute('aria-label', 'Start a conversation');

    const mark = document.createElement('div');
    mark.className = 'crump-empty-mark';
    const icon = document.createElement('img');
    icon.src = '/assets/logo-c.png';
    icon.alt = '';
    mark.appendChild(icon);

    const eyebrow = document.createElement('div');
    eyebrow.className = 'crump-empty-eyebrow';
    eyebrow.textContent = 'ASK CRUMP';

    const title = document.createElement('h1');
    title.textContent = 'What can I help with?';

    const description = document.createElement('p');
    description.textContent = 'Ask naturally. Bring an idea, a question, an image, a PDF, or something you want to build.';

    const prompts = document.createElement('div');
    prompts.className = 'crump-empty-prompts';
    for (const prompt of suggestionPrompts()) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'crump-empty-prompt';
      button.textContent = prompt;
      button.addEventListener('click', () => {
        const input = $('#userInput');
        if (!input) return;
        input.value = prompt;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.focus();
      });
      prompts.appendChild(button);
    }

    section.append(mark, eyebrow, title, description, prompts);
    return section;
  }

  function enhanceRenderedMessages(messages) {
    const container = $('#chatContainer');
    if (!container) return;

    const safeMessages = Array.isArray(messages) ? messages : [];
    if (!safeMessages.length) {
      if (v1OwnsEmptyState()) {
        // Ask Crump V1 has its own launchpad. Never let the 4.3 visual layer
        // create a second authenticated home screen on top of it.
        $$('.crump-empty-state', container).forEach(node => node.remove());
      } else if (!container.querySelector('.crump-empty-state')) {
        container.appendChild(makeEmptyState());
      }
    }

    $$('.assistant-message', container).forEach(row => {
      const wrapper = $('.message-wrapper', row);
      if (!wrapper || wrapper.querySelector('.crump-message-meta')) return;
      const meta = document.createElement('div');
      meta.className = 'crump-message-meta';
      const dot = document.createElement('span');
      dot.className = 'crump-message-avatar';
      dot.textContent = 'C';
      dot.setAttribute('aria-hidden', 'true');
      const label = document.createElement('span');
      label.textContent = 'Crump';
      meta.append(dot, label);
      wrapper.insertBefore(meta, wrapper.firstChild);

      const read = [...wrapper.querySelectorAll('.message-action-btn')].find(button => /read aloud/i.test(button.textContent));
      if (read) read.textContent = 'Listen';
    });
  }

  function patchRenderer() {
    if (window.renderMessages?.__crump43Wrapped) return true;
    const original = window.renderMessages;
    if (typeof original !== 'function') return false;

    function render43(messages) {
      original(messages);
      enhanceRenderedMessages(messages);
    }
    render43.__crump43Wrapped = true;
    render43.__original = original;
    window.renderMessages = render43;
    window.renderMessages(currentChatMessages());
    return true;
  }

  function enhanceConversationList() {
    const list = $('#chatsList');
    if (!list) return;
    const rows = [...list.querySelectorAll('.chat-item')];
    const chats = Array.isArray(window.chats) ? window.chats : [];

    rows.forEach((row, index) => {
      const chat = chats[index];
      const preview = $('.chat-preview', row);
      if (!preview || !chat) return;
      const messages = Array.isArray(chat.messages) ? chat.messages : [];
      const next = messages.length ? textPreview(messages[messages.length - 1]) : 'Start a new conversation';
      if (preview.textContent !== next) preview.textContent = next;
    });
  }

  function observeConversationList() {
    const list = $('#chatsList');
    if (!list || list.dataset.crump43 === 'true') return;
    list.dataset.crump43 = 'true';
    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      queueMicrotask(() => {
        queued = false;
        enhanceConversationList();
      });
    }).observe(list, { childList: true, subtree: true });
    enhanceConversationList();
  }

  function observeViewport() {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () => {
      const keyboardHeight = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
      document.documentElement.style.setProperty('--crump-keyboard-height', `${Math.round(keyboardHeight)}px`);
      document.body.classList.toggle('crump-keyboard-visible', keyboardHeight > 120);
    };
    viewport.addEventListener('resize', update, { passive: true });
    viewport.addEventListener('scroll', update, { passive: true });
    update();
  }

  function refreshQuickActionLabels() {
    const image = $('#imageQuickAction');
    const search = $('#searchQuickAction');
    const code = $('#codeQuickAction');
    if (image) image.textContent = 'Image';
    if (search) search.textContent = 'Web';
    if (code) code.textContent = 'Code';
  }

  function boot() {
    if (document.documentElement.dataset.crump43Booted === 'true') return;
    document.documentElement.dataset.crump43Booted = 'true';
    document.body.classList.add('crump-43');

    upgradeHeader();
    upgradeComposerIcons();
    fixPasswordCopy();
    wireComposer();
    observeConversationList();
    observeViewport();
    refreshQuickActionLabels();

    if (!patchRenderer()) {
      let attempts = 0;
      const timer = setInterval(() => {
        attempts += 1;
        if (patchRenderer() || attempts > 30) clearInterval(timer);
      }, 100);
    }
  }

  if (document.readyState === 'complete') boot();
  else window.addEventListener('load', boot, { once: true });
})();
