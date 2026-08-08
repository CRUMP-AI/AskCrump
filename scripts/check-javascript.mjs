import { access, readdir, readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';

const expectedFiles = new Set([
  'account-manager.js', 'app.js', 'auth-controller.js', 'billing-manager.js', 'chat-sync.js',
  'crump-4.3.js', 'crump-4.4.js', 'crump-5.0.js', 'crump-billing-5.1.js',
  'crump-5.2.js', 'crump-5.2.2.js', 'crump-5.2.4.js', 'crump-v1.js',
  'device-auth.js', 'install-prompt.js', 'landing.js', 'mobile-bridge.js', 'native-entry.js',
  'native-runtime.js', 'onboarding.js', 'presence-manager.js', 'profile-manager.js',
  'runtime-config.js', 'runtime-config-v1.js', 'safe-storage.js', 'scroll-manager.js',
  'subscription-ui.js', 'sw.js', 'sync-manager.js', 'ui-functions.js',
]);

const publicDirectory = new URL('../public/', import.meta.url);
const files = (await readdir(publicDirectory)).filter(name => name.endsWith('.js')).sort();

const unexpected = files.filter(name => !expectedFiles.has(name));
const missing = [...expectedFiles].filter(name => !files.includes(name));

if (unexpected.length || missing.length) {
  if (unexpected.length) console.error(`Unexpected JavaScript files: ${unexpected.join(', ')}`);
  if (missing.length) console.error(`Missing JavaScript files: ${missing.join(', ')}`);
  process.exit(1);
}

for (const name of files) {
  const path = new URL(name, publicDirectory);
  const source = await readFile(path, 'utf8');

  if (/console\.(log|debug|info)\s*\(/.test(source)) {
    console.error(`${name} contains a development console statement.`);
    process.exit(1);
  }

  const result = spawnSync(process.execPath, ['--check', path.pathname], { stdio: 'inherit' });
  if (result.status !== 0) process.exit(result.status ?? 1);
}



const repoRoot = new URL('../', import.meta.url);
const requiredV1Files = [
  'public/crump-v1.css',
  'public/crump-v1.js',
  'public/runtime-config-v1.js',
  'public/assets/brand/crump-mark.png',
  'public/assets/brand/crump-horizontal-light.png',
  'public/assets/brand/crump-horizontal-dark.png',
  'public/assets/brand/crump-mark-master.png',
  'public/assets/brand/crump-horizontal-light-master.png',
  'public/assets/brand/crump-horizontal-dark-master.png',
];

for (const relative of requiredV1Files) {
  try {
    await access(new URL(relative, repoRoot));
  } catch (_) {
    console.error(`Missing Ask Crump V1 file: ${relative}`);
    process.exit(1);
  }
}

const appHtml = await readFile(new URL('public/app.html', repoRoot), 'utf8');
const requiredHtmlSignals = [
  '/runtime-config-v1.js',
  '/crump-v1.css',
  'class="crump-v1"',
  '/assets/brand/crump-horizontal-light.png',
];

for (const signal of requiredHtmlSignals) {
  if (!appHtml.includes(signal)) {
    console.error(`Ask Crump V1 app.html integration is incomplete: missing ${signal}`);
    process.exit(1);
  }
}

if (appHtml.includes('fonts.googleapis.com') || appHtml.includes('fonts.gstatic.com')) {
  console.error('Ask Crump V1 should not depend on external Google Fonts in the application shell.');
  process.exit(1);
}

const runtimeV1 = await readFile(new URL('public/runtime-config-v1.js', repoRoot), 'utf8');
if (!runtimeV1.includes('/crump-v1.js') || !runtimeV1.includes('/crump-v1.css')) {
  console.error('Ask Crump V1 runtime is missing the canonical V1 shell.');
  process.exit(1);
}
if (runtimeV1.includes('/crump-5.2.4.js') || runtimeV1.includes('/crump-5.2.4.css')) {
  console.error('Retired 5.2.4 branding must not load inside the V1 runtime.');
  process.exit(1);
}

const serviceWorker = await readFile(new URL('public/sw.js', repoRoot), 'utf8');
if (!serviceWorker.includes('ask-crump-v1-shell-r1') ||
    !serviceWorker.includes('/runtime-config-v1.js') ||
    !serviceWorker.includes('/crump-v1.js')) {
  console.error('Ask Crump V1 service-worker boot contract is incomplete.');
  process.exit(1);
}

console.log('Ask Crump V1 integration contract validated.');

console.log(`Validated ${files.length} JavaScript files.`);
