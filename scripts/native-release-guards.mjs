function decodeNumericCharacterReferences(value) {
  return String(value || '')
    .replace(/&#x([0-9a-f]+);/gi, (match, digits) => {
      const codePoint = Number.parseInt(digits, 16);
      try {
        return Number.isSafeInteger(codePoint) ? String.fromCodePoint(codePoint) : match;
      } catch {
        return match;
      }
    })
    .replace(/&#([0-9]+);/g, (match, digits) => {
      const codePoint = Number.parseInt(digits, 10);
      try {
        return Number.isSafeInteger(codePoint) ? String.fromCodePoint(codePoint) : match;
      } catch {
        return match;
      }
    });
}

export const IOS_MEDIA_USAGE_DESCRIPTION_KEYS = Object.freeze([
  'NSCameraUsageDescription',
  'NSPhotoLibraryUsageDescription',
  'NSPhotoLibraryAddUsageDescription',
]);

export function topLevelPlistStringValues(source, wantedKey) {
  const withoutComments = String(source || '').replace(/<!--[\s\S]*?-->/g, '');
  const tokens = withoutComments.matchAll(/<([^>]+)>|([^<]+)/g);
  const stack = [];
  const values = [];
  let rootDictDepth = null;
  let pendingKey = null;
  let capture = null;

  const finishCapture = tag => {
    if (!capture || capture.tag !== tag) return;
    const text = decodeNumericCharacterReferences(capture.text).trim();
    if (tag === 'key') {
      if (pendingKey !== null && pendingKey === wantedKey) values.push(null);
      pendingKey = text;
    } else if (tag === 'string' && pendingKey !== null) {
      if (pendingKey === wantedKey) values.push(capture.text);
      pendingKey = null;
    }
    capture = null;
  };

  for (const token of tokens) {
    if (token[2] !== undefined) {
      if (capture) capture.text += token[2];
      continue;
    }
    const raw = String(token[1] || '').trim();
    if (!raw || raw.startsWith('?') || raw.startsWith('!')) continue;
    const closing = raw.startsWith('/');
    const selfClosing = raw.endsWith('/');
    const tag = raw.replace(/^\//, '').replace(/\/$/, '').trim().split(/\s+/, 1)[0];
    if (!tag) continue;

    if (closing) {
      finishCapture(tag);
      const popped = stack.pop();
      if (popped !== tag) return [];
      if (rootDictDepth !== null && tag === 'dict' && stack.length < rootDictDepth) {
        if (pendingKey !== null && pendingKey === wantedKey) values.push(null);
        pendingKey = null;
        rootDictDepth = -1;
      }
      continue;
    }

    const directRootChild = rootDictDepth !== null
      && rootDictDepth > 0
      && stack.length === rootDictDepth
      && stack[stack.length - 1] === 'dict';
    if (directRootChild && tag === 'key') {
      if (pendingKey !== null && pendingKey === wantedKey) values.push(null);
      pendingKey = null;
      capture = { tag: 'key', text: '' };
    } else if (directRootChild && tag === 'string') {
      capture = { tag: 'string', text: '' };
    } else if (directRootChild && pendingKey !== null) {
      if (pendingKey === wantedKey) values.push(null);
      pendingKey = null;
    }

    if (selfClosing) {
      finishCapture(tag);
      continue;
    }
    const isRootDict = rootDictDepth === null && tag === 'dict' && stack.at(-1) === 'plist';
    stack.push(tag);
    if (isRootDict) rootDictDepth = stack.length;
  }
  return values;
}

export function nonEmptyPlistString(source, key) {
  const values = topLevelPlistStringValues(source, key);
  if (values.length !== 1 || typeof values[0] !== 'string') return null;
  const value = decodeNumericCharacterReferences(values[0]).trim();
  return value || null;
}

export function missingNonEmptyPlistStrings(
  source,
  keys = IOS_MEDIA_USAGE_DESCRIPTION_KEYS,
) {
  return [...keys].filter(key => !nonEmptyPlistString(source, key));
}
