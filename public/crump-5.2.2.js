(() => {
  'use strict';

  if (window.__crump522Loaded) return;
  window.__crump522Loaded = true;

  const PACK_CODES = new Set(['credits_50', 'credits_150', 'credits_400']);
  const BILLING_REQUEST_TIMEOUT_MS = 15_000;
  const state = {
    checkoutOpening: false,
    lastPointerCheckoutAt: 0,
    scroll: {
      installed: false,
      chatId: null,
      lastCompletedAssistantId: null,
      newResponsePending: false,
      renderHooked: false,
      button: null,
      container: null,
      status: null,
    },
  };

  const asElement = value => value instanceof Element ? value : value?.parentElement || null;

  function show(message, tone = 'info') {
    window.showToast?.(message, tone);
  }

  async function jsonFetch(url, options = {}) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), BILLING_REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        ...options,
        signal: controller.signal,
        headers: {
          ...(options.body ? {'Content-Type': 'application/json'} : {}),
          ...(options.headers || {}),
        },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) {
        throw new Error(data.error || data.message || `Checkout could not start (${response.status}).`);
      }
      return data;
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error('Billing took too long. Check your connection and try again.');
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  function normalizeBillingCards(root = document) {
    root.querySelectorAll?.('.billing51-pack[data-crump-pack]').forEach(card => {
      const code = String(card.dataset.crumpPack || '');
      if (!PACK_CODES.has(code)) return;
      card.removeAttribute('tabindex');
      card.removeAttribute('role');
      card.removeAttribute('aria-disabled');
      const button = card.querySelector('.billing51-buy');
      if (button && !state.checkoutOpening) {
        const credits = String(card.querySelector('.billing51-pack-amount')?.textContent || '').trim();
        const price = String(card.querySelector('.billing51-pack-price')?.textContent || '').trim();
        const accessibleLabel = `Add ${credits} Crump Credits${price ? ` for ${price}` : ''}`;
        button.disabled = false;
        button.removeAttribute('aria-disabled');
        if (!button.dataset.crump522Label) button.dataset.crump522Label = 'Add credits';
        button.dataset.crump522AriaLabel = accessibleLabel;
        button.setAttribute('aria-label', accessibleLabel);
        if (/not configured/i.test(button.textContent || '')) button.textContent = 'Add credits';
      }
    });
  }

  function billingActivationTarget(event) {
    const target = asElement(event.target);
    if (!target) return null;
    const packNode = target.closest('.billing51-pack[data-crump-pack], .billing51-buy[data-crump-pack]');
    if (!packNode) return null;
    const modal = packNode.closest('.billing51-modal');
    if (!modal) return null;
    const card = packNode.matches('.billing51-pack') ? packNode : packNode.closest('.billing51-pack');
    const code = String(card?.dataset.crumpPack || packNode.dataset.crumpPack || '');
    if (!card || !PACK_CODES.has(code)) return null;
    return { card, code, button: card.querySelector('.billing51-buy') };
  }

  async function openCheckout(code, card, button) {
    if (state.checkoutOpening) return;
    state.checkoutOpening = true;

    const original = button?.textContent || 'Add credits';
    const originalAccessibleLabel = button?.getAttribute?.('aria-label') || original;
    card?.setAttribute('aria-busy', 'true');
    if (button) {
      button.disabled = true;
      button.textContent = 'Opening checkout…';
      button.setAttribute('aria-label', `Opening secure checkout. ${originalAccessibleLabel}`);
    }

    try {
      const data = await jsonFetch('/api/billing/credits/checkout', {
        method: 'POST',
        body: JSON.stringify({pack: code}),
      });
      const url = String(data.url || '');
      if (!/^https:\/\/checkout\.stripe\.com\//i.test(url)) {
        throw new Error('Stripe did not return a secure checkout destination.');
      }
      window.location.assign(url);
    } catch (error) {
      state.checkoutOpening = false;
      card?.removeAttribute('aria-busy');
      if (button) {
        button.disabled = false;
        button.textContent = original === 'Opening checkout…' ? 'Add credits' : original;
        button.setAttribute('aria-label', originalAccessibleLabel);
      }
      show(error?.message || 'Could not open secure checkout.', 'error');
    }
  }

  function activateBilling(event) {
    const activation = billingActivationTarget(event);
    if (!activation) return;

    if (event.type === 'pointerup') {
      if (event.pointerType === 'mouse') return;
      state.lastPointerCheckoutAt = Date.now();
    } else if (event.type === 'click' && Date.now() - state.lastPointerCheckoutAt < 700) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    openCheckout(activation.code, activation.card, activation.button);
  }

  function activateBillingKeyboard(event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    if (!asElement(event.target)?.closest('.billing51-buy[data-crump-pack]')) return;
    const activation = billingActivationTarget(event);
    if (!activation) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openCheckout(activation.code, activation.card, activation.button);
  }

  function installBillingContract() {
    normalizeBillingCards();
    document.addEventListener('pointerup', activateBilling, true);
    document.addEventListener('click', activateBilling, true);
    document.addEventListener('keydown', activateBillingKeyboard, true);

    const observer = new MutationObserver(mutations => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches?.('.billing51-modal, .billing51-pack') || node.querySelector?.('.billing51-pack')) {
            normalizeBillingCards(node.matches?.('.billing51-pack') ? node.parentElement || document : node);
          }
        }
      }
    });
    observer.observe(document.body, {childList: true, subtree: true});
  }

  function distanceFromBottom() {
    const container = state.scroll.container;
    if (!container) return 0;
    return Math.max(0, container.scrollHeight - container.scrollTop - container.clientHeight);
  }

  function currentMessages() {
    const chat = (window.chats || []).find(item => (item.id || item.chat_id) === window.currentChatId);
    return Array.isArray(chat?.messages) ? chat.messages : [];
  }

  function latestCompletedAssistantId(messages = currentMessages()) {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const item = messages[index];
      const hasOutcome = String(item?.content || '').trim() || item?.imageUrl || item?.artifact || item?.creationHandoff;
      if (item?.role === 'assistant' && item?.id && hasOutcome) return String(item.id);
    }
    return null;
  }

  function ensureNewResponseStatus() {
    const existing = document.getElementById('crump522NewResponseStatus');
    if (existing) return existing;
    const status = document.createElement('div');
    status.id = 'crump522NewResponseStatus';
    status.className = 'sr-only';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.setAttribute('aria-atomic', 'true');
    state.scroll.button?.insertAdjacentElement('afterend', status);
    return status;
  }

  function clearNewResponse() {
    state.scroll.newResponsePending = false;
    state.scroll.button?.removeAttribute('data-new-response');
    state.scroll.button?.setAttribute('aria-label', 'Jump to newest message');
    if (state.scroll.status) state.scroll.status.textContent = '';
  }

  function markNewResponse() {
    if (distanceFromBottom() <= 12) return;
    state.scroll.newResponsePending = true;
    state.scroll.button?.setAttribute('data-new-response', 'true');
    state.scroll.button?.setAttribute('aria-label', 'New response available. Jump to newest message');
    if (state.scroll.status) {
      state.scroll.status.textContent = 'New response available. Use Jump to newest message when you are ready.';
    }
  }

  function updateDownButton() {
    const button = state.scroll.button;
    if (!button) return;
    const distance = distanceFromBottom();
    if (distance <= 12 && state.scroll.newResponsePending) clearNewResponse();
    const visible = distance > 160 || (state.scroll.newResponsePending && distance > 12);
    button.classList.toggle('visible', visible);
    button.setAttribute('aria-hidden', visible ? 'false' : 'true');
  }

  function jumpToNewest() {
    const container = state.scroll.container;
    if (!container) return;
    clearNewResponse();
    container.scrollTo({top: container.scrollHeight, behavior: 'smooth'});
    updateDownButton();
  }

  function replaceDownButton() {
    const current = document.getElementById('scrollToEndBtn');
    if (!current) return null;
    if (current.dataset.crump522 === 'true') return current;

    const button = current.cloneNode(true);
    button.id = 'scrollToEndBtn';
    button.dataset.crump522 = 'true';
    button.setAttribute('aria-label', 'Jump to newest message');
    current.replaceWith(button);
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      jumpToNewest();
    });
    return button;
  }

  function replaceScrollManager() {
    const previous = window.crumpScrollManager || {};
    window.crumpScrollManager = {
      ...previous,
      init: () => undefined,
      scrollToBottom: () => undefined,
      autoScrollToBottom: () => undefined,
      scrollToMessageTop: () => undefined,
      isNearBottom: () => distanceFromBottom() < 100,
      setUserScrolling: () => updateDownButton(),
    };
  }

  function hookRenderMessages() {
    if (state.scroll.renderHooked || typeof window.renderMessages !== 'function') return;
    state.scroll.renderHooked = true;

    const previous = window.renderMessages;
    state.scroll.chatId = String(window.currentChatId || '');
    state.scroll.lastCompletedAssistantId = latestCompletedAssistantId();
    window.renderMessages = function crump522RenderMessages(messages) {
      const container = state.scroll.container;
      const preservedScrollTop = container?.scrollTop ?? 0;
      const chatId = String(window.currentChatId || '');
      const nextAssistantId = latestCompletedAssistantId(Array.isArray(messages) ? messages : []);
      let hasNewResponse = false;
      if (chatId !== state.scroll.chatId) {
        state.scroll.chatId = chatId;
        state.scroll.lastCompletedAssistantId = nextAssistantId;
        clearNewResponse();
      } else if (nextAssistantId && nextAssistantId !== state.scroll.lastCompletedAssistantId) {
        state.scroll.lastCompletedAssistantId = nextAssistantId;
        hasNewResponse = true;
      }
      const result = previous.apply(this, arguments);
      if (container && container.scrollTop !== preservedScrollTop) container.scrollTop = preservedScrollTop;
      if (hasNewResponse) markNewResponse();
      requestAnimationFrame(updateDownButton);
      return result;
    };
  }

  function installScrollContract() {
    const container = document.getElementById('chatContainer');
    if (!container) return;

    state.scroll.container = container;
    state.scroll.button = replaceDownButton();
    state.scroll.status = ensureNewResponseStatus();

    container.addEventListener('scroll', updateDownButton, {passive: true});

    replaceScrollManager();
    hookRenderMessages();
    updateDownButton();
    state.scroll.installed = true;
  }

  function boot() {
    installBillingContract();
    installScrollContract();

    const observer = new MutationObserver(() => {
      normalizeBillingCards();
      if (!document.getElementById('scrollToEndBtn')?.dataset.crump522) {
        state.scroll.button = replaceDownButton();
        state.scroll.status = ensureNewResponseStatus();
        updateDownButton();
      }
      hookRenderMessages();
      replaceScrollManager();
    });
    observer.observe(document.body, {childList: true, subtree: true});
  }

  if (document.readyState === 'complete') setTimeout(boot, 700);
  else window.addEventListener('load', () => setTimeout(boot, 700), {once: true});
})();
