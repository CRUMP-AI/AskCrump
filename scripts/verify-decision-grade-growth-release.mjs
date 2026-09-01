import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const BASE = '7cb357e3452d273375106bfdce5ff390dbadad66';
const MIGRATION = 'migrations/20260901012708_decision_grade_growth_snapshot.sql';
const ALLOWED = new Set([
  'docs/DECISION_GRADE_GROWTH_EVIDENCE_RELEASE_2026-08-31.md',
  MIGRATION,
  'scripts/export_weekly_growth.py',
  'scripts/verify-decision-grade-growth-release.mjs',
  'tests/test_decision_grade_growth_snapshot.py',
  'tests/test_weekly_growth_export.py',
]);

function fail(message) {
  console.error(`Decision-grade growth release verification failed: ${message}`);
  process.exit(1);
}

function git(...args) {
  return execFileSync('git', args, { encoding: 'utf8' }).trim();
}

function splitTopLevel(source) {
  const values = [];
  let start = 0;
  let depth = 0;
  let quote = null;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (quote) {
      if (character === quote && source[index - 1] !== '\\') quote = null;
      continue;
    }
    if (character === "'" || character === '"') {
      quote = character;
    } else if (character === '(') {
      depth += 1;
    } else if (character === ')') {
      depth -= 1;
    } else if (character === ',' && depth === 0) {
      values.push(source.slice(start, index).trim());
      start = index + 1;
    }
  }
  values.push(source.slice(start).trim());
  return values.filter(Boolean);
}

function parenthesizedBlock(source, marker) {
  const markerIndex = source.indexOf(marker);
  if (markerIndex < 0) fail(`missing SQL marker: ${marker}`);
  const openIndex = source.indexOf('(', markerIndex + marker.length);
  let depth = 0;
  let quote = null;
  for (let index = openIndex; index < source.length; index += 1) {
    const character = source[index];
    if (quote) {
      if (character === quote && source[index - 1] !== '\\') quote = null;
      continue;
    }
    if (character === "'" || character === '"') quote = character;
    else if (character === '(') depth += 1;
    else if (character === ')') {
      depth -= 1;
      if (depth === 0) return source.slice(openIndex + 1, index);
    }
  }
  fail(`unclosed SQL block after: ${marker}`);
}

const statusPaths = execFileSync('git', ['status', '--porcelain=v1'], { encoding: 'utf8' })
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => line.slice(3).replaceAll('\\', '/'));
let committedPaths = [];
try {
  committedPaths = git('diff', '--name-only', `${BASE}..HEAD`)
    .split(/\r?\n/)
    .filter(Boolean)
    .map((path) => path.replaceAll('\\', '/'));
} catch {
  fail(`baseline ${BASE} is not available locally`);
}
const changedPaths = new Set([...statusPaths, ...committedPaths]);
for (const path of changedPaths) {
  if (!ALLOWED.has(path)) fail(`unexpected changed path ${path}`);
}
for (const path of ALLOWED) {
  if (!changedPaths.has(path)) fail(`required release path is unchanged: ${path}`);
}

const sql = readFileSync(MIGRATION, 'utf8').toLowerCase();
for (const forbidden of [
  'create table',
  'alter table',
  'create index',
  'insert into',
  'update public.',
  'delete from',
  'api_',
]) {
  if (sql.includes(forbidden)) fail(`migration contains forbidden scope: ${forbidden}`);
}
for (const required of [
  'security invoker',
  'set search_path = \'\'',
  'from public, anon, authenticated',
  'to service_role',
  "e.event_name = 'outcomefeedbacksubmitted'",
  "e.source = 'useful'",
  'signals.activation_24h',
  'signals.useful_feedback_24h',
  'signals.durable_value_24h',
  'where j.active_subscription_payer or j.credit_payer',
]) {
  if (!sql.includes(required)) fail(`migration is missing required contract: ${required}`);
}

const returnFields = splitTopLevel(parenthesizedBlock(sql, 'returns table'));
const returnNames = returnFields.map((field) => field.split(/\s+/)[0]);
const expectedNames = [
  'cohort_since', 'cohort_until', 'acquisition', 'placement', 'campaign',
  'creative', 'intent', 'accounts_created', 'account_event_recorded',
  'verified_now', 'workspace_opened', 'activation_eligible_24h',
  'activation_reached_24h', 'useful_feedback_reached_24h',
  'durable_value_eligible_24h', 'durable_value_reached_24h',
  'decision_grade_value_reached_24h', 'project_created_reached_24h',
  'project_file_reached_24h', 'ready_file_reached_24h', 'd1_eligible',
  'd1_returned', 'd7_eligible', 'd7_returned', 'plan_intent_reached',
  'subscription_checkout_opened', 'subscription_checkout_completed',
  'credit_checkout_opened', 'credit_checkout_completed', 'distinct_payers',
  'paid_conversion_eligible', 'active_paid_now', 'refund_accounts',
  'recognized_revenue_cents', 'variable_cost_cents',
];
if (JSON.stringify(returnNames) !== JSON.stringify(expectedNames)) {
  fail('SQL return fields differ from the approved aggregate-only schema');
}
const sensitiveReturn = returnNames.filter((name) => [
  'user_id', 'email', 'prompt', 'response', 'filename', 'project_id', 'file_id',
  'payment_method', 'payment_object', 'referrer', 'url', 'metadata',
].includes(name));
if (sensitiveReturn.length) fail(`sensitive return fields: ${sensitiveReturn.join(', ')}`);

const finalSelectStart = sql.indexOf('  select\n    greatest(', sql.indexOf('journeys as'));
const finalSelectEnd = sql.indexOf('\n  from journeys as j', finalSelectStart);
if (finalSelectStart < 0 || finalSelectEnd < 0) fail('final aggregate SELECT was not found');
const selectExpressions = splitTopLevel(
  sql.slice(finalSelectStart + '  select'.length, finalSelectEnd),
);
if (selectExpressions.length !== returnNames.length) {
  fail(`SQL returns ${returnNames.length} fields but selects ${selectExpressions.length}`);
}

const payerExpression = selectExpressions[29];
if (!payerExpression.includes('active_subscription_payer or j.credit_payer')) {
  fail('distinct payer output is not provider-backed');
}
if (payerExpression.includes('checkout_completed')) {
  fail('checkout diagnostics are being counted as payers');
}

execFileSync('git', ['diff', '--check'], { stdio: 'inherit' });
console.log(
  `Decision-grade growth release boundary verified (${changedPaths.size} files, ${returnNames.length} aggregate fields).`,
);
