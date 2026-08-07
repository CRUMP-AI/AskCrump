(() => {
  'use strict';

  if (window.__crump522Loaded) return;
  window.__crump522Loaded = true;

  const PACK_CODES = new Set(['credits_50', 'credits_150', 'credits_400']);
  const state = {
    checkoutOpening: false,
    lastPointerCheckoutAt: 0,
    scroll: {
      installed: false,
      chatId: null,
      lastAssistantId: null,
      suppressLegacyBottomUntil: 0,
      lastUserIntentAt: 0,
      renderHooked: false,
      button: null,
      container: null,
    },
  };

  const asElement = value => value instanceof Element ? value : value?.parentElement || null;

  function show(message, tone = 'info') {
    window.showToast?.(message, tone);
  }

  function normalizeBillingCards(root = document) {
    root.querySelectorAll?.('.billing51-pack[data-crump-pack]').forEach(card => {
      const code = String(card.dataset.crumpPack || '');
      if (!PACK_CODES.has(code)) return;
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      card.removeAttribute('aria-disabled');
      const button = card.querySelector('.billing51-buy');
      if (button && !state.checkoutOpening) {
        button.disabled = false;
        button.removeAttribute('aria-disabled');
        if (!button.dataset.crump522Label) button.dataset.crump522Label = 'Add credits';
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
    card?.setAttribute('aria-busy', 'true');
    if (button) {
      button.disabled = true;
      button.textContent = 'Opening checkout…';
    }

    try {
      const response = await fetch('/api/billing/credits/checkout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pack: code}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) {
        throw new Error(data.error || data.message || `Checkout could not start (${response.status}).`);
      }
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

  function currentMessages() {
    const chat = (window.chats || []).find(item => (item.id || item.chat_id) === window.currentChatId);
    return Array.isArray(chat?.messages) ? chat.messages : [];
  }

  function latestAssistantId(messages = currentMessages()) {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const item = messages[index];
      if (item?.role === 'assistant' && item?.id) return String(item.id);
    }
    return null;
  }

  function distanceFromBottom() {
    const container = state.scroll.container;
    if (!container) return 0;
    return Math.max(0, container.scrollHeight - container.scrollTop - container.clientHeight);
  }

  function updateDownButton() {
    const button = state.scroll.button;
    if (!button) return;
    const visible = distanceFromBottom() > 160;
    button.classList.toggle('visible', visible);
    button.setAttribute('aria-hidden', visible ? 'false' : 'true');
  }

  function scrollBottom({force = false} = {}) {
    const container = state.scroll.container;
    if (!container) return;
    if (!force && Date.now() < state.scroll.suppressLegacyBottomUntil) return;
    container.scrollTo({top: container.scrollHeight, behavior: 'auto'});
    updateDownButton();
  }

  function rowForMessage(messageId) {
    if (!messageId) return null;
    const escape = window.CSS?.escape ? window.CSS.escape(String(messageId)) : String(messageId).replace(/"/g, '\\"');
    return document.querySelector(`[data-message-id="${escape}"]`);
  }

  function anchorElementTop(element) {
    const container = state.scroll.container;
    if (!container || !element) return;
    const containerRect = container.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    const target = Math.max(0, container.scrollTop + elementRect.top - containerRect.top - 14);
    container.scrollTo({top: target, behavior: 'auto'});
    updateDownButton();
  }

  function anchorNewReply(messageId) {
    const container = state.scroll.container;
    if (!container) return;

    const recentlyInteracting = Date.now() - state.scroll.lastUserIntentAt < 2500;
    if (recentlyInteracting && distanceFromBottom() > 420) {
      updateDownButton();
      return;
    }

    state.scroll.suppressLegacyBottomUntil = Date.now() + 3200;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const row = rowForMessage(messageId);
        if (row) anchorElementTop(row);
      });
    });
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
      scrollBottom({force: true});
    });
    return button;
  }

  function replaceScrollManager() {
    const previous = window.crumpScrollManager || {};
    window.crumpScrollManager = {
      ...previous,
      init: () => undefined,
      scrollToBottom: value => {
        const force = Boolean(value && typeof value === 'object' && value.force === true);
        scrollBottom({force});
      },
      autoScrollToBottom: () => {
        if (Date.now() >= state.scroll.suppressLegacyBottomUntil && distanceFromBottom() < 90) {
          scrollBottom();
        }
      },
      scrollToMessageTop: element => {
        state.scroll.suppressLegacyBottomUntil = Date.now() + 2200;
        anchorElementTop(element);
      },
      isNearBottom: () => distanceFromBottom() < 100,
      setUserScrolling: value => {
        if (value) state.scroll.lastUserIntentAt = Date.now();
      },
    };
  }

  function hookRenderMessages() {
    if (state.scroll.renderHooked || typeof window.renderMessages !== 'function') return;
    state.scroll.renderHooked = true;

    const previous = window.renderMessages;
    state.scroll.chatId = String(window.currentChatId || '');
    state.scroll.lastAssistantId = latestAssistantId();

    window.renderMessages = function crump522RenderMessages(messages) {
      const chatId = String(window.currentChatId || '');
      const nextAssistantId = latestAssistantId(Array.isArray(messages) ? messages : []);

      let shouldAnchor = false;
      if (chatId !== state.scroll.chatId) {
        state.scroll.chatId = chatId;
        state.scroll.lastAssistantId = nextAssistantId;
      } else if (nextAssistantId && nextAssistantId !== state.scroll.lastAssistantId) {
        shouldAnchor = true;
        state.scroll.lastAssistantId = nextAssistantId;
        state.scroll.suppressLegacyBottomUntil = Date.now() + 3200;
      }

      const result = previous.apply(this, arguments);
      if (shouldAnchor) anchorNewReply(nextAssistantId);
      requestAnimationFrame(updateDownButton);
      return result;
    };
  }

  function installScrollContract() {
    const container = document.getElementById('chatContainer');
    if (!container) return;

    state.scroll.container = container;
    state.scroll.button = replaceDownButton();

    const noteUserIntent = () => { state.scroll.lastUserIntentAt = Date.now(); };
    container.addEventListener('wheel', noteUserIntent, {passive: true});
    container.addEventListener('touchstart', noteUserIntent, {passive: true});
    container.addEventListener('pointerdown', noteUserIntent, {passive: true});
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
