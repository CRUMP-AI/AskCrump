(() => {
  'use strict';

  if (window.__crump52Loaded) return;
  window.__crump52Loaded = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const planCenterSources = new Set(['settings', 'plan_intent', 'upgrade_prompt']);
  const state = {
    menu: null,
    billing: null,
    renderHooked: false,
    legacyFileCache: new Map(),
    legacyFileLoading: new Set(),
    checkoutOpening: false,
  };

  function planCenterSource(options = {}) {
    if (['professional', 'enterprise'].includes(String(options?.plan || '').toLowerCase())) {
      return 'plan_intent';
    }
    const requested = String(options?.source || '').trim().toLowerCase();
    return planCenterSources.has(requested) ? requested : 'settings';
  }

  async function recordPlanCenterView(options = {}) {
    const source = planCenterSource(options);
    document.documentElement.dataset.crumpPlanCenterEvent = `pending:${source}`;
    try {
      if (await window.CrumpAnalytics?.track?.('PlanCenterViewed', {
        eventKey: 'plan-center-viewed',
        source,
      })) {
        document.documentElement.dataset.crumpPlanCenterEvent = `accepted:${source}`;
        return true;
      }
      const response = await fetch('/api/analytics/events', {
        method: 'POST',
        credentials: 'same-origin',
        keepalive: true,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          eventName: 'PlanCenterViewed',
          eventKey: 'plan-center-viewed',
          source,
        }),
      });
      document.documentElement.dataset.crumpPlanCenterEvent =
        `${response.ok ? 'accepted' : 'rejected'}:${source}`;
      return response.ok;
    } catch (_) {
      document.documentElement.dataset.crumpPlanCenterEvent = `failed:${source}`;
      return false;
    }
  }

  function cssEscape(value) {
    if (window.CSS?.escape) return window.CSS.escape(String(value));
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  function currentMessages() {
    const chat = (window.chats || []).find(item => (item.id || item.chat_id) === window.currentChatId);
    return Array.isArray(chat?.messages) ? chat.messages : [];
  }

  function fileUrl(file) {
    if (file?.id && /^[0-9a-f-]{36}$/i.test(String(file.id))) return `/api/files/${file.id}/content`;
    const raw = String(file?.url || '').trim();
    return raw.startsWith('/api/files/') ? raw : null;
  }

  function isImage(file) {
    return String(file?.type || '').toLowerCase().startsWith('image/');
  }

  function sizeLabel(value) {
    const bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
  }

  function shortType(file) {
    const name = String(file?.name || '');
    const match = name.match(/\.([A-Za-z0-9]{1,8})$/);
    if (match) return match[1].toUpperCase();
    const type = String(file?.type || 'File').split('/').pop() || 'File';
    return type.replace('vnd.openxmlformats-officedocument.', '').replace(/[^a-z0-9]+/gi, ' ').trim().toUpperCase().slice(0, 12) || 'FILE';
  }

  function openStoredFile(file) {
    const url = fileUrl(file);
    if (!url) {
      window.showToast?.('This older attachment no longer has an openable file reference.', 'warning');
      return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  function createImageAttachment(file) {
    const url = fileUrl(file);
    const figure = document.createElement('figure');
    figure.className = 'crump52-image-attachment';
    const image = document.createElement('img');
    image.alt = file?.name || 'Uploaded image';
    image.loading = 'lazy';
    if (url) image.src = url;
    else figure.classList.add('is-unavailable');
    image.addEventListener('click', () => openStoredFile(file));
    const caption = document.createElement('figcaption');
    const name = document.createElement('span');
    name.textContent = file?.name || 'Image';
    const meta = document.createElement('small');
    meta.textContent = [shortType(file), sizeLabel(file?.size)].filter(Boolean).join(' · ');
    caption.append(name, meta);
    figure.append(image, caption);
    return figure;
  }

  function createFileAttachment(file) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'crump52-file-attachment';
    button.disabled = !fileUrl(file);
    button.addEventListener('click', () => openStoredFile(file));

    const icon = document.createElement('span');
    icon.className = 'crump52-file-icon';
    icon.textContent = shortType(file).slice(0, 4);
    const text = document.createElement('span');
    text.className = 'crump52-file-copy';
    const name = document.createElement('strong');
    name.textContent = file?.name || 'Attachment';
    const meta = document.createElement('small');
    meta.textContent = [shortType(file), sizeLabel(file?.size)].filter(Boolean).join(' · ');
    text.append(name, meta);
    const arrow = document.createElement('span');
    arrow.className = 'crump52-file-arrow';
    arrow.textContent = fileUrl(file) ? '↗' : '';
    button.append(icon, text, arrow);
    return button;
  }


  function fileMatchKey(file) {
    return `${String(file?.name || '').trim().toLowerCase()}|${String(file?.type || '').trim().toLowerCase()}`;
  }

  async function hydrateLegacyFileRefs(messages = currentMessages()) {
    const chatId = String(window.currentChatId || '');
    if (!chatId || !Array.isArray(messages)) return;
    const missing = messages.some(message => Array.isArray(message?.files) && message.files.some(file => !file?.id));
    if (!missing || state.legacyFileLoading.has(chatId)) return;

    state.legacyFileLoading.add(chatId);
    try {
      let catalog = state.legacyFileCache.get(chatId);
      if (!catalog) {
        const response = await fetch(`/api/files/chat/${encodeURIComponent(chatId)}`, {credentials:'same-origin'});
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) return;
        catalog = Array.isArray(data.files) ? data.files : [];
        state.legacyFileCache.set(chatId, catalog);
      }

      const pools = new Map();
      for (const file of catalog) {
        const key = fileMatchKey(file);
        if (!pools.has(key)) pools.set(key, []);
        pools.get(key).push(file);
      }
      for (const message of messages) {
        if (!Array.isArray(message?.files)) continue;
        message.files = message.files.map(file => {
          if (file?.id) return file;
          const pool = pools.get(fileMatchKey(file)) || [];
          const match = pool.shift();
          return match ? {...file, ...match} : file;
        });
      }
      enhanceMessageAttachments(messages);
    } catch (_) {
      // Legacy recovery is best-effort. New 5.2 messages already retain IDs.
    } finally {
      state.legacyFileLoading.delete(chatId);
    }
  }

  function enhanceMessageAttachments(messages = currentMessages()) {
    for (const message of Array.isArray(messages) ? messages : []) {
      if (!message?.id || !Array.isArray(message.files) || !message.files.length) continue;
      const row = document.querySelector(`[data-message-id="${cssEscape(message.id)}"]`);
      if (!row) continue;
      const wrapper = $('.message-wrapper', row);
      if (!wrapper) continue;

      $('.crump52-rich-attachments', wrapper)?.remove();
      wrapper.querySelectorAll('.message-attachment, .crump50-message-files').forEach(node => node.remove());

      const host = document.createElement('div');
      host.className = 'crump52-rich-attachments';
      const images = message.files.filter(isImage);
      const documents = message.files.filter(file => !isImage(file));

      if (images.length) {
        const gallery = document.createElement('div');
        gallery.className = `crump52-image-gallery count-${Math.min(images.length, 4)}`;
        images.forEach(file => gallery.appendChild(createImageAttachment(file)));
        host.appendChild(gallery);
      }
      documents.forEach(file => host.appendChild(createFileAttachment(file)));

      const content = $('.message-content', wrapper);
      if (content?.nextSibling) wrapper.insertBefore(host, content.nextSibling);
      else wrapper.appendChild(host);
    }
    if ((Array.isArray(messages) ? messages : []).some(message => Array.isArray(message?.files) && message.files.some(file => !file?.id))) {
      hydrateLegacyFileRefs(messages);
    }
  }

  function hookRenderer() {
    if (state.renderHooked || typeof window.renderMessages !== 'function') return;
    state.renderHooked = true;
    const previous = window.renderMessages;
    window.renderMessages = function crump52RenderMessages(messages) {
      const result = previous.apply(this, arguments);
      requestAnimationFrame(() => enhanceMessageAttachments(messages));
      return result;
    };
    enhanceMessageAttachments(currentMessages());
  }


  function recentDocumentFile() {
    const messages = currentMessages();
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const files = Array.isArray(messages[index]?.files) ? messages[index].files : [];
      for (let fileIndex = files.length - 1; fileIndex >= 0; fileIndex -= 1) {
        const file = files[fileIndex];
        const type = String(file?.type || '').toLowerCase();
        if (!type.startsWith('image/')) return file;
      }
    }
    return null;
  }

  function inferredArtifactFormat(message) {
    const text = String(message || '').toLowerCase();
    if (!/\b(rewrite|revise|improve|update|edit|fix|polish|reformat|format|optimize|tailor)\b/.test(text)) return null;
    const file = recentDocumentFile();
    if (!file) return null;
    const name = String(file.name || '').toLowerCase();
    const type = String(file.type || '').toLowerCase();
    if (name.includes('resume') || /(^|[^a-z])cv([^a-z]|$)/.test(name)) return 'docx';
    if (type.includes('spreadsheet') || /\.xlsx?$/.test(name)) return 'xlsx';
    if (type.includes('presentation') || /\.pptx?$/.test(name)) return 'pptx';
    if (type === 'application/pdf' || /\.pdf$/.test(name)) return 'pdf';
    return 'docx';
  }

  function installRequestEnhancer() {
    if (window.fetch?.__crump52Enhanced) return;
    const previousFetch = window.fetch.bind(window);
    const enhanced = async function crump52Fetch(input, init = {}) {
      const rawUrl = typeof input === 'string' ? input : input?.url || '';
      const isChat = /(?:^|\/)api\/chat(?:$|\?)/.test(rawUrl) && !/\/ack(?:$|\?)/.test(rawUrl);
      if (!isChat || !init?.body || typeof init.body !== 'string') {
        return previousFetch(input, init);
      }
      try {
        const payload = JSON.parse(init.body);
        if (payload && typeof payload === 'object') {
          if (!payload.creativeTool && document.documentElement.dataset.crump52CreativeTool === 'image') {
            payload.creativeTool = 'image';
            delete document.documentElement.dataset.crump52CreativeTool;
          }
          if (!payload.artifactFormat) {
            const inferred = inferredArtifactFormat(payload.message);
            if (inferred) payload.artifactFormat = inferred;
          }
          init = { ...init, body: JSON.stringify(payload) };
        }
      } catch (_) {}
      return previousFetch(input, init);
    };
    enhanced.__crump52Enhanced = true;
    window.fetch = enhanced;
  }

  function closeAttachMenu() {
    state.menu?.remove();
    state.menu = null;
  }

  function launchExistingPicker(accept, { multiple = true, capture = null } = {}) {
    closeAttachMenu();
    const input = $('#fileInput');
    if (!input) {
      window.showToast?.('The attachment picker is still loading.', 'warning');
      return;
    }
    input.accept = accept;
    input.multiple = multiple;
    if (capture) input.setAttribute('capture', capture);
    else input.removeAttribute('capture');
    // Closing the Crump sheet before invoking the browser picker prevents the
    // two interfaces from visually stacking on iOS Safari.
    requestAnimationFrame(() => setTimeout(() => input.click(), 40));
  }

  function attachChoice(icon, title, detail, handler) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'crump52-attach-choice';
    const glyph = document.createElement('span');
    glyph.className = 'crump52-choice-icon';
    glyph.textContent = icon;
    const copy = document.createElement('span');
    const strong = document.createElement('strong');
    strong.textContent = title;
    const small = document.createElement('small');
    small.textContent = detail;
    copy.append(strong, small);
    const arrow = document.createElement('b');
    arrow.textContent = '›';
    button.append(glyph, copy, arrow);
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      handler();
    });
    return button;
  }

  function showAttachMenu52(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    closeAttachMenu();

    const overlay = document.createElement('div');
    overlay.className = 'crump52-attach-overlay';
    overlay.innerHTML = `
      <div class="crump52-attach-backdrop" data-close></div>
      <section class="crump52-attach-sheet" role="dialog" aria-modal="true" aria-labelledby="crump52AttachTitle">
        <div class="crump52-attach-handle"></div>
        <header><div><span>ADD TO CRUMP</span><h2 id="crump52AttachTitle">What do you want to add?</h2></div><button type="button" data-close aria-label="Close">×</button></header>
        <div class="crump52-attach-list" id="crump52AttachList"></div>
      </section>`;
    overlay.querySelectorAll('[data-close]').forEach(node => node.addEventListener('click', closeAttachMenu));
    overlay.addEventListener('click', event => event.stopPropagation());

    const list = $('#crump52AttachList', overlay);
    list.append(
      attachChoice('▧', 'Photos', 'Choose one or more images', () => launchExistingPicker('image/*', { multiple: true })),
      attachChoice('▤', 'Files', 'PDF, Word, PowerPoint, spreadsheets, text', () => launchExistingPicker('.pdf,.docx,.pptx,.xlsx,.txt,.md,.csv,.tsv,.json,.rtf', { multiple: true })),
      attachChoice('◉', 'Camera', 'Take a new photo', () => launchExistingPicker('image/*', { multiple: false, capture: 'environment' })),
      attachChoice('✦', 'Create image', 'Generate or edit an image with Crump', () => {
        closeAttachMenu();
        const input = $('#userInput');
        if (input) {
          input.placeholder = 'Describe the image you want Crump to create…';
          input.focus();
          document.documentElement.dataset.crump52CreativeTool = 'image';
        }
        window.showToast?.('Image creation mode ready', 'info');
      }),
      attachChoice('▥', 'Create document', 'DOCX, PDF, slides, spreadsheet, text', () => {
        closeAttachMenu();
        const input = $('#userInput');
        if (input) {
          input.placeholder = 'Describe the document you want Crump to create…';
          input.focus();
        }
        window.showToast?.('Tell Crump what document you want and name the format.', 'info');
      })
    );

    document.body.appendChild(overlay);
    state.menu = overlay;
    requestAnimationFrame(() => overlay.classList.add('is-visible'));
  }

  function ownAttachButton() {
    const current = $('#attachBtn');
    if (!current || current.dataset.crump52 === 'true') return;
    const button = current.cloneNode(true);
    button.id = 'attachBtn';
    button.dataset.crump52 = 'true';
    button.setAttribute('aria-label', 'Add to conversation');
    current.replaceWith(button);
    button.addEventListener('click', showAttachMenu52, { capture: true });
  }

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers: {
        ...(options.body ? {'Content-Type': 'application/json'} : {}),
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
      const error = new Error(data.error || 'That billing request could not be completed.');
      error.code = data.code;
      throw error;
    }
    return data;
  }

  function closeBilling52() {
    state.billing?.remove();
    state.billing = null;
    document.body.classList.remove('billing51-open');
  }

  async function openCreditCheckout(packCode, trigger) {
    if (!packCode || state.checkoutOpening) return;
    state.checkoutOpening = true;
    const button = trigger?.closest?.('.billing51-buy') || trigger;
    const prior = button?.textContent || 'Add credits';
    if (button) {
      button.disabled = true;
      button.textContent = 'Opening checkout…';
    }
    try {
      const result = await jsonFetch('/api/billing/credits/checkout', {
        method: 'POST',
        body: JSON.stringify({pack: packCode}),
      });
      if (!result.url) throw new Error('Stripe did not return a checkout destination.');
      window.location.href = result.url;
    } catch (error) {
      state.checkoutOpening = false;
      if (button) {
        button.disabled = false;
        button.textContent = prior;
      }
      window.showToast?.(error.message || 'Could not open secure checkout.', 'error');
    }
  }

  function creditPackCard(pack) {
    const article = document.createElement('article');
    article.className = `billing51-pack ${Number(pack.credits) === 150 ? 'is-featured' : ''}`;
    article.dataset.crumpPack = String(pack.code || '');
    article.tabIndex = pack.available === false ? -1 : 0;
    if (pack.available !== false) article.setAttribute('role', 'button');
    if (Number(pack.credits) === 150) {
      const badge = document.createElement('span');
      badge.className = 'billing51-badge';
      badge.textContent = 'Popular';
      article.appendChild(badge);
    }
    const amount = document.createElement('strong');
    amount.className = 'billing51-pack-amount';
    amount.textContent = String(pack.credits);
    const label = document.createElement('span');
    label.className = 'billing51-pack-label';
    label.textContent = 'Crump Credits';
    const price = document.createElement('div');
    price.className = 'billing51-pack-price';
    price.textContent = pack.price;
    const buy = document.createElement('button');
    buy.type = 'button';
    buy.className = 'billing51-buy';
    buy.dataset.crumpPack = String(pack.code || '');
    buy.disabled = pack.available === false;
    buy.textContent = pack.available === false ? 'Not configured' : 'Add credits';
    article.append(amount, label, price, buy);
    return article;
  }

  function renderBillingHistory(host, history = []) {
    host.replaceChildren();
    const visible = Array.isArray(history) ? history.slice(0, 8) : [];
    if (!visible.length) {
      const p = document.createElement('p');
      p.className = 'billing51-empty';
      p.textContent = 'No credit activity yet.';
      host.appendChild(p);
      return;
    }
    visible.forEach(item => {
      const row = document.createElement('div');
      row.className = 'billing51-history-row';
      const label = document.createElement('span');
      const delta = Number(item?.delta || 0);
      const reason = String(item?.reason || '');
      label.textContent = reason === 'beta_qa_grant' ? 'Founder QA credits'
        : reason === 'credit_purchase' ? 'Credit purchase'
        : reason === 'refund' ? 'Returned credit'
        : delta < 0 ? 'Crump request' : 'Credit adjustment';
      const amount = document.createElement('strong');
      amount.textContent = `${delta > 0 ? '+' : ''}${delta}`;
      if (delta > 0) amount.className = 'is-positive';
      row.append(label, amount);
      host.appendChild(row);
    });
  }

  function renderAllowance(host, daily = {}) {
    const limit = Number(daily?.limit ?? 0);
    const used = Number(daily?.used ?? 0);
    const remaining = limit < 0 ? 'Unlimited' : `${Math.max(0, Number(daily?.remaining ?? Math.max(0, limit - used)))} left`;
    const percent = limit < 0 ? 100 : limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 100;
    host.innerHTML = `<div class="billing51-allowance"><div><span>Included today</span><strong>${remaining}</strong></div><div class="billing51-progress"><i style="width:${percent}%"></i></div></div>`;
  }

  async function hydrateBilling52(modal) {
    const balance = $('#billing52Balance', modal);
    const packs = $('#billing52Packs', modal);
    const allowance = $('#billing52Allowance', modal);
    const history = $('#billing52History', modal);
    try {
      const [creditData, usageData] = await Promise.all([
        jsonFetch('/api/billing/credits/status'),
        jsonFetch('/api/usage/check').catch(() => ({daily:{limit:0,used:0,remaining:0}})),
      ]);
      if (!modal.isConnected || state.billing !== modal) return;
      if (balance) balance.textContent = String(Math.max(0, Number(creditData.credits?.balance || 0)));
      if (allowance) renderAllowance(allowance, usageData.daily || {});
      if (packs) {
        packs.replaceChildren();
        const catalog = Array.isArray(creditData.catalog) && creditData.catalog.length
          ? creditData.catalog
          : [
              {code:'credits_50', credits:50, price:'$4.99', available:false},
              {code:'credits_150', credits:150, price:'$9.99', available:false},
              {code:'credits_400', credits:400, price:'$19.99', available:false},
            ];
        catalog.forEach(pack => packs.appendChild(creditPackCard(pack)));
      }
      if (history) renderBillingHistory(history, creditData.history || []);
      const sidebarBadge = document.querySelector('#upgradeBtnSidebar .billing51-sidebar-balance');
      if (sidebarBadge) sidebarBadge.textContent = `${Math.max(0, Number(creditData.credits?.balance || 0))} C`;
    } catch (error) {
      if (!modal.isConnected || state.billing !== modal) return;
      window.showToast?.(error.message || 'Billing information could not be loaded.', 'error');
      if (packs) {
        packs.replaceChildren();
        const message = document.createElement('p');
        message.className = 'billing51-empty crump52-billing-error';
        message.textContent = 'Credit packs could not be loaded. Close this panel and try again.';
        packs.appendChild(message);
      }
    }
  }

  function showBillingCenter52(options = {}) {
    closeBilling52();
    const modal = document.createElement('div');
    modal.className = 'billing51-modal is-visible crump52-billing-modal';
    modal.innerHTML = `
      <div class="billing51-backdrop" data-close></div>
      <section class="billing51-sheet" role="dialog" aria-modal="true" aria-labelledby="billing52Title">
        <header class="billing51-header">
          <div class="billing51-brand"><span class="billing51-mark">C</span><div><span>ASK CRUMP</span><h2 id="billing52Title">Plan & credits</h2></div></div>
          <button type="button" class="billing51-close" data-close aria-label="Close">×</button>
        </header>
        <div class="billing51-balance-card">
          <div><span>YOUR BALANCE</span><strong><b id="billing52Balance">…</b> <small>credits</small></strong><p>Credits take over only after your included allowance runs out.</p></div>
          <div id="billing52Allowance"><div class="billing51-allowance"><div><span>Included today</span><strong>Loading…</strong></div><div class="billing51-progress"><i style="width:25%"></i></div></div></div>
        </div>
        <section class="billing51-section">
          <div class="billing51-section-head"><div><span>KEEP GOING</span><h3>Add Crump Credits</h3></div><p>1 request = 1 credit after included usage. Purchased credits never expire.</p></div>
          <div class="billing51-packs" id="billing52Packs">
            ${[50,150,400].map((credits, index) => `<article class="billing51-pack ${credits === 150 ? 'is-featured' : ''}">${credits === 150 ? '<span class="billing51-badge">Popular</span>' : ''}<strong class="billing51-pack-amount">${credits}</strong><span class="billing51-pack-label">Crump Credits</span><div class="billing51-pack-price">${['$4.99','$9.99','$19.99'][index]}</div><button class="billing51-buy" disabled>Loading…</button></article>`).join('')}
          </div>
        </section>
        <section class="billing51-section">
          <div class="billing51-section-head"><div><span>MONTHLY ACCESS</span><h3>Subscriptions</h3></div><p>Choose monthly access for more included usage. You can manage or cancel a web subscription at any time.</p></div>
          <div class="billing51-plans">
            <article class="billing51-plan is-featured" data-crump-plan="professional">
              <div class="billing51-plan-top"><strong>Professional</strong><span>$20/month</span></div>
              <p class="billing51-plan-summary">For independent work you return to every day.</p>
              <ul class="billing51-plan-benefits"><li>500 included messages daily</li><li>25 private Projects</li><li>20 research · 1 image · 20 visual analyses daily</li><li>Think Longer and premium creation access</li></ul>
              <p class="billing51-plan-meter-note">Premium video and other high-compute generations use Crump Credits.</p>
              <button class="billing51-plan-button" disabled>Loading plan…</button>
            </article>
            <article class="billing51-plan" data-crump-plan="enterprise">
              <div class="billing51-plan-top"><strong>Enterprise</strong><span>$50/month</span></div>
              <p class="billing51-plan-summary">For sustained, high-capacity individual or organization workflows.</p>
              <ul class="billing51-plan-benefits"><li>5,000 included messages daily</li><li>200 private Projects</li><li>50 research · 2 images · 100 visual analyses daily</li><li>10-second Cinematic video access</li></ul>
              <p class="billing51-plan-meter-note">Premium video and other high-compute generations use Crump Credits.</p>
              <button class="billing51-plan-button" disabled>Loading plan…</button>
            </article>
          </div>
        </section>
        <section class="billing51-section billing51-history-section">
          <div class="billing51-section-head"><div><span>LEDGER</span><h3>Recent credit activity</h3></div><p>Every addition, request, and refund is recorded server-side.</p></div>
          <div id="billing52History"><p class="billing51-empty">Loading activity…</p></div>
        </section>
        <footer class="billing51-footer"><div class="billing51-footer-actions"><span>Secure web payments are processed by Stripe.</span></div><p>Credits have no cash value and do not expire. Store purchases use the payment system required by your device. <a href="/legal.html#terms">Terms</a> · <a href="/legal.html#privacy">Privacy</a></p></footer>
      </section>`;
    modal.querySelectorAll('[data-close]').forEach(node => node.addEventListener('click', closeBilling52));
    document.body.appendChild(modal);
    state.billing = modal;
    document.body.classList.add('billing51-open');
    void recordPlanCenterView(options);

    // One capture-phase handler owns checkout for both the explicit button and
    // the full credit card. This survives re-renders and is reliable on iOS
    // Safari even when child buttons are replaced during hydration.
    modal.addEventListener('click', event => {
      const packTarget = event.target.closest?.('[data-crump-pack]');
      if (!packTarget || !modal.contains(packTarget)) return;
      const card = packTarget.closest('.billing51-pack');
      const button = card?.querySelector('.billing51-buy');
      if (!card || button?.disabled) return;
      event.preventDefault();
      event.stopPropagation();
      openCreditCheckout(card.dataset.crumpPack || packTarget.dataset.crumpPack, button);
    }, {capture: true});
    modal.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const card = event.target.closest?.('.billing51-pack[data-crump-pack]');
      if (!card) return;
      event.preventDefault();
      const button = card.querySelector('.billing51-buy');
      if (!button?.disabled) openCreditCheckout(card.dataset.crumpPack, button);
    });
    hydrateBilling52(modal);
    return modal;
  }

  function ownBillingButton() {
    window.showBillingCenter = showBillingCenter52;
    window.showUpgradePrompt = options => showBillingCenter52({
      ...(options && typeof options === 'object' ? options : {}),
      source: 'upgrade_prompt',
    });
    const current = $('#upgradeBtnSidebar');
    if (!current || current.dataset.crump52Billing === 'true') return;
    const button = current.cloneNode(true);
    button.id = 'upgradeBtnSidebar';
    button.dataset.crump52Billing = 'true';
    current.replaceWith(button);
    button.addEventListener('click', () => showBillingCenter52({source: 'settings'}));
  }

  function boot() {
    installRequestEnhancer();
    hookRenderer();
    ownAttachButton();
    ownBillingButton();

    const observer = new MutationObserver(() => {
      hookRenderer();
      ownAttachButton();
      ownBillingButton();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    // 5.0 performs one delayed legacy-control replacement. Reassert ownership
    // afterward, then stop actively polling; the MutationObserver handles later UI changes.
    setTimeout(() => { ownAttachButton(); ownBillingButton(); enhanceMessageAttachments(); }, 1200);
    setTimeout(() => { ownAttachButton(); ownBillingButton(); enhanceMessageAttachments(); }, 2200);
  }

  if (document.readyState === 'complete') setTimeout(boot, 900);
  else window.addEventListener('load', () => setTimeout(boot, 900), {once: true});
})();
