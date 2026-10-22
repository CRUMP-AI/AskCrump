const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8767';
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const root = path.resolve(__dirname, '..');

function watch(page) {
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));
  return errors;
}

async function composerActions(browser) {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = watch(page);
  const apiRequests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url());
  });
  await page.goto(`${fixtureOrigin}/tests/fixtures/composer-mode-handoff.html`, {
    waitUntil: 'domcontentloaded',
  });
  await page.waitForFunction(() => document.documentElement.dataset.crump43Booted === 'true');

  const think = page.getByRole('button', {name: 'Think with Crump', exact: true});
  const research = page.getByRole('button', {name: 'Research something', exact: true});
  const documentEntry = page.getByRole('button', {name: 'Create a document', exact: true});
  const file = page.getByRole('button', {name: 'Analyze a file', exact: true});
  const image = page.getByRole('button', {name: 'Create an image', exact: true});

  const preservedDraft = 'Keep this composer draft exactly as written.';
  await page.locator('#userInput').fill(preservedDraft);
  await documentEntry.focus();
  await page.keyboard.press('Enter');
  await page.evaluate(() => new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }));
  assert.equal(await page.evaluate(() => window.__documentStudioOpens), 1);
  assert.equal(await page.locator('#userInput').inputValue(), preservedDraft);
  assert.deepEqual(apiRequests, []);
  assert.equal(await page.evaluate(() => window.__sendClicks), 0);
  assert.deepEqual(await page.evaluate(() => window.__starterEvents), []);
  await page.locator('#userInput').fill('');

  await think.click();
  await page.waitForFunction(() => document.activeElement?.id === 'userInput');
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'userInput');
  assert.equal(await page.locator('#userInput').inputValue(), '');

  await research.click();
  await page.waitForFunction(() => document.activeElement?.id === 'userInput');
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'userInput');
  assert.equal(await page.locator('#userInput').inputValue(), 'Search the web for ');
  await research.click();
  assert.equal(await page.locator('#userInput').inputValue(), 'Search the web for ');

  await image.click();
  assert.equal(await page.evaluate(() => window.__imageStudioOpens), 1);

  await file.click();
  assert.equal(await page.evaluate(() => window.__filePickerClicks), 1);

  await page.evaluate(() => { window.__starterChipInputEvents = 0; });

  const starterPrompts = [
    'Pick up where we left off.',
    'Help me plan my week.',
    'Research a topic for me.',
    'Help me think through an idea.',
  ];
  for (const [index, prompt] of starterPrompts.entries()) {
    await page.locator(`[data-starter-prompt="${prompt}"]`).click();
    const state = await page.evaluate(() => ({
      activeElement: document.activeElement?.id,
      value: document.getElementById('userInput')?.value,
      hasContent: document.querySelector('.input-container')?.classList.contains('has-content'),
      composerActive: document.body.classList.contains('v1-composer-active'),
      inputEvents: window.__starterChipInputEvents,
      sendClicks: window.__sendClicks,
      sendDisabled: document.getElementById('sendButton')?.disabled,
      sendAriaDisabled: document.getElementById('sendButton')?.getAttribute('aria-disabled'),
    }));
    assert.deepEqual(state, {
      activeElement: 'userInput',
      value: prompt,
      hasContent: true,
      composerActive: true,
      inputEvents: index + 1,
      sendClicks: 0,
      sendDisabled: false,
      sendAriaDisabled: 'false',
    });
  }

  await page.waitForFunction(() => window.__starterEvents.length === 5);
  const events = await page.evaluate(() => window.__starterEvents);
  assert.deepEqual(events.map(item => item.name), Array(5).fill('StarterIntentReached'));
  assert.deepEqual(events.map(item => item.detail.eventKey), Array(5).fill('first-starter-intent'));
  assert.deepEqual(events.map(item => item.detail.source), [
    'focus', 'research', 'research', 'image', 'file',
  ]);
  assert.deepEqual(errors, []);
  await page.close();
}

