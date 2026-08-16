import { access } from 'node:fs/promises';
import { constants } from 'node:fs';
import { spawnSync } from 'node:child_process';

const root = new URL('../', import.meta.url);
const platform = String(process.argv[2] || '').toLowerCase();

if (!['android', 'ios'].includes(platform)) {
  console.error('Usage: node scripts/prepare-store-release.mjs <android|ios>');
  process.exit(1);
}
if (platform === 'ios' && process.platform === 'win32') {
  console.error('iOS preparation requires macOS because CocoaPods/Xcode must resolve the native project.');
  process.exit(1);
}

const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';

async function exists(url) {
  try { await access(url, constants.F_OK); return true; } catch { return false; }
}

function run(command, args) {
  console.log(`\n> ${command} ${args.join(' ')}`);
  const result = spawnSync(command, args, {
    cwd: root,
    env: process.env,
    stdio: 'inherit',
    shell: false,
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

run(npm, ['run', 'build']);

if (!(await exists(new URL(`${platform}/`, root)))) {
  run(npx, ['cap', 'add', platform]);
}

run(npx, ['cap', 'sync', platform]);
run(npx, [
  '--yes', '@capacitor/assets@3.0.5', 'generate',
  '--iconBackgroundColor', '#0f1419',
  '--iconBackgroundColorDark', '#0f1419',
  '--splashBackgroundColor', '#0f1419',
  '--splashBackgroundColorDark', '#0f1419',
]);
run(process.execPath, ['scripts/configure-native.mjs', platform]);
run(process.execPath, ['scripts/verify-native-release.mjs', platform]);

console.log(`\nAsk Crump ${platform} release source is prepared and verified.`);
console.log('Signing credentials, store products, physical-device testing, and final upload remain owner-controlled release gates.');
