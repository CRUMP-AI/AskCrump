(() => {
  'use strict';

  let configured = false;

  const native = () => Boolean(window.CrumpAPI?.isNative);
  const platform = () => window.CrumpNative?.Capacitor?.getPlatform?.() || window.Capacitor?.getPlatform?.() || 'web';
  const purchases = () => window.CrumpNative?.Purchases;
  const config = () => window.CRUMP_CONFIG || {};

  async function configure() {
    if (!native()) return false;
    await window.CrumpAPI?.ready;
    if (configured) return true;
    const plugin = purchases();
    const values = config();
    const key = platform() === 'ios' ? values.revenueCatAppleApiKey : values.revenueCatGoogleApiKey;
    if (!plugin || !key) return false;
    await plugin.configure({ apiKey: key, appUserID: window.currentUser?.id || null });
    if (window.currentUser?.id && plugin.logIn) {
      await plugin.logIn({ appUserID: window.currentUser.id }).catch(() => {});
    }
    configured = true;
    return true;
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
    const packageId = String(item.identifier || item.packageIdentifier || item.package_identifier || '');
    const label = `${productId} ${packageId}`.toLowerCase();
    if (productId === values.revenueCatEnterpriseProductId || label.includes('enterprise')) return 'enterprise';
    if (productId === values.revenueCatProfessionalProductId || label.includes('professional') || label.includes('pro')) return 'professional';
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
    const packageId = String(item.identifier || item.packageIdentifier || item.package_identifier || '');
    return creditPackConfig().find(pack => (
      productId === pack.productId
      || packageId === pack.code
      || packageId.includes(pack.productId)
    )) || null;
  }

  async function offeringPackages() {
    if (!(await configure())) return [];
    const offeringsResult = await purchases().getOfferings();
    const offering = offeringsResult?.offerings?.current || offeringsResult?.current;
    return offering?.availablePackages || offering?.available_packages || [];
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

  async function purchase(tier = 'professional') {
    if (!native()) throw new Error('Native billing is only available in the installed mobile app.');
    if (!(await configure())) {
      throw new Error('App Store billing is not configured yet. Add the RevenueCat public SDK key before submission.');
    }
    const packages = await offeringPackages();
    const selected = packages.find(item => tierForPackage(item) === tier);
    if (!selected) throw new Error('That subscription package is not available from the store.');
    const result = await purchases().purchasePackage({ aPackage: selected });
    await synchronizeServerEntitlement();
    await refreshStatus();
    return result;
  }

  async function purchaseCredits(packCode) {
    if (!native()) throw new Error('Use secure web checkout to purchase credits on the web.');
    if (!(await configure())) {
      throw new Error('App Store billing is not configured yet.');
    }
    const packages = await offeringPackages();
    const selected = packages.find(item => creditPackForPackage(item)?.code === packCode);
    if (!selected) throw new Error('That credit pack is not available from the store yet.');
    const result = await purchases().purchasePackage({ aPackage: selected });
    // RevenueCat records the consumable purchase. Ask Crump then queries the
    // server-side customer record and grants only transaction IDs it has never
    // seen before, preventing duplicate credit deposits.
    await purchases().invalidateVirtualCurrenciesCache?.().catch?.(() => {});
    await synchronizeServerCredits();
    return result;
  }

  async function restore() {
    if (!(await configure())) throw new Error('Native billing is not configured.');
    const result = await purchases().restorePurchases();
    await synchronizeServerEntitlement();
    await synchronizeServerCredits().catch(() => {});
    await refreshStatus();
    return result;
  }

  async function synchronizeServerEntitlement() {
    const response = await fetch('/api/billing/revenuecat/sync', { method: 'POST' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) {
      throw new Error(data.error || 'Your purchase completed, but subscription verification is still processing.');
    }
    if (data.user) {
      window.currentUser = data.user;
      window.profileManager?.applyServerSubscription?.(data.user);
    }
    return data;
  }

  async function synchronizeServerCredits() {
    const response = await fetch('/api/billing/credits/revenuecat/sync', { method: 'POST' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) {
      throw new Error(data.error || 'Your purchase completed, but credit verification is still processing.');
    }
    window.dispatchEvent(new CustomEvent('crump:credits-updated', { detail: data.credits || {} }));
    return data;
  }

  async function manageSubscription() {
    if (native()) {
      if (!(await configure())) throw new Error('Native billing is not configured.');
      const result = await purchases().getCustomerInfo();
      const info = result?.customerInfo || result?.customer_info || result;
      const url = info?.managementURL || info?.managementUrl || info?.management_url;
      if (!url) throw new Error('No active store subscription was found.');
      window.open(url, '_blank', 'noopener,noreferrer');
      return {url};
    }
    const response = await fetch('/api/stripe/customer-portal', {method: 'POST'});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.url) throw new Error(data.error || 'Subscription management could not be opened.');
    window.location.assign(data.url);
    return data;
  }

  async function refreshStatus() {
    const response = await fetch('/api/billing/status');
    const data = await response.json().catch(() => ({}));
    if (response.ok && data.success && data.user) {
      window.currentUser = data.user;
      window.profileManager?.applyServerSubscription?.(data.user);
    }
    return data;
  }

  async function refreshCredits() {
    const response = await fetch('/api/billing/credits/status');
    const data = await response.json().catch(() => ({}));
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
    refreshStatus,
    refreshCredits,
    synchronizeServerCredits,
    isNative: native,
  };
})();
