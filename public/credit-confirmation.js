(() => {
  'use strict';

  if (window.CrumpCreditConfirmation) return;

  const REQUIRED_CODES = new Set([
    'CREDIT_CONFIRMATION_REQUIRED',
    'CREDIT_QUOTE_INVALID',
  ]);
  let activeDialog = null;
  let boundaryUnregister = null;

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

  function authBoundaryError() {
    return Object.assign(
      new Error('The signed-in account changed before credit use was confirmed. Nothing was charged.'),
      {code: 'AUTH_OWNER_MISMATCH', quiet: true},
    );
  }

  function dataFor(error) {
    return error?.data && typeof error.data === 'object' ? error.data : {};
  }

  function quoteFor(error) {
    const quote = dataFor(error).creditQuote;
    return quote && typeof quote === 'object' ? quote : null;
  }

  function isRequired(error) {
    return REQUIRED_CODES.has(
      String(dataFor(error).code || error?.code || '').toUpperCase(),
    ) && Boolean(quoteFor(error));
  }

  function closeDialog(result, {restoreFocus = true} = {}) {
    if (!activeDialog) return;
    const {node, resolve, priorFocus, authBoundary} = activeDialog;
    activeDialog = null;
    node.remove();
    document.body.classList.remove('crump-credit-confirming');
    if (restoreFocus && authBoundaryIsCurrent(authBoundary) && priorFocus instanceof HTMLElement) {
      priorFocus.focus({preventScroll: true});
    }
    resolve(result);
  }

  function present(quote, authBoundary = captureAuthBoundary()) {
    if (!quote || Number(quote.creditsRequired || 0) <= 0) {
      return Promise.resolve(null);
    }
    if (!authBoundaryIsCurrent(authBoundary)) return Promise.resolve(null);
    if (activeDialog) closeDialog(null);
    const credits = Math.max(0, Number(quote.creditsRequired || 0));
    const balance = Math.max(0, Number(quote.creditBalance || 0));
    const after = Math.max(0, Number(quote.balanceAfter || 0));
    const multi = quote.multiStep && typeof quote.multiStep === 'object'
      ? quote.multiStep
      : null;
    const node = document.createElement('div');
    node.className = 'crump-credit-confirmation';
    node.innerHTML = `
      <div class="crump-credit-confirmation__backdrop" data-credit-cancel></div>
      <section class="crump-credit-confirmation__sheet" role="dialog" aria-modal="true" aria-labelledby="crumpCreditTitle" aria-describedby="crumpCreditDetail">
        <button type="button" class="crump-credit-confirmation__close" data-credit-cancel aria-label="Cancel credit use">x</button>
        <span class="crump-credit-confirmation__eyebrow">EXACT CREDIT CHECK</span>
        <h2 id="crumpCreditTitle">Review before Crump starts</h2>
        <p id="crumpCreditDetail">Your included allowance is used. This action will use <strong>${credits.toLocaleString()} Crump Credits</strong>. Your balance after the action will be <strong>${after.toLocaleString()}</strong>.</p>
        ${multi ? `
          <dl class="crump-credit-confirmation__facts">
            <div><dt>Planned steps</dt><dd>${Number(multi.plannedSteps || 0).toLocaleString()}</dd></div>
            <div><dt>Chargeable steps</dt><dd>${Number(multi.chargeableSteps || 0).toLocaleString()}</dd></div>
            <div><dt>Per charged step</dt><dd>${Number(multi.perStepCredits || 0).toLocaleString()} credits</dd></div>
            <div><dt>Maximum</dt><dd>${credits.toLocaleString()} credits</dd></div>
          </dl>
          <p class="crump-credit-confirmation__stop">${String(multi.stoppingRule || 'The run stops before it can exceed the approved maximum.')}</p>
        ` : ''}
        <div class="crump-credit-confirmation__balance"><span>Current balance</span><strong>${balance.toLocaleString()} credits</strong></div>
        <div class="crump-credit-confirmation__actions">
          <button type="button" class="crump-credit-confirmation__cancel" data-credit-cancel>Not now</button>
          <button type="button" class="crump-credit-confirmation__confirm" data-credit-confirm>${multi ? 'Allow up to' : 'Use'} ${credits.toLocaleString()} credits</button>
        </div>
      </section>`;
    document.body.appendChild(node);
    document.body.classList.add('crump-credit-confirming');
    const priorFocus = document.activeElement;
    return new Promise(resolve => {
      activeDialog = {node, resolve, priorFocus, authBoundary};
      node.querySelectorAll('[data-credit-cancel]').forEach(button => {
        button.addEventListener('click', () => closeDialog(null));
      });
      node.querySelector('[data-credit-confirm]')?.addEventListener('click', () => {
        if (!authBoundaryIsCurrent(authBoundary)) {
          closeDialog(null, {restoreFocus: false});
          return;
        }
        closeDialog({
          quoteToken: String(quote.token || ''),
          confirmedCredits: credits,
        });
      });
      node.addEventListener('keydown', event => {
        if (event.key === 'Escape') closeDialog(null);
      });
      node.querySelector('[data-credit-confirm]')?.focus({preventScroll: true});
    });
  }

  async function run(executor, suppliedBoundary = null) {
    const authBoundary = suppliedBoundary || captureAuthBoundary();
    if (!authBoundaryIsCurrent(authBoundary)) throw authBoundaryError();
    let confirmation = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const result = await executor(confirmation, authBoundary);
        if (!authBoundaryIsCurrent(authBoundary)) throw authBoundaryError();
        return result;
      } catch (error) {
        if (!authBoundaryIsCurrent(authBoundary)) throw authBoundaryError();
        if (!isRequired(error) || attempt >= 2) throw error;
        confirmation = await present(quoteFor(error), authBoundary);
        if (!authBoundaryIsCurrent(authBoundary)) throw authBoundaryError();
        if (!confirmation) {
          const declined = new Error('Credit use was not approved. Nothing was charged.');
          declined.code = 'CREDIT_CONFIRMATION_DECLINED';
          declined.quiet = true;
          throw declined;
        }
      }
    }
    throw new Error('Crump could not confirm that credit quote.');
  }

  function scrubAuthBoundary() {
    if (activeDialog) closeDialog(null, {restoreFocus: false});
  }

  function ensureBoundaryRegistration() {
    if (boundaryUnregister || typeof window.CrumpAuthBoundary?.register !== 'function') return;
    boundaryUnregister = window.CrumpAuthBoundary.register(
      'credit-confirmation-private-dialog',
      scrubAuthBoundary,
    );
  }

  ensureBoundaryRegistration();
  window.addEventListener('crump:body-runtime-ready', ensureBoundaryRegistration, {once: true});

  window.CrumpCreditConfirmation = Object.freeze({
    isRequired,
    present,
    run,
    scrubAuthBoundary,
  });
})();

