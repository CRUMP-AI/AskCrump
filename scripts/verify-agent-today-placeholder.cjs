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
    // Today is a scroll region in its own grid row: content below its
    // fold is clipped by the panel, not painted over the hero. Overlap
    // is therefore judged on painted regions — each rect clipped to
    // the viewport, and Today descendants clipped to the panel box.
    const viewportBox = { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };
    const clip = (box, bounds) => {
      if (!box || !bounds) return box;
      const left = Math.max(box.left, bounds.left);
      const top = Math.max(box.top, bounds.top);
      const right = Math.min(box.right, bounds.right);
      const bottom = Math.min(box.bottom, bounds.bottom);
      return {
        left, top, right, bottom,
        width: Math.max(0, right - left), height: Math.max(0, bottom - top),
      };
    };
    const todayBox = rect(today);
    const inToday = box => clip(clip(box, todayBox), viewportBox);
    const inViewport = box => clip(box, viewportBox);
    return {
      titleText: title ? title.textContent : '',
      titleRect: inToday(rect(title)),
      titleColor: title ? getComputedStyle(title).color : '',
      titleBackground: title ? effectiveBackground(title) : '',
      titleOpacity: title ? Number(getComputedStyle(title).opacity) : 0,
      subColor: sub ? getComputedStyle(sub).color : '',
      subBackground: sub ? effectiveBackground(sub) : '',
      legacyCardPresent: Boolean(document.querySelector('.cat-connect')),
      cardInBriefArea: briefArea ? Boolean(briefArea.querySelector('.cat-card')) : false,
      noticeRect: inToday(rect(notice)),
      noticeRawHeight: notice ? rect(notice).height : 0,
      noticePosition: notice ? getComputedStyle(notice).position : '',
      noticeBackground: notice ? getComputedStyle(notice).backgroundColor : '',
      briefRect: inToday(rect(briefArea)),
      heroRect: inViewport(rect(document.querySelector('#v1Launchpad'))),
      waysLabelRect: inViewport(rect(document.querySelector('.v1-launchpad-actions-label'))),
      waysGridRect: inViewport(rect(document.querySelector('.v1-launchpad-grid'))),
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

async function measureReorg(page) {
  return page.evaluate(() => {
    const visible = element => {
      if (!element) return false;
      const style = getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      const box = element.getBoundingClientRect();
      return box.width > 0 && box.height > 0;
    };
    const waitSection = document.querySelector('section[aria-label="Waiting on you"]');
    const waitCards = waitSection
      ? [...waitSection.querySelectorAll('.cat-card')].filter(visible)
      : [];
    const queueRow = document.querySelector('.cat-queue-row');
    const firstCard = waitCards[0] || null;
    const meta = firstCard ? firstCard.querySelector('.cat-card-meta') : null;
    const actions = firstCard ? firstCard.querySelector('.cat-actions') : null;
    const detail = firstCard ? firstCard.querySelector('.cat-approval-detail') : null;
    const exact = firstCard ? firstCard.querySelector('.cat-card-exact') : null;
    const briefArea = document.querySelector('.cat-brief-area');
    const briefCard = document.querySelector('.cat-brief-card');
    const briefRows = briefArea ? [...briefArea.querySelectorAll('.cat-brief-row')] : [];
    const sectionTitle = document.querySelector('.cat-today-section-title');
    const connectBtn = document.querySelector('.cat-connect-btn');
    const sub = document.querySelector('.cat-today-sub');
    return {
      waitCardCount: waitCards.length,
      queueRowText: queueRow ? queueRow.textContent.trim() : '',
      queueRowVisible: visible(queueRow),
      exactText: exact ? exact.textContent : '',
      exactScrollWidth: exact ? exact.scrollWidth : 0,
      exactClientWidth: exact ? exact.clientWidth : 0,
      detailPresent: Boolean(detail),
      detailVisible: visible(detail),
      creditText: meta ? meta.textContent : '',
      creditBeforeActions: Boolean(meta && actions)
        ? meta.getBoundingClientRect().top <= actions.getBoundingClientRect().top
        : false,
      approvePresent: Boolean(firstCard && [...firstCard.querySelectorAll('button')]
        .some(btn => btn.textContent.trim() === 'Approve')),
      briefCardPresent: Boolean(briefCard),
      briefCountsText: briefCard ? (briefCard.querySelector('.cat-brief-counts') || {}).textContent || '' : '',
      briefLocalText: briefArea ? (briefArea.querySelector('.cat-brief-local') || {}).textContent || '' : '',
      briefRowTexts: briefRows.map(row => row.textContent),
      sectionTitleColor: sectionTitle ? getComputedStyle(sectionTitle).color : '',
      connectBtnHeight: connectBtn ? connectBtn.getBoundingClientRect().height : 0,
      subText: sub ? sub.textContent : '',
      browserTilePresent: Boolean(document.querySelector('.cat-browser-tile')),
      stepText: (document.querySelector('.cat-card-step') || {}).textContent || '',
    };
  });
}

function assertReorgStatics(m, label, state) {
  // One full approval card is visible at a time; the rest wait behind
  // a single queue row whose count is the real remaining count, and
  // the header line cites the same pending total.
  assert.equal(m.waitCardCount, 1, `${label}: visible approval cards ${m.waitCardCount}`);
  assert.equal(m.queueRowVisible, true, `${label}: queue row missing`);
  assert.equal(m.queueRowText, '+2 more waiting', `${label}: queue row text "${m.queueRowText}"`);
  assert.match(m.subText, /3 things need your call/, `${label}: header count "${m.subText}"`);
  // The card leads with the exact action from the frozen payload, the
  // frozen payload itself starts collapsed behind the detail toggle,
  // and the exact credit line stays visible before the buttons.
  assert.match(m.exactText, /ada@example\.com/, `${label}: exact summary "${m.exactText}"`);
  assert.match(m.exactText, /Following up/, `${label}: exact summary subject "${m.exactText}"`);
  assert.ok(m.exactScrollWidth <= m.exactClientWidth + 1,
    `${label}: exact summary clipped ${m.exactScrollWidth} > ${m.exactClientWidth}`);
  assert.equal(m.detailPresent, true, `${label}: approval detail missing`);
  assert.equal(m.detailVisible, false, `${label}: approval detail must start collapsed`);
  assert.match(m.creditText, /2 credits/, `${label}: credit line "${m.creditText}"`);
  assert.equal(m.creditBeforeActions, true, `${label}: credit line must precede the buttons`);
  assert.equal(m.approvePresent, true, `${label}: Approve button missing`);
  // Section eyebrows are the gold token, tracked and uppercase.
  assert.equal(m.sectionTitleColor, 'rgb(213, 185, 113)', `${label}: section eyebrow color`);
  // Live work shows a current step and the neutral browser tile.
  assert.equal(m.browserTilePresent, true, `${label}: browser preview tile missing`);
  assert.match(m.stepText, /Current step/, `${label}: step line "${m.stepText}"`);
  if (state === 'planned') {
    // Disconnected: no brief card, no calendar/inbox rows — the brief
    // area carries the notice plus the local counts only.
    assert.equal(m.briefCardPresent, false, `${label}: brief card rendered while disconnected`);
    assert.equal(m.briefRowTexts.length, 0,
      `${label}: brief rows while disconnected ${JSON.stringify(m.briefRowTexts)}`);
    assert.match(m.briefLocalText, /3 approvals waiting · 1 task running/,
      `${label}: local brief counts "${m.briefLocalText}"`);
    assert.ok(m.connectBtnHeight >= 44,
      `${label}: Connect Google hit target ${m.connectBtnHeight}px < 44px`);
  } else {
    // Connected: the brief card renders from the brief payload, with
    // counts from the same loaded approvals/runs as the sections.
    assert.equal(m.briefCardPresent, true, `${label}: connected brief card missing`);
    assert.match(m.briefCountsText, /3 approvals waiting · 1 task running/,
      `${label}: brief counts "${m.briefCountsText}"`);
    assert.equal(m.briefRowTexts.length, 2,
      `${label}: brief rows ${JSON.stringify(m.briefRowTexts)}`);
    assert.match(m.briefRowTexts[0], /Calendar/, `${label}: calendar row`);
    assert.match(m.briefRowTexts[0], /Design review/, `${label}: calendar row value`);
    assert.match(m.briefRowTexts[1], /Inbox/, `${label}: inbox row`);
    assert.match(m.briefRowTexts[1], /Launch checklist/, `${label}: inbox row value`);
  }
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
            // The raw (unclipped) height is what the cap governs.
            const fraction = m.noticeRawHeight / viewport.height;
            assert.ok(
              fraction <= viewport.maxNoticeFraction,
              `${label}: notice height ${m.noticeRawHeight}px is ${(fraction * 100).toFixed(1)}% of viewport`,
            );
            assert.equal(m.connectButton, true, `${label}: Connect Google action missing`);
            console.log(
              `${label}: greeting ${greetingRatio.toFixed(2)}:1, sub ${subRatio.toFixed(2)}:1, ` +
              `notice ${m.noticeRawHeight.toFixed(1)}px = ${(fraction * 100).toFixed(1)}% of ${viewport.height}px viewport`,
            );
          }
          const reorg = await measureReorg(page);
          assertReorgStatics(reorg, label, state);

          scenarios += 1;
          await page.close();
        }
      }
    }

    // Interactions, once per theme x brief state at the phone viewport:
    // the count row opens the Tasks panel with every pending approval
    // rendered in full, and the detail toggle opens the frozen payload.
    for (const theme of THEMES) {
      for (const state of STATES) {
        const label = `${theme}/${state} interactions @ 390x844`;
        const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
        await page.goto(`${fixtureUrl}?theme=${theme}&state=${state}`, { waitUntil: 'load' });
        await page.waitForSelector('.cat-queue-row', { timeout: 8000 });
        await page.waitForTimeout(150);
        await page.click('.cat-queue-row');
        await page.waitForSelector('#catTasksPanel.is-open', { timeout: 8000 });
        await page.waitForTimeout(120);
        const panel = await page.evaluate(() => {
          const panelEl = document.querySelector('#catTasksPanel');
          const cards = panelEl ? [...panelEl.querySelectorAll('.cat-card')] : [];
          const exacts = cards.map(card => {
            const exact = card.querySelector('.cat-card-exact');
            return exact
              ? { scroll: exact.scrollWidth, client: exact.clientWidth, text: exact.textContent }
              : null;
          });
          return { hidden: panelEl ? panelEl.hidden : true, cardCount: cards.length, exacts };
        });
        assert.equal(panel.hidden, false, `${label}: Tasks panel did not open`);
        assert.equal(panel.cardCount, 3, `${label}: Tasks panel approval cards ${panel.cardCount}`);
        // The long recipient list on the third card wraps without
        // overflowing its card at phone width.
        const thirdExact = panel.exacts[2];
        assert.ok(thirdExact, `${label}: third approval card missing in Tasks panel`);
        assert.match(thirdExact.text, /alexandria\.longaddress/, `${label}: long summary "${thirdExact.text}"`);
        assert.ok(thirdExact.scroll <= thirdExact.client + 1,
          `${label}: long summary clipped ${thirdExact.scroll} > ${thirdExact.client}`);
        await page.click('#catTasksPanel [aria-label="Close Tasks"]');
        await page.waitForTimeout(120);
        const panelClosed = await page.evaluate(() => {
          const panelEl = document.querySelector('#catTasksPanel');
          return panelEl ? panelEl.hidden : true;
        });
        assert.equal(panelClosed, true, `${label}: Tasks panel did not close`);
        let m = await measureReorg(page);
        assert.equal(m.waitCardCount, 1, `${label}: Today approval cards after Tasks ${m.waitCardCount}`);
        assert.equal(m.queueRowText, '+2 more waiting', `${label}: queue row after Tasks`);
        await page.click('.cat-today .cat-detail-toggle');
        await page.waitForTimeout(80);
        m = await measureReorg(page);
        assert.equal(m.detailVisible, true, `${label}: detail did not expand`);
        await page.close();
      }
    }
  } finally {
    await browser.close();
  }
  console.log(`Agent Today placeholder geometry: ${scenarios} scenarios passed ` +
    `(${THEMES.length} themes x ${STATES.length} brief states x ${VIEWPORTS.length} viewports) ` +
    `plus queue/detail interactions per theme x state.`);
}

run().catch(error => {
  console.error(error);
  process.exit(1);
});
