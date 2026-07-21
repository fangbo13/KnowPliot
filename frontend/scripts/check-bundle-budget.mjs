import { readdir, readFile, lstat } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const BUNDLE_LIMITS = Object.freeze({
  initialJsGzipBytes: 250 * 1024,
  lazyJsGzipBytes: 400 * 1024,
});

const AUTHENTICATED_ROUTE_ENTRIES = [
  { source: 'src/layout/AppLayout.tsx', name: 'AppLayout' },
  { source: 'src/pages/ChatPage.tsx', name: 'ChatPage' },
];
const MANIFEST_PATH = '.vite/manifest.json';
const INDEX_PATH = 'index.html';
const CONTROL_CHARACTER = /[\u0000-\u001f\u007f]/;

export class BundleBudgetError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'BundleBudgetError';
    this.code = code;
  }
}

function fail(code, message) {
  throw new BundleBudgetError(code, message);
}

function normalizeArtifactPath(value) {
  if (typeof value !== 'string' || value.length === 0) {
    fail('invalid_artifact_path', 'Bundle metadata contains an invalid artifact path.');
  }
  if (
    CONTROL_CHARACTER.test(value) ||
    value.includes('\\') ||
    value.includes(':') ||
    path.posix.isAbsolute(value)
  ) {
    fail('unsafe_artifact_path', 'Bundle metadata contains an unsafe artifact path.');
  }

  const normalized = path.posix.normalize(value);
  if (
    normalized !== value ||
    normalized === '..' ||
    normalized.startsWith('../') ||
    normalized.split('/').includes('..')
  ) {
    fail('unsafe_artifact_path', 'Bundle metadata contains an unsafe artifact path.');
  }
  return normalized;
}

function normalizeLimits(limits) {
  const normalized = {
    initialJsGzipBytes:
      limits?.initialJsGzipBytes ?? BUNDLE_LIMITS.initialJsGzipBytes,
    lazyJsGzipBytes:
      limits?.lazyJsGzipBytes ?? BUNDLE_LIMITS.lazyJsGzipBytes,
  };
  if (
    !Number.isSafeInteger(normalized.initialJsGzipBytes) ||
    normalized.initialJsGzipBytes < 0 ||
    !Number.isSafeInteger(normalized.lazyJsGzipBytes) ||
    normalized.lazyJsGzipBytes < 0
  ) {
    fail('invalid_bundle_limits', 'Bundle limits must be non-negative integer byte counts.');
  }
  return normalized;
}

function readAttributes(tag) {
  const attributes = new Map();
  const attributePattern = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
  for (const match of tag.matchAll(attributePattern)) {
    attributes.set(match[1].toLowerCase(), match[2] ?? match[3] ?? match[4] ?? '');
  }
  return attributes;
}

function htmlModuleReferences(html) {
  const scripts = [];
  const modulepreloads = [];
  const tagPattern = /<(script|link)\b[^>]*>/gi;
  for (const match of html.matchAll(tagPattern)) {
    const tagName = match[1].toLowerCase();
    const attributes = readAttributes(match[0]);
    if (
      tagName === 'script' &&
      attributes.get('type')?.toLowerCase() === 'module' &&
      attributes.has('src')
    ) {
      scripts.push(attributes.get('src'));
    }
    if (
      tagName === 'link' &&
      attributes.get('rel')?.toLowerCase().split(/\s+/).includes('modulepreload') &&
      attributes.has('href')
    ) {
      modulepreloads.push(attributes.get('href'));
    }
  }
  return { scripts, modulepreloads };
}

function emittedPathFromUrl(value, emittedFiles) {
  if (typeof value !== 'string' || CONTROL_CHARACTER.test(value)) {
    fail('unsafe_html_module_reference', 'index.html contains an unsafe module reference.');
  }

  let url;
  try {
    url = new URL(value, 'https://bundle.invalid/');
  } catch {
    fail('unsafe_html_module_reference', 'index.html contains an unsafe module reference.');
  }
  if (url.origin !== 'https://bundle.invalid') {
    fail('external_html_module_reference', 'index.html contains an unmeasurable external module reference.');
  }

  let pathname;
  try {
    pathname = decodeURIComponent(url.pathname).replace(/^\/+/, '');
  } catch {
    fail('unsafe_html_module_reference', 'index.html contains an unsafe module reference.');
  }

  const direct = emittedFiles.has(pathname) ? pathname : null;
  if (direct) return direct;

  const suffixMatches = [...emittedFiles].filter((file) => pathname.endsWith(`/${file}`));
  if (suffixMatches.length === 1) return suffixMatches[0];

  fail('unknown_html_module_reference', 'index.html references a module missing from the build manifest.');
}

