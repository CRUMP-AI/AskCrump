import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const BASE = '8d836e5c4decb5a034314021c255520bbb371fd6';
const LANDING_VERSION = '5.9.76-marketing-landing-1';
const CACHE_NAME = 'ask-crump-new-body-v1-r173';

const allowedPaths = new Set([
  'public/ai-document-generator.html',
  'public/ai-presentation-maker.html',
  'public/ai-project-workspace.html',
  'public/ai-resume-builder.html',
  'public/ai-video-generator.html',
  'public/ask-crump.html',
  'public/guides/editable-ai-powerpoint-review.html',
  'public/guides/rough-idea-six-week-launch-plan.html',
  'public/guides/what-ai-project-should-remember.html',
  'public/landing.js',
  'public/sw.js',
  'scripts/check-javascript.mjs',
  'scripts/verify-marketing-landing-browser.cjs',
  'scripts/verify-marketing-landing-release.mjs',
  'tests/test_auth_request_resilience.py',
  'tests/test_billing_request_timeout.py',
  'tests/test_contextual_plan_recovery.py',
  'tests/test_conversation_creation_intelligence.py',
  'tests/test_credit_balance_refresh.py',
  'tests/test_destination_tool_hierarchy.py',
  'tests/test_intelligence_glasses_icon_contract.py',
  'tests/test_intelligence_receipt.py',
  'tests/test_lifecycle_activation.py',
  'tests/test_marketing_landing_measurement.py',
  'tests/test_mobile_documents_tool_contract.py',
  'tests/test_mobile_zoom_policy_contract.py',
  'tests/test_monetization_recovery_measurement.py',
  'tests/test_navigation_5930.py',
  'tests/test_plan_value_clarity.py',
  'tests/test_product531_contract.py',
  'tests/test_product53_contract.py',
  'tests/test_product56_polish.py',
  'tests/test_public_destination_consistency.py',
  'tests/test_release_guard.py',
  'tests/test_revenue_conversion.py',
  'tests/test_search_guides.py',
  'tests/test_workspace_runtime_fetch_plan.py',
]);

const landingPages = [
  'public/ai-document-generator.html',
  'public/ai-presentation-maker.html',
  'public/ai-project-workspace.html',
  'public/ai-resume-builder.html',
  'public/ai-video-generator.html',
  'public/ask-crump.html',
  'public/guides/editable-ai-powerpoint-review.html',
  'public/guides/rough-idea-six-week-launch-plan.html',
  'public/guides/what-ai-project-should-remember.html',
];

function lines(value) {
  return value.split(/\r?\n/).map(item => item.trim()).filter(Boolean);
}

function git(...args) {
  return execFileSync('git', args, { encoding: 'utf8' });
}

function fail(message) {
  console.error(`Marketing landing release verification failed: ${message}`);
  process.exit(1);
}

git('merge-base', '--is-ancestor', BASE, 'HEAD');
const tracked = lines(git('diff', '--name-only', BASE, '--'));
const untracked = lines(git('ls-files', '--others', '--exclude-standard'));
const changed = [...new Set([...tracked, ...untracked])].sort();
const unexpected = changed.filter(path => !allowedPaths.has(path));
const missing = [...allowedPaths].filter(path => !changed.includes(path));
if (unexpected.length || missing.length) {
  fail(`release boundary mismatch. Unexpected: ${unexpected.join(', ') || 'none'}. Missing: ${missing.join(', ') || 'none'}.`);
}

for (const forbiddenPrefix of ['backend/', 'migrations/', 'supabase/', 'api/']) {
  if (changed.some(path => path.startsWith(forbiddenPrefix))) {
    fail(`forbidden product surface changed: ${forbiddenPrefix}`);
  }
}
if (changed.includes('public/auth-controller.js')) {
  fail('authentication attribution is outside this release.');
}

const landing = readFileSync('public/landing.js', 'utf8');
const emitStart = landing.indexOf('function emitMarketingLanding');
const emitEnd = landing.indexOf('\n  emitMarketingLanding(attribution', emitStart + 1);
if (emitStart < 0 || emitEnd < 0) fail('MarketingLanding emitter is missing.');
const emitter = landing.slice(emitStart, emitEnd);
for (const marker of ["name: 'MarketingLanding'", 'touchpoint,', 'intent: attribution.intent']) {
  if (!emitter.includes(marker)) fail(`emitter marker is missing: ${marker}`);
}
for (const forbidden of ['accountId', 'userId', 'email', 'prompt', 'response', 'filename', 'referrer', 'document.cookie', 'localStorage', 'fetch(']) {
  if (emitter.includes(forbidden)) fail(`emitter contains forbidden data or persistence marker: ${forbidden}`);
}
if (!landing.includes("sessionStorage.setItem(MARKETING_LANDING_KEY, '1')") ||
    !landing.includes("? 'registered-campaign'") ||
    !landing.includes("? 'exact-referral'") ||
    !landing.includes(": 'rejected'")) {
  fail('once-per-tab or fail-closed attribution markers are incomplete.');
}

for (const page of landingPages) {
  const html = readFileSync(page, 'utf8');
  const expected = `<script defer src="/landing.js?v=${LANDING_VERSION}"></script>`;
  if (!html.includes(expected)) fail(`${page} does not pin ${LANDING_VERSION}.`);
}

const worker = readFileSync('public/sw.js', 'utf8');
if (!worker.includes(`const CACHE_NAME = '${CACHE_NAME}'`) ||
    !worker.includes(`/landing.js?v=${LANDING_VERSION}`)) {
  fail('service-worker cache or landing asset version is incorrect.');
}

execFileSync('git', ['diff', '--check', BASE, '--'], { stdio: 'inherit' });
console.log(`Marketing landing release boundary verified across ${changed.length} exact files.`);
