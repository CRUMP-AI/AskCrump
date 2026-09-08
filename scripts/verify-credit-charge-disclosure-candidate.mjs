import {createHash} from 'node:crypto';
import {execFileSync, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = fileURLToPath(new URL('../', import.meta.url));
const manifestPath = path.join(
  repoRoot,
  'docs',
  'credit-charge-disclosure-isolated-diff.json',
);
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

function fail(message) {
  console.error('Credit-charge disclosure candidate invalid: ' + message);
  process.exit(1);
}

function git(args) {
  return execFileSync('git', args, {
    cwd: repoRoot,
    encoding: 'utf8',
    windowsHide: true,
  }).trim();
}

function normalize(value) {
  return String(value || '').replaceAll('\\', '/');
}

function sha256(relativePath) {
  return createHash('sha256')
    .update(fs.readFileSync(path.join(repoRoot, relativePath)))
    .digest('hex');
}

if (manifest.schemaVersion !== 1) fail('unsupported manifest schema');
if (manifest.status !== 'held') fail('candidate must remain held');
if (manifest.requiresRebaseAfterEarlierRelease !== true) {
  fail('mandatory predecessor rebase gate is missing');
}
if (manifest.requiresFreshMigrationIdentity !== true) {
  fail('fresh action-time migration identity gate is missing');
}
if (git(['rev-parse', 'HEAD']) !== manifest.baseCommit) {
  fail('candidate base commit drifted');
}
if (String(manifest.remoteMigrationHeadObserved) !== '20260901074430') {
  fail('observed remote migration head drifted');
}

const cached = spawnSync('git', ['diff', '--cached', '--quiet'], {
  cwd: repoRoot,
  windowsHide: true,
});
if (cached.status !== 0) fail('candidate contains staged index changes');

const status = execFileSync('git', ['status', '--porcelain=v1', '-uall'], {
  cwd: repoRoot,
  encoding: 'utf8',
  windowsHide: true,
})
  .split(/\r?\n/)
  .filter(Boolean)
  .map(line => normalize(line.slice(3)))
  .sort();
const allowed = [...manifest.allowedPaths].map(normalize).sort();
if (JSON.stringify(status) !== JSON.stringify(allowed)) {
  const missing = allowed.filter(item => !status.includes(item));
  const unexpected = status.filter(item => !allowed.includes(item));
  fail(
    'path boundary drifted; missing=[' + missing.join(', ')
    + '] unexpected=[' + unexpected.join(', ') + ']',
  );
}

const queuedMigrations = status.filter(
  item => item.startsWith('migrations/') && item.endsWith('.sql'),
);
if (queuedMigrations.length !== 0) {
  fail('staging-only candidate entered the migration queue: ' + queuedMigrations.join(', '));
}
if (manifest.stagingSql !== 'staging/confirmed_feature_spending.sql') {
  fail('unexpected staging SQL path');
}
if (!status.includes(manifest.stagingSql)) fail('staging SQL is missing');
if (fs.existsSync(path.join(
  repoRoot,
  'migrations',
  '20260830222959_confirmed_feature_spending.sql',
))) {
  fail('void pre-ledger migration identity is present');
}

for (const [relativePath, expected] of Object.entries(manifest.contentHashes)) {
  if (!fs.existsSync(path.join(repoRoot, relativePath))) {
    fail('hashed file missing: ' + relativePath);
  }
  if (sha256(relativePath) !== expected) {
    fail('content hash drifted: ' + relativePath);
  }
}

for (const [relativePath, markers] of Object.entries(manifest.requiredMarkers)) {
  const source = fs.readFileSync(path.join(repoRoot, relativePath), 'utf8');
  for (const marker of markers) {
    if (!source.includes(marker)) {
      fail(relativePath + ' is missing required marker: ' + marker);
    }
  }
}

const sql = fs.readFileSync(path.join(repoRoot, manifest.stagingSql), 'utf8').toLowerCase();
const sqlFlat = sql.replace(/\s+/g, ' ');
if ((sql.match(/create or replace function public\.spend_credits_confirmed/g) || []).length !== 1) {
  fail('confirmed-spend function count drifted');
}
if ((sql.match(/security definer/g) || []).length !== 1) {
  fail('security-definer count drifted');
}
if ((sql.match(/set search_path = ''/g) || []).length !== 1) {
  fail('empty function search path drifted');
}
for (const marker of [
  'pg_advisory_xact_lock',
  'p_confirmed_max integer',
  'limit_exceeded boolean',
  'action_spent + p_amount > p_confirmed_max',
  "'confirmedmaximum', p_confirmed_max",
  "provider = 'feature-spend'",
  'external_id = external_key',
  'return query select existing.id',
  'credits_spent <= approved_credit_limit',
  "last_error_code = 'credit_budget_confirmation_required'",
  ') from public, anon, authenticated;',
  ') to service_role;',
  'revoke all on function public.spend_credits(',
  ') from service_role;',
]) {
  if (!sqlFlat.includes(marker)) fail('SQL marker is missing: ' + marker);
}
if (/grant\s+[^;]+\s+to\s+(?:public|anon|authenticated)\b/.test(sql)) {
  fail('candidate grants an RPC to a browser role');
}
for (const match of sql.matchAll(/\b(?:alter|update)\s+(?:table\s+)?public\.([a-z][a-z0-9_]*)/g)) {
  if (match[1] !== 'manuscript_runs' && match[1] !== 'credit_accounts') {
    fail('unexpected mutated table: ' + match[1]);
  }
}
const permittedPublicObjects = new Set([
  'credit_accounts',
  'credit_ledger',
  'manuscript_runs',
  'spend_credits',
  'spend_credits_confirmed',
]);
for (const match of sql.matchAll(/\bpublic\.([a-z][a-z0-9_]*)\b/g)) {
  if (!permittedPublicObjects.has(match[1])) {
    fail('unexpected public object: ' + match[1]);
  }
}
for (const apiOwned of [
  'api_conversations',
  'api_messages',
  'api_idempotency_records',
  'api_media_generations',
  'ask-crump-api-media',
]) {
  if (sql.includes(apiOwned)) fail('candidate touches API-owned namespace: ' + apiOwned);
}
for (const prohibited of [
  'prompt',
  'response_data',
  'request_payload',
  'message_content',
  'filename',
  'storage_path',
  'email',
  'password_hash',
]) {
  if (sql.includes(prohibited)) fail('content or sensitive field reference is present: ' + prohibited);
}

const actionRecord = fs.readFileSync(
  path.join(repoRoot, manifest.actionRecord),
  'utf8',
);
const exactApproval = [
  'Approve the credit-charge disclosure product release under ',
  'docs/CREDIT_CHARGE_DISCLOSURE_RELEASE_ACTION_RECORD_2026-08-30.md. ',
  'Do not bundle the Word/PDF release, publish social content, change profile ',
  'links, submit Search Console, alter prices or plans, modify Stripe or ',
  'RevenueCat, create or reset a demo account, send lifecycle messages, or ',
  'spend money.',
].join('');
if (!actionRecord.replace(/\r?\n/g, '').includes(exactApproval)) {
  fail('exact action-time approval sentence is missing');
}
for (const marker of [
  'staging/confirmed_feature_spending.sql',
  '20260901074430 harden_conversation_image_privileges',
  'supabase migration new confirmed_feature_spending',
  'Do not invent or pre-reserve a timestamp.',
]) {
  if (!actionRecord.includes(marker)) fail('action record marker is missing: ' + marker);
}

const runtime = fs.readFileSync(path.join(repoRoot, 'public', 'runtime-body-v1.js'), 'utf8');
const worker = fs.readFileSync(path.join(repoRoot, 'public', 'sw.js'), 'utf8');
const shell = fs.readFileSync(path.join(repoRoot, 'public', 'app.html'), 'utf8');
const native = fs.readFileSync(path.join(repoRoot, 'scripts', 'build-native.mjs'), 'utf8');
for (const marker of [
  '/credit-confirmation.css?v=5.9.76-credit-confirmation-1',
  '/credit-confirmation.js?v=5.9.76-credit-confirmation-1',
  '/chat-resilience.js?v=5.9.76-credit-confirmation-1',
  '/app.js?v=5.9.76-credit-confirmation-1',
  '/crump-product-5.3.js?v=5.9.76-credit-confirmation-1',
  '/crump-code-5.9.35.js?v=5.9.76-credit-confirmation-1',
  '/crump-billing-5.1.css?v=5.9.76-credit-truth-1',
  '/crump-billing-5.1.js?v=5.9.76-project-limit-plan-dormant-1',
  '/crump-5.2.js?v=5.9.76-uploaded-image-node-stability-1',
  '/crump-v1-body.css?v=5.9.76-credit-truth-1',
]) {
  if (!runtime.includes(marker)) fail('web runtime marker is missing: ' + marker);
  if (!worker.includes(marker)) fail('service-worker marker is missing: ' + marker);
  if (!native.includes(marker)) fail('native marker is missing: ' + marker);
}
if (!worker.includes("ask-crump-new-body-v1-r169")) {
  fail('reserved service-worker cache revision is missing');
}
if (!shell.includes('/runtime-body-v1.js?v=5.9.76-credit-confirmation-1')) {
  fail('shell runtime version is missing');
}
if (!shell.includes('/crump-v1-body.css?v=5.9.76-credit-truth-1')) {
  fail('shell credit-truth stylesheet version is missing');
}

const featureService = fs.readFileSync(
  path.join(repoRoot, 'backend', 'feature_service.py'),
  'utf8',
);
if (!featureService.includes('"creditsSpent": 0 if duplicate else credit_cost')) {
  fail('duplicate receipts can inflate newly spent credits');
}
for (const marker of [
  'def _scope_digest',
  'hmac.compare_digest(',
  '"p_confirmed_max": authorization.confirmed_credits',
  'if credit_row.get("limit_exceeded")',
]) {
  if (!featureService.includes(marker)) {
    fail('credit authorization boundary is missing: ' + marker);
  }
}

const featureRoute = fs.readFileSync(
  path.join(repoRoot, 'backend', 'routes', 'features.py'),
  'utf8',
);
for (const marker of ['quote.pop("token", None)', 'quote.pop("actionKey", None)']) {
  if (!featureRoute.includes(marker)) {
    fail('informational quote route exposes spend authority: ' + marker);
  }
}

const diffCheck = spawnSync('git', ['diff', '--check'], {
  cwd: repoRoot,
  encoding: 'utf8',
  windowsHide: true,
});
if (diffCheck.status !== 0) {
  fail('diff integrity failed: ' + String(diffCheck.stdout || diffCheck.stderr).trim());
}

console.log(
  'Validated held ' + manifest.candidateId + ': '
  + allowed.length + ' exact paths, '
  + Object.keys(manifest.contentHashes).length + ' immutable hashes, '
  + 'zero queued migrations, one staging-only service-role spend boundary, '
  + 'fresh migration identity and predecessor rebase gates retained.',
);
