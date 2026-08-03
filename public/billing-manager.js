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

  async function purchase(tier = 'professional') {
    if (!native()) throw new Error('Native billing is only available in the installed mobile app.');
    if (!(await configure())) {
      throw new Error('App Store billing is not configured yet. Add the RevenueCat public SDK key before submission.');
    }
    const packages = await offeringPackages();
    const selected = packages.find(item => tierForPackage(item) === tier) || packages[0];
    if (!selected) throw new Error('No subscription package is available from the store.');
    const result = await purchases().purchasePackage({ aPackage: selected });
    await synchronizeServerEntitlement();
    await refreshStatus();
    return result;
  }

  async function restore() {
    if (!(await configure())) throw new Error('Native billing is not configured.');
    const result = await purchases().restorePurchases();
    await synchronizeServerEntitlement();
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

  async function refreshStatus() {
    const response = await fetch('/api/billing/status');
    const data = await response.json().catch(() => ({}));
    if (response.ok && data.success && data.user) {
      window.currentUser = data.user;
      window.profileManager?.applyServerSubscription?.(data.user);
    }
    return data;
  }

  window.BillingManager = { configure, getProducts, purchase, restore, refreshStatus, isNative: native };
})();
