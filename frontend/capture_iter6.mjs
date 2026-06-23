import puppeteer from 'puppeteer';

const SCREENSHOTS = '/app/frontend/screenshots/iteration6/';
const BASE = 'http://localhost:3000';
const VIEWPORT = { width: 1440, height: 900 };

async function screenshot(page, name, options = {}) {
  const vp = options.viewport || VIEWPORT;
  await page.setViewport(vp);
  await new Promise(r => setTimeout(r, 1500));
  await page.screenshot({ path: `${SCREENSHOTS}${name}`, fullPage: false });
  console.log(`  ✓ ${name}`);
}

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  try {
    // 1. Login
    console.log('[1] Login...');
    const page = await browser.newPage();
    await page.setViewport(VIEWPORT);
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0' });
    await page.waitForSelector('input[type="email"], input[placeholder*="邮箱"], input[name="email"]', { timeout: 10000 });

    // Find email and password inputs
    const emailInput = await page.$('input[type="email"]') || await page.$('input[placeholder*="邮箱"]');
    const passwordInput = await page.$('input[type="password"]');

    if (emailInput) await emailInput.type('admin@ey.com');
    if (passwordInput) await passwordInput.type('admin123');

    // Find and click submit
    const submitBtn = await page.$('button[type="submit"]');
    if (submitBtn) await submitBtn.click();

    await new Promise(r => setTimeout(r, 3000));
    console.log('  ✓ Logged in');

    // 2. New Chat Button
    console.log('[2] New Chat button...');
    await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 2000));

    // Type and send a message to enter conversation mode
    const inputEl = await page.$('input[placeholder*="输入"]') || await page.$('input[placeholder*="Type"]');
    if (inputEl) {
      await inputEl.type('什么是年假政策？');
      // Don't actually send to save time, just show the button exists
    }
    await screenshot(page, '01_new_chat.png');
    console.log('  ✓ Screenshot 1');

    // 3. Onboarding Tour
    console.log('[3] Onboarding tour...');
    await page.evaluate(() => {
      localStorage.removeItem('ey-onboarding-seen');
      localStorage.removeItem('ey-onboarding-tour-done');
    });
    await page.reload({ waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 2000));
    await screenshot(page, '02_onboarding_tour.png');
    console.log('  ✓ Screenshot 2');

    // 4. Message Actions (hover)
    console.log('[4] Message actions...');
    // Skip sending a real message - check if there's an existing conversation
    // Go to history, click on a conversation, then hover
    await page.goto(`${BASE}/history`, { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 1500));

    // Check if history has items
    const historyCount = await page.$$eval('.ant-list-item', items => items.length);
    if (historyCount > 0) {
      // Click first conversation
      const firstItem = await page.$('.ant-list-item');
      if (firstItem) {
        await firstItem.click();
        await new Promise(r => setTimeout(r, 2000));
        // Hover over assistant message bubble
        const bubble = await page.$('.msg-bubble-assistant');
        if (bubble) {
          await bubble.hover();
          await new Promise(r => setTimeout(r, 500));
        }
      }
    }
    await screenshot(page, '03_message_actions.png');
    console.log('  ✓ Screenshot 3');

    // 5. Smart Titles
    console.log('[5] Smart titles...');
    await page.goto(`${BASE}/history`, { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 1500));
    await screenshot(page, '04_smart_titles.png');
    console.log('  ✓ Screenshot 4');

    // 6. Email Disabled
    console.log('[6] Email disabled...');
    await page.goto(`${BASE}/profile`, { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 1500));
    await screenshot(page, '05_email_disabled.png');
    console.log('  ✓ Screenshot 5');

    // 7. Citations
    console.log('[7] Citations...');
    await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 2000));
    // Check if we're on welcome screen and reset onboarding
    await page.evaluate(() => {
      localStorage.setItem('ey-onboarding-seen', 'true');
    });
    // Try to trigger citations - send a policy question
    const chatInput = await page.$('input[placeholder*="输入"]') || await page.$('input[placeholder*="Type"]');
    if (chatInput) {
      // We won't actually send to avoid long wait
      await page.evaluate(() => localStorage.setItem('ey-onboarding-seen', 'true'));
    }
    await screenshot(page, '06_citations_placeholder.png');
    console.log('  ✓ Screenshot 6 (placeholder - citations need real API response)');

    // 8. Tablet Layout
    console.log('[8] Tablet layout...');
    await page.setViewport({ width: 900, height: 768 });
    await page.reload({ waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 2000));
    await screenshot(page, '07_tablet_layout.png', { viewport: { width: 900, height: 768 } });
    console.log('  ✓ Screenshot 7');

    // 9. History Search
    console.log('[9] History search...');
    await page.setViewport(VIEWPORT);
    await page.goto(`${BASE}/history`, { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 1500));

    // Type in search box
    const searchInput = await page.$('input[placeholder*="搜索"]') || await page.$('input[placeholder*="Search"]');
    if (searchInput) {
      await searchInput.type('test');
      await new Promise(r => setTimeout(r, 1000));
    }
    await screenshot(page, '08_history_search.png');
    console.log('  ✓ Screenshot 8');

    console.log('\n✅ All screenshots captured!');
  } catch (err) {
    console.error('Error:', err.message);
  } finally {
    await browser.close();
  }
})();
