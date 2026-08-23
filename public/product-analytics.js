(() => {
  'use strict';

  if (window.__crumpProductAnalyticsLoaded) return;
  window.__crumpProductAnalyticsLoaded = true;

  const events = new Set(['WorkspaceOpened', 'PlanIntentReached', 'ResponseShared']);
  const plans = new Set(['professional', 'enterprise']);
  const safeKey = /^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$/;
  const safeSource = /^[a-z0-9_-]{1,32}$/;

  async function track(eventName, values = {}) {
    if (!events.has(eventName)) return false;
    const eventKey = String(values.eventKey || '').trim();
    if (!safeKey.test(eventKey)) return false;

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
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      return response.ok;
    } catch (_) {
      return false;
    }
  }

  window.CrumpAnalytics = Object.freeze({track});
})();
