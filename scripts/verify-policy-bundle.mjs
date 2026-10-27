import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const defaultRoot = new URL('../', import.meta.url);
const sourcePaths = Object.freeze({
  manifest: 'public/legal-policy-bundles.json',
  legal: 'public/legal.html',
  app: 'public/app.html',
  frontend: 'public/auth-controller.js',
  schemas: 'backend/schemas.py',
  policyModule: 'backend/policy_consent.py',
  migration: 'migrations/20261027075649_server_policy_consent_receipts.sql',
});
const policySectionIds = Object.freeze(['terms', 'ai', 'privacy', 'subscriptions', 'age', 'liability']);
const componentSections = Object.freeze({
  terms: 'terms',
  privacy: 'privacy',
  ageAttestation: 'age',
  providerDisclosure: 'ai',
});

const sha256 = value => createHash('sha256').update(value, 'utf8').digest('hex');
const escapeRegex = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function fail(message) {
  throw new Error(message);
}

function assertExact(actual, expected, label) {
  if (actual !== expected) {
    fail(`${label} is ${JSON.stringify(actual)}; expected ${JSON.stringify(expected)}.`);
  }
}

function assertExactKeys(value, expectedKeys, label) {
  const actual = Object.keys(value || {}).sort();
  const expected = [...expectedKeys].sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    fail(`${label} keys are ${JSON.stringify(actual)}; expected ${JSON.stringify(expected)}.`);
  }
}

function assertHex(value, label) {
  if (!/^[0-9a-f]{64}$/.test(String(value || ''))) {
    fail(`${label} must be one lowercase SHA-256 digest.`);
  }
}

function singleMatch(source, pattern, label) {
  const matches = [...source.matchAll(pattern)];
  if (matches.length !== 1) {
    fail(`${label} must have exactly one executable definition; found ${matches.length}.`);
  }
  return matches[0];
}

function outerSection(legal, id) {
  const pattern = new RegExp(`<section id="${escapeRegex(id)}">[\\s\\S]*?</section>`, 'g');
  const matches = [...legal.matchAll(pattern)];
  if (matches.length !== 1) {
    fail(`Covered legal section #${id} must occur exactly once; found ${matches.length}.`);
  }
  return matches[0][0];
}

function pythonStringConstant(source, name, label) {
  const escaped = escapeRegex(name);
  const direct = [...source.matchAll(new RegExp(`^${escaped}\\s*=\\s*"([^"\\r\\n]+)"\\s*$`, 'gm'))];
  const wrapped = [...source.matchAll(new RegExp(
    `^${escaped}\\s*=\\s*\\(\\s*\\n\\s*"([^"\\r\\n]+)"\\s*\\n\\)\\s*$`,
    'gm',
  ))];
  const matches = [...direct, ...wrapped];
  if (matches.length !== 1) {
    fail(`${label} must have exactly one top-level string assignment; found ${matches.length}.`);
  }
  return matches[0][1];
}

function pythonClassBody(source, className) {
  const declaration = singleMatch(
    source,
    new RegExp(`^class ${escapeRegex(className)}\\(APIModel\\):\\s*$`, 'gm'),
    `backend/schemas.py ${className}`,
  );
  const bodyStart = declaration.index + declaration[0].length;
  const remaining = source.slice(bodyStart);
  const nextClass = remaining.search(/^class [A-Za-z_][A-Za-z0-9_]*\(/m);
  return nextClass === -1 ? remaining : remaining.slice(0, nextClass);
}

function pythonLiteralFieldValues(classBody, fieldName, label) {
  const body = singleMatch(
    classBody,
    new RegExp(`^[ \\t]+${escapeRegex(fieldName)}:\\s*Literal\\[([\\s\\S]*?)\\](?:\\s*\\|\\s*None)?(?:\\s*=.*)?$`, 'gm'),
    label,
  )[1];
  const values = [...body.matchAll(/"([^"\r\n]+)"/g)].map(match => match[1]);
  if (values.length === 0) fail(`${label} must contain at least one string literal.`);
  return values;
}

function javascriptStringConstant(source, name, label) {
  return singleMatch(
    source,
    new RegExp(`^[ \\t]*const ${escapeRegex(name)} = '([^'\\r\\n]+)';\\s*$`, 'gm'),
    label,
  )[1];
}

function balancedObjectLiteral(source, assignmentName, label) {
  const assignment = singleMatch(
    source,
    new RegExp(`^${escapeRegex(assignmentName)}\\s*=\\s*\\{`, 'gm'),
    label,
  );
  const start = source.indexOf('{', assignment.index);
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let index = start; index < source.length; index += 1) {
    const character = source[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (character === '\\') escaped = true;
      else if (character === quote) quote = null;
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
    } else if (character === '{') {
      depth += 1;
    } else if (character === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  fail(`${label} has an unterminated object literal.`);
}

function policyComponents(source) {
  const literal = balancedObjectLiteral(
    source,
    'CURRENT_POLICY_COMPONENTS',
    'backend/policy_consent.py CURRENT_POLICY_COMPONENTS',
  );
  try {
    return JSON.parse(literal.replace(/,\s*([}\]])/g, '$1'));
  } catch (error) {
    fail(`backend/policy_consent.py CURRENT_POLICY_COMPONENTS is not an exact literal: ${error.message}`);
  }
}

