const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const projectId = '00000000-0000-4000-8000-000000000071';
const sections = [
  {name: 'video', title: 'Video Studio', label: 'Ask Crump Video Studio', closeLabel: 'Close Video Studio'},
  {name: 'library', title: 'Library', label: 'Ask Crump Library', closeLabel: 'Close Library'},
  {name: 'manuscripts', title: 'Manuscripts', label: 'Ask Crump Manuscripts', closeLabel: 'Close Manuscripts'},
];

async function inspect(page, viewport) {
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));

  await page.goto(
    'http://127.0.0.1:8765/tests/fixtures/project-open-navigation.html?hold=1',
    {waitUntil: 'load'},
  );
  await page.waitForFunction(() => (
    document.getElementById('crump53Sheet')?.dataset.projectView === 'detail'
    && !document.getElementById('crump53ProjectBack')?.hidden
  ));

  const transitions = [];
  for (const section of sections) {
    await page.evaluate(async id => {
      await window.CrumpProduct53.openProject(id);
    }, projectId);
    await page.waitForFunction(id => (
      new URLSearchParams(location.search).get('project') === id
      && document.getElementById('crump53Sheet')?.dataset.projectView === 'detail'
      && !document.getElementById('crump53ProjectBack')?.hidden
    ), projectId);
    assert.equal(
      await page.locator('#crump53Close').getAttribute('aria-label'),
      'Close Project: Launch Operations',
    );

    await page.evaluate(name => window.CrumpProduct53.open(name), section.name);
    await page.waitForFunction(name => (
      document.getElementById('crump53Sheet')?.dataset.crump53Section === name
    ), section.name);

    const actual = await page.evaluate(() => {
      const sheet = document.getElementById('crump53Sheet');
      const projectsPanel = document.querySelector('[data-crump53-panel="projects"]');
      const videoProjectContext = document.getElementById('crump53VideoProjectContext');
      return {
        section: sheet?.dataset.crump53Section || '',
        title: document.getElementById('crump53WorkspaceTitle')?.textContent || '',
        label: sheet?.getAttribute('aria-label') || '',
        closeLabel: document.getElementById('crump53Close')?.getAttribute('aria-label') || '',
        projectBackHidden: Boolean(document.getElementById('crump53ProjectBack')?.hidden),
        projectView: sheet?.dataset.projectView || '',
        projectPanelOpen: Boolean(projectsPanel?.classList.contains('is-project-open')),
        routeProject: new URLSearchParams(location.search).get('project') || '',
        videoProjectVisible: Boolean(videoProjectContext && !videoProjectContext.hidden && videoProjectContext.getClientRects().length),
        videoProjectName: document.getElementById('crump53VideoProjectName')?.textContent || '',
      };
    });
    assert.deepEqual(actual, {
      section: section.name,
      title: section.title,
      label: section.label,
      closeLabel: section.closeLabel,
      projectBackHidden: true,
      projectView: 'index',
      projectPanelOpen: false,
      routeProject: '',
      videoProjectVisible: section.name === 'video',
      videoProjectName: 'Launch Operations',
    });
    if (section.name === 'video') {
      await page.locator('#crump53VideoProjectClear').click();
      await page.waitForFunction(() => document.getElementById('crump53VideoProjectContext')?.hidden);
      const cleared = await page.evaluate(() => ({
        destinationHidden: Boolean(document.getElementById('crump53VideoProjectContext')?.hidden),
        activeProjectChip: Boolean(document.querySelector('.crump53-active-project')),
        status: document.getElementById('crump53VideoStatus')?.textContent || '',
      }));
      assert.deepEqual(cleared, {
        destinationHidden: true,
        activeProjectChip: false,
        status: 'This video will save to your private Files only.',
      });
      actual.filesOnly = cleared;
    }
    transitions.push(actual);
  }

  await page.evaluate(() => window.CrumpProduct53.open('projects'));
  await page.waitForFunction(() => document.getElementById('crump53Sheet')?.dataset.projectView === 'index');
  assert.equal(await page.locator('#crump53Close').getAttribute('aria-label'), 'Close Projects');

  await page.locator('#crump53OpenFiles').click();
  await page.waitForFunction(() => document.getElementById('crump53Sheet')?.dataset.projectView === 'files');
  assert.equal(await page.locator('#crump53Close').getAttribute('aria-label'), 'Close Files');
  assert.equal(await page.locator('#crump53RefreshLibrary').getAttribute('aria-label'), 'Refresh private Files');

  await page.evaluate(() => window.CrumpProduct53.open('projects'));
  await page.locator('#crump53CreateProject').click();
  await page.waitForFunction(() => document.getElementById('crump53Sheet')?.dataset.projectView === 'new');
  assert.equal(await page.locator('#crump53Close').getAttribute('aria-label'), 'Close new Project');

  const staticActionLabels = await page.evaluate(() => ({
    pause: document.getElementById('crump53PauseFullDraft')?.getAttribute('aria-label') || '',
    resume: document.getElementById('crump53ResumeFullDraft')?.getAttribute('aria-label') || '',
    cancel: document.getElementById('crump53CancelFullDraft')?.getAttribute('aria-label') || '',
    save: document.getElementById('crump53SaveSection')?.getAttribute('aria-label') || '',
    draft: document.getElementById('crump53DraftSection')?.getAttribute('aria-label') || '',
    addVideoReference: document.getElementById('crump53AddVideoReference')?.getAttribute('aria-label') || '',
  }));
  assert.deepEqual(staticActionLabels, {
    pause: 'Pause full manuscript draft',
    resume: 'Resume full manuscript draft',
    cancel: 'Cancel full manuscript draft',
    save: 'Save manuscript section',
    draft: 'Draft manuscript section with Crump',
    addVideoReference: 'Add video reference image',
  });

  assert.deepEqual(errors, []);
  assert.equal(await page.locator('#fixtureErrors').textContent(), '0');
  return {viewport, transitions, staticActionLabels, errors};
}

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? {executablePath} : {}),
  });
  const desktopViewport = {width: 1280, height: 800};
  const phoneViewport = {width: 390, height: 844};
  const desktop = await inspect(await browser.newPage({viewport: desktopViewport}), desktopViewport);
  const phone = await inspect(await browser.newPage({viewport: phoneViewport}), phoneViewport);
  await browser.close();
  process.stdout.write(JSON.stringify({desktop, phone}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
