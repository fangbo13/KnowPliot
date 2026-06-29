/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Diagnostic: inspect actual CSS properties of sidebar search input
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });

  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  // Login
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  const email = page.locator('input[type="email"], input[id*="email"]');
  const password = page.locator('input[type="password"]');
  if (await email.count() > 0) {
    await email.fill('admin@ey.com');
    await password.fill('admin123');
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(3000);
  }

  // Navigate to chat page
  await page.waitForURL(/\/(chat|profile)/, { timeout: 5000 }).catch(() => {});

  // Inspect the search input's CSS properties
  const searchWrapper = page.locator('#sidebar-search-input');
  const cssInfo = await searchWrapper.evaluate((el) => {
    const computed = window.getComputedStyle(el);
    return {
      minHeight: computed.minHeight,
      height: computed.height,
      padding: computed.padding,
      border: computed.border,
      borderRadius: computed.borderRadius,
      borderWidth: computed.borderWidth,
      boxSizing: computed.boxSizing,
      lineHeight: computed.lineHeight,
      fontSize: computed.fontSize,
      className: el.className,
      tagName: el.tagName,
      innerHTML_snippet: el.innerHTML.substring(0, 200),
      // Check if our CSS rule is applied
      hasImportantOverride: computed.minHeight !== '0px' && computed.minHeight !== 'auto',
    };
  });
  console.log('Search wrapper CSS info:', JSON.stringify(cssInfo, null, 2));

  // Also check the inner input element
  const innerInput = page.locator('#sidebar-search-input .ant-input');
  const innerCssInfo = await innerInput.evaluate((el) => {
    const computed = window.getComputedStyle(el);
    return {
      minHeight: computed.minHeight,
      height: computed.height,
      padding: computed.padding,
      lineHeight: computed.lineHeight,
      boxSizing: computed.boxSizing,
      className: el.className,
    };
  });
  console.log('Inner input CSS info:', JSON.stringify(innerCssInfo, null, 2));

  await ctx.close();
  await browser.close();
})();