function splitSqlList(source) {
  const values = [];
  let start = 0;
  let quoted = false;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (character === "'") {
      if (quoted && source[index + 1] === "'") {
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === ',' && !quoted) {
      values.push(source.slice(start, index).trim());
      start = index + 1;
    }
  }
  values.push(source.slice(start).trim());
  return values;
}

function sqlLiteral(value, label) {
  const date = /^date\s+'(\d{4}-\d{2}-\d{2})'$/.exec(value);
  if (date) return date[1];
  const text = /^'((?:''|[^'])*)'$/.exec(value);
  if (text) return text[1].replaceAll("''", "'");
  fail(`${label} contains a non-literal SQL value ${JSON.stringify(value)}.`);
}

function migrationSeed(source) {
  const executableSource = stripSqlComments(source);
  const match = singleMatch(
    executableSource,
    /^insert into public\.consent_policy_bundles\s*\(\s*\n([\s\S]*?)^\) values \(\s*\n([\s\S]*?)^\) on conflict \(bundle_id\) do nothing;\s*$/gm,
    'policy migration consent_policy_bundles seed',
  );
  const columns = match[1].split(',').map(value => value.trim()).filter(Boolean);
  const rawValues = splitSqlList(match[2]);
  if (columns.length !== rawValues.length) {
    fail(`Policy migration seed has ${columns.length} columns but ${rawValues.length} values.`);
  }
  return Object.fromEntries(columns.map((column, index) => [
    column,
    sqlLiteral(rawValues[index], `Policy migration seed column ${column}`),
  ]));
}

function stripSqlComments(source) {
  let output = '';
  let state = 'normal';
  for (let index = 0; index < source.length; index += 1) {
    const current = source[index];
    const next = source[index + 1];
    if (state === 'line') {
      if (current === '\n') {
        output += current;
        state = 'normal';
      } else output += ' ';
    } else if (state === 'block') {
      if (current === '*' && next === '/') {
        output += '  ';
        index += 1;
        state = 'normal';
      } else output += current === '\n' ? '\n' : ' ';
    } else if (state === 'quote') {
      output += current;
      if (current === "'" && next === "'") {
        output += next;
        index += 1;
      } else if (current === "'") state = 'normal';
    } else if (current === '-' && next === '-') {
      output += '  ';
      index += 1;
      state = 'line';
    } else if (current === '/' && next === '*') {
      output += '  ';
      index += 1;
      state = 'block';
    } else {
      output += current;
      if (current === "'") state = 'quote';
    }
  }
  return output;
}

