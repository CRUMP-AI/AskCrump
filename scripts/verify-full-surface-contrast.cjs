'use strict';

/*
 * Full-surface contrast gate.
 *
 * Greg's rule (2026-11-09): text color must change when the background
 * changes from light to dark — verified on ALL pages. This verifier renders
 * the real surfaces (the full-surface fixture with the production CSS stack,
 * the live Today fixture, the appearance fixture, and every standalone
 * public page), samples the effective foreground/background pairing of
 * every visible text node from the rendered DOM, and fails when a pairing
 * drops below WCAG AA (4.5:1 for normal text, 3:1 for large text).
 *
 * Gradient handling: an opaque gradient stop becomes a candidate background
 * and stops the ancestor walk; translucent stops blend over what is below.
 * aria-hidden subtrees and disabled controls are skipped.
 */

const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const repositoryRoot = path.resolve(__dirname, '..');
const outputPath = path.join(repositoryRoot, 'artifacts', 'browser-control-matrix', 'full-surface-contrast.json');
const rootBase = process.env.CRUMP_ROOT_BASE || 'http://127.0.0.1:8765';
const publicBase = process.env.CRUMP_PUBLIC_BASE || 'http://127.0.0.1:4173';

const VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 900 },
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'mobile-320', width: 320, height: 844 },
];

function scanInPage() {
  const parseColor = (value) => {
    const match = /rgba?\(([^)]+)\)/.exec(value || '');
    if (!match) return null;
    const parts = match[1].split(',').map((part) => Number.parseFloat(part));
    if (parts.length < 3 || parts.some((part) => Number.isNaN(part))) return null;
    return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
  };
  const blend = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const luminance = ({ r, g, b }) => {
    const channel = (value) => {
      const s = value / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const ratio = (a, b) => {
    const la = luminance(a);
    const lb = luminance(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  };
  const gradientStops = (image) => {
    if (!image || !image.includes('gradient')) return null;
    const stops = [...image.matchAll(/rgba?\([^)]+\)/g)].map((match) => parseColor(match[0])).filter(Boolean);
    return stops.length ? stops : null;
  };
  const effectiveBackgrounds = (element) => {
    // Walk up from the element. Translucent layers (solid colors and
    // gradient stops) accumulate as pending tints; the first opaque layer
    // is terminal, and the pending tints blend over it (farthest first).
    // A gradient with any opaque stop is terminal on those stops.
    const pending = [];
    let node = element;
    let terminal = null;
    while (node && node !== document.documentElement) {
      const style = getComputedStyle(node);
      const stops = gradientStops(style.backgroundImage);
      if (stops && stops.some((stop) => stop.a >= 0.99)) {
        terminal = stops.filter((stop) => stop.a >= 0.99).map((stop) => ({ ...stop, a: 1 }));
        break;
      }
      if (stops) pending.push(...stops);
      const color = parseColor(style.backgroundColor);
      if (color && color.a >= 0.99) {
        terminal = [{ ...color, a: 1 }];
        break;
      }
      if (color && color.a > 0) pending.push(color);
      node = node.parentElement;
    }
    if (!terminal) {
      const body = parseColor(getComputedStyle(document.body).backgroundColor);
      const html = parseColor(getComputedStyle(document.documentElement).backgroundColor);
      const base = (body && body.a > 0 ? body : null) || (html && html.a > 0 ? html : null) || { r: 255, g: 255, b: 255, a: 1 };
      terminal = [{ ...base, a: 1 }];
      if (base.a < 1) terminal = [blend(base, { r: 255, g: 255, b: 255, a: 1 })];
    }
    return terminal.map((base) => {
      let result = base;
      for (let index = pending.length - 1; index >= 0; index -= 1) {
        result = blend(pending[index], result);
      }
      return result;
    });
  };
  const failures = [];
  let sampled = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const text = (node.nodeValue || '').trim();
    if (!text) continue;
    const element = node.parentElement;
    if (!element) continue;
    if (element.closest('[aria-hidden="true"]')) continue;
    // The mobile nav is a mobile-only surface; the shell does not render it
    // at desktop widths.
    if (window.innerWidth > 1100 && element.closest('.cv-mnav')) continue;
    const style = getComputedStyle(element);
    // Gradient-clipped text (background-clip: text with a transparent fill)
    // paints the gradient itself as the glyphs; there is no single
    // foreground color to sample.
    if ((style.webkitBackgroundClip || '').includes('text')
      && (style.webkitTextFillColor === 'transparent' || style.webkitTextFillColor === 'rgba(0, 0, 0, 0)')) continue;
    // Image-replaced text (brand marks swap the glyphs for artwork and set
    // the text transparent) is not a color pairing.
    if ((style.color === 'rgba(0, 0, 0, 0)' || style.webkitTextFillColor === 'rgba(0, 0, 0, 0)')
      && (style.backgroundImage || '').includes('url(')) continue;
    if (style.visibility === 'hidden' || style.display === 'none' || Number(style.opacity) === 0) continue;
    if (element.closest(':disabled, [disabled]')) continue;
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    const foreground = parseColor(style.color);
    if (!foreground) continue;
    const fontSize = Number.parseFloat(style.fontSize) || 16;
    const fontWeight = Number.parseInt(style.fontWeight, 10) || 400;
    const large = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
    const threshold = large ? 3 : 4.5;
    const backgrounds = effectiveBackgrounds(element);
    if (!backgrounds.length) continue;
    sampled += 1;
    const worst = Math.min(...backgrounds.map((background) => ratio(foreground, background)));
    if (worst < threshold) {
      failures.push({
        tag: element.tagName,
        className: String(element.className || '').slice(0, 90),
        text: text.slice(0, 48),
        color: style.color,
        ratio: Math.round(worst * 100) / 100,
        threshold,
        fontSize,
      });
    }
  }
  return { sampled, failures };
}

