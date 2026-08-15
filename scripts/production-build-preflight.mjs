import { spawnSync } from 'node:child_process';

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: 'inherit',
    shell: false,
    ...options,
  });
  return result;
}

function runJavaScriptContract() {
  const result = run(process.execPath, ['scripts/check-javascript.mjs']);
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function findPython() {
  const candidates = process.platform === 'win32'
    ? [
        ['py', ['-3']],
        ['python', []],
      ]
    : [
        ['python', []],
        ['python3', []],
      ];

  for (const [command, prefix] of candidates) {
    const probe = run(command, [...prefix, '--version'], { stdio: 'ignore' });
    if (probe.status === 0) return [command, prefix];
  }
  return null;
}

function runPythonCompileGuard() {
  const python = findPython();
  const runningOnVercel = Boolean(process.env.VERCEL);

  if (!python) {
    if (runningOnVercel) {
      console.error('Production build guard could not find Python on Vercel.');
      process.exit(1);
    }
    console.warn('Python was not found locally; skipping Python compile guard outside Vercel.');
    return;
  }

  const [command, prefix] = python;
  const result = run(command, [...prefix, '-m', 'compileall', '-q', 'app.py', 'backend']);
  if (result.status !== 0) {
    console.error('Python compile guard failed. Refusing to produce a deployment build.');
    process.exit(result.status ?? 1);
  }
}

runJavaScriptContract();
runPythonCompileGuard();

console.log('Ask Crump production build preflight passed.');
