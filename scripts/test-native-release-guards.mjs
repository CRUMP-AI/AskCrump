import assert from 'node:assert/strict';

import {
  IOS_MEDIA_USAGE_DESCRIPTION_KEYS,
  missingNonEmptyPlistStrings,
  nonEmptyPlistString,
  topLevelPlistStringValues,
} from './native-release-guards.mjs';

const usageKeys = IOS_MEDIA_USAGE_DESCRIPTION_KEYS;

for (const key of usageKeys) {
  assert.equal(
    nonEmptyPlistString(`<plist><dict><key>${key}</key><string>   \n\t </string></dict></plist>`, key),
    null,
    `${key} must reject whitespace-only text`,
  );
  assert.equal(
    nonEmptyPlistString(`<plist><dict><key>${key}</key><string>&#x20;&#32;</string></dict></plist>`, key),
    null,
    `${key} must reject encoded whitespace-only text`,
  );
  assert.equal(
    nonEmptyPlistString(
      `<plist><dict><!-- <key>${key}</key><string>Comment only</string> --></dict></plist>`,
      key,
    ),
    null,
    `${key} must ignore commented-out declarations`,
  );
}

const meaningful = 'Ask Crump uses the camera only when you choose Take a photo.';
assert.equal(
  nonEmptyPlistString(
    `<plist><dict><key>NSCameraUsageDescription</key><string>  ${meaningful}  </string></dict></plist>`,
    'NSCameraUsageDescription',
  ),
  meaningful,
);

const releaseFixture = `
<plist><dict>
  <key>NSCameraUsageDescription</key><string>${meaningful}</string>
  <key>NSPhotoLibraryUsageDescription</key><string> &#x20; </string>
  <key>NSPhotoLibraryAddUsageDescription</key><string>    </string>
</dict></plist>`;
assert.deepEqual(
  missingNonEmptyPlistStrings(releaseFixture),
  ['NSPhotoLibraryUsageDescription', 'NSPhotoLibraryAddUsageDescription'],
);

const nestedOnly = `
<plist><dict>
  <key>Nested</key><dict>
    <key>NSCameraUsageDescription</key><string>Nested value</string>
  </dict>
</dict></plist>`;
assert.deepEqual(topLevelPlistStringValues(nestedOnly, 'NSCameraUsageDescription'), []);
assert.equal(nonEmptyPlistString(nestedOnly, 'NSCameraUsageDescription'), null);

const duplicate = `
<plist><dict>
  <key>NSCameraUsageDescription</key><string>${meaningful}</string>
  <key>NSCameraUsageDescription</key><string> </string>
</dict></plist>`;
assert.equal(nonEmptyPlistString(duplicate, 'NSCameraUsageDescription'), null);

const wrongType = `
<plist><dict><key>NSCameraUsageDescription</key><true/></dict></plist>`;
assert.deepEqual(topLevelPlistStringValues(wrongType, 'NSCameraUsageDescription'), [null]);
assert.equal(nonEmptyPlistString(wrongType, 'NSCameraUsageDescription'), null);

console.log(
  'Native release guard proof passed: one meaningful top-level usage string accepted; '
  + 'blank, nested, duplicate, and wrong-type declarations rejected.',
);
