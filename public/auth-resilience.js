(() => {
  'use strict';

  const DEFAULT_TIMEOUT_MS = 20_000;
  const SESSION_TIMEOUT_MS = 10_000;
  const LOGIN_TIMEOUT_MS = 30_000;

  async function request(url, options = {}, settings = {}) {
    const controller = new AbortController();
    const timeoutMs = Number(settings.timeoutMs) > 0
      ? Number(settings.timeoutMs)
      : DEFAULT_TIMEOUT_MS;
    let timeoutId;
    const deadline = new Promise((_, reject) => {
      timeoutId = window.setTimeout(() => {
        controller.abort();
        const error = new Error(settings.timeoutMessage || 'Ask Crump could not confirm that request in time. Try again.');
        error.code = 'AUTH_REQUEST_TIMEOUT';
        reject(error);
      }, timeoutMs);
    });

    try {
      return await Promise.race([deadline, (async () => {
      const response = await fetch(url, {
        credentials: 'same-origin',
        ...options,
        signal: controller.signal,
      });
      let data = {};
      try {
        data = await response.json();
      } catch (error) {
        if (controller.signal.aborted || error?.name === 'AbortError') throw error;
        if (response.ok) {
          const invalid = new Error('Ask Crump could not read the sign-in response. Your saved session has been kept. Try again.');
          invalid.code = 'AUTH_INVALID_RESPONSE';
          throw invalid;
        }
      }
      if (response.ok && (!data || typeof data !== 'object' || Array.isArray(data))) {
        const invalid = new Error('Ask Crump returned an incomplete sign-in response. Your saved session has been kept. Try again.');
        invalid.code = 'AUTH_INVALID_RESPONSE';
        throw invalid;
      }
      return {response, data};
      })()]);
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') {
        const timeoutError = new Error(
          settings.timeoutMessage || 'Ask Crump could not confirm that request in time. Try again.',
        );
        timeoutError.code = 'AUTH_REQUEST_TIMEOUT';
        throw timeoutError;
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  window.CrumpAuthTransport = Object.freeze({
    request,
    DEFAULT_TIMEOUT_MS,
    SESSION_TIMEOUT_MS,
    LOGIN_TIMEOUT_MS,
  });
})();