function validateManifest(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail('invalid_manifest', 'The Vite manifest must be a JSON object.');
  }

  const fileToKey = new Map();
  for (const [key, chunk] of Object.entries(value)) {
    if (!chunk || typeof chunk !== 'object' || Array.isArray(chunk)) {
      fail('invalid_manifest_chunk', 'The Vite manifest contains an invalid chunk.');
    }
    const file = normalizeArtifactPath(chunk.file);
    if (fileToKey.has(file)) {
      fail('duplicate_manifest_file', 'The Vite manifest maps more than one chunk to one file.');
    }
    fileToKey.set(file, key);

    if (chunk.imports !== undefined) {
      if (!Array.isArray(chunk.imports) || chunk.imports.some((item) => typeof item !== 'string')) {
        fail('invalid_manifest_imports', 'The Vite manifest contains invalid static imports.');
      }
    }
  }

  for (const chunk of Object.values(value)) {
    for (const importedKey of chunk.imports ?? []) {
      if (!Object.hasOwn(value, importedKey)) {
        fail('missing_manifest_import', 'The Vite manifest references a missing static import.');
      }
    }
  }

  return { manifest: value, fileToKey };
}

function collectStaticFiles(manifest, rootKeys, initialFiles) {
  const visitedKeys = new Set();
  const visit = (key) => {
    if (visitedKeys.has(key)) return;
    visitedKeys.add(key);
    const chunk = manifest[key];
    if (!chunk) {
      fail('missing_manifest_chunk', 'A required build entry is missing from the Vite manifest.');
    }
    initialFiles.add(normalizeArtifactPath(chunk.file));
    for (const importedKey of chunk.imports ?? []) visit(importedKey);
  };
  for (const rootKey of rootKeys) visit(rootKey);
}

function resolveRouteEntryKey(manifest, descriptor) {
  const direct = manifest[descriptor.source];
  if (direct) return descriptor.source;
  const candidates = Object.entries(manifest)
    .filter(([key, chunk]) =>
      chunk?.isDynamicEntry === true &&
      (chunk.src === descriptor.source || chunk.name === descriptor.name || key.includes(descriptor.name)),
    )
    .map(([key]) => key);
  return candidates.length === 1 ? candidates[0] : null;
}

async function listEmittedFiles(distDir, relativeDir = '') {
  const absoluteDir = path.join(distDir, ...relativeDir.split('/').filter(Boolean));
  const entries = await readdir(absoluteDir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const relativePath = normalizeArtifactPath(
      relativeDir ? `${relativeDir}/${entry.name}` : entry.name,
    );
    if (entry.isSymbolicLink()) {
      fail('unsafe_bundle_symlink', 'The build output contains a symbolic link.');
    }
    if (entry.isDirectory()) {
      files.push(...await listEmittedFiles(distDir, relativePath));
    } else if (entry.isFile()) {
      files.push(relativePath);
    }
  }
  return files;
}

async function measureFiles(distDir, files) {
  return Promise.all(
    [...files].sort().map(async (file) => {
      const normalized = normalizeArtifactPath(file);
      const absolute = path.resolve(distDir, ...normalized.split('/'));
      const expectedPrefix = `${path.resolve(distDir)}${path.sep}`;
      if (!absolute.startsWith(expectedPrefix)) {
        fail('unsafe_artifact_path', 'Bundle metadata contains an unsafe artifact path.');
      }
      const stats = await lstat(absolute).catch(() => null);
      if (!stats?.isFile() || stats.isSymbolicLink()) {
        fail('missing_bundle_artifact', 'A measured bundle artifact is missing or unsafe.');
      }
      const contents = await readFile(absolute);
      return {
        file: normalized,
        raw_bytes: contents.byteLength,
        gzip_bytes: gzipSync(contents).byteLength,
      };
    }),
  );
}

function sumFiles(files) {
  return {
    raw_bytes: files.reduce((total, file) => total + file.raw_bytes, 0),
    gzip_bytes: files.reduce((total, file) => total + file.gzip_bytes, 0),
  };
}

