// Quick verification: search input height after CSS fix
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const screenshotsDir = 'd:/Github/Onborading-AI/project_audit_output/screenshots';

  // Login and navigate to chat page
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  // Fill demo credentials
  const email = page.locator('input[type="email"], input[id*="email"], input[placeholder*="email"]');
  const password = page.locator('input[type="password"], input[id*="password"], input[placeholder*="密码"], input[placeholder*="password"]');
  if (await email.count() > 0 && await password.count() > 0) {
    await email.fill('admin@ey.com');
    await password.fill('admin123');
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(3000);
  }

  // Try demo button approach if login failed
  const demoBtn = page.locator('button').filter({ hasText: /demo|演示|使用演示/ });
  if (await page.url().includes('login') && await demoBtn.count() > 0) {
    await demoBtn.click();
    await page.waitForTimeout(500);
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(3000);
  }

  // Should be on chat page now
  await page.waitForURL(/\/(chat|profile)/, { timeout: 5000 }).catch(() => {});
  console.log('Current URL:', page.url());

  // Measure search input dimensions
  const searchInput = page.locator('#sidebar-search-input');
  if (await searchInput.count() > 0) {
    const box = await searchInput.boundingBox();
    console.log('Search input height:', box ? box.height : 'NOT FOUND', 'px');

    // Take screenshot of sidebar area with search
    await page.screenshot({ path: `${screenshotsDir}/fixed_v3.3_sidebar_search-desktop-light.png`, fullPage: false });
  } else {
    console.log('Search input NOT found on page');
    await page.screenshot({ path: `${screenshotsDir}/fixed_v3.3_sidebar_search-desktop-light.png`, fullPage: false });
  }

  // Navigate to profile page to check field_not_set
  await page.goto('http://localhost:3000/profile', { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(2000);
  console.log('Profile URL:', page.url());

  const fieldNotSetCount = await page.locator('text=暂未设置').count() + await page.locator('text=Not set').count();
  console.log('field_not_set count:', fieldNotSetCount);

  await page.screenshot({ path: `${screenshotsDir}/fixed_v3.3_profile_empty_fields-desktop-light.png`, fullPage: false });

  // Test dark mode
  await page.evaluate(() => {
    localStorage.setItem('ey-theme', 'dark');
  });
  await page.goto('http://localhost:3000/profile', { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(2000);
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
  });
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${screenshotsDir}/fixed_v3.3_profile_empty_fields-desktop-dark.png`, fullPage: false });

  // Test ZH mode login page
  const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page2 = await ctx2.newPage();
  await page2.evaluate(() => {
    localStorage.setItem('ey-language', 'zh');
  });
  await page2.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page2.waitForTimeout(2000);
  await page2.screenshot({ path: `${screenshotsDir}/fixed_v3.3_login_page_zh-desktop-light.png`, fullPage: false });

  // Test EN mode login page
  const ctx3 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page3 = await ctx3.newPage();
  await page3.evaluate(() => {
    localStorage.setItem('ey-language', 'en');
  });
  await page3.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page3.waitForTimeout(2000);
  await page3.screenshot({ path: `${screenshotsDir}/fixed_v3.3_login_page_en-desktop-light.png`, fullPage: false });

  await ctx.close();
  await ctx2.close();
  await ctx3.close();
  await browser.close();
  console.log('\n=== Verification screenshots taken ===');
})();
