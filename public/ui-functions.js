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
    let listTag = 'ul';
    let quote = [];
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
      output.push(`<${listTag}>${list.map(item => `<li>${inlineMarkdown(item)}</li>`).join('')}</${listTag}>`);
      list = [];
      listTag = 'ul';
    };
    const flushQuote = () => {
      if (!quote.length) return;
      output.push(`<blockquote>${quote.map(line => inlineMarkdown(line)).join('<br>')}</blockquote>`);
      quote = [];
    };
    const tableCells = line => line
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map(cell => cell.trim());
    const isTableDivider = line => /^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?$/.test(line);
    const renderTable = (header, rows) => {
      const head = `<thead><tr>${header.map(cell => `<th scope="col">${inlineMarkdown(cell)}</th>`).join('')}</tr></thead>`;
      const body = rows.length
        ? `<tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${inlineMarkdown(cell)}</td>`).join('')}</tr>`).join('')}</tbody>`
        : '';
      return `<div class="markdown-table-wrap"><table>${head}${body}</table></div>`;
    };

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trim();
      if (!trimmed) {
        flushParagraph();
        flushList();
        flushQuote();
        continue;
      }
      if (protectedBlocks.some(block => block.id === trimmed)) {
        flushParagraph();
        flushList();
        flushQuote();
        output.push(trimmed);
        continue;
      }
      if (index + 1 < lines.length && trimmed.includes('|') && isTableDivider(lines[index + 1].trim())) {
        flushParagraph();
        flushList();
        flushQuote();
        const header = tableCells(trimmed);
        const rows = [];
        index += 2;
        while (index < lines.length) {
          const row = lines[index].trim();
          if (!row || !row.includes('|')) break;
          const cells = tableCells(row);
          while (cells.length < header.length) cells.push('');
          rows.push(cells.slice(0, header.length));
          index += 1;
        }
        index -= 1;
        output.push(renderTable(header, rows));
        continue;
      }
      const quoteLine = trimmed.match(/^&gt;\s?(.*)$/);
      if (quoteLine) {
        flushParagraph();
        flushList();
        quote.push(quoteLine[1]);
        continue;
      }
      flushQuote();
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
        if (list.length && listTag !== 'ul') flushList();
        listTag = 'ul';
        list.push(bullet[1]);
        continue;
      }
      const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
      if (ordered) {
        flushParagraph();
        if (list.length && listTag !== 'ol') flushList();
        listTag = 'ol';
        list.push(ordered[1]);
        continue;
      }
      flushList();
      paragraph.push(trimmed);
    }
    flushParagraph();
    flushList();
    flushQuote();
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

  const reportedMessageIds = new Set();
  const reportCategories = Object.freeze([
    ['hate_or_harassment', 'Hate or harassment'],
    ['sexual_content', 'Sexual content'],
    ['violence_or_danger', 'Violence or dangerous guidance'],
    ['self_harm', 'Self-harm content'],
    ['deception_or_fraud', 'Deception or fraud'],
    ['privacy', 'Privacy concern'],
    ['copyright', 'Copyright concern'],
    ['other', 'Something else'],
  ]);

  async function reportMessage(message, trigger) {
    const dialog = document.createElement('dialog');
    dialog.className = 'content-report-dialog';
    dialog.setAttribute('aria-labelledby', 'content-report-title');
    dialog.setAttribute('aria-describedby', 'content-report-description');

    const form = document.createElement('form');
    form.className = 'content-report-dialog__card';
    form.method = 'dialog';

    const eyebrow = document.createElement('span');
    eyebrow.className = 'content-report-dialog__eyebrow';
    eyebrow.textContent = 'SAFETY REVIEW';

    const title = document.createElement('h2');
    title.id = 'content-report-title';
    title.textContent = 'Report this response';

    const description = document.createElement('p');
    description.id = 'content-report-description';
    description.textContent = 'Tell us why this response may be unsafe or inappropriate. Your report helps improve Ask Crump safeguards.';

    const reasonLabel = document.createElement('label');
    reasonLabel.htmlFor = 'content-report-reason';
    reasonLabel.textContent = 'Reason';
    const reason = document.createElement('select');
    reason.id = 'content-report-reason';
    reason.required = true;
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Choose a reason';
    placeholder.disabled = true;
    placeholder.selected = true;
    reason.appendChild(placeholder);
    for (const [value, label] of reportCategories) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      reason.appendChild(option);
    }

    const commentLabel = document.createElement('label');
    commentLabel.htmlFor = 'content-report-comment';
    commentLabel.textContent = 'Details (optional)';
    const comment = document.createElement('textarea');
    comment.id = 'content-report-comment';
    comment.maxLength = 2000;
    comment.rows = 4;
    comment.placeholder = 'What should our safety team know?';

    const actions = document.createElement('div');
    actions.className = 'content-report-dialog__actions';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'btn btn-secondary';
    cancel.textContent = 'Cancel';
    const submit = document.createElement('button');
    submit.type = 'submit';
    submit.className = 'btn btn-primary';
    submit.textContent = 'Send report';
    actions.append(cancel, submit);

    form.append(eyebrow, title, description, reasonLabel, reason, commentLabel, comment, actions);
    dialog.appendChild(form);
    document.body.appendChild(dialog);

    let submitting = false;
    const close = () => {
      if (submitting) return;
      dialog.close?.();
      dialog.remove();
      trigger?.focus?.();
    };
    cancel.addEventListener('click', close);
    dialog.addEventListener('cancel', event => {
      event.preventDefault();
      close();
    });
    dialog.addEventListener('click', event => {
      if (event.target === dialog) close();
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!reason.value || submitting) return;
      submitting = true;
      cancel.disabled = true;
      submit.disabled = true;
      submit.textContent = 'Sending…';
      try {
        const response = await fetch('/api/safety/reports', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            chatId: window.currentChatId,
            messageId: message?.id || null,
            category: reason.value,
            comment: comment.value,
            response: String(message?.content || '').slice(0, 30000),
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) throw new Error(data.error || 'The report could not be sent.');
        const messageKey = String(message?.id || '');
        if (messageKey) reportedMessageIds.add(messageKey);
        if (trigger) {
          trigger.textContent = 'Reported';
          trigger.disabled = true;
          trigger.setAttribute('aria-label', 'Response reported');
        }
        submitting = false;
        window.showToast?.('Thanks — this response was sent for safety review.', 'success');
        close();
      } catch (error) {
        submitting = false;
        cancel.disabled = false;
        submit.disabled = false;
        submit.textContent = 'Send report';
        window.showToast?.(error.message || 'The report could not be sent.', 'error');
      }
    });

    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    requestAnimationFrame(() => reason.focus());
  }

  const ASK_CRUMP_SHARE_URL = 'https://www.askcrump.com/?acquisition=referral&source=response-share';

  async function writeClipboard(content) {
    let clipboardError = null;
    try {
      await navigator.clipboard.writeText(content);
      return true;
    } catch (error) {
      clipboardError = error;
    }

    const area = document.createElement('textarea');
    area.value = content;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    try {
      area.select();
      if (document.execCommand?.('copy') !== true) {
        throw clipboardError || new Error('Clipboard access is unavailable.');
      }
      return true;
    } finally {
      area.remove();
    }
  }

  async function copyMessage(index) {
    const content = currentMessages()[index]?.content || '';
    try {
      await writeClipboard(content);
      window.showToast?.('Copied', 'success');
      return true;
    } catch (_) {
      window.showToast?.('Copy is unavailable in this browser.', 'error');
      return false;
    }
  }

  function responseShareKey(message, index) {
    const raw = String(message?.id || `${window.currentChatId || 'chat'}-${index}-${Date.now()}`);
    const safe = raw.replace(/[^A-Za-z0-9:._-]/g, '-').slice(0, 120) || String(Date.now());
    return `response-share:${safe}`;
  }

  function shareableResponse(content) {
    const normalized = String(content || '').trim();
    if (normalized.length <= 3500) return normalized;
    return `${normalized.slice(0, 3497).trimEnd()}…`;
  }

  async function recordResponseShare(message, index, source) {
    await window.CrumpAnalytics?.track?.('ResponseShared', {
      eventKey: responseShareKey(message, index),
      source,
    });
  }

  async function shareMessage(index) {
    const message = currentMessages()[index];
    const excerpt = shareableResponse(message?.content);
    if (!excerpt) return;
    const payload = {
      title: 'Ask Crump',
      text: `${excerpt}\n\nCreated with Ask Crump`,
      url: ASK_CRUMP_SHARE_URL,
    };
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share(payload);
        await recordResponseShare(message, index, 'native_share');
        window.showToast?.('Shared', 'success');
        return true;
      } catch (error) {
        if (error?.name === 'AbortError') return false;
      }
    }
    try {
      await writeClipboard(`${payload.text} — ${payload.url}`);
      await recordResponseShare(message, index, 'clipboard');
      window.showToast?.('Share text copied', 'success');
      return true;
    } catch (_) {
      window.showToast?.('Sharing is unavailable in this browser.', 'error');
      return false;
    }
  }

  async function shareAskCrump(message, index) {
    const payload = {
      title: 'Ask Crump',
      text: 'Ask Crump helped me move work forward. Try it free.',
      url: ASK_CRUMP_SHARE_URL,
    };
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share(payload);
        await recordResponseShare(message, index, 'useful_prompt_native');
        window.showToast?.('Shared', 'success');
        return true;
      } catch (error) {
        if (error?.name === 'AbortError') return false;
      }
    }
    try {
      await writeClipboard(`${payload.text} ${payload.url}`);
      await recordResponseShare(message, index, 'useful_prompt_clipboard');
      window.showToast?.('Ask Crump link copied', 'success');
      return true;
    } catch (_) {
      window.showToast?.('Sharing is unavailable in this browser.', 'error');
      return false;
    }
  }

  const OUTCOME_FEEDBACK_STORAGE_PREFIX = 'askcrump.outcome-feedback.';

  function responseOutcomeKey(message, index) {
    const raw = String(message?.id || `${window.currentChatId || 'chat'}-${index}`);
    const safe = raw.replace(/[^A-Za-z0-9:._-]/g, '-').slice(0, 120) || `message-${index}`;
    return `outcome-feedback:${safe}`;
  }

  function savedOutcomeFeedback(eventKey) {
    try {
      const value = window.sessionStorage.getItem(`${OUTCOME_FEEDBACK_STORAGE_PREFIX}${eventKey}`);
      return ['useful', 'needs_work'].includes(value) ? value : null;
    } catch (_) {
      return null;
    }
  }

  function saveOutcomeFeedback(eventKey, value) {
    try {
      window.sessionStorage.setItem(`${OUTCOME_FEEDBACK_STORAGE_PREFIX}${eventKey}`, value);
    } catch (_) {}
  }

  function currentProjectTarget() {
    const target = window.CrumpProduct53?.projectTarget?.();
    const id = String(target?.id || '').trim();
    if (!id) return null;
    const name = String(target?.name || 'Project').replace(/\s+/g, ' ').trim() || 'Project';
    return {id, name, displayName: name.length > 56 ? `${name.slice(0, 55)}…` : name};
  }

  function syncOutcomeProjectAction(button) {
    if (!button || button.dataset.saved === 'true') return;
    const target = currentProjectTarget();
    button.dataset.projectId = target?.id || '';
    button.textContent = target ? `Keep in \u201c${target.displayName}\u201d` : 'Start a Project';
    button.setAttribute(
      'aria-label',
      target
        ? `Save this private conversation to the Project \u201c${target.name}\u201d`
        : 'Start a private Project with this conversation',
    );
  }

  function showSavedOutcomeProject(button, project) {
    const projectId = String(project?.id || '').trim();
    if (!button || !projectId) return false;
    const projectName = String(project?.name || 'Project').replace(/\s+/g, ' ').trim() || 'Project';
    button.dataset.projectId = projectId;
    button.dataset.saved = 'true';
    button.textContent = 'Open Project';
    button.setAttribute('aria-label', `Open Project \u201c${projectName}\u201d containing this conversation`);
    const prompt = button.closest('.outcome-feedback')?.querySelector('.outcome-continuity-prompt');
    if (prompt) prompt.textContent = `Saved to "${projectName}".`;
    return true;
  }

  async function hydrateOutcomeProjectAction(button) {
    if (!button || button.dataset.saved === 'true' || button.dataset.projectLookup === 'pending') return;
    const chatId = String(button.dataset.chatId || '').trim();
    const resolver = window.CrumpProduct53?.resolveOutcomeProject;
    const lookup = window.CrumpProduct53?.projectForConversation;
    if (!chatId || (typeof resolver !== 'function' && typeof lookup !== 'function')) return;
    const wasDisabled = button.disabled;
    const previousBusy = button.getAttribute('aria-busy');
    button.dataset.projectLookup = 'pending';
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = 'Checking Project…';
    button.setAttribute('aria-label', 'Checking whether this conversation is already saved to a Project');
    try {
      const resolution = typeof resolver === 'function'
        ? await resolver(chatId)
        : {project: await lookup(chatId), saved: true};
      if (button.dataset.saved !== 'true' && resolution?.saved) {
        showSavedOutcomeProject(button, resolution.project);
      }
    } catch (_) {
      // Relationship recognition is fail-open; the existing save action remains available.
    } finally {
      delete button.dataset.projectLookup;
      if (button.dataset.saved !== 'true') syncOutcomeProjectAction(button);
      button.disabled = wasDisabled;
      if (previousBusy === null) button.removeAttribute('aria-busy');
      else button.setAttribute('aria-busy', previousBusy);
    }
  }

  function syncOutcomeProjectActions() {
    document.querySelectorAll('.outcome-project-btn').forEach(button => {
      syncOutcomeProjectAction(button);
      void hydrateOutcomeProjectAction(button);
    });
  }

  window.addEventListener?.('crump:project-target-changed', syncOutcomeProjectActions);
  window.addEventListener?.('crump:project-service-ready', syncOutcomeProjectActions);

  function createOutcomeFeedback(message, index) {
    const eventKey = responseOutcomeKey(message, index);
    const group = document.createElement('div');
    group.className = 'outcome-feedback';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', 'Keep this result and share feedback');

    const continuityPrompt = document.createElement('span');
    continuityPrompt.className = 'outcome-continuity-prompt';
    continuityPrompt.textContent = 'Keep this work moving?';
    const projectButton = document.createElement('button');
    projectButton.type = 'button';
    projectButton.className = 'outcome-feedback-btn outcome-project-btn';
    projectButton.dataset.chatId = String(window.currentChatId || '').trim();
    syncOutcomeProjectAction(projectButton);
    projectButton.addEventListener('click', async () => {
      if (projectButton.dataset.saved === 'true') {
        const projectId = String(projectButton.dataset.projectId || '').trim();
        const openProject = window.CrumpProduct53?.openProject;
        if (projectId && typeof openProject === 'function') {
          projectButton.disabled = true;
          projectButton.setAttribute('aria-busy', 'true');
          try {
            if (await openProject(projectId)) return;
          } finally {
            projectButton.disabled = false;
            projectButton.removeAttribute('aria-busy');
          }
        }
        window.CrumpProduct53?.open?.('projects');
        return;
      }
      projectButton.disabled = true;
      const keepConversation = window.CrumpProduct53?.keepConversation;
      if (typeof keepConversation !== 'function') {
        projectButton.disabled = false;
        window.showToast?.('Projects are still loading. Try again in a moment.', 'error');
        return;
      }
      try {
        const result = await keepConversation({projectId: projectButton.dataset.projectId || null});
        if (!result?.success) throw new Error('Projects are still loading. Try again in a moment.');
        continuityPrompt.textContent = `Saved to "${result.project?.name || 'Project'}".`;
        showSavedOutcomeProject(projectButton, result.project);
      } catch (_) {
        projectButton.disabled = false;
        return;
      }
      projectButton.disabled = false;
    });

    const renderThanks = value => {
      const status = document.createElement('span');
      status.className = 'outcome-feedback-status';
      status.setAttribute('role', 'status');
      status.textContent = 'Thanks — feedback saved.';
      group.replaceChildren(continuityPrompt, projectButton, status);
      if (value !== 'useful') return;

      const referralPrompt = document.createElement('span');
      referralPrompt.className = 'outcome-referral-prompt';
      referralPrompt.textContent = 'Or help someone else:';
      const referralButton = document.createElement('button');
      referralButton.type = 'button';
      referralButton.className = 'outcome-feedback-btn outcome-referral-btn';
      referralButton.textContent = 'Share Ask Crump';
      referralButton.setAttribute('aria-label', 'Share Ask Crump without including your conversation');
      referralButton.addEventListener('click', async () => {
        referralButton.disabled = true;
        try {
          await shareAskCrump(message, index);
        } finally {
          referralButton.disabled = false;
        }
      });
      group.append(referralPrompt, referralButton);
    };

    const savedFeedback = savedOutcomeFeedback(eventKey);
    if (savedFeedback) {
      renderThanks(savedFeedback);
      void hydrateOutcomeProjectAction(projectButton);
      return group;
    }

    const prompt = document.createElement('span');
    prompt.className = 'outcome-feedback-prompt';
    prompt.textContent = 'Did this move your work forward?';
    const buttons = [];

    for (const [label, value] of [['Yes', 'useful'], ['Not yet', 'needs_work']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'outcome-feedback-btn';
      button.textContent = label;
      button.addEventListener('click', async () => {
        buttons.forEach(item => { item.disabled = true; });
        const recorded = await window.CrumpAnalytics?.track?.('OutcomeFeedbackSubmitted', {
          eventKey,
          source: value,
        });
        if (!recorded) {
          buttons.forEach(item => { item.disabled = false; });
          window.showToast?.('Feedback could not be saved. Try again.', 'error');
          return;
        }
        saveOutcomeFeedback(eventKey, value);
        renderThanks(value);
      });
      buttons.push(button);
    }

    group.append(continuityPrompt, projectButton, prompt, ...buttons);
    void hydrateOutcomeProjectAction(projectButton);
    return group;
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

  function createIntelligenceReceipt(message) {
    const intelligence = message?.intelligence;
    if (!intelligence || typeof intelligence !== 'object') return null;
    const signals = [];
    if (intelligence.plannerUsed === true) signals.push('Thought longer');
    if (intelligence.verifierUsed === true) signals.push('Reviewed');
    if (!signals.length) return null;

    const receipt = document.createElement('div');
    receipt.className = 'message-intelligence-receipt';
    receipt.setAttribute('role', 'status');
    receipt.setAttribute('aria-label', `Advanced Intelligence used: ${signals.join(' and ')}`);
    const label = document.createElement('span');
    label.className = 'message-intelligence-label';
    label.textContent = 'Advanced Intelligence';
    receipt.appendChild(label);
    signals.forEach(signal => {
      const badge = document.createElement('span');
      badge.className = 'message-intelligence-signal';
      badge.textContent = signal;
      receipt.appendChild(badge);
    });
    return receipt;
  }

  function renderMessages(messages) {
    const container = document.getElementById('chatContainer');
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    const shouldStick = distanceFromBottom < 180 || container.childElementCount === 0;
    const fragment = document.createDocumentFragment();
    const safeMessages = Array.isArray(messages) ? messages : [];
    let lastUserIndex = -1;
    let lastAssistantIndex = -1;
    safeMessages.forEach((message, index) => { if (message?.role === 'user') lastUserIndex = index; });
    safeMessages.forEach((message, index) => { if (message?.role !== 'user') lastAssistantIndex = index; });

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
        const intelligenceReceipt = createIntelligenceReceipt(message);
        if (intelligenceReceipt) wrapper.appendChild(intelligenceReceipt);
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'message-action-btn';
        copy.textContent = 'Copy';
        copy.addEventListener('click', () => copyMessage(index));
        const share = document.createElement('button');
        share.type = 'button';
        share.className = 'message-action-btn message-share-btn';
        share.textContent = 'Share';
        share.setAttribute('aria-label', 'Share this response');
        share.addEventListener('click', () => shareMessage(index));
        const speak = document.createElement('button');
        speak.type = 'button';
        speak.className = 'message-action-btn';
        speak.textContent = 'Read aloud';
        speak.addEventListener('click', () => window.speakText?.(String(message?.content || '')));
        const report = document.createElement('button');
        report.type = 'button';
        report.className = 'message-action-btn message-report-btn';
        report.textContent = reportedMessageIds.has(String(message?.id || '')) ? 'Reported' : 'Report';
        report.disabled = reportedMessageIds.has(String(message?.id || ''));
        report.setAttribute('aria-label', report.disabled ? 'Response reported' : 'Report this response');
        report.addEventListener('click', () => reportMessage(message, report));
        actions.append(copy, share, speak, report);
        wrapper.appendChild(actions);
        if (
          index === lastAssistantIndex
          && (String(message?.content || '').trim() || message?.imageUrl)
        ) {
          wrapper.appendChild(createOutcomeFeedback(message, index));
        }
      }

      row.appendChild(wrapper);
      fragment.appendChild(row);
    });

    const presence = window.CrumpPresence?.indicator?.();
    if (presence) fragment.appendChild(createPresenceRow(presence));
    container.replaceChildren(fragment);
    if (shouldStick || presence) {
      requestAnimationFrame(() => {
        if (typeof window.crumpScrollManager?.scrollToBottom === 'function') {
          window.crumpScrollManager.scrollToBottom('auto');
          return;
        }
        container.scrollTop = container.scrollHeight;
      });
    }
  }

  window.renderMessages = renderMessages;
  window.renderMarkdown = renderSafeMarkdown;
  window.copyMessage = copyMessage;
  window.shareMessage = shareMessage;
  window.downloadImage = downloadImage;
  window.openImageInNewTab = openImage;
})();
