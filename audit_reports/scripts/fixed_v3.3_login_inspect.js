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
  await page.waitForTimeout(2000);
  console.log('Login page URL:', page.url());

  // Find all inputs on the login page
  const inputInfo = await page.evaluate(() => {
    const inputs = document.querySelectorAll('input');
    return Array.from(inputs).map(i => ({
      type: i.type,
      id: i.id,
      name: i.name,
      placeholder: i.placeholder,
      className: i.className.substring(0, 50),
    }));
  });
  console.log('Inputs on login page:', JSON.stringify(inputInfo));

  // Try to fill login form using any available inputs
  const emailInputs = await page.locator('input').count();
  console.log('Total input count:', emailInputs);

  // Use AntD form - fill by placeholder or label
  if (emailInputs >= 2) {
    const allInputs = page.locator('input');
    // First input should be email
    await allInputs.nth(0).fill('admin@ey.com');
    // Second should be password
    await allInputs.nth(1).fill('admin123');
    // Click submit
    const submitBtn = page.locator('button[type="submit"]');
    if (await submitBtn.count() > 0) {
      await submitBtn.click();
      await page.waitForTimeout(3000);
    }
  }

  console.log('After login URL:', page.url());

  // Now check the sidebar search structure
  if (page.url().includes('/chat')) {
    const wrapperInfo = await page.evaluate(() => {
      const input = document.getElementById('sidebar-search-input');
      if (!input) return { found: false };

      const wrapper = input.closest('.ant-input-affix-wrapper');
      const wComputed = wrapper ? window.getComputedStyle(wrapper) : null;
      const iComputed = window.getComputedStyle(input);

      return {
        found: true,
        hasWrapper: !!wrapper,
        wrapperTag: wrapper?.tagName || null,
        wrapperClasses: wrapper ? Array.from(wrapper.classList).filter(c => !c.startsWith('css-dev-only')).join(' ') : null,
        wrapperId: wrapper?.id || null,
        wrapperHeight: wComputed?.height || null,
        wrapperMinHeight: wComputed?.minHeight || null,
        wrapperPadding: wComputed?.padding || null,
        inputTag: input.tagName,
        inputHeight: iComputed.height,
        inputPadding: iComputed.padding,
      };
    });
    console.log('Wrapper info:', JSON.stringify(wrapperInfo));
  }

  await ctx.close();
  await browser.close();
})();
