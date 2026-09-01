const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));

  await page.goto(
    'http://127.0.0.1:8765/tests/fixtures/navigation-consolidation.html?mobile=drawer',
    {waitUntil: 'load'},
  );
  await page.waitForFunction(() => (
    document.documentElement.dataset.crumpNavigation5930 === 'ready'
    && document.getElementById('sidebar')?.classList.contains('active')
    && document.getElementById('sidebarOverlay')?.classList.contains('active')
  ));

  const geometry = await page.evaluate(() => {
    const box = id => {
      const rect = document.getElementById(id).getBoundingClientRect();
      return {top: Math.round(rect.top), bottom: Math.round(rect.bottom), height: Math.round(rect.height)};
    };
    return {
      drawer: box('sidebar'),
      overlay: box('sidebarOverlay'),
      navigation: box('crump5930MobileNav'),
    };
  });
  assert(Math.abs(geometry.drawer.bottom - geometry.navigation.top) <= 1);
  assert(Math.abs(geometry.overlay.bottom - geometry.navigation.top) <= 1);
  assert(geometry.navigation.height >= 58);

  await page.locator('#crump5930MobileNav [data-crump5930-destination="projects"]').click();
  const projects = await page.evaluate(() => ({
    drawerOpen: document.getElementById('sidebar').classList.contains('active'),
    overlayOpen: document.getElementById('sidebarOverlay').classList.contains('active'),
    studioOpen: !document.getElementById('crump53Studio').hidden,
    section: document.getElementById('crump53Sheet').dataset.crump53Section,
  }));
  assert.deepEqual(projects, {
    drawerOpen: false,
    overlayOpen: false,
    studioOpen: true,
    section: 'projects',
  });

  assert.deepEqual(errors, []);

  await browser.close();
  process.stdout.write(JSON.stringify({geometry, projects, errors}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