function sqlFunctionBody(source, functionName) {
  const declaration = singleMatch(
    source,
    new RegExp(`^create or replace function public\\.${escapeRegex(functionName)}\\(`, 'gm'),
    `policy migration function ${functionName}`,
  );
  const remaining = source.slice(declaration.index);
  const delimiterMatch = /\bas (\$[A-Za-z_][A-Za-z0-9_]*\$)\s*\n/.exec(remaining);
  if (!delimiterMatch) fail(`Policy migration function ${functionName} has no named body delimiter.`);
  const bodyStart = delimiterMatch.index + delimiterMatch[0].length;
  const bodyEnd = remaining.indexOf(`\n${delimiterMatch[1]};`, bodyStart);
  if (bodyEnd === -1) fail(`Policy migration function ${functionName} has no closing body delimiter.`);
  return stripSqlComments(remaining.slice(bodyStart, bodyEnd));
}

function assertSqlBundlePredicates(body, expectedSeed, columns, label) {
  for (const column of columns) {
    const value = expectedSeed[column];
    const literal = column === 'effective_date'
      ? `date '${value}'`
      : `'${String(value).replaceAll("'", "''")}'`;
    const pattern = new RegExp(
      `^[ \\t]*(?:where|and) bundle\\.${escapeRegex(column)}\\s*=\\s*${escapeRegex(literal)}\\s*$`,
      'gm',
    );
    singleMatch(body, pattern, `${label} ${column} predicate`);
  }
}

function returnedBundleHash(body, label) {
  return singleMatch(
    body,
    /^[ \t]*'([0-9a-f]{64})'::text[,;]\s*$/gm,
    `${label} returned bundle hash`,
  )[1];
}

function currentBundle(manifest) {
  if (manifest?.schemaVersion !== 1 || !Array.isArray(manifest?.bundles)) {
    fail('The legal-policy manifest must use schemaVersion 1 and a bundles array.');
  }
  const ids = manifest.bundles.map(bundle => bundle?.bundleId);
  if (new Set(ids).size !== ids.length) fail('The legal-policy manifest contains duplicate bundle IDs.');
  const matches = manifest.bundles.filter(bundle => bundle?.bundleId === manifest.currentBundleId);
  if (matches.length !== 1) {
    fail(`The current legal-policy bundle must occur exactly once; found ${matches.length}.`);
  }
  return matches[0];
}

export async function loadPolicyBundleSources(root = defaultRoot) {
  const entries = await Promise.all(Object.entries(sourcePaths).map(async ([name, path]) => [
    name,
    (await readFile(new URL(path, root), 'utf8')).replaceAll('\r\n', '\n'),
  ]));
  return Object.fromEntries(entries);
}

