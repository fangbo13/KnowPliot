/**
 * EY Onboarding AI — Screenshot capture for UX improvement report
 */
import puppeteer from 'puppeteer';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BASE_URL = 'http://localhost:3000';
const LOGIN_EMAIL = 'admin@ey.com';
const LOGIN_PASSWORD = 'admin123';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

async function login(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('input[type="email"], input[placeholder*="邮箱"]', { timeout: 10000 });
  await page.type('input[type="email"], input[placeholder*="邮箱"]', LOGIN_EMAIL);
  await page.type('input[type="password"]', LOGIN_PASSWORD);
  // SPA navigation — don't waitForNavigation, just click and wait for content
  await page.click('button[type="submit"]');
  await page.waitForSelector('.ant-layout-content, #main-content', { timeout: 15000 });
  await new Promise(r => setTimeout(r, 1000)); // settle
}

async function main() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--lang=zh-CN'],
  });

  try {
    // 1. History BEFORE
    console.log('📸 Capturing: 04_history_before.png');
    let page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle0' });
    await page.evaluate(() => { localStorage.removeItem('ey-onboarding-seen'); });
    await login(page);
    await page.goto(`${BASE_URL}/history`, { waitUntil: 'networkidle0' });
    await page.waitForSelector('.ant-list', { timeout: 10000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04_history_before.png'), fullPage: false });
    await page.close();

    // 2. History AFTER (with search/filter)
    console.log('📸 Capturing: 04_history_after.png');
    page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });
    await login(page);
    await page.goto(`${BASE_URL}/history`, { waitUntil: 'networkidle0' });
    await page.waitForSelector('.ant-input-search', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 500));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04_history_after.png'), fullPage: false });
    await page.close();

    // 3. Onboarding AFTER
    console.log('📸 Capturing: 03_onboarding_after.png');
    page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle0' });
    await page.evaluate(() => { localStorage.removeItem('ey-onboarding-seen'); });
    await login(page);
    await page.waitForSelector('.onboarding-modal', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03_onboarding_after.png'), fullPage: false });
    await page.close();

    // 4. Copy button AFTER
    console.log('📸 Capturing: 05_copy_after.png');
    page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });
    await login(page);
    await page.evaluate(() => { localStorage.setItem('ey-onboarding-seen', 'true'); });
    // Navigate to an existing history conversation to see messages
    await page.goto(`${BASE_URL}/history`, { waitUntil: 'networkidle0' });
    await page.waitForSelector('.ant-list-item', { timeout: 10000 });
    // Click first conversation
    await page.click('.ant-list-item button');
    await page.waitForSelector('.msg-bubble-assistant', { timeout: 15000 });
    await new Promise(r => setTimeout(r, 1000));
    // Hover over assistant message
    const msgBubble = await page.$('.msg-bubble-assistant');
    if (msgBubble) {
      await msgBubble.hover();
      await new Promise(r => setTimeout(r, 500));
    }
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05_copy_after.png'), fullPage: false });
    await page.close();

    console.log('✅ All screenshots captured!');

  } catch (err) {
    console.error('❌ Screenshot error:', err.message);
  } finally {
    await browser.close();
  }
}

main();
