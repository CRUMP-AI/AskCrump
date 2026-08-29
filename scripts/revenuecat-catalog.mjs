import { readFile } from 'node:fs/promises';

const catalogUrl = new URL('../backend/revenuecat_catalog.json', import.meta.url);

export async function loadRevenueCatCatalog(environment = process.env) {
  const source = JSON.parse(await readFile(catalogUrl, 'utf8'));
  const values = {
    entitlementId: String(environment.REVENUECAT_ENTITLEMENT || source.entitlementId || '').trim(),
    subscriptions: {
      professional: String(environment.REVENUECAT_PROFESSIONAL_PRODUCT_ID || source.subscriptions?.professional || '').trim(),
      enterprise: String(environment.REVENUECAT_ENTERPRISE_PRODUCT_ID || source.subscriptions?.enterprise || '').trim(),
    },
    credits: {
      credits_50: String(environment.REVENUECAT_CREDITS_50_PRODUCT_ID || source.credits?.credits_50 || '').trim(),
      credits_150: String(environment.REVENUECAT_CREDITS_150_PRODUCT_ID || source.credits?.credits_150 || '').trim(),
      credits_400: String(environment.REVENUECAT_CREDITS_400_PRODUCT_ID || source.credits?.credits_400 || '').trim(),
    },
  };

  const identifiers = [values.entitlementId, ...Object.values(values.subscriptions), ...Object.values(values.credits)];
  if (identifiers.some(value => !/^[A-Za-z0-9._-]+$/.test(value))) {
    throw new Error('RevenueCat identifiers must be non-empty and contain only letters, numbers, dots, underscores, or hyphens.');
  }
  const productIds = [...Object.values(values.subscriptions), ...Object.values(values.credits)];
  if (new Set(productIds).size !== productIds.length) {
    throw new Error('RevenueCat subscription and credit product identifiers must be unique.');
  }
  return Object.freeze({
    entitlementId: values.entitlementId,
    subscriptions: Object.freeze(values.subscriptions),
    credits: Object.freeze(values.credits),
  });
}
