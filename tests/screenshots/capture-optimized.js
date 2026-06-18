const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const SCREENSHOT_DIR = path.join(__dirname, 'ui-optimized');
const BASE_URL = 'http://localhost:5173';

const FAKE_AUTH = JSON.stringify({
  isAuthenticated: true,
  user: {
    id: '1',
    email: 'admin@ey.com',
    username: 'admin',
    is_hr_admin: true,
    language_preference: 'en',
    service_line: 'Consulting',
    office_location: 'Shanghai',
    role_level: 'Senior',
  },
  token: 'fake-token-for-screenshot',
});

async function main() {
  // Create output directory
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
  });

  // --- Desktop (1440px) screenshots ---
  const desktop = await browser.newPage();
  await desktop.setViewport({ width: 1440, height: 900 });

  // Wait helper
  const waitForFonts = async () => {
    await desktop.evaluateHandle('document.fonts.ready');
    await new Promise(r => setTimeout(r, 1500));
  };

  // 1. Login page (no auth needed)
  console.log('Capturing login page...');
  await desktop.goto(BASE_URL + '/login', { waitUntil: 'networkidle0', timeout: 15000 });
  await desktop.waitForSelector('.ant-layout', { timeout: 10000 });
  await waitForFonts();
  await desktop.screenshot({
    path: path.join(SCREENSHOT_DIR, '01_login_page_1440.png'),
    fullPage: false,
  });
  console.log('✓ Login page (1440px)');

  // Set fake auth for protected pages
  await desktop.evaluate((auth) => {
    localStorage.setItem('ey-auth', auth);
    localStorage.setItem('ey-theme', 'light');
  }, FAKE_AUTH);

  // 2. Chat page with welcome screen
  console.log('Capturing welcome screen...');
  await desktop.goto(BASE_URL + '/chat', { waitUntil: 'networkidle0', timeout: 15000 });
  try {
    await desktop.waitForSelector('.ant-card', { timeout: 10000 });
  } catch {
    // Welcome screen may not use ant-card in optimized version
    await new Promise(r => setTimeout(r, 2000));
  }
  await waitForFonts();
  await desktop.screenshot({
    path: path.join(SCREENSHOT_DIR, '02_welcome_screen_1440.png'),
    fullPage: false,
  });
  console.log('✓ Welcome screen (1440px)');

  // 3. Profile page
  console.log('Capturing profile page...');
  await desktop.goto(BASE_URL + '/profile', { waitUntil: 'networkidle0', timeout: 15000 });
  try {
    await desktop.waitForSelector('.ant-card', { timeout: 10000 });
  } catch {
    await new Promise(r => setTimeout(r, 2000));
  }
  await waitForFonts();
  await desktop.screenshot({
    path: path.join(SCREENSHOT_DIR, '03_profile_page_1440.png'),
    fullPage: false,
  });
  console.log('✓ Profile page (1440px)');

  // 4. Profile page - Dark mode
  console.log('Capturing dark mode...');
  const darkBtn = await desktop.$('button[title="Switch to Dark Mode"]');
  if (darkBtn) {
    await darkBtn.click();
    await new Promise(r => setTimeout(r, 1000));
    await desktop.screenshot({
      path: path.join(SCREENSHOT_DIR, '04_profile_dark_1440.png'),
      fullPage: false,
    });
    console.log('✓ Profile page dark (1440px)');

    // Toggle back to light
    const lightBtn = await desktop.$('button[title="Switch to Light Mode"]');
    if (lightBtn) await lightBtn.click();
    await new Promise(r => setTimeout(r, 500));
  }

  // 5. History page
  console.log('Capturing history page...');
  await desktop.goto(BASE_URL + '/history', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise(r => setTimeout(r, 1500));
  await waitForFonts();
  await desktop.screenshot({
    path: path.join(SCREENSHOT_DIR, '05_history_page_1440.png'),
    fullPage: false,
  });
  console.log('✓ History page (1440px)');

  // 6. Knowledge base page
  console.log('Capturing knowledge base page...');
  await desktop.goto(BASE_URL + '/admin/knowledge', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise(r => setTimeout(r, 1500));
  await waitForFonts();
  await desktop.screenshot({
    path: path.join(SCREENSHOT_DIR, '06_knowledge_base_1440.png'),
    fullPage: false,
  });
  console.log('✓ Knowledge base page (1440px)');

  // --- Mobile (375px) screenshots ---
  console.log('\nCapturing mobile screenshots...');
  const mobile = await browser.newPage();
  await mobile.setViewport({ width: 375, height: 812 });

  // Set fake auth on mobile too
  await mobile.goto(BASE_URL + '/login', { waitUntil: 'networkidle0', timeout: 15000 });
  await mobile.evaluate((auth) => {
    localStorage.setItem('ey-auth', auth);
    localStorage.setItem('ey-theme', 'light');
  }, FAKE_AUTH);

  // 7. Mobile login page
  await mobile.screenshot({
    path: path.join(SCREENSHOT_DIR, '07_login_page_375.png'),
    fullPage: false,
  });
  console.log('✓ Login page (375px)');

  // 8. Mobile welcome screen
  await mobile.goto(BASE_URL + '/chat', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise(r => setTimeout(r, 2000));
  await mobile.evaluateHandle('document.fonts.ready');
  await new Promise(r => setTimeout(r, 1000));
  await mobile.screenshot({
    path: path.join(SCREENSHOT_DIR, '08_welcome_screen_375.png'),
    fullPage: false,
  });
  console.log('✓ Welcome screen (375px)');

  // 9. Mobile profile
  await mobile.goto(BASE_URL + '/profile', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise(r => setTimeout(r, 2000));
  await mobile.screenshot({
    path: path.join(SCREENSHOT_DIR, '09_profile_page_375.png'),
    fullPage: false,
  });
  console.log('✓ Profile page (375px)');

  // 10. Tablet (768px) welcome screen
  console.log('\nCapturing tablet screenshots...');
  const tablet = await browser.newPage();
  await tablet.setViewport({ width: 768, height: 1024 });
  await tablet.goto(BASE_URL + '/login', { waitUntil: 'networkidle0', timeout: 15000 });
  await tablet.evaluate((auth) => {
    localStorage.setItem('ey-auth', auth);
    localStorage.setItem('ey-theme', 'light');
  }, FAKE_AUTH);

  await tablet.goto(BASE_URL + '/chat', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise(r => setTimeout(r, 2000));
  await tablet.evaluateHandle('document.fonts.ready');
  await new Promise(r => setTimeout(r, 1000));
  await tablet.screenshot({
    path: path.join(SCREENSHOT_DIR, '10_welcome_screen_768.png'),
    fullPage: false,
  });
  console.log('✓ Welcome screen (768px)');

  await desktop.close();
  await mobile.close();
  await tablet.close();
  await browser.close();

  console.log('\n✅ All screenshots saved to:', SCREENSHOT_DIR);

  // List files
  const files = fs.readdirSync(SCREENSHOT_DIR);
  files.forEach(f => {
    const stat = fs.statSync(path.join(SCREENSHOT_DIR, f));
    console.log(`  ${f} (${(stat.size / 1024).toFixed(0)} KB)`);
  });
}

main().catch(err => {
  console.error('Screenshot error:', err);
  process.exit(1);
});
