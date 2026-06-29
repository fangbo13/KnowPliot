// Test script for verifying Bug #1, #2, #3 fixes
import puppeteer from 'puppeteer';

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  console.log('=== Step 1: Login ===');
  await page.goto('http://localhost:3000/login', { waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 2000));
  await page.screenshot({ path: 'screenshots/01_login_page.png', fullPage: true });
  console.log('Screenshot: login page');

  // Fill login form - use more specific selectors
  const emailInput = await page.$('input[autocomplete="email"]');
  if (emailInput) {
    await emailInput.click({ clickCount: 3 });
    await emailInput.type('admin@ey.com');
  }

  const passwordInput = await page.$('input[type="password"]');
  if (passwordInput) {
    await passwordInput.click({ clickCount: 3 });
    await passwordInput.type('admin123');
  }

  // Submit login
  const submitBtn = await page.$('button[type="submit"]');
  if (submitBtn) {
    await submitBtn.click();
    await new Promise(r => setTimeout(r, 3000));
  }

  await page.screenshot({ path: 'screenshots/02_chat_page.png', fullPage: true });
  console.log('Screenshot: chat page after login');

  console.log('\n=== Step 2: Check input box position (Bug #3) ===');
  const inputBoxResult = await page.evaluate(() => {
    // Look for the fixed position container
    const allDivs = document.querySelectorAll('div');
    let fixedDiv = null;
    for (const div of allDivs) {
      if (div.style.position === 'fixed' && div.style.bottom !== undefined) {
        fixedDiv = div;
        break;
      }
    }
    if (!fixedDiv) return { found: false };
    const rect = fixedDiv.getBoundingClientRect();
    return {
      found: true,
      position: 'fixed',
      rect: { top: rect.top, bottom: rect.bottom },
      viewportHeight: window.innerHeight,
      isNearBottom: rect.bottom >= window.innerHeight - 50,
    };
  });
  console.log('Input box check:', JSON.stringify(inputBoxResult, null, 2));
  const bug3Fixed = inputBoxResult.found && inputBoxResult.isNearBottom;
  console.log(`Bug #3 (input position): ${bug3Fixed ? '✅ FIXED' : '❌ NOT FIXED'}\n`);

  console.log('=== Step 3: Navigate to History page ===');
  // Click history nav item by text content
  const historyNav = await page.evaluateHandle(() => {
    const menus = document.querySelectorAll('.ant-menu-item');
    for (const menu of menus) {
      if (menu.textContent.includes('历史') || menu.textContent.includes('History')) {
        return menu;
      }
    }
    return null;
  });
  if (historyNav) {
    await historyNav.asElement().click();
  } else {
    // Fallback: navigate directly
    await page.goto('http://localhost:3000/history', { waitUntil: 'domcontentloaded' });
  }
  await new Promise(r => setTimeout(r, 2000));
  await page.screenshot({ path: 'screenshots/03_history_page.png', fullPage: true });
  console.log('Screenshot: history page');

  console.log('\n=== Step 4: Click a conversation (Bug #1) ===');
  const urlBefore = page.url();
  console.log('URL before click:', urlBefore);

  // Click first conversation item
  const conversationBtns = await page.$$('.ant-list-item .ant-btn, .ant-list-item button');
  if (conversationBtns.length > 0) {
    await conversationBtns[0].click();
    await new Promise(r => setTimeout(r, 3000));

    const urlAfter = page.url();
    console.log('URL after click:', urlAfter);
    const bug1Fixed = urlAfter.includes('/history') && !urlAfter.includes('/chat');
    console.log(`Bug #1 (stay on history): ${bug1Fixed ? '✅ FIXED' : ' NOT FIXED'}\n`);

    await page.screenshot({ path: 'screenshots/04_history_conversation.png', fullPage: true });
    console.log('Screenshot: viewing conversation in history page');

    console.log('=== Step 5: Go back to history list ===');
    const backBtn = await page.$('.ant-btn:has(.anticon-arrow-left), button .anticon-arrow-left');
    if (backBtn) {
      await backBtn.click();
    } else {
      // Fallback: click the back button by finding it in the card title
      await page.evaluate(() => {
        const btn = document.querySelector('button .anticon-arrow-left')?.closest('button');
        if (btn) btn.click();
      });
    }
    await new Promise(r => setTimeout(r, 1500));
    await page.screenshot({ path: 'screenshots/05_history_back.png', fullPage: true });
    console.log('Screenshot: back to history list');

    console.log('\n=== Step 6: Navigate to Chat page (Bug #2) ===');
    const chatNav = await page.evaluateHandle(() => {
      const menus = document.querySelectorAll('.ant-menu-item');
      for (const menu of menus) {
        if (menu.textContent.includes('对话') || menu.textContent.includes('Chat')) {
          return menu;
        }
      }
      return null;
    });
    if (chatNav) {
      await chatNav.asElement().click();
    } else {
      await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded' });
    }
    await new Promise(r => setTimeout(r, 3000));
    await page.screenshot({ path: 'screenshots/06_chat_page_after_history.png', fullPage: true });
    console.log('Screenshot: chat page after returning from history');

    // Check page state
    const pageState = await page.evaluate(() => {
      // Check for welcome screen
      const welcomeScreen = document.querySelector('.ant-card .anticon-rocket')?.closest('.ant-card');
      const hasWelcome = !!welcomeScreen;

      // Count message bubbles
      const messageBubbles = document.querySelectorAll('.msg-bubble, .markdown-content');
      const hasMessages = messageBubbles.length > 0;

      return { hasWelcome, messageCount: messageBubbles.length };
    });
    console.log('Chat page state:', JSON.stringify(pageState, null, 2));
    const bug2Fixed = pageState.hasWelcome || pageState.messageCount === 0;
    console.log(`Bug #2 (clean chat on return): ${bug2Fixed ? '✅ FIXED' : '❌ NOT FIXED'}\n`);

    // Re-check input position
    const chatInputCheck = await page.evaluate(() => {
      const allDivs = document.querySelectorAll('div');
      for (const div of allDivs) {
        if (div.style.position === 'fixed') {
          const rect = div.getBoundingClientRect();
          return {
            found: true,
            isNearBottom: rect.bottom >= window.innerHeight - 50,
          };
        }
      }
      return { found: false };
    });
    console.log('Chat input position:', JSON.stringify(chatInputCheck, null, 2));
    const bug3StillFixed = chatInputCheck.found && chatInputCheck.isNearBottom;
    console.log(`Bug #3 (input still fixed): ${bug3StillFixed ? '✅ FIXED' : '❌ NOT FIXED'}`);
  } else {
    console.log('No history items found - cannot test bugs #1 and #2');
  }

  console.log('\n=== Summary ===');
  console.log(`Bug #1 (History stay): ${bug1Fixed ? '✅' : '❌'}`);
  console.log(`Bug #2 (Clean chat): ${bug2Fixed ? '✅' : '❌'}`);
  console.log(`Bug #3 (Input position): ${bug3StillFixed ? '✅' : ''}`);

  console.log('\nScreenshots saved to: screenshots/');
  await browser.close();
})();
