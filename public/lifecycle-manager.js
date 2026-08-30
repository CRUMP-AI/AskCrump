(() => {
  'use strict';

  const SESSION_KEY = 'askcrump.lifecycle-session';
  const MESSAGE_KEYS = new Set([
    'starter-assist', 'first-value-assist', 'continuity-assist',
    'artifact-assist', 'referral-ask',
  ]);
  const INTENTS = new Set(['document', 'presentation', 'resume', 'video', 'projects']);
  const SURFACES = new Set(['workspace-inline', 'composer-inline', 'post-response-inline']);
  const COPY = Object.freeze({
    'starter-assist': Object.freeze({
      default: Object.freeze({
        title: 'Bring one real task',
        body: 'Say what you are trying to move forward, who it is for, what constraints matter, and what you need next. The rough version is enough.',
        primary: 'Start a conversation',
      }),
      projects: Object.freeze({
        title: 'Give the work a clear boundary',
        body: 'Create a Project for the instructions, files, conversations, and decisions that belong to one body of work.',
        primary: 'Open Projects',
      }),
      presentation: Object.freeze({
        title: 'Start with the decision',
        body: 'Add the audience, the decision or idea the deck must carry, the evidence you have, and the length you need.',
        primary: 'Create a presentation',
      }),
      document: Object.freeze({
        title: 'Start with purpose and audience',
        body: 'Bring the request, notes, or source material. Choose who the document is for and what it needs to accomplish.',
        primary: 'Create a document',
      }),
      resume: Object.freeze({
        title: 'Bring the facts first',
        body: 'Add your real experience and the target role. Build an editable draft, then review every claim before using it.',
        primary: 'Create a résumé',
      }),
      video: Object.freeze({
        title: 'Define the scene before it generates',
        body: 'Choose the visual direction and generation mode, review the credit cost, then create when the setup is right.',
        primary: 'Open Video Studio',
      }),
    }),
    'first-value-assist': Object.freeze({
      default: Object.freeze({
        title: 'Four details are enough to begin',
        body: 'Name the task, the audience, the constraints, and the decision or deliverable you need. Clarity can come next.',
        primary: 'Ask Crump',
      }),
    }),
    'continuity-assist': Object.freeze({
      default: Object.freeze({
        title: 'Keep this work moving',
        body: 'Give the work a Project when its instructions, conversations, files, and decisions should stay together for the next return.',
        primary: 'Keep it in a Project',
      }),
    }),
    'artifact-assist': Object.freeze({
      default: Object.freeze({
        title: 'Turn the useful part into something you can keep',
        body: 'Choose the output you need, review the setup, and keep the finished file with the work.',
        primary: 'Open Create',
      }),
      presentation: Object.freeze({
        title: 'Turn the structure into an editable deck',
        body: 'Set the audience, evidence, decision, and length before Ask Crump prepares the PowerPoint draft.',
        primary: 'Create a presentation',
      }),
      document: Object.freeze({
        title: 'Turn the work into an editable document',
        body: 'Choose the audience, purpose, evidence, and format before creating the Word or PDF draft.',
        primary: 'Create a document',
      }),
      resume: Object.freeze({
        title: 'Make the next version role-specific',
        body: 'Use verified experience and the target role to prepare an editable résumé draft. Review every detail before sending it.',
        primary: 'Create a résumé',
      }),
    }),
    'referral-ask': Object.freeze({
      default: Object.freeze({
        title: 'Know someone carrying an unfinished project?',
        body: 'Send them Ask Crump. Share the workspace, not your private conversation or files.',
        primary: 'Share Ask Crump',
      }),
    }),
  });
  const FALLBACKS = Object.freeze({
    projects: 'Projects could not open. Your current work has not been moved. Try again when Projects is available.',
    create: 'Create could not open. Your conversation is still here. Try again when the workspace is available.',
    share: 'Sharing is unavailable right now. Nothing was posted or sent.',
  });

  let chosenIntent = null;
  let currentDecision = null;
  let currentCard = null;
  let evaluating = false;
  let nextEvaluationAt = 0;
  let evaluationTimer = 0;
  let volatileSessionId = '';

  function sessionId() {
    try {
      let value = sessionStorage.getItem(SESSION_KEY);
      if (!/^[A-Za-z0-9][A-Za-z0-9_-]{15,99}$/.test(value || '')) {
        value = crypto.randomUUID();
        sessionStorage.setItem(SESSION_KEY, value);
      }
      volatileSessionId = value;
      return value;
    } catch (_) {
      if (!volatileSessionId) volatileSessionId = crypto.randomUUID();
      return volatileSessionId;
    }
  }

  function isVisible(node) {
    if (!node || node.hidden || node.getAttribute('aria-hidden') === 'true') return false;
    const style = getComputedStyle(node);
    return style.display !== 'none' && style.visibility !== 'hidden' && node.getClientRects().length > 0;
  }

  function currentSurface() {
    if (document.body.classList.contains('crump5930-create-open')) return 'create';
    const sheet = document.getElementById('crump53Sheet');
    if (isVisible(sheet)) {
      if (sheet.dataset.crump53Section === 'projects') return 'projects';
      if (['manuscripts', 'video'].includes(sheet.dataset.crump53Section)) return 'create';
    }
    return 'ask';
  }

  function activeWork() {
    const input = document.getElementById('userInput');
    const preview = document.getElementById('filePreview');
    return Boolean(
      String(input?.value || '').trim()
      || window.CrumpPresence?.indicator?.()
      || document.getElementById('sendButton')?.disabled
      || (preview && isVisible(preview))
    );
  }

  function recoverySurface() {
    if (document.getElementById('appContainer')?.getAttribute('aria-busy') === 'true') return true;
    return Array.from(document.querySelectorAll(
      '.modal, .auth-error, [role="dialog"], .billing51-overlay, .crump51-recovery',
    )).some(node => !node.closest('.crump-lifecycle-card') && isVisible(node));
  }

  function context() {
    return {
      sessionId: sessionId(),
      intent: INTENTS.has(chosenIntent) ? chosenIntent : null,
      activeWork: activeWork(),
      recoverySurface: recoverySurface(),
      currentSurface: currentSurface(),
    };
  }

  async function api(path, body) {
    const response = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error('Lifecycle request failed.');
    return data;
  }

  function validDecision(value) {
    return Boolean(
      value?.eligible === true
      && MESSAGE_KEYS.has(value.messageKey)
      && SURFACES.has(value.surface)
      && /^[0-9a-fA-F-]{36}$/.test(value.decisionId || '')
      && (value.intent == null || INTENTS.has(value.intent))
    );
  }

  function copyFor(decision) {
    const family = COPY[decision.messageKey];
    return family?.[decision.intent] || family?.default || null;
  }

  function removeCard() {
    currentCard?.remove();
    currentCard = null;
    currentDecision = null;
  }

  async function action(name, suppressionReason = null) {
    if (!currentDecision) return {recorded: false};
    try {
      return await api('/api/lifecycle/actions', {
        ...context(),
        decisionId: currentDecision.decisionId,
        action: name,
        suppressionReason,
      });
    } catch (_) {
      return {recorded: false};
    }
  }

  function attach(card, decision) {
    const launchpad = document.getElementById('v1Launchpad');
    const conversation = document.getElementById('chatContainer');
    const launchpadIsOpen = launchpad && !launchpad.classList.contains('is-hidden');
    if (launchpadIsOpen && decision.surface !== 'post-response-inline') {
      const foot = launchpad.querySelector('.v1-launchpad-foot');
      launchpad.insertBefore(card, foot || null);
      card.dataset.lifecyclePlacement = 'launchpad';
      return true;
    }
    if (!conversation) return false;
    conversation.appendChild(card);
    card.dataset.lifecyclePlacement = 'conversation';
    return true;
  }

  function attachToConversation() {
    if (!currentCard || !currentDecision || currentCard.dataset.lifecyclePlacement !== 'conversation') return;
    document.getElementById('chatContainer')?.appendChild(currentCard);
  }

  async function openDestination(decision) {
    const intent = decision.intent;
    const navigation = window.CrumpNavigation5930;
    if (decision.messageKey === 'referral-ask') {
      const shared = await window.shareAskCrumpWorkspace?.();
      if (!shared) window.showToast?.(FALLBACKS.share, 'error');
      return;
    }
    if (decision.messageKey === 'continuity-assist' || intent === 'projects') {
      if (typeof navigation?.open !== 'function') {
        window.showToast?.(FALLBACKS.projects, 'error');
        return;
      }
      navigation.open('projects');
      return;
    }
    if (['document', 'presentation', 'resume', 'video'].includes(intent)) {
      const opened = navigation?.continueCreation?.({kind: intent});
      if (!opened) window.showToast?.(FALLBACKS.create, 'error');
      return;
    }
    if (decision.messageKey === 'artifact-assist') {
      if (typeof navigation?.open !== 'function') {
        window.showToast?.(FALLBACKS.create, 'error');
        return;
      }
      navigation.open('create');
      return;
    }
    navigation?.open?.('ask');
    requestAnimationFrame(() => document.getElementById('userInput')?.focus({preventScroll: true}));
  }

  async function reveal(decision) {
    const selectedCopy = copyFor(decision);
    if (!selectedCopy || activeWork() || recoverySurface()) return;

    const card = document.createElement('aside');
    card.className = 'crump-lifecycle-card is-pending';
    card.setAttribute('role', 'region');
    card.setAttribute('aria-labelledby', `crumpLifecycleTitle-${decision.decisionId}`);
    card.innerHTML = `
      <div class="crump-lifecycle-mark" aria-hidden="true">✦</div>
      <div class="crump-lifecycle-copy">
        <span>WORKSPACE GUIDE</span>
        <strong id="crumpLifecycleTitle-${decision.decisionId}"></strong>
        <p></p>
      </div>
      <div class="crump-lifecycle-actions">
        <button type="button" class="crump-lifecycle-primary"></button>
        <button type="button" class="crump-lifecycle-dismiss">Not now</button>
      </div>`;
    card.querySelector('strong').textContent = selectedCopy.title;
    card.querySelector('p').textContent = selectedCopy.body;
    card.querySelector('.crump-lifecycle-primary').textContent = selectedCopy.primary;

    currentDecision = decision;
    currentCard = card;
    if (!attach(card, decision)) {
      removeCard();
      return;
    }

    await new Promise(resolve => requestAnimationFrame(resolve));
    if (!currentCard || activeWork() || recoverySurface() || currentSurface() !== 'ask') {
      await action('suppressed', activeWork() ? 'active-work' : 'recovery-surface');
      removeCard();
      return;
    }
    const shown = await action('shown');
    if (!shown.recorded || !currentCard) {
      removeCard();
      return;
    }

    card.classList.remove('is-pending');
    card.classList.add('is-visible');
    const status = document.getElementById('conversationStatus');
    if (status) status.textContent = selectedCopy.title;

    card.querySelector('.crump-lifecycle-dismiss').addEventListener('click', async () => {
      const pending = action('dismissed');
      removeCard();
      await pending;
    }, {once: true});
    card.querySelector('.crump-lifecycle-primary').addEventListener('click', async () => {
      const chosen = currentDecision;
      const pending = action('acted');
      removeCard();
      await pending;
      if (chosen) await openDestination(chosen);
    }, {once: true});
  }

  async function evaluate({force = false} = {}) {
    if (
      evaluating || currentCard || document.hidden || !window.currentUser
      || !navigator.onLine || activeWork() || recoverySurface()
    ) return false;
    if (!force && Date.now() < nextEvaluationAt) return false;
    evaluating = true;
    nextEvaluationAt = Date.now() + 15_000;
    try {
      const decision = await api('/api/lifecycle/decision', context());
      if (validDecision(decision)) await reveal(decision);
      return validDecision(decision);
    } catch (_) {
      return false;
    } finally {
      evaluating = false;
    }
  }

  function schedule(delay = 900) {
    clearTimeout(evaluationTimer);
    evaluationTimer = setTimeout(() => { void evaluate(); }, delay);
  }

  function suppressActiveWork() {
    if (!currentCard) return;
    const pending = action('suppressed', 'active-work');
    removeCard();
    void pending;
  }

  document.addEventListener('input', event => {
    if (event.target?.id === 'userInput' && String(event.target.value || '').trim()) {
      suppressActiveWork();
    }
  });
  document.addEventListener('change', event => {
    if (event.target?.id === 'fileInput') suppressActiveWork();
  });
  document.addEventListener('click', event => {
    if (!currentCard) return;
    const manualDestination = event.target.closest(
      '[data-crump5930-destination="projects"], [data-crump5930-destination="create"], '
      + '[data-v1-command="projects"], [data-v1-command="video"]',
    );
    if (manualDestination) suppressActiveWork();
    else requestAnimationFrame(() => {
      if (currentCard && recoverySurface()) suppressActiveWork();
    });
  }, true);
  window.addEventListener('crump:creation-intent', event => {
    const intent = String(event.detail?.kind || '').toLowerCase();
    chosenIntent = INTENTS.has(intent) ? intent : null;
    suppressActiveWork();
  });
  window.addEventListener('crump:authenticated-ready', () => {
    schedule(1200);
    setTimeout(() => { void evaluate({force: true}); }, 65_000);
  });
  window.addEventListener('crump:body-runtime-ready', () => schedule(1400));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) schedule(700);
  });

  window.CrumpLifecycle = Object.freeze({
    evaluate,
    schedule,
    attachToConversation,
    suppressActiveWork,
  });
})();
