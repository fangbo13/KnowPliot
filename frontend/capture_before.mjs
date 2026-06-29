import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = path.join(__dirname, 'screenshots');

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--lang=zh-CN'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });

  async function screenshot(name, waitFor = 1000) {
    await sleep(waitFor);
    const filePath = path.join(OUTPUT_DIR, name);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`✅ ${name}`);
  }

  // Login
  console.log('Logging in...');
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle0', timeout: 15000 });
  await sleep(1000);
  const submitBtn = await page.$('button[type="submit"]');
  if (submitBtn) await submitBtn.click();
  await page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 15000 }).catch(() => {});
  await sleep(2000);

  // 01 Welcome page before (problem: no input box)
  console.log('Taking before screenshots...');
  await screenshot('01_welcome_before.png');

  // 02 Quick actions before (problem: English content)
  await screenshot('02_quick_actions_before.png');

  // 03 Onboarding before (problem: no guidance)
  await screenshot('03_onboarding_before.png');

  // 04 Sidebar before (problem: fixed, no collapse)
  await screenshot('04_sidebar_before.png');

  // 05 Lang switch before (problem: deep entry)
  await screenshot('05_lang_switch_before.png');

  // Navigate to profile for lang switch screenshot
  await page.goto('http://localhost:3000/profile', { waitUntil: 'networkidle0', timeout: 15000 });
  await screenshot('05_lang_entry_before.png');

  // 06 Login page before (problem: English brand panel)
  // Logout first
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle0', timeout: 15000 });
  await screenshot('06_login_before.png');

  // 07 Profile before (problem: disabled email field)
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle0', timeout: 15000 });
  await sleep(1000);
  const loginBtn = await page.$('button[type="submit"]');
  if (loginBtn) await loginBtn.click();
  await page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 15000 }).catch(() => {});
  await sleep(2000);
  await page.goto('http://localhost:3000/profile', { waitUntil: 'networkidle0', timeout: 15000 });
  await screenshot('07_profile_before.png');

  await browser.close();
  console.log('\n✅ All before screenshots captured!');
})();
