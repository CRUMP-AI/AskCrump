const NON_NAVIGATION_PREFIXES = [
  '#',
  'mailto:',
  'tel:',
  'javascript:',
  'data:',
  'blob:',
];

// Public JavaScript contains both literal anchors and runtime-built anchors. The
// latter are useful product code, but their source fragments are not URLs that a
// live destination monitor can request. These checks only apply to JavaScript:
// every literal HTML href must continue into URL parsing so the monitor stays
// fail-closed for malformed or unexpectedly redirected public markup.
const JAVASCRIPT_RUNTIME_HREF_PATTERNS = [
  /\$\{/,
  /\{\{/,
  /<%/,
  /([\'"`])\s*\+[\s\S]*?\+\s*\1/,
  /([\'"`])\s*\.concat\s*\(/,
];

export function staticAnchorHref(value, sourceType = 'html') {
  const raw = String(value || '').trim().replaceAll('&amp;', '&');
  const lower = raw.toLowerCase();
  if (!raw || NON_NAVIGATION_PREFIXES.some(prefix => lower.startsWith(prefix))) return null;
  const normalizedSourceType = String(sourceType || 'html').trim().toLowerCase();
  if (!['html', 'javascript'].includes(normalizedSourceType)) {
    throw new Error(`Unknown public destination source type: ${sourceType}`);
  }
  if (normalizedSourceType === 'javascript'
      && JAVASCRIPT_RUNTIME_HREF_PATTERNS.some(pattern => pattern.test(raw))) {
    return null;
  }
  return raw;
}
