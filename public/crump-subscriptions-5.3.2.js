(() => {
  'use strict';

  if (window.__crumpSubscriptions532Loaded) return;
  window.__crumpSubscriptions532Loaded = true;

  const config = window.CRUMP_CONFIG || {};
  const BILLING_REQUEST_TIMEOUT_MS = 15_000;
  const paidStatuses = new Set([
    'active',
    'trialing',
    'canceling',
    'billing_issue',
    'past_due',
    'paused',
  ]);

  function native() {
    return Boolean(window.BillingManager?.isNative?.());
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
        error.provider = data.provider;
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

  function setBusy(button, busy, label = 'Working…') {
    if (!button) return;
    if (busy) {
      if (!button.dataset.previousLabel) button.dataset.previousLabel = button.textContent;
      button.disabled = true;
      button.textContent = label;
      return;
    }
    button.disabled = false;
    button.textContent = button.dataset.previousLabel || button.textContent;
    delete button.dataset.previousLabel;
  }

  async function openPortal(button, provider = null) {
    if (provider === 'revenuecat' && !native()) {
      window.showToast?.(
        'This subscription is managed through the App Store or Google Play.',
        'info'
      );
      return;
    }

    setBusy(button, true, 'Opening…');
    try {
      if (native()) {
        await window.BillingManager?.manageSubscription?.();
        return;
      }
      const result = await jsonFetch('/api/stripe/customer-portal', {method: 'POST'});
      if (!result.url) throw new Error('Subscription management did not return a destination.');
      window.location.assign(result.url);
    } catch (error) {
      window.showToast?.(
        error.message || 'Subscription management could not be opened.',
        'error'
      );
      setBusy(button, false);
    }
  }

  async function openCheckout(tier, button) {
    setBusy(button, true, native() ? 'Opening store…' : 'Opening checkout…');
    try {
      if (native()) {
        if (!window.BillingManager?.purchase) {
          throw new Error('Mobile subscriptions are not available in this build yet.');
        }
        await window.BillingManager.purchase(tier);
        window.showToast?.('Subscription activated', 'success');
        await activatePlans(document.querySelector('.crump52-billing-modal'), true);
        return;
      }

      const result = await jsonFetch('/api/stripe/create-checkout-session', {
        method: 'POST',
        body: JSON.stringify({tier}),
      });
      if (!result.url) throw new Error('Secure checkout did not return a destination.');
      window.location.assign(result.url);
    } catch (error) {
      if (error.code === 'SUBSCRIPTION_ALREADY_ACTIVE') {
        setBusy(button, false);
        await openPortal(button, error.provider || null);
        return;
      }
      window.showToast?.(
        error.message || 'Subscription checkout could not be opened.',
        'error'
      );
      setBusy(button, false);
    }
  }

  function planDefinition(id) {
    if (id === 'enterprise') {
      return {
        id,
        name: 'Enterprise',
        price: config.webEnterprisePriceLabel || '$50/month',
        detail: 'For sustained, high-capacity individual or organization workflows.',
        benefits: [
          '5,000 included messages daily',
          '200 private Projects',
          '50 research · 2 images · 100 visual analyses daily',
          '10-second Cinematic video access',
        ],
        meterNote: 'Premium video and other high-compute generations use Crump Credits.',
      };
    }
    return {
      id: 'professional',
      name: 'Professional',
      price: config.webProfessionalPriceLabel || '$20/month',
      detail: 'For independent work you return to every day.',
      benefits: [
        '500 included messages daily',
        '25 private Projects',
        '20 research · 1 image · 20 visual analyses daily',
        'Think Longer and premium creation access',
      ],
      meterNote: 'Premium video and other high-compute generations use Crump Credits.',
    };
  }

  function planCard(plan, billingStatus) {
    const article = document.createElement('article');
    article.className = `billing51-plan ${plan.id === 'professional' ? 'is-featured' : ''}`;
    article.dataset.crumpPlan = plan.id;

    const tier = String(billingStatus?.tier || 'free').toLowerCase();
    const status = String(billingStatus?.status || 'inactive').toLowerCase();
    const provider = String(billingStatus?.provider || '').toLowerCase() || null;
    const hasPaidPlan = tier !== 'free' && paidStatuses.has(status);
    const current = hasPaidPlan && tier === plan.id;

    const top = document.createElement('div');
    top.className = 'billing51-plan-top';

    const name = document.createElement('strong');
    name.textContent = plan.name;

    const price = document.createElement('span');
    price.textContent = current ? `${plan.price} · Current` : plan.price;
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

    if (hasPaidPlan) {
      if (provider === 'revenuecat' && !native()) {
        button.textContent = current ? 'Managed in mobile store' : 'Manage in mobile store';
        button.addEventListener('click', () => openPortal(button, provider));
      } else {
        button.textContent = current ? 'Manage plan' : `Switch to ${plan.name}`;
        button.addEventListener('click', () => openPortal(button, provider));
      }
    } else {
      button.textContent = `Choose ${plan.name}`;
      button.addEventListener('click', () => openCheckout(plan.id, button));
    }

    article.append(top, detail, benefits, meterNote, button);
    return article;
  }

  function applyPlanIntent(modal, plan) {
    if (!modal?.isConnected || !['professional', 'enterprise'].includes(plan)) return;
    const host = modal.querySelector('.billing51-plans');
    const card = host?.querySelector(`[data-crump-plan="${plan}"]`);
    const section = host?.closest('.billing51-section');
    if (!host || !card || !section) return;

    host.querySelectorAll('[data-crump-plan]').forEach(node => node.classList.remove('is-intent'));
    card.classList.add('is-intent');

    let notice = section.querySelector('.crump52-plan-intent');
    if (!notice) {
      notice = document.createElement('p');
      notice.className = 'crump52-plan-intent';
      notice.setAttribute('role', 'status');
      section.insertBefore(notice, host);
    }
    const label = plan === 'enterprise' ? 'Enterprise' : 'Professional';
    notice.textContent = `You chose ${label}. Review the details, then continue when you are ready.`;
  }

  async function activatePlans(modal, force = false) {
    if (!modal || !modal.isConnected) return;
    if (!force && ['loading', 'ready'].includes(modal.dataset.crumpSubscriptions532)) return;

    const host = modal.querySelector('.billing51-plans');
    if (!host) return;

    modal.dataset.crumpSubscriptions532 = 'loading';

    const section = host.closest('.billing51-section');
    const explainer = section?.querySelector('.billing51-section-head p');
    if (explainer) {
      explainer.textContent =
        'Choose monthly access for more included usage. You can manage or cancel a web subscription at any time.';
    }

    let billingStatus = {tier: 'free', status: 'inactive', provider: null};
    try {
      billingStatus = await jsonFetch('/api/billing/status');
    } catch (error) {
      if (!modal.isConnected) return;
      host.replaceChildren();
      const message = document.createElement('p');
      message.className = 'billing51-empty crump52-billing-error';
      message.textContent = 'Subscription status could not be loaded. Close this panel and try again.';
      host.appendChild(message);
      delete modal.dataset.crumpSubscriptions532;
      return;
    }

    if (!modal.isConnected) return;
    host.replaceChildren(
      planCard(planDefinition('professional'), billingStatus),
      planCard(planDefinition('enterprise'), billingStatus)
    );
    modal.dataset.crumpSubscriptions532 = 'ready';
    applyPlanIntent(modal, modal.dataset.crumpPlanIntent);
  }

  function scan() {
    document.querySelectorAll('.crump52-billing-modal').forEach(modal => {
      void activatePlans(modal);
    });
  }

  const observer = new MutationObserver(scan);
  observer.observe(document.documentElement, {childList: true, subtree: true});
  window.addEventListener('crump:plan-intent', event => {
    const plan = String(event.detail?.plan || '').toLowerCase();
    if (!['professional', 'enterprise'].includes(plan)) return;
    const modal = window.showBillingCenter?.({plan});
    if (!modal) return;
    modal.dataset.crumpPlanIntent = plan;
    void activatePlans(modal, true).then(() => {
      if (modal.dataset.crumpSubscriptions532 !== 'ready') return;
      applyPlanIntent(modal, plan);
      window.va?.('event', {
        name: 'PlanIntentReached',
        data: {
          plan,
          source: String(event.detail?.source || 'direct').slice(0, 32),
          location: String(event.detail?.location || 'unknown').slice(0, 32),
        },
      });
      const source = String(event.detail?.source || 'direct').slice(0, 32);
      const capturedAt = Number(event.detail?.capturedAt || Date.now());
      void window.CrumpAnalytics?.track('PlanIntentReached', {
        eventKey: `plan-intent:${plan}:${capturedAt}`,
        plan,
        source,
      });
      window.dispatchEvent(new CustomEvent('crump:plan-intent-consumed', {detail: {plan}}));
    });
  });
  scan();
})();
