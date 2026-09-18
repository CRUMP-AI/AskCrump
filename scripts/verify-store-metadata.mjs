import { readFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const metadata = JSON.parse(await readFile(new URL('store/listing.en-US.json', root), 'utf8'));
const listingDraft = await readFile(new URL('docs/STORE_LISTING_COPY.md', root), 'utf8');
const failures = [];

function requireValue(value, label) {
  const text = String(value || '').trim();
  if (!text) failures.push(`${label} is empty.`);
  return text;
}

function maxCharacters(value, maximum, label) {
  const text = requireValue(value, label);
  if ([...text].length > maximum) failures.push(`${label} exceeds ${maximum} characters.`);
  return text;
}

function maxBytes(value, maximum, label) {
  const text = requireValue(value, label);
  if (Buffer.byteLength(text, 'utf8') > maximum) failures.push(`${label} exceeds ${maximum} UTF-8 bytes.`);
  return text;
}

function emailAddress(value, label) {
  const text = requireValue(value, label);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) failures.push(`${label} is not a valid email address.`);
  return text;
}

async function pngAsset(value, expected, label) {
  const relative = requireValue(value, label);
  if (!/^store\/assets\/[a-z0-9-]+\.png$/.test(relative)) {
    failures.push(`${label} must be a versioned PNG under store/assets.`);
    return;
  }
  let bytes;
  try {
    bytes = await readFile(new URL(relative, root));
  } catch {
    failures.push(`${label} is missing: ${relative}.`);
    return;
  }
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (bytes.length < 33 || !bytes.subarray(0, 8).equals(signature) || bytes.toString('ascii', 12, 16) !== 'IHDR') {
    failures.push(`${label} is not a valid PNG with an IHDR header.`);
    return;
  }
  const width = bytes.readUInt32BE(16);
  const height = bytes.readUInt32BE(20);
  const bitDepth = bytes[24];
  const colorType = bytes[25];
  if (width !== expected.width || height !== expected.height) {
    failures.push(`${label} must be ${expected.width}×${expected.height}; found ${width}×${height}.`);
  }
  if (bitDepth !== 8 || colorType !== expected.colorType) {
    failures.push(`${label} must be ${expected.format}; found PNG bit depth ${bitDepth}, color type ${colorType}.`);
  }
  if (bytes.length > expected.maxBytes) failures.push(`${label} exceeds its store size limit.`);
}

function httpsUrl(value, label) {
  const text = requireValue(value, label);
  try {
    const url = new URL(text);
    if (url.protocol !== 'https:') failures.push(`${label} must use HTTPS.`);
    if (url.hostname !== 'www.askcrump.com') {
      failures.push(`${label} must use the canonical www Ask Crump domain without an apex redirect.`);
    }
  } catch {
    failures.push(`${label} is not a valid URL.`);
  }
}

