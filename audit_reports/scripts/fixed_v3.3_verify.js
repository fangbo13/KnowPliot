/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V3.3 Fix Verification Script - Screenshots for all repaired items
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const screenshotsDir = 'd:/Github/Onborading-AI/project_audit_output/screenshots';

  // ========== Test 1: Login page (check i18n EN mode works) ==========
  const ctx1 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page1 = await ctx1.newPage();
  await page1.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page1.waitForTimeout(2000);
  await page1.screenshot({ path: `${screenshotsDir}/fixed_v3.3_login_page_en-desktop-light.png`, fullPage: false });
  await ctx1.close();

  // ========== Test 2: Sidebar search (P0-2 fix - check visual height) ==========
  const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page2 = await ctx2.newPage();
  // Login first
  await page2.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page2.waitForTimeout(1500);
  // Fill demo credentials
  const emailInput = page2.locator('input[type="email"], input[id*="email"]');
  const passwordInput = page2.locator('input[type="password"]');
  if (await emailInput.count() > 0) {
    await emailInput.fill('admin@ey.com');
    await passwordInput.fill('admin123');
    await page2.locator('button[type="submit"]').click();
  }
  // Try demo button approach
  const demoBtn = page2.locator('button').filter({ hasText: /demo|演示/ });
  if (await demoBtn.count() > 0) {
    await demoBtn.click();
    await page2.waitForTimeout(500);
    await page2.locator('button[type="submit"]').click();
  }
  await page2.waitForTimeout(3000);
  await page2.waitForURL(/\/(chat|profile)/, { timeout: 8000 }).catch(() => {});

  // Check if we're on a page with sidebar
  const currentUrl = page2.url();
  console.log('Current URL after login:', currentUrl);

  // Take sidebar search screenshot
  const searchInput = page2.locator('#sidebar-search-input');
  if (await searchInput.count() > 0) {
    // Measure the search input height
    const box = await searchInput.boundingBox();
    if (box) {
      console.log('Search input dimensions:', JSON.stringify(box));
      console.log('Search input height:', box.height, 'px');
    }
    // Screenshot of sidebar area with search
    await page2.screenshot({ path: `${screenshotsDir}/fixed_v3.3_sidebar_search-desktop-light.png`, fullPage: false });
  } else {
    console.log('Search input not found, taking full page screenshot');
    await page2.screenshot({ path: `${screenshotsDir}/fixed_v3.3_sidebar_search-desktop-light.png`, fullPage: false });
  }
  await ctx2.close();

  // ========== Test 3: Profile page (P1-1 fix - check empty field display) ==========
  const ctx3 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page3 = await ctx3.newPage();
  // Login
  await page3.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page3.waitForTimeout(1500);
  const email3 = page3.locator('input[type="email"], input[id*="email"]');
  const password3 = page3.locator('input[type="password"]');
  if (await email3.count() > 0) {
    await email3.fill('admin@ey.com');
    await password3.fill('admin123');
    await page3.locator('button[type="submit"]').click();
  }
  await page3.waitForTimeout(3000);
  // Navigate to profile
  await page3.goto('http://localhost:3000/profile', { waitUntil: 'networkidle' }).catch(() => {});
  await page3.waitForTimeout(2000);

  // Check for field_not_set text
  const notSetTexts = await page3.locator('text=暂未设置').count();
  const notSetEnTexts = await page3.locator('text=Not set').count();
  console.log('field_not_set (ZH) count:', notSetTexts);
  console.log('field_not_set (EN) count:', notSetEnTexts);

  // Check for em dash fallback (should not exist anymore for service_line, office_location, role_level)
  const dashCount = await page3.locator('text=—').count();
  console.log('Em dash "—" count (should be 0 or 1 for email):', dashCount);

  await page3.screenshot({ path: `${screenshotsDir}/fixed_v3.3_profile_empty_fields-desktop-light.png`, fullPage: false });

  // Also test dark mode profile
  await page3.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
    // Trigger theme change via localStorage
    localStorage.setItem('ey-theme', 'dark');
  });
  await page3.waitForTimeout(1000);
  await page3.reload({ waitUntil: 'networkidle' });
  await page3.waitForTimeout(2000);
  await page3.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
  });
  await page3.waitForTimeout(500);
  await page3.screenshot({ path: `${screenshotsDir}/fixed_v3.3_profile_empty_fields-desktop-dark.png`, fullPage: false });
  await ctx3.close();

  // ========== Test 4: i18n ZH mode verification ==========
  const ctx4 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page4 = await ctx4.newPage();
  // Set language to ZH before navigating
  await page4.evaluate(() => {
    localStorage.setItem('ey-language', 'zh');
  });
  await page4.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page4.waitForTimeout(2000);

  // Check that key ZH translations are present (no English fallback)
  const userMenuZh = await page4.locator('text=用户菜单').count();
  const loginTitleZh = await page4.locator('text=欢迎回来').count();
  console.log('ZH user_menu translation count:', userMenuZh);
  console.log('ZH login_title translation count:', loginTitleZh);

  await page4.screenshot({ path: `${screenshotsDir}/fixed_v3.3_login_page_zh-desktop-light.png`, fullPage: false });
  await ctx4.close();

  await browser.close();
  console.log('\n=== All screenshots taken successfully ===');
})();
