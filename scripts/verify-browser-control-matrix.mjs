import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {readdir} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {connect} from 'node:net';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const {chromium} = require('playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const scriptsDirectory = path.join(root, 'scripts');
const publicDirectory = path.join(root, 'public');
const expectedVerifiers = Object.freeze([
  'verify-attach-creation-routing.cjs',
  'verify-button-state-integrity.cjs',
  'verify-chat-action-accessibility.cjs',
  'verify-create-destination-handoff.cjs',
  'verify-creation-sheet-containment.cjs',
  'verify-credit-charge-disclosure-browser.cjs',
  'verify-credit-pack-accessibility.cjs',
  'verify-checkout-session-recovery.cjs',
  'verify-code-lazy-load.cjs',
  'verify-cross-device-verification-handoff.cjs',
  'verify-file-delivery.cjs',
  'verify-file-library-usability.cjs',
  'verify-first-action-browser.cjs',
  'verify-image-safety-recovery-browser.cjs',
  'verify-image-scroll-stability.cjs',
  'verify-library-lazy-load.cjs',
  'verify-lifecycle-project-continuity.cjs',
  'verify-lifecycle-referral-recovery.cjs',
  'verify-login-failure-classification.cjs',
  'verify-marketing-landing-browser.cjs',
  'verify-marketing-landing-preload.cjs',
  'verify-mobile-drawer-destinations.cjs',
  'verify-outcome-issue-categories.cjs',
  'verify-paid-plan-intent-delivery.cjs',
  'verify-precision-image-edit.cjs',
  'verify-precision-editor-lazy-load.cjs',
  'verify-presentation-attribution-browser.cjs',
  'verify-project-chat-context-boundary.cjs',
  'verify-project-limit-plan-default-off.cjs',
  'verify-project-limit-plan-delivery.cjs',
  'verify-project-output-action.cjs',
  'verify-project-save-activation.cjs',
  'verify-public-account-entry-buttons.cjs',
  'verify-resume-bullet-guide.cjs',
  'verify-runtime-update-auth-guard.cjs',
  'verify-search-guide-start-paths.cjs',
  'verify-service-worker-returning-load.cjs',
  'verify-settings-profile-trust.cjs',
  'verify-studio-section-isolation.cjs',
  'verify-video-destination.cjs',
  'verify-video-reference-browser.cjs',
  'verify-visual-media-browser.cjs',
  'verify-word-pdf-guide-render.cjs',
  'verify-workspace-runtime-fetch-plan.cjs',
]);

const serverPlan = Object.freeze([
  {port: 4173, directory: publicDirectory},
  {port: 8765, directory: root},
  {port: 8766, directory: publicDirectory},
  {port: 8767, directory: root},
  {port: 8770, directory: publicDirectory},
]);
const pythonExecutable = process.env.ASKCRUMP_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const verifierTimeoutMs = Math.max(30_000, Number(process.env.ASKCRUMP_BROWSER_MATRIX_TIMEOUT_MS || 120_000));

function sorted(values) {
  return [...values].sort((left, right) => left.localeCompare(right));
}

function assertExactInventory(actual) {
  const expected = sorted(expectedVerifiers);
  const observed = sorted(actual);
  if (JSON.stringify(expected) === JSON.stringify(observed)) return;
  const missing = expected.filter(name => !observed.includes(name));
  const unexpected = observed.filter(name => !expected.includes(name));
  throw new Error(`Browser verifier inventory drifted. Missing: ${missing.join(', ') || 'none'}. Unexpected: ${unexpected.join(', ') || 'none'}.`);
}

function portIsListening(port) {
  return new Promise(resolve => {
    const socket = connect({host: '127.0.0.1', port});
    const finish = listening => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(listening);
    };
    socket.setTimeout(500);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
  });
}

async function assertPortsAvailable() {
  const occupied = [];
  for (const {port} of serverPlan) {
    if (await portIsListening(port)) occupied.push(port);
  }
  if (occupied.length) {
    throw new Error(
      `Browser verifier ports are already occupied: ${occupied.join(', ')}. `
      + 'Stop the stale fixture servers before running the fail-closed matrix.',
    );
  }
}

async function waitForServer(port, processHandle) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (processHandle.exitCode !== null) throw new Error(`Static server on ${port} exited with ${processHandle.exitCode}.`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}/`, {signal: AbortSignal.timeout(1_000)});
      if (response.ok) return;
    } catch (_) {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Static server on ${port} did not become ready.`);
}

async function startServers() {
  await assertPortsAvailable();
  const servers = serverPlan.map(({port, directory}) => ({
    port,
    process: spawn(
      pythonExecutable,
      ['-m', 'http.server', String(port), '--bind', '127.0.0.1'],
      {cwd: directory, stdio: 'ignore', windowsHide: true},
    ),
  }));
  try {
    await Promise.all(servers.map(server => waitForServer(server.port, server.process)));
    return servers;
  } catch (error) {
    for (const server of servers) server.process.kill();
    throw error;
  }
}

async function stopServers(servers) {
  await Promise.all(servers.map(({process: processHandle}) => new Promise(resolve => {
    if (processHandle.exitCode !== null || processHandle.signalCode !== null) {
      resolve();
      return;
    }
    processHandle.once('exit', resolve);
    processHandle.kill();
    setTimeout(resolve, 2_000).unref();
  })));
}

function runVerifier(name, environment) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [path.join(scriptsDirectory, name)], {
      cwd: root,
      env: environment,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', chunk => { stdout += chunk; });
    child.stderr.on('data', chunk => { stderr += chunk; });
    const timeout = setTimeout(() => {
      child.kill();
      reject(new Error(`${name} exceeded ${verifierTimeoutMs}ms.`));
    }, verifierTimeoutMs);
    child.on('error', error => {
      clearTimeout(timeout);
      reject(new Error(`${name} could not start: ${error.message}`));
    });
    child.on('exit', code => {
      clearTimeout(timeout);
      if (code === 0) return resolve({name, output: stdout.trim()});
      reject(new Error(`${name} failed with exit ${code}.\n${stderr.trim() || stdout.trim()}`));
    });
  });
}

const discovered = (await readdir(scriptsDirectory))
  .filter(name => /^verify-.*\.cjs$/i.test(name));
assertExactInventory(discovered);

const requestedBrowserExecutable = process.env.ASKCRUMP_BROWSER_EXECUTABLE
  || process.env.ASK_CRUMP_BROWSER_PATH
  || process.env.CODEX_BROWSER_EXECUTABLE
  || '';
const browserExecutable = requestedBrowserExecutable && existsSync(requestedBrowserExecutable)
  ? requestedBrowserExecutable
  : chromium.executablePath();
const environment = {
  ...process.env,
  ASKCRUMP_PLAN_DELAY_RUNS: process.env.ASKCRUMP_PLAN_DELAY_RUNS || '1',
  ASKCRUMP_BROWSER_EXECUTABLE: browserExecutable,
  ASK_CRUMP_BROWSER_PATH: browserExecutable,
  CODEX_BROWSER_EXECUTABLE: browserExecutable,
};

let servers = [];
try {
  servers = await startServers();
  const results = [];
  for (const name of expectedVerifiers) {
    const result = await runVerifier(name, environment);
    results.push(result);
    process.stdout.write(`PASS ${name}\n`);
  }
  process.stdout.write(`Browser control matrix passed ${results.length}/${expectedVerifiers.length} verifiers.\n`);
} finally {
  await stopServers(servers);
}
