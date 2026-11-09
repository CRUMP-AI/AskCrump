const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const fixtureUrl = `${fixtureOrigin}/tests/fixtures/agent-today-placeholder.html`;

const VIEWPORTS = [
  { name: '1039x738', width: 1039, height: 738 },
  { name: '390x844', width: 390, height: 844 },
  { name: '320x844', width: 320, height: 844 },
];
const THEMES = ['dark', 'light'];
const STATES = ['planned', 'live'];

function channel(value) {
  const normalized = value / 255;
  return normalized <= 0.04045
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4;
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

function flatten(foreground, background) {
  return {
    r: foreground.r * foreground.a + background.r * (1 - foreground.a),
    g: foreground.g * foreground.a + background.g * (1 - foreground.a),
    b: foreground.b * foreground.a + background.b * (1 - foreground.a),
    a: 1,
  };
}

function luminance(color) {
  return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
}

function contrastRatio(foregroundValue, backgroundValue) {
  const background = parseColor(backgroundValue);
  const foreground = flatten(parseColor(foregroundValue), background);
  const high = Math.max(luminance(foreground), luminance(background));
  const low = Math.min(luminance(foreground), luminance(background));
  return (high + 0.05) / (low + 0.05);
}

function intersectionArea(a, b) {
  if (!a || !b) return 0;
  const width = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const height = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return Math.max(0, width) * Math.max(0, height);
}

async function measure(page) {
  return page.evaluate(() => {
    const rect = element => {
      if (!element) return null;
      const box = element.getBoundingClientRect();
      return {
        left: box.left, top: box.top, right: box.right, bottom: box.bottom,
        width: box.width, height: box.height,
      };
    };
    const effectiveBackground = element => {
      let node = element;
      while (node && node !== document.documentElement) {
        const background = getComputedStyle(node).backgroundColor;
        if (background && background !== 'rgba(0, 0, 0, 0)' && background !== 'transparent') {
          return background;
        }
        node = node.parentElement;
      }
      return getComputedStyle(document.body).backgroundColor;
    };
    const title = document.querySelector('.cat-today-title');
    const connect = document.querySelector('.cat-connect');
    const briefArea = document.querySelector('.cat-brief-area');
    const card = connect || briefArea;
    const summary = connect ? connect.querySelector('.cat-card-summary') : null;
    let childOverflow = null;
    if (connect) {
      const cardBox = connect.getBoundingClientRect();
      connect.querySelectorAll('*').forEach(element => {
        const box = element.getBoundingClientRect();
        if (box.width && (box.right > cardBox.right + 0.6 || box.left < cardBox.left - 0.6)) {
          childOverflow = {
            className: element.className || element.tagName,
            right: box.right, cardRight: cardBox.right,
            left: box.left, cardLeft: cardBox.left,
          };
        }
      });
    }
    const today = document.querySelector('.cat-today');
    return {
      titleText: title ? title.textContent : '',
      titleRect: rect(title),
      titleColor: title ? getComputedStyle(title).color : '',
      titleBackground: title ? effectiveBackground(title) : '',
      titleOpacity: title ? Number(getComputedStyle(title).opacity) : 0,
      cardRect: rect(card),
      cardBackground: connect ? getComputedStyle(connect).backgroundColor : '',
      heroRect: rect(document.querySelector('#v1Launchpad')),
      todayRect: rect(today),
      todayScrollWidth: today ? today.scrollWidth : 0,
      todayClientWidth: today ? today.clientWidth : 0,
      documentScrollWidth: document.documentElement.scrollWidth,
      summaryScrollWidth: summary ? summary.scrollWidth : 0,
      summaryClientWidth: summary ? summary.clientWidth : 0,
      summaryScrollHeight: summary ? summary.scrollHeight : 0,
      summaryClientHeight: summary ? summary.clientHeight : 0,
      childOverflow,
      connectButton: connect ? Boolean(connect.querySelector('.cat-btn-primary')) : false,
    };
  });
}

async function run() {
  const browser = await chromium.launch({ headless: true, executablePath });
  let scenarios = 0;
  try {
    for (const theme of THEMES) {
      for (const state of STATES) {
        for (const viewport of VIEWPORTS) {
          const label = `${theme}/${state} @ ${viewport.name}`;
          const page = await browser.newPage({ viewport });
          await page.goto(`${fixtureUrl}?theme=${theme}&state=${state}`, { waitUntil: 'load' });
          await page.waitForSelector(state === 'planned' ? '.cat-connect' : '.cat-brief-area', { timeout: 8000 });
          await page.waitForTimeout(150);
          const m = await measure(page);

          // The greeting is present, at full opacity, in off-white on the
          // layer's own ink ground — never ink-on-ink ghosted.
          assert.match(m.titleText, /^Good (morning|afternoon|evening), Gregory\./, label);
          assert.equal(m.titleColor, 'rgb(241, 239, 233)', `${label}: greeting color`);
          assert.equal(m.titleBackground, 'rgb(7, 10, 14)', `${label}: greeting ground`);
          assert.equal(m.titleOpacity, 1, `${label}: greeting opacity`);
          assert.ok(
            contrastRatio(m.titleColor, m.titleBackground) >= 4.5,
            `${label}: greeting contrast ${contrastRatio(m.titleColor, m.titleBackground)}`,
          );

          // Neither the brief card nor the launchpad hero may cover the
          // greeting, and the card stays clear of the hero, in both brief
          // states.
          assert.equal(intersectionArea(m.titleRect, m.cardRect), 0, `${label}: greeting x brief card`);
          assert.equal(intersectionArea(m.titleRect, m.heroRect), 0, `${label}: greeting x hero`);
          assert.equal(intersectionArea(m.cardRect, m.heroRect), 0, `${label}: brief card x hero`);

          // No horizontal overflow or clipped text at any width.
          assert.ok(
            m.documentScrollWidth <= viewport.width,
            `${label}: document scrollWidth ${m.documentScrollWidth} > ${viewport.width}`,
          );
          assert.ok(
            m.todayScrollWidth <= m.todayClientWidth + 1,
            `${label}: Today scrollWidth ${m.todayScrollWidth} > clientWidth ${m.todayClientWidth}`,
          );
          assert.ok(m.cardRect.left >= -0.6 && m.cardRect.right <= viewport.width + 0.6,
            `${label}: brief card escapes the viewport`);
          assert.equal(m.childOverflow, null, `${label}: card child overflow ${JSON.stringify(m.childOverflow)}`);
          if (state === 'planned') {
            assert.ok(m.summaryScrollWidth <= m.summaryClientWidth + 1,
              `${label}: summary clipped horizontally`);
            assert.ok(m.summaryScrollHeight <= m.summaryClientHeight + 1,
              `${label}: summary clipped vertically`);

            // The placeholder is a compact dark note, not a white slab:
            // dark panel, capped width, subordinate height, gold action.
            const cardLuminance = luminance(parseColor(m.cardBackground));
            assert.ok(cardLuminance < 0.05, `${label}: placeholder is not dark (luminance ${cardLuminance})`);
            assert.ok(m.cardRect.width <= 640, `${label}: placeholder width ${m.cardRect.width}`);
            if (viewport.width >= 1039) {
              assert.ok(m.cardRect.width <= m.todayRect.width * 0.75,
                `${label}: placeholder spans ${m.cardRect.width} of ${m.todayRect.width}`);
            }
            assert.ok(m.cardRect.height <= viewport.height * 0.45,
              `${label}: placeholder height ${m.cardRect.height}`);
            assert.equal(m.connectButton, true, `${label}: Connect Google action missing`);
          }
          scenarios += 1;
          await page.close();
        }
      }
    }
  } finally {
    await browser.close();
  }
  console.log(`Agent Today placeholder geometry: ${scenarios} scenarios passed ` +
    `(${THEMES.length} themes x ${STATES.length} brief states x ${VIEWPORTS.length} viewports).`);
}

run().catch(error => {
  console.error(error);
  process.exit(1);
});
