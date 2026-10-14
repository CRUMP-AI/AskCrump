import {existsSync} from 'node:fs';
import {mkdir, readFile, readdir, writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const require = createRequire(import.meta.url);
const {chromium} = require('playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fixturePath = '/tests/fixtures/ui-visual-regression.html';
const fixtureLocalPath = path.join(root, fixturePath.slice(1));
const outputRoot = path.resolve(
  process.env.ASKCRUMP_UI_AUDIT_OUTPUT || path.join(root, 'artifacts', 'ui-regression'),
);
const runId = new Date().toISOString().replaceAll(':', '-').replaceAll('.', '-');
const outputDirectory = path.join(outputRoot, runId);

const states = Object.freeze([
  'home',
  'conversation',
  'files',
  'video',
  'intelligence',
  'settings',
  'billing',
  'create',
  'activity',
]);
const themes = Object.freeze(['light', 'dark']);
const viewports = Object.freeze([
  {name: 'phone', width: 390, height: 844, strictTargets: true},
  {name: 'tablet', width: 1024, height: 1366, strictTargets: false},
  {name: 'desktop', width: 1440, height: 900, strictTargets: false},
]);
const expectedScenarioCount = states.length * themes.length * viewports.length;

async function inlinedFixture() {
  const fixtureDirectory = path.dirname(fixtureLocalPath);
  let source = await readFile(fixtureLocalPath, 'utf8');
  const links = [...source.matchAll(/<link\s+rel="stylesheet"\s+href="([^"]+)"\s*>/g)];
  for (const match of links) {
    const href = match[1].split('?')[0];
    const cssPath = path.resolve(fixtureDirectory, href);
    if (cssPath !== root && !cssPath.startsWith(`${root}${path.sep}`)) {
      throw new Error(`Fixture stylesheet escaped the repository: ${href}`);
    }
    const css = (await readFile(cssPath, 'utf8')).replaceAll('</style', '<\\/style');
    source = source.replace(match[0], `<style data-ui-audit-source="${path.basename(cssPath)}">\n${css}\n</style>`);
  }
  return source;
}

async function playwrightCandidates() {
  const candidates = [
    process.env.ASKCRUMP_BROWSER_EXECUTABLE,
    process.env.ASK_CRUMP_BROWSER_PATH,
    process.env.CODEX_BROWSER_EXECUTABLE,
    chromium.executablePath(),
    process.env.PROGRAMFILES ? path.join(process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe') : '',
    process.env['PROGRAMFILES(X86)'] ? path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe') : '',
  ].filter(Boolean);

  // Codex' Windows sandbox may virtualize LOCALAPPDATA while the installed
  // browser remains in the user's ordinary profile. Probe both locations.
  const playwrightRoots = [...new Set([
    process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, 'ms-playwright') : '',
    process.env.USERPROFILE ? path.join(process.env.USERPROFILE, 'AppData', 'Local', 'ms-playwright') : '',
  ].filter(Boolean))];
  for (const playwrightRoot of playwrightRoots) {
    if (!existsSync(playwrightRoot)) continue;
    for (const directory of await readdir(playwrightRoot, {withFileTypes: true})) {
      if (!directory.isDirectory() || !/^(chromium|chromium_headless_shell)-/i.test(directory.name)) continue;
      candidates.push(
        path.join(playwrightRoot, directory.name, 'chrome-win64', 'chrome.exe'),
        path.join(playwrightRoot, directory.name, 'chrome-win', 'chrome.exe'),
        path.join(playwrightRoot, directory.name, 'chrome-headless-shell-win64', 'chrome-headless-shell.exe'),
        path.join(playwrightRoot, directory.name, 'chrome-headless-shell-win', 'headless_shell.exe'),
      );
    }
  }
  return [...new Set(candidates)].filter(candidate => existsSync(candidate));
}

async function launchBrowser() {
  const candidates = await playwrightCandidates();
  const failures = [];
  for (const executablePath of candidates) {
    try {
      return await chromium.launch({headless: true, executablePath});
    } catch (error) {
      failures.push(`${executablePath}: ${error.message}`);
    }
  }
  try {
    return await chromium.launch({headless: true});
  } catch (error) {
    failures.push(`Playwright default: ${error.message}`);
  }
  throw new Error(`Chromium could not launch. Tried:\n${failures.join('\n')}`);
}

function compactViolations(items, limit = 12) {
  if (!items.length) return 'none';
  const shown = items.slice(0, limit).map(item => JSON.stringify(item)).join('\n  ');
  const remainder = items.length > limit ? `\n  … ${items.length - limit} more` : '';
  return `${shown}${remainder}`;
}

async function auditPage(page, {strictTargets}) {
  return page.evaluate(({strictTargets}) => {
    const contrastMinimum = 4.5;
    const mobileTargetMinimum = 44;
    const tolerance = 1.1;

    function isVisible(element) {
      if (!(element instanceof Element)) return false;
      if (element.closest('[aria-hidden="true"]')) return false;
      const style = getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
      const rect = element.getBoundingClientRect();
      return rect.width > .5 && rect.height > .5;
    }

    function selectorFor(element) {
      if (element.id) return `#${CSS.escape(element.id)}`;
      const parts = [];
      let node = element;
      while (node && node !== document.body && parts.length < 3) {
        let part = node.localName || 'node';
        const classes = [...node.classList].slice(0, 2);
        if (classes.length) part += `.${classes.map(value => CSS.escape(value)).join('.')}`;
        parts.unshift(part);
        node = node.parentElement;
      }
      return parts.join(' > ');
    }

    function parseColor(value) {
      const match = String(value || '').match(/^rgba?\(\s*([\d.]+)[, ]+\s*([\d.]+)[, ]+\s*([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/i);
      if (match) {
        const alpha = match[4]?.endsWith('%') ? Number(match[4].slice(0, -1)) / 100 : Number(match[4] ?? 1);
        return {r: Number(match[1]), g: Number(match[2]), b: Number(match[3]), a: Number.isFinite(alpha) ? alpha : 1};
      }
      // Chromium serializes color-mix() output as color(srgb ...). Keep the
      // translucent control background in the contrast calculation instead
      // of accidentally treating it as fully transparent.
      const srgb = String(value || '').match(/^color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+%?))?\s*\)$/i);
      if (!srgb) return null;
      const alpha = srgb[4]?.endsWith('%') ? Number(srgb[4].slice(0, -1)) / 100 : Number(srgb[4] ?? 1);
      return {r: Number(srgb[1]) * 255, g: Number(srgb[2]) * 255, b: Number(srgb[3]) * 255, a: Number.isFinite(alpha) ? alpha : 1};
    }

    function composite(foreground, background) {
      const alpha = foreground.a + background.a * (1 - foreground.a);
      if (alpha <= 0) return {r: 0, g: 0, b: 0, a: 0};
      return {
        r: (foreground.r * foreground.a + background.r * background.a * (1 - foreground.a)) / alpha,
        g: (foreground.g * foreground.a + background.g * background.a * (1 - foreground.a)) / alpha,
        b: (foreground.b * foreground.a + background.b * background.a * (1 - foreground.a)) / alpha,
        a: alpha,
      };
    }

    function effectiveBackground(element) {
      const chain = [];
      for (let node = element; node instanceof Element; node = node.parentElement) chain.unshift(node);
      const dark = document.documentElement.dataset.theme === 'dark';
      let result = dark ? {r: 9, g: 12, b: 16, a: 1} : {r: 246, g: 244, b: 238, a: 1};
      for (const node of chain) {
        const color = parseColor(getComputedStyle(node).backgroundColor);
        if (color && color.a > 0) result = composite(color, result);
      }
      return result;
    }

    function effectiveOpacity(element) {
      let opacity = 1;
      for (let node = element; node instanceof Element; node = node.parentElement) {
        const value = Number(getComputedStyle(node).opacity);
        if (Number.isFinite(value)) opacity *= value;
      }
      return opacity;
    }

    function luminance(color) {
      const channels = [color.r, color.g, color.b].map(channel => {
        const value = channel / 255;
        return value <= .03928 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
      });
      return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
    }

    function contrastRatio(foreground, background) {
      const foregroundLuminance = luminance(foreground);
      const backgroundLuminance = luminance(background);
      return (Math.max(foregroundLuminance, backgroundLuminance) + .05)
        / (Math.min(foregroundLuminance, backgroundLuminance) + .05);
    }

    function colorLabel(color) {
      const hex = [color.r, color.g, color.b]
        .map(channel => Math.max(0, Math.min(255, Math.round(channel))).toString(16).padStart(2, '0'))
        .join('');
      return `#${hex}`;
    }

    const contrast = [];
    const seenTextElements = new Set();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.textContent?.trim()) return NodeFilter.FILTER_REJECT;
        const parent = node.parentElement;
        if (!parent || !isVisible(parent)) return NodeFilter.FILTER_REJECT;
        const range = document.createRange();
        range.selectNodeContents(node);
        const rect = range.getBoundingClientRect();
        return rect.width > .5 && rect.height > .5 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const element = node.parentElement;
      if (!element || seenTextElements.has(element)) continue;
      seenTextElements.add(element);
      if (element.closest('[data-ui-contrast-exempt]')) continue;
      const background = effectiveBackground(element);
      const rawForeground = parseColor(getComputedStyle(element).color);
      if (!rawForeground) {
        contrast.push({selector: selectorFor(element), text: node.textContent.trim().slice(0, 60), reason: 'unparseable foreground color'});
        continue;
      }
      const foreground = composite({...rawForeground, a: rawForeground.a * effectiveOpacity(element)}, background);
      const ratio = contrastRatio(foreground, background);
      if (ratio + .005 < contrastMinimum) {
        contrast.push({
          selector: selectorFor(element),
          text: element.textContent.trim().replace(/\s+/g, ' ').slice(0, 60),
          ratio: Number(ratio.toFixed(2)),
          foreground: colorLabel(foreground),
          background: colorLabel(background),
          opacity: Number(effectiveOpacity(element).toFixed(3)),
        });
      }
    }

    const targets = [];
    if (strictTargets) {
      const selector = 'button,a[href],input:not([type="hidden"]),select,textarea,summary,[role="button"],[tabindex]:not([tabindex="-1"])';
      for (const element of document.querySelectorAll(selector)) {
        if (!isVisible(element) || element.closest('[data-ui-target-exempt]')) continue;
        let hitArea = element;
        if (element.matches('input[type="checkbox"],input[type="radio"]') && element.closest('label')) hitArea = element.closest('label');
        const rect = hitArea.getBoundingClientRect();
        if (rect.width + tolerance < mobileTargetMinimum || rect.height + tolerance < mobileTargetMinimum) {
          targets.push({selector: selectorFor(element), label: (element.getAttribute('aria-label') || element.textContent || element.getAttribute('placeholder') || '').trim().replace(/\s+/g, ' ').slice(0, 60), width: Number(rect.width.toFixed(1)), height: Number(rect.height.toFixed(1))});
        }
      }
    }

    const overflow = [];
    const rootOverflow = document.documentElement.scrollWidth - innerWidth;
    if (rootOverflow > tolerance) overflow.push({selector: 'html', overflow: Number(rootOverflow.toFixed(1))});
    for (const element of document.querySelectorAll('[data-ui-audit-box],[role="dialog"]')) {
      if (!isVisible(element) || element.closest('[data-ui-overflow-exempt]')) continue;
      const rect = element.getBoundingClientRect();
      if (rect.left < -tolerance || rect.right > innerWidth + tolerance) {
        overflow.push({selector: selectorFor(element), left: Number(rect.left.toFixed(1)), right: Number(rect.right.toFixed(1)), viewport: innerWidth});
      }
    }

    const overlap = [];
    const fixedControls = [...document.querySelectorAll('[data-ui-fixed-control]')].filter(isVisible);
    const sensitiveElements = [...document.querySelectorAll('[data-ui-overlap-sensitive]')].filter(isVisible);
    const intersects = (left, right) => Math.min(left.right, right.right) - Math.max(left.left, right.left) > tolerance
      && Math.min(left.bottom, right.bottom) - Math.max(left.top, right.top) > tolerance;
    for (const fixed of fixedControls) {
      const fixedRect = fixed.getBoundingClientRect();
      for (const sensitive of sensitiveElements) {
        if (fixed.contains(sensitive) || sensitive.contains(fixed)) continue;
        const sensitiveRect = sensitive.getBoundingClientRect();
        if (intersects(fixedRect, sensitiveRect)) overlap.push({fixed: selectorFor(fixed), obscures: selectorFor(sensitive)});
      }
      if (fixedRect.left < -tolerance || fixedRect.right > innerWidth + tolerance || fixedRect.bottom > innerHeight + tolerance) {
        overlap.push({fixed: selectorFor(fixed), reason: 'fixed control escaped viewport'});
      }
    }

    const tray = document.querySelector('#filePreview.crump50-attachment-tray');
    const inputArea = document.querySelector('.v1-command-dock .input-area');
    if (isVisible(tray) && isVisible(inputArea)) {
      const trayRect = tray.getBoundingClientRect();
      const inputRect = inputArea.getBoundingClientRect();
      if (trayRect.bottom > inputRect.top + tolerance) {
        overlap.push({fixed: selectorFor(tray), obscures: selectorFor(inputArea), pixels: Number((trayRect.bottom - inputRect.top).toFixed(1))});
      }
    }

    const motion = [];
    const seconds = value => String(value || '').split(',').map(part => Number.parseFloat(part) || 0);
    for (const element of document.querySelectorAll('body *')) {
      if (!isVisible(element) || element.closest('[data-ui-motion-exempt]')) continue;
      const style = getComputedStyle(element);
      const animationActive = style.animationName.split(',').some(name => name.trim() !== 'none')
        && Math.max(...seconds(style.animationDuration)) > .01;
      const transitionActive = style.transitionProperty.split(',').some(name => name.trim() !== 'none')
        && Math.max(...seconds(style.transitionDuration)) > .01;
      if (animationActive || transitionActive || style.scrollBehavior === 'smooth') {
        motion.push({selector: selectorFor(element), animation: style.animationName, animationDuration: style.animationDuration, transitionDuration: style.transitionDuration, scrollBehavior: style.scrollBehavior});
      }
    }

    return {
      counts: {
        textNodes: seenTextElements.size,
        interactiveTargets: strictTargets ? document.querySelectorAll('button,a[href],input:not([type="hidden"]),select,textarea,summary,[role="button"]').length : 0,
        fixedControls: fixedControls.length,
      },
      violations: {contrast, targets, overflow, overlap, motion},
    };
  }, {strictTargets});
}