async function scanPage(page, url, setup, settleMs = 500) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (setup) await setup(page);
  await page.waitForTimeout(settleMs);
  return page.evaluate(scanInPage);
}

async function main() {
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const failures = [];
  const surfaces = [];
  let totalSampled = 0;

  const record = (surface, theme, viewport, result) => {
    console.log(`scanned ${surface} ${theme} ${viewport.name}: ${result.sampled} nodes, ${result.failures.length} failures`);
    totalSampled += result.sampled;
    surfaces.push({ surface, theme, viewport: viewport.name, sampled: result.sampled, failures: result.failures.length });
    for (const failure of result.failures) {
      failures.push({ surface, theme, viewport: viewport.name, ...failure });
    }
  };

  // 1) Full-surface fixture: production CSS stack, both themes, 3 viewports.
  for (const theme of ['light', 'dark']) {
    for (const viewport of VIEWPORTS) {
      const page = await browser.newPage({ viewport });
      const result = await scanPage(page, `${rootBase}/tests/fixtures/full-surface-contrast.html?theme=${theme}`, null, 1900);
      record('full-surface-fixture', theme, viewport, result);
      await page.close();
    }
  }

  // 1b) Auth fixture: the signed-out screen loads only the static head
  // stack, so it is scanned on its own fixture in both appearances.
  for (const theme of ['light', 'dark']) {
    for (const viewport of VIEWPORTS) {
      const page = await browser.newPage({ viewport });
      const result = await scanPage(page, `${rootBase}/tests/fixtures/full-surface-contrast-auth.html?theme=${theme}`, null, 1900);
      record('auth-fixture', theme, viewport, result);
      await page.close();
    }
  }

  // 2) Today fixture: live renderer states, both themes.
  for (const state of ['planned', 'live']) {
    for (const theme of ['dark', 'light']) {
      for (const viewport of VIEWPORTS) {
        const page = await browser.newPage({ viewport });
        const result = await scanPage(page, `${rootBase}/tests/fixtures/agent-today-placeholder.html?state=${state}&theme=${theme}`);
        record(`today-${state}`, theme, viewport, result);
        await page.close();
      }
    }
  }

  // 2b) Chat fixture: the open conversation's agent cards (approval
  // primary in one state, approval + live + result in the other), both
  // themes — the new section's text must pass AA on its ink panel in
  // either appearance, exactly like Today's cards.
  for (const state of ['approval', 'both']) {
    for (const theme of ['dark', 'light']) {
      for (const viewport of VIEWPORTS) {
        const page = await browser.newPage({ viewport });
        const result = await scanPage(page, `${rootBase}/tests/fixtures/agent-chat-cards.html?state=${state}&theme=${theme}`);
        record(`chat-${state}`, theme, viewport, result);
        await page.close();
      }
    }
  }

  // 3) Appearance fixture: light render, then the runtime theme switch to dark.
  for (const viewport of VIEWPORTS) {
    const lightPage = await browser.newPage({ viewport });
    const light = await scanPage(lightPage, `${rootBase}/tests/fixtures/appearance-theme.html`);
    record('appearance-fixture', 'light', viewport, light);
    await lightPage.close();
    const darkPage = await browser.newPage({ viewport });
    const dark = await scanPage(darkPage, `${rootBase}/tests/fixtures/appearance-theme.html`, async (page) => {
      await page.evaluate(() => window.CrumpAppearance?.set?.('dark'));
    });
    record('appearance-fixture', 'dark', viewport, dark);
    await darkPage.close();
  }

  // 4) Standalone public pages, as shipped (dark brand surfaces + light legal pages).
  // app.html is not scanned here: its first paint is a boot/auth state driven
  // by account JS, so its rendered pairings are not deterministic. The auth
  // shell and every in-app surface are covered deterministically by the
  // full-surface fixture above in both themes.
  const publicPages = [
    'ask-crump.html',
    'clever-crump.html',
    'legal.html',
    'delete-account.html',
    'ai-document-generator.html',
    'ai-presentation-maker.html',
    'ai-project-workspace.html',
    'ai-resume-builder.html',
    'ai-video-generator.html',
    'guides/index.html',
    'guides/audit-ai-resume-bullets.html',
  ];
  for (const name of publicPages) {
    for (const viewport of [VIEWPORTS[0], VIEWPORTS[1]]) {
      const page = await browser.newPage({ viewport });
      const result = await scanPage(page, `${publicBase}/${name}`);
      record(`public:${name}`, 'as-shipped', viewport, result);
      await page.close();
    }
  }

  await browser.close();

  const report = { sampled: totalSampled, surfaces, failures };
  fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`);
  console.log(`full-surface contrast: sampled ${totalSampled} text nodes across ${surfaces.length} surface renders`);
  if (failures.length) {
    for (const failure of failures.slice(0, 60)) {
      console.error(`FAIL ${failure.surface} ${failure.theme} ${failure.viewport} ${failure.tag}.${failure.className} "${failure.text}" ${failure.ratio}:1 < ${failure.threshold}:1`);
    }
    throw new Error(`full-surface contrast gate failed: ${failures.length} pairing(s) below WCAG AA`);
  }
  console.log('full-surface contrast gate passed: every sampled pairing meets WCAG AA');
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

module.exports = { main };