export async function analyzeBundleBudget({
  distDir = path.resolve('dist'),
  limits,
} = {}) {
  const normalizedLimits = normalizeLimits(limits);
  const absoluteDistDir = path.resolve(distDir);
  const manifestFile = path.join(absoluteDistDir, '.vite', 'manifest.json');
  const indexFile = path.join(absoluteDistDir, 'index.html');

  let rawManifest;
  try {
    rawManifest = JSON.parse(await readFile(manifestFile, 'utf8'));
  } catch (error) {
    if (error instanceof SyntaxError) {
      fail('invalid_manifest_json', 'The Vite manifest is not valid JSON.');
    }
    fail('missing_manifest', 'Run a clean production build before checking the bundle budget.');
  }
  const { manifest, fileToKey } = validateManifest(rawManifest);

  let html;
  try {
    html = await readFile(indexFile, 'utf8');
  } catch {
    fail('missing_index_html', 'The production index.html artifact is missing.');
  }

  const emittedManifestFiles = new Set(fileToKey.keys());
  const references = htmlModuleReferences(html);
  if (references.scripts.length === 0) {
    fail('missing_html_entry', 'index.html does not contain a module entry script.');
  }

  const entryFiles = references.scripts.map((reference) =>
    emittedPathFromUrl(reference, emittedManifestFiles));
  const entryKeys = entryFiles.map((file) => fileToKey.get(file));
  if (
    entryKeys.some((key) => !key) ||
    entryKeys.some((key) => manifest[key].isEntry !== true)
  ) {
    fail('invalid_html_entry', 'index.html does not reference a Vite manifest entry.');
  }

  const initialFiles = new Set();
  collectStaticFiles(manifest, entryKeys, initialFiles);

  const preloadFiles = references.modulepreloads.map((reference) =>
    emittedPathFromUrl(reference, emittedManifestFiles));
  for (const file of preloadFiles) {
    const key = fileToKey.get(file);
    if (key) collectStaticFiles(manifest, [key], initialFiles);
    else initialFiles.add(file);
  }

  const resolvedRouteEntries = AUTHENTICATED_ROUTE_ENTRIES.map((descriptor) => ({
    ...descriptor,
    manifestKey: resolveRouteEntryKey(manifest, descriptor),
  }));
  const routeEntryKeys = resolvedRouteEntries
    .map(({ manifestKey }) => manifestKey)
    .filter((key) => key !== null);
  if (routeEntryKeys.length > 0) {
    collectStaticFiles(manifest, routeEntryKeys, initialFiles);
  }

  const emittedFiles = await listEmittedFiles(absoluteDistDir);
  const ignoredMetadata = new Set([MANIFEST_PATH, INDEX_PATH]);
  const jsFiles = new Set(
    emittedFiles.filter((file) => /\.(?:c|m)?js$/i.test(file)),
  );
  for (const file of initialFiles) {
    if (!jsFiles.has(file)) {
      fail('missing_initial_js_artifact', 'An initial JavaScript artifact is missing from the build output.');
    }
  }

  const lazyFiles = new Set([...jsFiles].filter((file) => !initialFiles.has(file)));
  const cssFiles = new Set(emittedFiles.filter((file) => /\.css$/i.test(file)));
  const assetFiles = new Set(
    emittedFiles.filter((file) =>
      !ignoredMetadata.has(file) &&
      !jsFiles.has(file) &&
      !cssFiles.has(file) &&
      !/\.map$/i.test(file)),
  );

  const [initialMeasurements, lazyMeasurements, cssMeasurements, assetMeasurements] =
    await Promise.all([
      measureFiles(absoluteDistDir, initialFiles),
      measureFiles(absoluteDistDir, lazyFiles),
      measureFiles(absoluteDistDir, cssFiles),
      measureFiles(absoluteDistDir, assetFiles),
    ]);

  const initialTotals = sumFiles(initialMeasurements);
  const cssTotals = sumFiles(cssMeasurements);
  const assetTotals = sumFiles(assetMeasurements);
  const violations = [];
  if (initialTotals.gzip_bytes > normalizedLimits.initialJsGzipBytes) {
    violations.push({
      code: 'initial_js_gzip_budget_exceeded',
      gzip_bytes: initialTotals.gzip_bytes,
      limit_bytes: normalizedLimits.initialJsGzipBytes,
    });
  }
  for (const file of lazyMeasurements) {
    if (file.gzip_bytes > normalizedLimits.lazyJsGzipBytes) {
      violations.push({
        code: 'lazy_js_gzip_budget_exceeded',
        file: file.file,
        gzip_bytes: file.gzip_bytes,
        limit_bytes: normalizedLimits.lazyJsGzipBytes,
      });
    }
  }

  return {
    schema_version: 1,
    status: violations.length === 0 ? 'pass' : 'fail',
    route: '/chat',
    compression: { format: 'gzip', level: 'zlib-default' },
    limits: {
      initial_js_gzip_bytes: normalizedLimits.initialJsGzipBytes,
      lazy_js_gzip_bytes: normalizedLimits.lazyJsGzipBytes,
    },
    route_entries: resolvedRouteEntries.map(({ source, manifestKey }) => ({
      manifest_key: manifestKey,
      source,
      disposition: manifestKey ? 'dynamic_entry' : 'included_in_html_entry',
    })),
    initial: {
      ...initialTotals,
      limit_bytes: normalizedLimits.initialJsGzipBytes,
      files: initialMeasurements,
    },
    lazy: {
      limit_bytes: normalizedLimits.lazyJsGzipBytes,
      files: lazyMeasurements,
    },
    css: { ...cssTotals, files: cssMeasurements },
    assets: { ...assetTotals, files: assetMeasurements },
    violations,
  };
}

async function runCli() {
  try {
    const report = await analyzeBundleBudget();
    console.log(JSON.stringify(report, null, 2));
    if (report.status === 'fail') {
      for (const violation of report.violations) {
        console.error(JSON.stringify(violation));
      }
      process.exitCode = 1;
    }
  } catch (error) {
    const code = error instanceof BundleBudgetError
      ? error.code
      : 'bundle_budget_checker_error';
    const message = error instanceof BundleBudgetError
      ? error.message
      : 'The bundle budget checker failed unexpectedly.';
    console.log(JSON.stringify({
      schema_version: 1,
      status: 'error',
      error: { code, message },
    }, null, 2));
    console.error(JSON.stringify({ code, message }));
    process.exitCode = 1;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await runCli();
}
