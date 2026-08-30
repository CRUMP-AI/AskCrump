(() => {
  'use strict';

  const SHARE_URL = 'https://www.askcrump.com/?acquisition=referral&source=response-share';
  const SHARE_TEXT = 'Ask Crump helped me move work forward. Try it free.';

  async function record(source) {
    const day = new Date().toISOString().slice(0, 10);
    await window.CrumpAnalytics?.track?.('ResponseShared', {
      eventKey: `response-share:${day}`,
      source,
    });
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      const area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      try {
        area.select();
        return document.execCommand?.('copy') === true;
      } finally {
        area.remove();
      }
    }
  }

  async function shareAskCrumpWorkspace() {
    const payload = {title: 'Ask Crump', text: SHARE_TEXT, url: SHARE_URL};
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share(payload);
        await record('useful_prompt_native');
        window.showToast?.('Shared', 'success');
        return true;
      } catch (error) {
        if (error?.name === 'AbortError') return false;
      }
    }
    if (!await copy(`${SHARE_TEXT} ${SHARE_URL}`)) return false;
    await record('useful_prompt_clipboard');
    window.showToast?.('Ask Crump link copied', 'success');
    return true;
  }

  window.shareAskCrumpWorkspace = shareAskCrumpWorkspace;
})();
