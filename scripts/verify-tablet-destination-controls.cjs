const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {chromium} = require('playwright');

const expectedDestinations = ['home', 'chats', 'projects', 'library', 'studios'];
const legacyDestination = {home: 'ask', projects: 'projects', library: 'library', studios: 'video'};

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
  const page = await browser.newPage({viewport: {width: 1024, height: 1366}});
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/assets/brand/crump-mark-320.webp', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: readFileSync(join(process.cwd(), 'public', 'assets', 'brand', 'crump-mark.png')),
  }));

  try {
    await page.goto(
      'http://127.0.0.1:8765/tests/fixtures/navigation-consolidation.html',
      {waitUntil: 'load'},
    );
    await page.waitForFunction(() => document.documentElement.dataset.crumpNavigation5930 === 'ready');

    const destination = name => page.locator(
      `#cvMobileNav [data-cv-destination="${name}"]`,
    );
    const clickDestination = async name => {
      await destination(name).click();
      if (legacyDestination[name]) {
        await page.waitForFunction(
          expected => document.documentElement.dataset.crumpNavigationDestination === expected,
          legacyDestination[name],
        );
      }
      assert.equal(await destination(name).getAttribute('aria-current'), 'page');
    };
    const surfaceGeometry = async selector => page.locator(selector).evaluate(element => {
      const rect = element.getBoundingClientRect();
      const nav = document.getElementById('cvMobileNav').getBoundingClientRect();
      return {
        top: Math.round(rect.top),
        right: Math.round(rect.right),
        bottom: Math.round(rect.bottom),
        left: Math.round(rect.left),
        navTop: Math.round(nav.top),
      };
    });

    const baseline = await page.evaluate(() => {
      const nav = document.getElementById('cvMobileNav');
      const buttons = [...nav.querySelectorAll('[data-cv-destination]')]
        .filter(button => button.getClientRects().length);
      const boxes = buttons.map(button => button.getBoundingClientRect());
      return {
        visibleDestinations: buttons.map(button => button.dataset.cvDestination),
        minimumTouchWidth: Math.floor(Math.min(...boxes.map(box => box.width))),
        minimumTouchHeight: Math.floor(Math.min(...boxes.map(box => box.height))),
        documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        navBottom: Math.round(nav.getBoundingClientRect().bottom),
        viewportHeight: window.innerHeight,
        you: (() => {
          const button = document.getElementById('cvMobileYou');
          const box = button.getBoundingClientRect();
          return {
            visible: Boolean(button.getClientRects().length),
            width: Math.floor(box.width),
            height: Math.floor(box.height),
            destination: button.dataset.cvDestination,
          };
        })(),
      };
    });
    assert.deepEqual(baseline.visibleDestinations, expectedDestinations);
    assert(baseline.minimumTouchWidth >= 44, JSON.stringify(baseline));
    assert(baseline.minimumTouchHeight >= 44, JSON.stringify(baseline));
    assert.equal(baseline.documentOverflow, 0);
    assert.equal(baseline.navBottom, baseline.viewportHeight);
    assert.deepEqual(baseline.you, {visible: true, width: 44, height: 44, destination: 'you'});

    await clickDestination('projects');
    await page.waitForFunction(() => (
      !document.getElementById('crump53Studio')?.hidden
      && document.getElementById('crump53Sheet')?.dataset.crump53Section === 'projects'
    ));
    const projects = await surfaceGeometry('#crump53Studio');
    assert.equal(projects.bottom, projects.navTop, JSON.stringify(projects));
    await page.locator('#crump53Close').click();

    await clickDestination('library');
    await page.waitForFunction(() => document.getElementById('crump53Sheet')?.dataset.crump53Section === 'library');
    assert.equal(await page.locator('#crump53WorkspaceTitle').textContent(), 'Library');
    await page.locator('#crump53Close').click();

    await clickDestination('studios');
    await page.waitForFunction(() => document.getElementById('crump53Sheet')?.dataset.crump53Section === 'video');
    assert.equal(await page.locator('#crump53WorkspaceTitle').textContent(), 'Video Studio');
    const studios = await surfaceGeometry('#crump53Studio');
    assert.equal(studios.bottom, studios.navTop, JSON.stringify(studios));
    await page.locator('#crump53Close').click();

    await clickDestination('chats');
    await page.waitForFunction(() => document.getElementById('sidebar')?.classList.contains('active'));
    await page.waitForFunction(() => document.activeElement?.id === 'newChatBtn');
    assert.equal(await page.locator('#newChatBtn').evaluate(element => document.activeElement === element), true);
    const chats = await surfaceGeometry('#sidebar');
    assert.equal(chats.bottom, chats.navTop, JSON.stringify(chats));
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.getElementById('sidebar')?.classList.contains('active'));
    await page.waitForFunction(() => document.activeElement?.dataset.cvDestination === 'chats');
    assert.equal(await destination('chats').evaluate(element => document.activeElement === element), true);

    await page.locator('#cvMobileYou').click();
    await page.waitForFunction(() => {
      const settings = document.getElementById('settingsModal');
      return settings?.style.display && settings.style.display !== 'none';
    });
    const you = await surfaceGeometry('#settingsModal');
    assert.equal(you.bottom, you.navTop, JSON.stringify(you));
    await page.waitForFunction(() => document.activeElement?.id === 'settingsTitle');

    await page.locator('#closeSettingsBtn').click();
    await clickDestination('home');
    await page.waitForFunction(() => (
      document.getElementById('crump53Studio')?.hidden
      && document.getElementById('crump5930CreateHub')?.hidden
      && document.getElementById('settingsModal')?.style.display === 'none'
    ));
    await page.waitForFunction(() => document.activeElement?.id === 'userInput');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'userInput');

    await page.locator('#cvMobileYou').click();
    await page.locator('[data-v1-settings-tab="plan"]').click();
    await page.locator('#v1OpenPlanBtn').click();
    await page.waitForFunction(() => window.fixtureEvents.billing === 1);
    const plan = await page.evaluate(() => ({
      billing: window.fixtureEvents.billing,
      proofDisplay: getComputedStyle(document.getElementById('billingProof')).display,
      result: document.getElementById('result').textContent,
      fixtureErrorCount: document.documentElement.dataset.fixtureErrorCount,
    }));
    assert.deepEqual(plan, {
      billing: 1,
      proofDisplay: 'grid',
      result: 'billing=1',
      fixtureErrorCount: '0',
    });
    assert.deepEqual(errors, []);

    process.stdout.write(JSON.stringify({baseline, projects, studios, chats, you, plan, errors}));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
