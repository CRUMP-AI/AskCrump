const assert = require('node:assert/strict');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

const fixtureOrigin = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const fixtureUrl = `${fixtureOrigin}/tests/fixtures/agent-today-placeholder.html`;
const chatFixtureUrl = `${fixtureOrigin}/tests/fixtures/agent-chat-cards.html`;
const projectsYouFixtureUrl = `${fixtureOrigin}/tests/fixtures/reorg-projects-you.html`;

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

async function measureChat(page) {
  return page.evaluate(() => {
    const visible = element => {
      if (!element) return false;
      const style = getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      const box = element.getBoundingClientRect();
      return box.width > 0 && box.height > 0;
    };
    const section = document.querySelector('#catChatWork');
    const cards = section ? [...section.querySelectorAll('.cat-card')].filter(visible) : [];
    const primary = cards[0] || null;
    const rows = section ? [...section.querySelectorAll('.cat-chat-row')] : [];
    const exact = primary ? primary.querySelector('.cat-card-exact') : null;
    const detail = primary ? primary.querySelector('.cat-approval-detail') : null;
    const meta = primary ? primary.querySelector('.cat-card-meta') : null;
    const actions = primary ? primary.querySelector('.cat-actions') : null;
    const sectionBox = section ? section.getBoundingClientRect() : null;
    const dock = document.querySelector('.v1-command-dock');
    const dockBox = dock ? dock.getBoundingClientRect() : null;
    const container = document.querySelector('#chatContainer');
    const containerBox = container ? container.getBoundingClientRect() : null;
    const inputBar = document.querySelector('.input-container');
    return {
      sectionPresent: Boolean(section),
      sectionVisible: visible(section),
      sectionText: section ? section.textContent : '',
      cardCount: cards.length,
      primaryText: primary ? primary.textContent : '',
      exactText: exact ? exact.textContent : '',
      exactScrollWidth: exact ? exact.scrollWidth : 0,
      exactClientWidth: exact ? exact.clientWidth : 0,
      detailPresent: Boolean(detail),
      detailVisible: visible(detail),
      creditText: meta ? meta.textContent : '',
      creditBeforeActions: Boolean(meta && actions)
        ? meta.getBoundingClientRect().top <= actions.getBoundingClientRect().top
        : false,
      approvePresent: Boolean(primary && [...primary.querySelectorAll('button')]
        .some(btn => btn.textContent.trim() === 'Approve')),
      stepText: primary ? (primary.querySelector('.cat-card-step') || {}).textContent || '' : '',
      rowTexts: rows.map(row => row.textContent),
      rowIsCard: rows.some(row => row.classList.contains('cat-card')),
      todayVisible: visible(document.querySelector('#catToday')),
      sectionBottom: sectionBox ? sectionBox.bottom : 0,
      sectionRight: sectionBox ? sectionBox.right : 0,
      sectionScrollWidth: section ? section.scrollWidth : 0,
      sectionClientWidth: section ? section.clientWidth : 0,
      dockTop: dockBox ? dockBox.top : 0,
      containerBottom: containerBox ? containerBox.bottom : 0,
      documentScrollWidth: document.documentElement.scrollWidth,
      composerChildIds: inputBar
        ? [...inputBar.children].map(child => child.id || child.tagName)
        : [],
      fetchCalls: Array.isArray(window.__fetchCalls) ? window.__fetchCalls.slice() : [],
    };
  });
}

