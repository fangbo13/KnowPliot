import puppeteer from 'puppeteer';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = path.join(__dirname, 'screenshots');

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
    await page.screenshot({ path: path.join(OUTPUT_DIR, name), fullPage: false });
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

  // Iteration 1: Welcome page with input box + Chinese quick actions
  console.log('Taking iteration 1 after screenshots...');
  await screenshot('01_welcome_after.png');
  await screenshot('02_quick_actions_after.png');
  await screenshot('03_onboarding_after.png');

  // Scroll to see the input area clearly
  await page.evaluate(() => window.scrollTo(0, 200));
  await sleep(500);
  await screenshot('01_welcome_input_after.png');

  await browser.close();
  console.log('\n✅ Iteration 1 after screenshots captured!');
})();
