(() => {
  'use strict';

  window.va = window.va || function queueVercelAnalytics() {
    (window.vaq = window.vaq || []).push(arguments);
  };

  const ACQUISITION_KEY = 'askcrump.acquisition-source';
  const ACQUISITION_PLACEMENT_KEY = 'askcrump.acquisition-placement';
  const FIRST_TOUCH_KEY = 'askcrump.first-touch-attribution';
  const MARKETING_LANDING_KEY = 'askcrump.marketing-landing-emitted';
  const FIRST_TOUCH_TTL_MS = 24 * 60 * 60 * 1000;
  const MARKETING_LANDING_KINDS = new Set([
    'exact-referral', 'registered-campaign', 'rejected',
  ]);
  let firstTouchMarketingKind = 'rejected';
  const ACQUISITION_SOURCES = new Set([
    'direct', 'instagram', 'facebook', 'facebook-pinned', 'linkedin', 'tiktok',
    'youtube', 'x', 'referral', 'organic', 'organic-search', 'clevercrump',
    'founder-outreach',
  ]);
  const LEGACY_ACQUISITION_SOURCES = new Set([
    'instagram', 'facebook', 'facebook-pinned', 'linkedin', 'tiktok',
    'youtube', 'x', 'referral', 'organic', 'clevercrump',
  ]);
  const ACQUISITION_PLACEMENTS = new Set([
    'response-share', 'profile-link', 'workflow-guide', 'organic-social',
    'creator-cohort',
  ]);
  const CREATION_INTENTS = new Set([
    'document', 'presentation', 'resume', 'video', 'projects',
  ]);
  const PAGE_INTENTS = Object.freeze({
    '/ai-document-generator': 'document',
    '/ai-presentation-maker': 'presentation',
    '/ai-resume-builder': 'resume',
    '/ai-video-generator': 'video',
    '/ai-project-workspace': 'projects',
    '/guides/rough-idea-six-week-launch-plan': 'projects',
    '/guides/what-ai-project-should-remember': 'projects',
    '/guides/editable-ai-powerpoint-review': 'presentation',
  });
  const PAGE_CAMPAIGN_DEFAULTS = Object.freeze({
    '/guides/rough-idea-six-week-launch-plan': {
      placement: 'workflow-guide',
      campaign: 'rough-idea-launch-plan',
      creative: 'search-article',
    },
    '/guides/what-ai-project-should-remember': {
      placement: 'workflow-guide',
      campaign: 'project-memory-boundaries',
      creative: 'search-article',
    },
    '/guides/editable-ai-powerpoint-review': {
      placement: 'workflow-guide',
      campaign: 'editable-powerpoint-review',
      creative: 'search-article',
    },
  });
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

  function tokenValue(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return /^[a-z0-9][a-z0-9-]{0,31}$/.test(normalized) ? normalized : '';
  }

  function safeSource(value, fallback = '') {
    const normalized = String(value || '').trim().toLowerCase();
    return /^[a-z0-9_-]{1,32}$/.test(normalized) ? normalized : fallback;
  }

  function referringSource() {
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
        || searchHosts.some(domain => host === domain || host.endsWith(`.${domain}`))
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
      return sources.find(([domain]) => host === domain || host.endsWith(`.${domain}`))?.[1] || 'referral';
    } catch (_) {
      return 'direct';
    }
  }

  function normalizeAttribution(candidate) {
    const acquisitionToken = tokenValue(candidate?.acquisition);
    const acquisition = ACQUISITION_SOURCES.has(acquisitionToken) ? acquisitionToken : 'direct';
    const placementToken = tokenValue(candidate?.placement);
    const placement = ACQUISITION_PLACEMENTS.has(placementToken) ? placementToken : null;
    const intentToken = tokenValue(candidate?.intent);
    const intent = CREATION_INTENTS.has(intentToken) ? intentToken : null;
    const campaignToken = tokenValue(candidate?.campaign);
    const specification = CAMPAIGN_REGISTRY[campaignToken];
    const campaign = specification
      && specification.acquisitions.has(acquisition)
      && specification.placements.has(placement)
      && specification.intent === intent
      ? campaignToken
      : null;
    const creativeToken = tokenValue(candidate?.creative);
    const creative = campaign && specification.creatives.has(creativeToken)
      ? creativeToken
      : null;
    return {acquisition, placement, campaign, creative, intent};
  }

  function explicitAttributionInputsValid(params) {
    for (const key of ['acquisition', 'utm_source']) {
      if (params.has(key) && !ACQUISITION_SOURCES.has(tokenValue(params.get(key)))) {
        return false;
      }
    }
    if (params.has('source')) {
      const source = tokenValue(params.get('source'));
      if (!ACQUISITION_PLACEMENTS.has(source) && !LEGACY_ACQUISITION_SOURCES.has(source)) {
        return false;
      }
    }
    if (params.has('campaign') && !tokenValue(params.get('campaign'))) return false;
    if (params.has('creative') && !tokenValue(params.get('creative'))) return false;
    if (params.has('intent') && !CREATION_INTENTS.has(tokenValue(params.get('intent')))) {
      return false;
    }
    return true;
  }

  function currentAttribution() {
    const params = new URLSearchParams(location.search);
    const pageCampaign = PAGE_CAMPAIGN_DEFAULTS[location.pathname];
    const sourceToken = tokenValue(params.get('source'));
    const explicitAcquisition = tokenValue(params.get('acquisition') || params.get('utm_source'));
    const legacyAcquisition = LEGACY_ACQUISITION_SOURCES.has(sourceToken) ? sourceToken : '';
    let storedAcquisition = '';
    let storedPlacement = '';
    try {
      storedAcquisition = tokenValue(sessionStorage.getItem(ACQUISITION_KEY));
      storedPlacement = tokenValue(sessionStorage.getItem(ACQUISITION_PLACEMENT_KEY));
    } catch (_) {}
    const referredAcquisition = referringSource();
    const detectedAcquisition = explicitAcquisition
      || legacyAcquisition
      || (ACQUISITION_SOURCES.has(storedAcquisition) ? storedAcquisition : '')
      || referredAcquisition;
    const acquisition = pageCampaign && detectedAcquisition === 'organic'
      ? 'organic-search'
      : detectedAcquisition;
    const pageCampaignEligible = Boolean(pageCampaign && acquisition === 'organic-search');
    const placement = ACQUISITION_PLACEMENTS.has(sourceToken)
      ? sourceToken
      : (storedPlacement || (pageCampaignEligible ? pageCampaign.placement : ''));
    const queryIntent = tokenValue(params.get('intent'));
    const intent = CREATION_INTENTS.has(queryIntent)
      ? queryIntent
      : PAGE_INTENTS[location.pathname] || null;
    const attribution = normalizeAttribution({
      acquisition,
      placement,
      campaign: params.get('campaign') || (pageCampaignEligible ? pageCampaign.campaign : ''),
      creative: params.get('creative') || (pageCampaignEligible ? pageCampaign.creative : ''),
      intent,
    });
    const explicitInputsValid = explicitAttributionInputsValid(params);
    const exactReferral = explicitInputsValid
      && attribution.acquisition === 'referral'
      && attribution.placement === 'response-share'
      && !params.has('campaign')
      && !params.has('creative');
    firstTouchMarketingKind = explicitInputsValid && attribution.campaign && attribution.creative
      ? 'registered-campaign'
      : (exactReferral ? 'exact-referral' : 'rejected');
    return attribution;
  }

  function storedFirstTouch() {
    try {
      const stored = JSON.parse(sessionStorage.getItem(FIRST_TOUCH_KEY) || 'null');
      const capturedAt = Number(stored?.capturedAt || 0);
      if (!capturedAt || Date.now() - capturedAt > FIRST_TOUCH_TTL_MS) {
        sessionStorage.removeItem(FIRST_TOUCH_KEY);
        return null;
      }
      const attribution = normalizeAttribution(stored);
      const fallbackKind = attribution.campaign && attribution.creative
        ? 'registered-campaign'
        : 'rejected';
      const marketingLandingKind = MARKETING_LANDING_KINDS.has(stored?.marketingLandingKind)
        ? stored.marketingLandingKind
        : fallbackKind;
      return {...attribution, capturedAt, marketingLandingKind};
    } catch (_) {
      return null;
    }
  }

  function firstTouchAttribution() {
    const candidate = currentAttribution();
    const stored = storedFirstTouch();
    const capturedAt = stored?.capturedAt || Date.now();
    const attribution = stored ? normalizeAttribution(stored) : candidate;
    firstTouchMarketingKind = stored?.marketingLandingKind || firstTouchMarketingKind;
    try {
      sessionStorage.setItem(FIRST_TOUCH_KEY, JSON.stringify({
        ...attribution,
        capturedAt,
        marketingLandingKind: firstTouchMarketingKind,
      }));
      sessionStorage.setItem(ACQUISITION_KEY, attribution.acquisition);
      if (attribution.placement) {
        sessionStorage.setItem(ACQUISITION_PLACEMENT_KEY, attribution.placement);
      }
    } catch (_) {}
    return attribution;
  }

  function marketingLandingTouchpoint(attribution, marketingLandingKind) {
    if (
      marketingLandingKind === 'exact-referral'
      && attribution.acquisition === 'referral'
      && attribution.placement === 'response-share'
      && !attribution.campaign
      && !attribution.creative
    ) return 'referral.response-share';

    if (marketingLandingKind !== 'registered-campaign') return '';

    const specification = CAMPAIGN_REGISTRY[attribution.campaign];
    if (
      !specification
      || !attribution.creative
      || !specification.acquisitions.has(attribution.acquisition)
      || !specification.placements.has(attribution.placement)
      || !specification.creatives.has(attribution.creative)
      || specification.intent !== attribution.intent
    ) return '';

    return [
      attribution.acquisition,
      attribution.placement,
      attribution.campaign,
      attribution.creative,
    ].join('.');
  }

  function emitMarketingLanding(attribution, marketingLandingKind) {
    const touchpoint = marketingLandingTouchpoint(attribution, marketingLandingKind);
    if (!touchpoint) return;

    try {
      if (sessionStorage.getItem(MARKETING_LANDING_KEY)) return;
      sessionStorage.setItem(MARKETING_LANDING_KEY, '1');
    } catch (_) {
      return;
    }

    try {
      window.va('event', {
        name: 'MarketingLanding',
        data: {
          touchpoint,
          intent: attribution.intent || 'unspecified',
        },
      });
    } catch (_) {}
  }

  const attribution = firstTouchAttribution();
  emitMarketingLanding(attribution, firstTouchMarketingKind);
  document.querySelectorAll('[data-cta]').forEach(link => {
    let analyticsEvent = 'MarketingCTA';
    let creationIntent = attribution.intent || 'unspecified';
    try {
      const destination = new URL(link.getAttribute('href'), location.href);
      if (destination.origin === location.origin && destination.pathname === '/app') {
        analyticsEvent = destination.searchParams.get('signup') === '1'
          ? 'MarketingCTA'
          : 'MarketingSignin';
        creationIntent = safeSource(destination.searchParams.get('intent'), creationIntent);
        destination.searchParams.set('acquisition', attribution.acquisition);
        if (attribution.placement) destination.searchParams.set('source', attribution.placement);
        if (attribution.campaign) destination.searchParams.set('campaign', attribution.campaign);
        if (attribution.creative) destination.searchParams.set('creative', attribution.creative);
        link.setAttribute('href', `${destination.pathname}${destination.search}${destination.hash}`);
      }
    } catch (_) {}
    link.addEventListener('click', () => {
      window.va('event', {
        name: analyticsEvent,
        data: {
          location: link.dataset.cta || 'unknown',
          plan: link.dataset.plan || 'unspecified',
          ...attribution,
          intent: creationIntent,
        },
      });
    });
  });

  document.querySelectorAll('[data-explore]').forEach(link => {
    link.addEventListener('click', () => {
      window.va('event', {
        name: 'MarketingExplore',
        data: {
          destination: safeSource(link.dataset.explore, 'unknown'),
          ...attribution,
        },
      });
    });
  });

  const navbar = document.querySelector('.navbar');
  if (!navbar) return;
  const updateNavbar = () => navbar.classList.toggle('scrolled', window.scrollY > 24);
  window.addEventListener('scroll', updateNavbar, { passive: true });
  updateNavbar();
})();
