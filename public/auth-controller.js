(() => {
  'use strict';
  let appStarted = false;
  let activeUser = null;
  let planIntentDispatched = false;
  let pagePlanIntent = null;
  let planIntentDeliveryKey = '';
  let planIntentDeliveryAttempts = 0;
  let planIntentDeliveryTimer = 0;
  let planIntentConsumedHandler = null;
  let authFlowRevision = 0;
  let signupIntentTracked = false;
  let workspaceRuntimeGateTimer = 0;
  let workspaceRuntimeGateWaiting = false;
  let workspaceRuntimeGateRevealFrame = 0;
  const TERMS_VERSION = '2026-08-01';
  const PLAN_INTENT_KEY = 'askcrump.pending-plan-intent';
  const CREATION_INTENT_KEY = 'askcrump.pending-creation-intent';
  const ACQUISITION_KEY = 'askcrump.acquisition-source';
  const ACQUISITION_PLACEMENT_KEY = 'askcrump.acquisition-placement';
  const FIRST_TOUCH_KEY = 'askcrump.first-touch-attribution';
  const FREE_REGISTRATION_ASSURANCE = 'Free includes 25 messages each day and 2 private Projects. We’ll email a secure verification link; no card required.';
  const PAID_REGISTRATION_ASSURANCE = 'We’ll email a secure verification link. Creating your account does not start billing; checkout remains a separate confirmation.';
  const PLAN_INTENT_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  const PLAN_INTENT_DELIVERY_INTERVAL_MS = 500;
  const PLAN_INTENT_DELIVERY_MAX_ATTEMPTS = 32;
  const CREATION_INTENT_TTL_MS = 24 * 60 * 60 * 1000;
  const FIRST_TOUCH_TTL_MS = 24 * 60 * 60 * 1000;
  const PAID_PLAN_INTENTS = new Set(['professional', 'enterprise']);
  const CREATION_INTENTS = new Set(['document', 'presentation', 'resume', 'video', 'projects']);
  const CREATION_INTENT_EXPLORE_DESTINATIONS = Object.freeze({
    document: {href: '/ai-document-generator', label: 'See document examples first'},
    presentation: {href: '/ai-presentation-maker', label: 'See presentation examples first'},
    resume: {href: '/ai-resume-builder', label: 'See résumé examples first'},
    video: {href: '/ai-video-generator', label: 'Explore Video Studio first'},
    projects: {href: '/ai-project-workspace', label: 'See how Projects work first'},
  });
  const REGISTRATION_CREATION_HANDOFFS = Object.freeze({
    document: {
      title: 'Create your document workspace.',
      description: 'After verification, Ask Crump opens the document workspace so you can turn a request, notes, or source material into an editable Word draft or PDF.',
    },
    presentation: {
      title: 'Create your presentation workspace.',
      description: 'After verification, Ask Crump opens the presentation workspace so you can turn a topic, outline, or source material into an editable PowerPoint draft.',
    },
    resume: {
      title: 'Build your résumé workspace.',
      description: 'After verification, Ask Crump opens the résumé workspace so you can shape your real experience into an editable Word résumé without invented credentials.',
    },
    video: {
      title: 'Open your Video Studio.',
      description: 'After verification, Ask Crump opens Video Studio so you can choose a generation mode, see its Crump Credit cost, and find completed clips in Projects → Files.',
    },
    projects: {
      title: 'Open your private Project workspace.',
      description: 'After verification, Ask Crump opens Projects so you can keep instructions, files, conversations, and durable context together before you continue the work.',
    },
  });
  const REGISTRATION_PLAN_HANDOFFS = Object.freeze({
    professional: {
      title: 'Create your account for Professional.',
      disclosure: 'Professional includes Advanced Intelligence at $20/month and remains unpurchased until you review and confirm checkout.',
      button: 'Create account & review Professional',
    },
    enterprise: {
      title: 'Create your account for Enterprise.',
      disclosure: 'Enterprise includes Advanced Intelligence at $50/month and remains unpurchased until you review and confirm checkout.',
      button: 'Create account & review Enterprise',
    },
  });
  const LEGACY_ACQUISITION_SOURCES = new Set([
    'instagram', 'facebook', 'facebook-pinned', 'linkedin', 'tiktok',
    'youtube', 'x', 'referral', 'organic', 'clevercrump',
  ]);
  const ACQUISITION_SOURCES = new Set([
    'direct', 'instagram', 'facebook', 'facebook-pinned', 'linkedin', 'tiktok',
    'youtube', 'x', 'referral', 'organic', 'organic-search', 'clevercrump',
    'founder-outreach',
  ]);
  const ACQUISITION_PLACEMENTS = new Set([
    'response-share', 'profile-link', 'workflow-guide', 'organic-social',
    'creator-cohort',
  ]);
  const CAMPAIGN_REGISTRY = Object.freeze({
    'presentation-proof-current': {
      intent: 'presentation',
      acquisitions: new Set(['facebook', 'instagram']),
      placements: new Set(['profile-link', 'organic-social']),
      creatives: new Set(['fb-static', 'ig-feed', 'ig-story']),
    },
    'real-product-continuity': {
      intent: 'projects',
      acquisitions: new Set(['facebook', 'instagram']),
      placements: new Set(['profile-link', 'organic-social']),
      creatives: new Set(['continuity-feed', 'continuity-story']),
    },
    'rough-idea-launch-plan': {
      intent: 'projects',
      acquisitions: new Set(['organic-search']),
      placements: new Set(['workflow-guide']),
      creatives: new Set(['search-article']),
    },
    'project-memory-boundaries': {
      intent: 'projects',
      acquisitions: new Set(['organic-search', 'facebook', 'instagram']),
      placements: new Set(['workflow-guide', 'organic-social']),
      creatives: new Set(['search-article', 'project-memory-feed', 'project-memory-story']),
    },
    'editable-powerpoint-review': {
      intent: 'presentation',
      acquisitions: new Set(['organic-search', 'facebook', 'instagram']),
      placements: new Set(['workflow-guide', 'organic-social']),
      creatives: new Set(['search-article', 'presentation-feed', 'presentation-story']),
    },
    'creator-cohort-01': {
      intent: 'projects',
      acquisitions: new Set(['founder-outreach']),
      placements: new Set(['creator-cohort']),
      creatives: new Set(['personal-invite']),
    },
  });

  window.va = window.va || function queueVercelAnalytics() {
    (window.vaq = window.vaq || []).push(arguments);
  };

  const byId = id => document.getElementById(id);
  const show = (id, display = 'block') => { const node = byId(id); if (node) node.style.display = display; };
  const hide = id => { const node = byId(id); if (node) node.style.display = 'none'; };
  const setText = (id, text, visible = true) => { const node = byId(id); if (!node) return; node.textContent = text || ''; node.style.display = visible ? 'block' : 'none'; };
  const AUTH_VIEWS = Object.freeze({
    login: {containerId: 'loginForm', fieldId: 'loginEmail'},
    register: {containerId: 'registerForm', fieldId: 'registerEmail'},
    forgot: {containerId: 'forgotPasswordForm', fieldId: 'forgotPasswordEmail'},
    reset: {containerId: 'resetPasswordForm', fieldId: 'newPassword'},
  });

  function authRequest(url, options, timeoutMessage) {
    return window.CrumpAuthTransport.request(url, options, {timeoutMessage});
  }

  function funnelValue(value, fallback) {
    const normalized = String(value || '').trim().toLowerCase();
    return /^[a-z0-9_-]{1,32}$/.test(normalized) ? normalized : fallback;
  }

  function attributionToken(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return /^[a-z0-9][a-z0-9-]{0,31}$/.test(normalized) ? normalized : '';
  }

  function normalizeAttribution(candidate) {
    const acquisitionToken = attributionToken(candidate?.acquisition);
    const acquisition = ACQUISITION_SOURCES.has(acquisitionToken) ? acquisitionToken : 'direct';
    const placementToken = attributionToken(candidate?.placement);
    const placement = ACQUISITION_PLACEMENTS.has(placementToken) ? placementToken : null;
    const intentToken = attributionToken(candidate?.intent);
    const intent = CREATION_INTENTS.has(intentToken) ? intentToken : null;
    const campaignToken = attributionToken(candidate?.campaign);
    const specification = CAMPAIGN_REGISTRY[campaignToken];
    const campaign = specification
      && specification.acquisitions.has(acquisition)
      && specification.placements.has(placement)
      && specification.intent === intent
      ? campaignToken
      : null;
    const creativeToken = attributionToken(candidate?.creative);
    const creative = campaign && specification.creatives.has(creativeToken)
      ? creativeToken
      : null;
    return {acquisition, placement, campaign, creative, intent};
  }

  function referringAcquisitionSource() {
    if (!document.referrer) return 'direct';
    try {
      const host = new URL(document.referrer).hostname.toLowerCase();
      if (
        host === location.hostname
        || host === 'askcrump.com'
        || host.endsWith('.askcrump.com')
      ) return 'direct';
      const searchHosts = [
        'bing.com',
        'duckduckgo.com',
        'search.yahoo.com',
        'ecosia.org',
        'search.brave.com',
      ];
      if (
        /(^|\.)google\.[a-z.]+$/.test(host)
        || searchHosts.some(domain => host === domain || host.endsWith('.' + domain))
      ) return 'organic';
      const sources = [
        ['instagram.com', 'instagram'],
        ['facebook.com', 'facebook'],
        ['linkedin.com', 'linkedin'],
        ['tiktok.com', 'tiktok'],
        ['youtube.com', 'youtube'],
        ['youtu.be', 'youtube'],
        ['twitter.com', 'x'],
        ['x.com', 'x'],
        ['t.co', 'x'],
        ['clevercrump.com', 'clevercrump'],
      ];
      return sources.find(([domain]) => host === domain || host.endsWith('.' + domain))?.[1] || 'referral';
    } catch (_) {
      return 'direct';
    }
  }

  function currentAttribution() {
    const params = new URLSearchParams(location.search);
    const locationSource = attributionToken(params.get('source'));
    const explicitAcquisition = attributionToken(
      params.get('acquisition') || params.get('utm_source'),
    );
    // Older social links used `source=<channel>` before the dedicated
    // `acquisition` parameter existed. Recover only known external channels;
    // on-site CTA locations such as hero, pricing, and footer stay locations.
    const legacyAcquisition = LEGACY_ACQUISITION_SOURCES.has(locationSource)
      ? locationSource
      : '';
    let storedAcquisition = '';
    let storedPlacement = '';
    try {
      storedAcquisition = attributionToken(sessionStorage.getItem(ACQUISITION_KEY));
      storedPlacement = attributionToken(sessionStorage.getItem(ACQUISITION_PLACEMENT_KEY));
    } catch (_) {}
    const acquisition = explicitAcquisition
      || legacyAcquisition
      || (ACQUISITION_SOURCES.has(storedAcquisition) ? storedAcquisition : '')
      || referringAcquisitionSource();
    const placement = ACQUISITION_PLACEMENTS.has(locationSource)
      ? locationSource
      : storedPlacement;
    const intent = creationIntentValue(params.get('intent')) || pendingCreationIntent()?.kind || null;
    return normalizeAttribution({
      acquisition,
      placement,
      campaign: params.get('campaign'),
      creative: params.get('creative'),
      intent,
    });
  }

  function storedFirstTouch() {
    try {
      const stored = JSON.parse(sessionStorage.getItem(FIRST_TOUCH_KEY) || 'null');
      const capturedAt = Number(stored?.capturedAt || 0);
      if (!capturedAt || Date.now() - capturedAt > FIRST_TOUCH_TTL_MS) {
        sessionStorage.removeItem(FIRST_TOUCH_KEY);
        return null;
      }
      return {...normalizeAttribution(stored), capturedAt};
    } catch (_) {
      return null;
    }
  }

  function firstTouchAttribution() {
    const candidate = currentAttribution();
    const stored = storedFirstTouch();
    const capturedAt = stored?.capturedAt || Date.now();
    const attribution = stored ? normalizeAttribution(stored) : candidate;
    try {
      sessionStorage.setItem(FIRST_TOUCH_KEY, JSON.stringify({...attribution, capturedAt}));
      sessionStorage.setItem(ACQUISITION_KEY, attribution.acquisition);
      if (attribution.placement) {
        sessionStorage.setItem(ACQUISITION_PLACEMENT_KEY, attribution.placement);
      }
    } catch (_) {}
    return attribution;
  }

  function funnelContext() {
    const params = new URLSearchParams(location.search);
    const attribution = firstTouchAttribution();
    return {
      source: funnelValue(params.get('source'), 'direct'),
      ...attribution,
      plan: funnelValue(params.get('plan'), 'unspecified'),
      intent: attribution.intent || creationIntentValue(params.get('intent')) || pendingCreationIntent()?.kind || 'unspecified',
    };
  }

  function trackFunnel(name, data = {}) {
    window.va('event', {name, data: {...funnelContext(), ...data}});
  }

  function trackSignupIntent(locationName) {
    if (signupIntentTracked) return;
    signupIntentTracked = true;
    trackFunnel('SignupIntent', {location: locationName});
  }

  function capturePlanIntent() {
    const context = funnelContext();
    const params = new URLSearchParams(location.search);
    if (params.get('signup') === '1' && context.plan === 'free') {
      pagePlanIntent = null;
      try { localStorage.removeItem(PLAN_INTENT_KEY); } catch (_) {}
      return;
    }
    if (!PAID_PLAN_INTENTS.has(context.plan)) return;
    pagePlanIntent = {
      plan: context.plan,
      source: context.acquisition,
      location: context.source,
      capturedAt: Date.now(),
    };
    try {
      localStorage.setItem(PLAN_INTENT_KEY, JSON.stringify(pagePlanIntent));
    } catch (_) {}
  }

  function creationIntentValue(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return CREATION_INTENTS.has(normalized) ? normalized : '';
  }

  function configureRegistrationExploreLink() {
    const link = byId('registrationExploreLink');
    if (!link) return;
    const params = new URLSearchParams(location.search);
    const kind = creationIntentValue(params.get('intent')) || pendingCreationIntent()?.kind || '';
    const destination = CREATION_INTENT_EXPLORE_DESTINATIONS[kind] || {
      href: '/',
      label: 'Explore Ask Crump first',
    };
    link.href = destination.href;
    link.textContent = destination.label;
    link.dataset.exploreDestination = kind || 'overview';
  }

  function configureRegistrationHandoff() {
    const title = byId('registrationTitle');
    const description = byId('registrationDescription');
    const button = byId('registrationSubmitBtn');
    const assurance = byId('registrationAssurance');
    if (!title || !description || !button) return;

    const params = new URLSearchParams(location.search);
    const creationKind = creationIntentValue(params.get('intent')) || pendingCreationIntent()?.kind || '';
    const explicitPlan = funnelValue(params.get('plan'), '');
    const planKind = PAID_PLAN_INTENTS.has(explicitPlan)
      ? explicitPlan
      : (params.has('plan') ? '' : pendingPlanIntent()?.plan || '');
    const creation = REGISTRATION_CREATION_HANDOFFS[creationKind];
    const plan = REGISTRATION_PLAN_HANDOFFS[planKind];

    title.textContent = creation?.title || plan?.title || 'Create your workspace.';
    description.textContent = creation?.description
      || (plan
        ? 'Account creation is free. Your workspace opens after verification.'
        : 'Ask questions, create useful work, and pick up where you left off. Free to start—no card required.');
    if (plan) description.textContent += ` ${plan.disclosure}`;
    else if (creation) description.textContent += ' Free to start—no card required.';
    button.textContent = plan?.button || (creation ? 'Create account & continue' : 'Create free account');
    if (assurance) assurance.textContent = plan
      ? PAID_REGISTRATION_ASSURANCE
      : FREE_REGISTRATION_ASSURANCE;
  }

  function wireExploreRegistrationLink() {
    const link = byId('registrationExploreLink');
    if (!link) return;
    link.addEventListener('click', () => {
      const destination = creationIntentValue(link.dataset.exploreDestination) || 'overview';
      trackFunnel('RegistrationExplore', {destination});
    });
  }

  function captureCreationIntent() {
    const params = new URLSearchParams(location.search);
    const kind = creationIntentValue(params.get('intent'));
    if (!kind) {
      if (params.get('signup') === '1') {
        try { localStorage.removeItem(CREATION_INTENT_KEY); } catch (_) {}
      }
      return;
    }
    const context = funnelContext();
    try {
      localStorage.setItem(CREATION_INTENT_KEY, JSON.stringify({
        kind,
        source: context.source,
        acquisition: context.acquisition,
        capturedAt: Date.now(),
      }));
    } catch (_) {}
  }

  function pendingCreationIntent() {
    try {
      const intent = JSON.parse(localStorage.getItem(CREATION_INTENT_KEY) || 'null');
      const capturedAt = Number(intent?.capturedAt || 0);
      const kind = creationIntentValue(intent?.kind);
      if (!kind || !capturedAt || Date.now() - capturedAt > CREATION_INTENT_TTL_MS) {
        localStorage.removeItem(CREATION_INTENT_KEY);
        return null;
      }
      return {
        kind,
        source: funnelValue(intent.source, 'unknown'),
        acquisition: funnelValue(intent.acquisition, 'direct'),
        capturedAt,
      };
    } catch (_) {
      try { localStorage.removeItem(CREATION_INTENT_KEY); } catch (_) {}
      return null;
    }
  }

  function dispatchPendingCreationIntent() {
    const intent = pendingCreationIntent();
    if (!intent) return;

    const deliver = () => {
      window.addEventListener('crump:creation-intent-consumed', event => {
        if (event.detail?.kind !== intent.kind) return;
        try { localStorage.removeItem(CREATION_INTENT_KEY); } catch (_) {}
      }, {once: true});
      window.dispatchEvent(new CustomEvent('crump:creation-intent', {detail: intent}));
    };

    if (document.documentElement.dataset.crumpBodyRuntime === 'ready') {
      queueMicrotask(deliver);
    } else {
      window.addEventListener('crump:body-runtime-ready', deliver, {once: true});
    }
  }

  function pendingPlanIntent() {
    const normalize = intent => {
      const capturedAt = Number(intent?.capturedAt || 0);
      if (!PAID_PLAN_INTENTS.has(intent?.plan) || !capturedAt || Date.now() - capturedAt > PLAN_INTENT_TTL_MS) {
        return null;
      }
      return {
        plan: intent.plan,
        source: funnelValue(intent.source, 'direct'),
        location: funnelValue(intent.location, 'unknown'),
        capturedAt,
      };
    };
    const pageIntent = normalize(pagePlanIntent);
    if (pageIntent) return pageIntent;
    pagePlanIntent = null;
    try {
      const intent = JSON.parse(localStorage.getItem(PLAN_INTENT_KEY) || 'null');
      const normalized = normalize(intent);
      if (!normalized) {
        localStorage.removeItem(PLAN_INTENT_KEY);
        return null;
      }
      return normalized;
    } catch (_) {
      try { localStorage.removeItem(PLAN_INTENT_KEY); } catch (_) {}
      return null;
    }
  }

  function dispatchPendingPlanIntent() {
    if (planIntentDispatched) return;
    const intent = pendingPlanIntent();
    if (!intent) return;
    const deliveryKey = `${intent.plan}:${intent.capturedAt}`;

    if (planIntentDeliveryKey && planIntentDeliveryKey !== deliveryKey) {
      clearTimeout(planIntentDeliveryTimer);
      planIntentDeliveryTimer = 0;
      planIntentDeliveryAttempts = 0;
      if (planIntentConsumedHandler) {
        window.removeEventListener('crump:plan-intent-consumed', planIntentConsumedHandler);
        planIntentConsumedHandler = null;
      }
    }
    planIntentDeliveryKey = deliveryKey;

    if (!planIntentConsumedHandler) {
      planIntentConsumedHandler = event => {
        if (event.detail?.plan !== intent.plan) return;
        const consumedAt = Number(event.detail?.capturedAt || intent.capturedAt);
        if (consumedAt !== intent.capturedAt) return;
        planIntentDispatched = true;
        pagePlanIntent = null;
        clearTimeout(planIntentDeliveryTimer);
        planIntentDeliveryTimer = 0;
        planIntentDeliveryAttempts = 0;
        planIntentDeliveryKey = '';
        window.removeEventListener('crump:plan-intent-consumed', planIntentConsumedHandler);
        planIntentConsumedHandler = null;
        try { localStorage.removeItem(PLAN_INTENT_KEY); } catch (_) {}
      };
      window.addEventListener('crump:plan-intent-consumed', planIntentConsumedHandler);
    }

    const deliver = () => {
      if (planIntentDispatched) return;
      planIntentDeliveryTimer = 0;
      planIntentDeliveryAttempts += 1;
      window.dispatchEvent(new CustomEvent('crump:plan-intent', {detail: intent}));
      if (!planIntentDispatched && planIntentDeliveryAttempts < PLAN_INTENT_DELIVERY_MAX_ATTEMPTS) {
        planIntentDeliveryTimer = window.setTimeout(deliver, PLAN_INTENT_DELIVERY_INTERVAL_MS);
      }
    };

    const beginDelivery = () => {
      if (planIntentDispatched || planIntentDeliveryTimer || planIntentDeliveryAttempts) return;
      queueMicrotask(deliver);
    };

    if (document.documentElement.dataset.crumpBodyRuntime === 'ready') {
      beginDelivery();
    } else {
      window.addEventListener('crump:body-runtime-ready', beginDelivery, {once: true});
    }
  }

  function applyServerSettings(settings) {
    if (!settings || typeof settings !== 'object') return;
    const keys = window.STORAGE_KEYS || {};
    const mappings = [
      ['assistant_name', keys.ASSISTANT_NAME || 'crump_assistant_name'],
      ['work_mode', keys.WORK_MODE || 'crump_work_mode'],
      ['work_start', keys.WORK_START || 'crump_work_start'],
      ['work_end', keys.WORK_END || 'crump_work_end'],
    ];
    for (const [field, key] of mappings) {
      if (settings[field] !== undefined && settings[field] !== null) {
        localStorage.setItem(key, String(settings[field]));
      }
    }
  }

  function releaseWorkspaceRuntimeGate() {
    if (workspaceRuntimeGateTimer) window.clearTimeout(workspaceRuntimeGateTimer);
    workspaceRuntimeGateTimer = 0;
    workspaceRuntimeGateWaiting = false;
    if (workspaceRuntimeGateRevealFrame) window.cancelAnimationFrame(workspaceRuntimeGateRevealFrame);
    workspaceRuntimeGateRevealFrame = 0;
    window.removeEventListener('crump:body-runtime-ready', scheduleWorkspaceRuntimeGateRelease);
    byId('appContainer')?.removeAttribute('aria-busy');
    document.querySelector('.v1-shell')?.removeAttribute('inert');
    const gate = byId('v1RuntimeGate');
    if (!gate || gate.hidden) return;
    gate.classList.add('is-ready');
    gate.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => {
      if (gate.classList.contains('is-ready')) gate.hidden = true;
    }, 220);
  }

  function scheduleWorkspaceRuntimeGateRelease() {
    if (document.documentElement.dataset.crumpBodyRuntime !== 'ready') return;
    if (workspaceRuntimeGateRevealFrame) window.cancelAnimationFrame(workspaceRuntimeGateRevealFrame);
    // Commit one complete workspace frame before beginning the cover fade.
    // The second frame prevents deferred navigation and authenticated modules
    // from visibly rearranging the shell underneath a partially transparent gate.
    workspaceRuntimeGateRevealFrame = window.requestAnimationFrame(() => {
      workspaceRuntimeGateRevealFrame = window.requestAnimationFrame(() => {
        workspaceRuntimeGateRevealFrame = 0;
        releaseWorkspaceRuntimeGate();
      });
    });
  }

  function holdWorkspaceForRuntime() {
    if (document.documentElement.dataset.crumpBodyRuntime === 'ready') {
      return;
    }
    const gate = byId('v1RuntimeGate');
    const shell = document.querySelector('.v1-shell');
    if (gate) {
      gate.hidden = false;
      gate.classList.remove('is-ready');
      gate.removeAttribute('aria-hidden');
    }
    byId('appContainer')?.setAttribute('aria-busy', 'true');
    shell?.setAttribute('inert', '');
    if (!workspaceRuntimeGateWaiting) {
      workspaceRuntimeGateWaiting = true;
      window.addEventListener('crump:body-runtime-ready', scheduleWorkspaceRuntimeGateRelease, {once: true});
    }
    if (workspaceRuntimeGateTimer) window.clearTimeout(workspaceRuntimeGateTimer);
    workspaceRuntimeGateTimer = window.setTimeout(releaseWorkspaceRuntimeGate, 5000);
  }

  function showReturningVisitorGate() {
    hide('authContainer');
    hide('tosModal');
    hide('onboardingModal');
    const gate = byId('v1RuntimeGate');
    const shell = document.querySelector('.v1-shell');
    if (gate) {
      gate.hidden = false;
      gate.classList.remove('is-ready');
      gate.removeAttribute('aria-hidden');
    }
    byId('appContainer')?.setAttribute('aria-busy', 'true');
    shell?.setAttribute('inert', '');
    show('appContainer', 'flex');
  }

  async function prepareAuthenticatedWorkspace() {
    const runtime = window.CrumpWorkspaceRuntime;
    if (!runtime || typeof runtime.load !== 'function') {
      throw new Error('Ask Crump could not prepare your workspace. Reload and try again.');
    }
    await runtime.load();
  }

  function startApp() {
    hide('authContainer');
    hide('tosModal');
    hide('onboardingModal');
    holdWorkspaceForRuntime();
    show('appContainer', 'flex');
    if (!appStarted) {
      window.initializeApp?.();
      appStarted = true;
    }
    if (activeUser) {
      window.initializeAuthenticatedApp?.(activeUser);
      window.dispatchEvent(new Event('crump:authenticated-ready'));
    }
    scheduleWorkspaceRuntimeGateRelease();
    if (activeUser) {
      const day = new Date().toISOString().slice(0, 10);
      void window.CrumpAnalytics?.track('WorkspaceOpened', {eventKey: `workspace-open:${day}`});
    }
    setTimeout(() => window.tutorial?.autoStart?.(), 450);
    dispatchPendingCreationIntent();
    dispatchPendingPlanIntent();
  }

  function profileNudgeKey() {
    return window.STORAGE_KEYS?.PROFILE_NUDGE_DISMISSED || 'crump_profile_nudge_dismissed';
  }

  function profileNudgeDismissed() {
    try { return localStorage.getItem(profileNudgeKey()) === 'true'; } catch (_) { return false; }
  }

  function maybeOfferProfileSetup() {
    const nudge = byId('v1ProfileNudge');
    if (!nudge) return;
    nudge.hidden = Boolean(window.currentUser?.fullName || activeUser?.fullName) || profileNudgeDismissed();
  }

  function openProfileSetup() {
    const nudge = byId('v1ProfileNudge');
    if (nudge) nudge.hidden = true;
    setText('onboardingError', '', false);
    show('onboardingModal', 'flex');
    requestAnimationFrame(() => byId('onboardingName')?.focus());
  }

  function dismissProfileSetup() {
    try { localStorage.setItem(profileNudgeKey(), 'true'); } catch (_) {}
    hide('onboardingModal');
    const nudge = byId('v1ProfileNudge');
    if (nudge) nudge.hidden = true;
    byId('userInput')?.focus({preventScroll: true});
  }

  function routeAuthenticatedUser(user) {
    activeUser = user;
    window.currentUser = user;
    window.configureUserStorage?.(user.id);
    window.profileManager?.applyServerSubscription?.(user);
    if (!user.termsAcceptedAt) {
      hide('authContainer');
      show('tosModal', 'flex');
      return;
    }
    if (user.fullName) {
      localStorage.setItem(window.STORAGE_KEYS?.HAS_ONBOARDED || 'crump_has_onboarded', 'true');
      window.profileManager?.updateProfile?.({ name: user.fullName, email: user.email });
    }
    startApp();
    if (!user.fullName) maybeOfferProfileSetup();
  }

  function focusAuthView(view) {
    const fieldId = AUTH_VIEWS[view]?.fieldId;
    if (!fieldId) return;
    requestAnimationFrame(() => byId(fieldId)?.focus({preventScroll: true}));
  }

  function showAuth(view = 'login') {
    const normalizedView = AUTH_VIEWS[view] ? view : 'login';
    hide('appContainer');
    hide('tosModal');
    hide('onboardingModal');
    show('authContainer', 'flex');
    Object.values(AUTH_VIEWS).forEach(({containerId}) => hide(containerId));
    if (normalizedView === 'register') {
      resetRegistrationView();
      configureRegistrationHandoff();
    }
    show(AUTH_VIEWS[normalizedView].containerId);
    focusAuthView(normalizedView);
  }

  function resetRegistrationView() {
    hide('registrationPending');
    show('registerEntry');
    setText('registrationPendingSuccess', '', false);
    setText('registrationPendingError', '', false);
  }

  function showRegistrationPending(email, message, {deliveryFailed = false} = {}) {
    const loginEmail = byId('loginEmail');
    if (loginEmail) loginEmail.value = email;
    const forgotEmail = byId('forgotPasswordEmail');
    if (forgotEmail) forgotEmail.value = email;
    const pendingEmail = byId('registrationPendingEmail');
    if (pendingEmail) pendingEmail.textContent = email;
    setText('registerError', '', false);
    setText('registerSuccess', '', false);
    setText('registrationPendingSuccess', deliveryFailed ? '' : message, !deliveryFailed);
    setText('registrationPendingError', deliveryFailed ? message : '', deliveryFailed);
    hide('registerEntry');
    show('registrationPending');
    byId('registrationPending')?.focus();
  }

  async function resendVerificationEmail(email, {button, successId, errorId}) {
    setText(successId, '', false);
    setText(errorId, '', false);
    if (!email) {
      setText(errorId, 'Enter your email first.');
      return;
    }
    button.disabled = true;
    try {
      const {response, data} = await authRequest('/api/auth/resend-verification', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          email,
          intent: pendingCreationIntent()?.kind || null,
          plan: pendingPlanIntent()?.plan || null,
        }),
      }, 'Sending the verification email took too long. Check your inbox before retrying.');
      const message = data.message || data.error || 'Request completed.';
      setText(response.ok ? successId : errorId, message);
    } catch (error) {
      setText(errorId, error.message || 'Verification email could not be sent. Check your connection and try again.');
    } finally {
      button.disabled = false;
    }
  }

  function showVerificationResult(value) {
    const messages = {
      success: 'Email verified. Your workspace is ready.',
      already_verified: 'This email is already verified.',
      failed: 'That verification link is invalid, expired, or already used. Enter your email below to resend verification, or sign in if verification already completed.',
    };
    if (!messages[value]) return;
    setText(value === 'failed' ? 'loginError' : 'loginSuccess', messages[value]);
    if (value === 'failed') {
      show('verificationNeeded');
      byId('loginEmail')?.focus({preventScroll: true});
    }
  }

  async function bootstrap() {
    captureCreationIntent();
    configureRegistrationExploreLink();
    capturePlanIntent();
    configureRegistrationHandoff();
    const params = new URLSearchParams(location.search);
    const signupRequested = params.get('signup') === '1';
    const resetToken = params.get('token');
    if (resetToken) {
      showAuth('reset');
      byId('resetPasswordForm').dataset.token = resetToken;
      history.replaceState({}, document.title, location.pathname);
      return;
    }

    const verification = params.get('verification');
    if (verification) {
      history.replaceState({}, document.title, location.pathname);
    }

    if (signupRequested) {
      showAuth('register');
    } else {
      showReturningVisitorGate();
    }

    const bootstrapAuthFlowRevision = authFlowRevision;
    await window.CrumpAPI?.ready;
    const session = await window.deviceAuth.checkSession();
    if (authFlowRevision !== bootstrapAuthFlowRevision) return;
    if (session.unavailable) {
      if (!signupRequested) {
        showAuth('login');
        setText(
          'loginError',
          'Ask Crump could not verify your existing session right now. Your saved sign-in was preserved; try again in a moment.',
        );
      }
      if (verification) showVerificationResult(verification);
      return;
    }
    if (!session.authenticated || !session.data?.user) {
      if (!signupRequested) showAuth('login');
      if (signupRequested) trackSignupIntent('deep-link');
      if (verification) showVerificationResult(verification);
      return;
    }
    await prepareAuthenticatedWorkspace();
    if (authFlowRevision !== bootstrapAuthFlowRevision) return;
    activeUser = session.data.user;
    window.currentUser = activeUser;
    window.configureUserStorage?.(activeUser.id);
    applyServerSettings(session.data.settings);
    routeAuthenticatedUser(activeUser);
    if (verification) showVerificationResult(verification);
  }

  function wireNavigation() {
    byId('showRegisterLink')?.addEventListener('click', event => {
      event.preventDefault();
      showAuth('register');
      trackSignupIntent('auth-link');
    });
    byId('showLoginLink')?.addEventListener('click', event => { event.preventDefault(); showAuth('login'); });
    byId('showForgotPasswordLink')?.addEventListener('click', event => { event.preventDefault(); showAuth('forgot'); });
    byId('showLoginFromForgot')?.addEventListener('click', event => { event.preventDefault(); showAuth('login'); });
    byId('showLoginFromReset')?.addEventListener('click', event => {
      event.preventDefault();
      const resetForm = byId('resetPasswordForm');
      if (resetForm) delete resetForm.dataset.token;
      history.replaceState({}, document.title, location.pathname);
      showAuth('login');
    });
  }

  function wireTerms() {
    byId('tosAccept')?.addEventListener('change', event => {
      const button = byId('tosAcceptBtn');
      if (!button) return;
      button.disabled = !event.target.checked;
      button.style.opacity = event.target.checked ? '1' : '.5';
    });
    byId('tosAcceptBtn')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      const original = button.textContent;
      button.textContent = 'Saving…';
      try {
        const {response, data} = await authRequest('/api/account/accept-terms', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version: TERMS_VERSION }),
        }, 'Saving your acceptance took too long. Try Continue again.');
        if (!response.ok || !data.success) throw new Error(data.error || 'Could not save your acceptance.');
        activeUser = data.user || { ...activeUser, termsAcceptedAt: new Date().toISOString(), termsVersion: TERMS_VERSION };
        window.currentUser = activeUser;
        hide('tosModal');
        startApp();
        if (!activeUser.fullName) maybeOfferProfileSetup();
      } catch (error) {
        window.showToast?.(error.message, 'error');
        button.disabled = false;
        button.textContent = original;
      }
    });
  }

  function setBusy(form, busy, label) {
    const button = form?.querySelector('button[type="submit"]');
    if (!button) return () => {};
    const original = button.dataset.originalText || button.textContent;
    button.dataset.originalText = original;
    button.disabled = busy;
    button.textContent = busy ? label : original;
    return () => { button.disabled = false; button.textContent = original; };
  }

  function passwordRuleState(password) {
    return {
      length: password.length >= 10,
      withinLimit: password.length <= 256,
      letter: /[A-Za-z]/.test(password),
      number: /\d/.test(password),
    };
  }

  function validatePasswordInput(password) {
    const rules = passwordRuleState(password);
    if (!rules.length) return 'Password must be at least 10 characters long.';
    if (!rules.withinLimit) return 'Password is too long.';
    if (!rules.letter || !rules.number) {
      return 'Password must contain at least one letter and one number.';
    }
    return null;
  }

  function updateRegistrationPasswordGuidance({ touched = false } = {}) {
    const input = byId('registerPassword');
    const hint = byId('registerPasswordHint');
    const status = byId('registerPasswordStatus');
    if (!input || !hint || !status) return;

    if (touched) input.dataset.passwordTouched = 'true';
    const value = input.value || '';
    const rules = passwordRuleState(value);
    const ruleNames = {
      length: '10 or more characters',
      letter: 'one letter',
      number: 'one number',
    };
    const missing = [];

    for (const [rule, label] of Object.entries(ruleNames)) {
      const item = hint.querySelector(`[data-password-rule="${rule}"]`);
      const met = rules[rule];
      item?.classList.toggle('is-met', met);
      const marker = item?.querySelector('i');
      if (marker) marker.textContent = met ? '✓' : '○';
      if (!met) missing.push(label);
    }

    const complete = missing.length === 0 && rules.withinLimit;
    if (!value) input.removeAttribute('aria-invalid');
    else if (input.dataset.passwordTouched === 'true') input.setAttribute('aria-invalid', String(!complete));

    const stateKey = `${Number(rules.length)}${Number(rules.letter)}${Number(rules.number)}${Number(rules.withinLimit)}`;
    if (input.dataset.passwordRuleState === stateKey) return;
    input.dataset.passwordRuleState = stateKey;
    if (!value) status.textContent = 'Password requires 10 or more characters, one letter, and one number.';
    else if (!rules.withinLimit) status.textContent = 'Password is too long.';
    else if (complete) status.textContent = 'Password meets all requirements.';
    else status.textContent = `Password still needs ${missing.join(', ')}.`;
  }

  function applyPasswordPolicyMarkup() {
    const ids = ['registerPassword', 'newPassword', 'confirmNewPassword'];
    for (const id of ids) {
      const input = byId(id);
      if (!input) continue;
      input.setAttribute('minlength', '10');
      input.setAttribute('maxlength', '256');
    }

    const registerPassword = byId('registerPassword');
    const resetPassword = byId('newPassword');
    if (registerPassword) registerPassword.placeholder = 'Create a password';
    if (resetPassword) resetPassword.placeholder = '10+ characters with a letter and number';

    const resetHint = resetPassword?.closest?.('.form-group')?.querySelector('.form-hint');
    if (resetHint) resetHint.textContent = 'At least 10 characters with a letter and a number';
    updateRegistrationPasswordGuidance();
  }

  function wirePasswordVisibility() {
    document.querySelectorAll('[data-password-target]').forEach(button => {
      if (button.dataset.passwordVisibilityWired === 'true') return;
      const input = byId(button.dataset.passwordTarget);
      if (!input) return;
      button.dataset.passwordVisibilityWired = 'true';
      button.addEventListener('click', () => {
        const showing = input.type === 'text';
        input.type = showing ? 'password' : 'text';
        button.textContent = showing ? 'Show' : 'Hide';
        button.setAttribute('aria-pressed', String(!showing));
        button.setAttribute(
          'aria-label',
          `${showing ? 'Show' : 'Hide'} ${button.dataset.passwordLabel || 'password'}`,
        );
        input.focus({preventScroll: true});
      });
    });
  }

  function wireLogin() {
    const form = byId('loginFormElement');
    if (!form) return;
    let nativeValidationTracked = false;

    form.addEventListener('invalid', event => {
      if (nativeValidationTracked) return;
      nativeValidationTracked = true;
      setTimeout(() => { nativeValidationTracked = false; }, 0);
      const field = event.target;
      const isEmail = field?.id === 'loginEmail';
      const reason = isEmail
        ? (field.validity?.typeMismatch ? 'email_format' : 'email_required')
        : 'password_required';
      const message = reason === 'email_format'
        ? 'Enter a valid email address.'
        : (isEmail ? 'Enter your email.' : 'Enter your password.');
      field?.setAttribute('aria-invalid', 'true');
      setText('loginError', message);
      trackFunnel('LoginValidationFailed', {reason});
    }, true);

    form.addEventListener('input', event => {
      event.target?.removeAttribute('aria-invalid');
    }, {passive: true});

    form.addEventListener('submit', async event => {
      event.preventDefault();
      authFlowRevision += 1;
      setText('loginError', '', false);
      hide('verificationNeeded');
      trackFunnel('LoginSubmitted');
      const restore = setBusy(event.currentTarget, true, 'Signing in…');
      try {
        const result = await window.deviceAuth.login(byId('loginEmail').value.trim(), byId('loginPassword').value);
        if (!result.success || !result.data?.user) throw Object.assign(new Error(result.error || 'Sign in failed.'), { result });
        await prepareAuthenticatedWorkspace();
        activeUser = result.data.user;
        window.currentUser = activeUser;
        window.configureUserStorage?.(activeUser.id);
        applyServerSettings(result.data.settings);
        setText('loginSuccess', 'Signed in.');
        trackFunnel('LoginCompleted');
        routeAuthenticatedUser(activeUser);
      } catch (error) {
        setText('loginError', error.message || 'Network error. Try again.');
        trackFunnel('LoginFailed', {
          reason: error.result?.needsVerification ? 'verification_required' : 'request_failed',
        });
        if (error.result?.needsVerification) show('verificationNeeded');
      } finally {
        restore();
      }
    });
  }

  function wireRegistration() {
    const form = byId('registerFormElement');
    if (!form) return;
    const passwordInput = byId('registerPassword');
    let signupStartedTracked = false;
    let credentialsReadyTracked = false;
    let nativeValidationTracked = false;

    const trackSignupStarted = () => {
      if (signupStartedTracked) return;
      signupStartedTracked = true;
      const deepLinked = new URLSearchParams(location.search).get('signup') === '1';
      trackSignupIntent(deepLinked ? 'deep-link' : 'registration');
      trackFunnel('SignupStarted');
    };

    const trackCredentialsReady = () => {
      trackSignupStarted();
      updateRegistrationPasswordGuidance();
      if (credentialsReadyTracked) return;
      const email = byId('registerEmail');
      const password = byId('registerPassword');
      if (!email?.value.trim() || !email.validity.valid || validatePasswordInput(password?.value || '')) return;
      credentialsReadyTracked = true;
      trackFunnel('SignupCredentialsReady');
    };

    // showAuth() deliberately moves focus to the first field for keyboard and
    // screen-reader users. Focus alone therefore is not evidence that a person
    // began registration. The first input (or a direct autofill submit below)
    // records the milestone without collecting field values.
    form.addEventListener('input', trackCredentialsReady, {passive: true});

    passwordInput?.addEventListener('blur', () => updateRegistrationPasswordGuidance({touched: true}));

    form.addEventListener('invalid', event => {
      if (nativeValidationTracked) return;
      nativeValidationTracked = true;
      setTimeout(() => { nativeValidationTracked = false; }, 0);
      const field = event.target;
      let reason = 'required_field';
      if (field?.id === 'registerEmail' && field.validity?.typeMismatch) reason = 'email_format';
      if (field?.id === 'registerPassword') reason = 'password_length';
      if (field?.id === 'registerTerms') reason = 'terms_required';
      trackFunnel('SignupValidationFailed', {reason});
    }, true);

    form.addEventListener('submit', async event => {
      event.preventDefault();
      authFlowRevision += 1;
      setText('registerError', '', false);
      setText('registerSuccess', '', false);
      const password = byId('registerPassword').value;
      const passwordError = validatePasswordInput(password);
      if (passwordError) {
        updateRegistrationPasswordGuidance({touched: true});
        const reason = password.length < 10 ? 'password_length' : 'password_rules';
        trackFunnel('SignupValidationFailed', {reason});
        return setText('registerError', passwordError);
      }
      trackCredentialsReady();
      trackFunnel('SignupSubmitted');
      const restore = setBusy(event.currentTarget, true, 'Creating account…');
      try {
        const email = byId('registerEmail').value.trim();
        const attribution = firstTouchAttribution();
        const planIntent = pendingPlanIntent();
        const {response, data} = await authRequest('/api/auth/register', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            password,
            fullName: byId('registerName')?.value.trim() || '',
            source: attribution.acquisition,
            placement: attribution.placement,
            campaign: attribution.campaign,
            creative: attribution.creative,
            intent: attribution.intent,
            plan: planIntent?.plan || null,
            termsAccepted: byId('registerTerms')?.checked === true,
            termsVersion: TERMS_VERSION,
          }),
        }, 'Creating your account took too long to confirm. Check your inbox before retrying; the account may already exist.');
        if (!response.ok || !data.success) {
          if (data.accountCreated && data.needsVerification) {
            trackFunnel('AccountCreated', {verification_delivery: 'failed'});
            showRegistrationPending(
              email,
              data.error || 'Your account exists, but the verification email could not be delivered. Use Resend verification email to try again.',
              {deliveryFailed: true},
            );
            return;
          }
          throw new Error(data.error || 'Registration failed.');
        }
        trackFunnel('AccountCreated', {verification_delivery: 'sent'});
        showRegistrationPending(email, data.message || 'Verification email sent.');
      } catch (error) {
        setText('registerError', error.message);
      } finally { restore(); }
    });
  }

  function wireRecovery() {
    byId('forgotPasswordFormElement')?.addEventListener('submit', async event => {
      event.preventDefault();
      setText('forgotPasswordError', '', false);
      const restore = setBusy(event.currentTarget, true, 'Sending…');
      try {
        const {response, data} = await authRequest('/api/auth/forgot-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: byId('forgotPasswordEmail').value.trim() }) }, 'Sending the reset email took too long. Check your inbox before retrying.');
        if (!response.ok) throw new Error(data.error || 'Could not send the reset email.');
        setText('forgotPasswordSuccess', data.message);
      } catch (error) { setText('forgotPasswordError', error.message); }
      finally { restore(); }
    });

    byId('resetPasswordFormElement')?.addEventListener('submit', async event => {
      event.preventDefault();
      setText('resetPasswordError', '', false);
      const password = byId('newPassword').value;
      const passwordError = validatePasswordInput(password);
      if (passwordError) return setText('resetPasswordError', passwordError);
      if (password !== byId('confirmNewPassword').value) return setText('resetPasswordError', 'Passwords do not match.');
      const restore = setBusy(event.currentTarget, true, 'Updating…');
      try {
        const {response, data} = await authRequest('/api/auth/reset-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: byId('resetPasswordForm').dataset.token, newPassword: password }) }, 'Updating your password took too long to confirm. Try signing in before submitting it again.');
        if (!response.ok) throw new Error(data.error || 'Password reset failed.');
        const resetForm = byId('resetPasswordForm');
        if (resetForm) delete resetForm.dataset.token;
        history.replaceState({}, document.title, location.pathname);
        showAuth('login');
        setText('loginSuccess', data.message || 'Password updated. Sign in with your new password.');
      } catch (error) { setText('resetPasswordError', error.message); }
      finally { restore(); }
    });

    byId('resendVerificationBtn')?.addEventListener('click', event => {
      void resendVerificationEmail(byId('loginEmail').value.trim(), {
        button: event.currentTarget,
        successId: 'loginSuccess',
        errorId: 'loginError',
      });
    });

    byId('registrationPendingResendBtn')?.addEventListener('click', event => {
      void resendVerificationEmail(byId('registrationPendingEmail').textContent.trim(), {
        button: event.currentTarget,
        successId: 'registrationPendingSuccess',
        errorId: 'registrationPendingError',
      });
    });

    byId('registrationPendingSigninBtn')?.addEventListener('click', () => {
      showAuth('login');
      hide('verificationNeeded');
      setText('loginError', '', false);
      setText('loginSuccess', 'Sign in here if you completed verification on another device.');
    });
  }

  window.completeOnboarding = async function completeOnboarding() {
    const name = byId('onboardingName').value.trim();
    setText('onboardingError', '', false);
    if (!name) {
      setText('onboardingError', 'Enter a name or choose Not now.');
      byId('onboardingName')?.focus();
      return;
    }
    const button = byId('onboardingContinueBtn');
    const skip = byId('onboardingSkipBtn');
    const original = button?.textContent || 'Save name';
    if (button) {
      button.disabled = true;
      button.textContent = 'Saving…';
    }
    if (skip) skip.disabled = true;
    try {
      const {response, data} = await authRequest('/api/account/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fullName: name }),
      }, 'Saving your profile took too long. Try again or choose Not now.');
      if (!response.ok || !data.success) throw new Error(data.error || 'Could not save your profile.');
      activeUser = data.user || { ...activeUser, fullName: name };
      window.currentUser = activeUser;
      window.profileManager?.updateProfile?.({ name, email: activeUser.email, initial: name.charAt(0).toUpperCase() });
      localStorage.setItem(window.STORAGE_KEYS?.HAS_ONBOARDED || 'crump_has_onboarded', 'true');
      try { localStorage.removeItem(profileNudgeKey()); } catch (_) {}
      startApp();
    } catch (error) {
      setText('onboardingError', error.message || 'Could not save your name. Try again or choose Not now.');
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = original;
      }
      if (skip) skip.disabled = false;
    }
  };

  window.exportChats = function exportChats() {
    const chats = window.chats || JSON.parse(localStorage.getItem(window.STORAGE_KEYS?.CHATS || 'crump_chats') || '[]');
    const url = URL.createObjectURL(new Blob([JSON.stringify(chats, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `ask-crump-conversations-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  window.logoutUser = async function logoutUser() {
    try {
      await window.deviceAuth.logout();
    } catch (error) {
      console.warn('[Auth] Sign-out confirmation unavailable:', error);
    } finally {
      location.replace('/app');
    }
  };

  window.restartTutorial = function restartTutorial() {
    window.closeSettings?.();
    window.tutorial?.restart?.();
  };

  document.addEventListener('DOMContentLoaded', () => {
    applyPasswordPolicyMarkup();
    wirePasswordVisibility();
    byId('onboardingContinueBtn')?.addEventListener('click', () => window.completeOnboarding());
    byId('onboardingSkipBtn')?.addEventListener('click', dismissProfileSetup);
    byId('v1ProfileNudgeAdd')?.addEventListener('click', openProfileSetup);
    byId('v1ProfileNudgeDismiss')?.addEventListener('click', dismissProfileSetup);
    window.addEventListener('crump:profile-updated', maybeOfferProfileSetup);
    byId('onboardingModal')?.addEventListener('keydown', event => {
      if (event.key === 'Escape') dismissProfileSetup();
    });
    byId('onboardingName')?.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        window.completeOnboarding();
      }
    });
    wireNavigation();
    wireExploreRegistrationLink();
    wireTerms();
    wireLogin();
    wireRegistration();
    wireRecovery();
    bootstrap().catch(error => { console.error('[Bootstrap]', error); showAuth(); });
  });
})();
