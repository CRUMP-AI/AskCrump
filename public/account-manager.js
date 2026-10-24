(() => {
  'use strict';

  const EXPECTED_OWNER_HEADER = 'X-Ask-Crump-Expected-Owner';
  let previouslyFocused = null;
  let accountBoundaryGeneration = 0;
  let unregisterAuthBoundary = null;
  const accountRequests = new Set();

  function captureAuthBoundary() {
    const boundary = window.CrumpAuthBoundary;
    const ownerId = String(
      typeof boundary?.authenticatedUserId === 'function'
        ? boundary.authenticatedUserId()
        : window.currentUser?.id || '',
    ).trim();
    const rawRevision = typeof boundary?.revision === 'function' ? boundary.revision() : 0;
    const revision = Number(rawRevision);
    return Object.freeze({
      ownerId,
      revision: Number.isFinite(revision) ? revision : 0,
      generation: accountBoundaryGeneration,
    });
  }

  function authBoundaryIsCurrent(snapshot) {
    if (!snapshot?.ownerId || snapshot.generation !== accountBoundaryGeneration) return false;
    const current = captureAuthBoundary();
    return current.ownerId === snapshot.ownerId && current.revision === snapshot.revision;
  }

  function newAccountRequest() {
    const controller = new AbortController();
    accountRequests.add(controller);
    return controller;
  }

  function releaseAccountRequest(controller) {
    accountRequests.delete(controller);
  }

  function closeModal(id, {restoreFocus = true} = {}) {
    document.getElementById(id)?.remove();
    if (restoreFocus && previouslyFocused?.isConnected) previouslyFocused.focus?.();
    previouslyFocused = null;
  }

  function scrubAuthBoundary() {
    accountBoundaryGeneration += 1;
    accountRequests.forEach(controller => controller.abort());
    accountRequests.clear();
    closeModal('devicesModal', {restoreFocus: false});
    closeModal('deleteAccountModal', {restoreFocus: false});
    previouslyFocused = null;
  }

  function ensureAuthBoundaryRegistration() {
    if (unregisterAuthBoundary || typeof window.CrumpAuthBoundary?.register !== 'function') return;
    unregisterAuthBoundary = window.CrumpAuthBoundary.register(
      'account-dialogs',
      scrubAuthBoundary,
    );
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

  async function revokeDevice(button, sessionId, authBoundary) {
    if (!authBoundaryIsCurrent(authBoundary) || !button?.isConnected) return;
    const controller = newAccountRequest();
    button.disabled = true;
    try {
      const response = await fetch('/api/auth/revoke-device', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          [EXPECTED_OWNER_HEADER]: authBoundary.ownerId,
        },
        body: JSON.stringify({ sessionId }),
        signal: controller.signal,
      });
      if (!authBoundaryIsCurrent(authBoundary) || !button.isConnected) return;
      if (!response.ok) throw new Error('Unable to sign out that device.');
      button.closest('.device-row')?.remove();
    } catch (error) {
      if (!authBoundaryIsCurrent(authBoundary) || controller.signal.aborted || !button.isConnected) return;
      button.disabled = false;
      window.showToast?.(error.message, 'error');
    } finally {
      releaseAccountRequest(controller);
    }
  }

  async function openDevices() {
    ensureAuthBoundaryRegistration();
    const authBoundary = captureAuthBoundary();
    if (!authBoundary.ownerId || !authBoundaryIsCurrent(authBoundary)) return;
    const { root, card } = createModal('devicesModal', 'Signed-in devices');
    const status = textElement('p', 'Loading devices…', 'account-modal-status');
    status.setAttribute('role', 'status');
    card.appendChild(status);
    const controller = newAccountRequest();

    try {
      const response = await fetch('/api/auth/devices', {
        headers: {[EXPECTED_OWNER_HEADER]: authBoundary.ownerId},
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!authBoundaryIsCurrent(authBoundary) || !root.isConnected) return;
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
          button.addEventListener('click', () => revokeDevice(button, device.id, authBoundary));
          row.appendChild(button);
        }
        list.appendChild(row);
      }

      status.replaceWith(list);
    } catch (error) {
      if (!authBoundaryIsCurrent(authBoundary) || controller.signal.aborted || !root.isConnected) return;
      status.textContent = error.message;
    } finally {
      releaseAccountRequest(controller);
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
    ensureAuthBoundaryRegistration();
    const authBoundary = captureAuthBoundary();
    if (!authBoundary.ownerId || !authBoundaryIsCurrent(authBoundary)) return;
    const { root, card } = createModal('deleteAccountModal', 'Delete account');
    card.appendChild(textElement(
      'p',
      'This immediately ends account access and deletes synchronized records. Private files are then permanently removed by a background cleanup that is retried and verified. This action cannot be undone.',
    ));

    const warning = textElement(
      'p',
      'A web subscription is canceled immediately during deletion; deletion does not issue a refund. Apple App Store or Google Play subscriptions must be canceled separately in store settings to prevent renewal.',
      'account-modal-warning',
    );
    card.appendChild(warning);

    const password = labeledInput('Password', 'deleteAccountPassword', 'password', 'current-password');
    const confirmation = labeledInput('Type DELETE', 'deleteAccountConfirmation', 'text', 'off');
    const error = textElement('div', '', 'account-modal-error');
    error.setAttribute('aria-live', 'polite');
    const confirm = textElement('button', 'Schedule permanent deletion', 'account-danger-button');
    confirm.type = 'button';
    card.append(password.label, confirmation.label, error, confirm);

    confirm.addEventListener('click', async () => {
      if (!authBoundaryIsCurrent(authBoundary) || !root.isConnected) return;
      error.textContent = '';
      confirm.disabled = true;
      const nativeToken = window.CrumpAPI?.isNative
        ? window.CrumpAPI?.getSessionToken?.() || null
        : null;
      const controller = newAccountRequest();
      try {
        const response = await fetch('/api/account', {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
            [EXPECTED_OWNER_HEADER]: authBoundary.ownerId,
          },
          body: JSON.stringify({
            password: password.input.value,
            confirmation: confirmation.input.value,
          }),
          signal: controller.signal,
        });
        const data = await response.json().catch(() => ({}));
        if (!authBoundaryIsCurrent(authBoundary) || !root.isConnected) return;
        if (!response.ok) throw new Error(data.error || 'Account deletion failed.');
        const cleared = await window.CrumpAPI?.clearSessionToken?.(nativeToken);
        if (window.CrumpAPI?.isNative && cleared === false) return;
        if (!authBoundaryIsCurrent(authBoundary)) return;
        const localCleared = window.deviceAuth?.clearLocalState?.(authBoundary.ownerId);
        if (localCleared === false) return;
        window.location.replace('/');
      } catch (exception) {
        if (!authBoundaryIsCurrent(authBoundary) || controller.signal.aborted || !root.isConnected) return;
        error.textContent = exception.message;
        confirm.disabled = false;
      } finally {
        releaseAccountRequest(controller);
      }
    });
  }

  window.CrumpAccountBoundary = Object.freeze({scrubAuthBoundary});
  window.openDevices = openDevices;
  window.openDeleteAccountDialog = openDeleteAccountDialog;
  window.addEventListener('crump:authenticated-ready', ensureAuthBoundaryRegistration);
  window.addEventListener('crump:authentication-required', scrubAuthBoundary);
  ensureAuthBoundaryRegistration();
})();
