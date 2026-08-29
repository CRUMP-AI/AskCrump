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
maxBytes(metadata.apple?.keywords, 100, 'Apple keywords');
const appleDescription = maxCharacters(metadata.apple?.description, 4000, 'Apple description');
const googleShort = maxCharacters(metadata.google?.shortDescription, 80, 'Google short description');
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
