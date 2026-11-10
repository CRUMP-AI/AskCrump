const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const fixtureUrl = `${fixtureOrigin}/tests/fixtures/agent-today-placeholder.html`;

const VIEWPORTS = [
  { name: '1039x738', width: 1039, height: 738, maxNoticeFraction: 0.10 },
  { name: '390x844', width: 390, height: 844, maxNoticeFraction: 0.13 },
  { name: '320x844', width: 320, height: 844, maxNoticeFraction: 0.16 },
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
    const sub = document.querySelector('.cat-today-sub');
    const notice = document.querySelector('.cat-connect-notice');
    const briefArea = document.querySelector('.cat-brief-area');
    const noticeText = notice ? notice.querySelector('.cat-connect-text') : null;
    // Any descendant of the brief area that spills outside the brief
    // area's box horizontally counts as clipped or overflowing text.
    let briefOverflow = null;
    if (briefArea) {
      const briefBox = briefArea.getBoundingClientRect();
      briefArea.querySelectorAll('*').forEach(element => {
        const box = element.getBoundingClientRect();
        if (box.width && (box.right > briefBox.right + 0.6 || box.left < briefBox.left - 0.6)) {
          briefOverflow = {
            className: element.className || element.tagName,
            right: box.right, briefRight: briefBox.right,
            left: box.left, briefLeft: briefBox.left,
          };
        }
        if (element.scrollWidth > element.clientWidth + 1) {
          briefOverflow = briefOverflow || {
            className: element.className || element.tagName,
            scrollWidth: element.scrollWidth, clientWidth: element.clientWidth,
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
      subColor: sub ? getComputedStyle(sub).color : '',
      subBackground: sub ? effectiveBackground(sub) : '',
      legacyCardPresent: Boolean(document.querySelector('.cat-connect')),
      cardInBriefArea: briefArea ? Boolean(briefArea.querySelector('.cat-card')) : false,
      noticeRect: rect(notice),
      noticePosition: notice ? getComputedStyle(notice).position : '',
      noticeBackground: notice ? getComputedStyle(notice).backgroundColor : '',
      briefRect: rect(briefArea),
      heroRect: rect(document.querySelector('#v1Launchpad')),
      waysLabelRect: rect(document.querySelector('.v1-launchpad-actions-label')),
      waysGridRect: rect(document.querySelector('.v1-launchpad-grid')),
      todayRect: rect(today),
      todayScrollWidth: today ? today.scrollWidth : 0,
      todayClientWidth: today ? today.clientWidth : 0,
      documentScrollWidth: document.documentElement.scrollWidth,
      noticeTextScrollWidth: noticeText ? noticeText.scrollWidth : 0,
      noticeTextClientWidth: noticeText ? noticeText.clientWidth : 0,
      noticeTextScrollHeight: noticeText ? noticeText.scrollHeight : 0,
      noticeTextClientHeight: noticeText ? noticeText.clientHeight : 0,
      briefOverflow,
      connectButton: notice ? Boolean(notice.querySelector('.cat-connect-btn')) : false,
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
          await page.waitForSelector(state === 'planned' ? '.cat-connect-notice' : '.cat-brief-area', { timeout: 8000 });
          await page.waitForTimeout(150);
          const m = await measure(page);

          // The greeting is present, at full opacity, in off-white on the
          // layer's own ink ground — never ink-on-ink ghosted. The fix is
          // the text color against its ground, in both appearances.
          assert.match(m.titleText, /^Good (morning|afternoon|evening), Gregory\./, label);
          assert.equal(m.titleColor, 'rgb(241, 239, 233)', `${label}: greeting color`);
          assert.equal(m.titleBackground, 'rgb(7, 10, 14)', `${label}: greeting ground`);
          assert.equal(m.titleOpacity, 1, `${label}: greeting opacity`);
          const greetingRatio = contrastRatio(m.titleColor, m.titleBackground);
          assert.ok(greetingRatio >= 4.5, `${label}: greeting contrast ${greetingRatio}`);
          const subRatio = contrastRatio(m.subColor, m.subBackground);
          assert.ok(subRatio >= 4.5, `${label}: sub contrast ${subRatio}`);

          // Nothing overlays or covers the greeting or the ways-to-begin
          // content: every pairing intersects by exactly zero pixels.
          assert.equal(intersectionArea(m.titleRect, m.briefRect), 0, `${label}: greeting x brief area`);
          assert.equal(intersectionArea(m.titleRect, m.heroRect), 0, `${label}: greeting x hero`);
          assert.equal(intersectionArea(m.briefRect, m.heroRect), 0, `${label}: brief area x hero`);
          assert.equal(intersectionArea(m.titleRect, m.waysLabelRect), 0, `${label}: greeting x ways label`);
          if (state === 'planned') {
            assert.equal(intersectionArea(m.noticeRect, m.heroRect), 0, `${label}: notice x hero`);
            assert.equal(intersectionArea(m.noticeRect, m.waysLabelRect), 0, `${label}: notice x ways label`);
            assert.equal(intersectionArea(m.noticeRect, m.waysGridRect), 0, `${label}: notice x ways grid`);
          }

          // No horizontal overflow or clipped text anywhere in the brief
          // area, at any width.
          assert.ok(
            m.documentScrollWidth <= viewport.width,
            `${label}: document scrollWidth ${m.documentScrollWidth} > ${viewport.width}`,
          );
          assert.ok(
            m.todayScrollWidth <= m.todayClientWidth + 1,
            `${label}: Today scrollWidth ${m.todayScrollWidth} > clientWidth ${m.todayClientWidth}`,
          );
          assert.ok(m.briefRect.left >= -0.6 && m.briefRect.right <= viewport.width + 0.6,
            `${label}: brief area escapes the viewport`);
          assert.equal(m.briefOverflow, null, `${label}: brief overflow ${JSON.stringify(m.briefOverflow)}`);

          if (state === 'planned') {
            // The connect prompt is a notice, not a card: no legacy card
            // element, no card inside the brief area, no panel fill, and
            // it sits in normal document flow — never positioned over
            // content.
            assert.equal(m.legacyCardPresent, false, `${label}: legacy connect card still rendered`);
            assert.equal(m.cardInBriefArea, false, `${label}: a card still renders in the brief area`);
            assert.equal(m.noticePosition, 'static', `${label}: notice position ${m.noticePosition}`);
            assert.equal(m.noticeBackground, 'rgba(0, 0, 0, 0)', `${label}: notice fill ${m.noticeBackground}`);
            assert.ok(m.noticeTextScrollWidth <= m.noticeTextClientWidth + 1,
              `${label}: notice text clipped horizontally`);
            assert.ok(m.noticeTextScrollHeight <= m.noticeTextClientHeight + 1,
              `${label}: notice text clipped vertically`);

            // The notice is slim: a small fraction of the viewport
            // height at every size — single digits at desktop. A
            // covering card coming back fails here on height alone.
            const fraction = m.noticeRect.height / viewport.height;
            assert.ok(
              fraction <= viewport.maxNoticeFraction,
              `${label}: notice height ${m.noticeRect.height}px is ${(fraction * 100).toFixed(1)}% of viewport`,
            );
            assert.equal(m.connectButton, true, `${label}: Connect Google action missing`);
            console.log(
              `${label}: greeting ${greetingRatio.toFixed(2)}:1, sub ${subRatio.toFixed(2)}:1, ` +
              `notice ${m.noticeRect.height.toFixed(1)}px = ${(fraction * 100).toFixed(1)}% of ${viewport.height}px viewport`,
            );
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
