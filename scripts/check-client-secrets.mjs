import {readdir, readFile, stat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = fileURLToPath(new URL('../', import.meta.url));
const clientRoots = Object.freeze(['public', 'dist']);
const textExtensions = new Set([
  '.css', '.html', '.js', '.json', '.mjs', '.svg', '.txt', '.webmanifest', '.xml',
]);

const fixedSecretPatterns = Object.freeze([
  ['OpenAI secret key', String.raw`(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{20,}`],
  ['Anthropic secret key', String.raw`(?<![A-Za-z0-9])sk-ant-[A-Za-z0-9_-]{20,}`],
  ['Stripe secret key', String.raw`(?<![A-Za-z0-9])(?:sk|rk)_live_[A-Za-z0-9]{16,}`],
  ['Stripe webhook secret', String.raw`(?<![A-Za-z0-9])whsec_[A-Za-z0-9]{16,}`],
  ['Supabase backend secret', String.raw`(?<![A-Za-z0-9])sb_secret_[A-Za-z0-9_-]{16,}`],
  ['Replicate API token', String.raw`(?<![A-Za-z0-9])r8_[A-Za-z0-9]{24,}`],
  ['GitHub access token', String.raw`(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{24,}`],
  ['SendGrid API key', String.raw`(?<![A-Za-z0-9])SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}`],
  ['AWS access key', String.raw`(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])`],
  ['Private key material', String.raw`-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----`],
]);

const sensitiveLiteralNames = Object.freeze([
  'OPENAI_API_KEY',
  'OPENAI_SECRET_KEY',
  'ANTHROPIC_API_KEY',
  'ELEVENLABS_API_KEY',
  'REPLICATE_API_TOKEN',
  'RUNWAY_API_SECRET',
  'STRIPE_SECRET_KEY',
  'STRIPE_WEBHOOK_SECRET',
  'SUPABASE_SERVICE_KEY',
  'SUPABASE_SERVICE_ROLE_KEY',
  'VERCEL_TOKEN',
  'GITHUB_TOKEN',
  'APNS_PRIVATE_KEY',
]);

function findingsInText(source) {
  const findings = new Set();
  for (const [label, pattern] of fixedSecretPatterns) {
    if (new RegExp(pattern, 'g').test(source)) findings.add(label);
  }

  const literalPattern = new RegExp(
    String.raw`\b(${sensitiveLiteralNames.join('|')})\b\s*[:=]\s*["'\x60]([^"'\x60\r\n]{8,})["'\x60]`,
    'g',
  );
  for (const match of source.matchAll(literalPattern)) {
    findings.add(`Hard-coded ${match[1]}`);
  }

  const jwtPattern = /\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b/g;
  for (const token of source.match(jwtPattern) || []) {
    try {
      const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));
      if (payload?.role === 'service_role' || payload?.app_metadata?.role === 'service_role') {
        findings.add('Supabase service-role JWT');
      }
    } catch (_) {
      // A token-shaped string with an unreadable payload is handled only by fixed signatures.
    }
  }
  return [...findings].sort();
}

async function collectTextFiles(root) {
  const files = [];
  async function visit(current) {
    for (const entry of await readdir(current, {withFileTypes: true})) {
      const absolute = path.join(current, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) await visit(absolute);
      else if (entry.isFile() && textExtensions.has(path.extname(entry.name).toLowerCase())) files.push(absolute);
    }
  }
  await visit(root);
  return files.sort();
}

async function scanClientRoots() {
  const findings = [];
  for (const relativeRoot of clientRoots) {
    const absoluteRoot = path.join(repoRoot, relativeRoot);
    const rootStat = await stat(absoluteRoot).catch(() => null);
    if (!rootStat?.isDirectory()) throw new Error(`Required client artifact root is missing: ${relativeRoot}`);
    for (const absoluteFile of await collectTextFiles(absoluteRoot)) {
      const source = await readFile(absoluteFile, 'utf8');
      for (const kind of findingsInText(source)) {
        findings.push({kind, path: path.relative(repoRoot, absoluteFile).replaceAll('\\', '/')});
      }
    }
  }
  return findings;
}

function selfTest() {
  const fakeServiceJwt = [
    Buffer.from(JSON.stringify({alg: 'HS256', typ: 'JWT'})).toString('base64url'),
    Buffer.from(JSON.stringify({role: 'service_role'})).toString('base64url'),
    'fixture_signature_only',
  ].join('.');
  const unsafe = [
    `OPENAI_API_KEY="sk-proj-${'A'.repeat(32)}"`,
    `STRIPE_WEBHOOK_SECRET='whsec_${'B'.repeat(32)}'`,
    `SUPABASE_SERVICE_KEY="sb_secret_${'C'.repeat(32)}"`,
    fakeServiceJwt,
  ].join('\n');
  const unsafeFindings = findingsInText(unsafe);
  for (const expected of [
    'OpenAI secret key',
    'Stripe webhook secret',
    'Supabase backend secret',
    'Supabase service-role JWT',
  ]) {
    if (!unsafeFindings.includes(expected)) throw new Error(`Client-secret self-test missed ${expected}`);
  }

  const safe = [
    'https://www.askcrump.com',
    'const product = "ask-crump";',
    'const stripePublishableKey = "pk_live_public_value";',
    'const supabasePublishableKey = "sb_publishable_public_value";',
    'const revenueCatPublicSdkKey = "appl_public_value";',
  ].join('\n');
  if (findingsInText(safe).length) throw new Error('Client-secret self-test rejected public configuration.');
}

export {clientRoots, findingsInText, scanClientRoots, selfTest};

if (path.resolve(process.argv[1] || '') === fileURLToPath(import.meta.url)) {
  selfTest();
  const findings = await scanClientRoots();
  if (findings.length) {
    console.error('Privileged credential material detected in client artifacts:');
    for (const finding of findings) console.error(`- ${finding.kind}: ${finding.path}`);
    process.exit(1);
  }
  console.log('Client credential boundary passed: public and native web artifacts contain no privileged key signatures.');
}
