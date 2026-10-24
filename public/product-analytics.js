(() => {
  'use strict';

  if (window.__crumpProductAnalyticsLoaded) return;
  window.__crumpProductAnalyticsLoaded = true;

  const events = new Set(['WorkspaceOpened', 'NavigationDestinationSelected', 'StarterIntentReached', 'ProjectSaveOfferShown', 'ProjectSaveIntentReached', 'ActivationReached', 'OutcomeFeedbackSubmitted', 'OutcomeIssueCategorized', 'RecentWorkResumed', 'PlanCenterViewed', 'PlanIntentReached', 'ResponseShared']);
  const plans = new Set(['professional', 'enterprise']);
  const safeKey = /^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$/;
  const safeSource = /^[a-z0-9_-]{1,32}$/;

  function captureAuthBoundary() {
    const boundary = window.CrumpAuthBoundary;
    const revision = Number(boundary?.revision?.() || 0);
    return Object.freeze({
      ownerId: String(boundary?.authenticatedUserId?.() || window.currentUser?.id || '').trim(),
      revision: Number.isFinite(revision) ? revision : 0,
    });
  }

  function authBoundaryIsCurrent(snapshot) {
    if (!snapshot?.ownerId) return false;
    const current = captureAuthBoundary();
    return current.ownerId === snapshot.ownerId && current.revision === snapshot.revision;
  }

  async function track(eventName, values = {}, suppliedBoundary = null) {
    if (!events.has(eventName)) return false;
    const eventKey = String(values.eventKey || '').trim();
    if (!safeKey.test(eventKey)) return false;
    const authBoundary = suppliedBoundary || captureAuthBoundary();
    if (!authBoundaryIsCurrent(authBoundary)) return false;

    const body = {eventName, eventKey};
    const source = String(values.source || '').trim().toLowerCase();
    const plan = String(values.plan || '').trim().toLowerCase();
    if (source) body.source = safeSource.test(source) ? source : 'direct';
    if (plans.has(plan)) body.plan = plan;

    try {
      const response = await fetch('/api/analytics/events', {
        method: 'POST',
        credentials: 'same-origin',
        keepalive: true,
        headers: {
          'Content-Type': 'application/json',
          'X-Ask-Crump-Expected-Owner': authBoundary.ownerId,
        },
        body: JSON.stringify(body),
      });
      return authBoundaryIsCurrent(authBoundary) && response.ok;
    } catch (_) {
      return false;
    }
  }

  window.CrumpAnalytics = Object.freeze({track});
})();
