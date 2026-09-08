const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const CONTROL = 'Compare monthly plans below before creating another Project. Nothing changes until you choose and confirm.';
const TREATMENT = 'Your two Free Projects stay available. Professional raises the active Project limit to 25 for $20/month. You can keep using Free or review the plan before deciding.';

(async () => {
  const executablePath = process.env.CODEX_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const results = [];
  for (const runtime of ['51', '52']) {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const errors = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:8765/tests/fixtures/project-limit-plan-default-off.html?runtime=${runtime}`, {
      waitUntil: 'load',
    });
    await page.waitForFunction(() => typeof window.showBillingCenter === 'function', null, {timeout: 5000});
    await page.evaluate(() => window.showBillingCenter({accessCode: 'PROJECT_LIMIT_REACHED'}));
    const recovery = page.locator('.billing51-recovery');
    await recovery.waitFor({state: 'visible'});
    const detail = await recovery.locator('p').textContent();
    const title = await recovery.locator('h3').textContent();
    await page.waitForFunction(() => !document.querySelector('.billing51-modal')?.classList.contains('is-loading'));
    assert.equal(title, 'Your active Project limit has been reached.');
    assert.equal(detail, CONTROL);
    assert.equal((await page.locator('body').innerText()).includes(TREATMENT), false);
    assert.deepEqual(errors, []);
    const controlShape = await page.evaluate(control => {
      const modal = document.querySelector('.billing51-modal');
      const links = [...modal.querySelectorAll('a')].map(link => link.getAttribute('href'));
      const buttons = [...modal.querySelectorAll('button')].map(button => button.textContent.trim());
      return {text: modal.innerText.replace(control, '<DETAIL>'), links, buttons};
    }, CONTROL);
    await page.evaluate(() => {
      document.querySelector('.billing51-modal')?.remove();
      document.body.classList.remove('billing51-open');
      window.showBillingCenter({
        accessCode: 'PROJECT_LIMIT_REACHED',
        projectLimitPlan: {
          eligible: true,
          experiment: 'project-limit-plan-copy',
          eventName: 'ProjectLimitPlanMessageShown',
          eventKey: 'project-limit-plan-message-shown',
          source: 'recovery_project',
          plan: 'professional',
          variant: 'value-specific'
        }
      });
    });
    const treatmentRecovery = page.locator('.billing51-recovery');
    await treatmentRecovery.waitFor({state: 'visible'});
    await page.waitForFunction(() => !document.querySelector('.billing51-modal')?.classList.contains('is-loading'));
    assert.equal(await treatmentRecovery.locator('p').textContent(), TREATMENT);
    const treatmentShape = await page.evaluate(treatment => {
      const modal = document.querySelector('.billing51-modal');
      const links = [...modal.querySelectorAll('a')].map(link => link.getAttribute('href'));
      const buttons = [...modal.querySelectorAll('button')].map(button => button.textContent.trim());
      return {text: modal.innerText.replace(treatment, '<DETAIL>'), links, buttons};
    }, TREATMENT);
    assert.deepEqual(treatmentShape, controlShape);
    assert.equal(windowCheckoutRequestCount(await page.evaluate(() => window.__fixture.fetches)), 0);
    await page.locator('.billing51-close').click();
    await page.locator('.billing51-modal').waitFor({state: 'detached'});
    results.push({
      runtime,
      title,
      detail,
      treatmentVisible: true,
      parity: true,
      checkoutRequests: 0,
      closeWorks: true,
      errors
    });
    await page.close();
  }
  await browser.close();
  process.stdout.write(JSON.stringify({defaultOff: true, results}));
})().catch(error => {
  console.error(error);
  process.exit(1);
});

function windowCheckoutRequestCount(fetches) {
  return fetches.filter(url => url.includes('/checkout')).length;
}
