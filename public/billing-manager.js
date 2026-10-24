(() => {
  'use strict';

  let configured = false;
  let configuredUserId = null;
  let configurationPromise = null;
  let identityPromise = null;
  let nativeOperationQueue = Promise.resolve();
  const CHECKOUT_RECOVERY_KEY = 'askcrump.pending-checkout-recovery';
  const CHECKOUT_RECOVERY_TTL_MS = 15 * 60 * 1000;
  const CREDIT_PACKS = new Set(['credits_50', 'credits_150', 'credits_400']);
  const PAID_PLANS = new Set(['professional', 'enterprise']);
  const STRIPE_DESTINATION_HOSTS = Object.freeze({
    checkout: 'checkout.stripe.com',
    portal: 'billing.stripe.com',
  });

  const native = () => Boolean(window.CrumpAPI?.isNative);
  const platform = () => window.CrumpNative?.Capacitor?.getPlatform?.() || window.Capacitor?.getPlatform?.() || 'web';
  const purchases = () => window.CrumpNative?.Purchases;
  const config = () => window.CRUMP_CONFIG || {};

  function captureBillingBoundary() {
    const boundary = window.CrumpAuthBoundary;
    return Object.freeze({
      ownerId: String(boundary?.authenticatedUserId?.() || window.currentUser?.id || '').trim(),
      revision: Number(boundary?.revision?.() || 0),
    });
  }

  function billingBoundaryIsCurrent(snapshot) {
    const current = captureBillingBoundary();
    return !!snapshot?.ownerId
      && current.ownerId === snapshot.ownerId
      && current.revision === snapshot.revision;
  }

  function billingHeaders(authBoundary, headers = {}) {
    return {
      ...(authBoundary?.ownerId ? {'X-Ask-Crump-Expected-Owner': authBoundary.ownerId} : {}),
      ...headers,
    };
  }

  function assertBillingBoundary(authBoundary) {
    if (billingBoundaryIsCurrent(authBoundary)) return;
    const error = new Error('Your account changed. Reopen billing and try again.');
    error.code = 'AUTH_OWNER_CHANGED';
    throw error;
  }

  function stripeDestination(value, kind = 'checkout') {
    const expectedHost = STRIPE_DESTINATION_HOSTS[kind];
    if (!expectedHost) return null;
    try {
      const url = new URL(String(value || ''));
      if (
        url.protocol !== 'https:'
        || url.hostname !== expectedHost
        || url.username
        || url.password
        || url.port
      ) return null;
      return url.href;
    } catch (_) {
      return null;
    }
  }

  function requireStripeDestination(value, kind = 'checkout') {
    const url = stripeDestination(value, kind);
    if (!url) {
      throw new Error(
        kind === 'portal'
          ? 'Subscription management did not return a secure destination.'
          : 'Stripe did not return a secure checkout destination.',
      );
    }
    return url;
  }

  function normalizeCheckoutRecovery(value) {
    const kind = String(value?.kind || '').toLowerCase();
    const selection = String(value?.selection || '').toLowerCase();
    const capturedAt = Number(value?.capturedAt || 0);
    const age = Date.now() - capturedAt;
    const validSelection = kind === 'credit'
      ? CREDIT_PACKS.has(selection)
      : kind === 'plan' && PAID_PLANS.has(selection);
    if (!validSelection || !capturedAt || age < 0 || age > CHECKOUT_RECOVERY_TTL_MS) {
      return null;
    }
    return {kind, selection, capturedAt};
  }

  function pendingCheckoutRecovery() {
    try {
      const recovery = normalizeCheckoutRecovery(
        JSON.parse(sessionStorage.getItem(CHECKOUT_RECOVERY_KEY) || 'null'),
      );
      if (!recovery) sessionStorage.removeItem(CHECKOUT_RECOVERY_KEY);
      return recovery;
    } catch (_) {
      try { sessionStorage.removeItem(CHECKOUT_RECOVERY_KEY); } catch (_) {}
      return null;
    }
  }

  function requestCheckoutReauthentication(kind, selection) {
    const recovery = normalizeCheckoutRecovery({kind, selection, capturedAt: Date.now()});
    if (!recovery) return false;
    try {
      sessionStorage.setItem(CHECKOUT_RECOVERY_KEY, JSON.stringify(recovery));
    } catch (_) {
      return false;
    }
    window.dispatchEvent(new CustomEvent('crump:authentication-required', {
      detail: {reason: 'checkout'},
    }));
    return true;
  }

  function consumeCheckoutRecovery(expected) {
    const recovery = pendingCheckoutRecovery();
    if (!recovery) return null;
    if (expected && (recovery.kind !== expected.kind || recovery.selection !== expected.selection)) {
      return null;
    }
    try { sessionStorage.removeItem(CHECKOUT_RECOVERY_KEY); } catch (_) {}
    return recovery;
  }

  function activeAppUserId() {
    const userId = String(window.currentUser?.id || '').trim();
    return userId || null;
  }

  async function readConfiguredAppUser(plugin) {
    if (typeof plugin.getAppUserID !== 'function') {
      throw new Error('Store billing identity is unavailable.');
    }
    const result = await plugin.getAppUserID();
    const appUserId = String(result?.appUserID || '').trim();
    let anonymous = appUserId.startsWith('$RCAnonymousID:');
    if (typeof plugin.isAnonymous === 'function') {
      const status = await plugin.isAnonymous();
      anonymous = Boolean(status?.isAnonymous);
    }
    return anonymous ? null : (appUserId || null);
  }

  async function adoptNativeConfiguration(plugin) {
    if (configured || typeof plugin.isConfigured !== 'function') return configured;
    const status = await plugin.isConfigured();
    if (!status?.isConfigured) return false;
    configuredUserId = await readConfiguredAppUser(plugin);
    configured = true;
    return true;
  }

  async function performAppUserAlignment(plugin, nextUserId) {
    if (nextUserId === configuredUserId) return;

    try {
      if (nextUserId) {
        if (typeof plugin.logIn !== 'function') throw new Error('RevenueCat login is unavailable.');
        await plugin.logIn({appUserID: nextUserId});
        configuredUserId = nextUserId;
        return;
      }
      if (configuredUserId) {
        if (typeof plugin.logOut !== 'function') throw new Error('RevenueCat logout is unavailable.');
        await plugin.logOut();
      }
      configuredUserId = null;
    } catch (_) {
      throw new Error('Store billing could not confirm the signed-in account. Try again.');
    }
  }

  async function alignAppUser(plugin, requestedUserId = undefined) {
    const followsCurrentSession = requestedUserId === undefined;
    const desiredUserId = () => followsCurrentSession ? activeAppUserId() : requestedUserId;
    while (desiredUserId() !== configuredUserId) {
      if (!identityPromise) {
        identityPromise = performAppUserAlignment(plugin, desiredUserId()).finally(() => {
          identityPromise = null;
        });
      }
      await identityPromise;
    }
  }

  function withNativeOperation(operation) {
    const queued = nativeOperationQueue.catch(() => {}).then(operation);
    nativeOperationQueue = queued.catch(() => {});
    return queued;
  }

  async function configureUnlocked(requestedUserId = undefined) {
    if (!native()) return false;
    await window.CrumpAPI?.ready;
    const plugin = purchases();
    const values = config();
    const key = platform() === 'ios' ? values.revenueCatAppleApiKey : values.revenueCatGoogleApiKey;
    if (!plugin || !key) return false;

    if (!configured) {
      if (!configurationPromise) {
        const appUserID = activeAppUserId();
        configurationPromise = (async () => {
          if (await adoptNativeConfiguration(plugin)) return;
          await plugin.configure({apiKey: key, ...(appUserID ? {appUserID} : {})});
          configured = true;
          configuredUserId = appUserID;
        })().finally(() => {
          configurationPromise = null;
        });
      }
      await configurationPromise;
    }

    await alignAppUser(plugin, requestedUserId);
    return true;
  }

  function configure() {
    return withNativeOperation(() => configureUnlocked());
  }

  function disconnect() {
    return withNativeOperation(async () => {
    if (!native()) return false;
    await window.CrumpAPI?.ready;
    const plugin = purchases();
    if (!plugin) return false;

    if (!configured) {
      if (!configurationPromise) {
        configurationPromise = adoptNativeConfiguration(plugin).finally(() => {
          configurationPromise = null;
        });
      }
      await configurationPromise;
    }
    if (!configured) return true;
    await alignAppUser(plugin, null);
    return true;
    });
  }

  function packageProduct(item = {}) {
    return item.product || item.storeProduct || item.store_product || {};
  }

  function productIdentifier(item = {}) {
    const product = packageProduct(item);
    return product.identifier || product.productIdentifier || product.product_identifier || '';
  }

  function priceLabel(item = {}) {
    const product = packageProduct(item);
    return product.priceString || product.price_string || product.localizedPriceString || product.localized_price_string || '';
  }

  function tierForPackage(item = {}) {
    const values = config();
    const productId = productIdentifier(item);
    if (productId === values.revenueCatEnterpriseProductId) return 'enterprise';
    if (productId === values.revenueCatProfessionalProductId) return 'professional';
    return null;
  }

  function creditPackConfig() {
    const values = config();
    return [
      {
        code: 'credits_50',
        credits: 50,
        productId: values.revenueCatCredits50ProductId || 'askcrump_credits_50',
        webPrice: values.webCredits50PriceLabel || '$4.99',
      },
      {
        code: 'credits_150',
        credits: 150,
        productId: values.revenueCatCredits150ProductId || 'askcrump_credits_150',
        webPrice: values.webCredits150PriceLabel || '$9.99',
      },
      {
        code: 'credits_400',
        credits: 400,
        productId: values.revenueCatCredits400ProductId || 'askcrump_credits_400',
        webPrice: values.webCredits400PriceLabel || '$19.99',
      },
    ];
  }

  function creditPackForPackage(item = {}) {
    const productId = productIdentifier(item);
    return creditPackConfig().find(pack => productId === pack.productId) || null;
  }

  async function offeringPackagesUnlocked(requestedUserId = undefined) {
    if (!(await configureUnlocked(requestedUserId))) return [];
    const offeringsResult = await purchases().getOfferings();
    const offering = offeringsResult?.offerings?.current || offeringsResult?.current;
    return offering?.availablePackages || offering?.available_packages || [];
  }

  function offeringPackages() {
    return withNativeOperation(() => offeringPackagesUnlocked());
  }

  async function getProducts() {
    if (!native()) {
      const values = config();
      return {
        professional: { tier: 'professional', price: values.webProfessionalPriceLabel || '$20/month' },
        enterprise: { tier: 'enterprise', price: values.webEnterprisePriceLabel || '$50/month' },
      };
    }
    const products = {};
    for (const item of await offeringPackages()) {
      const tier = tierForPackage(item);
      if (!tier || products[tier]) continue;
      products[tier] = {
        tier,
        price: priceLabel(item) || 'View store price',
        productId: productIdentifier(item),
        package: item,
      };
    }
    return products;
  }

  async function getCreditProducts() {
    const configuredPacks = creditPackConfig();
    if (!native()) {
      return Object.fromEntries(configuredPacks.map(pack => [
        pack.code,
        {
          code: pack.code,
          credits: pack.credits,
          productId: pack.productId,
          price: pack.webPrice,
        },
      ]));
    }
    const products = {};
    for (const item of await offeringPackages()) {
      const pack = creditPackForPackage(item);
      if (!pack || products[pack.code]) continue;
      products[pack.code] = {
        code: pack.code,
        credits: pack.credits,
        price: priceLabel(item) || 'View store price',
        productId: productIdentifier(item),
        package: item,
      };
    }
    return products;
  }

  async function purchase(tier = 'professional', suppliedBoundary = null) {
    if (!native()) throw new Error('Native billing is only available in the installed mobile app.');
    const authBoundary = suppliedBoundary || captureBillingBoundary();
    assertBillingBoundary(authBoundary);
    return withNativeOperation(async () => {
      assertBillingBoundary(authBoundary);
      if (!(await configureUnlocked(authBoundary.ownerId))) {
        throw new Error('App Store billing is not configured yet. Add the RevenueCat public SDK key before submission.');
      }
      assertBillingBoundary(authBoundary);
      const packages = await offeringPackagesUnlocked(authBoundary.ownerId);
      assertBillingBoundary(authBoundary);
      const selected = packages.find(item => tierForPackage(item) === tier);
      if (!selected) throw new Error('That subscription package is not available from the store.');
      const result = await purchases().purchasePackage({ aPackage: selected });
      assertBillingBoundary(authBoundary);
      await synchronizeServerEntitlement(authBoundary);
      assertBillingBoundary(authBoundary);
      await refreshStatus(authBoundary);
      assertBillingBoundary(authBoundary);
      return result;
    });
  }

  async function purchaseCredits(packCode, suppliedBoundary = null) {
    if (!native()) throw new Error('Use secure web checkout to purchase credits on the web.');
    const authBoundary = suppliedBoundary || captureBillingBoundary();
    assertBillingBoundary(authBoundary);
    const eligibilityResponse = await fetch('/api/billing/credits/purchase-eligibility', {
      method: 'POST',
      credentials: 'same-origin',
      headers: billingHeaders(authBoundary, {'Content-Type': 'application/json'}),
      body: JSON.stringify({pack: packCode}),
    });
    const eligibility = await eligibilityResponse.json().catch(() => ({}));
    assertBillingBoundary(authBoundary);
    if (!eligibilityResponse.ok || eligibility.success === false || eligibility.creditPurchasesAllowed !== true) {
      const error = new Error(
        eligibility.error
        || 'Subscribe to Professional or Enterprise before adding Crump Credits.',
      );
      error.code = eligibility.code || 'CREDIT_PURCHASE_REQUIRES_SUBSCRIPTION';
      throw error;
    }
    return withNativeOperation(async () => {
      assertBillingBoundary(authBoundary);
      if (!(await configureUnlocked(authBoundary.ownerId))) {
        throw new Error('App Store billing is not configured yet.');
      }
      assertBillingBoundary(authBoundary);
      const packages = await offeringPackagesUnlocked(authBoundary.ownerId);
      assertBillingBoundary(authBoundary);
      const selected = packages.find(item => creditPackForPackage(item)?.code === packCode);
      if (!selected) throw new Error('That credit pack is not available from the store yet.');
      const result = await purchases().purchasePackage({ aPackage: selected });
      assertBillingBoundary(authBoundary);
      // RevenueCat records the consumable purchase. Ask Crump then queries the
      // server-side customer record and grants only transaction IDs it has never
      // seen before, preventing duplicate credit deposits.
      await purchases().invalidateVirtualCurrenciesCache?.().catch?.(() => {});
      assertBillingBoundary(authBoundary);
      await synchronizeServerCredits(authBoundary);
      assertBillingBoundary(authBoundary);
      return result;
    });
  }

  async function restore(suppliedBoundary = null) {
    const authBoundary = suppliedBoundary || captureBillingBoundary();
    assertBillingBoundary(authBoundary);
    return withNativeOperation(async () => {
      assertBillingBoundary(authBoundary);
      if (!(await configureUnlocked(authBoundary.ownerId))) throw new Error('Native billing is not configured.');
      assertBillingBoundary(authBoundary);
      const result = await purchases().restorePurchases();
      assertBillingBoundary(authBoundary);
      await synchronizeServerEntitlement(authBoundary);
      assertBillingBoundary(authBoundary);
      await synchronizeServerCredits(authBoundary).catch(error => {
        assertBillingBoundary(authBoundary);
        return undefined;
      });
      assertBillingBoundary(authBoundary);
      await refreshStatus(authBoundary);
      assertBillingBoundary(authBoundary);
      return result;
    });
  }

  async function synchronizeServerEntitlement(authBoundary = captureBillingBoundary()) {
    const response = await fetch('/api/billing/revenuecat/sync', {
      method: 'POST',
      headers: billingHeaders(authBoundary),
    });
    const data = await response.json().catch(() => ({}));
    assertBillingBoundary(authBoundary);
    if (!response.ok || !data.success) {
      throw new Error(data.error || 'Your purchase completed, but subscription verification is still processing.');
    }
    if (data.user) {
      window.currentUser = data.user;
      window.profileManager?.applyServerSubscription?.(data.user);
    }
    return data;
  }

  async function synchronizeServerCredits(authBoundary = captureBillingBoundary()) {
    const response = await fetch('/api/billing/credits/revenuecat/sync', {
      method: 'POST',
      headers: billingHeaders(authBoundary),
    });
    const data = await response.json().catch(() => ({}));
    assertBillingBoundary(authBoundary);
    if (!response.ok || !data.success) {
      const error = new Error(data.error || 'Your purchase completed, but credit verification is still processing.');
      error.code = data.code || 'CREDIT_VERIFICATION_PENDING';
      throw error;
    }
    if (Number(data.rejectedTransactions || 0) > 0) {
      const error = new Error(
        'RevenueCat could not prove that this credit purchase occurred during a paid subscription period. No unverified credits were added.',
      );
      error.code = data.settlementCode || 'REVENUECAT_PAID_INTERVAL_NOT_PROVEN';
      throw error;
    }
    window.dispatchEvent(new CustomEvent('crump:credits-updated', { detail: data.credits || {} }));
    return data;
  }

  async function manageSubscription(suppliedBoundary = null) {
    const authBoundary = suppliedBoundary || captureBillingBoundary();
    assertBillingBoundary(authBoundary);
    if (native()) {
      return withNativeOperation(async () => {
        assertBillingBoundary(authBoundary);
        if (!(await configureUnlocked(authBoundary.ownerId))) throw new Error('Native billing is not configured.');
        assertBillingBoundary(authBoundary);
        const result = await purchases().getCustomerInfo();
        assertBillingBoundary(authBoundary);
        const info = result?.customerInfo || result?.customer_info || result;
        const url = info?.managementURL || info?.managementUrl || info?.management_url;
        if (!url) throw new Error('No active store subscription was found.');
        window.open(url, '_blank', 'noopener,noreferrer');
        return {url};
      });
    }
    const response = await fetch('/api/stripe/customer-portal', {
      method: 'POST',
      headers: billingHeaders(authBoundary),
    });
    const data = await response.json().catch(() => ({}));
    assertBillingBoundary(authBoundary);
    if (!response.ok || !data.url) throw new Error(data.error || 'Subscription management could not be opened.');
    const url = requireStripeDestination(data.url, 'portal');
    window.location.assign(url);
    return {...data, url};
  }

  function subscriptionCheckoutAttempt(tier) {
    const normalizedTier = ['professional', 'enterprise'].includes(String(tier || '').toLowerCase())
      ? String(tier).toLowerCase()
      : 'professional';
    const storageKey = `crump:subscription-checkout-attempt:${normalizedTier}`;
    try {
      const stored = sessionStorage.getItem(storageKey);
      if (/^[A-Za-z0-9][A-Za-z0-9:._-]{15,99}$/.test(stored || '')) return stored;
    } catch (_) {}
    const randomId = globalThis.crypto?.randomUUID?.()
      || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
    const attemptId = `web:${randomId}`;
    try { sessionStorage.setItem(storageKey, attemptId); } catch (_) {}
    return attemptId;
  }

  function completeSubscriptionCheckoutAttempt(tier, attemptId) {
    const normalizedTier = ['professional', 'enterprise'].includes(String(tier || '').toLowerCase())
      ? String(tier).toLowerCase()
      : 'professional';
    const storageKey = `crump:subscription-checkout-attempt:${normalizedTier}`;
    try {
      if (sessionStorage.getItem(storageKey) === attemptId) sessionStorage.removeItem(storageKey);
    } catch (_) {}
  }

  function creditCheckoutAttempt(packCode) {
    const normalizedPack = ['credits_50', 'credits_150', 'credits_400'].includes(
      String(packCode || '').toLowerCase(),
    ) ? String(packCode).toLowerCase() : 'credits_50';
    const storageKey = `crump:credit-checkout-attempt:${normalizedPack}`;
    try {
      const stored = sessionStorage.getItem(storageKey);
      if (/^[A-Za-z0-9][A-Za-z0-9:._-]{15,99}$/.test(stored || '')) return stored;
    } catch (_) {}
    const randomId = globalThis.crypto?.randomUUID?.()
      || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
    const attemptId = `web:${randomId}`;
    try { sessionStorage.setItem(storageKey, attemptId); } catch (_) {}
    return attemptId;
  }

  function completeCreditCheckoutAttempt(packCode, attemptId) {
    const normalizedPack = ['credits_50', 'credits_150', 'credits_400'].includes(
      String(packCode || '').toLowerCase(),
    ) ? String(packCode).toLowerCase() : 'credits_50';
    const storageKey = `crump:credit-checkout-attempt:${normalizedPack}`;
    try {
      if (sessionStorage.getItem(storageKey) === attemptId) sessionStorage.removeItem(storageKey);
    } catch (_) {}
  }

  async function refreshStatus(authBoundary = captureBillingBoundary()) {
    const response = await fetch('/api/billing/status', {headers: billingHeaders(authBoundary)});
    const data = await response.json().catch(() => ({}));
    assertBillingBoundary(authBoundary);
    if (response.ok && data.success && data.user) {
      window.currentUser = data.user;
      window.profileManager?.applyServerSubscription?.(data.user);
    }
    return data;
  }

  async function refreshCredits(authBoundary = captureBillingBoundary()) {
    const response = await fetch('/api/billing/credits/status', {headers: billingHeaders(authBoundary)});
    const data = await response.json().catch(() => ({}));
    assertBillingBoundary(authBoundary);
    if (response.ok && data.success) {
      window.dispatchEvent(new CustomEvent('crump:credits-updated', { detail: data.credits || {} }));
    }
    return data;
  }

  window.BillingManager = {
    configure,
    getProducts,
    getCreditProducts,
    purchase,
    purchaseCredits,
    restore,
    manageSubscription,
    subscriptionCheckoutAttempt,
    completeSubscriptionCheckoutAttempt,
    creditCheckoutAttempt,
    completeCreditCheckoutAttempt,
    requestCheckoutReauthentication,
    pendingCheckoutRecovery,
    consumeCheckoutRecovery,
    refreshStatus,
    refreshCredits,
    synchronizeServerCredits,
    stripeDestination,
    requireStripeDestination,
    disconnect,
    isNative: native,
  };
})();
