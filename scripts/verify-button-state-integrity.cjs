const playwrightModule = process.env.ASKCRUMP_PLAYWRIGHT_MODULE || 'playwright';
const {chromium} = require(playwrightModule);

(async () => {
  const executablePath = process.env.ASKCRUMP_BROWSER_EXECUTABLE || undefined;
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage({viewport: {width: 980, height: 760}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(error.message));

  await page.goto('http://127.0.0.1:8765/tests/fixtures/creation-sheet-containment.html', {waitUntil: 'networkidle'});
  await page.locator('#sendButton[data-crump50="true"]').waitFor();
  const input = page.getByRole('textbox', {name: 'Message Crump'});
  const send = page.getByRole('button', {name: 'Send message'});
  const composerState = async () => ({
    disabled: await send.isDisabled(),
    ariaDisabled: await send.getAttribute('aria-disabled'),
    readyClass: await send.evaluate(node => node.classList.contains('is-ready')),
  });
  const emptyComposer = await composerState();
  await input.fill('Button state check');
  const textComposer = await composerState();
  await input.fill('');
  const clearedComposer = await composerState();
  await page.locator('#filePreview').evaluate(tray => {
    tray.hidden = false;
    tray.style.display = 'flex';
    tray.appendChild(document.createElement('span'));
  });
  await page.waitForFunction(() => document.getElementById('sendButton')?.disabled === false);
  const attachmentComposer = await composerState();
  await page.locator('#filePreview').evaluate(tray => {
    tray.replaceChildren();
    tray.hidden = true;
    tray.style.display = 'none';
  });
  await page.waitForFunction(() => document.getElementById('sendButton')?.disabled === true);
  const removedAttachmentComposer = await composerState();
  await page.getByRole('button', {name: 'Open Document Studio', exact: true}).click();
  await page.getByRole('button', {name: /Academic & professional writing/}).click();

  const specializedPlaceholder = await input.getAttribute('placeholder');
  await page.getByRole('button', {name: 'Create DOCX'}).click();
  const neutral = {
    placeholder: await input.getAttribute('placeholder'),
    focused: await input.evaluate(node => document.activeElement === node),
    toolChips: await page.locator('.crump50-tool-chip').count(),
  };

  await page.getByRole('button', {name: 'Simulate Project conversation'}).click();
  await page.waitForTimeout(750);
  const contextualBeforeTool = await input.getAttribute('placeholder');
  await page.getByRole('button', {name: 'Open Document Studio', exact: true}).click();
  await page.getByRole('button', {name: /A clear, decision-ready narrative/}).click();
  const projectSpecializedPlaceholder = await input.getAttribute('placeholder');
  await page.getByRole('button', {name: 'Create PPTX'}).click();
  const contextualAfterTool = {
    placeholder: await input.getAttribute('placeholder'),
    focused: await input.evaluate(node => document.activeElement === node),
    toolChips: await page.locator('.crump50-tool-chip').count(),
  };

  const evidence = {
    specializedPlaceholder,
    neutral,
    contextualBeforeTool,
    projectSpecializedPlaceholder,
    contextualAfterTool,
    emptyComposer,
    textComposer,
    clearedComposer,
    attachmentComposer,
    removedAttachmentComposer,
    errors,
  };

  const expected = {
    specializedPlaceholder: 'Describe the topic, audience, length, requirements, and citation style…',
    contextual: 'Message Crump in Button QA…',
    projectSpecializedPlaceholder: 'Describe the audience, objective, key evidence, and desired next step…',
  };
  if (
    specializedPlaceholder !== expected.specializedPlaceholder
    || neutral.placeholder !== 'Message Crump'
    || !neutral.focused
    || neutral.toolChips !== 0
    || contextualBeforeTool !== expected.contextual
    || projectSpecializedPlaceholder !== expected.projectSpecializedPlaceholder
    || contextualAfterTool.placeholder !== expected.contextual
    || !contextualAfterTool.focused
    || contextualAfterTool.toolChips !== 0
    || JSON.stringify(emptyComposer) !== JSON.stringify({disabled:true, ariaDisabled:'true', readyClass:false})
    || JSON.stringify(textComposer) !== JSON.stringify({disabled:false, ariaDisabled:'false', readyClass:true})
    || JSON.stringify(clearedComposer) !== JSON.stringify({disabled:true, ariaDisabled:'true', readyClass:false})
    || JSON.stringify(attachmentComposer) !== JSON.stringify({disabled:false, ariaDisabled:'false', readyClass:true})
    || JSON.stringify(removedAttachmentComposer) !== JSON.stringify({disabled:true, ariaDisabled:'true', readyClass:false})
    || errors.length
  ) {
    throw new Error(`Button state integrity failed: ${JSON.stringify(evidence)}`);
  }

  console.log(JSON.stringify(evidence, null, 2));
  await browser.close();
})().catch(error => {
  console.error(error);
  process.exit(1);
});
