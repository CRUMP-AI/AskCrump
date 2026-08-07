import { readdir, readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';

const expectedFiles = new Set([
  'account-manager.js', 'app.js', 'auth-controller.js', 'billing-manager.js', 'chat-sync.js',
  'crump-4.3.js', 'crump-4.4.js', 'crump-5.0.js', 'crump-billing-5.1.js', 'crump-5.2.js',
  'device-auth.js', 'install-prompt.js', 'landing.js', 'mobile-bridge.js', 'native-entry.js',
  'native-runtime.js', 'onboarding.js', 'presence-manager.js', 'profile-manager.js',
  'runtime-config.js', 'safe-storage.js', 'scroll-manager.js', 'subscription-ui.js',
  'sw.js', 'sync-manager.js', 'ui-functions.js',
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
console.log(`Validated ${files.length} JavaScript files.`);
