export const minimumVercelNodeVersion = Object.freeze([22, 23, 4]);

export function supportsVercelNodeVersion(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  if (!match) return false;

  const [, majorText, minorText, patchText] = match;
  const [major, minor, patch] = [majorText, minorText, patchText].map(Number);
  const [minimumMajor, minimumMinor, minimumPatch] = minimumVercelNodeVersion;

  return major === minimumMajor
    && (minor > minimumMinor || (minor === minimumMinor && patch >= minimumPatch));
}
