(() => {
  'use strict';

  if (window.CrumpAIDataSharingConsent) return;

  const CONSENT_VERSION = '2026-09-17';
  const CONSENT_ENDPOINT = '/api/account/ai-data-sharing-consent';
  const EXACT_PROVIDER_PATHS = new Set([
    '/api/chat',
    '/api/voice/synthesize',
    '/api/media/video',
  ]);
  const PROVIDER_PATH_PATTERNS = Object.freeze([
    /^\/api\/media\/video\/[^/]+\/continue$/,
    /^\/api\/code\/tasks\/[^/]+\/run$/,
    /^\/api\/manuscripts\/[^/]+\/(?:blueprint|draft-next)$/,
    /^\/api\/manuscripts\/[^/]+\/sections\/[^/]+\/draft$/,
  ]);
  const SERVER_AUTHORITATIVE_CONSENT_PATTERNS = Object.freeze([
    /^\/api\/manuscripts\/[^/]+\/runs$/,
    /^\/api\/manuscript-runs\/[^/]+\/resume$/,
  ]);
  const CODE_APPROVAL_PATH = /^\/api\/code\/tasks\/[^/]+\/approvals\/[^/]+$/;
  const transport = window.fetch.bind(window);
  let decisionPromise = null;
  let decisionResolve = null;
  let lastFocus = null;
  let mode = 'request';
  let modalBusy = false;

  const byId = id => document.getElementById(id);

  function currentUserAllowsSharing() {
    const user = window.currentUser;
    return Boolean(
      user
      && user.aiDataSharingConsentAt
      && String(user.aiDataSharingConsentVersion || '') === CONSENT_VERSION
      && !user.aiDataSharingConsentRevokedAt
    );
  }

  function requestMethod(input, init) {
    return String(init?.method || (typeof input === 'object' && input?.method) || 'GET').toUpperCase();
  }

  function requestPath(input) {
    try {
      const value = input instanceof URL
        ? input.href
        : (typeof input === 'string' ? input : input?.url);
      const pathname = new URL(value, window.location.href).pathname;
      return pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
    } catch (_) {
      return '';
    }
  }

  function isProviderBoundAction(input, init) {
    if (requestMethod(input, init) !== 'POST') return false;
    const path = requestPath(input);
    return EXACT_PROVIDER_PATHS.has(path)
      || PROVIDER_PATH_PATTERNS.some(pattern => pattern.test(path));
  }

  function isServerAuthoritativeConsentAction(input, init) {
    if (requestMethod(input, init) !== 'POST') return false;
    const path = requestPath(input);
    return CODE_APPROVAL_PATH.test(path)
      || SERVER_AUTHORITATIVE_CONSENT_PATTERNS.some(pattern => pattern.test(path));
  }

  function syntheticRequiredResponse() {
    return new Response(JSON.stringify({
      success: false,
      error: 'AI data-sharing permission is required before this request can be sent.',
      code: 'AI_DATA_SHARING_CONSENT_REQUIRED',
    }), {
      status: 428,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store',
      },
    });
  }

  function updateCurrentUser(next = {}) {
    if (!window.currentUser) return;
    window.currentUser = {...window.currentUser, ...next};
    refreshSettingsState();
    window.dispatchEvent(new CustomEvent('crump:ai-data-sharing-consent-changed', {
      detail: {
        allowed: currentUserAllowsSharing(),
        version: CONSENT_VERSION,
      },
    }));
  }

  function userFromPayload(payload) {
    return payload?.user || payload?.data?.user || null;
  }

  function refreshSettingsState() {
    const allowed = currentUserAllowsSharing();
    const status = byId('aiDataSharingConsentStatus');
    const help = byId('aiDataSharingConsentHelp');
    const button = byId('aiDataSharingConsentBtn');
    if (status) {
      status.textContent = allowed ? 'Allowed' : 'Not allowed';
      status.dataset.allowed = String(allowed);
    }
    if (help) {
      help.textContent = allowed
        ? 'Allowed for this consent version. Review or withdraw for future requests.'
        : 'Nothing is sent to an AI provider until you explicitly allow it.';
    }
    if (button) {
      button.setAttribute('aria-label', `AI provider data sharing: ${allowed ? 'allowed' : 'not allowed'}. Review permission.`);
    }
  }

  function focusableControls() {
    const modal = byId('aiDataSharingConsentModal');
    if (!modal) return [];
    return [...modal.querySelectorAll('a[href], button:not([hidden]):not([disabled])')]
      .filter(node => !node.closest('[hidden]'));
  }

  function setError(message = '') {
    const error = byId('aiConsentError');
    if (!error) return;
    error.textContent = message;
    error.hidden = !message;
  }

  function setBusy(busy, label = '') {
    modalBusy = Boolean(busy);
    for (const id of ['aiConsentNotNow', 'aiConsentAllow', 'aiConsentWithdraw', 'aiConsentDone']) {
      const button = byId(id);
      if (button) button.disabled = Boolean(busy);
    }
    const primary = mode === 'allowed-review' ? byId('aiConsentWithdraw') : byId('aiConsentAllow');
    if (!primary) return;
    if (!primary.dataset.defaultLabel) primary.dataset.defaultLabel = primary.textContent;
    primary.textContent = busy && label ? label : primary.dataset.defaultLabel;
    primary.setAttribute('aria-busy', String(Boolean(busy)));
  }

  function renderModal(nextMode) {
    mode = nextMode;
    const allowedReview = nextMode === 'allowed-review';
    const title = byId('aiConsentTitle');
    const eyebrow = byId('aiConsentEyebrow');
    const requestActions = byId('aiConsentRequestActions');
    const reviewActions = byId('aiConsentReviewActions');
    const status = byId('aiConsentReviewStatus');
    if (eyebrow) eyebrow.textContent = allowedReview ? 'PERMISSION ALLOWED' : 'YOUR CHOICE';
    if (title) title.textContent = allowedReview
      ? 'AI provider data sharing is allowed.'
      : 'Allow AI provider data sharing?';
    if (requestActions) requestActions.hidden = allowedReview;
    if (reviewActions) reviewActions.hidden = !allowedReview;
    if (status) status.hidden = !allowedReview;
    setError('');
    setBusy(false);
  }

  function showModal(nextMode) {
    const modal = byId('aiDataSharingConsentModal');
    if (!modal) return false;
    lastFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    renderModal(nextMode);
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('ai-consent-modal-open');
    requestAnimationFrame(() => {
      const target = nextMode === 'allowed-review' ? byId('aiConsentDone') : byId('aiConsentNotNow');
      target?.focus({preventScroll: true});
    });
    return true;
  }

  function hideModal() {
    const modal = byId('aiDataSharingConsentModal');
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('ai-consent-modal-open');
    const focus = lastFocus;
    lastFocus = null;
    if (focus?.isConnected) focus.focus({preventScroll: true});
  }

  function settleDecision(allowed) {
    const resolve = decisionResolve;
    decisionResolve = null;
    decisionPromise = null;
    hideModal();
    resolve?.(Boolean(allowed));
  }

  function requestDecision() {
    if (currentUserAllowsSharing()) return Promise.resolve(true);
    if (decisionPromise) return decisionPromise;
    decisionPromise = new Promise(resolve => { decisionResolve = resolve; });
    if (!showModal('request')) settleDecision(false);
    return decisionPromise;
  }

  async function persistPermission() {
    setError('');
    setBusy(true, 'Allowing…');
    try {
      const response = await transport(CONSENT_ENDPOINT, {
        method: 'POST',
        credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({version: CONSENT_VERSION}),
      });
      const payload = await response.clone().json().catch(() => ({}));
      if (!response.ok || payload.success === false) {
        throw new Error(payload.error || 'Ask Crump could not save this permission. Try again.');
      }
      const user = userFromPayload(payload);
      updateCurrentUser(user || {
        aiDataSharingConsentAt: new Date().toISOString(),
        aiDataSharingConsentVersion: CONSENT_VERSION,
        aiDataSharingConsentRevokedAt: null,
      });
      if (!currentUserAllowsSharing()) {
        updateCurrentUser({
          aiDataSharingConsentAt: new Date().toISOString(),
          aiDataSharingConsentVersion: CONSENT_VERSION,
          aiDataSharingConsentRevokedAt: null,
        });
      }
      if (decisionPromise) settleDecision(true);
      else hideModal();
      window.showToast?.('AI provider data sharing allowed for future requests.', 'success');
      return true;
    } catch (error) {
      setError(error?.message || 'Ask Crump could not save this permission. Try again.');
      setBusy(false);
      return false;
    }
  }

  async function withdrawPermission() {
    setError('');
    setBusy(true, 'Withdrawing…');
    try {
      const response = await transport(CONSENT_ENDPOINT, {
        method: 'DELETE',
        credentials: 'include',
        headers: {'Content-Type': 'application/json'},
      });
      const payload = await response.clone().json().catch(() => ({}));
      if (!response.ok || payload.success === false) {
        throw new Error(payload.error || 'Ask Crump could not withdraw this permission. Try again.');
      }
      const user = userFromPayload(payload);
      updateCurrentUser(user || {
        aiDataSharingConsentRevokedAt: new Date().toISOString(),
      });
      if (currentUserAllowsSharing()) {
        updateCurrentUser({
          aiDataSharingConsentRevokedAt: new Date().toISOString(),
        });
      }
      hideModal();
      window.showToast?.('Permission withdrawn. Future AI provider requests will ask first.', 'success');
      return true;
    } catch (error) {
      setError(error?.message || 'Ask Crump could not withdraw this permission. Try again.');
      setBusy(false);
      return false;
    }
  }

  function reviewPermission() {
    refreshSettingsState();
    showModal(currentUserAllowsSharing() ? 'allowed-review' : 'review');
  }

  function wireControls() {
    byId('aiDataSharingConsentBtn')?.addEventListener('click', reviewPermission);
    byId('aiConsentNotNow')?.addEventListener('click', () => {
      if (decisionPromise) settleDecision(false);
      else hideModal();
    });
    byId('aiConsentAllow')?.addEventListener('click', () => { void persistPermission(); });
    byId('aiConsentWithdraw')?.addEventListener('click', () => { void withdrawPermission(); });
    byId('aiConsentDone')?.addEventListener('click', hideModal);
    byId('aiDataSharingConsentModal')?.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (modalBusy) return;
        if (decisionPromise) settleDecision(false);
        else hideModal();
        return;
      }
      if (event.key !== 'Tab') return;
      const controls = focusableControls();
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    refreshSettingsState();
  }

  async function consentRequired(response) {
    if (response.status !== 428) return false;
    const payload = await response.clone().json().catch(() => ({}));
    return payload?.code === 'AI_DATA_SHARING_CONSENT_REQUIRED';
  }

  async function consentFetch(input, init = {}) {
    const providerBound = isProviderBoundAction(input, init);
    const serverAuthoritative = isServerAuthoritativeConsentAction(input, init);
    if (!providerBound && !serverAuthoritative) return transport(input, init);
    if (providerBound && !currentUserAllowsSharing()) {
      const allowed = await requestDecision();
      if (!allowed) return syntheticRequiredResponse();
    }

    const preparedRequest = input instanceof Request ? new Request(input, init) : null;
    const send = () => (
      preparedRequest
        ? transport(preparedRequest.clone())
        : transport(input, init)
    );
    let response = await send();
    if (!await consentRequired(response)) return response;

    updateCurrentUser({
      aiDataSharingConsentRevokedAt: new Date().toISOString(),
    });
    const allowed = await requestDecision();
    if (!allowed) return response;

    response = await send();
    if (await consentRequired(response)) {
      updateCurrentUser({
        aiDataSharingConsentRevokedAt: new Date().toISOString(),
      });
    }
    return response;
  }

  consentFetch.__crumpAIDataSharingConsent = true;
  window.fetch = consentFetch;
  if (window.CrumpAPI && typeof window.CrumpAPI.fetch === 'function') {
    window.CrumpAPI.fetch = consentFetch;
  }
  window.CrumpAIDataSharingConsent = Object.freeze({
    version: CONSENT_VERSION,
    isAllowed: currentUserAllowsSharing,
    isProviderBoundAction,
    isServerAuthoritativeConsentAction,
    refresh: refreshSettingsState,
    review: reviewPermission,
    withdraw: withdrawPermission,
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireControls, {once: true});
  } else {
    wireControls();
  }
  window.addEventListener('crump:authenticated-ready', refreshSettingsState);
  window.addEventListener('crump:server-settings-applied', refreshSettingsState);
})();
