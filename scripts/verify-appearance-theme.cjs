const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const fixtureUrl = `${fixtureOrigin}/tests/fixtures/appearance-theme.html`;
const STORAGE_KEY = 'askcrump.appearance';

function channel(value) {
  const normalized = value / 255;
  return normalized <= 0.04045
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(colorValue, backgroundValue = 'rgb(255, 255, 255)') {
  const color = flatten(colorValue, backgroundValue);
  return 0.2126 * channel(color.r)
    + 0.7152 * channel(color.g)
    + 0.0722 * channel(color.b);
}

function parseColor(value) {
  const match = String(value).match(/rgba?\(\s*([\d.]+)[, ]+\s*([\d.]+)[, ]+\s*([\d.]+)(?:\s*[,/]\s*([\d.]+))?\s*\)/i);
  assert.ok(match, `Expected an rgb/rgba color, received ${value}`);
  return {
    r: Number(match[1]),
    g: Number(match[2]),
    b: Number(match[3]),
    a: match[4] === undefined ? 1 : Number(match[4]),
  };
}

function flatten(foregroundValue, backgroundValue) {
  const foreground = parseColor(foregroundValue);
  const background = parseColor(backgroundValue);
  return {
    r: foreground.r * foreground.a + background.r * (1 - foreground.a),
    g: foreground.g * foreground.a + background.g * (1 - foreground.a),
    b: foreground.b * foreground.a + background.b * (1 - foreground.a),
    a: 1,
  };
}

function contrastRatio(foregroundValue, backgroundValue, pageBackgroundValue) {
  const pageBackground = parseColor(pageBackgroundValue);
  const background = flatten(backgroundValue, `rgb(${pageBackground.r}, ${pageBackground.g}, ${pageBackground.b})`);
  const foreground = flatten(foregroundValue, `rgb(${background.r}, ${background.g}, ${background.b})`);
  const luminance = color => (
    0.2126 * channel(color.r)
    + 0.7152 * channel(color.g)
    + 0.0722 * channel(color.b)
  );
  const high = Math.max(luminance(foreground), luminance(background));
  const low = Math.min(luminance(foreground), luminance(background));
  return (high + 0.05) / (low + 0.05);
}

function watch(page) {
  const errors = [];
  page.on('response', response => {
    if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`);
  });
  page.on('console', message => {
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource:')) errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));
  return errors;
}

async function snapshot(page) {
  return page.evaluate(() => {
    const style = (selector, pseudo) => getComputedStyle(document.querySelector(selector), pseudo || null);
    const drawerBackground = style('#sidebar').backgroundColor;
    const pageBackground = style('body').backgroundColor;
    const workspaceBackground = style('.v1-workspace').backgroundColor;
    const settingsBackground = style('.v1-settings-sheet').backgroundColor;
    const pairs = {
      drawerHeader: [style('.v1-library-header', '::before').color, drawerBackground],
      newConversation: [style('#newChatBtn').color, style('#newChatBtn').backgroundColor],
      sectionTitle: [style('.section-title').color, drawerBackground],
      syncHint: [style('.v1-library-hint').color, drawerBackground],
      chatTitle: [style('.chat-title').color, style('.chat-item').backgroundColor],
      chatPreview: [style('.chat-preview').color, style('.chat-item').backgroundColor],
      headline: [style('.cv-headline').color, workspaceBackground],
      intro: [style('.cv-sub').color, workspaceBackground],
      cardTitle: [style('.cv-card-title').color, style('.cv-card').backgroundColor],
      cardCopy: [style('.cv-card-copy').color, style('.cv-card').backgroundColor],
      settingsHeading: [style('.v1-settings-sheet h2').color, settingsBackground],
      settingsCopy: [style('.v1-settings-sheet p').color, settingsBackground],
      intelligenceTitle: [style('.crump44-panel-header strong').color, style('.crump44-panel').backgroundColor],
      intelligenceCopy: [style('.crump44-panel-header small').color, style('.crump44-panel').backgroundColor],
      intelligenceOption: [style('.crump44-segment.active').color, style('.crump44-segment.active').backgroundColor],
      imageStudioTitle: [style('.crump50-sheet-head strong').color, style('.crump50-sheet').backgroundColor],
      imageStudioCopy: [style('.crump50-reference-action small').color, style('.crump50-reference-action').backgroundColor],
      addSheetTitle: [style('.crump52-attach-sheet h2').color, style('.crump52-attach-sheet').backgroundColor],
      addSheetCopy: [style('.crump52-attach-choice small').color, style('.crump52-attach-sheet').backgroundColor],
      billingTitle: [style('.billing51-brand h2').color, style('.billing51-sheet').backgroundColor],
      billingCopy: [style('.billing51-balance-card p').color, style('.billing51-balance-card').backgroundColor],
      mediaTitle: [style('.crump53-card h3').color, style('.crump53-card').backgroundColor],
      mediaCopy: [style('.crump53-card p').color, style('.crump53-card').backgroundColor],
    };
    if (innerWidth <= 1100) {
      pairs.mobileSheetTitle = [style('.cv-more-head h2').color, style('.cv-more-sheet').backgroundColor];
      pairs.mobileSheetItem = [style('.cv-more-item').color, style('.cv-more-sheet').backgroundColor];
    }
    return {
      theme: document.documentElement.dataset.theme,
      colorScheme: style('html').colorScheme,
      stored: localStorage.getItem('askcrump.appearance'),
      meta: document.querySelector('meta[name="theme-color"]')?.content || '',
      lightChecked: document.getElementById('appearanceLight')?.checked || false,
      darkChecked: document.getElementById('appearanceDark')?.checked || false,
      hasApi: Boolean(window.CrumpAppearance
        && typeof window.CrumpAppearance.get === 'function'
        && typeof window.CrumpAppearance.set === 'function'
        && typeof window.CrumpAppearance.syncControls === 'function'),
      pageBackground,
      drawerBackground,
      workspaceBackground,
      settingsBackground,
      surfaceBackgrounds: {
        intelligence: style('.crump44-panel').backgroundColor,
        imageStudio: style('.crump50-sheet').backgroundColor,
        addSheet: style('.crump52-attach-sheet').backgroundColor,
        billing: style('.billing51-sheet').backgroundColor,
        media: style('.crump53-card').backgroundColor,
        mobileSheet: style('.cv-more-sheet').backgroundColor,
      },
      pairs,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });
}

function assertContrast(state) {
  for (const [name, [foreground, background]] of Object.entries(state.pairs)) {
    const actualBackground = parseColor(background).a === 0 ? state.pageBackground : background;
    const ratio = contrastRatio(foreground, actualBackground, state.pageBackground);
    assert.ok(ratio >= 4.5, `${state.theme} ${name} contrast was ${ratio.toFixed(2)} (${foreground} on ${actualBackground})`);
  }
}

function assertLightSurfaces(state, includeMobile = false) {
  const keys = ['intelligence', 'imageStudio', 'addSheet', 'billing', 'media'];
  if (includeMobile) keys.push('mobileSheet');
  for (const key of keys) {
    const background = state.surfaceBackgrounds[key];
    assert.ok(relativeLuminance(background, state.pageBackground) > 0.72, `light ${key} surface remained dark (${background})`);
  }
}

function assertDarkSurfaces(state, lightState, includeMobile = false) {
  const keys = ['intelligence', 'imageStudio', 'addSheet', 'billing', 'media'];
  if (includeMobile) keys.push('mobileSheet');
  for (const key of keys) {
    const background = state.surfaceBackgrounds[key];
    assert.notEqual(background, lightState.surfaceBackgrounds[key], `${key} did not change with the theme`);
    assert.ok(relativeLuminance(background, state.pageBackground) < 0.06, `dark ${key} surface was too bright (${background})`);
  }
}

(async () => {
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const context = await browser.newContext({viewport: {width: 1440, height: 900}});
  const page = await context.newPage();
  const errors = watch(page);
  try {
    await page.goto(fixtureUrl, {waitUntil: 'networkidle'});
    let state = await snapshot(page);
    assert.equal(state.theme, 'light');
    assert.equal(state.colorScheme, 'light');
    assert.equal(state.stored, null);
    assert.equal(state.meta.toLowerCase(), '#f6f4ee');
    assert.equal(state.lightChecked, true);
    assert.equal(state.darkChecked, false);
    assert.equal(state.hasApi, true);
    assert.equal(state.horizontalOverflow, false);
    assertContrast(state);
    assertLightSurfaces(state);
    const lightState = state;

    await page.evaluate(() => {
      window.__appearanceEvents = [];
      window.addEventListener('crump:appearance-changed', event => {
        window.__appearanceEvents.push(event.detail?.theme || '');
      });
    });
    await page.locator('#appearanceDark').check();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    await page.waitForTimeout(200);
    state = await snapshot(page);
    assert.equal(state.theme, 'dark');
    assert.equal(state.colorScheme, 'dark');
    assert.equal(state.stored, 'dark');
    assert.equal(state.meta.toLowerCase(), '#101216');
    assert.equal(state.lightChecked, false);
    assert.equal(state.darkChecked, true);
    assert.deepEqual(await page.evaluate(() => window.__appearanceEvents), ['dark']);
    assert.notEqual(state.pageBackground, lightState.pageBackground);
    assert.notEqual(state.drawerBackground, lightState.drawerBackground);
    assert.notEqual(state.settingsBackground, lightState.settingsBackground);
    assert.ok(relativeLuminance(state.pageBackground) < 0.03, state.pageBackground);
    assert.ok(relativeLuminance(state.drawerBackground, state.pageBackground) < 0.04, state.drawerBackground);
    assert.ok(relativeLuminance(state.settingsBackground, state.pageBackground) < 0.05, state.settingsBackground);
    assertContrast(state);
    assertDarkSurfaces(state, lightState);

    await page.reload({waitUntil: 'networkidle'});
    state = await snapshot(page);
    assert.equal(state.theme, 'dark');
    assert.equal(state.stored, 'dark');
    assert.equal(state.darkChecked, true);
    assertContrast(state);

    await page.locator('#appearanceLight').check();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');
    await page.waitForTimeout(200);
    state = await snapshot(page);
    assert.equal(state.theme, 'light');
    assert.equal(state.stored, 'light');
    assert.equal(state.lightChecked, true);
    assertContrast(state);
    assertLightSurfaces(state);

    assert.deepEqual(errors, []);

    const mobileContext = await browser.newContext({viewport: {width: 390, height: 844}});
    const mobilePage = await mobileContext.newPage();
    const mobileErrors = watch(mobilePage);
    try {
      await mobilePage.goto(fixtureUrl, {waitUntil: 'networkidle'});
      let mobileState = await snapshot(mobilePage);
      assert.equal(mobileState.theme, 'light');
      assert.equal(mobileState.horizontalOverflow, false);
      assertContrast(mobileState);
      assertLightSurfaces(mobileState, true);
      const mobileLightState = mobileState;

      await mobilePage.locator('#appearanceDark').check();
      await mobilePage.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
      await mobilePage.waitForTimeout(200);
      mobileState = await snapshot(mobilePage);
      assert.equal(mobileState.theme, 'dark');
      assert.equal(mobileState.darkChecked, true);
      assert.equal(mobileState.horizontalOverflow, false);
      assert.ok(relativeLuminance(mobileState.pageBackground) < 0.03, mobileState.pageBackground);
      assertContrast(mobileState);
      assertDarkSurfaces(mobileState, mobileLightState, true);
      assert.deepEqual(mobileErrors, []);
    } finally {
      await mobileContext.close();
    }

    process.stdout.write('Appearance proof passed: Light is the stable default, Dark persists, chrome updates, and representative drawer, workspace, Intelligence, media, billing, and mobile-sheet text meets WCAG AA in both modes.\n');
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
