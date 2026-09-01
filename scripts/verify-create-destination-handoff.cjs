const assert = require('node:assert/strict');
const {chromium} = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:8765';
const executablePath = process.env.CODEX_BROWSER_EXECUTABLE
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

async function verify(browser, viewport) {
  const page = await browser.newPage({viewport});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/assets/brand/crump-mark.png', route => route.fulfill({status: 204, body: ''}));

  await page.goto(`${baseUrl}/tests/fixtures/navigation-consolidation.html`, {waitUntil: 'load'});
  await page.waitForFunction(() => document.documentElement.dataset.crumpNavigation5930 === 'ready');

  const visibleDestination = value => page.locator(
    `[data-crump5930-destination="${value}"]:visible`,
  );

  await visibleDestination('create').click();
  await page.waitForFunction(() => !document.getElementById('crump5930CreateHub')?.hidden);
  await page.waitForFunction(() => document.activeElement?.id === 'crump5930CreateClose');

  const opened = await page.evaluate(() => {
    const box = element => {
      const rect = element.getBoundingClientRect();
      return {
        top: Math.round(rect.top),
        right: Math.round(rect.right),
        bottom: Math.round(rect.bottom),
        left: Math.round(rect.left),
        height: Math.round(rect.height),
        width: Math.round(rect.width),
      };
    };
    const hub = document.getElementById('crump5930CreateHub');
    const app = document.getElementById('appContainer');
    const workspace = document.querySelector('.v1-workspace');
    const sidebar = document.getElementById('sidebar');
    const navigation = window.innerWidth <= 1100
      ? document.getElementById('crump5930MobileNav')
      : document.querySelector('.crump5930-rail');
    const createButton = [...document.querySelectorAll('[data-crump5930-destination="create"]')]
      .find(button => button.getClientRects().length);
    return {
      ariaModal: hub.querySelector('[role="dialog"]')?.getAttribute('aria-modal'),
      focus: document.activeElement?.id,
      appInert: app.hasAttribute('inert'),
      appAriaHidden: app.getAttribute('aria-hidden'),
      workspaceInert: workspace.hasAttribute('inert'),
      workspaceAriaHidden: workspace.getAttribute('aria-hidden'),
      sidebarInert: sidebar.hasAttribute('inert'),
      destinationInsideInert: Boolean(createButton.closest('[inert]')),
      overlay: box(hub),
      navigation: box(navigation),
    };
  });

  assert.equal(opened.ariaModal, 'false');
  assert.equal(opened.focus, 'crump5930CreateClose');
  assert.equal(opened.appInert, false);
  assert.equal(opened.appAriaHidden, null);
  assert.equal(opened.workspaceInert, true);
  assert.equal(opened.workspaceAriaHidden, 'true');
  assert.equal(opened.sidebarInert, true, JSON.stringify(opened));
  assert.equal(opened.destinationInsideInert, false);
  if (viewport.width <= 1100) {
    assert(Math.abs(opened.overlay.bottom - opened.navigation.top) <= 1);
    assert(opened.navigation.height >= 58);
  } else {
    assert(Math.abs(opened.overlay.left - opened.navigation.right) <= 1);
    assert(opened.navigation.width >= 90);
  }

  await visibleDestination('video').click();
  await page.waitForFunction(() => (
    document.getElementById('crump5930CreateHub')?.hidden
    && !document.getElementById('crump53Studio')?.hidden
    && document.getElementById('crump53Sheet')?.dataset.crump53Section === 'video'
  ));
  await page.waitForFunction(() => document.activeElement?.id === 'crump53WorkspaceTitle');
  const switched = await page.evaluate(() => ({
    createHidden: document.getElementById('crump5930CreateHub').hidden,
    studioOpen: !document.getElementById('crump53Studio').hidden,
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    active: document.querySelector('[data-crump5930-destination].is-active')?.dataset.crump5930Destination,
    focus: document.activeElement?.id,
  }));
  assert.deepEqual(switched, {
    createHidden: true,
    studioOpen: true,
    section: 'video',
    active: 'video',
    focus: 'crump53WorkspaceTitle',
  });

  await visibleDestination('ask').click();
  await page.waitForFunction(() => document.getElementById('crump53Studio')?.hidden);
  const returned = await page.evaluate(() => ({
    studioHidden: document.getElementById('crump53Studio').hidden,
    workspaceInert: document.querySelector('.v1-workspace').hasAttribute('inert'),
    active: document.querySelector('[data-crump5930-destination].is-active')?.dataset.crump5930Destination,
  }));
  assert.deepEqual(returned, {studioHidden: true, workspaceInert: false, active: 'ask'});
  assert.deepEqual(errors, []);
  await page.close();
  return {viewport, opened, switched, returned, errors};
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath});
  try {
    const desktop = await verify(browser, {width: 1280, height: 720});
    const mobile = await verify(browser, {width: 390, height: 844});
    process.stdout.write(JSON.stringify({desktop, mobile}));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