export function verifyPolicyBundleSources(sources) {
  for (const name of Object.keys(sourcePaths)) {
    if (typeof sources?.[name] !== 'string') fail(`Policy verifier source ${name} is missing.`);
  }

  let manifest;
  try {
    manifest = JSON.parse(sources.manifest);
  } catch (error) {
    fail(`The legal-policy manifest is not valid JSON: ${error.message}`);
  }
  const current = currentBundle(manifest);
  const bundleMatch = /^ask-crump-legal-(\d{4}-\d{2}-\d{2})-([0-9a-f]{8})$/.exec(current.bundleId || '');
  if (!bundleMatch) fail('The current legal-policy bundle ID has an invalid format.');
  assertHex(current.policySectionsSha256, 'Current policy-sections hash');
  if (bundleMatch[2] !== current.policySectionsSha256.slice(0, 8)) {
    fail('The current bundle ID suffix is not the first eight characters of policySectionsSha256.');
  }
  assertExact(current.effectiveDate, bundleMatch[1], 'Current bundle effective date');
  assertExact(current.legalPath, '/legal.html', 'Current bundle legal path');
  assertExact(current.canonicalization, 'html-section-outerhtml-lf-v1', 'Current bundle canonicalization');
  for (const [field, label] of [
    ['legalDocumentSha256', 'Legal document hash'],
    ['registrationDisclosureSha256', 'Registration disclosure hash'],
    ['fallbackDisclosureSha256', 'Fallback disclosure hash'],
  ]) assertHex(current[field], label);

  assertExactKeys(current.components, Object.keys(componentSections), 'Current policy components');
  for (const [name, sectionId] of Object.entries(componentSections)) {
    const component = current.components[name];
    assertExact(component.legalSectionId, sectionId, `Policy component ${name} legal section`);
    if (!/^ask-crump-[a-z0-9-]+-v[0-9]+$/.test(String(component.id || ''))) {
      fail(`Policy component ${name} has an invalid component ID.`);
    }
    assertHex(component.sha256, `Policy component ${name} hash`);
    assertExact(
      sha256(outerSection(sources.legal, component.legalSectionId)),
      component.sha256,
      `Covered legal section #${component.legalSectionId} hash`,
    );
  }

  const policySections = policySectionIds.map(id => outerSection(sources.legal, id)).join('\n');
  assertExact(sha256(policySections), current.policySectionsSha256, 'Covered legal content hash');
  assertExact(sha256(sources.legal), current.legalDocumentSha256, 'legal.html document hash');

  const registrationLabel = singleMatch(
    sources.app,
    /<label class="v1-registration-consent"[\s\S]*?<\/label>/g,
    'Registration consent disclosure',
  )[0];
  const fallbackLabel = singleMatch(
    sources.app,
    /<label class="terms-consent"[\s\S]*?<\/label>/g,
    'Authenticated consent disclosure',
  )[0];
  assertExact(
    sha256(registrationLabel),
    current.registrationDisclosureSha256,
    'Registration consent disclosure hash',
  );
  assertExact(
    sha256(fallbackLabel),
    current.fallbackDisclosureSha256,
    'Authenticated consent disclosure hash',
  );

  assertExact(
    javascriptStringConstant(sources.frontend, 'TERMS_VERSION', 'public/auth-controller.js TERMS_VERSION'),
    current.bundleId,
    'public/auth-controller.js TERMS_VERSION',
  );
  assertExact(
    javascriptStringConstant(sources.frontend, 'TERMS_BUNDLE_HASH', 'public/auth-controller.js TERMS_BUNDLE_HASH'),
    current.policySectionsSha256,
    'public/auth-controller.js TERMS_BUNDLE_HASH',
  );

  assertExact(
    pythonStringConstant(sources.schemas, 'CURRENT_POLICY_BUNDLE_ID', 'backend/schemas.py CURRENT_POLICY_BUNDLE_ID'),
    current.bundleId,
    'backend/schemas.py CURRENT_POLICY_BUNDLE_ID',
  );
  assertExact(
    pythonStringConstant(sources.schemas, 'CURRENT_POLICY_BUNDLE_HASH', 'backend/schemas.py CURRENT_POLICY_BUNDLE_HASH'),
    current.policySectionsSha256,
    'backend/schemas.py CURRENT_POLICY_BUNDLE_HASH',
  );
  const expectedTransitionVersions = ['2026-08-01', current.bundleId].sort();
  const registerVersions = pythonLiteralFieldValues(
    pythonClassBody(sources.schemas, 'RegisterRequest'),
    'termsVersion',
    'backend/schemas.py RegisterRequest.termsVersion',
  ).sort();
  const acceptanceVersions = pythonLiteralFieldValues(
    pythonClassBody(sources.schemas, 'TermsAcceptanceRequest'),
    'version',
    'backend/schemas.py TermsAcceptanceRequest.version',
  ).sort();
  assertExact(
    JSON.stringify(registerVersions),
    JSON.stringify(expectedTransitionVersions),
    'backend/schemas.py RegisterRequest transition versions',
  );
  assertExact(
    JSON.stringify(acceptanceVersions),
    JSON.stringify(expectedTransitionVersions),
    'backend/schemas.py TermsAcceptanceRequest transition versions',
  );

  assertExact(
    pythonStringConstant(
      sources.policyModule,
      'CURRENT_POLICY_BUNDLE_ID',
      'backend/policy_consent.py CURRENT_POLICY_BUNDLE_ID',
    ),
    current.bundleId,
    'backend/policy_consent.py CURRENT_POLICY_BUNDLE_ID',
  );
  assertExact(
    pythonStringConstant(
      sources.policyModule,
      'CURRENT_POLICY_BUNDLE_HASH',
      'backend/policy_consent.py CURRENT_POLICY_BUNDLE_HASH',
    ),
    current.policySectionsSha256,
    'backend/policy_consent.py CURRENT_POLICY_BUNDLE_HASH',
  );
  const expectedComponents = Object.fromEntries(Object.keys(componentSections).map(name => [name, {
    id: current.components[name].id,
    sha256: current.components[name].sha256,
  }]));
  const moduleComponents = policyComponents(sources.policyModule);
  if (JSON.stringify(moduleComponents) !== JSON.stringify(expectedComponents)) {
    fail('backend/policy_consent.py CURRENT_POLICY_COMPONENTS does not exactly mirror the manifest.');
  }

  const expectedSeed = {
    bundle_id: current.bundleId,
    effective_date: current.effectiveDate,
    legal_path: current.legalPath,
    canonicalization: current.canonicalization,
    legal_document_sha256: current.legalDocumentSha256,
    policy_sections_sha256: current.policySectionsSha256,
    registration_disclosure_sha256: current.registrationDisclosureSha256,
    fallback_disclosure_sha256: current.fallbackDisclosureSha256,
    terms_component_id: current.components.terms.id,
    terms_sha256: current.components.terms.sha256,
    privacy_component_id: current.components.privacy.id,
    privacy_sha256: current.components.privacy.sha256,
    age_attestation_component_id: current.components.ageAttestation.id,
    age_attestation_sha256: current.components.ageAttestation.sha256,
    provider_disclosure_component_id: current.components.providerDisclosure.id,
    provider_disclosure_sha256: current.components.providerDisclosure.sha256,
  };
  const actualSeed = migrationSeed(sources.migration);
  if (JSON.stringify(actualSeed) !== JSON.stringify(expectedSeed)) {
    fail('Policy migration seed does not exactly mirror the current manifest and component values.');
  }

  const allSeedColumns = Object.keys(expectedSeed);
  const componentColumns = [
    'bundle_id',
    'policy_sections_sha256',
    'terms_component_id',
    'terms_sha256',
    'privacy_component_id',
    'privacy_sha256',
    'age_attestation_component_id',
    'age_attestation_sha256',
    'provider_disclosure_component_id',
    'provider_disclosure_sha256',
  ];
  const recordBody = sqlFunctionBody(sources.migration, 'record_policy_acceptance_v1');
  assertExact(
    singleMatch(
      recordBody,
      /^[ \t]*if p_bundle_id is distinct from '([^'\r\n]+)'\s*$/gm,
      'record_policy_acceptance_v1 current bundle check',
    )[1],
    current.bundleId,
    'record_policy_acceptance_v1 current bundle check',
  );
  assertSqlBundlePredicates(recordBody, expectedSeed, allSeedColumns, 'record_policy_acceptance_v1');
  assertExact(
    returnedBundleHash(recordBody, 'record_policy_acceptance_v1'),
    current.policySectionsSha256,
    'record_policy_acceptance_v1 returned bundle hash',
  );

  const readBody = sqlFunctionBody(sources.migration, 'read_current_policy_acceptance_v1');
  assertSqlBundlePredicates(readBody, expectedSeed, componentColumns, 'read_current_policy_acceptance_v1');
  assertExact(
    singleMatch(
      readBody,
      /^[ \t]*and receipt\.bundle_id = '([^'\r\n]+)'\s*$/gm,
      'read_current_policy_acceptance_v1 receipt bundle check',
    )[1],
    current.bundleId,
    'read_current_policy_acceptance_v1 receipt bundle check',
  );
  assertExact(
    returnedBundleHash(readBody, 'read_current_policy_acceptance_v1'),
    current.policySectionsSha256,
    'read_current_policy_acceptance_v1 returned bundle hash',
  );

  const assertionBody = sqlFunctionBody(sources.migration, 'assert_policy_consent_schema_v1');
  assertSqlBundlePredicates(assertionBody, expectedSeed, allSeedColumns, 'assert_policy_consent_schema_v1');

  return {bundleId: current.bundleId, policySectionsSha256: current.policySectionsSha256};
}

export async function verifyPolicyBundle(root = defaultRoot) {
  return verifyPolicyBundleSources(await loadPolicyBundleSources(root));
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : '';
if (invokedPath && fileURLToPath(import.meta.url) === invokedPath) {
  const result = await verifyPolicyBundle();
  console.log(`Verified policy bundle ${result.bundleId}.`);
}
