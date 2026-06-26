const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://127.0.0.1:3010';
const OUTPUT_DIR = 'audit_reports/v4.2/ui_ux/screenshots';

// Ensure output directory exists
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

async function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function takeScreenshot(page, filename, width = 1280, height = 720) {
  await page.setViewportSize({ width, height });
  await delay(500);
  const filePath = path.join(OUTPUT_DIR, filename);
  await page.screenshot({ path: filePath, fullPage: false });
  console.log(`Screenshot saved: ${filePath}`);
  return filePath;
}

async function main() {
  console.log('Launching browser...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // === Test 1: Login Page ===
    console.log('Navigating to login page...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await delay(2000);
    await takeScreenshot(page, 'v42_login_page.png', 1280, 720);
    console.log('Login page screenshot taken');

    // Check login page elements
    const hasEmailInput = await page.locator('input[type="email"], input[type="text"]').count() > 0;
    const hasPasswordInput = await page.locator('input[type="password"]').count() > 0;
    console.log(`Login page has email input: ${hasEmailInput}`);
    console.log(`Login page has password input: ${hasPasswordInput}`);

    // === Test 2: Try Demo Login (if available) ===
    // Look for demo login button
    const demoBtn = await page.locator('button:has-text("Demo"), button:has-text("demo")').first();
    if (await demoBtn.isVisible().catch(() => false)) {
      console.log('Found demo login button');
      await demoBtn.click();
      await delay(3000);
      await takeScreenshot(page, 'v42_after_demo_login.png', 1280, 720);
    } else {
      console.log('No demo login button found, attempting manual login...');
      // Try to fill in login form
      const emailInput = await page.locator('input[type="email"], input[type="text"]').first();
      const passwordInput = await page.locator('input[type="password"]').first();
      const submitBtn = await page.locator('button[type="submit"]').first();

      if (await emailInput.isVisible().catch(() => false)) {
        await emailInput.fill('admin@example.com');
        await passwordInput.fill('admin123');
        await submitBtn.click();
        await delay(5000);
        await takeScreenshot(page, 'v42_after_login.png', 1280, 720);
      }
    }

    // === Test 3: Welcome Screen ===
    console.log('Checking welcome screen...');
    await delay(2000);
    const welcomeCards = await page.locator('.welcome-card').count();
    console.log(`Welcome screen has ${welcomeCards} quick action cards`);
    if (welcomeCards > 0) {
      await takeScreenshot(page, 'v42_welcome_screen.png', 1280, 720);
    }

    // === Test 4: Dark Mode Toggle (BUG-005, BUG-015) ===
    console.log('Checking dark mode...');
    const themeToggle = await page.locator('button[aria-label*="theme"], .theme-toggle, [data-testid="theme-toggle"]').first();
    if (await themeToggle.isVisible().catch(() => false)) {
      await themeToggle.click();
      await delay(1000);
      await takeScreenshot(page, 'v42_dark_mode.png', 1280, 720);

      // Toggle back to light
      await themeToggle.click();
      await delay(500);
    }

    // === Test 5: Sidebar Search (BUG-012) ===
    console.log('Checking sidebar search...');
    const searchInput = await page.locator('input[placeholder*="搜索"], input[placeholder*="Search"], #sidebar-search-input').first();
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill('test');
      await delay(1000);
      await takeScreenshot(page, 'v42_sidebar_search.png', 1280, 720);
    }

    // === Test 6: Chat Input (BUG-006) ===
    console.log('Checking chat input...');
    const chatInput = await page.locator('textarea, input[placeholder*="输入"], input[placeholder*="message"]').first();
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill('Hello, this is a test message');
      await delay(500);
      await takeScreenshot(page, 'v42_chat_input.png', 1280, 720);
    }

    // === Test 7: Mobile Viewport Test (BUG-006) ===
    console.log('Testing mobile viewport...');
    await page.setViewportSize({ width: 375, height: 667 });
    await delay(1000);
    await takeScreenshot(page, 'v42_mobile_viewport.png', 375, 667);

    // Reset viewport
    await page.setViewportSize({ width: 1280, height: 720 });
    await delay(500);

    console.log('All screenshots captured successfully');

  } catch (error) {
    console.error('Error during audit:', error.message);
  } finally {
    await browser.close();
    console.log('Browser closed');
  }
}

main().catch(console.error);
