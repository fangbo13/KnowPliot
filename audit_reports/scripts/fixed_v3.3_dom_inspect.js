/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Diagnostic: inspect full DOM structure of the sidebar search area
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });

  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  // Login
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  const email = page.locator('input[type="email"]');
  const password = page.locator('input[type="password"]');
  if (await email.count() > 0) {
    await email.fill('admin@ey.com');
    await password.fill('admin123');
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(3000);
  }

  // Get the DOM structure around the search input
  const structure = await page.evaluate(() => {
    const input = document.getElementById('sidebar-search-input');
    if (!input) return { error: 'input not found' };

    // Get the parent chain
    const parents = [];
    let el = input;
    while (el && parents.length < 5) {
      const computed = window.getComputedStyle(el);
      parents.push({
        tag: el.tagName,
        id: el.id || undefined,
        classes: el.className ? el.className.split(' ').filter(c => c && !c.startsWith('css-dev-only')) : [],
        height: computed.height,
        minHeight: computed.minHeight,
        padding: computed.padding,
        border: computed.border,
        borderRadius: computed.borderRadius,
        background: computed.background,
      });
      el = el.parentElement;
    }

    return parents;
  });
  console.log('DOM structure (from input upward):');
  structure.forEach((s, i) => {
    console.log(`  Level ${i}: ${s.tag}${s.id ? '#' + s.id : ''}.${s.classes?.join('.') || ''}`);
    console.log(`    height=${s.height}, minH=${s.minHeight}, padding=${s.padding}, border=${s.border}, radius=${s.borderRadius}`);
  });

  // Measure actual bounding boxes
  const boxes = await page.evaluate(() => {
    const input = document.getElementById('sidebar-search-input');
    if (!input) return [];

    const results = [];
    let el = input;
    while (el && results.length < 5) {
      const rect = el.getBoundingClientRect();
      results.push({
        tag: el.tagName,
        id: el.id || '',
        classes: el.className ? el.className.split(' ').filter(c => c && !c.startsWith('css-dev-only')).join(' ') : '',
        width: rect.width,
        height: rect.height,
        top: rect.top,
        left: rect.left,
      });
      el = el.parentElement;
    }
    return results;
  });

  console.log('\nBounding boxes:');
  boxes.forEach((b, i) => {
    console.log(`  ${b.tag}#${b.id}.${b.classes}: ${b.width}x${b.height}px`);
  });

  await ctx.close();
  await browser.close();
})();
