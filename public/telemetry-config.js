(() => {
  'use strict';

  function sanitizedEvent(event) {
    if (!event || typeof event.url !== 'string') return null;

    try {
      const url = new URL(event.url);
      url.search = '';
      url.hash = '';
      return {...event, url: url.toString()};
    } catch (_) {
      return null;
    }
  }

  window.va = window.va || function queueVercelAnalytics() {
    (window.vaq = window.vaq || []).push(arguments);
  };
  window.va('beforeSend', sanitizedEvent);

  window.si = window.si || function queueSpeedInsight() {
    (window.siq = window.siq || []).push(arguments);
  };
  window.si('beforeSend', sanitizedEvent);
})();