async function documentEntryLayout(browser) {
  const app = readFileSync(path.join(root, 'public', 'app.html'), 'utf8');
  const launchStart = app.indexOf('<section id="v1Launchpad"');
  const launchEnd = app.indexOf('\n\n        </section>', launchStart);
  assert.ok(launchStart >= 0 && launchEnd > launchStart, 'Production launchpad markup was not found.');
  const launchpad = app.slice(launchStart, launchEnd + '\n\n        </section>'.length);
  const styles = [
    'styles.css',
    'crump-v1-body.css',
    'crump-design-pass.css',
    'crump-ui-guardrails.css',
    'crump-motion-system.css',
  ].map(name => readFileSync(path.join(root, 'public', name), 'utf8')).join('\n');
  const viewports = [
    {name: 'desktop', width: 1280, height: 720},
    {name: 'tablet', width: 768, height: 1024},
    {name: 'iphone', width: 390, height: 844},
  ];
  const themes = ['light', 'dark'];

  for (const viewport of viewports) {
    for (const theme of themes) {
      for (const keyboardVisible of [false, true]) {
        const page = await browser.newPage({viewport});
        const errors = watch(page);
        await page.setContent(`<!doctype html>
          <html lang="en" data-theme="${theme}" data-cv-shell="ready">
          <head><meta name="viewport" content="width=device-width,initial-scale=1"><style>${styles}
            html,body{width:100%;height:100%;margin:0;overflow:hidden}
            body.crump-v1-body .v1-workspace-body{position:relative!important;width:100vw;height:100vh;overflow:hidden!important}
          </style></head>
          <body class="crump-v1-body crump-50${keyboardVisible ? ' crump-v1-keyboard-visible' : ''}">
            <main class="v1-workspace-body">${launchpad}</main>
          </body></html>`, {waitUntil: 'load'});

        const entry = page.locator('[data-home-document-entry]');
        assert.equal(await entry.count(), 1);
        await entry.scrollIntoViewIfNeeded();
        await entry.focus();
        const state = await page.evaluate(() => {
          const parse = value => (value.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
          const luminance = ([red, green, blue]) => {
            const channels = [red, green, blue].map(channel => {
              const normalized = channel / 255;
              return normalized <= .03928 ? normalized / 12.92 : ((normalized + .055) / 1.055) ** 2.4;
            });
            return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
          };
          const contrast = (foreground, background) => {
            const light = Math.max(luminance(parse(foreground)), luminance(parse(background)));
            const dark = Math.min(luminance(parse(foreground)), luminance(parse(background)));
            return (light + .05) / (dark + .05);
          };
          const card = document.querySelector('[data-home-document-entry]');
          const grid = card.closest('.v1-launchpad-grid');
          const launch = card.closest('.v1-launchpad');
          const title = card.querySelector('strong');
          const description = card.querySelector('small');
          const rect = card.getBoundingClientRect();
          const bodyBackground = getComputedStyle(document.body).backgroundColor;
          return {
            cardCount: grid.querySelectorAll('.v1-launch-card').length,
            indices: [...grid.querySelectorAll('.v1-launch-card')].map(node => node.dataset.v1Index),
            focused: document.activeElement === card,
            documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            launchOverflow: launch.scrollWidth - launch.clientWidth,
            gridOverflow: grid.scrollWidth - grid.clientWidth,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
            titleContrast: contrast(getComputedStyle(title).color, bodyBackground),
            descriptionContrast: contrast(getComputedStyle(description).color, bodyBackground),
          };
        });
        assert.equal(state.cardCount, 5, `${viewport.name}/${theme} card count`);
        assert.deepEqual(state.indices, ['01', '02', '03', '04', '05']);
        assert.equal(state.focused, true, `${viewport.name}/${theme} keyboard focus`);
        assert.ok(state.documentOverflow <= 1, `${viewport.name}/${theme} document overflow`);
        assert.ok(state.launchOverflow <= 1, `${viewport.name}/${theme} launchpad overflow`);
        assert.ok(state.gridOverflow <= 1, `${viewport.name}/${theme} grid overflow`);
        assert.ok(state.width >= 44 && state.height >= 44, `${viewport.name}/${theme} target size`);
        assert.ok(state.left >= -1 && state.right <= viewport.width + 1, `${viewport.name}/${theme} horizontal containment`);
        assert.ok(state.top >= -1 && state.bottom <= viewport.height + 1, `${viewport.name}/${theme} keyboard reachability`);
        assert.ok(state.titleContrast >= 4.5, `${viewport.name}/${theme} title contrast ${state.titleContrast}`);
        assert.ok(state.descriptionContrast >= 4.5, `${viewport.name}/${theme} description contrast ${state.descriptionContrast}`);
        assert.deepEqual(errors, []);
        await page.close();
      }
    }
  }
}

async function delayedProductActions(browser) {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = watch(page);
  await page.goto(`${fixtureOrigin}/tests/fixtures/launchpad-runtime-race.html`, {
    waitUntil: 'domcontentloaded',
  });

  const projects = page.getByRole('button', {name: 'Start or open a Project', exact: true});
  const video = page.getByRole('button', {name: 'Create a video', exact: true});
  await projects.click();
  assert.equal(await projects.getAttribute('aria-busy'), 'true');
  assert.deepEqual(await page.evaluate(() => window.__openedProductTabs), []);

  await video.click();
  assert.equal(await projects.getAttribute('aria-busy'), null);
  assert.equal(await video.getAttribute('aria-busy'), 'true');
  await page.evaluate(() => window.makeProductRuntimeReady());
  await page.waitForFunction(() => window.__openedProductTabs.length === 1);

  assert.deepEqual(await page.evaluate(() => window.__openedProductTabs), ['video']);
  assert.equal(await video.getAttribute('aria-busy'), null);
  const events = await page.evaluate(() => window.__starterEvents);
  assert.deepEqual(events.map(item => item.name), ['StarterIntentReached', 'StarterIntentReached']);
  assert.deepEqual(events.map(item => item.detail.eventKey), [
    'first-starter-intent', 'first-starter-intent',
  ]);
  assert.deepEqual(events.map(item => item.detail.source), ['projects', 'video']);
  assert.deepEqual(errors, []);
  await page.close();
}

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
    await composerActions(browser);
    await delayedProductActions(browser);
    await documentEntryLayout(browser);
    process.stdout.write('First-action proof passed: named choices, the document entry, responsive layouts, starter prompts, and the latest runtime-delayed destination preserve their exact behavior.\n');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
