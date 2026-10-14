import assert from 'node:assert/strict';

import {staticAnchorHref} from './public-destination-parser.mjs';

const validStaticCases = [
  ['/legal.html#privacy', 'html', '/legal.html#privacy'],
  ['../guides/rough-idea-to-launch-plan', 'html', '../guides/rough-idea-to-launch-plan'],
  [
    'https://www.askcrump.com/app?signup=1&amp;source=homepage',
    'html',
    'https://www.askcrump.com/app?signup=1&source=homepage',
  ],
  ['https://www.clevercrump.com/', 'html', 'https://www.clevercrump.com/'],
  ["/search?q='+term", 'html', "/search?q='+term"],
  ["/search?q='+term", 'javascript', "/search?q='+term"],
  ["' + esc(url) + '", 'html', "' + esc(url) + '"],
];

for (const [source, sourceType, expected] of validStaticCases) {
  assert.equal(
    staticAnchorHref(source, sourceType),
    expected,
    `expected a static ${sourceType} href for ${source}`,
  );
}

const ignoredCases = [
  ['', 'html'],
  ['#privacy', 'html'],
  ['MAILTO:help@askcrump.com', 'html'],
  ['tel:+10000000000', 'html'],
  ['javascript:void(0)', 'html'],
  ['${escapeHtml(projectRouteHref(item.id))}', 'javascript'],
  ['{{ runtime_destination }}', 'javascript'],
  ['<%= runtimeDestination %>', 'javascript'],
  ["' + esc(url) + '", 'javascript'],
  ['` + runtimeUrl + `', 'javascript'],
  ["'.concat(esc(url), '", 'javascript'],
  ["/asset/'.concat(id, '.png')", 'javascript'],
];

for (const [source, sourceType] of ignoredCases) {
  assert.equal(
    staticAnchorHref(source, sourceType),
    null,
    `expected a non-static ${sourceType} href for ${source}`,
  );
}

assert.throws(
  () => staticAnchorHref('/legal', 'unknown'),
  /Unknown public destination source type/,
);

console.log(
  `Public destination parser proof passed: ${validStaticCases.length} static hrefs accepted and `
  + `${ignoredCases.length} non-navigation or runtime-built hrefs ignored.`,
);