function normalized(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

if (metadata.schemaVersion !== 1) failures.push('Unsupported store metadata schema version.');
if (metadata.locale !== 'en-US') failures.push('The initial store packet must use en-US.');
if (metadata.app?.bundleId !== 'com.clevercrump.askcrump') failures.push('The permanent app bundle/package ID changed.');

maxCharacters(metadata.app?.name, 30, 'App name');
maxCharacters(metadata.apple?.subtitle, 30, 'Apple subtitle');
maxCharacters(metadata.apple?.promotionalText, 170, 'Apple promotional text');
const appleKeywords = maxBytes(metadata.apple?.keywords, 100, 'Apple keywords');
const keywordItems = appleKeywords.split(',').map(item => item.trim());
if (keywordItems.some(item => [...item].length <= 2)) failures.push('Every Apple keyword must contain more than two characters.');
if (new Set(keywordItems.map(item => item.toLocaleLowerCase('en-US'))).size !== keywordItems.length) {
  failures.push('Apple keywords must not contain duplicates.');
}
const appleCopyright = requireValue(metadata.apple?.copyright, 'Apple copyright');
if (!/^20\d{2}\s+\S/.test(appleCopyright) || /replace|example/i.test(appleCopyright)) {
  failures.push('Apple copyright must contain a current owner-controlled year and holder.');
}
const appleDescription = maxCharacters(metadata.apple?.description, 4000, 'Apple description');
const googleShort = maxCharacters(metadata.google?.shortDescription, 80, 'Google short description');
const googleDeveloperEmail = emailAddress(metadata.google?.developerEmail, 'Google developer contact email');
if (googleDeveloperEmail !== 'askcrump@gmail.com') failures.push('Google developer contact email must use the monitored support inbox.');
await pngAsset(metadata.google?.appIcon, {
  width: 512,
  height: 512,
  colorType: 6,
  format: 'a 32-bit RGBA PNG',
  maxBytes: 1024 * 1024,
}, 'Google Play listing icon');
await pngAsset(metadata.google?.featureGraphic, {
  width: 1024,
  height: 500,
  colorType: 2,
  format: 'a 24-bit RGB PNG without alpha',
  maxBytes: 15 * 1024 * 1024,
}, 'Google Play feature graphic');
const googleDescription = maxCharacters(metadata.google?.fullDescription, 4000, 'Google full description');

if ([...appleDescription].length < 250) failures.push('Apple description is too thin for review.');
if ([...googleDescription].length < 250) failures.push('Google full description is too thin for review.');
if ((metadata.apple?.screenshotPlan || []).length < 4) failures.push('Apple screenshot plan needs at least four frames.');
if ((metadata.google?.screenshotPlan || []).length < 4) failures.push('Google screenshot plan needs at least four frames.');

for (const [key, label, expected] of [
  ['supportUrl', 'Support URL', 'https://www.askcrump.com/legal#contact'],
  ['marketingUrl', 'Marketing URL', 'https://www.askcrump.com/'],
  ['privacyUrl', 'Privacy URL', 'https://www.askcrump.com/legal#privacy'],
  ['privacyChoicesUrl', 'Privacy choices URL', 'https://www.askcrump.com/delete-account'],
  ['accountDeletionUrl', 'Account deletion URL', 'https://www.askcrump.com/delete-account'],
]) {
  httpsUrl(metadata.app?.[key], label);
  if (metadata.app?.[key] !== expected) failures.push(`${label} must use the verified direct-200 canonical URL.`);
}

for (const phrase of [
  metadata.app?.name,
  metadata.apple?.subtitle,
  metadata.apple?.promotionalText,
  metadata.apple?.keywords,
  googleShort,
]) {
  if (!listingDraft.includes(String(phrase || ''))) failures.push(`Store listing draft is out of sync: ${phrase}`);
}
if (!normalized(listingDraft).includes(normalized(appleDescription))) failures.push('Apple description is out of sync with the listing draft.');
if (!normalized(listingDraft).includes(normalized(googleDescription))) failures.push('Google description is out of sync with the listing draft.');

const prohibitedClaims = /(?:#1|best ai|million (?:users|downloads)|guaranteed|human[- ]level)/i;
for (const [label, text] of [
  ['Apple metadata', `${metadata.apple?.subtitle} ${metadata.apple?.promotionalText} ${appleDescription}`],
  ['Google metadata', `${googleShort} ${googleDescription}`],
]) if (prohibitedClaims.test(text)) failures.push(`${label} contains an unsubstantiated promotional claim.`);

const serialized = JSON.stringify(metadata).toLowerCase();
if (/"(?:password|secret|token|apikey)"\s*:\s*"(?!\s*")/.test(serialized)) {
  failures.push('Store metadata must not contain credentials or secrets.');
}

if (failures.length) {
  failures.forEach(item => console.error(`FAIL: ${item}`));
  process.exit(1);
}

console.log('Store metadata source checks passed.');
console.log(`Apple: subtitle ${[...metadata.apple.subtitle].length}/30, promotional text ${[...metadata.apple.promotionalText].length}/170, keywords ${Buffer.byteLength(metadata.apple.keywords, 'utf8')}/100 bytes, description ${[...appleDescription].length}/4000.`);
console.log(`Google: short description ${[...googleShort].length}/80, full description ${[...googleDescription].length}/4000.`);
console.log('Reviewer credentials, screenshots from the signed build, privacy forms, and console submission remain release-time gates.');
