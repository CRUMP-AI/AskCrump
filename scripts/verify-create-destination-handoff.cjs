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
  await page.route('**/assets/brand/crump-mark-320.webp', route => route.fulfill({status: 204, body: ''}));

  await page.goto(`${baseUrl}/tests/fixtures/navigation-consolidation.html`, {waitUntil: 'load'});
  await page.waitForFunction(() => document.documentElement.dataset.crumpNavigation5930 === 'ready');

  const visibleDestination = value => page.locator(
    `[data-cv-destination="${value}"]:visible`,
  ).first();

  await page.evaluate(() => window.CrumpNavigation5930.open('create'));
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
      ? document.getElementById('cvMobileNav')
      : document.querySelector('.cv-rail');
    const createButton = window.innerWidth <= 1100
      ? document.querySelector('#cvMobileNav [data-cv-destination="ask"]')
      : document.querySelector('.cv-rail [data-cv-new-conversation]');
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
    assert(opened.navigation.width >= 240);
  }

  await visibleDestination('video').click();
  await page.waitForFunction(() => (
    document.getElementById('crump5930CreateHub')?.hidden
    && !document.getElementById('crump53Studio')?.hidden
    && document.getElementById('crump53Sheet')?.dataset.crump53Section === 'video'
  ));
  await page.waitForFunction(() => document.activeElement?.id === 'crump53WorkspaceTitle');
  const switched = await page.evaluate(() => {
    const studio = document.getElementById('crump53Studio').getBoundingClientRect();
    const nav = document.getElementById('cvMobileNav')?.getBoundingClientRect();
    return {
      createHidden: document.getElementById('crump5930CreateHub').hidden,
      studioOpen: !document.getElementById('crump53Studio').hidden,
      section: document.getElementById('crump53Sheet').dataset.crump53Section,
      active: document.querySelector('[data-cv-destination].is-active')?.dataset.cvDestination,
      focus: document.activeElement?.id,
      studioBottom: Math.round(studio.bottom),
      navTop: nav ? Math.round(nav.top) : null,
    };
  });
  assert.deepEqual({
    createHidden: switched.createHidden,
    studioOpen: switched.studioOpen,
    section: switched.section,
    active: switched.active,
    focus: switched.focus,
  }, {
    createHidden: true,
    studioOpen: true,
    section: 'video',
    active: 'video',
    focus: 'crump53WorkspaceTitle',
  });
  if (viewport.width <= 1100) {
    assert(Math.abs(switched.studioBottom - switched.navTop) <= 1, JSON.stringify(switched));
  }

  // Product workspaces stop above the persistent mobile navigation, so the
  // visible Ask destination remains a direct, reliable way home.
  await visibleDestination('ask').click();
  await page.waitForFunction(() => document.getElementById('crump53Studio')?.hidden);
  const returned = await page.evaluate(() => ({
    studioHidden: document.getElementById('crump53Studio').hidden,
    workspaceInert: document.querySelector('.v1-workspace').hasAttribute('inert'),
    active: document.querySelector('[data-cv-destination].is-active')?.dataset.cvDestination,
  }));
  assert.deepEqual(returned, {studioHidden: true, workspaceInert: false, active: 'ask'});

  let desktopRail = null;
  if (viewport.width > 1100) {
    const drawerToggle = page.locator('.cv-rail [data-cv-drawer-toggle]');
    await drawerToggle.click();
    await page.waitForFunction(() => (
      document.body.classList.contains('cv-conversations-open')
      && document.querySelector('.cv-rail [data-cv-drawer-toggle]')?.getAttribute('aria-expanded') === 'true'
    ));
    const openedDrawer = await page.evaluate(() => ({
      open: document.body.classList.contains('cv-conversations-open'),
      expanded: document.querySelector('.cv-rail [data-cv-drawer-toggle]')?.getAttribute('aria-expanded'),
      sidebarHidden: document.getElementById('sidebar')?.getAttribute('aria-hidden'),
      sidebarInert: document.getElementById('sidebar')?.hasAttribute('inert'),
    }));
    assert.deepEqual(openedDrawer, {
      open: true,
      expanded: 'true',
      sidebarHidden: 'false',
      sidebarInert: false,
    });

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => (
      !document.body.classList.contains('cv-conversations-open')
      && document.querySelector('.cv-rail [data-cv-drawer-toggle]')?.getAttribute('aria-expanded') === 'false'
    ));
    const closedDrawer = await page.evaluate(() => ({
      open: document.body.classList.contains('cv-conversations-open'),
      expanded: document.querySelector('.cv-rail [data-cv-drawer-toggle]')?.getAttribute('aria-expanded'),
      focus: document.activeElement?.hasAttribute('data-cv-drawer-toggle') || false,
    }));
    assert.deepEqual(closedDrawer, {open: false, expanded: 'false', focus: true});

    await page.locator('.cv-rail [data-cv-new-conversation]').click();
    await page.waitForFunction(() => window.fixtureEvents.newConversation === 1);
    await page.waitForFunction(() => document.activeElement?.id === 'userInput');
    const newConversation = await page.evaluate(() => ({
      count: window.fixtureEvents.newConversation,
      result: document.getElementById('result')?.textContent,
      focus: document.activeElement?.id,
    }));
    assert.deepEqual(newConversation, {count: 1, result: 'new=1', focus: 'userInput'});
    desktopRail = {openedDrawer, closedDrawer, newConversation};
  }
  assert.deepEqual(errors, []);
  await page.close();
  return {viewport, opened, switched, returned, desktopRail, errors};
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