async function measureTasks(page) {
  return page.evaluate(() => {
    const visible = element => {
      if (!element) return false;
      const style = getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      const box = element.getBoundingClientRect();
      return box.width > 0 && box.height > 0;
    };
    const panel = document.querySelector('#catTasksPanel');
    const groups = panel ? [...panel.querySelectorAll('.cat-group')] : [];
    const groupInfo = groups.map(group => {
      const title = group.querySelector('.cat-group-title');
      return {
        title: title ? title.textContent.trim() : '',
        titleColor: title ? getComputedStyle(title).color : '',
        text: group.textContent,
        cards: [...group.querySelectorAll('.cat-card')].filter(visible).length,
        rows: [...group.querySelectorAll('.cat-task-row')].map(row => {
          const titleEl = row.querySelector('.cat-task-row-title');
          const metaEl = row.querySelector('.cat-task-row-meta');
          const detail = row.querySelector('.cat-task-detail');
          return {
            title: titleEl ? titleEl.textContent : '',
            titleScrollWidth: titleEl ? titleEl.scrollWidth : 0,
            titleClientWidth: titleEl ? titleEl.clientWidth : 0,
            meta: metaEl ? metaEl.textContent : '',
            marker: Boolean(row.querySelector('.cat-row-marker')),
            detailText: detail ? detail.textContent : '',
            detailVisible: visible(detail),
          };
        }),
        emptyText: (group.querySelector('.cat-group-empty') || {}).textContent || '',
      };
    });
    return {
      panelVisible: visible(panel),
      panelBackground: panel ? getComputedStyle(panel).backgroundColor : '',
      groupTitles: groupInfo.map(group => group.title),
      groups: groupInfo,
      panelText: panel ? panel.textContent : '',
      panelScrollWidth: panel ? panel.scrollWidth : 0,
      panelClientWidth: panel ? panel.clientWidth : 0,
      fetchCalls: Array.isArray(window.__fetchCalls) ? window.__fetchCalls.slice() : [],
    };
  });
}

async function openTasksFixture(page, url) {
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(250);
  await page.evaluate(() => window.CrumpAgentToday.openTasks());
  await page.waitForSelector('#catTasksPanel.is-open', { timeout: 8000 });
  await page.waitForTimeout(150);
}

