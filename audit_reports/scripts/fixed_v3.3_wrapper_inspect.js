/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  // Login
  await page.locator('input[type="email"]').fill('admin@ey.com');
  await page.locator('input[type="password"]').fill('admin123');
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(3000);
  console.log('URL:', page.url());

  // Get parent chain of search input
  const html = await page.evaluate(() => {
    const input = document.getElementById('sidebar-search-input');
    if (!input) return 'NOT FOUND';
    // Get outerHTML of the wrapper div parent
    let el = input.parentElement;
    for (let i = 0; i < 3 && el; i++) {
      el = el.parentElement;
    }
    return el ? el.outerHTML.substring(0, 1000) : 'no parent';
  });
  console.log('Parent HTML snippet:', html);

  // Get wrapper info
  const wrapperInfo = await page.evaluate(() => {
    const input = document.getElementById('sidebar-search-input');
    if (!input) return null;

    // Find the affix-wrapper parent
    const wrapper = input.closest('.ant-input-affix-wrapper');
    if (!wrapper) return { found: false, inputTag: input.tagName };

    const wComputed = window.getComputedStyle(wrapper);
    const iComputed = window.getComputedStyle(input);

    return {
      found: true,
      wrapperTag: wrapper.tagName,
      wrapperClasses: Array.from(wrapper.classList).filter(c => !c.startsWith('css-dev-only')).join(' '),
      wrapperId: wrapper.id,
      wrapperHeight: wComputed.height,
      wrapperMinHeight: wComputed.minHeight,
      wrapperPadding: wComputed.padding,
      wrapperBorder: wComputed.border,
      wrapperBorderRadius: wComputed.borderRadius,
      inputTag: input.tagName,
      inputHeight: iComputed.height,
      inputPadding: iComputed.padding,
    };
  });
  console.log('Wrapper info:', JSON.stringify(wrapperInfo));

  await ctx.close();
  await browser.close();
})();
