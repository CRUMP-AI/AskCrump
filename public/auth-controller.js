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
  let reauthenticationPreparation = Promise.resolve();
  let guestEntryFailure = null;
  let guestAccountSwitchPending = false;
  let onboardingProfileController = null;
  let onboardingProfileGeneration = 0;
  let onboardingBoundaryUnregister = null;
  let termsAcceptanceGeneration = 0;
  let termsBoundaryUnregister = null;
  let authIdentityStorageGeneration = 0;
  const AUTH_USER_CACHE_KEY = 'crump_user_cache_v4';
  const REGISTERED_ACCOUNT_HINT_KEY = 'askcrump.registered-account-seen-v1';
  const EXPLICIT_GUEST_INTENT_KEY = 'askcrump.explicit-guest-entry-v1';
  const TERMS_VERSION = '2026-08-01';
  const PLAN_INTENT_KEY = 'askcrump.pending-plan-intent';
  const CREATION_INTENT_KEY = 'askcrump.pending-creation-intent';
  const ACQUISITION_KEY = 'askcrump.acquisition-source';
  const ACQUISITION_PLACEMENT_KEY = 'askcrump.acquisition-placement';
  const FIRST_TOUCH_KEY = 'askcrump.first-touch-attribution';
  const WORKSPACE_SIGN_IN_SOURCE = 'workspace-signin';
  const FREE_REGISTRATION_ASSURANCE = 'Free includes up to 5 text messages in any rolling 24-hour window. Advanced tools require a paid plan. We’ll email a secure verification link, then ask you to set your password from that verified browser; no card required.';
  const PAID_REGISTRATION_ASSURANCE = 'We’ll email a secure verification link, then ask you to set your password from that verified browser. Creating your account does not start billing; checkout remains a separate confirmation.';
  const PLAN_INTENT_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  const PLAN_INTENT_DELIVERY_INTERVAL_MS = 500;
  const PLAN_INTENT_DELIVERY_MAX_ATTEMPTS = 32;
  const CREATION_INTENT_TTL_MS = 24 * 60 * 60 * 1000;
  const FIRST_TOUCH_TTL_MS = 24 * 60 * 60 * 1000;

  // This controller loads before the private app runtime. Keep an early
  // cross-tab identity generation so an account rotation cannot occur while
  // app.js is still loading and escape the later app-level storage listener.
  window.addEventListener('storage', event => {
    if (event.key === AUTH_USER_CACHE_KEY) authIdentityStorageGeneration += 1;
  });
  const PAID_PLAN_INTENTS = new Set(['professional', 'enterprise']);
  const CREATION_INTENTS = new Set(['document', 'presentation', 'resume', 'image', 'video', 'projects']);
  const CREATION_INTENT_EXPLORE_DESTINATIONS = Object.freeze({
    document: {href: '/ai-document-generator', label: 'See document examples first'},
    presentation: {href: '/ai-presentation-maker', label: 'See presentation examples first'},
    resume: {href: '/ai-resume-builder', label: 'See résumé examples first'},
    image: {href: '/#use-cases', label: 'See Image Studio details first'},
    video: {href: '/ai-video-generator', label: 'Explore Video Studio first'},
    projects: {href: '/ai-project-workspace', label: 'See how Projects work first'},
  });
  const REGISTRATION_CREATION_HANDOFFS = Object.freeze({
    document: {
      title: 'Create your document workspace.',
      description: 'After verification, Ask Crump preserves your request and opens plan options. Document creation requires a paid plan.',
    },
    presentation: {
      title: 'Create your presentation workspace.',
      description: 'After verification, Ask Crump preserves your request and opens plan options. Presentation creation requires a paid plan.',
    },
    resume: {
      title: 'Build your résumé workspace.',
      description: 'After verification, Ask Crump preserves your request and opens plan options. Résumé creation requires a paid plan.',
    },
    image: {
      title: 'Open your Image Studio.',
      description: 'After verification, Ask Crump preserves your request and opens plan options. Image Studio requires a paid plan.',
    },
    video: {
      title: 'Open your Video Studio.',
      description: 'After verification, Ask Crump preserves your request and opens plan options. Video Studio requires a paid plan. After upgrading, choose a generation mode, see its Crump Credit cost, and find completed clips in Files.',
    },
    projects: {
      title: 'Open your private Project workspace.',
      description: 'After verification, Ask Crump preserves your conversation and opens plan options. Projects require a paid plan.',
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
    'founder-outreach', 'paid-social',
  ]);
  const ACQUISITION_PLACEMENTS = new Set([
    'response-share', 'profile-link', 'workflow-guide', 'organic-social',
    'creator-cohort', 'facebook-paid',
  ]);
  const CAMPAIGN_REGISTRY = Object.freeze({
    'presentation-proof-current': {
      intent: 'presentation',
      acquisitions: new Set(['facebook', 'instagram']),
      placements: new Set(['profile-link', 'organic-social']),
      creatives: new Set(['fb-static', 'ig-story']),
      touchpoints: new Set([
        'facebook|profile-link|',
        'instagram|profile-link|',
        'facebook|organic-social|fb-static',
        'instagram|organic-social|ig-story',
      ]),
    },
    'real-product-continuity': {
      intent: 'projects',
      acquisitions: new Set(['facebook', 'instagram']),
      placements: new Set(['profile-link', 'organic-social']),
      creatives: new Set(['continuity-feed', 'continuity-story']),
    },
    'rough-to-useful-v2': {
      intent: 'projects',
      acquisitions: new Set(['facebook', 'instagram', 'paid-social']),
      placements: new Set(['organic-social', 'facebook-paid']),
      creatives: new Set(['rough-to-useful-current-feed', 'rough-to-useful-current-reel']),
      touchpoints: new Set([
        'facebook|organic-social|rough-to-useful-current-feed',
        'facebook|organic-social|rough-to-useful-current-reel',
        'instagram|organic-social|rough-to-useful-current-feed',
        'paid-social|facebook-paid|rough-to-useful-current-feed',
      ]),
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
    'word-or-pdf-decision': {
      intent: 'document',
      acquisitions: new Set(['organic-search']),
      placements: new Set(['workflow-guide']),
      creatives: new Set(['search-article']),
      touchpoints: new Set([
        'organic-search|workflow-guide|search-article',
      ]),
    },
    'resume-bullet-truth-audit': {
      intent: 'resume',
      acquisitions: new Set(['organic-search']),
      placements: new Set(['workflow-guide']),
      creatives: new Set(['search-article']),
      touchpoints: new Set([
        'organic-search|workflow-guide|search-article',
      ]),
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
    guest: {containerId: 'guestEntryForm', fieldId: null},
    register: {containerId: 'registerForm', fieldId: 'registerEmail'},
    forgot: {containerId: 'forgotPasswordForm', fieldId: 'forgotPasswordEmail'},
    reset: {containerId: 'resetPasswordForm', fieldId: 'newPassword'},
  });

  function authRequest(url, options, timeoutMessage) {
    return window.CrumpAuthTransport.request(url, options, {timeoutMessage});
  }

  function captureExpectedOwnerBoundary(generation) {
    const boundary = window.CrumpAuthBoundary;
    const ownerId = String(
      typeof boundary?.authenticatedUserId === 'function'
        ? boundary.authenticatedUserId()
        : activeUser?.id || window.currentUser?.id || ''
    ).trim();
    const rawRevision = typeof boundary?.revision === 'function' ? boundary.revision() : 0;
    const revision = Number(rawRevision);
    return Object.freeze({
      ownerId,
      revision: Number.isFinite(revision) ? revision : 0,
      authFlowRevision,
      generation,
    });
  }

  function expectedOwnerBoundaryIsCurrent(snapshot, generation) {
    if (!snapshot?.ownerId || snapshot.generation !== generation) return false;
    const boundary = window.CrumpAuthBoundary;
    const currentOwnerId = String(
      typeof boundary?.authenticatedUserId === 'function'
        ? boundary.authenticatedUserId()
        : window.currentUser?.id || activeUser?.id || ''
    ).trim();
    const rawRevision = typeof boundary?.revision === 'function' ? boundary.revision() : 0;
    const revision = Number(rawRevision);
    return currentOwnerId === snapshot.ownerId
      && String(window.currentUser?.id || '').trim() === snapshot.ownerId
      && String(activeUser?.id || '').trim() === snapshot.ownerId
      && (Number.isFinite(revision) ? revision : 0) === snapshot.revision
      && authFlowRevision === snapshot.authFlowRevision;
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
    const creativeToken = attributionToken(candidate?.creative);
    const campaignToken = attributionToken(candidate?.campaign);
    const specification = CAMPAIGN_REGISTRY[campaignToken];
    const touchpoint = `${acquisition}|${placement || ''}|${creativeToken}`;
    const campaign = specification
      && specification.acquisitions.has(acquisition)
      && specification.placements.has(placement)
      && specification.intent === intent
      && (!specification.touchpoints || specification.touchpoints.has(touchpoint))
      ? campaignToken
      : null;
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
    try {
      const delivery = window.va?.('event', {name, data: {...funnelContext(), ...data}});
      delivery?.catch?.(() => {});
      return true;
    } catch (_) {
      // Measurement must never become an authentication dependency. Vercel
      // Analytics can be blocked, injected late, or throw in privacy-focused
      // browsers; the visible auth flow still has to continue.
      return false;
    }
  }

  function trackSignupIntent(locationName) {
    if (signupIntentTracked) return;
    signupIntentTracked = true;
    trackFunnel('SignupIntent', {location: locationName});
  }

  function capturePlanIntent() {
    const context = funnelContext();
    const params = new URLSearchParams(location.search);
    if (isFreeGuestEntryRequest(params)) {
      discardPendingPlanIntent();
      return;
    }
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

  function isFreeGuestEntryRequest(params = new URLSearchParams(location.search)) {
    return params.get('plan') === 'free' && params.get('signup') !== '1';
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
    button.textContent = creationKind === 'image'
      ? 'Create account & review Image Studio access'
      : (plan?.button || (creation ? 'Create account & continue' : 'Create free account'));
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
    if (isFreeGuestEntryRequest(params)) {
      try { localStorage.removeItem(CREATION_INTENT_KEY); } catch (_) {}
      return;
    }
    const kind = creationIntentValue(params.get('intent'));
    if (!kind) {
      if (params.has('intent') || params.get('signup') === '1') {
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
    if (isFreeGuestEntryRequest()) return '';
    const intent = pendingCreationIntent();
    if (!intent) return '';

    const deliver = () => {
      const consumed = event => {
        if (event.detail?.kind !== intent.kind) return;
        if (Number(event.detail?.capturedAt || 0) !== intent.capturedAt) return;
        window.removeEventListener('crump:creation-intent-consumed', consumed);
        try {
          const stored = JSON.parse(localStorage.getItem(CREATION_INTENT_KEY) || 'null');
          if (
            creationIntentValue(stored?.kind) === intent.kind
            && Number(stored?.capturedAt || 0) === intent.capturedAt
          ) localStorage.removeItem(CREATION_INTENT_KEY);
        } catch (_) {
          try { localStorage.removeItem(CREATION_INTENT_KEY); } catch (_) {}
        }
        const url = new URL(location.href);
        if (creationIntentValue(url.searchParams.get('intent')) === intent.kind) {
          url.searchParams.delete('intent');
          if (intent.kind === 'image') {
            url.searchParams.delete('plan');
            url.searchParams.delete('signup');
            url.searchParams.delete('source');
          }
          history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);
        }
        if (intent.kind === 'image') discardPendingPlanIntent();
      };
      window.addEventListener('crump:creation-intent-consumed', consumed);
      window.dispatchEvent(new CustomEvent('crump:creation-intent', {detail: intent}));
    };

    if (document.documentElement.dataset.crumpBodyRuntime === 'ready') {
      queueMicrotask(deliver);
    } else {
      window.addEventListener('crump:body-runtime-ready', deliver, {once: true});
    }
    return intent.kind;
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

  function discardPendingPlanIntent() {
    pagePlanIntent = null;
    clearTimeout(planIntentDeliveryTimer);
    planIntentDeliveryTimer = 0;
    planIntentDeliveryAttempts = 0;
    planIntentDeliveryKey = '';
    if (planIntentConsumedHandler) {
      window.removeEventListener('crump:plan-intent-consumed', planIntentConsumedHandler);
      planIntentConsumedHandler = null;
    }
    try { localStorage.removeItem(PLAN_INTENT_KEY); } catch (_) {}
  }

  function dispatchPendingPlanIntent() {
    if (isFreeGuestEntryRequest()) {
      discardPendingPlanIntent();
      return;
    }
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

  // Vision demo mode (preview builds only): when the demo is requested, the
  // demo module owns the stage and the real auth flow must not run — it would
  // otherwise re-hide the app after the demo reveals it (?demo=1 blank page).
  function isVisionDemoRequested() {
    try {
      var host = String(window.location.hostname || '').toLowerCase();
      if (!/\.vercel\.app$/.test(host)) return false;
      if (window.__crumpVisionDemo === true) return true;
      var hash = String(window.location.hash || '').toLowerCase();
      if (hash === '#demo' || hash.indexOf('#demo&') === 0) return true;
      return /(^|[?&])demo=1(&|#|$)/.test(String(window.location.search || ''));
    } catch (_) {
      return false;
    }
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

  function hasReturningDeviceHint() {
    let cachedUser = null;
    try { cachedUser = window.deviceAuth?.cachedUser?.() || null; } catch (_) {}
    if (cachedUser && !isGuestUser(cachedUser)) {
      try { localStorage.setItem(REGISTERED_ACCOUNT_HINT_KEY, '1'); } catch (_) {}
    }
    let registeredAccountSeen = false;
    try { registeredAccountSeen = localStorage.getItem(REGISTERED_ACCOUNT_HINT_KEY) === '1'; } catch (_) {}
    return Boolean(cachedUser || registeredAccountSeen);
  }

  function rememberRegisteredAccount(user) {
    if (!user || isGuestUser(user)) return;
    try { localStorage.setItem(REGISTERED_ACCOUNT_HINT_KEY, '1'); } catch (_) {}
  }

  function routePasswordSetupRequiredUser(user, serverSettings) {
    if (!user?.isVerified || isGuestUser(user) || !user.passwordSetupRequired) return false;
    rememberRegisteredAccount(user);
    activeUser = user;
    window.currentUser = user;
    window.configureUserStorage?.(user.id);
    applyServerSettings(serverSettings);
    setText('loginSuccess', '', false);
    configurePasswordForm('setup');
    showAuth('reset');
    return true;
  }

  function consumeExplicitGuestEntryIntent() {
    try {
      const stored = sessionStorage.getItem(EXPLICIT_GUEST_INTENT_KEY);
      sessionStorage.removeItem(EXPLICIT_GUEST_INTENT_KEY);
      const createdAt = JSON.parse(stored || 'null')?.createdAt;
      const age = Date.now() - createdAt;
      return Number.isFinite(createdAt) && age >= 0 && age <= 30_000;
    } catch (_) {
      return false;
    }
  }

  async function prepareAuthenticatedWorkspace() {
    const runtime = window.CrumpWorkspaceRuntime;
    if (!runtime || typeof runtime.load !== 'function') {
      throw new Error('Ask Crump could not prepare your workspace. Reload and try again.');
    }
    await runtime.load();
  }

  function recordWorkspaceOpenedWhenVisible() {
    if (!activeUser) return;
    void window.CrumpAnalytics?.recordWorkspaceOpenedWhenVisible?.();
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
    recordWorkspaceOpenedWhenVisible();
    setTimeout(() => window.tutorial?.autoStart?.(), 450);
    const creationKind = dispatchPendingCreationIntent();
    if (creationKind !== 'image') dispatchPendingPlanIntent();
    applyServerAllowance(activeUser);
    renderFreeAllowancePill();
    void refreshFreeAllowanceFromServer();
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
    if (isGuestUser(window.currentUser || activeUser)) {
      nudge.hidden = true;
      return;
    }
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

  function scrubOnboardingAuthBoundary() {
    onboardingProfileGeneration += 1;
    onboardingProfileController?.abort?.();
    onboardingProfileController = null;
    const modal = byId('onboardingModal');
    const focusedInModal = Boolean(modal?.contains(document.activeElement));
    const name = byId('onboardingName');
    if (name) {
      name.value = '';
      name.removeAttribute('aria-busy');
    }
    setText('onboardingError', '', false);
    hide('onboardingModal');
    if (focusedInModal) document.activeElement?.blur?.();
    const button = byId('onboardingContinueBtn');
    if (button) {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.textContent = 'Save name';
    }
    const skip = byId('onboardingSkipBtn');
    if (skip) skip.disabled = false;
  }

  function ensureOnboardingBoundaryRegistration() {
    if (onboardingBoundaryUnregister || typeof window.CrumpAuthBoundary?.register !== 'function') return;
    onboardingBoundaryUnregister = window.CrumpAuthBoundary.register(
      'auth-onboarding-profile',
      scrubOnboardingAuthBoundary,
    );
  }

  function captureOnboardingAuthBoundary(generation) {
    ensureOnboardingBoundaryRegistration();
    return captureExpectedOwnerBoundary(generation);
  }

  function onboardingAuthBoundaryIsCurrent(snapshot) {
    return expectedOwnerBoundaryIsCurrent(snapshot, onboardingProfileGeneration);
  }

  ensureOnboardingBoundaryRegistration();
  window.addEventListener('crump:body-runtime-ready', ensureOnboardingBoundaryRegistration, {once: true});

  function routeAuthenticatedUser(user) {
    rememberRegisteredAccount(user);
    activeUser = user;
    window.currentUser = user;
    window.configureUserStorage?.(user.id);
    const profileManager = window.CrumpProfileState?.bindAuthenticatedUser?.(user)
      || window.profileManager;
    profileManager?.applyServerSubscription?.(user);
    if (!user.termsAcceptedAt) {
      hide('authContainer');
      show('tosModal', 'flex');
      return;
    }
    if (user.fullName) {
      localStorage.setItem(window.STORAGE_KEYS?.HAS_ONBOARDED || 'crump_has_onboarded', 'true');
      profileManager?.updateProfile?.({ name: user.fullName, email: user.email });
    }
    startApp();
    if (!user.fullName) maybeOfferProfileSetup();
  }

  // ---- Free text access -----------------------------------------------
  // Guest and registered-Free users share one server-authoritative rolling
  // allowance. Registration converts the same account, so neither the chat
  // nor its remaining allowance resets. The browser only renders values the
  // server returned; it never predicts or decrements usage locally.
  const FREE_TEXT_MESSAGE_LIMIT = 5;
  const PAID_TIERS = new Set(['professional', 'enterprise']);
  let freeAllowanceState = null;

  function isGuestUser(user) {
    return Boolean(user?.isGuest);
  }

  function explicitSignInPath(source = WORKSPACE_SIGN_IN_SOURCE) {
    const params = new URLSearchParams({
      source: String(source || WORKSPACE_SIGN_IN_SOURCE),
      plan: 'free',
    });
    return `/app?${params.toString()}`;
  }

  function renderAccountAccessControls(user) {
    const guest = isGuestUser(user);
    const button = byId('signOutBtn');
    const label = byId('signOutLabel');
    const help = byId('signOutHelp');
    button?.classList.toggle('settings-danger', !guest);
    button?.classList.toggle('settings-row-action', guest);
    if (label) label.textContent = guest ? 'Sign in to another account' : 'Sign out';
    if (help) {
      help.textContent = guest
        ? 'Open sign in without ending this guest session'
        : 'Log out of this device';
    }
  }

  function renderGuestSigninNotice(visible) {
    const notice = byId('guestSigninNotice');
    if (notice) notice.hidden = !visible;
  }

  function effectiveTier(user = window.currentUser || activeUser) {
    return String(user?.subscriptionTier || user?.tier || '').trim().toLowerCase();
  }

  function hasPaidToolAccess(user = window.currentUser || activeUser) {
    return Boolean(user?.internalAccess) || PAID_TIERS.has(effectiveTier(user));
  }

  function isFreeTextUser(user = window.currentUser || activeUser) {
    return isGuestUser(user) || effectiveTier(user) === 'free';
  }

  function finiteNumber(...values) {
    for (const value of values) {
      if (value === null || value === undefined || value === '') continue;
      const number = Number(value);
      if (Number.isFinite(number)) return number;
    }
    return null;
  }

  function allowanceObject(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const candidates = [
      payload.freeMessageAllowance,
      payload.dailyUsage?.freeMessageAllowance,
      payload.usage?.freeMessageAllowance,
      payload.user?.freeMessageAllowance,
      payload.data?.freeMessageAllowance,
      payload.data?.user?.freeMessageAllowance,
    ];
    return candidates.find(candidate => candidate && typeof candidate === 'object') || null;
  }

  function parseServerAllowance(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const allowance = allowanceObject(payload) || {};
    const limit = finiteNumber(
      allowance.limit,
      payload.freeMessageLimit,
      payload.user?.freeMessageLimit,
      payload.data?.freeMessageLimit,
      payload.data?.user?.freeMessageLimit,
    );
    const used = finiteNumber(
      allowance.used,
      payload.freeMessagesUsed,
      payload.user?.freeMessagesUsed,
      payload.data?.freeMessagesUsed,
      payload.data?.user?.freeMessagesUsed,
    );
    const remaining = finiteNumber(
      allowance.remaining,
      payload.freeMessagesRemaining,
      payload.user?.freeMessagesRemaining,
      payload.data?.freeMessagesRemaining,
      payload.data?.user?.freeMessagesRemaining,
    );
    // A limit by itself is product configuration, not an authoritative usage
    // snapshot. Keep the neutral checking state until the server supplies at
    // least one observed count.
    if (used === null && remaining === null) return null;
    const normalizedLimit = Math.max(1, Math.floor(limit ?? FREE_TEXT_MESSAGE_LIMIT));
    const normalizedUsed = Math.max(0, Math.min(normalizedLimit, Math.floor(
      used ?? Math.max(0, normalizedLimit - (remaining ?? normalizedLimit)),
    )));
    const normalizedRemaining = Math.max(0, Math.min(normalizedLimit, Math.floor(
      remaining ?? Math.max(0, normalizedLimit - normalizedUsed),
    )));
    return {
      limit: normalizedLimit,
      used: normalizedUsed,
      remaining: normalizedRemaining,
      windowKind: String(allowance.windowKind || payload.freeMessageWindowKind || 'rolling_24h'),
      windowSeconds: Math.max(1, Math.floor(finiteNumber(allowance.windowSeconds, payload.freeMessageWindowSeconds) ?? 86400)),
      nextAvailableAt: allowance.nextAvailableAt
        || payload.freeMessageNextAvailableAt
        || payload.user?.freeMessageNextAvailableAt
        || payload.data?.freeMessageNextAvailableAt
        || payload.data?.user?.freeMessageNextAvailableAt
        || null,
    };
  }

  function applyServerAllowance(payload) {
    const allowance = parseServerAllowance(payload);
    if (!allowance) return false;
    const user = window.currentUser || activeUser;
    freeAllowanceState = {...allowance, ownerId: String(user?.id || '')};
    if (user) {
      user.freeMessageAllowance = {...allowance};
      user.freeMessageLimit = allowance.limit;
      user.freeMessagesUsed = allowance.used;
      user.freeMessagesRemaining = allowance.remaining;
      user.freeMessageNextAvailableAt = allowance.nextAvailableAt;
    }
    renderFreeAllowancePill();
    window.dispatchEvent(new CustomEvent('crump:free-message-allowance', {detail: {...allowance}}));
    return true;
  }

  async function refreshFreeAllowanceFromServer() {
    const user = window.currentUser || activeUser;
    if (!isFreeTextUser(user) || hasPaidToolAccess(user)) return false;
    try {
      const {response, data} = await authRequest(
        '/api/usage/check',
        {method: 'GET', cache: 'no-store'},
        'Checking your free message allowance took too long.',
      );
      if (!response.ok) {
        applyServerAllowance(data);
        return false;
      }
      return applyServerAllowance(data);
    } catch (_) {
      // Keep the neutral "checking" state. A send always performs the same
      // server-authoritative preflight before accepting a message.
      return false;
    }
  }

  function nextFreeMessageCopy(allowance = freeAllowanceState) {
    const timestamp = Date.parse(String(allowance?.nextAvailableAt || ''));
    if (!Number.isFinite(timestamp)) return 'A message becomes available when the oldest message leaves the rolling 24-hour window.';
    const formatted = new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(timestamp));
    return `Your next free text message becomes available ${formatted}.`;
  }

  function renderFreeAllowancePill() {
    const user = window.currentUser || activeUser;
    renderAccountAccessControls(user);
    const existing = byId('freeTextAllowancePill') || byId('guestPreviewPill');
    const ownerId = String(user?.id || '');
    if (freeAllowanceState?.ownerId && freeAllowanceState.ownerId !== ownerId) freeAllowanceState = null;
    if (!isFreeTextUser(user) || hasPaidToolAccess(user)) {
      freeAllowanceState = null;
      document.body.classList.remove('free-allowance-active');
      document.body.classList.remove('guest-active');
      existing?.remove();
      return;
    }
    document.body.classList.add('free-allowance-active');
    document.body.classList.toggle('guest-active', isGuestUser(user));
    if (!freeAllowanceState) {
      const initial = parseServerAllowance(user);
      if (initial) freeAllowanceState = {...initial, ownerId};
    }
    let pill = existing;
    if (!pill) {
      pill = document.createElement('div');
      pill.id = 'freeTextAllowancePill';
      pill.className = 'free-text-allowance-pill';
      pill.setAttribute('role', 'region');
      pill.setAttribute('aria-label', 'Free text message allowance');
      const copy = document.createElement('span');
      copy.className = 'free-text-allowance-copy';
      const link = document.createElement('a');
      link.href = '#';
      link.className = 'free-text-allowance-link';
      link.addEventListener('click', event => {
        event.preventDefault();
        if (isGuestUser(window.currentUser || activeUser)) showGuestWall();
        else showPaidToolPrompt('More messages');
      });
      const signIn = document.createElement('a');
      signIn.href = explicitSignInPath();
      signIn.className = 'free-text-allowance-link free-text-allowance-signin';
      signIn.textContent = 'Sign in';
      signIn.setAttribute('aria-label', 'Sign in to an existing Ask Crump account');
      pill.append(copy, link, signIn);
      document.querySelector('.v1-workspace-header')?.append(pill);
    }
    const guest = isGuestUser(user);
    const copy = pill.querySelector('.free-text-allowance-copy');
    const link = pill.querySelector('.free-text-allowance-link');
    const signIn = pill.querySelector('.free-text-allowance-signin');
    if (copy) {
      copy.textContent = freeAllowanceState
        ? `${guest ? 'Guest' : 'Free'} · ${freeAllowanceState.remaining} of ${freeAllowanceState.limit} free text messages left`
        : `${guest ? 'Guest' : 'Free'} · checking text allowance…`;
      copy.title = freeAllowanceState
        ? `${freeAllowanceState.remaining} of ${freeAllowanceState.limit} free text messages left in the last 24 hours.${freeAllowanceState.remaining === 0 ? ` ${nextFreeMessageCopy()}` : ''}`
        : 'Ask Crump is checking the server-authoritative rolling 24-hour allowance.';
    }
    if (link) link.textContent = guest ? 'Save conversation' : 'Compare plans';
    if (signIn) signIn.hidden = !guest;
  }

  function showGuestNote(text) {
    const note = byId('guestWallNote');
    if (!note) return;
    note.textContent = text;
    note.hidden = false;
  }

  function showGuestWall() {
    showAuth('register');
    const reset = freeAllowanceState?.remaining === 0 ? ` ${nextFreeMessageCopy()}` : '';
    showGuestNote(`Create a free account to preserve this conversation and your remaining allowance. Signing up does not add another five messages. More messages and advanced tools require a paid plan.${reset}`);
  }

  function showPaidToolPrompt(featureLabel = 'That tool') {
    const user = window.currentUser || activeUser;
    if (hasPaidToolAccess(user)) return true;
    if (isGuestUser(user)) {
      showAuth('register');
      showGuestNote(`${featureLabel} requires a paid plan. Create a free account to preserve this conversation and its remaining allowance; signing up does not add another five messages. You can review a paid plan after verification.`);
      return false;
    }
    window.showUpgradePrompt?.({
      accessCode: 'SUBSCRIPTION_REQUIRED',
      plan: 'professional',
      source: 'advanced_tool_guard',
    });
    window.showToast?.(`${featureLabel} requires a paid plan.`, 'info');
    return false;
  }

  function requireOwnedWorkspace(featureLabel = 'That workspace') {
    const user = window.currentUser || activeUser;
    if (!user?.id) {
      window.showToast?.(`${featureLabel} is unavailable until account access finishes loading.`, 'info');
      return false;
    }
    if (isGuestUser(user)) {
      showAuth('register');
      showGuestNote(`Create a free account to keep and revisit your private ${featureLabel.toLowerCase()}. Creating or changing premium work still requires a paid plan.`);
      return false;
    }
    return true;
  }

  function handleGuestChatError(error) {
    const code = String(error?.code || '').toUpperCase();
    applyServerAllowance(error?.data || error);
    if (code === 'FREE_TEXT_LIMIT_REACHED' || code === 'GUEST_LIMIT_REACHED') {
      if (isGuestUser(window.currentUser || activeUser)) showGuestWall();
      else {
        showPaidToolPrompt('More messages');
        window.showToast?.(nextFreeMessageCopy(), 'info');
      }
    } else if (code === 'GUEST_ACCOUNT_REQUIRED') {
      const match = /to use (.+?) —/.exec(String(error?.message || ''));
      const feature = match ? match[1].charAt(0).toUpperCase() + match[1].slice(1) : 'That feature';
      showPaidToolPrompt(feature);
    }
  }

  async function enterAsGuest() {
    guestEntryFailure = null;
    try {
      const {response, data} = await authRequest(
        '/api/auth/guest',
        {method: 'POST'},
        'Starting a guest preview took too long. Try again.',
      );
      if (!response.ok || !data?.success) {
        guestEntryFailure = {
          code: String(data?.code || '').toUpperCase(),
          retryAfter: Number(data?.retryAfter || response.headers.get('Retry-After') || 0),
          status: response.status,
        };
        return false;
      }
      const session = await window.deviceAuth.checkSession();
      // The guest endpoint deliberately preserves any valid session. Another
      // tab may have completed sign-in after bootstrap's first session check,
      // so the authoritative follow-up may be a registered user rather than a
      // guest. Route either authenticated identity instead of showing a false
      // guest-entry failure.
      if (!session.authenticated || !session.data?.user) {
        guestEntryFailure = {code: 'SESSION_NOT_READY', retryAfter: 0, status: 503};
        return false;
      }
      if (routePasswordSetupRequiredUser(session.data.user, session.data.settings)) return true;
      await prepareAuthenticatedWorkspace();
      activeUser = session.data.user;
      window.currentUser = activeUser;
      window.configureUserStorage?.(activeUser.id);
      applyServerSettings(session.data.settings);
      if (new URLSearchParams(location.search).get('signup') === '1') trackSignupIntent('deep-link');
      routeAuthenticatedUser(activeUser);
      return true;
    } catch (error) {
      guestEntryFailure = {
        code: String(error?.code || 'GUEST_ENTRY_UNAVAILABLE').toUpperCase(),
        retryAfter: 0,
        status: 0,
      };
      return false;
    }
  }

  function formatGuestRetryDelay(value) {
    const seconds = Math.max(0, Number(value) || 0);
    if (!seconds) return '';
    if (seconds < 120) return 'about a minute';
    if (seconds < 3600) return `about ${Math.ceil(seconds / 60)} minutes`;
    if (seconds < 7200) return 'about 1 hour';
    if (seconds < 86400) return `about ${Math.ceil(seconds / 3600)} hours`;
    return 'about a day';
  }

  function showGuestEntryFailure(failure = {}) {
    const code = String(failure.code || '').toUpperCase();
    const delay = formatGuestRetryDelay(failure.retryAfter);
    let message = 'Ask Crump could not start this private preview yet. You did nothing wrong. Try again in a moment, or sign in if you already have an account.';
    if (code === 'RATE_LIMITED') {
      message = `Free preview has been started several times from this browser or network today. You did nothing wrong. Try again${delay ? ` in ${delay}` : ' later'}, or sign in if you already have an account.`;
    } else if (code === 'GUEST_MODE_DISABLED') {
      message = 'Free preview is temporarily paused. You did nothing wrong. Try again later, or sign in if you already have an account.';
    }
    const retryLink = byId('guestEntryRetryLink');
    if (retryLink) retryLink.href = `${location.pathname}${location.search || '?plan=free'}`;
    setText('guestEntryMessage', message);
    showAuth('guest');
  }

  window.CrumpAccess = Object.freeze({
    isGuest: () => isGuestUser(window.currentUser || activeUser),
    isFree: () => isFreeTextUser(window.currentUser || activeUser) && !hasPaidToolAccess(window.currentUser || activeUser),
    hasPaidToolAccess: () => hasPaidToolAccess(window.currentUser || activeUser),
    applyServerAllowance,
    requireOwnedWorkspace,
    requirePaidTool: showPaidToolPrompt,
    onChatError: handleGuestChatError,
    refreshAllowance: refreshFreeAllowanceFromServer,
  });

  // Compatibility for modules loaded from an older PWA cache. This alias no
  // longer mutates usage: only a server response may update the allowance.
  window.CrumpGuest = Object.freeze({
    isGuest: window.CrumpAccess.isGuest,
    noteMessageSent: applyServerAllowance,
    onChatError: handleGuestChatError,
    showAccountPrompt: showPaidToolPrompt,
    refreshPill: renderFreeAllowancePill,
  });

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
    renderGuestSigninNotice(normalizedView === 'login' && guestAccountSwitchPending);
    show(AUTH_VIEWS[normalizedView].containerId);
    focusAuthView(normalizedView);
  }

  function configurePasswordForm(mode = 'reset') {
    const setup = mode === 'setup';
    const form = byId('resetPasswordForm');
    if (form) form.dataset.mode = setup ? 'setup' : 'reset';
    const eyebrow = byId('passwordFormEyebrow');
    const title = byId('passwordFormTitle');
    const description = byId('passwordFormDescription');
    const submit = byId('passwordFormSubmit');
    const footer = byId('passwordFormFooter');
    if (eyebrow) eyebrow.textContent = setup ? 'EMAIL VERIFIED' : 'ACCOUNT RECOVERY';
    if (title) title.textContent = setup ? 'Secure your password.' : 'Set new password.';
    if (description) description.textContent = setup
      ? 'Set a fresh password now. The password entered before inbox verification was deliberately disabled.'
      : 'Choose a new password for your account.';
    if (submit) submit.textContent = setup ? 'Set Password & Continue' : 'Reset Password';
    if (footer) footer.style.display = setup ? 'none' : '';
    setText('resetPasswordError', '', false);
    setText('resetPasswordSuccess', setup ? 'Email verified. Finish securing your account to open the workspace.' : '', setup);
  }

  function handleAuthenticationRequired(event) {
    if (String(event.detail?.reason || '') !== 'checkout') return;
    authFlowRevision += 1;
    activeUser = null;
    window.currentUser = null;
    reauthenticationPreparation = Promise.resolve(window.deviceAuth?.clearLocalState?.()).catch(() => {});
    showAuth('login');
    setText(
      'loginError',
      'Your session expired. Sign in again to return to your selected purchase. Nothing has been charged.',
    );
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
      }, 'Submitting the verification email request took too long. It may already be queued; check your inbox before retrying.');
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
      already_verified: 'This email is already verified. Sign in, or use Forgot password if you have not set one yet.',
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
    if (isVisionDemoRequested()) return; // demo module owns the stage
    captureCreationIntent();
    configureRegistrationExploreLink();
    capturePlanIntent();
    configureRegistrationHandoff();
    const params = new URLSearchParams(location.search);
    const signupRequested = params.get('signup') === '1';
    const signInRequested = (params.get('source') || '').toLowerCase().includes('signin');
    const explicitGuestIntent = consumeExplicitGuestEntryIntent();
    const explicitGuestRequested = params.get('plan') === 'free'
      && !signupRequested && !signInRequested && explicitGuestIntent;
    const returningDeviceHint = hasReturningDeviceHint();
    const resetToken = params.get('token');
    if (resetToken) {
      configurePasswordForm('reset');
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
    const bootstrapIdentityStorageGeneration = authIdentityStorageGeneration;
    await window.CrumpAPI?.ready;
    // Bootstrap owns the decision to adopt or clear this identity. Keep the
    // transport probe non-committing until its auth-flow generation is still
    // current; otherwise a delayed prior-account response could repopulate
    // DeviceAuth and its shared identity cache after a same-page login.
    const session = await window.deviceAuth.checkSession({commit: false});
    if (authFlowRevision !== bootstrapAuthFlowRevision) return;
    if (authIdentityStorageGeneration !== bootstrapIdentityStorageGeneration) return bootstrap();
    if (!session.unavailable && session.authenticated && session.data?.user) {
      window.deviceAuth.acceptSession?.(session.data);
    } else if (!session.unavailable && !session.authenticated) {
      window.deviceAuth.clearLocalState?.();
    }
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
      // Guest preview: a genuinely new visitor starts chatting right away
      // in a bounded guest session. A device holding an account keeps the
      // classic sign-in path, a pending email verification always
      // finishes on the auth screens, and an explicit Sign in link
      // (source=*signin*) always lands on the login form it promised.
      const cachedHintUser = window.deviceAuth?.cachedUser?.() || null;
      let registeredAccountSeen = false;
      try { registeredAccountSeen = localStorage.getItem(REGISTERED_ACCOUNT_HINT_KEY) === '1'; } catch (_) {}
      const accountOnDevice = registeredAccountSeen || (returningDeviceHint && !cachedHintUser?.isGuest);
      const mayStartGuest = !signupRequested
        && !verification
        && !signInRequested
        && (explicitGuestRequested || !accountOnDevice);
      if (mayStartGuest && await enterAsGuest()) return;
      if (authFlowRevision !== bootstrapAuthFlowRevision) return;
      if (signupRequested) {
        showAuth('register');
        trackSignupIntent('deep-link');
      } else if (mayStartGuest && guestEntryFailure) {
        showGuestEntryFailure(guestEntryFailure);
      } else {
        showAuth('login');
      }
      if (verification) showVerificationResult(verification);
      return;
    }
    if (signInRequested && isGuestUser(session.data.user)) {
      // An explicit Sign in action must keep its promise even when this
      // browser currently holds a guest session. Keep that guest session
      // active while credentials are entered, disclose that successful login
      // switches accounts, and do not mint another guest.
      guestAccountSwitchPending = true;
      showAuth('login');
      return;
    }
    if (signupRequested && isGuestUser(session.data.user)) {
      activeUser = session.data.user;
      window.currentUser = activeUser;
      window.configureUserStorage?.(activeUser.id);
      applyServerSettings(session.data.settings);
      showAuth('register');
      trackSignupIntent('deep-link');
      return;
    }
    rememberRegisteredAccount(session.data.user);
    if (routePasswordSetupRequiredUser(session.data.user, session.data.settings)) return;
    await prepareAuthenticatedWorkspace();
    if (authFlowRevision !== bootstrapAuthFlowRevision) return;
    if (authIdentityStorageGeneration !== bootstrapIdentityStorageGeneration) return bootstrap();
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
    byId('showForgotPasswordLink')?.addEventListener('click', event => {
      event.preventDefault();
      openPasswordRecoveryFromLogin();
    });
    byId('loginRecoveryAction')?.addEventListener('click', openPasswordRecoveryFromLogin);
    byId('showLoginFromForgot')?.addEventListener('click', event => { event.preventDefault(); showAuth('login'); });
    byId('showLoginFromReset')?.addEventListener('click', event => {
      event.preventDefault();
      const resetForm = byId('resetPasswordForm');
      if (resetForm) delete resetForm.dataset.token;
      history.replaceState({}, document.title, location.pathname);
      configurePasswordForm('reset');
      showAuth('login');
    });
  }

  function scrubTermsAuthBoundary() {
    termsAcceptanceGeneration += 1;
    hide('tosModal');
    const checkbox = byId('tosAccept');
    if (checkbox) checkbox.checked = false;
    const button = byId('tosAcceptBtn');
    if (button) {
      button.disabled = true;
      button.removeAttribute('aria-busy');
      button.textContent = button.dataset.originalText || 'Continue';
    }
  }

  function ensureTermsBoundaryRegistration() {
    if (termsBoundaryUnregister || typeof window.CrumpAuthBoundary?.register !== 'function') return;
    termsBoundaryUnregister = window.CrumpAuthBoundary.register(
      'auth-terms-acceptance',
      scrubTermsAuthBoundary,
    );
  }

  ensureTermsBoundaryRegistration();
  window.addEventListener('crump:body-runtime-ready', ensureTermsBoundaryRegistration, {once: true});

  function wireTerms() {
    ensureTermsBoundaryRegistration();
    byId('tosAccept')?.addEventListener('change', event => {
      const button = byId('tosAcceptBtn');
      if (!button) return;
      button.disabled = !event.target.checked;
      button.style.opacity = event.target.checked ? '1' : '.5';
    });
    byId('tosAcceptBtn')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      termsAcceptanceGeneration += 1;
      const generation = termsAcceptanceGeneration;
      const authBoundary = captureExpectedOwnerBoundary(generation);
      if (!authBoundary.ownerId) {
        scrubTermsAuthBoundary();
        window.showToast?.('Your account changed. Reopen the workspace and accept the terms again.', 'error');
        return;
      }
      button.disabled = true;
      const original = button.textContent;
      button.dataset.originalText = original;
      button.setAttribute('aria-busy', 'true');
      button.textContent = 'Saving…';
      try {
        const {response, data} = await authRequest('/api/account/accept-terms', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Ask-Crump-Expected-Owner': authBoundary.ownerId,
          },
          body: JSON.stringify({ version: TERMS_VERSION }),
        }, 'Saving your acceptance took too long. Try Continue again.');
        if (!expectedOwnerBoundaryIsCurrent(authBoundary, termsAcceptanceGeneration)) return;
        if (!response.ok || !data.success) throw new Error(data.error || 'Could not save your acceptance.');
        const responseOwnerId = String(data.user?.id || authBoundary.ownerId).trim();
        if (responseOwnerId !== authBoundary.ownerId) return;
        activeUser = data.user || { ...activeUser, termsAcceptedAt: new Date().toISOString(), termsVersion: TERMS_VERSION };
        window.currentUser = activeUser;
        button.removeAttribute('aria-busy');
        button.textContent = original;
        hide('tosModal');
        startApp();
        if (!activeUser.fullName) maybeOfferProfileSetup();
      } catch (error) {
        if (!expectedOwnerBoundaryIsCurrent(authBoundary, termsAcceptanceGeneration)) return;
        window.showToast?.(error.message, 'error');
        button.disabled = false;
        button.removeAttribute('aria-busy');
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
    button.setAttribute('aria-busy', String(Boolean(busy)));
    button.textContent = busy ? label : original;
    return () => {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.textContent = original;
    };
  }

  function showLoginError(message) {
    setText('loginError', message);
    requestAnimationFrame(() => {
      const error = byId('loginError');
      if (!error || getComputedStyle(error).display === 'none') return;
      error.scrollIntoView?.({block: 'nearest', inline: 'nearest'});
    });
  }

  function setLoginRecoveryActionVisible(visible = false) {
    const action = byId('loginRecoveryAction');
    if (!action) return;
    action.style.display = visible ? 'block' : 'none';
    if (!visible) return;
    requestAnimationFrame(() => action.scrollIntoView?.({block: 'nearest', inline: 'nearest'}));
  }

  function openPasswordRecoveryFromLogin() {
    const loginEmail = byId('loginEmail')?.value.trim() || '';
    const forgotEmail = byId('forgotPasswordEmail');
    if (forgotEmail && loginEmail) forgotEmail.value = loginEmail;
    setLoginRecoveryActionVisible(false);
    setText('forgotPasswordError', '', false);
    setText('forgotPasswordSuccess', '', false);
    showAuth('forgot');
  }

  function showWorkspaceLoginRecovery() {
    let button = byId('loginWorkspaceRecovery');
    if (!button) {
      button = document.createElement('button');
      button.id = 'loginWorkspaceRecovery';
      button.type = 'button';
      button.className = 'auth-submit-btn';
      button.textContent = 'Reload workspace';
      button.addEventListener('click', () => window.location.reload());
      byId('loginError')?.insertAdjacentElement('afterend', button);
    }
    button.hidden = false;
    requestAnimationFrame(() => button.scrollIntoView?.({block: 'nearest', inline: 'nearest'}));
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

  function loginFailureReason(error) {
    const result = error?.result || {};
    const code = String(result.code || error?.code || '').trim().toUpperCase();
    if (result.needsVerification || code === 'EMAIL_VERIFICATION_REQUIRED') return 'verification_required';
    if (code === 'INVALID_CREDENTIALS') return 'credentials_rejected';
    if (code === 'RATE_LIMITED') return 'rate_limited';
    if (code === 'SESSION_ESTABLISHMENT_FAILED') return 'session_establishment';
    if (code === 'AUTH_REQUEST_TIMEOUT') return 'timeout';
    if (navigator.onLine === false) return 'offline';
    return 'request_failed';
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
      setLoginRecoveryActionVisible(false);
      showLoginError(message);
      trackFunnel('LoginValidationFailed', {reason});
    }, true);

    form.addEventListener('input', event => {
      event.target?.removeAttribute('aria-invalid');
      setLoginRecoveryActionVisible(false);
    }, {passive: true});

    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (form.querySelector('button[type="submit"]')?.disabled) return;
      authFlowRevision += 1;
      setText('loginError', '', false);
      setText('loginSuccess', '', false);
      setLoginRecoveryActionVisible(false);
      const workspaceRecovery = byId('loginWorkspaceRecovery');
      if (workspaceRecovery) workspaceRecovery.hidden = true;
      hide('verificationNeeded');
      const restore = setBusy(event.currentTarget, true, 'Signing in…');
      trackFunnel('LoginSubmitted');
      let credentialsConfirmed = false;
      try {
        await reauthenticationPreparation;
        const result = await window.deviceAuth.login(byId('loginEmail').value.trim(), byId('loginPassword').value);
        if (!result.success || !result.data?.user) throw Object.assign(new Error(result.error || 'Sign in failed.'), { result });
        credentialsConfirmed = true;
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = 'Opening workspace…';
        setText('loginSuccess', 'Signed in. Opening your workspace…');
        rememberRegisteredAccount(result.data.user);
        // The issued credential has already switched this installation to the
        // registered account. Remove the guest-return affordance before any
        // fallible workspace preparation so a later error cannot misrepresent
        // the now-replaced guest session as recoverable.
        guestAccountSwitchPending = false;
        renderGuestSigninNotice(false);
        if (routePasswordSetupRequiredUser(result.data.user, result.data.settings)) return;
        await prepareAuthenticatedWorkspace();
        activeUser = result.data.user;
        window.currentUser = activeUser;
        window.configureUserStorage?.(activeUser.id);
        applyServerSettings(result.data.settings);
        setText('loginSuccess', 'Signed in.');
        trackFunnel('LoginCompleted');
        routeAuthenticatedUser(activeUser);
      } catch (error) {
        setText('loginSuccess', '', false);
        const invalidCredentials = error.result?.code === 'INVALID_CREDENTIALS';
        const recoveryHint = invalidCredentials
          ? ' Use Forgot password to restore access to an existing account.'
          : '';
        showLoginError((error.message || 'Network error. Try again.') + recoveryHint);
        setLoginRecoveryActionVisible(invalidCredentials);
        if (credentialsConfirmed) showWorkspaceLoginRecovery();
        trackFunnel('LoginFailed', {
          reason: loginFailureReason(error),
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
        const creationIntent = pendingCreationIntent();
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
            intent: creationIntent?.kind || attribution.intent,
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
              data.error || 'Your account exists, but the verification email request could not be queued. Use Resend verification email to try again.',
              {deliveryFailed: true},
            );
            return;
          }
          throw new Error(data.error || 'Registration failed.');
        }
        trackFunnel('AccountCreated', {verification_delivery: 'queued'});
        showRegistrationPending(email, data.message || 'A verification email will be sent shortly.');
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
        const resetForm = byId('resetPasswordForm');
        const initialSetup = resetForm?.dataset.mode === 'setup';
        const requestBody = initialSetup
          ? {newPassword: password}
          : {token: resetForm?.dataset.token, newPassword: password};
        const {response, data} = await authRequest(initialSetup ? '/api/auth/complete-password-setup' : '/api/auth/reset-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody) }, initialSetup ? 'Securing your password took too long to confirm. Refresh before trying again.' : 'Updating your password took too long to confirm. Try signing in before submitting it again.');
        if (!response.ok) throw new Error(data.error || 'Password reset failed.');
        if (resetForm) delete resetForm.dataset.token;
        byId('newPassword').value = '';
        byId('confirmNewPassword').value = '';
        history.replaceState({}, document.title, location.pathname);
        if (initialSetup) {
          configurePasswordForm('reset');
          await bootstrap();
          return;
        }
        configurePasswordForm('reset');
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
    onboardingProfileGeneration += 1;
    const generation = onboardingProfileGeneration;
    onboardingProfileController?.abort?.();
    const controller = new AbortController();
    onboardingProfileController = controller;
    const authBoundary = captureOnboardingAuthBoundary(generation);
    if (!authBoundary.ownerId) {
      onboardingProfileController = null;
      setText('onboardingError', 'Your account changed. Reopen profile setup and try again.');
      return;
    }
    if (button) {
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.textContent = 'Saving…';
    }
    if (skip) skip.disabled = true;
    try {
      const {response, data} = await authRequest('/api/account/profile', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-Ask-Crump-Expected-Owner': authBoundary.ownerId,
        },
        body: JSON.stringify({ fullName: name }),
        signal: controller.signal,
      }, 'Saving your profile took too long. Try again or choose Not now.');
      if (!onboardingAuthBoundaryIsCurrent(authBoundary)) return;
      if (!response.ok || !data.success) throw new Error(data.error || 'Could not save your profile.');
      const responseOwnerId = String(data.user?.id || authBoundary.ownerId).trim();
      if (responseOwnerId !== authBoundary.ownerId) return;
      activeUser = data.user || { ...activeUser, fullName: name };
      window.currentUser = activeUser;
      window.profileManager?.updateProfile?.({ name, email: activeUser.email, initial: name.charAt(0).toUpperCase() });
      localStorage.setItem(window.STORAGE_KEYS?.HAS_ONBOARDED || 'crump_has_onboarded', 'true');
      try { localStorage.removeItem(profileNudgeKey()); } catch (_) {}
      startApp();
    } catch (error) {
      if (!onboardingAuthBoundaryIsCurrent(authBoundary)) return;
      setText('onboardingError', error.message || 'Could not save your name. Try again or choose Not now.');
    } finally {
      if (onboardingProfileController === controller) onboardingProfileController = null;
      if (!onboardingAuthBoundaryIsCurrent(authBoundary)) return;
      if (button) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
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
    if (isGuestUser(window.currentUser || activeUser)) {
      // A guest choosing the account action is trying to reach an existing
      // account, not erase the only session holding the current conversation.
      // Keep it active while credentials are entered; the login screen makes
      // the account switch and conversation boundary explicit.
      location.assign(explicitSignInPath('guest-settings-signin'));
      return;
    }
    try {
      const result = await window.deviceAuth.logout();
      if (result?.stale) return;
    } catch (error) {
      console.warn('[Auth] Sign-out confirmation unavailable:', error);
      const currentOwner = String(window.CrumpAuthBoundary?.authenticatedUserId?.() || '').trim();
      if (currentOwner) return;
    }
    location.replace(explicitSignInPath('logout-signin'));
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
    window.addEventListener('crump:authentication-required', handleAuthenticationRequired);
    bootstrap().catch(error => {
      console.error('[Bootstrap]', error);
      showAuth('login');
      setText(
        'loginError',
        error?.message || 'Ask Crump could not finish loading your workspace. Your sign-in is safe—reload to try again.',
      );
    });
  });
})();
