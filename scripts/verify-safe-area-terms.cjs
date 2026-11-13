// Safe-area terms guard: the v2 shell shipped headers under the iPhone
// status bar / Dynamic Island and a dock that chased host inset variance,
// because the scroll-surface roots carried fixed top padding with no
// safe-area-inset-top term. Headless fixtures evaluate env() to zero, so
// they cannot see the defect; this verifier proves the fix terms are
// present in the shipped CSS bytes. It guards against missing-term
// regressions only — it does NOT establish real-device behavior, which
// only physical-iPhone captures can close.
const {readFileSync} = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
// ASKCRUMP_SAFE_AREA_PUBLIC exists only so the guard can be run against a
// pristine copy of public/ to prove it fails when the terms are absent.
const publicDirectory = process.env.ASKCRUMP_SAFE_AREA_PUBLIC
  || path.join(root, 'public');

const read = (name) => readFileSync(path.join(publicDirectory, name), 'utf8');

function ruleBody(source, selector, fromIndex = 0) {
  const start = source.indexOf(selector, fromIndex);
  if (start === -1) return null;
  const open = source.indexOf('{', start);
  if (open === -1) return null;
  const close = source.indexOf('}', open);
  if (close === -1) return null;
  return source.slice(open + 1, close);
}

function mediaBlock(source, query) {
  const start = source.indexOf(query);
  if (start === -1) return null;
  const open = source.indexOf('{', start);
  if (open === -1) return null;
  let depth = 1;
  for (let i = open + 1; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(open + 1, i);
    }
  }
  return null;
}

const failures = [];
let checkCount = 0;
const check = (label, present) => {
  checkCount += 1;
  if (!present) failures.push(label);
};

const shell = read('crump-vision-shell-1.0.css');
const projects = read('crump-vision-projects-1.0.css');
const library = read('crump-vision-library-1.0.css');
const studios = read('crump-vision-studios-1.0.css');
const you = read('crump-vision-you-1.0.css');
const today = read('crump-agent-today-1.0.css');
const body = read('crump-v1-body.css');

// Shell stage view: base + 680px roots carry the top inset; bottoms stay.
check('shell .cv-view base top inset', (ruleBody(shell, '.cv-view {') || '')
  .includes('padding: calc(70px + env(safe-area-inset-top, 0px)) 36px 140px;'));
check('shell .cv-view 680px top inset', (mediaBlock(shell, '@media (max-width: 680px)') || '')
  .includes('.cv-view { padding: calc(34px + env(safe-area-inset-top, 0px)) 16px 162px; }'));

// Dock: bottom is clamped so host inset inflation cannot lift the pill
// off the bottom; the 63px dock + 5px float = 68px clearance contract.
const dock = ruleBody(shell, 'html[data-cv-shell="ready"] body.crump-v1-body .cv-mobile-nav {') || '';
check('dock bottom clamp', dock.includes('bottom: clamp(5px, calc(env(safe-area-inset-bottom) + 5px), 44px);'));
check('dock 63px height (68px clearance contract)', dock.includes('height: 63px;'));

// Projects / Library roots: base + 900px rules AND their doubled-selector
// workspace-shell mirrors, which win the cascade in production.
for (const [label, source, selector] of [
  ['projects', projects, '.cvp-root'],
  ['library', library, '.cvl-root'],
]) {
  const mirror = `body.crump-v1-body ${selector}.${selector.slice(1)}`;
  check(`${label} root base top inset`, (ruleBody(source, `${selector} {`) || '')
    .includes(`padding: calc(48px + env(safe-area-inset-top, 0px)) 36px calc(96px + env(safe-area-inset-bottom, 0px));`));
  check(`${label} root 900px top inset`, (mediaBlock(source, '@media (max-width: 900px)') || '')
    .includes(`${selector} { padding: calc(32px + env(safe-area-inset-top, 0px)) 20px calc(64px + env(safe-area-inset-bottom, 0px)); }`));
  check(`${label} root shell-mirror base top inset`, (ruleBody(source, mirror) || '')
    .includes(`padding: calc(48px + env(safe-area-inset-top, 0px)) 36px calc(96px + env(safe-area-inset-bottom, 0px));`));
  const responsiveMirrors = source.slice(source.indexOf('Workspace shell responsive mirrors'));
  check(`${label} root shell-mirror 900px top inset`, (mediaBlock(responsiveMirrors, '@media (max-width: 900px)') || '')
    .includes(`${mirror} { padding: calc(32px + env(safe-area-inset-top, 0px)) 20px calc(64px + env(safe-area-inset-bottom, 0px)); }`));
}

// Studios root: base + 640px; bottom values carry no inset term by design.
check('studios .cv-view base top inset', (ruleBody(studios, '.cv-view {') || '')
  .includes('padding: calc(48px + env(safe-area-inset-top, 0px)) 32px 96px;'));
check('studios .cv-view 640px top inset', (mediaBlock(studios, '@media (max-width: 640px)') || '')
  .includes('padding: calc(32px + env(safe-area-inset-top, 0px)) 18px 80px;'));

// You root: base + 640px.
check('you .cv-you base top inset', (ruleBody(you, '.cv-you {') || '')
  .includes('padding: calc(36px + env(safe-area-inset-top, 0px)) 24px 64px;'));
check('you .cv-you 640px top inset', (mediaBlock(you, '@media (max-width: 640px)') || '')
  .includes('padding: calc(28px + env(safe-area-inset-top, 0px)) 20px 56px;'));

// Tasks drawer head clears the island; at dock widths the drawer and its
// overlay stop at the dock's top edge so navigation stays reachable.
check('tasks drawer head top inset', (ruleBody(today, '.cat-drawer-head {') || '')
  .includes('padding: calc(18px + env(safe-area-inset-top, 0px)) 20px 14px;'));
const drawerStrip = mediaBlock(today, '@media (max-width: 1100px)') || '';
check('tasks drawer bottom offset at <=1100px', drawerStrip
  .includes('.cat-drawer { bottom: calc(var(--cv-mobile-nav, 68px) + env(safe-area-inset-bottom, 0px)); }'));
check('tasks overlay bottom offset at <=1100px', drawerStrip
  .includes('.cat-overlay { bottom: calc(var(--cv-mobile-nav, 68px) + env(safe-area-inset-bottom, 0px)); }'));

// Settings header: the 820px rule adds the top inset on top of the 12px
// design padding, at the base rule's !important weight.
check('settings header base design padding preserved', (ruleBody(body, 'body.crump-v1-body .v1-settings-header {') || '')
  .includes('padding: 12px 15px !important;'));
const settingsMobile = mediaBlock(body, '@media (max-width: 820px)') || '';
check('settings header 820px top inset', (ruleBody(settingsMobile, 'body.crump-v1-body .v1-settings-header {') || '')
  .includes('padding-top: calc(12px + env(safe-area-inset-top, 0px)) !important;'));

if (failures.length) {
  throw new Error(JSON.stringify({missingSafeAreaTerms: failures}));
}
process.stdout.write(`${JSON.stringify({safeAreaTerms: 'present', checks: checkCount})}\n`);
