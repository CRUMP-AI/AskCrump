#!/usr/bin/env node
// Regression coverage for the Video Studio delete option.
//
// Greg asked for a way to delete saved videos. The UI offers Delete on each
// finished row of the Recent videos list and on the open player. Deleting
// goes through DELETE /api/media/video/{id}; the backend refuses jobs that
// are still generating. Which rows may offer Delete is decided by the real
// videoJobCanDelete predicate extracted from the production source.

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

const sourcePath = resolve(process.env.PRODUCT53_SOURCE || 'public/crump-product-5.3.js');
const source = readFileSync(sourcePath, 'utf8');

function extractFunction(name) {
  const start = source.indexOf(`function ${name}`);
  if (start < 0) throw new Error(`function ${name} not found`);
  const open = source.indexOf('{', start);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error('unbalanced braces');
}

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(`${extractFunction('videoJobCanDelete')}; this.__can = videoJobCanDelete;`, sandbox);
const canDelete = sandbox.__can;

let passed = 0;
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) {
    console.error(`FAIL: ${name}\n  expected: ${JSON.stringify(expected)}\n  actual:   ${JSON.stringify(actual)}`);
    process.exit(1);
  }
  passed += 1;
}

// Finished jobs can be deleted; in-flight and unknown states cannot.
check('ready is deletable', canDelete({ status: 'ready' }), true);
check('failed is deletable', canDelete({ status: 'failed' }), true);
check('queued is not deletable', canDelete({ status: 'queued' }), false);
check('processing is not deletable', canDelete({ status: 'processing' }), false);
check('unknown status is not deletable', canDelete({ status: 'mystery' }), false);
check('missing job is not deletable', canDelete(null), false);
check('status casing is normalized', canDelete({ status: 'READY' }), true);

// Wiring: the row button, the player button, the delegated listener, the
// confirmation prompt, and the DELETE call must all be present.
check('row renders a delete button', source.includes('data-video-job-delete='), true);
check('player renders a delete button', source.includes('id="crump53DeleteVideo"'), true);
check('a delegated listener handles row deletes',
  source.includes("closest?.('[data-video-job-delete]')"), true);
check('delete asks for confirmation first',
  source.includes("window.confirm('Delete this video?"), true);
check('delete calls the DELETE endpoint',
  source.includes("method: 'DELETE'"), true);
check('deleteVideoJob is defined', source.includes('async function deleteVideoJob(job)'), true);

console.log(`PASS: video-delete (${passed}/${passed})`);
