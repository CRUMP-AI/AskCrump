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
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

    try {
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
      }
      return {response, data};
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
