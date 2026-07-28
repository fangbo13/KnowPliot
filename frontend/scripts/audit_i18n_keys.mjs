// One-off audit: collect t('key') refs under src and diff against en/zh common.json
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve('src');
const en = JSON.parse(fs.readFileSync('src/i18n/locales/en/common.json', 'utf8'));
const zh = JSON.parse(fs.readFileSync('src/i18n/locales/zh/common.json', 'utf8'));

const keys = new Set();
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) { walk(p); continue; }
    if (!/\.(tsx?|ts)$/.test(entry.name) || entry.name.endsWith('.test.tsx') || entry.name.endsWith('.test.ts')) continue;
    const text = fs.readFileSync(p, 'utf8');
    for (const m of text.matchAll(/\bt\(\s*'([a-z0-9_.]+)'/g)) keys.add(m[1]);
    for (const m of text.matchAll(/labelKey:\s*'([a-z0-9_.]+)'/g)) keys.add(m[1]);
  }
}
walk(SRC);

const missEn = [...keys].filter((k) => !(k in en)).sort();
const missZh = [...keys].filter((k) => !(k in zh)).sort();
console.log('TOTAL_KEYS', keys.size);
console.log('MISSING_EN', JSON.stringify(missEn, null, 1));
console.log('MISSING_ZH', JSON.stringify(missZh, null, 1));