async function runTasksScenarios(browser) {
  let scenarios = 0;
  // Mixed record at every viewport in both appearances: waiting holds
  // every approval as a full card, then Running, Scheduled, Done in
  // the locked order, each row a one-line record with a marker.
  for (const theme of THEMES) {
    for (const viewport of VIEWPORTS) {
      const label = `tasks ${theme}/mixed @ ${viewport.name}`;
      const page = await browser.newPage({ viewport });
      await openTasksFixture(page, `${fixtureUrl}?theme=${theme}&state=live&tasks=mixed`);
      const m = await measureTasks(page);
      assert.equal(m.panelVisible, true, `${label}: Tasks panel not visible`);
      assert.equal(m.panelBackground, 'rgb(7, 10, 14)', `${label}: drawer ground ${m.panelBackground}`);
      assert.deepEqual(m.groupTitles, ['Waiting on you', 'Running', 'Scheduled', 'Done'],
        `${label}: group order ${JSON.stringify(m.groupTitles)}`);
      const [waiting, running, scheduled, done] = m.groups;
      assert.equal(waiting.titleColor, 'rgb(213, 185, 113)', `${label}: group eyebrow color`);
      // PR2 dependency: every pending approval renders in full here.
      assert.equal(waiting.cards, 3, `${label}: waiting approval cards ${waiting.cards}`);
      assert.equal(running.rows.length, 1, `${label}: running rows`);
      assert.match(running.rows[0].title, /Act in the browser/, `${label}: running title`);
      assert.match(running.rows[0].meta, /Running/, `${label}: running meta`);
      assert.equal(running.rows[0].marker, true, `${label}: running marker missing`);
      // Scheduled: the enabled automation and the paused one both
      // render in this group; the line comes from the stored schedule
      // (daily + local time) and the stored next run — nothing else.
      assert.equal(scheduled.rows.length, 2, `${label}: scheduled rows ${scheduled.rows.length}`);
      assert.match(scheduled.rows[0].title, /Send the morning brief/, `${label}: scheduled title`);
      assert.match(scheduled.rows[0].meta, /Scheduled/, `${label}: enabled meta "${scheduled.rows[0].meta}"`);
      assert.match(scheduled.rows[0].meta, /Daily at 7:00 AM/, `${label}: schedule line "${scheduled.rows[0].meta}"`);
      assert.match(scheduled.rows[0].meta, /Next Nov 11/, `${label}: next run "${scheduled.rows[0].meta}"`);
      assert.doesNotMatch(m.panelText, /every weekday/i, `${label}: invented frequency wording`);
      assert.match(scheduled.rows[1].meta, /Paused/, `${label}: paused meta "${scheduled.rows[1].meta}"`);
      assert.equal(scheduled.rows[1].marker, true, `${label}: paused marker missing`);
      // The long automation title wraps without clipping at 320px too.
      assert.ok(scheduled.rows[1].titleScrollWidth <= scheduled.rows[1].titleClientWidth + 1,
        `${label}: long title clipped ${scheduled.rows[1].titleScrollWidth} > ${scheduled.rows[1].titleClientWidth}`);
      assert.equal(done.rows.length, 1, `${label}: done rows`);
      assert.match(done.rows[0].meta, /Done/, `${label}: done meta`);
      assert.ok(m.panelScrollWidth <= m.panelClientWidth + 1,
        `${label}: panel clipped ${m.panelScrollWidth} > ${m.panelClientWidth}`);
      scenarios += 1;
      await page.close();
    }
  }

  // Row expansion: a run row opens its recorded steps; a scheduled
  // row opens the schedule record it carries, including last run.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await openTasksFixture(page, `${fixtureUrl}?theme=dark&state=live&tasks=mixed`);
    await page.click('#catTasksPanel .cat-group:nth-of-type(2) .cat-task-row-head');
    await page.waitForTimeout(300);
    let m = await measureTasks(page);
    assert.equal(m.groups[1].rows[0].detailVisible, true, 'tasks expand: run detail did not open');
    assert.match(m.groups[1].rows[0].detailText, /Run created/, 'tasks expand: steps missing');
    assert.match(m.groups[1].rows[0].detailText, /Queued/, 'tasks expand: second step missing');
    await page.click('#catTasksPanel .cat-group:nth-of-type(3) .cat-task-row-head');
    await page.waitForTimeout(120);
    m = await measureTasks(page);
    assert.equal(m.groups[2].rows[0].detailVisible, true, 'tasks expand: scheduled detail did not open');
    assert.match(m.groups[2].rows[0].detailText, /Last run/, 'tasks expand: last run missing');
    assert.match(m.groups[2].rows[0].detailText, /America\/New_York/, 'tasks expand: timezone missing');
    await page.close();
    scenarios += 1;
  }

  // Scheduled-only: the standing record renders with the other groups
  // quiet, and nothing else is invented to fill them.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await openTasksFixture(page, `${fixtureUrl}?theme=dark&state=live&tasks=scheduled`);
    const m = await measureTasks(page);
    assert.deepEqual(m.groupTitles, ['Waiting on you', 'Running', 'Scheduled', 'Done'],
      `tasks scheduled-only: order ${JSON.stringify(m.groupTitles)}`);
    assert.equal(m.groups[2].rows.length, 2, 'tasks scheduled-only: scheduled rows');
    assert.match(m.groups[0].emptyText, /Nothing is waiting on you/, 'tasks scheduled-only: waiting empty');
    assert.match(m.groups[1].emptyText, /Nothing is running/, 'tasks scheduled-only: running empty');
    await page.close();
    scenarios += 1;
  }

  // Empty record: every group quiet, Scheduled with its own line.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await openTasksFixture(page, `${fixtureUrl}?theme=dark&state=live&tasks=empty`);
    const m = await measureTasks(page);
    assert.match(m.groups[2].emptyText, /Nothing is scheduled\./, 'tasks empty: scheduled empty line');
    assert.equal(m.groups[2].rows.length, 0, 'tasks empty: scheduled rows rendered');
    await page.close();
    scenarios += 1;
  }

  // Guests: the drawer shows the sign-in line and the session makes
  // zero agent calls, automations included.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await openTasksFixture(page, `${fixtureUrl}?theme=dark&state=live&guest=1`);
    const m = await measureTasks(page);
    assert.match(m.panelText, /Sign in to see your tasks/, 'tasks guest: sign-in line missing');
    assert.equal(m.fetchCalls.filter(path => path.indexOf('/api/agent/') === 0).length, 0,
      `tasks guest: agent calls made ${JSON.stringify(m.fetchCalls)}`);
    await page.close();
    scenarios += 1;
  }

  console.log(`Agent Tasks record: ${scenarios} scenarios passed ` +
    `(${THEMES.length} themes x mixed x ${VIEWPORTS.length} viewports, plus expansion, ` +
    `scheduled-only, empty, and guest).`);
  return scenarios;
}

