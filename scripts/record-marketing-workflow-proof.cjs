const assert = require('node:assert/strict');
const {existsSync, mkdirSync} = require('node:fs');
const {join, resolve} = require('node:path');
const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

const baseUrl = process.argv[2] || 'http://127.0.0.1:8765';
const outputDir = resolve(process.argv[3] || 'artifacts/marketing-workflow-proof');
const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
const fixtureProjectId = '00000000-0000-4000-8000-000000000072';

(async () => {
  mkdirSync(outputDir, {recursive: true});
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const context = await browser.newContext({
    viewport: {width: 390, height: 844},
    deviceScaleFactor: 1,
    colorScheme: 'dark',
    recordVideo: {dir: outputDir, size: {width: 390, height: 844}},
  });
  const page = await context.newPage();
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));

  await page.goto(`${baseUrl}/tests/fixtures/marketing-workflow-proof.html`, {waitUntil: 'networkidle'});
  await page.waitForFunction(() => Boolean(window.CrumpProduct53?.openProject && window.CrumpFileTools?.open));
  await page.waitForTimeout(650);

  const request = 'Turn these rough notes into a concise six-week launch plan and an editable PowerPoint.';
  await page.getByRole('textbox', {name: 'Message Crump'}).fill(request);
  await page.waitForTimeout(700);
  await page.getByRole('button', {name: 'Send message'}).click();
  await page.waitForFunction(() => document.querySelector('[data-artifact-project]')?.textContent === 'Keep in a Project');
  await page.waitForTimeout(1400);

  const keepButton = page.locator('[data-artifact-project]');
  assert.equal(await keepButton.getAttribute('aria-label'), 'Keep Six-week launch plan and its source conversation together in a private Project');
  await keepButton.click();
  await page.waitForFunction(() => document.querySelector('[data-artifact-project]')?.textContent === 'Open Project');
  await page.waitForTimeout(1200);
  await keepButton.click();

  const projectOpenState = await page.evaluate(() => {
    const button = document.querySelector('[data-artifact-project]');
    const studio = document.querySelector('#crump53Studio');
    const dialog = document.querySelector('#crump53Sheet');
    const studioStyle = studio ? getComputedStyle(studio) : null;
    const dialogRect = dialog?.getBoundingClientRect();
    return {
      buttonLabel: button?.textContent || '',
      projectId: button?.dataset?.projectId || '',
      studioExists: Boolean(studio),
      studioHidden: studio?.hidden ?? null,
      studioDisplay: studioStyle?.display || '',
      studioVisibility: studioStyle?.visibility || '',
      dialogRole: dialog?.getAttribute('role') || '',
      dialogLabel: dialog?.getAttribute('aria-label') || '',
      dialogWidth: dialogRect?.width || 0,
      dialogHeight: dialogRect?.height || 0,
      activeProjectId: window.CrumpProduct53?.projectTarget?.()?.id || '',
      unexpectedRequests: window.__fixture.unexpectedRequests.slice(),
      fixtureErrors: window.__fixture.errors.slice(),
    };
  });
  assert.equal(projectOpenState.buttonLabel, 'Open Project');
  assert.equal(projectOpenState.projectId, fixtureProjectId);
  assert.equal(projectOpenState.studioExists, true);
  assert.equal(projectOpenState.studioHidden, false, `Open Project left the studio hidden: ${JSON.stringify(projectOpenState)}`);
  assert.equal(projectOpenState.studioDisplay, 'grid', `Open Project did not display the studio: ${JSON.stringify(projectOpenState)}`);
  assert.equal(projectOpenState.dialogRole, 'dialog');
  assert.equal(projectOpenState.dialogLabel, 'Ask Crump Project: Launch planning');
  assert.ok(projectOpenState.dialogWidth > 0 && projectOpenState.dialogHeight > 0,
    `Open Project did not render a visible dialog box: ${JSON.stringify(projectOpenState)}`);

  const projectDialog = page.locator('#crump53Sheet');
  await projectDialog.waitFor({state: 'visible'});
  await page.waitForFunction(() => document.querySelector('#crump53ProjectName')?.value === 'Launch planning');
  await page.waitForFunction(() => document.querySelector('[data-open-project-file]'));
  await page.waitForTimeout(1500);

  const fileButton = page.locator('[data-open-project-file]').first();
  assert.match(await fileButton.innerText(), /six-week-launch-plan\.pptx/i);
  await fileButton.click();
  const viewer = page.locator('.crump50-file-viewer');
  await viewer.waitFor({state: 'visible'});
  assert.equal(await viewer.locator('#crump50FileViewerTitle').textContent(), 'six-week-launch-plan.pptx');
  assert.equal(await viewer.locator('.crump50-file-viewer-placeholder strong').textContent(), 'Editable PowerPoint ready');
  await page.waitForTimeout(2200);

  const evidence = await page.evaluate(() => ({
    title: document.querySelector('#proofTitle')?.textContent || '',
    saved: window.__fixture.saved,
    requests: window.__fixture.requests.map(item => ({path: item.path, method: item.method, role: item.body?.role || null})),
    analytics: window.__fixture.analytics,
    unexpectedRequests: window.__fixture.unexpectedRequests,
    fixtureErrors: window.__fixture.errors,
    viewerTitle: document.querySelector('#crump50FileViewerTitle')?.textContent || '',
    viewerReady: document.querySelector('.crump50-file-viewer-placeholder strong')?.textContent || '',
    overflow: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
  }));

  assert.equal(evidence.title, 'Launch plan');
  assert.equal(evidence.saved, true);
  assert.deepEqual(evidence.requests.map(item => item.method), ['POST', 'POST']);
  assert.equal(evidence.requests[1].role, 'generated_document');
  assert.equal(evidence.unexpectedRequests.length, 0);
  assert.equal(evidence.fixtureErrors.length, 0);
  assert.equal(evidence.viewerTitle, 'six-week-launch-plan.pptx');
  assert.equal(evidence.viewerReady, 'Editable PowerPoint ready');
  assert.ok(evidence.overflow <= 1, `workflow overflowed the phone viewport by ${evidence.overflow}px`);
  assert.deepEqual(errors, []);

  const finalScreenshot = join(outputDir, 'ask-crump-continuity-proof-final.png');
  await page.screenshot({path: finalScreenshot, fullPage: false});
  const video = page.video();
  await page.close();
  const finalVideo = join(outputDir, 'ask-crump-continuity-proof.webm');
  if (video) await video.saveAs(finalVideo);
  await context.close();
  await browser.close();

  assert.ok(existsSync(finalScreenshot), 'final proof screenshot was not written');
  assert.ok(existsSync(finalVideo), 'continuous proof video was not written');
  process.stdout.write(`${JSON.stringify({projectOpenState, evidence, errors, finalScreenshot, finalVideo}, null, 2)}\n`);
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
