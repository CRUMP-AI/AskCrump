import {
  loadPolicyBundleSources,
  verifyPolicyBundleSources,
} from './verify-policy-bundle.mjs';

function expectFailure(name, sources, expectedMessage) {
  try {
    verifyPolicyBundleSources(sources);
  } catch (error) {
    if (!expectedMessage.test(String(error?.message || error))) {
      throw new Error(`${name} failed for the wrong reason: ${error?.message || error}`);
    }
    return;
  }
  throw new Error(`${name} unexpectedly passed policy-bundle verification.`);
}

const sources = await loadPolicyBundleSources();
const verified = verifyPolicyBundleSources(sources);
const manifest = JSON.parse(sources.manifest);
const bundle = manifest.bundles.find(item => item.bundleId === manifest.currentBundleId);
if (!bundle) throw new Error('Policy verifier self-test could not locate the current bundle.');

expectFailure('covered legal-content mutation', {
  ...sources,
  legal: sources.legal.replace(
    '<section id="terms">',
    '<section id="terms">\n<!-- verifier self-test legal drift -->',
  ),
}, /Covered legal section #terms hash|Covered legal content hash|document hash/);

const hashDriftManifest = structuredClone(manifest);
hashDriftManifest.bundles.find(item => item.bundleId === hashDriftManifest.currentBundleId)
  .policySectionsSha256 = '0'.repeat(64);
expectFailure('manifest hash mutation', {
  ...sources,
  manifest: `${JSON.stringify(hashDriftManifest, null, 2)}\n`,
}, /bundle ID suffix|Covered legal content hash/);

const driftedBundleId = `${bundle.bundleId.slice(0, -8)}ffffffff`;
const idDriftSources = Object.fromEntries(Object.entries(sources).map(([name, source]) => [
  name,
  source.replaceAll(bundle.bundleId, driftedBundleId),
]));
expectFailure(
  'same-hash bundle-ID mutation across every mirror',
  idDriftSources,
  /bundle ID suffix/,
);

expectFailure('migration component mirror mutation', {
  ...sources,
  migration: sources.migration.replace(
    `'${bundle.components.terms.sha256}',`,
    `'${'1'.repeat(64)}',`,
  ),
}, /migration seed/);

expectFailure('comment-only dead-string mirror', {
  ...sources,
  policyModule: sources.policyModule.replace(
    `CURRENT_POLICY_BUNDLE_ID = "${bundle.bundleId}"`,
    `CURRENT_POLICY_BUNDLE_ID = "${driftedBundleId}"\n# Dead mirror only: ${bundle.bundleId}`,
  ),
}, /CURRENT_POLICY_BUNDLE_ID is/);

console.log(`Policy-bundle verifier mutation probes passed for ${verified.bundleId}.`);