async function measureProjectsYou(page) {
  return page.evaluate(() => {
    const text = el => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '');
    const lines = el => {
      if (!el) return { height: 0, lineHeight: 0 };
      const style = getComputedStyle(el);
      return { height: el.clientHeight, lineHeight: Number.parseFloat(style.lineHeight) || 0 };
    };
    const rows = [...document.querySelectorAll('#projectsRoot .cvp-row')].map(row => {
      const name = row.querySelector('.cvp-switch-name');
      const box = lines(name);
      return {
        name: text(name),
        meta: text(row.querySelector('.cvp-row-meta')),
        titleAttr: name ? name.getAttribute('title') : null,
        buttonTitle: row.getAttribute('title'),
        ariaLabel: row.getAttribute('aria-label'),
        chevron: Boolean(row.querySelector('.cvp-row-chevron')),
        nameHeight: box.height,
        nameLineHeight: box.lineHeight,
      };
    });
    const tiles = [...document.querySelectorAll('#projectsRoot .cvp-artifact')].map(tile => {
      const title = tile.querySelector('.cvp-artifact-title');
      const box = lines(title);
      const open = tile.querySelector('[data-cvp-open-library]');
      return {
        title: text(title),
        titleAttr: title ? title.getAttribute('title') : null,
        titleHeight: box.height,
        titleLineHeight: box.lineHeight,
        openLabel: open ? open.getAttribute('aria-label') : null,
        kind: text(tile.querySelector('.cvp-artifact-kind')),
        meta: text(tile.querySelector('.cvp-artifact-meta')),
      };
    });
    const books = [...document.querySelectorAll('#libraryRoot .cvl-book')].map(book => {
      const title = book.querySelector('.cvl-book-title');
      const box = lines(title);
      const open = book.querySelector('[data-cvl-open]');
      return {
        titleAttr: title ? title.getAttribute('title') : null,
        titleHeight: box.height,
        titleLineHeight: box.lineHeight,
        openLabel: open ? open.getAttribute('aria-label') : null,
      };
    });
    const youRows = [...document.querySelectorAll('#youRoot [data-connections-root] .cv-you-row')]
      .map(row => [...row.children].map(text));
    const settingsRows = [...document.querySelectorAll('[data-cat-you-connections] .cat-you-row')]
      .map(row => [...row.querySelectorAll('.settings-label')].map(text));
    return {
      rows,
      tiles,
      books,
      youRows,
      settingsRows,
      youText: text(document.querySelector('#youRoot')),
      projectsText: text(document.querySelector('#projectsRoot')),
      libraryText: text(document.querySelector('#libraryRoot')),
      shelfText: text(document.querySelector('#projectsRoot [data-cvp-library]')),
      memoryItems: document.querySelectorAll('#youRoot .cv-memory-item').length,
      memoryControls: Boolean(document.querySelector('#youRoot [data-memory-edit]'))
        && Boolean(document.querySelector('#youRoot [data-memory-delete]')),
      youConnect: Boolean(document.querySelector('#youRoot [data-connections-connect]')),
      fetchCalls: window.__fetchCalls || [],
      longProjectName: window.__longProjectName || '',
      longTitle: window.__longTitle || '',
      documentScrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    };
  });
}