function scenarioFailures(result) {
  return Object.entries(result.violations)
    .filter(([, violations]) => violations.length)
    .map(([kind, violations]) => `${kind} (${violations.length}):\n  ${compactViolations(violations)}`);
}

await mkdir(outputDirectory, {recursive: true});
let browser;
const inlineHtml = await inlinedFixture();
const results = [];
try {
  browser = await launchBrowser();
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: {width: viewport.width, height: viewport.height},
      deviceScaleFactor: 1,
      colorScheme: 'light',
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const browserErrors = [];
    page.on('pageerror', error => browserErrors.push(`pageerror: ${error.message}`));
    page.on('console', message => {
      if (message.type() === 'error') browserErrors.push(`console: ${message.text()}`);
    });
    for (const theme of themes) {
      await page.emulateMedia({colorScheme: theme, reducedMotion: 'reduce'});
      for (const stateName of states) {
        browserErrors.length = 0;
        // Inline local fixture CSS so the suite is deterministic and works in
        // managed Windows environments that block browser loopback traffic.
        await page.setContent(inlineHtml, {waitUntil: 'load'});
        await page.evaluate(({stateName, theme}) => {
          document.documentElement.dataset.theme = theme;
          document.querySelectorAll('[data-ui-state]').forEach(node => {
            const active = node.dataset.uiState === stateName;
            node.dataset.auditActive = String(active);
            node.setAttribute('aria-hidden', String(!active));
          });
          document.body.dataset.uiAuditState = stateName;
          document.body.dataset.uiAuditReady = 'true';
        }, {stateName, theme});
        await page.waitForFunction(() => document.body.dataset.uiAuditReady === 'true');
        await page.evaluate(() => {
          const region = document.querySelector('[data-ui-scroll-region]');
          if (region) region.scrollTop = region.scrollHeight;
        });
        await page.evaluate(() => document.fonts?.ready);
        const result = await auditPage(page, viewport);
        if (browserErrors.length) result.violations.browser = [...browserErrors];
        const screenshot = `${viewport.name}-${theme}-${stateName}.png`;
        await page.screenshot({
          path: path.join(outputDirectory, screenshot),
          fullPage: stateName !== 'conversation',
          animations: 'disabled',
        });
        const scenario = {viewport: viewport.name, theme, state: stateName, screenshot, ...result};
        results.push(scenario);
        const failures = scenarioFailures(scenario);
        process.stdout.write(`${failures.length ? 'FAIL' : 'PASS'} ${viewport.name}/${theme}/${stateName}\n`);
      }
    }
    await context.close();
  }
} finally {
  await browser?.close();
}

