// Kept outside Vitest's default *.test.* discovery; run through node --test.
import assert from 'node:assert/strict';
import { gzipSync } from 'node:zlib';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  BUNDLE_LIMITS,
  BundleBudgetError,
  analyzeBundleBudget,
} from './check-bundle-budget.mjs';

async function writeFixture({ html, manifest, files }) {
  const distDir = await mkdtemp(path.join(tmpdir(), 'knowpilot-bundle-budget-'));
  await mkdir(path.join(distDir, '.vite'), { recursive: true });
  await writeFile(path.join(distDir, 'index.html'), html);
  await writeFile(
    path.join(distDir, '.vite', 'manifest.json'),
    JSON.stringify(manifest),
  );
  for (const [file, contents] of Object.entries(files)) {
    const target = path.join(distDir, ...file.split('/'));
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, contents);
  }
  return distDir;
}

function gzipBytes(value) {
  return gzipSync(Buffer.from(value)).byteLength;
}

test('counts entry imports, chat route and modulepreloads once', async () => {
  const contents = {
    entry: 'const entry = "entry";'.repeat(20),
    shared: 'const shared = "shared";'.repeat(20),
    chat: 'const chat = "chat";'.repeat(20),
    preload: 'const preload = "preload";'.repeat(20),
    lazy: 'const lazy = "lazy";'.repeat(20),
    css: '.root { color: rebeccapurple; }'.repeat(10),
    asset: '<svg xmlns="http://www.w3.org/2000/svg"/>',
  };
  const distDir = await writeFixture({
    html:
      '<script type="module" src="/assets/entry.js"></script>' +
      '<link rel="modulepreload" href="/assets/preload.js">',
    manifest: {
      'index.html': {
        file: 'assets/entry.js',
        isEntry: true,
        imports: ['_shared.js'],
      },
      '_shared.js': { file: 'assets/shared.js' },
      '_preload.js': {
        file: 'assets/preload.js',
        imports: ['_shared.js'],
      },
      'src/pages/ChatPage.tsx': {
        file: 'assets/chat.js',
        isDynamicEntry: true,
        imports: ['_shared.js'],
      },
      '_AppLayout.js': {
        file: 'assets/layout.js',
        name: 'AppLayout',
        isDynamicEntry: true,
        imports: ['_shared.js'],
      },
      'src/pages/LazyPage.tsx': {
        file: 'assets/lazy.js',
        isDynamicEntry: true,
        imports: ['_shared.js'],
      },
    },
    files: {
      'assets/entry.js': contents.entry,
      'assets/shared.js': contents.shared,
      'assets/chat.js': contents.chat,
      'assets/layout.js': 'const layout = "layout";'.repeat(20),
      'assets/preload.js': contents.preload,
      'assets/lazy.js': contents.lazy,
      'assets/app.css': contents.css,
      'assets/logo.svg': contents.asset,
    },
  });

  const report = await analyzeBundleBudget({ distDir });

  assert.equal(report.status, 'pass');
  assert.deepEqual(
    report.route_entries.map(({ manifest_key }) => manifest_key),
    ['_AppLayout.js', 'src/pages/ChatPage.tsx'],
  );
  assert.deepEqual(
    report.initial.files.map(({ file }) => file),
    ['assets/chat.js', 'assets/entry.js', 'assets/layout.js', 'assets/preload.js', 'assets/shared.js'],
  );
  assert.equal(
    report.initial.gzip_bytes,
    gzipBytes(contents.chat) +
      gzipBytes(contents.entry) +
      gzipBytes('const layout = "layout";'.repeat(20)) +
      gzipBytes(contents.preload) +
      gzipBytes(contents.shared),
  );
  assert.deepEqual(
    report.lazy.files.map(({ file }) => file),
    ['assets/lazy.js'],
  );
  assert.deepEqual(report.css.files.map(({ file }) => file), ['assets/app.css']);
  assert.deepEqual(report.assets.files.map(({ file }) => file), ['assets/logo.svg']);
});

test('reports initial and individual lazy chunk violations without relaxing limits', async () => {
  const distDir = await writeFixture({
    html: '<script type="module" src="/assets/entry.js"></script>',
    manifest: {
      'index.html': { file: 'assets/entry.js', isEntry: true },
      'src/pages/LazyPage.tsx': {
        file: 'assets/lazy.js',
        isDynamicEntry: true,
      },
    },
    files: {
      'assets/entry.js': 'entry payload',
      'assets/lazy.js': 'lazy payload',
    },
  });

  const report = await analyzeBundleBudget({
    distDir,
    limits: { initialJsGzipBytes: 1, lazyJsGzipBytes: 1 },
  });

  assert.equal(report.status, 'fail');
  assert.deepEqual(
    report.violations.map(({ code }) => code),
    ['initial_js_gzip_budget_exceeded', 'lazy_js_gzip_budget_exceeded'],
  );
  assert.deepEqual(BUNDLE_LIMITS, {
    initialJsGzipBytes: 250 * 1024,
    lazyJsGzipBytes: 400 * 1024,
  });
});

test('rejects unsafe manifest artifact paths', async () => {
  const distDir = await writeFixture({
    html: '<script type="module" src="/assets/entry.js"></script>',
    manifest: {
      'index.html': {
        file: '../entry.js',
        isEntry: true,
      },
    },
    files: { 'assets/entry.js': 'entry payload' },
  });

  await assert.rejects(
    analyzeBundleBudget({ distDir }),
    (error) =>
      error instanceof BundleBudgetError &&
      error.code === 'unsafe_artifact_path',
  );
});
