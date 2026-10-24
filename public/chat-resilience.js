(() => {
  'use strict';

  if (window.CrumpChatTransport) return;

  const USAGE_TIMEOUT_MS = 10_000;
  const ACK_TIMEOUT_MS = 12_000;
  const REPLY_TIMEOUT_MS = 105_000;
  const STATUS_TIMEOUT_MS = 10_000;
  const STATUS_RETRY_MS = 3_000;
  const STATUS_MAX_POLLS = 10;
  const FEATURE_ACCESS_CODES = new Set([
    'SUBSCRIPTION_REQUIRED',
    'CREDITS_REQUIRED',
    'FEATURE_LIMIT_REACHED',
  ]);

  const wait = milliseconds => new Promise(resolve => window.setTimeout(resolve, milliseconds));

  function currentOwnerId() {
    const boundary = window.CrumpAuthBoundary;
    return String(
      typeof boundary?.authenticatedUserId === 'function'
        ? boundary.authenticatedUserId()
        : window.currentUser?.id || ''
    ).trim();
  }

  function requestOwnerId(options = {}) {
    return String(options?.expectedOwnerId || currentOwnerId()).trim();
  }

  function ownerIsCurrent(expectedOwnerId) {
    return !expectedOwnerId || currentOwnerId() === expectedOwnerId;
  }

  function assertOwnerCurrent(expectedOwnerId) {
    if (ownerIsCurrent(expectedOwnerId)) return;
    const error = transportError(
      'This message belongs to a previous authentication session.',
      'AUTH_OWNER_CHANGED',
    );
    error.quiet = true;
    error.staleAuth = true;
    throw error;
  }

  function transportError(message, code, cause) {
    const error = new Error(message);
    error.code = code;
    error.cause = cause;
    return error;
  }

  function safeImageRecovery(value) {
    const changeRequired = String(value?.changeRequired || '');
    if (
      value?.action !== 'revise_image_request'
      || value?.usageRestored !== true
      || !['prompt_or_reference', 'reference'].includes(changeRequired)
    ) return null;
    return Object.freeze({action: 'revise_image_request', usageRestored: true, changeRequired});
  }

  function apiError(response, data, fallback) {
    applyServerAllowance(data);
    const error = new Error(data?.message || data?.error || fallback || `Request failed (${response.status})`);
    error.code = data?.code;
    error.shouldRetry = Boolean(data?.shouldRetry);
    error.retryAfter = data?.retryAfter;
    error.status = response.status;
    error.data = data;
    error.recovery = safeImageRecovery(data?.recovery);
    return error;
  }

  function applyServerAllowance(data) {
    window.CrumpAccess?.applyServerAllowance?.(data);
  }

  function offerPlanRecovery(data) {
    const code = String(data?.code || '').toUpperCase();
    if (!data?.upgradeRequired && !FEATURE_ACCESS_CODES.has(code)) return;
    const creditsRequired = data?.creditsRequired == null ? null : Number(data.creditsRequired);
    const creditBalance = data?.creditBalance == null ? null : Number(data.creditBalance);
    window.showUpgradePrompt?.({
      accessCode: code,
      ...(code === 'SUBSCRIPTION_REQUIRED' && data?.requiredTier ? {plan: data.requiredTier} : {}),
      ...(Number.isFinite(creditsRequired) ? {creditsRequired: Math.max(0, Math.floor(creditsRequired))} : {}),
      ...(Number.isFinite(creditBalance) ? {creditBalance: Math.max(0, Math.floor(creditBalance))} : {}),
      source: 'feature_recovery',
    });
  }

  function notifyCreditBalance(data) {
    const balance = Number(
      data?.featureUsage?.creditBalance
      ?? data?.dailyUsage?.creditBalance
      ?? data?.credits?.balance,
    );
    if (!Number.isFinite(balance)) return;
    window.dispatchEvent(new CustomEvent('crump:credits-updated', {
      detail: {balance: Math.max(0, balance)},
    }));
  }

  async function requestJson(path, options, config) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), config.timeoutMs);
    const expectedOwnerId = requestOwnerId(config);
    try {
      assertOwnerCurrent(expectedOwnerId);
      const response = await fetch(path, {
        credentials: 'same-origin',
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(expectedOwnerId ? {'X-Ask-Crump-Expected-Owner': expectedOwnerId} : {}),
          ...(options?.headers || {}),
        },
      });
      const data = await response.json().catch(() => ({}));
      assertOwnerCurrent(expectedOwnerId);
      return {response, data};
    } catch (error) {
      if (error?.code === 'AUTH_OWNER_CHANGED') throw error;
      if (error?.name === 'AbortError') {
        throw transportError(config.timeoutMessage, 'CLIENT_TIMEOUT', error);
      }
      throw transportError(config.networkMessage, 'NETWORK_INTERRUPTED', error);
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  async function ensureUsage(options = {}) {
    const expectedOwnerId = requestOwnerId(options);
    const {response, data} = await requestJson('/api/usage/check', {method: 'GET'}, {
      expectedOwnerId,
      timeoutMs: USAGE_TIMEOUT_MS,
      timeoutMessage: 'Message check took too long. Your draft is still here — try again.',
      networkMessage: 'Crump could not check message availability. Check your connection and try again.',
    });
    assertOwnerCurrent(expectedOwnerId);
    if (response.status === 401) throw new Error('Your session expired. Please sign in again.');
    if (!response.ok) {
      throw apiError(response, data, 'Crump could not check message availability. Try again.');
    }
    applyServerAllowance(data);
    notifyCreditBalance(data);
    const freeAllowance = data?.freeMessageAllowance
      || data?.dailyUsage?.freeMessageAllowance
      || data?.usage?.freeMessageAllowance;
    if (
      window.CrumpAccess?.isFree?.()
      && freeAllowance
      && Number(freeAllowance.remaining) <= 0
    ) {
      const error = apiError(
        response,
        {...data, code: 'FREE_TEXT_LIMIT_REACHED'},
        'Your five free text messages in the rolling 24-hour window have been used.',
      );
      throw error;
    }
    if (data.limits?.messages !== -1 && data.usage?.messages >= data.limits?.messages) {
      window.showUpgradePrompt?.({
        accessCode: 'USAGE_LIMIT',
        usageLimit: Math.max(0, Number(data.limits?.messages || 0)),
        source: 'feature_recovery',
      });
      throw new Error('Your daily message limit has been reached.');
    }
    return data;
  }

  async function acknowledge(payload, options = {}) {
    const expectedOwnerId = requestOwnerId(options);
    const {response, data} = await requestJson('/api/chat/ack', {
      method: 'POST',
      body: JSON.stringify(payload),
    }, {
      expectedOwnerId,
      timeoutMs: ACK_TIMEOUT_MS,
      timeoutMessage: 'Crump could not confirm this message in time. Tap the message to retry.',
      networkMessage: 'The message connection was interrupted. Tap the message to retry.',
    });
    assertOwnerCurrent(expectedOwnerId);
    if (response.status === 401) window.deviceAuth?.clearLocalState?.(expectedOwnerId);
    if (!response.ok) throw apiError(response, data, 'Crump could not receive the message.');
    return data;
  }

  async function checkJob(messageId, expectedOwnerId) {
    const {response, data} = await requestJson(
      `/api/chat/status/${encodeURIComponent(messageId)}`,
      {method: 'GET', cache: 'no-store'},
      {
        expectedOwnerId,
        timeoutMs: STATUS_TIMEOUT_MS,
        timeoutMessage: 'Reply recovery took too long.',
        networkMessage: 'Reply recovery lost its connection.',
      },
    );
    assertOwnerCurrent(expectedOwnerId);
    if (response.status === 401) {
      window.deviceAuth?.clearLocalState?.(expectedOwnerId);
      throw new Error('Your session expired. Please sign in again.');
    }
    if (response.status === 404 || data.status === 'missing') return {state: 'retryable'};
    if (response.status === 202 && data.status === 'processing') {
      return {state: 'processing', retryAfter: data.retryAfter};
    }
    if (response.ok && data.status === 'completed') return {state: 'completed', data};
    if (data.status === 'retryable' || data.status === 'failed') return {state: 'retryable'};
    throw apiError(response, data, 'Crump could not recover this reply.');
  }

  async function recover(messageId, {maxPolls = STATUS_MAX_POLLS, expectedOwnerId: requestedOwnerId} = {}) {
    const expectedOwnerId = requestOwnerId({expectedOwnerId: requestedOwnerId});
    const polls = Math.max(1, Math.min(STATUS_MAX_POLLS, Number(maxPolls) || 1));
    let lastTransportError = null;
    for (let attempt = 0; attempt < polls; attempt += 1) {
      let job;
      try {
        job = await checkJob(messageId, expectedOwnerId);
        lastTransportError = null;
      } catch (error) {
        if (!['CLIENT_TIMEOUT', 'NETWORK_INTERRUPTED'].includes(error?.code)) throw error;
        lastTransportError = error;
      }
      if (job?.state === 'completed') {
        applyServerAllowance(job.data);
        notifyCreditBalance(job.data);
        return job.data;
      }
      if (job?.state === 'retryable') return null;
      if (attempt < polls - 1) {
        const retryAfter = Math.min(10, Math.max(1, Number(job?.retryAfter || STATUS_RETRY_MS / 1000)));
        await wait(retryAfter * 1000);
        assertOwnerCurrent(expectedOwnerId);
      }
    }
    if (lastTransportError) {
      throw new Error('Crump could not reconnect to this reply. Tap the message to try again.');
    }
    const error = new Error('Crump is still working on this message. Tap it to check again.');
    error.code = 'REPLY_PENDING';
    throw error;
  }

  async function sendWithRetries(requestBody, expectedOwnerId) {
    let lastError = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      let response;
      let data;
      try {
        ({response, data} = await requestJson('/api/chat', {
          method: 'POST',
          body: JSON.stringify(requestBody),
        }, {
          expectedOwnerId,
          timeoutMs: REPLY_TIMEOUT_MS,
          timeoutMessage: 'Crump took too long to reconnect to this reply. Tap the message to try again.',
          networkMessage: 'The reply connection was interrupted. Tap the message to recover it.',
        }));
        assertOwnerCurrent(expectedOwnerId);
      } catch (error) {
        if (['CLIENT_TIMEOUT', 'NETWORK_INTERRUPTED'].includes(error?.code)) {
          const recovered = await recover(requestBody.messageId, {expectedOwnerId});
          if (recovered) return recovered;
        }
        throw error;
      }

      if (response.ok) {
        applyServerAllowance(data);
        notifyCreditBalance(data);
        return data;
      }
      lastError = apiError(response, data, 'Crump could not complete that request.');
      if (response.status === 401) window.deviceAuth?.clearLocalState?.(expectedOwnerId);
      offerPlanRecovery(data);
      if (data.code === 'REPLY_IN_PROGRESS') {
        const recovered = await recover(requestBody.messageId, {expectedOwnerId});
        if (recovered) return recovered;
      }
      if (!(lastError.shouldRetry && attempt === 0)) throw lastError;
      const retryAfter = Math.min(30, Math.max(1, Number(lastError.retryAfter || 3)));
      window.CrumpPresence?.update?.('thinking');
      await wait(retryAfter * 1000);
      assertOwnerCurrent(expectedOwnerId);
    }
    throw lastError || new Error('Crump could not complete that request.');
  }

  async function send(requestBody, options = {}) {
    const expectedOwnerId = requestOwnerId(options);
    const controller = window.CrumpCreditConfirmation;
    if (!controller?.run) return sendWithRetries(requestBody, expectedOwnerId);
    return controller.run(confirmation => sendWithRetries({
      ...requestBody,
      ...(confirmation ? {creditConfirmation: confirmation} : {}),
    }, expectedOwnerId));
  }

  window.CrumpChatTransport = Object.freeze({acknowledge, ensureUsage, recover, send});
})();
