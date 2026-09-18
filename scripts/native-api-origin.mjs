export const PRODUCTION_NATIVE_API_BASE = 'https://www.askcrump.com';

export function requireProductionNativeApiBase(value = '') {
  const candidate = String(value || PRODUCTION_NATIVE_API_BASE).trim();
  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error('CRUMP_API_BASE must be the production Ask Crump HTTPS origin.');
  }

  const originOnly = parsed.pathname === '/'
    && !parsed.username
    && !parsed.password
    && !parsed.search
    && !parsed.hash;
  if (parsed.protocol !== 'https:' || parsed.origin !== PRODUCTION_NATIVE_API_BASE || !originOnly) {
    throw new Error(
      `CRUMP_API_BASE must resolve exactly to ${PRODUCTION_NATIVE_API_BASE}; `
      + 'native bearer credentials must never be built for another host or URL path.',
    );
  }
  return PRODUCTION_NATIVE_API_BASE;
}