async function openProjectsYou(page, query) {
  await page.goto(`${projectsYouFixtureUrl}?${query}`, { waitUntil: 'load' });
  await page.waitForFunction(() => {
    const you = document.querySelector('#youRoot [data-connections-root]');
    const settings = document.querySelector('[data-cat-you-connections]');
    return you && you.textContent.trim().length > 0
      && settings && settings.querySelector('.cat-you-row');
  }, { timeout: 8000 });
  await page.waitForTimeout(200);
}

async function runProjectsYouScenarios(browser) {
  let scenarios = 0;
  // Full data, partial Google scopes, every viewport in both
  // appearances: project rows carry real fields only, artifact titles
  // are bounded everywhere, and both You surfaces derive the same
  // capability lines from the one Google record.
  for (const theme of THEMES) {
    for (const viewport of VIEWPORTS) {
      const label = `projects-you ${theme}/full-partial @ ${viewport.name}`;
      const page = await browser.newPage({ viewport });
      await openProjectsYou(page, `theme=${theme}&state=full&google=partial`);
      const m = await measureProjectsYou(page);
      assert.equal(m.rows.length, 3, `${label}: project rows ${m.rows.length}`);
      assert.equal(m.rows[0].name, 'Ask Crump', `${label}: first row name`);
      assert.match(m.rows[0].meta, /Product/, `${label}: first row meta "${m.rows[0].meta}"`);
      assert.match(m.rows[2].meta, /Sports media/, `${label}: third row meta`);
      assert.ok(m.rows.every(row => row.chevron), `${label}: chevron missing`);
      assert.doesNotMatch(m.projectsText, /\d+ notes|\d+ artifacts|\d+ character locks/i,
        `${label}: invented counts in Projects`);
      // The long project name is bounded to two lines; the full name
      // stays on the title attribute and the row's aria-label.
      const longRow = m.rows[1];
      assert.equal(longRow.name, m.longProjectName, `${label}: long row name`);
      assert.ok(longRow.nameHeight <= longRow.nameLineHeight * 2 + 6,
        `${label}: long name height ${longRow.nameHeight} > 2 lines (${longRow.nameLineHeight})`);
      assert.equal(longRow.buttonTitle, m.longProjectName, `${label}: row title attribute`);
      assert.equal(longRow.ariaLabel, m.longProjectName, `${label}: row aria-label`);
      // Library shelf inside Projects: bounded tiles, full title
      // accessible on the tile and its Open control.
      assert.equal(m.tiles.length, 3, `${label}: library tiles ${m.tiles.length}`);
      const longTile = m.tiles[0];
      assert.equal(longTile.titleAttr, m.longTitle, `${label}: tile title attribute`);
      assert.ok(longTile.titleHeight <= longTile.titleLineHeight * 2 + 6,
        `${label}: tile title height ${longTile.titleHeight} > 2 lines (${longTile.titleLineHeight}) at ${viewport.name}`);
      assert.ok(longTile.openLabel && longTile.openLabel.includes(m.longTitle),
        `${label}: tile open aria-label "${longTile.openLabel}"`);
      assert.match(longTile.kind, /Created with Crump/, `${label}: tile kind "${longTile.kind}"`);
      // Full-screen Library: the same bounding on its book cards.
      assert.equal(m.books.length, 3, `${label}: library books ${m.books.length}`);
      assert.equal(m.books[0].titleAttr, m.longTitle, `${label}: book title attribute`);
      assert.ok(m.books[0].titleHeight <= m.books[0].titleLineHeight * 2 + 6,
        `${label}: book title height ${m.books[0].titleHeight} > 2 lines`);
      assert.ok(m.books[0].openLabel && m.books[0].openLabel.includes(m.longTitle),
        `${label}: book open aria-label "${m.books[0].openLabel}"`);
      // You, single model: partial scopes (gmail.readonly only) render
      // the account and exactly one derived capability — no Calendar,
      // no Send — identically on the You view and the Settings mount.
      for (const [surface, rows] of [['you', m.youRows], ['settings', m.settingsRows]]) {
        assert.deepEqual(rows[0], ['Google', 'gregory@example.com'],
          `${label}: ${surface} google row ${JSON.stringify(rows[0])}`);
        assert.deepEqual(rows.slice(1), [['Gmail', 'Read']],
          `${label}: ${surface} capability lines ${JSON.stringify(rows)}`);
      }
      assert.equal(m.memoryItems, 1, `${label}: memory items`);
      assert.equal(m.memoryControls, true, `${label}: memory edit/delete controls`);
      assert.ok(m.documentScrollWidth <= viewport.width,
        `${label}: document scrollWidth ${m.documentScrollWidth} > ${viewport.width}`);
      scenarios += 1;
      await page.close();
    }
  }

  // Full scopes at phone width: every granted capability line renders.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await openProjectsYou(page, 'theme=dark&state=full&google=full');
    const m = await measureProjectsYou(page);
    assert.deepEqual(m.youRows.slice(1), [['Gmail', 'Read'], ['Gmail', 'Send'], ['Calendar', 'Read/write']],
      `projects-you full scopes: you lines ${JSON.stringify(m.youRows)}`);
    assert.deepEqual(m.settingsRows.slice(1), [['Gmail', 'Read'], ['Gmail', 'Send'], ['Calendar', 'Read/write']],
      `projects-you full scopes: settings lines ${JSON.stringify(m.settingsRows)}`);
    await page.close();
    scenarios += 1;
  }

  // Disconnected + empty: no capability lines anywhere, the Library
  // states are the honest empty states, and Connect is offered.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await openProjectsYou(page, 'theme=dark&state=empty&google=disconnected');
    const m = await measureProjectsYou(page);
    assert.deepEqual(m.youRows, [['Google', 'Not connected']],
      `projects-you disconnected: you rows ${JSON.stringify(m.youRows)}`);
    assert.deepEqual(m.settingsRows, [['Google', 'Not connected']],
      `projects-you disconnected: settings rows ${JSON.stringify(m.settingsRows)}`);
    assert.equal(m.youConnect, true, 'projects-you disconnected: connect action missing');
    assert.match(m.projectsText, /Give your work a place to continue/, 'projects-you empty: projects empty state');
    assert.match(m.shelfText, /Nothing finished yet/, 'projects-you empty: shelf empty line');
    assert.match(m.libraryText, /Your shelf is ready/, 'projects-you empty: library empty state');
    await page.close();
    scenarios += 1;
  }

  // Guest: signed-out rows on both You surfaces and zero fetches for
  // projects, library, or the Google record.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await openProjectsYou(page, 'theme=dark&state=full&guest=1');
    const m = await measureProjectsYou(page);
    assert.deepEqual(m.youRows, [['Google', 'Not connected']],
      `projects-you guest: you rows ${JSON.stringify(m.youRows)}`);
    assert.equal(m.fetchCalls.filter(path => path.indexOf('/api/connections/') === 0).length, 0,
      `projects-you guest: connection fetches ${JSON.stringify(m.fetchCalls)}`);
    assert.equal(m.fetchCalls.filter(path => path.indexOf('/api/projects') === 0).length, 0,
      `projects-you guest: project fetches ${JSON.stringify(m.fetchCalls)}`);
    // The Projects shelf itself stays signed-out and fetches nothing:
    // the single library call in this run is the full-screen Library
    // view's own pre-existing currentUser.id gate.
    assert.match(m.shelfText, /Sign in to see your finished artifacts/,
      `projects-you guest: shelf signed-out line "${m.shelfText}"`);
    assert.ok(m.fetchCalls.filter(path => path.indexOf('/api/library/') === 0).length <= 1,
      `projects-you guest: library fetches ${JSON.stringify(m.fetchCalls)}`);
    await page.close();
    scenarios += 1;
  }

  console.log(`Reorg Projects/Library/You: ${scenarios} scenarios passed ` +
    `(${THEMES.length} themes x full/partial x ${VIEWPORTS.length} viewports, plus full scopes, ` +
    `disconnected/empty, and guest).`);
  return scenarios;
}

