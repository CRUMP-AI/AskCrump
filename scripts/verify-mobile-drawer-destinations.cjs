const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {chromium} = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/assets/brand/crump-mark-320.webp', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: readFileSync(join(process.cwd(), 'public', 'assets', 'brand', 'crump-mark.png')),
  }));

  await page.goto(
    'http://127.0.0.1:8765/tests/fixtures/navigation-consolidation.html?mobile=drawer',
    {waitUntil: 'load'},
  );
  await page.waitForFunction(() => (
    document.documentElement.dataset.crumpNavigation5930 === 'ready'
    && document.getElementById('sidebar')?.classList.contains('active')
    && document.getElementById('sidebarOverlay')?.classList.contains('active')
    && document.getElementById('cvMobileNav')
  ));

  const geometry = await page.evaluate(() => {
    const box = id => {
      const rect = document.getElementById(id).getBoundingClientRect();
      return {top: Math.round(rect.top), bottom: Math.round(rect.bottom), height: Math.round(rect.height)};
    };
    return {
      drawer: box('sidebar'),
      overlay: box('sidebarOverlay'),
      navigation: box('cvMobileNav'),
    };
  });
  assert.equal(geometry.drawer.bottom, geometry.navigation.top);
  assert.equal(geometry.overlay.bottom, geometry.navigation.top);
  assert.equal(geometry.navigation.bottom, 844);
  assert(geometry.navigation.height >= 58);
  assert.equal(await page.locator('#menuBtn').isHidden(), true, 'legacy mobile Chats control must be replaced by the five-tab shell');

  // The Atelier shell no longer renders a duplicate close control inside the
  // legacy conversation list.  Compact drawers close through the shell's
  // universal Escape/backdrop interaction instead.
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.getElementById('sidebar')?.classList.contains('active'));
  await page.evaluate(() => { window.fixtureEvents.analytics = []; });
  await page.locator('#cvMobileNav [data-cv-destination="chats"]').click();
  await page.waitForFunction(() => document.getElementById('sidebar')?.classList.contains('active'));
  const chatsAnalytics = await page.evaluate(() => window.fixtureEvents.analytics);
  assert.deepEqual(chatsAnalytics, [{
    eventName: 'NavigationDestinationSelected',
    eventKey: 'navigation-destination-selected',
    source: 'chats',
  }]);
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.getElementById('sidebar')?.classList.contains('active'));
  await page.evaluate(() => { window.fixtureEvents.analytics = []; });
  await page.locator('#cvMobileNav [data-cv-destination="projects"]').click();
  const projects = await page.evaluate(() => ({
    drawerOpen: document.getElementById('sidebar').classList.contains('active'),
    overlayOpen: document.getElementById('sidebarOverlay').classList.contains('active'),
    studioOpen: !document.getElementById('crump53Studio').hidden,
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
    analytics: window.fixtureEvents.analytics,
  }));
  assert.deepEqual(projects, {
    drawerOpen: false,
    overlayOpen: false,
    studioOpen: true,
    section: 'projects',
    analytics: [{
      eventName: 'NavigationDestinationSelected',
      eventKey: 'navigation-destination-selected',
      source: 'projects',
    }],
  });

  await page.evaluate(() => {
    window.CrumpVision.registerView('projects', {
      render(host) {
        host.innerHTML = '<section id="cvDrawerReturnProbe">Projects return probe</section>';
      },
    });
    window.fixtureEvents.analytics = [];
  });
  await page.evaluate(() => { window.fixtureEvents.analytics = []; });
  await page.locator('#cvMobileNav [data-cv-destination="chats"]').click();
  await page.waitForFunction(() => document.getElementById('sidebar')?.classList.contains('active'));
  const chatsFromProjects = await page.evaluate(() => ({
    analytics: window.fixtureEvents.analytics,
    projectSurfaceHidden: document.getElementById('crump53Studio').hidden,
    projectStageHidden: document.getElementById('cvStage').hidden,
  }));
  assert.deepEqual(chatsFromProjects, {
    analytics: [{
      eventName: 'NavigationDestinationSelected',
      eventKey: 'navigation-destination-selected',
      source: 'chats',
    }],
    projectSurfaceHidden: true,
    projectStageHidden: true,
  });

  await page.keyboard.press('Escape');
  await page.waitForFunction(() => (
    !document.getElementById('sidebar')?.classList.contains('active')
    && window.CrumpVision.current() === 'projects'
    && document.getElementById('cvStage')?.hidden === false
  ));
  const restoredFromChats = await page.evaluate(() => ({
    current: window.CrumpVision.current(),
    projectStageHidden: document.getElementById('cvStage').hidden,
    projectContentRestored: Boolean(document.getElementById('cvDrawerReturnProbe')),
    projectsActive: document.querySelector('#cvMobileNav [data-cv-destination="projects"]')?.getAttribute('aria-current'),
    analytics: window.fixtureEvents.analytics,
  }));
  assert.deepEqual(restoredFromChats, {
    current: 'projects',
    projectStageHidden: false,
    projectContentRestored: true,
    projectsActive: 'page',
    analytics: [{
      eventName: 'NavigationDestinationSelected',
      eventKey: 'navigation-destination-selected',
      source: 'chats',
    }],
  });

  assert.deepEqual(errors, []);

  await browser.close();
  process.stdout.write(JSON.stringify({geometry, chatsAnalytics, projects, chatsFromProjects, restoredFromChats, errors}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
