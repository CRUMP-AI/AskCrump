const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8765/tests/fixtures/feature-access-recovery.html', {
    waitUntil: 'load',
  });
  await page.locator('#fixtureProject').click();
  const recoveryButton = page.locator('#crump53ProjectStatus .crump53-feature-recovery button');
  await recoveryButton.waitFor({state: 'visible'});
  assert.equal((await page.evaluate(() => window.__fixture.recoveries.length)), 0);
  await recoveryButton.click();
  await page.waitForFunction(() => window.__fixture.recoveries.length === 1);
  const result = await page.evaluate(() => ({
    status: document.getElementById('crump53ProjectStatus')?.textContent || '',
    requests: window.__fixture.requests,
    recovery: window.__fixture.recoveries[0],
  }));
  const createIndex = result.requests.findIndex(item => item.path === '/api/projects' && item.method === 'POST');
  const shownIndex = result.requests.findIndex(item => item.path === '/api/projects/limit-plan-message/shown' && item.method === 'POST');
  assert.ok(createIndex >= 0);
  assert.ok(shownIndex > createIndex);
  assert.match(result.status, /supports up to 25 active projects/i);
  assert.equal(result.status.includes('supports up to 2 active projects'), false);
  assert.equal(result.recovery.accessCode, 'PROJECT_LIMIT_REACHED');
  assert.equal(result.recovery.source, 'feature_recovery');
  assert.equal(result.recovery.projectLimitPlan.eventName, 'ProjectLimitPlanMessageShown');
  assert.equal(result.recovery.projectLimitPlan.eventKey, 'project-limit-plan-message-shown');
  assert.equal(result.recovery.projectLimitPlan.variant, 'value-specific');
  assert.equal(result.recovery.projectLimitPlan.source, 'recovery_project');
  assert.equal(result.recovery.projectLimitPlan.plan, 'professional');
  assert.equal(result.recovery.projectLimitPlan.detail, 'Projects require a paid plan. Professional supports up to 25 active Projects for $20/month. Review the plan before deciding; nothing changes until checkout is confirmed.');
  assert.equal(result.requests.filter(item => item.path === '/api/projects' && item.method === 'POST').length, 1);
  assert.equal(result.requests.filter(item => item.path === '/api/projects/limit-plan-message/shown' && item.method === 'POST').length, 1);
  assert.equal(result.requests.some(item => item.path.includes('checkout')), false);
  assert.deepEqual(errors, []);
  await browser.close();
  process.stdout.write(JSON.stringify({
    deliveryRecordedBeforeTreatment: true,
    checkoutRequests: 0,
    errors,
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
