const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {chromium} = require('playwright');

const expectedDestinations = ['home', 'chats', 'projects', 'library', 'studios', 'you'];
const legacyDestination = {home: 'ask', projects: 'projects', library: 'library', studios: 'video'};

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
  const geometryViewports = [
    {width: 320, height: 568},
    {width: 375, height: 812},
    {width: 390, height: 844},
    {width: 430, height: 932},
  ];
  const mobileProofs = [];
  for (const viewport of geometryViewports) {
    const proofPage = await browser.newPage({viewport});
    const proofErrors = [];
    proofPage.on('console', message => {
      if (message.type() === 'error') proofErrors.push(message.text());
    });
    proofPage.on('pageerror', error => proofErrors.push(error.message));
    await proofPage.route('**/assets/brand/crump-mark-320.webp', route => route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: readFileSync(join(process.cwd(), 'public', 'assets', 'brand', 'crump-mark.png')),
    }));
    await proofPage.goto(
      'http://127.0.0.1:8765/tests/fixtures/navigation-consolidation.html',
      {waitUntil: 'load'},
    );
    await proofPage.waitForFunction(() => document.documentElement.dataset.crumpNavigation5930 === 'ready');
    const proof = await proofPage.evaluate(() => {
      const workspace = document.querySelector('.v1-workspace');
      const header = document.createElement('header');
      header.className = 'header v1-workspace-header';
      header.innerHTML = `
        <div class="v1-workspace-context"><span>WORKSPACE</span><strong>New conversation</strong></div>
        <button id="crumpActivityTrigger" class="crump-activity-trigger" type="button" aria-label="Activity">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"></circle></svg>
          <span class="crump-activity-trigger-label">Activity</span>
        </button>
        <button id="crumpIntelligenceButton" class="crump44-control-button" type="button" aria-label="Crump intelligence controls">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="12" r="3"></circle><circle cx="16" cy="12" r="3"></circle></svg>
        </button>`;
      workspace.prepend(header);
      const nav = document.getElementById('cvMobileNav');
      const buttons = [...nav.querySelectorAll('[data-cv-destination]')]
        .filter(button => button.getClientRects().length);
      const boxes = buttons.map(button => button.getBoundingClientRect());
      const labels = buttons.map(button => ({
        destination: button.dataset.cvDestination,
        text: button.querySelector('span')?.textContent?.trim(),
        visible: getComputedStyle(button.querySelector('span')).display !== 'none',
      }));
      const you = document.getElementById('cvMobileYou');
      const activity = document.getElementById('crumpActivityTrigger').getBoundingClientRect();
      const intelligence = document.getElementById('crumpIntelligenceButton').getBoundingClientRect();
      const title = header.querySelector('.v1-workspace-context strong').getBoundingClientRect();
      const intersects = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      const result = {
        viewport: {width: innerWidth, height: innerHeight},
        destinations: buttons.map(button => button.dataset.cvDestination),
        labels,
        minimumTouchWidth: Math.floor(Math.min(...boxes.map(box => box.width))),
        minimumTouchHeight: Math.floor(Math.min(...boxes.map(box => box.height))),
        documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        youInsideDock: you?.parentElement === nav,
        duplicateFloatingYou: Boolean(document.querySelector('.cv-mobile-you')),
        activityIntelligenceOverlap: intersects(activity, intelligence),
        titleControlOverlap: intersects(title, activity) || intersects(title, intelligence),
      };
      document.body.classList.add('crump-v1-keyboard-visible');
      result.keyboardHidesDock = getComputedStyle(nav).display === 'none';
      document.body.classList.remove('crump-v1-keyboard-visible');
      return result;
    });
    assert.deepEqual(proof.destinations, expectedDestinations, JSON.stringify(proof));
    assert(proof.labels.every(label => label.visible && label.text), JSON.stringify(proof));
    assert(proof.minimumTouchWidth >= 44, JSON.stringify(proof));
    assert(proof.minimumTouchHeight >= 44, JSON.stringify(proof));
    assert.equal(proof.documentOverflow, 0, JSON.stringify(proof));
    assert.equal(proof.youInsideDock, true, JSON.stringify(proof));
    assert.equal(proof.duplicateFloatingYou, false, JSON.stringify(proof));
    assert.equal(proof.activityIntelligenceOverlap, false, JSON.stringify(proof));
    if (viewport.width >= 375) assert.equal(proof.titleControlOverlap, false, JSON.stringify(proof));
    assert.equal(proof.keyboardHidesDock, true, JSON.stringify(proof));
    assert.deepEqual(proofErrors, [], JSON.stringify(proof));
    mobileProofs.push(proof);
    await proofPage.close();
  }
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
            minimumTouchWidth: Math.floor(box.width),
            minimumTouchHeight: Math.floor(box.height),
            destination: button.dataset.cvDestination,
            parent: button.parentElement?.id,
          };
        })(),
      };
    });
    assert.deepEqual(baseline.visibleDestinations, expectedDestinations);
    assert(baseline.minimumTouchWidth >= 44, JSON.stringify(baseline));
    assert(baseline.minimumTouchHeight >= 44, JSON.stringify(baseline));
    assert.equal(baseline.documentOverflow, 0);
    assert.equal(baseline.navBottom, baseline.viewportHeight);
    assert.equal(baseline.you.visible, true, JSON.stringify(baseline));
    assert(baseline.you.minimumTouchWidth >= 44, JSON.stringify(baseline));
    assert(baseline.you.minimumTouchHeight >= 44, JSON.stringify(baseline));
    assert.equal(baseline.you.destination, 'you');
    assert.equal(baseline.you.parent, 'cvMobileNav');

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

    process.stdout.write(JSON.stringify({mobileProofs, baseline, projects, studios, chats, you, plan, errors}));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
