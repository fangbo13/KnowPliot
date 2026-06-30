/**
 * i18n Key Existence Checker
 * Scans all .tsx/.ts files for t('key') calls and verifies
 * that each key exists in the corresponding locale JSON file.
 *
 * Usage: node scripts/check-i18n.cjs
 */

const fs = require('fs');
const path = require('path');

const LOCALES_DIR = path.resolve(__dirname, '../src/i18n/locales');
const SRC_DIR = path.resolve(__dirname, '../src');
const LANGUAGES = ['zh', 'en'];

/**
 * Patterns that should NOT be treated as i18n keys even if
 * they appear inside what looks like a t() call.
 */
function isFalsePositiveKey(key) {
  // API / URL paths
  if (key.startsWith('/') || key.startsWith('http://') || key.startsWith('https://')) return true;
  // Import paths
  if (key.startsWith('./') || key.startsWith('../')) return true;
  // Newlines, single dots, or empty-ish strings
  if (key === '\\n' || key === '\n' || key === '.' || key.trim() === '') return true;
  // HTML tags / CSS selectors (single lowercase word with no underscore)
  if (/^(textarea|div|span|input|button|form|select|option|label|table|tbody|thead|tr|td|th|ul|ol|li|img|a|p|h[1-6]|pre|code|nav|section|article|aside|header|footer|main|dialog|details|summary|canvas|svg|video|audio)$/.test(key)) return true;
  // Strings that contain spaces and look like natural language sentences
  // (real i18n keys use underscores/dots, not spaces)
  if (key.includes(' ') && key.length > 2) return true;
  return false;
}

/**
 * Check if a file is a test file that should be skipped.
 */
function isTestFile(filePath) {
  const rel = filePath.replace(/\\/g, '/');
  return (
    rel.includes('__tests__') ||
    rel.includes('.test.') ||
    rel.includes('.spec.') ||
    rel.includes('__mocks__')
  );
}

/**
 * Collect all t('key') calls from source files.
 *
 * Only matches:
 *   t('key')   t("key")
 *   i18n.t('key')   i18next.t('key')
 *
 * Does NOT match:
 *   import('...')  get('...')  set('...')  test('...')  it('...')
 *   document.createElement('...')  etc.
 */
function findTranslationKeys(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');

  // Regex explanation:
  //   (?:^|[^a-zA-Z0-9_$])  — must NOT be preceded by an identifier char
  //                            (prevents matching 'import(', 'get(', 'test(', etc.)
  //   (?:i18n(?:ext)?\.)?    — optional i18n. or i18next. prefix
  //   t\s*\(\s*              — the t( call, with optional whitespace
  //   ['"]([^'"]+)['"]       — the string argument (captured)
  //
  const regex = /(?:^|[^a-zA-Z0-9_$])(?:i18n(?:ext)?\.)?t\s*\(\s*['"]([^'"]+)['"]/g;

  const keys = [];
  let match;
  while ((match = regex.exec(content)) !== null) {
    const key = match[1];
    // Skip template-literal-style dynamic keys that slipped through
    if (key.includes('${')) continue;
    // Skip false positives
    if (isFalsePositiveKey(key)) continue;
    keys.push(key);
  }
  return [...new Set(keys)]; // deduplicate within a file
}

// Determine which namespace a file uses
function detectNamespace(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  // Match useTranslation('namespace')
  const regex = /useTranslation\s*\(\s*['"]([^'"]+)['"]/g;
  let match;
  const namespaces = new Set();
  while ((match = regex.exec(content)) !== null) {
    namespaces.add(match[1]);
  }
  // Files without useTranslation use 'common' by default
  return namespaces.size > 0 ? [...namespaces] : ['common'];
}

// Find all .tsx/.ts files (skip test files and node_modules)
function findSourceFiles(dir, files = []) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.git') continue;
      findSourceFiles(fullPath, files);
    } else if (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) {
      // Skip test files entirely
      if (!isTestFile(fullPath)) {
        files.push(fullPath);
      }
    }
  }
  return files;
}

// Load locale file
function loadLocale(lang, namespace) {
  const localePath = path.join(LOCALES_DIR, lang, `${namespace}.json`);
  if (!fs.existsSync(localePath)) return null;
  try {
    let raw = fs.readFileSync(localePath, 'utf-8');
    // Strip UTF-8 BOM
    if (raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1);
    return JSON.parse(raw);
  } catch (e) {
    console.error(`Failed to parse ${localePath}: ${e.message}`);
    return null;
  }
}

// Flatten nested JSON keys with dot notation
function flattenKeys(obj, prefix = '') {
  const keys = new Set();
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    keys.add(fullKey);
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const nested of flattenKeys(v, fullKey)) {
        keys.add(nested);
      }
    }
  }
  return keys;
}

// Main
let errors = 0;
let warnings = 0;

console.log('🔍 Checking i18n keys...\n');

const sourceFiles = findSourceFiles(SRC_DIR);

for (const file of sourceFiles) {
  const namespaces = detectNamespace(file);
  const keys = findTranslationKeys(file);
  if (keys.length === 0) continue;

  // Build a set of all available keys across relevant namespaces and languages
  for (const lang of LANGUAGES) {
    // Collect all keys from all available locale files for this language
    const allAvailableKeys = new Set();
    for (const ns of ['common', 'chat', 'admin']) {
      const locale = loadLocale(lang, ns);
      if (locale) {
        for (const k of flattenKeys(locale)) {
          allAvailableKeys.add(k);
        }
      }
    }

    for (const key of keys) {
      if (!allAvailableKeys.has(key)) {
        const relFile = path.relative(SRC_DIR, file);
        console.error(`❌ Missing key "${key}" in ${lang} locale (used in ${relFile})`);
        errors++;
      }
    }
  }
}

console.log(`\n📊 Checked ${sourceFiles.length} source files`);
if (errors === 0 && warnings === 0) {
  console.log('✅ All i18n keys are present!');
  process.exit(0);
} else {
  console.log(`\n❌ ${errors} missing keys, ${warnings} warnings`);
  process.exit(errors > 0 ? 1 : 0);
}
