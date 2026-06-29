/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const screenshotsDir = 'd:/Github/Onborading-AI/project_audit_output/screenshots';
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  // Login
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.locator('#email').fill('admin@ey.com');
  await page.locator('#password').fill('admin123');
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(3000);
  console.log('After login URL:', page.url());

  // Measure search input dimensions
  const dims = await page.evaluate(() => {
    const input = document.getElementById('sidebar-search-input');
    const wrapper = input?.closest('.ant-input-affix-wrapper');
    const iBox = input?.getBoundingClientRect();
    const wBox = wrapper?.getBoundingClientRect();
    const iComputed = input ? window.getComputedStyle(input) : null;
    const wComputed = wrapper ? window.getComputedStyle(wrapper) : null;
    return {
      inputHeight: iBox?.height,
      wrapperHeight: wBox?.height,
      inputComputedStyle: { height: iComputed?.height, padding: iComputed?.padding },
      wrapperComputedStyle: { height: wComputed?.height, padding: wComputed?.padding, minHeight: wComputed?.minHeight },
    };
  });
  console.log('Search dimensions:', JSON.stringify(dims));

  // Take screenshot
  await page.screenshot({ path: `${screenshotsDir}/fixed_v3.3_sidebar_search-desktop-light.png`, fullPage: false });

  // Navigate to profile page
  await page.goto('http://localhost:3000/profile', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // Check field_not_set display
  const notSetCount = await page.locator('text=暂未设置').count() + await page.locator('text=Not set').count();
  const dashCount = await page.locator('text=—').count();
  console.log('field_not_set count:', notSetCount);
  console.log('Em dash count:', dashCount);

  // Check styling of field_not_set elements
  const stylingInfo = await page.evaluate(() => {
    const spans = document.querySelectorAll('span');
    const notSetSpans = Array.from(spans).filter(s =>
      s.textContent?.includes('暂未设置') || s.textContent?.includes('Not set')
    );
    return notSetSpans.map(s => {
      const c = window.getComputedStyle(s);
      return { color: c.color, fontStyle: c.fontStyle, fontSize: c.fontSize };
    });
  });
  console.log('field_not_set styling:', JSON.stringify(stylingInfo));

  await page.screenshot({ path: `${screenshotsDir}/fixed_v3.3_profile_empty_fields-desktop-light.png`, fullPage: false });

  // Dark mode profile
  await page.evaluate(() => localStorage.setItem('ey-theme', 'dark'));
  await page.goto('http://localhost:3000/profile', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.waitForTimeout(500);

  // Check dark mode styling
  const darkStylingInfo = await page.evaluate(() => {
    const spans = document.querySelectorAll('span');
    const notSetSpans = Array.from(spans).filter(s =>
      s.textContent?.includes('暂未设置') || s.textContent?.includes('Not set')
    );
    return notSetSpans.map(s => {
      const c = window.getComputedStyle(s);
      return { color: c.color, fontStyle: c.fontStyle };
    });
  });
  console.log('Dark mode field_not_set styling:', JSON.stringify(darkStylingInfo));

  await page.screenshot({ path: `${screenshotsDir}/fixed_v3.3_profile_empty_fields-desktop-dark.png`, fullPage: false });

  await ctx.close();
  await browser.close();
  console.log('\n=== Final verification complete ===');
})();
