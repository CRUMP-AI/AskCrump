const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

const baseUrl = process.env.ASKCRUMP_FIXTURE_ORIGIN || 'http://127.0.0.1:8765';
const fixture = `${baseUrl}/tests/fixtures/reorg-projects-you.html`;

const collect = async (page) => page.evaluate(() => ({
  projectsHeading: document.querySelector('#projectsRoot h2')?.textContent || '',
  projectsText: document.getElementById('projectsRoot')?.textContent || '',
  projectsPanelRole: document.querySelector('#projectsRoot .cvp-panel')?.getAttribute('role') || '',
  projectsHasRetry: Boolean(document.querySelector('#projectsRoot [data-cvp-retry]')),
  projectsHasCreate: Boolean(document.querySelector('#projectsRoot [data-cvp-create-account]')),
  shelfText: document.querySelector('#projectsRoot [data-cvp-library]')?.textContent || '',
  libraryHeading: document.querySelector('#libraryRoot h2')?.textContent || '',
  libraryText: document.getElementById('libraryRoot')?.textContent || '',
  libraryPanelRole: document.querySelector('#libraryRoot .cvl-panel')?.getAttribute('role') || '',
  libraryHasRetry: Boolean(document.querySelector('#libraryRoot [data-cvl-retry]')),
  libraryHasCreate: Boolean(document.querySelector('#libraryRoot [data-cvl-create-account]')),
  fetchCalls: window.__fetchCalls || [],
  horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
}));

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  try {
  const gateDark = await browser.newPage({viewport: {width: 390, height: 844}});
  const gateDarkErrors = [];
  gateDark.on('console', message => { if (message.type() === 'error') gateDarkErrors.push(message.text()); });
  gateDark.on('pageerror', error => gateDarkErrors.push(error.message));
  await gateDark.goto(`${fixture}?state=gate&session=guest-account&theme=dark`, {waitUntil: 'networkidle'});
  await gateDark.waitForFunction(() => document.querySelector('#projectsRoot h2')?.textContent === 'Projects need an account.');
  await gateDark.waitForFunction(() => document.querySelector('#libraryRoot h2')?.textContent === 'The Library needs an account.');
  const gateDarkState = await collect(gateDark);
  // Snapshot errors before the click: the navigation target 404s on the
  // fixture server, and that expected 404 lands in the console log.
  const gateDarkErrorsBeforeClick = [...gateDarkErrors];
  // The fixture stacks every root and the settings mount in one flat page,
  // so the settings sheet covers the button's hit point and a coordinate
  // click lands on the sheet instead. dispatchEvent targets the button
  // itself; the navigation target is what is under test. waitUntil
  // 'commit': the fixture server answers /app with a 404 page, and only
  // the navigation target is asserted.
  await Promise.all([
    gateDark.waitForURL(/\/app\?signup=1&source=projects-gate&plan=free/, {waitUntil: 'commit'}),
    gateDark.locator('#projectsRoot [data-cvp-create-account]').dispatchEvent('click'),
  ]);
  const gateDarkUrl = gateDark.url();
  await gateDark.close();

  const gateLight = await browser.newPage({viewport: {width: 390, height: 844}});
  const gateLightErrors = [];
  gateLight.on('console', message => { if (message.type() === 'error') gateLightErrors.push(message.text()); });
  gateLight.on('pageerror', error => gateLightErrors.push(error.message));
  await gateLight.goto(`${fixture}?state=gate&session=guest-account&theme=light`, {waitUntil: 'networkidle'});
  await gateLight.waitForFunction(() => document.querySelector('#projectsRoot h2')?.textContent === 'Projects need an account.');
  await gateLight.waitForFunction(() => document.querySelector('#libraryRoot h2')?.textContent === 'The Library needs an account.');
  const gateLightState = await collect(gateLight);
  const gateLightErrorsBeforeClick = [...gateLightErrors];
  await Promise.all([
    gateLight.waitForURL(/\/app\?signup=1&source=library-gate&plan=free/, {waitUntil: 'commit'}),
    gateLight.locator('#libraryRoot [data-cvl-create-account]').dispatchEvent('click'),
  ]);
  const gateLightUrl = gateLight.url();
  await gateLight.close();

  const errorPage = await browser.newPage({viewport: {width: 390, height: 844}});
  const errorErrors = [];
  errorPage.on('console', message => { if (message.type() === 'error') errorErrors.push(message.text()); });
  errorPage.on('pageerror', error => errorErrors.push(error.message));
  await errorPage.goto(`${fixture}?state=error&session=guest-account&theme=dark`, {waitUntil: 'networkidle'});
  await errorPage.waitForFunction(() => document.querySelector('#projectsRoot h2')?.textContent === 'Projects could not load.');
  await errorPage.waitForFunction(() => document.querySelector('#libraryRoot h2')?.textContent === 'The Library could not load.');
  const errorState = await collect(errorPage);
  await errorPage.close();

  const signedOutPage = await browser.newPage({viewport: {width: 390, height: 844}});
  const signedOutErrors = [];
  signedOutPage.on('console', message => { if (message.type() === 'error') signedOutErrors.push(message.text()); });
  signedOutPage.on('pageerror', error => signedOutErrors.push(error.message));
  await signedOutPage.goto(`${fixture}?guest=1&theme=dark`, {waitUntil: 'networkidle'});
  await signedOutPage.waitForFunction(() => document.querySelector('#projectsRoot h2')?.textContent === 'Sign in to see your projects.');
  await signedOutPage.waitForFunction(() => document.querySelector('#libraryRoot h2')?.textContent === 'Sign in to open your library.');
  const signedOutState = await collect(signedOutPage);
  await signedOutPage.close();

  await browser.close();

  const gateFailed = (state, errors) => (
    state.projectsHeading !== 'Projects need an account.'
    || state.projectsPanelRole !== 'status'
    || !state.projectsHasCreate
    || state.projectsHasRetry
    || state.projectsText.includes('could not load')
    || state.shelfText.trim() !== 'Create a free account to keep finished artifacts in your Library.'
    || state.libraryHeading !== 'The Library needs an account.'
    || state.libraryPanelRole !== 'status'
    || !state.libraryHasCreate
    || state.libraryHasRetry
    || state.libraryText.includes('could not load')
    || !state.fetchCalls.some(call => String(call).indexOf('/api/projects') === 0)
    || !state.fetchCalls.some(call => String(call).indexOf('/api/library/books') === 0)
    || state.horizontalOverflow
    || errors.length
  );
  const failed = gateFailed(gateDarkState, gateDarkErrorsBeforeClick)
    || !gateDarkUrl.includes('/app?signup=1&source=projects-gate&plan=free')
    || gateFailed(gateLightState, gateLightErrorsBeforeClick)
    || !gateLightUrl.includes('/app?signup=1&source=library-gate&plan=free')
    || errorState.projectsHeading !== 'Projects could not load.'
    || errorState.projectsPanelRole !== 'alert'
    || !errorState.projectsHasRetry
    || errorState.projectsHasCreate
    || errorState.projectsText.includes('needs an account')
    || errorState.shelfText.trim() !== 'Your library could not load just now.'
    || errorState.libraryHeading !== 'The Library could not load.'
    || errorState.libraryPanelRole !== 'alert'
    || !errorState.libraryHasRetry
    || errorState.libraryHasCreate
    || errorState.libraryText.includes('needs an account')
    || errorState.horizontalOverflow
    || errorErrors.length
    || signedOutState.projectsHeading !== 'Sign in to see your projects.'
    || signedOutState.shelfText.trim() !== 'Sign in to see your finished artifacts.'
    || signedOutState.libraryHeading !== 'Sign in to open your library.'
    || signedOutState.fetchCalls.some(call => String(call).indexOf('/api/projects') === 0)
    || signedOutState.fetchCalls.some(call => String(call).indexOf('/api/library/books') === 0)
    || signedOutState.horizontalOverflow
    || signedOutErrors.length;
  if (failed) {
    throw new Error(JSON.stringify({
      gateDarkState, gateDarkErrors, gateDarkUrl,
      gateLightState, gateLightErrors, gateLightUrl,
      errorState, errorErrors, signedOutState, signedOutErrors,
    }));
  }
  process.stdout.write(`${JSON.stringify({gateDarkState, gateDarkUrl, gateLightState, gateLightUrl, errorState, signedOutState})}\n`);
  } finally {
    await browser.close().catch(() => {});
  }
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
