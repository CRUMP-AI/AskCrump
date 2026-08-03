(() => {
  'use strict';

  let previouslyFocused = null;

  function closeModal(id) {
    document.getElementById(id)?.remove();
    previouslyFocused?.focus?.();
    previouslyFocused = null;
  }

  function createModal(id, title) {
    closeModal(id);
    previouslyFocused = document.activeElement;

    const root = document.createElement('div');
    root.id = id;
    root.className = 'account-modal';

    const backdrop = document.createElement('div');
    backdrop.className = 'account-modal-backdrop';

    const card = document.createElement('section');
    card.className = 'account-modal-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-labelledby', `${id}-title`);

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'account-modal-close';
    close.setAttribute('aria-label', 'Close');
    close.textContent = '×';

    const heading = document.createElement('h2');
    heading.id = `${id}-title`;
    heading.textContent = title;

    card.append(close, heading);
    root.append(backdrop, card);
    document.body.appendChild(root);

    const dismiss = () => closeModal(id);
    backdrop.addEventListener('click', dismiss);
    close.addEventListener('click', dismiss);
    root.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        dismiss();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = [...card.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      )].filter(element => !element.hidden && element.getClientRects().length > 0);
      if (!focusable.length) {
        event.preventDefault();
        card.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    requestAnimationFrame(() => close.focus());

    return { root, card };
  }

  function textElement(tag, text, className = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    return element;
  }

  function formatDate(value) {
    if (!value) return 'Unknown';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString();
  }

  async function revokeDevice(button, sessionId) {
    button.disabled = true;
    try {
      const response = await fetch('/api/auth/revoke-device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId }),
      });
      if (!response.ok) throw new Error('Unable to sign out that device.');
      button.closest('.device-row')?.remove();
    } catch (error) {
      button.disabled = false;
      window.showToast?.(error.message, 'error');
    }
  }

  async function openDevices() {
    const { card } = createModal('devicesModal', 'Signed-in devices');
    const status = textElement('p', 'Loading devices…', 'account-modal-status');
    status.setAttribute('role', 'status');
    card.appendChild(status);

    try {
      const response = await fetch('/api/auth/devices');
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Unable to load devices.');

      const list = document.createElement('div');
      list.className = 'device-list';
      const devices = Array.isArray(data.devices) ? data.devices : [];

      if (!devices.length) {
        list.appendChild(textElement('p', 'No active devices were found.'));
      }

      for (const device of devices) {
        const row = document.createElement('div');
        row.className = 'device-row';

        const details = document.createElement('div');
        details.appendChild(textElement('strong', device.device_name || 'Unknown device'));
        const activity = device.current
          ? `${device.platform || 'web'} · This device`
          : `${device.platform || 'web'} · Last active ${formatDate(device.last_activity)}`;
        details.appendChild(textElement('small', activity));
        row.appendChild(details);

        if (device.current) {
          row.appendChild(textElement('span', 'Current', 'device-current'));
        } else {
          const button = textElement('button', 'Sign out');
          button.type = 'button';
          button.addEventListener('click', () => revokeDevice(button, device.id));
          row.appendChild(button);
        }
        list.appendChild(row);
      }

      status.replaceWith(list);
    } catch (error) {
      status.textContent = error.message;
    }
  }

  function labeledInput(labelText, id, type, autocomplete) {
    const label = document.createElement('label');
    label.className = 'account-field';
    label.appendChild(document.createTextNode(labelText));
    const input = document.createElement('input');
    input.id = id;
    input.type = type;
    input.autocomplete = autocomplete;
    label.appendChild(input);
    return { label, input };
  }

  function openDeleteAccountDialog() {
    const { card } = createModal('deleteAccountModal', 'Delete account');
    card.appendChild(textElement(
      'p',
      'This permanently deletes your account, synchronized conversations, settings, and active sessions. This action cannot be undone.',
    ));

    if (window.BillingManager?.isNative?.()) {
      const warning = textElement(
        'p',
        'Deleting your Ask Crump account does not cancel an Apple App Store or Google Play subscription. Cancel the subscription in your device settings to prevent renewal.',
        'account-modal-warning',
      );
      card.appendChild(warning);
    }

    const password = labeledInput('Password', 'deleteAccountPassword', 'password', 'current-password');
    const confirmation = labeledInput('Type DELETE', 'deleteAccountConfirmation', 'text', 'off');
    const error = textElement('div', '', 'account-modal-error');
    error.setAttribute('aria-live', 'polite');
    const confirm = textElement('button', 'Delete account permanently', 'account-danger-button');
    confirm.type = 'button';
    card.append(password.label, confirmation.label, error, confirm);

    confirm.addEventListener('click', async () => {
      error.textContent = '';
      confirm.disabled = true;
      try {
        const response = await fetch('/api/account', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            password: password.input.value,
            confirmation: confirmation.input.value,
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Account deletion failed.');
        await window.CrumpAPI?.clearSessionToken?.();
        window.deviceAuth?.clearLocalState?.();
        window.location.replace('/');
      } catch (exception) {
        error.textContent = exception.message;
        confirm.disabled = false;
      }
    });
  }

  window.openDevices = openDevices;
  window.openDeleteAccountDialog = openDeleteAccountDialog;
})();
