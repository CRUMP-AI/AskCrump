(() => {
  'use strict';

  window.si = window.si || function queueSpeedInsight() {
    (window.siq = window.siq || []).push(arguments);
  };

  window.si('beforeSend', event => {
    if (!event || typeof event.url !== 'string') return null;

    try {
      const url = new URL(event.url);
      url.search = '';
      url.hash = '';
      return {...event, url: url.toString()};
    } catch (_) {
      return null;
    }
  });
})();
