(() => {
  'use strict';

  const plans = [
    { id: 'professional', name: 'Professional', fallbackPrice: '$20/month', detail: '500 included messages daily, 25 private Projects, and broader research and creation access.' },
    { id: 'enterprise', name: 'Enterprise', fallbackPrice: '$50/month', detail: '5,000 included messages daily, 200 private Projects, and the highest current limits for demanding individual workflows.' },
  ];

  function closeUpgradePrompt() {
    document.querySelector('.upgrade-modal')?.remove();
  }

  async function upgradePlan(tier, button = null) {
    if (button) { button.disabled = true; button.textContent = 'Opening…'; }
    try {
      if (window.BillingManager?.isNative?.()) {
        await window.BillingManager.purchase(tier);
        window.showToast?.('Subscription activated', 'success');
        closeUpgradePrompt();
        return;
      }
      const response = await fetch('/api/stripe/create-checkout-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tier }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.url) throw new Error(data.error || 'Unable to open checkout.');
      window.location.assign(data.url);
    } catch (error) {
      window.showToast?.(error.message || 'Billing could not be opened.', 'error');
      if (button) { button.disabled = false; button.textContent = 'Choose plan'; }
    }
  }

  async function restorePurchases() {
    try {
      await window.BillingManager.restore();
      window.showToast?.('Purchases restored', 'success');
      closeUpgradePrompt();
    } catch (error) {
      window.showToast?.(error.message || 'No purchases were restored.', 'error');
    }
  }

  async function hydratePrices(modal, native) {
    try {
      const products = await window.BillingManager?.getProducts?.();
      plans.forEach(plan => {
        const price = products?.[plan.id]?.price || (native ? 'View store price' : plan.fallbackPrice);
        const node = modal.querySelector(`[data-plan-price="${plan.id}"]`);
        if (node) node.textContent = price;
      });
    } catch (error) {
      console.warn('[Billing] Could not load localized prices:', error);
    }
  }

  function showUpgradePrompt() {
    closeUpgradePrompt();
    const native = window.BillingManager?.isNative?.();
    const modal = document.createElement('div');
    modal.className = 'upgrade-modal active';
    modal.innerHTML = `
      <div class="upgrade-overlay" data-close-upgrade></div>
      <section class="upgrade-content" role="dialog" aria-modal="true" aria-labelledby="upgrade-title">
        <button class="upgrade-close" data-close-upgrade type="button" aria-label="Close">×</button>
        <div class="upgrade-header"><h2 id="upgrade-title">Upgrade Ask Crump</h2><p>Choose the level that fits how you work.</p></div>
        <div class="tier-comparison">
          ${plans.map(plan => `
            <article class="tier-card-premium ${plan.id === 'professional' ? 'tier-featured' : ''}">
              <div class="tier-card-header"><h3 class="tier-name">${plan.name}</h3></div>
              <div class="tier-price-section"><div class="tier-price-free"><span class="price-main" data-plan-price="${plan.id}">${native ? 'Loading store price…' : plan.fallbackPrice}</span></div></div>
              <p>${plan.detail}</p>
              <div class="tier-card-footer"><button class="tier-btn tier-btn-upgrade" type="button" data-tier="${plan.id}">Choose plan</button></div>
            </article>`).join('')}
        </div>
        ${native ? '<button class="tier-btn" id="restorePurchasesBtn" type="button">Restore purchases</button>' : '<p class="upgrade-footer">Secure web checkout is handled by Stripe.</p>'}
        <p class="upgrade-footer">Premium video and other high-compute generations use Crump Credits.</p>
        <p class="upgrade-footer">Subscriptions renew automatically each month until canceled through the billing provider. The final localized price and terms are shown before purchase. <a href="/legal.html#terms">Terms</a> · <a href="/legal.html#privacy">Privacy</a></p>
      </section>`;
    modal.querySelectorAll('[data-close-upgrade]').forEach(node => node.addEventListener('click', closeUpgradePrompt));
    modal.querySelectorAll('[data-tier]').forEach(node => node.addEventListener('click', () => upgradePlan(node.dataset.tier, node)));
    modal.querySelector('#restorePurchasesBtn')?.addEventListener('click', restorePurchases);
    document.body.appendChild(modal);
    hydratePrices(modal, native);
  }

  window.showUpgradePrompt = showUpgradePrompt;
  window.upgradePlan = upgradePlan;
  window.restorePurchases = restorePurchases;
})();
