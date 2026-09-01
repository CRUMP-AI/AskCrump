(() => {
  'use strict';

  if (window.__crumpBilling51Loaded) return;
  window.__crumpBilling51Loaded = true;

  const state = {
    modal: null,
    credits: 0,
    loading: false,
    lastBalanceFetchAt: 0,
    balanceRequest: null,
    trigger: null,
    background: [],
  };

  const BALANCE_STALE_MS = 5 * 60 * 1000;
  const BILLING_REQUEST_TIMEOUT_MS = 15_000;

  const $ = (selector, root = document) => root.querySelector(selector);
  const native = () => Boolean(window.BillingManager?.isNative?.());
  const recoverySources = Object.freeze({
    CREDITS_REQUIRED: 'recovery_credits',
    SUBSCRIPTION_REQUIRED: 'recovery_subscription',
    FEATURE_LIMIT_REACHED: 'recovery_feature',
    PROJECT_LIMIT_REACHED: 'recovery_project',
    USAGE_LIMIT: 'recovery_usage',
  });
  const planCenterSources = new Set([
    'settings',
    'plan_intent',
    'upgrade_prompt',
    ...Object.values(recoverySources),
  ]);
  const BILLING_FOCUSABLE = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[role="button"][tabindex]:not([tabindex="-1"])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(',');

  function moneySafe(value, fallback) {
    const text = String(value || fallback || '').trim();
    return text || fallback;
  }

  function planCenterSource(options = {}) {
    const recoverySource = recoverySources[String(options?.accessCode || '').toUpperCase()];
    if (recoverySource) return recoverySource;
    if (['professional', 'enterprise'].includes(String(options?.plan || '').toLowerCase())) {
      return 'plan_intent';
    }
    const requested = String(options?.source || '').trim().toLowerCase();
    return planCenterSources.has(requested) ? requested : 'settings';
  }

  function boundedCount(value) {
    if (value == null || !Number.isFinite(Number(value))) return null;
    return Math.max(0, Math.floor(Number(value)));
  }

  function billingRecoveryContext(options = {}) {
    const code = String(options?.accessCode || '').toUpperCase();
    const creditsRequired = boundedCount(options?.creditsRequired);
    const creditBalance = boundedCount(options?.creditBalance);
    const usageLimit = boundedCount(options?.usageLimit);
    const plan = ['professional', 'enterprise'].includes(String(options?.plan || '').toLowerCase())
      ? String(options.plan).toLowerCase()
      : '';
    if (code === 'CREDITS_REQUIRED') {
      return {
        code,
        kind: 'credits',
        title: creditsRequired == null ? 'More credits are needed to continue.' : `This action needs ${creditsRequired.toLocaleString()} credits.`,
        detail: creditBalance == null
          ? 'Review the credit packs below, then return and retry when you are ready.'
          : `You currently have ${creditBalance.toLocaleString()}. Add enough credits below, then return and retry.`,
      };
    }
    if (code === 'SUBSCRIPTION_REQUIRED') {
      const label = plan === 'enterprise' ? 'Enterprise' : 'Professional';
      return {
        code,
        kind: 'plan',
        plan: plan || 'professional',
        title: `${label} access is needed for this feature.`,
        detail: 'Compare the monthly plans below. Nothing changes until you choose a plan and confirm checkout.',
      };
    }
    if (code === 'FEATURE_LIMIT_REACHED') {
      return {
        code,
        kind: 'plan',
        title: 'Your included use for this feature is complete.',
        detail: 'Compare monthly plans below, or return after the allowance resets. Nothing changes automatically.',
      };
    }
    if (code === 'PROJECT_LIMIT_REACHED') {
      return {
        code,
        kind: 'plan',
        title: 'Your active Project limit has been reached.',
        detail: 'Compare monthly plans below before creating another Project. Nothing changes until you choose and confirm.',
      };
    }
    if (code === 'USAGE_LIMIT') {
      return {
        code,
        kind: 'plan',
        title: usageLimit ? `Today's ${usageLimit.toLocaleString()} included messages have been used.` : 'Today\'s included messages have been used.',
        detail: 'Compare monthly plans for more included daily messages, or return after the daily allowance resets.',
      };
    }
    return null;
  }

  function billingRecoveryMarkup(context) {
    if (!context) return '';
    return `<aside class="billing51-recovery" data-recovery-kind="${context.kind}" aria-label="Why Plan and credits opened"><span>CONTINUE YOUR WORK</span><h3>${context.title}</h3><p>${context.detail}</p></aside>`;
  }

  async function recordPlanCenterView(options = {}) {
    const source = planCenterSource(options);
    document.documentElement.dataset.crumpPlanCenterEvent = `pending:${source}`;
    try {
      if (await window.CrumpAnalytics?.track?.('PlanCenterViewed', {
        eventKey: 'plan-center-viewed',
        source,
      })) {
        document.documentElement.dataset.crumpPlanCenterEvent = `accepted:${source}`;
        return true;
      }
      const response = await fetch('/api/analytics/events', {
        method: 'POST',
        credentials: 'same-origin',
        keepalive: true,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          eventName: 'PlanCenterViewed',
          eventKey: 'plan-center-viewed',
          source,
        }),
      });
      document.documentElement.dataset.crumpPlanCenterEvent =
        `${response.ok ? 'accepted' : 'rejected'}:${source}`;
      return response.ok;
    } catch (_) {
      document.documentElement.dataset.crumpPlanCenterEvent = `failed:${source}`;
      return false;
    }
  }

  async function jsonFetch(url, options = {}) {
    const {
      timeoutMs = BILLING_REQUEST_TIMEOUT_MS,
      signal: upstreamSignal,
      ...requestOptions
    } = options;
    const controller = new AbortController();
    const abortFromUpstream = () => controller.abort();
    if (upstreamSignal?.aborted) controller.abort();
    else upstreamSignal?.addEventListener?.('abort', abortFromUpstream, {once: true});
    const timeoutId = window.setTimeout(
      () => controller.abort(),
      Math.max(1, Number(timeoutMs) || BILLING_REQUEST_TIMEOUT_MS),
    );
    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        ...requestOptions,
        signal: controller.signal,
        headers: {
          ...(requestOptions.body ? {'Content-Type': 'application/json'} : {}),
          ...(requestOptions.headers || {}),
        },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) {
        const error = new Error(data.error || 'Billing could not complete that request.');
        error.code = data.code;
        throw error;
      }
      return data;
    } catch (error) {
      if (controller.signal.aborted && !upstreamSignal?.aborted) {
        const timeoutError = new Error('Billing took too long. Check your connection and try again.');
        timeoutError.code = 'BILLING_REQUEST_TIMEOUT';
        throw timeoutError;
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
      upstreamSignal?.removeEventListener?.('abort', abortFromUpstream);
    }
  }

  function visibleElement(element) {
    return Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));
  }

  function restoreBillingBackground() {
    state.background.forEach(item => {
      if (!item.element?.isConnected) return;
      if (!item.inert) item.element.removeAttribute('inert');
      if (item.ariaHidden === null) item.element.removeAttribute('aria-hidden');
      else item.element.setAttribute('aria-hidden', item.ariaHidden);
    });
    state.background = [];
  }

  function isolateBillingBackground(modal) {
    restoreBillingBackground();
    state.background = [...document.body.children]
      .filter(element => element !== modal)
      .filter(element => !['SCRIPT', 'STYLE', 'LINK'].includes(element.tagName))
      .filter(element => element.id !== 'toastContainer')
      .filter(visibleElement)
      .map(element => ({
        element,
        inert: element.hasAttribute('inert'),
        ariaHidden: element.getAttribute('aria-hidden'),
      }));
    state.background.forEach(item => {
      item.element.setAttribute('inert', '');
      item.element.setAttribute('aria-hidden', 'true');
    });
  }

  function billingFocusable(modal) {
    const sheet = $('.billing51-sheet', modal);
    if (!sheet) return [];
    return [...sheet.querySelectorAll(BILLING_FOCUSABLE)].filter(element => {
      if (element.closest('[hidden], [aria-hidden="true"]')) return false;
      return visibleElement(element);
    });
  }

  function containBillingFocus(event, modal) {
    if (event.key !== 'Tab') return false;
    const focusable = billingFocusable(modal);
    const sheet = $('.billing51-sheet', modal);
    if (!focusable.length) {
      event.preventDefault();
      sheet?.focus({preventScroll: true});
      return true;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !modal.contains(active))) {
      event.preventDefault();
      last.focus({preventScroll: true});
      return true;
    }
    if (!event.shiftKey && (active === last || !modal.contains(active))) {
      event.preventDefault();
      first.focus({preventScroll: true});
      return true;
    }
    return false;
  }

  function close({restoreFocus = true} = {}) {
    const trigger = state.trigger;
    state.modal?.remove();
    state.modal = null;
    document.body.classList.remove('billing51-open');
    restoreBillingBackground();
    state.trigger = null;
    if (restoreFocus && trigger?.isConnected && !trigger.disabled) {
      requestAnimationFrame(() => trigger.focus?.({preventScroll: true}));
    }
  }

  function setBusy(button, busy, label = null) {
    if (!button) return;
    if (busy) {
      button.dataset.previousLabel = button.textContent;
      button.disabled = true;
      button.textContent = label || 'Working…';
    } else {
      button.disabled = false;
      button.textContent = button.dataset.previousLabel || button.textContent;
      delete button.dataset.previousLabel;
    }
  }

  async function buyCredits(pack, button) {
    setBusy(button, true, native() ? 'Opening store…' : 'Opening checkout…');
    try {
      if (native()) {
        await window.BillingManager.purchaseCredits(pack.code);
        window.showToast?.(`${pack.credits} credits added`, 'success');
        await hydrate(state.modal);
        return;
      }
      const result = await jsonFetch('/api/billing/credits/checkout', {
        method: 'POST',
        body: JSON.stringify({pack: pack.code}),
      });
      if (!result.url) throw new Error('Secure checkout did not return a destination.');
      window.location.assign(result.url);
    } catch (error) {
      window.showToast?.(error.message || 'Credit purchase could not be opened.', 'error');
      setBusy(button, false);
    }
  }

  async function buyPlan(tier, button) {
    setBusy(button, true, native() ? 'Opening store…' : 'Opening checkout…');
    try {
      if (native()) {
        await window.BillingManager.purchase(tier);
        window.showToast?.('Subscription activated', 'success');
        await hydrate(state.modal);
        return;
      }
      const attemptId = window.BillingManager?.subscriptionCheckoutAttempt?.(tier);
      const response = await jsonFetch('/api/stripe/create-checkout-session', {
        method: 'POST',
        body: JSON.stringify({tier, attemptId}),
      });
      if (!response.url) throw new Error('Secure checkout did not return a destination.');
      window.location.assign(response.url);
      window.BillingManager?.completeSubscriptionCheckoutAttempt?.(tier, attemptId);
    } catch (error) {
      window.showToast?.(error.message || 'Subscription checkout could not be opened.', 'error');
      setBusy(button, false);
    }
  }

  async function restore(button) {
    setBusy(button, true, 'Restoring…');
    try {
      await window.BillingManager.restore();
      window.showToast?.('Purchases restored', 'success');
      await hydrate(state.modal);
    } catch (error) {
      window.showToast?.(error.message || 'No purchases were restored.', 'error');
    } finally {
      setBusy(button, false);
    }
  }

  async function manageSubscription(button) {
    setBusy(button, true, 'Opening…');
    try {
      await window.BillingManager.manageSubscription();
    } catch (error) {
      window.showToast?.(error.message || 'Subscription management could not be opened.', 'error');
      setBusy(button, false);
    }
  }

  function progressMarkup(daily) {
    const limit = Number(daily?.limit ?? 0);
    const used = Number(daily?.used ?? 0);
    if (limit < 0) {
      return `
        <div class="billing51-allowance">
          <div><span>Included today</span><strong>Unlimited</strong></div>
          <div class="billing51-progress"><i style="width:100%"></i></div>
        </div>`;
    }
    const remaining = Math.max(0, Number(daily?.remaining ?? Math.max(0, limit - used)));
    const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 100;
    return `
      <div class="billing51-allowance">
        <div><span>Included today</span><strong>${remaining} left</strong></div>
        <div class="billing51-progress"><i style="width:${percent}%"></i></div>
      </div>`;
  }

  function creditHistoryLabel(item) {
    const delta = Number(item?.delta || 0);
    const reason = String(item?.reason || '');
    if (reason === 'beta_qa_grant') return 'Founder QA credits';
    if (reason === 'credit_purchase') return 'Credit purchase';
    if (reason === 'refund') return 'Returned credit';
    if (delta < 0) return 'Crump request';
    return 'Credit adjustment';
  }

  function renderHistory(history = []) {
    const host = $('#billing51History', state.modal);
    if (!host) return;
    host.replaceChildren();
    const visible = history.slice(0, 8);
    if (!visible.length) {
      host.innerHTML = '<p class="billing51-empty">No credit activity yet.</p>';
      return;
    }
    visible.forEach(item => {
      const row = document.createElement('div');
      row.className = 'billing51-history-row';
      const label = document.createElement('span');
      label.textContent = creditHistoryLabel(item);
      const amount = document.createElement('strong');
      const delta = Number(item.delta || 0);
      amount.textContent = `${delta > 0 ? '+' : ''}${delta}`;
      amount.className = delta > 0 ? 'is-positive' : '';
      row.append(label, amount);
      host.appendChild(row);
    });
  }

  function packCard(pack, nativeProduct) {
    const article = document.createElement('article');
    article.className = 'billing51-pack';
    const amount = document.createElement('strong');
    amount.className = 'billing51-pack-amount';
    amount.textContent = String(pack.credits);
    const label = document.createElement('span');
    label.className = 'billing51-pack-label';
    label.textContent = 'Crump Credits';
    const price = document.createElement('div');
    price.className = 'billing51-pack-price';
    const displayPrice = moneySafe(nativeProduct?.price, pack.price);
    price.textContent = displayPrice;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'billing51-buy';
    const available = native() ? Boolean(nativeProduct?.package) : pack.available !== false;
    button.disabled = !available;
    button.textContent = available ? 'Add credits' : 'Not configured';
    button.setAttribute(
      'aria-label',
      available
        ? `Add ${pack.credits} Crump Credits for ${displayPrice}`
        : `${pack.credits} Crump Credits are not available`,
    );
    button.addEventListener('click', () => buyCredits(pack, button));
    article.append(amount, label, price, button);
    return article;
  }

  function planCard(plan, product, billingStatus) {
    const article = document.createElement('article');
    article.className = `billing51-plan ${plan.id === 'professional' ? 'is-featured' : ''}`;
    article.dataset.crumpPlan = plan.id;
    const top = document.createElement('div');
    top.className = 'billing51-plan-top';
    const name = document.createElement('strong');
    name.textContent = plan.name;
    const price = document.createElement('span');
    price.textContent = moneySafe(product?.price, plan.fallback);
    top.append(name, price);
    const detail = document.createElement('p');
    detail.className = 'billing51-plan-summary';
    detail.textContent = plan.detail;
    const benefits = document.createElement('ul');
    benefits.className = 'billing51-plan-benefits';
    plan.benefits.forEach(item => {
      const benefit = document.createElement('li');
      benefit.textContent = item;
      benefits.appendChild(benefit);
    });
    const meterNote = document.createElement('p');
    meterNote.className = 'billing51-plan-meter-note';
    meterNote.textContent = plan.meterNote;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'billing51-plan-button';
    const currentTier = String(billingStatus?.tier || 'free').toLowerCase();
    const currentStatus = String(billingStatus?.status || 'inactive').toLowerCase();
    const needsBillingAttention = ['past_due', 'unpaid', 'incomplete', 'paused', 'billing_issue']
      .includes(currentStatus);
    const isCurrent = currentTier === plan.id && ['active', 'trialing', 'canceling', 'billing_issue'].includes(currentStatus);
    button.textContent = needsBillingAttention
      ? 'Resolve billing to change plans'
      : isCurrent ? 'Current plan' : `Choose ${plan.name}`;
    if (isCurrent || needsBillingAttention) {
      button.disabled = true;
    } else if (native() && !product?.package && !product?.productId) {
      button.disabled = true;
      button.textContent = 'Not configured';
    }
    button.addEventListener('click', () => {
      if (!isCurrent && !needsBillingAttention) buyPlan(plan.id, button);
    });
    article.append(top, detail, benefits, meterNote, button);
    return article;
  }

  async function hydrate(modal) {
    if (!modal || state.loading) return;
    state.loading = true;
    modal.classList.add('is-loading');
    try {
      const [creditData, usageData, subscriptions, nativeCredits, billingStatus] = await Promise.all([
        jsonFetch('/api/billing/credits/status'),
        jsonFetch('/api/usage/check'),
        Promise.resolve(window.BillingManager?.getProducts?.() || {}).catch(() => ({})),
        Promise.resolve(window.BillingManager?.getCreditProducts?.() || {}).catch(() => ({})),
        jsonFetch('/api/billing/status').catch(() => ({tier:'free', plan:null, status:'inactive', provider:null, manageable:false})),
      ]);

      applyBalance(creditData.credits?.balance);
      const balance = $('#billing51Balance', modal);
      if (balance) balance.textContent = String(state.credits);
      const allowance = $('#billing51Allowance', modal);
      if (allowance) allowance.innerHTML = progressMarkup(usageData.daily);

      const packsHost = $('#billing51Packs', modal);
      packsHost?.replaceChildren();
      (creditData.catalog || []).forEach(pack => {
        packsHost?.appendChild(packCard(pack, nativeCredits?.[pack.code]));
      });

      const plans = [
        {
          id: 'professional',
          name: 'Professional',
          fallback: (window.CRUMP_CONFIG || {}).webProfessionalPriceLabel || '$20/month',
          detail: 'For independent work you return to every day.',
          benefits: [
            '500 included messages daily',
            '25 private Projects',
            '20 research · 1 image · 20 visual analyses daily',
            'Advanced Intelligence: Think Longer + Always Review',
            'Premium creation access',
          ],
          meterNote: 'Premium video and other high-compute generations use Crump Credits.',
        },
        {
          id: 'enterprise',
          name: 'Enterprise',
          fallback: (window.CRUMP_CONFIG || {}).webEnterprisePriceLabel || '$50/month',
          detail: 'For sustained work that needs the largest current individual limits.',
          benefits: [
            '5,000 included messages daily',
            '200 private Projects',
            '50 research · 2 images · 100 visual analyses daily',
            'Advanced Intelligence: Think Longer + Always Review',
            '10-second Cinematic video access',
          ],
          meterNote: 'Premium video and other high-compute generations use Crump Credits.',
        },
      ];
      const plansHost = $('#billing51Plans', modal);
      plansHost?.replaceChildren();
      plans.forEach(plan => plansHost?.appendChild(
        planCard(plan, subscriptions?.[plan.id], billingStatus)
      ));

      const manageButton = $('#billing51Manage', modal);
      if (manageButton) {
        const canManage = Boolean(billingStatus?.manageable);
        manageButton.hidden = !canManage;
        manageButton.disabled = !canManage;
        manageButton.textContent = 'Manage subscription';
      }

      renderHistory(creditData.history || []);
    } catch (error) {
      window.showToast?.(error.message || 'Billing information could not be loaded.', 'error');
    } finally {
      state.loading = false;
      modal.classList.remove('is-loading');
    }
  }

  function showBillingCenter(options = {}) {
    close({restoreFocus: false});
    state.trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const recovery = billingRecoveryContext(options);
    const modal = document.createElement('div');
    modal.className = 'billing51-modal';
    modal.innerHTML = `
      <div class="billing51-backdrop" data-billing-close></div>
      <section class="billing51-sheet" role="dialog" aria-modal="true" aria-labelledby="billing51Title" tabindex="-1">
        <header class="billing51-header">
          <div class="billing51-brand">
            <span class="billing51-mark">C</span>
            <div><span>ASK CRUMP</span><h2 id="billing51Title">Plan & credits</h2></div>
          </div>
          <button type="button" class="billing51-close" data-billing-close aria-label="Close">×</button>
        </header>

        ${billingRecoveryMarkup(recovery)}

        <div class="billing51-balance-card">
          <div>
            <span>YOUR BALANCE</span>
            <strong><b id="billing51Balance">—</b> <small>credits</small></strong>
            <p>Credits take over only after your included allowance runs out.</p>
          </div>
          <div id="billing51Allowance">${progressMarkup({limit:0,used:0,remaining:0})}</div>
        </div>

        <section class="billing51-section">
          <div class="billing51-section-head">
            <div><span>KEEP GOING</span><h3>Add Crump Credits</h3></div>
            <p>1 request = 1 credit after included usage. Purchased credits never expire.</p>
          </div>
          <div class="billing51-packs" id="billing51Packs">
            <div class="billing51-skeleton"></div><div class="billing51-skeleton"></div><div class="billing51-skeleton"></div>
          </div>
        </section>

        <section class="billing51-section">
          <div class="billing51-section-head">
            <div><span>MONTHLY ACCESS</span><h3>Subscriptions</h3></div>
            <p>Increase the usage included with your account each day.</p>
          </div>
          <div class="billing51-plans" id="billing51Plans"></div>
        </section>

        <section class="billing51-section billing51-history-section">
          <div class="billing51-section-head">
            <div><span>LEDGER</span><h3>Recent credit activity</h3></div>
            <p>Every addition, request, and refund is recorded server-side.</p>
          </div>
          <div id="billing51History"></div>
        </section>

        <footer class="billing51-footer">
          <div class="billing51-footer-actions">
            <button type="button" id="billing51Manage" hidden>Manage subscription</button>
            ${native() ? '<button type="button" id="billing51Restore">Restore subscriptions</button>' : '<span>Secure web payments are processed by Stripe.</span>'}
          </div>
          <p>Credits have no cash value and do not expire. Store purchases use the payment system required by your device. Subscription terms and localized prices are shown before confirmation. <a href="/legal.html#terms">Terms</a> · <a href="/legal.html#privacy">Privacy</a></p>
        </footer>
      </section>`;

    modal.querySelectorAll('[data-billing-close]').forEach(node => node.addEventListener('click', () => close()));
    modal.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      containBillingFocus(event, modal);
    });
    modal.querySelector('#billing51Restore')?.addEventListener('click', event => restore(event.currentTarget));
    modal.querySelector('#billing51Manage')?.addEventListener('click', event => manageSubscription(event.currentTarget));
    document.body.appendChild(modal);
    state.modal = modal;
    if (recovery?.plan) modal.dataset.crumpPlanIntent = recovery.plan;
    document.body.classList.add('billing51-open');
    $('.billing51-close', modal)?.focus({preventScroll: true});
    isolateBillingBackground(modal);
    void recordPlanCenterView(options);
    requestAnimationFrame(() => modal.classList.add('is-visible'));
    hydrate(modal);
    return modal;
  }

  function updateSidebarBalance(balance) {
    const button = $('#upgradeBtnSidebar');
    if (!button) return;
    const label = button.querySelector('span');
    if (label) label.textContent = 'Plan & credits';
    let badge = button.querySelector('.billing51-sidebar-balance');
    if (!badge) {
      badge = document.createElement('b');
      badge.className = 'billing51-sidebar-balance';
      button.appendChild(badge);
    }
    badge.textContent = `${Math.max(0, Number(balance || 0))} C`;
  }

  function ownSidebarButton() {
    const old = $('#upgradeBtnSidebar');
    if (!old || old.dataset.billing51 === 'true') return;
    const button = old.cloneNode(true);
    button.dataset.billing51 = 'true';
    old.replaceWith(button);
    button.addEventListener('click', () => showBillingCenter({source: 'settings'}));
    updateSidebarBalance(state.credits);
  }

  async function finalizeReturn() {
    const url = new URL(window.location.href);
    const billing = url.searchParams.get('billing');
    const sessionId = url.searchParams.get('session_id');
    if (billing === 'success' && sessionId) {
      try {
        let result;
        for (let attempt = 0; attempt < 2; attempt += 1) {
          try {
            result = await jsonFetch('/api/stripe/finalize-checkout', {
              method: 'POST',
              body: JSON.stringify({sessionId}),
            });
            break;
          } catch (error) {
            const retryable = ['BILLING_PROVIDER_UNAVAILABLE', 'SUBSCRIPTION_PENDING'].includes(error.code);
            if (!retryable || attempt > 0) throw error;
            await new Promise(resolve => setTimeout(resolve, 2500));
          }
        }
        if (result?.user) {
          window.currentUser = result.user;
          window.profileManager?.applyServerSubscription?.(result.user);
        }
        window.dispatchEvent(new CustomEvent('crump:subscription-updated', {detail: result || {}}));
        const plan = result?.tier === 'enterprise' ? 'Enterprise' : 'Professional';
        window.showToast?.(`${plan} is active`, 'success');
      } catch (error) {
        window.showToast?.(
          error.message || 'Payment completed; subscription activation is still processing.',
          'warning'
        );
        setTimeout(() => window.BillingManager?.refreshStatus?.(), 8000);
      }
      url.searchParams.delete('billing');
      url.searchParams.delete('session_id');
      history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    } else if (billing === 'cancelled') {
      window.showToast?.('Subscription checkout cancelled', 'info');
      url.searchParams.delete('billing');
      history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    } else if (billing === 'credits-success' && sessionId) {
      try {
        const result = await jsonFetch('/api/billing/credits/finalize', {
          method: 'POST',
          body: JSON.stringify({sessionId}),
        });
        state.credits = Number(result.balance || 0);
        window.showToast?.(`${result.credits || ''} credits added to Crump`, 'success');
        window.dispatchEvent(new CustomEvent('crump:credits-updated', {detail:{balance:state.credits}}));
      } catch (error) {
        window.showToast?.(error.message || 'Payment completed; credit verification is still processing.', 'warning');
      }
      url.searchParams.delete('billing');
      url.searchParams.delete('session_id');
      history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    } else if (billing === 'credits-cancelled') {
      window.showToast?.('Credit purchase cancelled', 'info');
      url.searchParams.delete('billing');
      history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    }
  }

  function applyBalance(balance) {
    const normalized = Number(balance);
    if (!Number.isFinite(normalized)) return false;
    state.credits = Math.max(0, normalized);
    state.lastBalanceFetchAt = Date.now();
    updateSidebarBalance(state.credits);
    return true;
  }

  function refreshBalance({force = false} = {}) {
    if (!window.currentUser) return Promise.resolve(false);
    if (!force && state.lastBalanceFetchAt && Date.now() - state.lastBalanceFetchAt < BALANCE_STALE_MS) {
      return Promise.resolve(false);
    }
    if (state.balanceRequest) return state.balanceRequest;
    state.balanceRequest = jsonFetch('/api/billing/credits/status')
      .then(data => applyBalance(data.credits?.balance))
      .catch(() => false)
      .finally(() => { state.balanceRequest = null; });
    return state.balanceRequest;
  }

  function boot() {
    window.showBillingCenter = showBillingCenter;
    // Every existing "upgrade required" call now opens the combined premium
    // billing center rather than a subscription-only dead end.
    window.showUpgradePrompt = options => showBillingCenter({
      ...(options && typeof options === 'object' ? options : {}),
      source: 'upgrade_prompt',
    });
    ownSidebarButton();
    finalizeReturn();
    if (window.currentUser) refreshBalance();
    window.addEventListener('crump:authenticated-ready', () => refreshBalance());
    window.addEventListener('crump:credits-updated', event => {
      const balance = Number(event.detail?.balance ?? event.detail?.credits?.balance);
      if (!applyBalance(balance)) refreshBalance({force: true});
    });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) refreshBalance();
    });
    window.addEventListener('focus', () => refreshBalance());
    setTimeout(ownSidebarButton, 1200);
  }

  if (document.readyState === 'complete') setTimeout(boot, 80);
  else window.addEventListener('load', () => setTimeout(boot, 80), {once: true});
})();
