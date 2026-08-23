(() => {
  'use strict';

  if (window.__crumpV1Loaded) return;
  window.__crumpV1Loaded = true;

  const BRAND = Object.freeze({
    mark: '/assets/brand/crump-mark.png',
    horizontalLight: '/assets/brand/crump-horizontal-light.png',
    horizontalDark: '/assets/brand/crump-horizontal-dark.png',
  });

  function image(src, className, alt = 'Ask Crump') {
    const node = document.createElement('img');
    node.src = src;
    node.alt = alt;
    node.className = className;
    node.decoding = 'async';
    return node;
  }

  function brandHeader() {
    const host = document.querySelector('.header-branding');
    if (!host) return;

    const current = host.querySelector(':scope > .crump-v1-header-logo');
    if (current && host.children.length === 1) return;

    host.replaceChildren(image(BRAND.horizontalLight, 'crump-v1-header-logo'));
  }

  function brandSidebar() {
    const host = document.querySelector('.sidebar-branding');
    if (!host) return;

    const current = host.querySelector(':scope > .crump-v1-sidebar-logo');
    if (current && host.children.length === 1) return;

    host.replaceChildren(image(BRAND.horizontalLight, 'crump-v1-sidebar-logo'));
  }

  function brandAuth() {
    document.querySelectorAll('.auth-logo').forEach(node => {
      if (!(node instanceof HTMLImageElement)) return;
      node.src = BRAND.horizontalLight;
      node.alt = 'Ask Crump';
      node.classList.add('crump-v1-auth-logo');
      node.removeAttribute('width');
      node.removeAttribute('height');
    });

    document.querySelectorAll('.onboarding-logo').forEach(node => {
      if (!(node instanceof HTMLImageElement)) return;
      node.src = BRAND.horizontalLight;
      node.alt = 'Ask Crump';
      node.classList.add('crump-v1-onboarding-logo');
      node.removeAttribute('width');
      node.removeAttribute('height');
    });
  }

  function refineEmptyState(root = document) {
    root.querySelectorAll?.('.crump-empty-state').forEach(section => {
      const mark = section.querySelector('.crump-empty-mark');
      if (mark) {
        const existing = mark.querySelector('.crump-v1-empty-logo');
        if (!existing) {
          mark.replaceChildren(image(BRAND.mark, 'crump-v1-empty-logo', ''));
          mark.setAttribute('aria-hidden', 'true');
        }
      }

      const eyebrow = section.querySelector('.crump-empty-eyebrow');
      if (eyebrow) {
        eyebrow.hidden = true;
        eyebrow.setAttribute('aria-hidden', 'true');
      }

      const title = section.querySelector('h1');
      if (title && title.dataset.crumpV1 !== 'true') {
        title.textContent = 'What are we working on?';
        title.dataset.crumpV1 = 'true';
      }

      const description = section.querySelector(':scope > p');
      if (description && description.dataset.crumpV1 !== 'true') {
        description.textContent = 'Bring a question, a file, a half-formed idea, or something you want to build.';
        description.dataset.crumpV1 = 'true';
      }
    });
  }

  function refineNavigationCopy() {
    const plan = document.getElementById('upgradeBtnSidebar');
    const label = plan?.querySelector('span');
    if (label) label.textContent = 'Plan & credits';

    const input = document.getElementById('userInput');
    if (input) {
      const assistantName = window.getAssistantName?.() || 'Crump';
      input.placeholder = `Message ${assistantName}`;
      input.setAttribute('aria-label', `Message ${assistantName}`);
    }

    document.getElementById('crumpIntelligenceButton')
      ?.setAttribute('aria-label', `${window.getAssistantName?.() || 'Crump'} controls`);
  }

  function installChatObserver() {
    const chat = document.getElementById('chatContainer');
    if (!chat || chat.dataset.crumpV1Observed === 'true') return;
    chat.dataset.crumpV1Observed = 'true';

    new MutationObserver(mutations => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (
            node.matches?.('.crump-empty-state') ||
            node.querySelector?.('.crump-empty-state')
          ) {
            refineEmptyState(node.matches?.('.crump-empty-state') ? node.parentElement || chat : node);
          }
        }
      }
    }).observe(chat, {childList: true, subtree: true});
  }

  function installViewportContract() {
    const viewport = window.visualViewport;
    if (!viewport || document.documentElement.dataset.crumpV1Viewport === 'true') return;
    document.documentElement.dataset.crumpV1Viewport = 'true';

    const update = () => {
      const keyboard = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
      document.documentElement.style.setProperty('--v1-keyboard-offset', `${Math.round(keyboard)}px`);
      document.body.classList.toggle('crump-v1-keyboard-visible', keyboard > 120);
    };

    viewport.addEventListener('resize', update, {passive: true});
    viewport.addEventListener('scroll', update, {passive: true});
    update();
  }

  function apply() {
    document.body.classList.add('crump-v1');

    brandHeader();
    brandSidebar();
    brandAuth();
    refineEmptyState();
    refineNavigationCopy();
    installChatObserver();
    installViewportContract();

    document.documentElement.dataset.crumpV1 = 'ready';
  }

  // Legacy enhancement modules intentionally load first. V1 then becomes the
  // final shell owner once, without polling or a whole-document mutation loop.
  function reassertStaticBranding() {
    brandHeader();
    brandSidebar();
    brandAuth();
    refineEmptyState();
    refineNavigationCopy();
  }

  function start() {
    requestAnimationFrame(apply);

    // 5.0 performs two bounded legacy shell passes (initial + delayed).
    // Reassert immediately after each possible pass, then stop. This prevents
    // header ownership races without a whole-document observer or polling loop.
    setTimeout(reassertStaticBranding, 140);
    setTimeout(reassertStaticBranding, 980);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
  } else {
    start();
  }

  window.addEventListener('pageshow', () => requestAnimationFrame(reassertStaticBranding));
})();