async function runChatScenarios(browser) {
  let scenarios = 0;
  const CHAT_STATES = ['approval', 'live', 'both', 'none', 'result'];
  for (const theme of THEMES) {
    for (const state of CHAT_STATES) {
      for (const viewport of VIEWPORTS) {
        const label = `chat ${theme}/${state} @ ${viewport.name}`;
        const page = await browser.newPage({ viewport });
        await page.goto(`${chatFixtureUrl}?theme=${theme}&state=${state}`, { waitUntil: 'load' });
        await page.waitForTimeout(250);
        const m = await measureChat(page);
        // The composer bar is plus, input, and send only — in order —
        // at every size, and nothing the section renders overlaps it.
        assert.deepEqual(m.composerChildIds, ['attachBtn', 'userInput', 'sendButton'],
          `${label}: composer bar ${JSON.stringify(m.composerChildIds)}`);
        assert.ok(m.documentScrollWidth <= viewport.width,
          `${label}: document scrollWidth ${m.documentScrollWidth} > ${viewport.width}`);
        assert.equal(m.todayVisible, false, `${label}: Today surface visible in a conversation`);
        if (state === 'none') {
          // No work in the open conversation: no section, no cards, no
          // placeholder — even though another conversation has work.
          assert.equal(m.sectionVisible, false, `${label}: section rendered with no work`);
          assert.equal(m.cardCount, 0, `${label}: cards rendered with no work`);
        } else {
          assert.equal(m.sectionVisible, true, `${label}: chat work section missing`);
          assert.ok(m.sectionBottom <= m.dockTop + 0.6,
            `${label}: section overlaps the composer dock (${m.sectionBottom} > ${m.dockTop})`);
          assert.ok(m.containerBottom <= m.sectionBottom + 0.6 || m.containerBottom <= m.dockTop + 0.6,
            `${label}: message list escapes below the section`);
          assert.ok(m.sectionRight <= viewport.width + 0.6,
            `${label}: section escapes the viewport`);
          assert.ok(m.sectionScrollWidth <= m.sectionClientWidth + 1,
            `${label}: section clipped ${m.sectionScrollWidth} > ${m.sectionClientWidth}`);
          // Scoping: the other conversation's work never appears here.
          assert.doesNotMatch(m.sectionText, /other@example\.com|For the other conversation/,
            `${label}: other conversation's work leaked into the section`);
          // One-card emphasis: exactly one full card in the section.
          assert.equal(m.cardCount, 1, `${label}: full cards in section ${m.cardCount}`);
          assert.equal(m.rowIsCard, false, `${label}: a secondary row renders as a card`);
        }
        if (state === 'approval' || state === 'both') {
          // The primary card is this conversation's pending approval,
          // rendered by the shared builder: the exact action leads
          // (the long recipient list unwrapped-clipped at 320px too),
          // the frozen payload starts collapsed, and the credit line
          // precedes the decision buttons.
          assert.match(m.exactText, /alexandria\.longaddress/, `${label}: exact summary "${m.exactText}"`);
          assert.match(m.exactText, /Quarterly planning notes/, `${label}: exact subject "${m.exactText}"`);
          assert.ok(m.exactScrollWidth <= m.exactClientWidth + 1,
            `${label}: exact summary clipped ${m.exactScrollWidth} > ${m.exactClientWidth}`);
          assert.equal(m.detailPresent, true, `${label}: approval detail missing`);
          assert.equal(m.detailVisible, false, `${label}: approval detail must start collapsed`);
          assert.match(m.creditText, /2 credits/, `${label}: credit line "${m.creditText}"`);
          assert.equal(m.creditBeforeActions, true, `${label}: credit line must precede the buttons`);
          assert.equal(m.approvePresent, true, `${label}: Approve button missing`);
        }
        if (state === 'live') {
          assert.match(m.stepText, /Current step/, `${label}: live run step line "${m.stepText}"`);
          assert.equal(m.approvePresent, false, `${label}: approval rendered in the live-only state`);
        }
        if (state === 'both') {
          // The live run and the finished result sit behind the one
          // primary card as quiet rows, never as equal-weight cards.
          assert.equal(m.rowTexts.length, 2, `${label}: secondary rows ${JSON.stringify(m.rowTexts)}`);
          assert.match(m.rowTexts.join(' '), /Book a calendar event/, `${label}: live run row`);
          assert.match(m.rowTexts.join(' '), /Found 3 threads/, `${label}: result row`);
        }
        if (state === 'result') {
          assert.match(m.primaryText, /Found 3 threads about the launch checklist\./,
            `${label}: result card text "${m.primaryText}"`);
        }
        scenarios += 1;
        await page.close();
      }
    }
  }

  // Guests: no section, and zero agent-endpoint calls at all.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(`${chatFixtureUrl}?theme=dark&state=guest`, { waitUntil: 'load' });
    await page.waitForTimeout(250);
    const m = await measureChat(page);
    assert.equal(m.sectionVisible, false, 'chat guest: section rendered for a guest');
    assert.equal(m.cardCount, 0, 'chat guest: cards rendered for a guest');
    assert.equal(m.fetchCalls.filter(path => path.indexOf('/api/agent/') === 0).length, 0,
      `chat guest: agent calls made ${JSON.stringify(m.fetchCalls)}`);
    await page.close();
    scenarios += 1;
  }

  // Today view: the same loaded work renders no chat section while
  // the launchpad home state is up — Chat cards belong to Chat only.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(`${chatFixtureUrl}?theme=dark&state=both&view=today`, { waitUntil: 'load' });
    await page.waitForTimeout(250);
    const m = await measureChat(page);
    assert.equal(m.sectionVisible, false, 'chat today-view: section rendered on Today');
    assert.equal(m.cardCount, 0, 'chat today-view: cards rendered on Today');
    await page.close();
    scenarios += 1;
  }

  // Conversation switch: opening the other conversation re-scopes
  // the section to that conversation's own pending approval (its
  // live run sits behind it as a quiet row), and the first
  // conversation's approval leaves the surface.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(`${chatFixtureUrl}?theme=dark&state=both`, { waitUntil: 'load' });
    await page.waitForTimeout(250);
    await page.evaluate(() => {
      window.currentChatId = 'conv-b';
      window.dispatchEvent(new CustomEvent('crump:conversation-opened', { detail: { chatId: 'conv-b', fresh: false } }));
    });
    await page.waitForTimeout(250);
    const m = await measureChat(page);
    assert.equal(m.sectionVisible, true, 'chat switch: section missing for conv-b');
    assert.equal(m.cardCount, 1, 'chat switch: full cards for conv-b');
    assert.match(m.exactText, /other@example\.com/, `chat switch: primary exact "${m.exactText}"`);
    assert.match(m.rowTexts.join(' '), /Act in the browser/, 'chat switch: conv-b live run row');
    assert.doesNotMatch(m.sectionText, /alexandria\.longaddress/,
      'chat switch: conv-a approval still rendered');
    await page.close();
    scenarios += 1;
  }

  // The primary approval's detail toggle opens the frozen payload.
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(`${chatFixtureUrl}?theme=dark&state=approval`, { waitUntil: 'load' });
    await page.waitForTimeout(250);
    await page.click('#catChatWork .cat-detail-toggle');
    await page.waitForTimeout(80);
    const m = await measureChat(page);
    assert.equal(m.detailVisible, true, 'chat detail: frozen payload did not expand');
    await page.close();
    scenarios += 1;
  }

  console.log(`Agent Chat cards: ${scenarios} scenarios passed ` +
    `(${THEMES.length} themes x 5 states x ${VIEWPORTS.length} viewports, plus guest, ` +
    `Today-view, conversation-switch, and detail interactions).`);
  return scenarios;
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

    scenarios += await runTasksScenarios(browser);
    scenarios += await runChatScenarios(browser);
    scenarios += await runProjectsYouScenarios(browser);
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