const failedScenarios = results.filter(result => scenarioFailures(result).length);
const summary = {
  generatedAt: new Date().toISOString(),
  contract: {
    contrastMinimum: 4.5,
    mobileTargetMinimum: 44,
    reducedMotion: 'reduce',
    expectedScenarioCount,
    states,
    themes,
    viewports,
  },
  totals: {
    scenarios: results.length,
    passed: results.length - failedScenarios.length,
    failed: failedScenarios.length,
  },
  results,
};
await writeFile(path.join(outputDirectory, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`, 'utf8');

if (results.length !== expectedScenarioCount) {
  throw new Error(`UI regression coverage was incomplete: ${results.length}/${expectedScenarioCount} scenarios ran.`);
}
if (failedScenarios.length) {
  const details = failedScenarios.map(result => (
    `${result.viewport}/${result.theme}/${result.state}\n${scenarioFailures(result).join('\n')}`
  )).join('\n\n');
  throw new Error(
    `UI regression failed ${failedScenarios.length}/${results.length} scenarios.\n`
    + `Evidence: ${outputDirectory}\n\n${details}`,
  );
}

process.stdout.write(`UI visual regression passed ${results.length}/${expectedScenarioCount} scenarios.\n`);
process.stdout.write(`Screenshots and machine-readable evidence: ${outputDirectory}\n`);
