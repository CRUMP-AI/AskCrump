const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

async function runViewport(browser, viewport) {
  const page = await browser.newPage({viewport});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8765/tests/fixtures/attach-creation-routing.html', {waitUntil: 'networkidle'});
  await page.waitForFunction(() => document.getElementById('attachBtn')?.dataset.crump52 === 'true');

  const add = page.getByRole('button', {name:'Add to conversation'});
  await add.click();
  await page.getByRole('button', {name:/Create image Generate or edit an image/}).click();
  const imageStudio = page.getByRole('dialog', {name:'Image Studio'});
  await imageStudio.waitFor();
  const imageCloseFocused = await imageStudio.getByRole('button', {name:'Close Image Studio'})
    .evaluate(node => document.activeElement === node);
  await page.keyboard.press('Escape');

  await add.click();
  await page.getByRole('button', {name:/Create document DOCX/}).click();
  const documentStudio = page.getByRole('dialog', {name:/Start with the outcome/});
  await documentStudio.waitFor();
  const documentCloseFocused = await documentStudio.getByRole('button', {name:'Close Document Studio'})
    .evaluate(node => document.activeElement === node);
  const legacyMode = await page.evaluate(() => document.documentElement.dataset.crump52CreativeTool || '');
  await page.keyboard.press('Escape');

  const evidence = {
    viewport,
    imageStudio:true,
    imageCloseFocused,
    documentStudio:true,
    documentCloseFocused,
    legacyMode,
    placeholder:await page.getByRole('textbox', {name:'Message Crump'}).getAttribute('placeholder'),
    errors,
  };
  if (!imageCloseFocused || !documentCloseFocused || legacyMode || evidence.placeholder !== 'Message Crump' || errors.length) {
    throw new Error(`Add-menu creation routing failed: ${JSON.stringify(evidence)}`);
  }
  await page.close();
  return evidence;
}

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless:true, ...(executablePath ? {executablePath} : {})});
  const results = [];
  for (const viewport of [{width:390,height:844}, {width:1280,height:720}]) {
    results.push(await runViewport(browser, viewport));
  }
  console.log(JSON.stringify(results));
  await browser.close();
})().catch(error => {
  console.error(error);
  process.exit(1);
});
