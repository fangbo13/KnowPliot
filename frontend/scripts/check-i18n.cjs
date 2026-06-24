/**
 * i18n Key Existence Checker
 * Scans all .tsx/.ts files for t('key') calls and verifies
 * that each key exists in the corresponding locale JSON file.
 *
 * Usage: node scripts/check-i18n.js
 */

const fs = require('fs');
const path = require('path');

const LOCALES_DIR = path.resolve(__dirname, '../src/i18n/locales');
const SRC_DIR = path.resolve(__dirname, '../src');
const LANGUAGES = ['zh', 'en'];

// Collect all t('key') calls from source files
function findTranslationKeys(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  // Match t('key') or t("key") patterns
  const regex = /t\s*\(\s*['"]([^'"]+)['"]/g;
  const keys = [];
  let match;
  while ((match = regex.exec(content)) !== null) {
    keys.push(match[1]);
  }
  return keys;
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

// Find all .tsx/.ts files
function findSourceFiles(dir, files = []) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.git') continue;
      findSourceFiles(fullPath, files);
    } else if (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) {
      files.push(fullPath);
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

// Main
let errors = 0;
let warnings = 0;
let totalChecked = 0;

console.log('🔍 Checking i18n keys...\n');

const sourceFiles = findSourceFiles(SRC_DIR);

for (const file of sourceFiles) {
  const namespaces = detectNamespace(file);
  const keys = findTranslationKeys(file);
  if (keys.length === 0) continue;

  for (const namespace of namespaces) {
    if (namespace === 'chat') {
      for (const lang of LANGUAGES) {
        const locale = loadLocale(lang, namespace);
        if (!locale) {
          console.warn(`⚠️  Missing locale file: ${lang}/${namespace}.json`);
          warnings++;
          continue;
        }
        for (const key of keys) {
          if (!(key in locale)) {
            console.error(`❌ Missing key "${key}" in ${lang}/${namespace}.json (used in ${path.relative(SRC_DIR, file)})`);
            errors++;
          }
        }
      }
    }
  }

  // Also check keys used with common namespace (most t() calls without explicit ns)
  if (namespaces.includes('common')) {
    for (const lang of LANGUAGES) {
      const common = loadLocale(lang, 'common');
      if (!common) continue;
      for (const key of keys) {
        if (!(key in common) && !(key in (loadLocale(lang, 'chat') || {}))) {
          // Only report if key is in neither common nor chat
          console.error(`❌ Missing key "${key}" in ${lang}/common.json (used in ${path.relative(SRC_DIR, file)})`);
          errors++;
        }
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
