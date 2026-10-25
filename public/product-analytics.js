(() => {
  'use strict';

  if (window.__crumpProductAnalyticsLoaded) return;
  window.__crumpProductAnalyticsLoaded = true;

  const events = new Set(['WorkspaceOpened', 'NavigationDestinationSelected', 'StarterIntentReached', 'ProjectSaveOfferShown', 'ProjectSaveIntentReached', 'ActivationReached', 'OutcomeFeedbackSubmitted', 'OutcomeIssueCategorized', 'RecentWorkResumed', 'PlanCenterViewed', 'PlanIntentReached', 'ResponseShared']);
  const plans = new Set(['professional', 'enterprise']);
  const safeKey = /^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$/;
  const safeSource = /^[a-z0-9_-]{1,32}$/;
  const workspaceOpenedMaxAttempts = 3;
  const workspaceOpenedRetryDelaysMs = Object.freeze([1000, 5000]);
  let workspaceOpenedRecordedFor = '';
  let workspaceOpenedRetryFor = '';
  let workspaceOpenedAttempts = 0;
  let workspaceOpenedGeneration = 0;
  let workspaceOpenedRequest = null;
  let workspaceOpenedAbortController = null;
  let workspaceOpenedRetryTimer = 0;
  let workspaceOpenedWakeListenersBound = false;

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

  async function track(eventName, values = {}, suppliedBoundary = null, requestOptions = {}) {
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
        signal: requestOptions.signal,
        headers: {
          'Content-Type': 'application/json',
          'X-Ask-Crump-Expected-Owner': authBoundary.ownerId,
        },
        body: JSON.stringify(body),
      });
      if (!authBoundaryIsCurrent(authBoundary) || !response.ok) return false;
      if (eventName !== 'WorkspaceOpened') return true;
      const result = await response.json();
      return authBoundaryIsCurrent(authBoundary)
        && result?.success === true
        && result?.accepted === true;
    } catch (_) {
      return false;
    }
  }

  function workspaceOpenedDay() {
    return new Date().toISOString().slice(0, 10);
  }

  function workspaceOpenedCanRun() {
    return document.visibilityState !== 'hidden'
      && (typeof navigator === 'undefined' || navigator.onLine !== false);
  }

  function clearWorkspaceOpenedRetryTimer() {
    if (!workspaceOpenedRetryTimer) return;
    clearTimeout(workspaceOpenedRetryTimer);
    workspaceOpenedRetryTimer = 0;
  }

  function removeWorkspaceOpenedWakeListeners() {
    if (!workspaceOpenedWakeListenersBound) return;
    document.removeEventListener('visibilitychange', wakeWorkspaceOpened);
    window.removeEventListener('online', wakeWorkspaceOpened);
    workspaceOpenedWakeListenersBound = false;
  }

  function scrubWorkspaceOpenedState() {
    workspaceOpenedGeneration += 1;
    clearWorkspaceOpenedRetryTimer();
    workspaceOpenedAbortController?.abort();
    workspaceOpenedAbortController = null;
    workspaceOpenedRequest = null;
    workspaceOpenedRecordedFor = '';
    workspaceOpenedRetryFor = '';
    workspaceOpenedAttempts = 0;
    removeWorkspaceOpenedWakeListeners();
  }

  function ensureWorkspaceOpenedWakeListeners() {
    if (workspaceOpenedWakeListenersBound) return;
    document.addEventListener('visibilitychange', wakeWorkspaceOpened);
    window.addEventListener('online', wakeWorkspaceOpened);
    workspaceOpenedWakeListenersBound = true;
  }

  function workspaceOpenedTarget() {
    const boundary = captureAuthBoundary();
    if (!boundary.ownerId) return null;
    const day = workspaceOpenedDay();
    return Object.freeze({
      boundary,
      day,
      recordedFor: `${boundary.ownerId}:${day}`,
      retryFor: `${boundary.ownerId}:${boundary.revision}:${day}`,
    });
  }

  function activateWorkspaceOpenedTarget(target) {
    if (workspaceOpenedRetryFor === target.retryFor) return;
    workspaceOpenedGeneration += 1;
    clearWorkspaceOpenedRetryTimer();
    workspaceOpenedAbortController?.abort();
    workspaceOpenedAbortController = null;
    workspaceOpenedRequest = null;
    workspaceOpenedRetryFor = target.retryFor;
    workspaceOpenedAttempts = 0;
  }

  function scheduleWorkspaceOpenedRetry(generation) {
    if (generation !== workspaceOpenedGeneration
        || workspaceOpenedAttempts >= workspaceOpenedMaxAttempts
        || workspaceOpenedRetryTimer) return;
    const delay = workspaceOpenedRetryDelaysMs[workspaceOpenedAttempts - 1];
    if (!Number.isFinite(delay)) return;
    workspaceOpenedRetryTimer = window.setTimeout(() => {
      workspaceOpenedRetryTimer = 0;
      void attemptWorkspaceOpened();
    }, delay);
  }

  async function attemptWorkspaceOpened() {
    const target = workspaceOpenedTarget();
    if (!target) {
      scrubWorkspaceOpenedState();
      return false;
    }
    activateWorkspaceOpenedTarget(target);
    ensureWorkspaceOpenedWakeListeners();
    if (workspaceOpenedRecordedFor === target.recordedFor) return true;
    if (!workspaceOpenedCanRun()
        || workspaceOpenedAttempts >= workspaceOpenedMaxAttempts) return false;
    if (workspaceOpenedRequest) return workspaceOpenedRequest;

    const generation = workspaceOpenedGeneration;
    const abortController = new AbortController();
    workspaceOpenedAbortController = abortController;
    workspaceOpenedAttempts += 1;
    const request = track(
      'WorkspaceOpened',
      {eventKey: `workspace-open:${target.day}`},
      target.boundary,
      {signal: abortController.signal},
    ).then(accepted => {
      if (generation !== workspaceOpenedGeneration
          || workspaceOpenedRetryFor !== target.retryFor
          || !authBoundaryIsCurrent(target.boundary)) return false;
      if (accepted) {
        workspaceOpenedRecordedFor = target.recordedFor;
        clearWorkspaceOpenedRetryTimer();
        return true;
      }
      scheduleWorkspaceOpenedRetry(generation);
      return false;
    }).finally(() => {
      if (workspaceOpenedRequest === request) workspaceOpenedRequest = null;
      if (workspaceOpenedAbortController === abortController) {
        workspaceOpenedAbortController = null;
      }
    });
    workspaceOpenedRequest = request;
    return request;
  }

  function wakeWorkspaceOpened() {
    if (!workspaceOpenedCanRun()) return;
    clearWorkspaceOpenedRetryTimer();
    void attemptWorkspaceOpened();
  }

  function recordWorkspaceOpenedWhenVisible() {
    ensureWorkspaceOpenedWakeListeners();
    return attemptWorkspaceOpened();
  }

  window.CrumpAuthBoundary?.register?.(
    'workspace-opened-retention',
    scrubWorkspaceOpenedState,
  );

  window.CrumpAnalytics = Object.freeze({track, recordWorkspaceOpenedWhenVisible});
})();
