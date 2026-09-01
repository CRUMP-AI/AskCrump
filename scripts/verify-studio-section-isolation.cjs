const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const projectId = '00000000-0000-4000-8000-000000000071';
const sections = [
  {name: 'video', title: 'Video Studio', label: 'Ask Crump Video Studio'},
  {name: 'library', title: 'Library', label: 'Ask Crump Library'},
  {name: 'manuscripts', title: 'Manuscripts', label: 'Ask Crump Manuscripts'},
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

    await page.evaluate(name => window.CrumpProduct53.open(name), section.name);
    await page.waitForFunction(name => (
      document.getElementById('crump53Sheet')?.dataset.crump53Section === name
    ), section.name);

    const actual = await page.evaluate(() => {
      const sheet = document.getElementById('crump53Sheet');
      const projectsPanel = document.querySelector('[data-crump53-panel="projects"]');
      return {
        section: sheet?.dataset.crump53Section || '',
        title: document.getElementById('crump53WorkspaceTitle')?.textContent || '',
        label: sheet?.getAttribute('aria-label') || '',
        projectBackHidden: Boolean(document.getElementById('crump53ProjectBack')?.hidden),
        projectView: sheet?.dataset.projectView || '',
        projectPanelOpen: Boolean(projectsPanel?.classList.contains('is-project-open')),
        routeProject: new URLSearchParams(location.search).get('project') || '',
      };
    });
    assert.deepEqual(actual, {
      section: section.name,
      title: section.title,
      label: section.label,
      projectBackHidden: true,
      projectView: 'index',
      projectPanelOpen: false,
      routeProject: '',
    });
    transitions.push(actual);
  }

  assert.deepEqual(errors, []);
  assert.equal(await page.locator('#fixtureErrors').textContent(), '0');
  return {viewport, transitions, errors};
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
